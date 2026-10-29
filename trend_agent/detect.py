"""급등 탐지 (ADR 0002). 계산은 전부 여기서 하고, LLM은 결과 숫자를 인용만 한다."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

BASELINE_DAYS = 28
Z_MIN = 3.5
RATIO_MIN = 3.0
INDEX_MIN = 20.0
MAX_GAP = 1
MIN_OBSERVED = 14
WEEKDAY_WEEKS = 4
WEEKDAY_MARGIN = 1.5  # 같은 요일이 이만큼 높을 때만 요일 주기로 본다
MIN_DISTINCT = 20


@dataclass
class Spike:
    start: date
    end: date
    peak_date: date
    peak_value: float
    baseline_median: float  # 대표일 기준선: 직전 28일 중앙값, 요일 주기가 있으면 직전 4주 같은 요일 중앙값
    baseline_kind: str       # "rolling"(28일) | "same_weekday"(같은 요일)
    ratio: float | None      # peak / baseline, 기준선 0이면 None
    z: float


@dataclass
class Detection:
    series: list[tuple[date, float]]
    observed_days: int  # API가 실제로 돌려준 날 수 (0 채우기 전)
    insufficient: bool
    reason: str | None = None  # "few_observed_days" | "low_volume"
    spikes: list[Spike] = field(default_factory=list)


def fill_missing(data, start: date, end: date) -> list[tuple[date, float]]:
    """검색어트렌드 data([{period, ratio}])를 start~end 일별 시계열로. 누락일은 0 (ADR 0001)."""
    by_day = {date.fromisoformat(d["period"]): float(d["ratio"]) for d in data}
    n = (end - start).days + 1
    return [(start + timedelta(days=i), by_day.get(start + timedelta(days=i), 0.0)) for i in range(n)]


def _score(window: list[float], same_weekday: list[float], x: float):
    """기준선 = 28일 중앙값. 단, 같은 요일 중앙값이 1.5배 이상이면 그쪽 (로또 토·일 같은 요일 주기)."""
    med = median(window)
    mad = median(abs(v - med) for v in window)
    wd = median(same_weekday)
    base, kind = (wd, "same_weekday") if wd >= WEEKDAY_MARGIN * med and wd > 0 else (med, "rolling")
    scale = max(1.4826 * mad, 0.1 * base, 1.0)
    ratio = x / base if base > 0 else None
    return base, kind, (x - base) / scale, ratio


def detect_spikes(
    series: list[tuple[date, float]],
    baseline_days: int = BASELINE_DAYS,
    z_min: float = Z_MIN,
    ratio_min: float = RATIO_MIN,
    index_min: float = INDEX_MIN,
    max_gap: int = MAX_GAP,
) -> list[Spike]:
    values = [v for _, v in series]
    start = max(baseline_days, 7 * WEEKDAY_WEEKS)
    hits = []  # (index, base, kind, z, ratio)
    for i in range(start, len(values)):
        x = values[i]
        same_weekday = [values[i - 7 * k] for k in range(1, WEEKDAY_WEEKS + 1)]
        base, kind, z, ratio = _score(values[i - baseline_days:i], same_weekday, x)
        if z >= z_min and x >= index_min and (ratio is None or ratio >= ratio_min):
            hits.append((i, base, kind, z, ratio))

    groups: list[list[tuple]] = []
    for h in hits:
        if groups and h[0] - groups[-1][-1][0] <= max_gap + 1:
            groups[-1].append(h)
        else:
            groups.append([h])

    spikes = []
    for g in groups:
        i, base, kind, z, ratio = max(g, key=lambda h: values[h[0]])
        spikes.append(Spike(
            start=series[g[0][0]][0],
            end=series[g[-1][0]][0],
            peak_date=series[i][0],
            peak_value=values[i],
            baseline_median=base,
            baseline_kind=kind,
            ratio=ratio,
            z=z,
        ))
    return spikes


def detect(data, start: date, end: date, min_observed: int = MIN_OBSERVED,
           min_distinct: int = MIN_DISTINCT, **params) -> Detection:
    """API 응답 data → 0 채우기 → 탐지. 판단 근거가 부족하면 탐지하지 않는다.

    low_volume: 검색 수가 한 자릿수면 지수가 몇 가지 값으로만 계단진다 (라이브: 장호열 6종류).
    """
    in_range = [float(d["ratio"]) for d in data if start <= date.fromisoformat(d["period"]) <= end]
    series = fill_missing(data, start, end)
    observed = len(in_range)
    if observed < min_observed:
        return Detection(series, observed, insufficient=True, reason="few_observed_days")
    if len({v for v in in_range if v > 0}) < min_distinct:
        return Detection(series, observed, insufficient=True, reason="low_volume")
    return Detection(series, observed, insufficient=False, spikes=detect_spikes(series, **params))
