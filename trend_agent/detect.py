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


@dataclass
class Spike:
    start: date
    end: date
    peak_date: date
    peak_value: float
    baseline_median: float  # 대표일 직전 28일 중앙값
    ratio: float | None      # peak / median, 기준선 0이면 None
    z: float


@dataclass
class Detection:
    series: list[tuple[date, float]]
    observed_days: int  # API가 실제로 돌려준 날 수 (0 채우기 전)
    insufficient: bool
    spikes: list[Spike] = field(default_factory=list)


def fill_missing(data, start: date, end: date) -> list[tuple[date, float]]:
    """검색어트렌드 data([{period, ratio}])를 start~end 일별 시계열로. 누락일은 0 (ADR 0001)."""
    by_day = {date.fromisoformat(d["period"]): float(d["ratio"]) for d in data}
    n = (end - start).days + 1
    return [(start + timedelta(days=i), by_day.get(start + timedelta(days=i), 0.0)) for i in range(n)]


def _score(window: list[float], x: float) -> tuple[float, float, float | None]:
    med = median(window)
    mad = median(abs(v - med) for v in window)
    scale = max(1.4826 * mad, 0.1 * med, 1.0)
    ratio = x / med if med > 0 else None
    return med, (x - med) / scale, ratio


def detect_spikes(
    series: list[tuple[date, float]],
    baseline_days: int = BASELINE_DAYS,
    z_min: float = Z_MIN,
    ratio_min: float = RATIO_MIN,
    index_min: float = INDEX_MIN,
    max_gap: int = MAX_GAP,
) -> list[Spike]:
    values = [v for _, v in series]
    hits = []  # (index, median, z, ratio)
    for i in range(baseline_days, len(values)):
        x = values[i]
        med, z, ratio = _score(values[i - baseline_days:i], x)
        if z >= z_min and x >= index_min and (ratio is None or ratio >= ratio_min):
            hits.append((i, med, z, ratio))

    groups: list[list[tuple]] = []
    for h in hits:
        if groups and h[0] - groups[-1][-1][0] <= max_gap + 1:
            groups[-1].append(h)
        else:
            groups.append([h])

    spikes = []
    for g in groups:
        i, med, z, ratio = max(g, key=lambda h: values[h[0]])
        spikes.append(Spike(
            start=series[g[0][0]][0],
            end=series[g[-1][0]][0],
            peak_date=series[i][0],
            peak_value=values[i],
            baseline_median=med,
            ratio=ratio,
            z=z,
        ))
    return spikes


def detect(data, start: date, end: date, min_observed: int = MIN_OBSERVED, **params) -> Detection:
    """API 응답 data → 0 채우기 → 탐지. 관측일이 너무 적으면 탐지하지 않는다."""
    observed = sum(1 for d in data if start <= date.fromisoformat(d["period"]) <= end)
    series = fill_missing(data, start, end)
    if observed < min_observed:
        return Detection(series, observed, insufficient=True)
    return Detection(series, observed, insufficient=False, spikes=detect_spikes(series, **params))
