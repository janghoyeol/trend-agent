"""정답셋 채점 테스트 (ADR 0003). 실행: python -m unittest -v"""
import unittest
from datetime import date

from trend_agent.detect import Spike
from trend_agent.evaluate import Case, cause_hit, detection_hit

CASE = Case(
    id="assassins-history",
    keyword="암살자들",
    source="user",
    verified=True,
    event_start=date(2026, 9, 28),
    event_end=date(2026, 9, 30),
    window_start=date(2026, 7, 17),
    window_end=date(2026, 10, 14),
    cause="영화 '암살자(들)' 역사 왜곡 논란, 제작진 고발",
    cause_keywords=[["암살자"], ["역사왜곡", "왜곡", "고발"]],
)


def spike(start, end):
    return Spike(start=start, end=end, peak_date=start, peak_value=100, baseline_median=3,
                 baseline_kind="rolling", ratio=30, z=50)


class DetectionHitTest(unittest.TestCase):
    def test_overlap_hits(self):
        self.assertTrue(detection_hit(CASE, [spike(date(2026, 9, 23), date(2026, 10, 5))]))

    def test_within_tolerance_hits(self):
        # 사건 시작 3일 전에 끝난 급등 → 허용
        self.assertTrue(detection_hit(CASE, [spike(date(2026, 9, 20), date(2026, 9, 25))]))

    def test_outside_tolerance_misses(self):
        self.assertFalse(detection_hit(CASE, [spike(date(2026, 9, 10), date(2026, 9, 24))]))
        self.assertFalse(detection_hit(CASE, [spike(date(2026, 10, 4), date(2026, 10, 6))]))

    def test_no_spikes_misses(self):
        self.assertFalse(detection_hit(CASE, []))


class CauseHitTest(unittest.TestCase):
    def test_all_groups_and_dated_citation_hits(self):
        text = "영화 '암살자(들)'이 역사 왜곡 논란으로 제작진이 고발당하며 검색이 급증했습니다."
        self.assertTrue(cause_hit(CASE, text, [date(2026, 9, 29)]))

    def test_spacing_and_case_ignored(self):
        case = Case(**{**CASE.__dict__, "cause_keywords": [["GTA6"], ["출시일"]]})
        self.assertTrue(cause_hit(case, "gta 6 출시 일 발표", [date(2026, 9, 29)]))

    def test_missing_group_misses(self):
        self.assertFalse(cause_hit(CASE, "영화 '암살자(들)' 개봉 효과입니다.", [date(2026, 9, 29)]))

    def test_citation_outside_window_misses(self):
        text = "암살자(들) 역사 왜곡 논란"
        self.assertFalse(cause_hit(CASE, text, [date(2026, 10, 20)]))
        self.assertFalse(cause_hit(CASE, text, []))


if __name__ == "__main__":
    unittest.main()
