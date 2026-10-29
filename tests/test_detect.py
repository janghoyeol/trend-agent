"""급등 탐지 테스트 (ADR 0002). 실행: python -m unittest -v"""
import unittest
from datetime import date, timedelta

from trend_agent.detect import detect, detect_spikes, fill_missing

D0 = date(2026, 8, 1)


def series(values):
    return [(D0 + timedelta(days=i), float(v)) for i, v in enumerate(values)]


def noisy(n, base=10.0):
    # 결정적 잔떨림: base ±1
    return [base + ((i * 7) % 3 - 1) for i in range(n)]


def varied(n, base=10.0):
    # 실데이터처럼 값 종류가 많은 잔떨림: base ±1, 최대 101종류
    return [base + (i * 37 % 101) / 50 - 1 for i in range(n)]


def to_data(values, keep=lambda d: True):
    return [{"period": d.isoformat(), "ratio": x} for d, x in series(values) if keep(d)]


class FillMissingTest(unittest.TestCase):
    def test_fills_gaps_with_zero_inclusive(self):
        data = [{"period": "2026-08-02", "ratio": 5.0}, {"period": "2026-08-04", "ratio": 7.5}]
        got = fill_missing(data, date(2026, 8, 1), date(2026, 8, 5))
        self.assertEqual([v for _, v in got], [0.0, 5.0, 0.0, 7.5, 0.0])
        self.assertEqual(got[0][0], date(2026, 8, 1))
        self.assertEqual(got[-1][0], date(2026, 8, 5))

    def test_ignores_out_of_range(self):
        data = [{"period": "2026-07-31", "ratio": 9.0}, {"period": "2026-08-01", "ratio": 1.0}]
        got = fill_missing(data, date(2026, 8, 1), date(2026, 8, 2))
        self.assertEqual([v for _, v in got], [1.0, 0.0])


