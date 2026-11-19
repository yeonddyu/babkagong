"""환경변수 설정과 LLM Provider 선택 - 단위 테스트 (외부 호출 없음)."""
from __future__ import annotations

from dataclasses import replace

from app.core.config import DEFAULT_GMS_BASE_URL, DEFAULT_LLM_MODEL, load_settings
from app.core.llm_provider import create_llm, llm_status

NAMES = ("REDTABLE_API_KEY", "SEOUL_FOOD_API_TOKEN", "SEOUL_OPENAPI_KEY", "SEOUL_OPEN_API_KEY", "OPENAI_API_KEY",
         "GMS_API_KEY", "GMS_BASE_URL", "GMS_MODEL", "AI_PROVIDER", "KMA_API_KEY", "KAKAO_REST_API_KEY")


def _clear(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_alias_env_names(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SEOUL_FOOD_API_TOKEN", "a")
    monkeypatch.setenv("SEOUL_OPEN_API_KEY", "b")
    s = load_settings(load_env_file=False)
    assert s.redtable_api_key == "a" and s.seoul_openapi_key == "b"


def test_key_status_hides_values(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GMS_API_KEY", "secret-gms")
    status = load_settings(load_env_file=False).key_status()
    assert status["GMS_API_KEY"] is True and status["OPENAI_API_KEY"] is False
    assert "secret-gms" not in str(status)


def test_gms_is_default_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GMS_API_KEY", "gms-key")
    s = load_settings(load_env_file=False)
    st = llm_status(s)
    assert (st.available, st.provider, st.model) == (True, "gms", DEFAULT_LLM_MODEL)
    llm = create_llm(s)
    assert llm.model_name == DEFAULT_LLM_MODEL and str(llm.openai_api_base).rstrip("/") == DEFAULT_GMS_BASE_URL
    assert llm.openai_api_key.get_secret_value() == "gms-key"


def test_gms_model_placeholder_ignored(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GMS_MODEL", "SSAFY에서_사용_허가된_모델_ID")
    assert load_settings(load_env_file=False).gms_model is None
    monkeypatch.setenv("GMS_MODEL", "gpt-4.1-mini")
    assert load_settings(load_env_file=False).gms_model == "gpt-4.1-mini"


def test_gms_custom_base_url_and_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GMS_API_KEY", "k")
    monkeypatch.setenv("GMS_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("GMS_MODEL", "gpt-4.1-mini")
    llm = create_llm(load_settings(load_env_file=False))
    assert llm.model_name == "gpt-4.1-mini" and str(llm.openai_api_base).startswith("https://example.test/v1")


def test_no_gms_key_means_rule_based(monkeypatch):
    _clear(monkeypatch)
    s = load_settings(load_env_file=False)
    assert llm_status(s).available is False and create_llm(s) is None
    assert "GMS_API_KEY" in llm_status(s).reason


def test_openai_provider_when_selected(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    s = replace(load_settings(load_env_file=False), openai_api_key="sk-test")
    llm = create_llm(s)
    assert llm_status(s).provider == "openai" and llm.model_name == s.openai_model
