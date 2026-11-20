"""서울 지하철역 목록 (역사마스터 → 역) 과 발화에서 역 찾기 (Mock)."""
from __future__ import annotations

from app.datasets.stations import StationDirectory, build_stations


def row(name, route, lat, lng):
    return {"BLDN_ID": "x", "BLDN_NM": name, "ROUTE": route, "LAT": str(lat), "LOT": str(lng)}


ROWS = [
    row("홍대입구", "2호선", 37.55679, 126.923708), row("홍대입구", "경의중앙선", 37.557641, 126.926683),
    row("서울역", "1호선", 37.556228, 126.972135), row("서울역", "4호선", 37.55281, 126.972556),
    row("신촌", "2호선", 37.555134, 126.936893), row("신촌", "경의중앙선", 37.559733, 126.942597),
    row("신논현", "9호선", 37.504598, 127.02506), row("논현", "7호선", 37.511093, 127.021415),
    row("강남구청", "7호선", 37.517186, 127.041303), row("방학", "1호선", 37.667503, 127.044273),
    row("성수", "2호선", 37.544581, 127.055961),
]


class FakeDirectory(StationDirectory):
    def __init__(self, rows):
        super().__init__(None, None)
        self._items = self._builtin() + build_stations(rows)

    def stations(self):
        return self._items


def test_build_merges_transfer_lines_and_splits_far_same_names():
    by = {s.name: s for s in build_stations(ROWS)}
    assert by["홍대입구역"].lines == ("2호선", "경의중앙선")  # 약 280m → 한 역
    assert by["서울역"].base == "서울" and len(by["서울역"].lines) == 2  # '서울역' 은 그대로, 역을 두 번 붙이지 않음
    assert {"신촌역(2호선)", "신촌역(경의중앙선)"} <= set(by)  # 약 700m 떨어진 같은 이름 → 노선으로 구분


def test_find_in_text():
    d = FakeDirectory(ROWS)
    f = lambda t: (d.find_in_text(t) or None) and d.find_in_text(t).name  # noqa: E731
    assert f("홍대입구역 근처 점심") == "홍대입구역"
    assert f("홍대에서 점심 먹고 카공") == "홍대입구역"  # 별칭
    assert f("신논현역 점심") == "신논현역"  # '논현역' 과 헷갈리지 않음
    assert f("논현역 점심") == "논현역"
    assert f("성수 근처 점심") == "성수역"  # 역 없이 이름 + 근처
    assert f("강남구청역 점심") == "강남구청역"  # '강남' 보다 긴 이름 우선
    assert f("강남 점심") == "강남역"  # 기존 동작 유지
    assert f("방학이라 점심 추천해줘") is None  # 흔한 낱말은 역으로 보지 않음
    assert f("서울에서 점심") is None  # '서울' 만으로는 서울역 아님
    assert f("서울역 점심") == "서울역"
    assert f("점심 추천해줘") is None


def test_get_and_nearest_other():
    d = FakeDirectory(ROWS)
    assert d.get("홍대입구").name == "홍대입구역" and d.get("홍대입구역").name == "홍대입구역"
    assert d.get("없는역") is None
    assert d.nearest_other("강남역").name == "신논현역"  # 약 750m (역삼역은 약 830m)
    assert d.nearest_other("방학역") is None  # 2km 안에 다른 역이 없음


def test_without_list_only_builtin_stations():
    d = StationDirectory(None, None)
    assert d.names() == ["강남역", "역삼역"]
    assert d.refresh() is False


def test_names_normalised_and_suffix_only_when_needed():
    rows = [row("서울", "1호선", 37.5562, 126.9721), row("서울역", "경의중앙선", 37.5572, 126.9710),  # 이름 표기가 달라도 한 역
            row("잠실(송파구청)", "2호선", 37.5133, 127.1001), row("잠실(송파구청)", "8호선", 37.5145, 127.1038),
            row("양평", "5호선", 37.5258, 126.8865), row("양평", "경의중앙선", 37.4925, 127.4917)]  # 서울 / 경기 양평
    seoul_only = build_stations(rows, keep=lambda st: st.longitude < 127.3)
    names = sorted(s.name for s in seoul_only)
    assert names == ["서울역", "양평역", "잠실역"]  # 중복 없음, 괄호 제거, 걸러진 뒤 하나뿐이면 노선 표시 안 함
    both = build_stations(rows)
    assert sorted(s.name for s in both if s.base == "양평") == ["양평역(5호선)", "양평역(경의중앙선)"]
