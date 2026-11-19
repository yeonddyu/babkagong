"""기본 Tool 레지스트리 구성 (F3001).

Agent 는 build_default_registry() 가 돌려준 레지스트리만 사용한다.
"""
from __future__ import annotations

from app.clients.kakao_local import KakaoLocalClient
from app.clients.kma import KMAClient
from app.clients.redtable import RedtableClient
from app.clients.seoul_opendata import SeoulOpenDataClient
from app.core.config import Settings, load_settings
from app.datasets.cache import JsonCache
from app.datasets.restaurants import GangnamLicenseDataset, RedtableDetailDataset, RedtableRestaurantDataset
from app.tools import nearby_cafes, restaurant_candidates, restaurant_details, weather
from app.tools.registry import ToolRegistry


def build_default_registry(settings: Settings | None = None, *, session=None, today_fn=None, now_fn=None) -> ToolRegistry:
    """session/today_fn 은 테스트에서 HTTP 와 날짜를 고정하기 위해 주입한다."""
    settings = settings or load_settings()
    cache = JsonCache(settings.cache_dir, settings.cache_ttl_hours)
    redtable_client = RedtableClient(settings.redtable_api_key, timeout=settings.http_timeout_sec, session=session)
    seoul_client = SeoulOpenDataClient(settings.seoul_openapi_key, timeout=settings.http_timeout_sec, session=session)
    kakao_client = KakaoLocalClient(settings.kakao_rest_api_key, timeout=settings.http_timeout_sec, session=session)

    redtable_restaurants = RedtableRestaurantDataset(redtable_client, cache)
    redtable_details = RedtableDetailDataset(redtable_client, cache, redtable_restaurants)
    gangnam_license = GangnamLicenseDataset(seoul_client, cache)

    registry = ToolRegistry()
    date_kw = {"today_fn": today_fn} if today_fn else {}
    registry.register(restaurant_candidates.create_tool(redtable_restaurants, gangnam_license, **date_kw))
    registry.register(restaurant_details.create_tool(redtable_restaurants, redtable_details, gangnam_license))
    rest_food = GangnamLicenseDataset.rest_food(seoul_client, cache)
    registry.register(nearby_cafes.create_tool(kakao_client, rest_food, **date_kw))
    kma_client = KMAClient(settings.kma_api_key, timeout=settings.http_timeout_sec, session=session)
    registry.register(weather.create_tool(kma_client, **({"now_fn": now_fn} if now_fn else {})))
    return registry