class DetectSpikesTest(unittest.TestCase):
    def test_flat_noise_has_no_spike(self):
        self.assertEqual(detect_spikes(series(noisy(90))), [])

    def test_single_spike(self):
        v = noisy(90)
        v[60] = 100
        spikes = detect_spikes(series(v))
        self.assertEqual(len(spikes), 1)
        s = spikes[0]
        self.assertEqual(s.peak_date, D0 + timedelta(days=60))
        self.assertEqual((s.start, s.end), (s.peak_date, s.peak_date))
        self.assertEqual(s.peak_value, 100)
        self.assertEqual(s.baseline_median, 10.0)
        self.assertAlmostEqual(s.ratio, 10.0)
        self.assertGreater(s.z, 3.5)

    def test_consecutive_days_merge_into_one_event(self):
        v = noisy(90)
        v[50:53] = [60, 100, 70]
        spikes = detect_spikes(series(v))
        self.assertEqual(len(spikes), 1)
        s = spikes[0]
        self.assertEqual(s.start, D0 + timedelta(days=50))
        self.assertEqual(s.end, D0 + timedelta(days=52))
        self.assertEqual(s.peak_date, D0 + timedelta(days=51))
        self.assertEqual(s.peak_value, 100)

    def test_one_day_gap_merges_but_long_gap_splits(self):
        v = noisy(90)
        v[40], v[42] = 80, 90  # 사이 1일 공백 → 한 사건
        v[70] = 100            # 멀리 떨어짐 → 별도 사건
        spikes = detect_spikes(series(v))
        self.assertEqual(len(spikes), 2)
        self.assertEqual(spikes[0].start, D0 + timedelta(days=40))
        self.assertEqual(spikes[0].end, D0 + timedelta(days=42))
        self.assertEqual(spikes[0].peak_value, 90)
        self.assertEqual(spikes[1].peak_date, D0 + timedelta(days=70))

    def test_zero_heavy_series(self):
        v = [0.0] * 90
        for i in range(0, 90, 9):
            v[i] = 1.0
        v[60] = 60   # 기준선 0 → 비율 조건 통과, 최소지수 통과
        v[75] = 5    # 기준선 0이지만 최소지수 20 미만 → 제외
        spikes = detect_spikes(series(v))
        self.assertEqual([s.peak_date for s in spikes], [D0 + timedelta(days=60)])
        self.assertEqual(spikes[0].baseline_median, 0.0)
        self.assertIsNone(spikes[0].ratio)  # 0 대비 배수는 정의하지 않음

    def test_no_judgement_before_full_baseline(self):
        v = noisy(90)
        v[10] = 100  # 기준선 28일이 안 차는 구간
        self.assertEqual(detect_spikes(series(v)), [])

    def test_high_z_but_low_ratio_rejected(self):
        v = [30.0] * 90  # MAD=0 → scale 하한 3.0
        v[60] = 60       # z=10 이지만 2배뿐
        self.assertEqual(detect_spikes(series(v)), [])
        v[60] = 100      # 3.33배
        self.assertEqual(len(detect_spikes(series(v))), 1)

    def test_baseline_robust_to_earlier_spike(self):
        v = noisy(90)
        v[40:42] = [100, 100]
        v[53] = 90  # 직전 28일에 첫 급등이 포함돼도 중앙값은 그대로
        spikes = detect_spikes(series(v))
        self.assertEqual(len(spikes), 2)
        self.assertEqual(spikes[1].peak_date, D0 + timedelta(days=53))
        self.assertEqual(spikes[1].baseline_median, 10.0)

    def test_weekly_cycle_is_not_a_spike(self):
        # 로또형: 주말만 높음 (라이브: 토 45.6 / 일 47.2 vs 평일 5~16)
        v = [30.0 if (D0 + timedelta(days=i)).weekday() >= 5 else 5.0 + (i % 3) for i in range(90)]
        self.assertEqual(detect_spikes(series(v)), [])

    def test_spike_on_top_of_weekly_cycle(self):
        v = [30.0 if (D0 + timedelta(days=i)).weekday() >= 5 else 5.0 + (i % 3) for i in range(90)]
        sat = next(i for i in range(60, 90) if (D0 + timedelta(days=i)).weekday() == 5)
        v[sat] = 100
        spikes = detect_spikes(series(v))
        self.assertEqual([s.peak_date for s in spikes], [D0 + timedelta(days=sat)])
        self.assertEqual(spikes[0].baseline_kind, "same_weekday")
        self.assertEqual(spikes[0].baseline_median, 30.0)
        self.assertAlmostEqual(spikes[0].ratio, 100 / 30)

    def test_baseline_kind_rolling_when_no_weekly_cycle(self):
        v = noisy(90)
        v[60] = 100
        self.assertEqual(detect_spikes(series(v))[0].baseline_kind, "rolling")


class DetectTest(unittest.TestCase):
    def test_insufficient_observed_days(self):
        data = [{"period": (D0 + timedelta(days=i)).isoformat(), "ratio": 100.0} for i in range(0, 90, 7)]
        r = detect(data, D0, D0 + timedelta(days=89))
        self.assertEqual(r.observed_days, 13)
        self.assertTrue(r.insufficient)
        self.assertEqual(r.reason, "few_observed_days")
        self.assertEqual(r.spikes, [])

    def test_low_volume_step_values(self):
        # 장호열형: 검색 수가 한 자릿수라 지수가 몇 가지 값으로만 계단짐 (라이브: 6종류)
        steps = [45.45454, 54.54545, 63.63636, 81.81818, 100.0]
        v = [steps[i % 5] for i in range(90)]
        r = detect(to_data(v, keep=lambda d: d.toordinal() % 3 == 0), D0, D0 + timedelta(days=89))
        self.assertGreaterEqual(r.observed_days, 14)
        self.assertTrue(r.insufficient)
        self.assertEqual(r.reason, "low_volume")
        self.assertEqual(r.spikes, [])

    def test_end_to_end_with_gaps(self):
        v = varied(90)
        v[60] = 100
        r = detect(to_data(v, keep=lambda d: d.day % 10 != 5), D0, D0 + timedelta(days=89))
        self.assertFalse(r.insufficient)
        self.assertIsNone(r.reason)
        self.assertEqual(len(r.series), 90)
        self.assertEqual([s.peak_date for s in r.spikes], [D0 + timedelta(days=60)])


if __name__ == "__main__":
    unittest.main()
