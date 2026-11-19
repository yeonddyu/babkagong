"""환경변수 설정과 LLM Provider 선택 - 단위 테스트 (외부 호출 없음)."""
from __future__ import annotations

from dataclasses import replace

from app.core.config import load_settings
from app.core.llm_provider import create_llm, llm_status


def _clear(monkeypatch):
    for name in ("REDTABLE_API_KEY", "SEOUL_FOOD_API_TOKEN", "SEOUL_OPENAPI_KEY", "SEOUL_OPEN_API_KEY", "OPENAI_API_KEY",
                 "GMS_API_KEY", "AI_PROVIDER", "KMA_API_KEY", "KAKAO_REST_API_KEY"):
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


def test_gms_provider_not_used(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "gms")
    monkeypatch.setenv("GMS_API_KEY", "x")
    s = load_settings(load_env_file=False)
    st = llm_status(s)
    assert st.provider == "openai" and st.available is False  # OpenAI 키 없음 → GMS 로 대체하지 않음
    assert create_llm(s) is None


def test_openai_llm_created_when_key_present(monkeypatch):
    _clear(monkeypatch)
    s = replace(load_settings(load_env_file=False), openai_api_key="sk-test")
    llm = create_llm(s)
    assert llm is not None and llm.model_name == s.openai_model
