"""예산·서비스 테스트 (ADR 0005). 네이버·Claude는 가짜. 실행: python -m unittest -v"""
import unittest
from datetime import date, timedelta

from trend_agent.agent import Explanation
from trend_agent.budget import WORST_CASE_USD, DailyBudget
from trend_agent.service import Service

TODAY = date(2026, 10, 29)
HAIKU = "claude-haiku-5-5"


class Clock:
    def __init__(self, d):
        self.d = d

    def __call__(self):
        return self.d


class BudgetTest(unittest.TestCase):
    def test_reserve_until_cap(self):
        b = DailyBudget(0.025, today=Clock(TODAY))
        self.assertIsNotNone(b.reserve(HAIKU))
        self.assertIsNotNone(b.reserve(HAIKU))
        self.assertIsNone(b.reserve(HAIKU))  # 0.03 > 0.025

    def test_settle_frees_unused_reservation(self):
        b = DailyBudget(0.02, today=Clock(TODAY))
        r = b.reserve(HAIKU)
        b.settle(r, 0.002)
        self.assertAlmostEqual(b.remaining, 0.018)

    def test_sonnet_needs_bigger_budget(self):
        self.assertIsNone(DailyBudget(0.1, today=Clock(TODAY)).reserve("claude-sonnet-5-5"))
        self.assertGreater(WORST_CASE_USD["claude-sonnet-5-5"], 0.1)

    def test_resets_next_day(self):
        clock = Clock(TODAY)
        b = DailyBudget(0.01, today=clock)
        b.settle(b.reserve(HAIKU), 0.01)
        self.assertIsNone(b.reserve(HAIKU))
        clock.d = TODAY + timedelta(days=1)
        self.assertIsNotNone(b.reserve(HAIKU))


def series_with_spikes(start, end, spike_days):
    out, d = [], start
    while d <= end:
        base = 10 + (d.toordinal() * 7919 % 23) / 4  # 저검색량 판정을 피하려고 값에 변화를 준다
        out.append({"period": d.isoformat(), "ratio": 100.0 if d in spike_days else float(base)})
        d += timedelta(days=1)
    return out


SPIKES = {date(2026, 9, 10), date(2026, 10, 25)}


class FakeExplain:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, keyword, spike, client, model):
        self.calls.append((keyword, spike.start))
        if self.fail:
            raise ConnectionError("down")
        return Explanation(keyword, spike, "unknown", "", [], model=model, input_tokens=10000, output_tokens=1000)


def make(cap=0.1, adult=False, explain=None, ip_daily=5):
    explain = explain or FakeExplain()
    svc = Service(DailyBudget(cap, today=Clock(TODAY)), lambda: object(), model=HAIKU, ip_daily=ip_daily,
                  today=Clock(TODAY), trend=lambda kw, s, e: series_with_spikes(s, e, SPIKES),
                  adult=lambda kw: adult, explain_fn=explain)
    return svc, explain


class ServiceTest(unittest.TestCase):
    def test_explains_only_latest_spike(self):
        svc, ex = make()
        r = svc.analyze("태풍", ip="1.1.1.1")
        self.assertEqual([s["start"] for s in r["spikes"]], ["2026-09-10", "2026-10-25"])
        self.assertEqual([s["explain_state"] for s in r["spikes"]], ["not_requested", "done"])
        self.assertEqual(ex.calls, [("태풍", date(2026, 10, 25))])
        self.assertEqual(r["end"], "2026-10-28")

    def test_cache_does_not_spend_twice(self):
        svc, ex = make()
        svc.analyze("태풍", ip="a")
        r = svc.analyze("태풍", ip="b")
        self.assertEqual(len(ex.calls), 1)
        self.assertEqual(r["spikes"][1]["explain_state"], "done")

    def test_budget_exhausted_still_returns_detection(self):
        svc, ex = make(cap=0.005)
        r = svc.analyze("태풍")
        self.assertEqual(r["spikes"][1]["explain_state"], "budget_exhausted")
        self.assertEqual(len(r["series"]), 90)
        self.assertEqual(ex.calls, [])

    def test_ip_limit(self):
        svc, ex = make(ip_daily=1)
        svc.analyze("태풍", ip="x")
        r = svc.analyze("폭우", ip="x")
        self.assertEqual(r["spikes"][1]["explain_state"], "rate_limited")
        self.assertEqual(svc.analyze("폭우", ip="y")["spikes"][1]["explain_state"], "done")

    def test_adult_blocked_before_trend_and_llm(self):
        svc, ex = make(adult=True)
        self.assertTrue(svc.analyze("성인키워드")["blocked"])
        self.assertEqual(ex.calls, [])

    def test_error_charges_reservation(self):
        svc, _ = make(cap=0.1, explain=FakeExplain(fail=True))
        r = svc.analyze("태풍")
        self.assertEqual(r["spikes"][1]["explain_state"], "error")
        self.assertAlmostEqual(svc.budget.remaining, 0.1 - WORST_CASE_USD[HAIKU])

    def test_seeded_daily_explanation_reused(self):
        svc, ex = make()
        spike = {"start": "2026-10-25", "end": "2026-10-25"}
        svc.seed("태풍", spike, {"status": "found", "cause": "x", "citations": []})
        r = svc.analyze("태풍")
        self.assertEqual(r["spikes"][1]["explanation"]["cause"], "x")
        self.assertEqual(ex.calls, [])

    def test_recent_days_skips_old_spike(self):
        svc, ex = make()
        r = svc.analyze("태풍", recent_days=2)  # 마지막 급등 10-25 < 10-27
        self.assertEqual(r["spikes"][1]["explain_state"], "not_requested")
        self.assertEqual(ex.calls, [])


if __name__ == "__main__":
    unittest.main()
