"""정답셋 초안 → eval/cases.json + 사례별 90일 스냅샷 (ADR 0003).

사용법: python scripts/build_eval.py
- 후보 기사는 eval/candidates.json(mine_candidates.py)에서, 사용자 사례는 맥락어 검색으로 붙인다.
- 이미 있는 스냅샷은 다시 받지 않는다 (재현성).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.mine_candidates import news_in, sim_news  # noqa: E402
from trend_agent.naver import fetch_trend  # noqa: E402

YESTERDAY = date.today() - timedelta(days=1)

# (id, keyword, source, event_start, event_end, cause, cause_keywords, context_query, note)
DRAFTS = [
    ("rain-1018", "폭우", "mined", "2026-10-18", "2026-10-18",
     "서울 강북구 시간당 53.5㎜ 폭우로 곳곳 침수·교통통제", [["침수", "교통통제"], ["서울", "강북"]], None, ""),
    ("heat-0804", "폭염", "mined", "2026-08-03", "2026-08-04",
     "폭염중대경보 발령", [["폭염중대경보", "중대경보"]], None, ""),
    ("typhoon-1023", "태풍", "mined", "2026-10-20", "2026-10-26",
     "가을 태풍 '참피' 제주 피해, 태풍 '인파' 북상", [["참피", "인파"]], None, "태풍 2개가 겹침 — 확인 필요"),
    ("sinkhole-0529", "싱크홀", "mined", "2026-05-29", "2026-05-30",
     "의정부 신곡동 도로 싱크홀로 차량 3대 파손", [["의정부"], ["차량", "파손"]], None, ""),
    ("nobel-1008", "노벨상", "mined", "2026-10-05", "2026-10-12",
     "2026 노벨상 발표 주간 (문학상 앤 카슨 등)", [["수상", "발표", "수상자"]], None, ""),
    ("blackpink-0808", "블랙핑크", "mined", "2026-08-07", "2026-08-10",
     "데뷔 10주년 행사(팬 40명 초대) 팬 홀대 논란·멤버 사과", [["10주년"], ["홀대", "사과", "팬미팅"]], None, ""),
    ("newjeans-0722", "뉴진스", "mined", "2026-07-22", "2026-07-23",
     "민지 어도어 복귀 시그널·컴백 기대", [["민지", "복귀", "컴백"]], None, "기사가 급등 다음날(07-24) 위주 — 확인 필요"),
    ("gta6-0619", "GTA6", "mined", "2026-06-19", "2026-06-19",
     "사전예약 일정(6/25)과 정식 출시일(11/19) 발표", [["출시일", "사전예약", "사전주문", "11월19일"]], None, ""),
    ("gta6-0625", "GTA6", "mined", "2026-06-24", "2026-06-30",
     "사전예약 시작", [["사전예약", "사전주문", "예약"]], None, ""),
    ("gta6-0828", "GTA6", "mined", "2026-08-28", "2026-08-31",
     "유출자 추적·용량 250GB 전망 등", [["유출", "250GB", "용량"]], None, "원인 불분명 — 확인 필요"),
    ("tesla-1016", "테슬라", "mined", "2026-10-16", "2026-10-17",
     "하늘 나는 로드스터 시연", [["로드스터", "나는", "비행", "하늘"]], None, ""),
    ("ks-1027", "한국시리즈", "mined", "2026-10-26", "2026-10-27",
     "플레이오프 삼성-KIA 진행 (한국시리즈 진출 경쟁)", [["플레이오프", "PO"], ["삼성", "KIA"]], None, "PO 기사가 대부분 — 확인 필요"),
    ("kimyk-0926", "김연경", "mined", "2026-09-23", "2026-09-27",
     "'신인감독 김연경2' 예고편 공개", [["신인감독"], ["예고편", "예고"]], None, "확인 필요"),
    ("kimyk-1011", "김연경", "mined", "2026-10-11", "2026-10-11",
     "'신인감독 김연경2' 첫 방송", [["신인감독"], ["첫방", "첫방송", "첫회"]], None, ""),
    ("kimyk-1018", "김연경", "mined", "2026-10-18", "2026-10-18",
     "'신인감독 김연경2' 2회 일본팀전", [["신인감독"], ["일본", "2회"]], None, ""),
    ("minwage-0715", "최저임금", "mined", "2026-07-14", "2026-07-15",
     "2027년 최저임금 1만700원 결정", [["1만700원", "10700원", "10,700원"]], None, ""),
    ("assassins-0929", "암살자들", "user", "2026-09-26", "2026-10-02",
     "영화 '암살자(들)' 역사 왜곡 논란, 제작진 고발", [["역사왜곡", "왜곡"], ["논란", "고발"]],
     "암살자들 역사왜곡", ""),
    ("dujjonku-2601", "두쫀쿠", "user", "2025-12-10", "2026-01-16",
     "두바이 쫀득쿠키(두쫀쿠) 유행, 품절 대란", [["두바이", "두쫀쿠"], ["품절", "유행", "열풍"]],
     "두쫀쿠 품절", "유행형: 12월 초부터 서서히 올라 01-15 정점"),
]

cands = json.loads((ROOT / "eval" / "candidates.json").read_text(encoding="utf-8"))
snap_dir = ROOT / "eval" / "snapshots"
snap_dir.mkdir(parents=True, exist_ok=True)
cases = []
for cid, kw, source, es, ee, cause, ckw, ctx, note in DRAFTS:
    es, ee = date.fromisoformat(es), date.fromisoformat(ee)
    w_end = min(ee + timedelta(days=14), YESTERDAY)
    w_start = w_end - timedelta(days=89)
    if ctx:
        evidence = news_in(sim_news(ctx, pages=5), es - timedelta(days=1), ee + timedelta(days=1))[:5]
    else:
        evidence = next(c["articles"] for c in cands if c["keyword"] == kw and c["start"] <= ee.isoformat() and c["end"] >= es.isoformat())
    snap = snap_dir / f"{cid}.json"
    if not snap.exists():
        snap.write_text(json.dumps(fetch_trend(kw, w_start, w_end), ensure_ascii=False), encoding="utf-8")
    cases.append({
        "id": cid, "keyword": kw, "source": source, "verified": False,
        "event_start": es.isoformat(), "event_end": ee.isoformat(),
        "window_start": w_start.isoformat(), "window_end": w_end.isoformat(),
        "cause": cause, "cause_keywords": ckw, "evidence": evidence, "note": note,
    })
(ROOT / "eval" / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"사례 {len(cases)}건 저장")
