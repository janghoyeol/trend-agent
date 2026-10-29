"""원인 설명 에이전트 테스트 (ADR 0004). Claude·네이버 호출은 가짜로 대체. 실행: python -m unittest -v"""
import json
import unittest
from datetime import date
from types import SimpleNamespace as NS

from trend_agent.agent import explain, render
from trend_agent.detect import Spike

SPIKE = Spike(start=date(2026, 9, 28), end=date(2026, 9, 30), peak_date=date(2026, 9, 29),
              peak_value=100, baseline_median=4, baseline_kind="rolling", ratio=25, z=40)


def art(title, d, link):
    return {"title": title, "description": "", "link": link, "pubDate": "", "date": d}


NEWS = {
    "암살자들": [art("암살자들 흥행", date(2026, 10, 20), "L0")],  # 기간 밖
    "암살자들 역사왜곡": [art("암살자들 역사왜곡 고발", date(2026, 9, 29), "L1"),
                    art("암살자들 제작진 해명", date(2026, 9, 30), "L2"),
                    art("암살자들 개봉", date(2026, 8, 1), "L3")],  # 기간 밖
}


def usage():
    return NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def tool_call(query, i=0):
    return NS(stop_reason="tool_use", usage=usage(),
              content=[NS(type="tool_use", id=f"t{i}", name="search_news", input={"query": query})])


def final(**answer):
    return NS(stop_reason="end_turn", usage=usage(),
              content=[NS(type="text", text=json.dumps(answer, ensure_ascii=False))])


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.responses.pop(0)


def run(responses, **kw):
    client = FakeClient(responses)
    return explain("암살자들", SPIKE, client, search=lambda q: NEWS.get(q, []), **kw), client


class ExplainTest(unittest.TestCase):
    def test_found_with_valid_citations(self):
        exp, client = run([
            tool_call("암살자들"),
            tool_call("암살자들 역사왜곡", 1),
            final(status="found", cause="역사 왜곡 논란으로 제작진이 고발됐다", citations=["a1", "a2"]),
        ])
        self.assertEqual(exp.status, "found")
        self.assertEqual([a["link"] for a in exp.citations], ["L1", "L2"])
        self.assertEqual([s["in_window"] for s in exp.searches], [0, 2])
        self.assertEqual(exp.input_tokens, 3000)

    def test_only_in_window_articles_are_shown(self):
        _, client = run([tool_call("암살자들 역사왜곡"), final(status="unknown", cause="", citations=[])])
        shown = json.loads(client.calls[1]["messages"][2]["content"][0]["content"])
        self.assertEqual([a["title"] for a in shown["articles"]], ["암살자들 역사왜곡 고발", "암살자들 제작진 해명"])

    def test_hints_when_nothing_in_period_and_not_citable(self):
        exp, client = run([tool_call("암살자들"), final(status="found", cause="흥행", citations=["a1"])])
        out = json.loads(client.calls[1]["messages"][2]["content"][0]["content"])
        self.assertEqual(out["articles"], [])
        self.assertEqual(out["out_of_period_hints"]["titles"], ["2026-10-20 암살자들 흥행"])
        self.assertEqual(exp.status, "unknown")  # 힌트 기사는 id가 없어 인용 불가

    def test_unknown_or_unshown_citation_rejected(self):
        exp, _ = run([
            tool_call("암살자들 역사왜곡"),
            final(status="found", cause="고발", citations=["a1", "a9", "a1"]),
        ])
        self.assertEqual([a["id"] for a in exp.citations], ["a1"])
        self.assertEqual(exp.rejected, ["a9", "a1"])

    def test_found_without_valid_citation_becomes_unknown(self):
        exp, _ = run([final(status="found", cause="지어낸 원인", citations=["a1"])])
        self.assertEqual(exp.status, "unknown")
        self.assertEqual(exp.citations, [])

    def test_search_limit(self):
        exp, client = run([tool_call("q", i) for i in range(3)] + [final(status="unknown", cause="", citations=[])],
                          max_searches=2)
        self.assertEqual(len(exp.searches), 2)
        last = client.calls[3]["messages"][-1]["content"][0]
        self.assertTrue(last["is_error"])

    def test_same_article_keeps_id(self):
        exp, client = run([
            tool_call("암살자들 역사왜곡"), tool_call("암살자들 역사왜곡", 1),
            final(status="found", cause="고발", citations=["a2"]),
        ])
        second = json.loads(client.calls[2]["messages"][-1]["content"][0]["content"])
        self.assertEqual([a["id"] for a in second["articles"]], ["a1", "a2"])

    def test_refusal(self):
        exp, _ = run([NS(stop_reason="refusal", usage=usage(), content=[])])
        self.assertEqual(exp.status, "unknown")

    def test_render_numbers_from_detection(self):
        exp, _ = run([tool_call("암살자들 역사왜곡"), final(status="found", cause="고발", citations=["a1"])])
        text = render(exp)
        self.assertIn("상대지수 100 (직전 28일 중앙값 4)", text)
        self.assertIn("[1] 2026-09-29 암살자들 역사왜곡 고발 — L1", text)


if __name__ == "__main__":
    unittest.main()
