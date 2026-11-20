"""추가 기능 — 날씨 조회 Tool: get_weather_context (기상청 단기예보).

방문 날짜·시각의 기온·강수확률·강수형태·하늘상태를 돌려준다. 실제로 사용한 발표 시각과
예보 시각을 함께 표시하고, 응답에 없는 항목은 null 로 둔다.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Callable, Literal

from pydantic import BaseModel, Field, model_validator

from app.clients.kma import BASE_HOURS, KMAClient, latlon_to_grid
from app.core.errors import ErrorCode, ExternalAPIError
from app.datasets.stations import StationDirectory
from app.datasets.cache import KST, now_kst
from app.tools.common import ToolError, ToolKind, ToolSpec

TOOL_NAME = "get_weather_context"
RELEASE_DELAY_MIN = 10  # 발표 후 API 제공까지 대기
PTY_LABELS = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
SKY_LABELS = {"1": "맑음", "3": "구름많음", "4": "흐림"}


class WeatherInput(BaseModel):
    area: str | None = Field(default=None, max_length=30, description="서비스 역 이름. 위경도를 주지 않으면 필수")
    latitude: float | None = Field(default=None, ge=33.0, le=39.0)
    longitude: float | None = Field(default=None, ge=124.0, le=132.0)
    visit_date: date | None = Field(default=None, description="방문 날짜. 생략하면 오늘(KST)")
    visit_time: time | None = Field(default=None, description="방문 시각(HH:MM). 생략하면 현재 시각 이후 가장 가까운 정시")

    @model_validator(mode="after")
    def _location(self) -> "WeatherInput":
        if self.area is None and (self.latitude is None or self.longitude is None):
            raise ValueError("area 또는 latitude·longitude 가 필요합니다")
        return self


class WeatherOutput(BaseModel):
    location: dict[str, float | str | None]
    grid: dict[str, int]
    requested: dict[str, str | None]
    forecast_datetime: str = Field(description="실제로 사용한 예보 시각 (정시)")
    base_datetime: str = Field(description="사용한 예보의 기상청 발표 시각")
    default_applied: list[str]
    temperature_c: float | None
    precipitation_probability: int | None = Field(description="강수확률(%)")
    precipitation_type: str | None = Field(description="강수형태 (없음/비/비·눈/눈/소나기)")
    sky: str | None = Field(description="하늘상태 (맑음/구름많음/흐림)")
    precipitation_amount: str | None = Field(description="1시간 강수량 원문 (예: 강수없음, 1mm)")
    humidity: int | None
    wind_speed_ms: float | None
    missing_fields: list[str]
    notes: list[str]
    source: str = "기상청 단기예보 조회서비스(getVilageFcst)"


DESCRIPTION = (
    "방문 날짜·시각의 날씨(기온, 강수확률, 비·눈 여부)를 반영해 음식점·카페 추천 우선순위를 정해야 할 때 사용한다. "
    "지역(서비스 역 이름) 또는 위경도와 방문 날짜·시각을 넣는다. 오늘부터 약 3일 이내 예보만 제공한다."
)


def latest_base(at: datetime) -> datetime:
    """at 시점에 조회 가능한 가장 최근 발표 시각."""
    ready = at - timedelta(minutes=RELEASE_DELAY_MIN)
    candidates = [h for h in BASE_HOURS if h <= ready.hour]
    if candidates:
        return ready.replace(hour=max(candidates), minute=0, second=0, microsecond=0)
    prev = ready - timedelta(days=1)
    return prev.replace(hour=23, minute=0, second=0, microsecond=0)


def base_before(dt: datetime) -> datetime:
    """dt 보다 앞선 가장 최근 발표 시각."""
    t = dt - timedelta(minutes=1)
    candidates = [h for h in BASE_HOURS if h <= t.hour]
    if candidates:
        return t.replace(hour=max(candidates), minute=0, second=0, microsecond=0)
    return (t - timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)


def _num(value, cast):
    try:
        return cast(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def create_tool(client: KMAClient, *, now_fn: Callable[[], datetime] = now_kst,
                stations: StationDirectory | None = None) -> ToolSpec:
    def run(params: WeatherInput) -> WeatherOutput:
        now = now_fn()
        defaults: list[str] = []
        notes: list[str] = []
        if params.latitude is not None and params.longitude is not None:
            lat, lon, label = params.latitude, params.longitude, params.area
        else:
            station = (stations or StationDirectory(None, None)).get(params.area)
            if station is None:
                raise ToolError(ErrorCode.INVALID_INPUT, f"서비스 역 목록에서 '{params.area}' 을(를) 찾지 못했습니다.")
            lat, lon, label = station.latitude, station.longitude, station.name
        nx, ny = latlon_to_grid(lat, lon)

        visit_date = params.visit_date or now.date()
        if params.visit_date is None:
            defaults.append("visit_date=오늘")
        if params.visit_time is None:
            target = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            if params.visit_date is not None and params.visit_date != now.date():
                target = datetime.combine(visit_date, time(12, 0), KST)
            defaults.append(f"visit_time={target.strftime('%H:%M')}")
        else:
            target = datetime.combine(visit_date, params.visit_time, KST)
        forecast_dt = target.replace(minute=0, second=0, microsecond=0)
        if params.visit_time and params.visit_time.minute:
            notes.append(f"예보는 정시 단위라 {params.visit_time.strftime('%H:%M')} 대신 {forecast_dt.strftime('%H:00')} 예보를 사용했습니다.")

        if forecast_dt.date() < now.date():
            raise ToolError(ErrorCode.NO_RESULT, "지난 날짜의 예보는 단기예보 API 로 조회할 수 없습니다.")
        if forecast_dt > now + timedelta(days=3):
            raise ToolError(ErrorCode.NO_RESULT, "단기예보는 약 3일 이내만 제공되어 해당 날짜의 날씨를 확인할 수 없습니다.")

        # 예보는 발표 시각 이후 시각부터 들어 있으므로 '조회 가능한 최신 발표'와 '예보 시각 직전 발표' 중 이른 것을 쓴다
        base = min(latest_base(now), base_before(forecast_dt))
        if forecast_dt < now.replace(minute=0, second=0, microsecond=0):
            notes.append("이미 지난 시각이라 그 시각 이전에 발표된 예보값을 사용했습니다(실측값 아님).")

        result = client.fetch_forecast(base.strftime("%Y%m%d"), base.strftime("%H%M"), nx, ny)
        fd, ft = forecast_dt.strftime("%Y%m%d"), forecast_dt.strftime("%H%M")
        values = {it.get("category"): it.get("fcstValue") for it in result.items if it.get("fcstDate") == fd and it.get("fcstTime") == ft}
        if not values:
            raise ToolError(ErrorCode.NO_RESULT, f"{forecast_dt.strftime('%m/%d %H:00')} 예보를 찾지 못했습니다.")

        out = {
            "temperature_c": _num(values.get("TMP"), float),
            "precipitation_probability": _num(values.get("POP"), int),
            "precipitation_type": PTY_LABELS.get(str(values.get("PTY"))) if values.get("PTY") is not None else None,
            "sky": SKY_LABELS.get(str(values.get("SKY"))) if values.get("SKY") is not None else None,
            "precipitation_amount": values.get("PCP"),
            "humidity": _num(values.get("REH"), int),
            "wind_speed_ms": _num(values.get("WSD"), float),
        }
        missing = [k for k, v in out.items() if v is None]
        return WeatherOutput(
            location={"label": label, "latitude": lat, "longitude": lon},
            grid={"nx": nx, "ny": ny},
            requested={"visit_date": params.visit_date.isoformat() if params.visit_date else None,
                       "visit_time": params.visit_time.strftime("%H:%M") if params.visit_time else None},
            forecast_datetime=forecast_dt.isoformat(),
            base_datetime=base.isoformat(),
            default_applied=defaults,
            missing_fields=missing,
            notes=notes,
            **out,
        )

    return ToolSpec(
        name=TOOL_NAME,
        description=DESCRIPTION,
        kind=ToolKind.EXTERNAL_API,
        providers=["기상청 단기예보 조회서비스 (공공데이터포털)"],
        input_model=WeatherInput,
        output_model=WeatherOutput,
        error_codes=[ErrorCode.INVALID_INPUT, ErrorCode.MISSING_API_KEY, ErrorCode.NO_RESULT, ErrorCode.TIMEOUT, ErrorCode.API_ERROR],
        func=run,
    )
