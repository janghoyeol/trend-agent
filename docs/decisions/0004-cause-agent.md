# 0004. 원인 설명 에이전트 (Claude tool-use)

- 상태: 채택 (2026-10-29, 사용자 합의) — **Claude 라이브 미확인** (이 환경에 `ANTHROPIC_API_KEY` 없음)

## 맥락

- 뉴스 API는 날짜 필터가 없고, 키워드만으로는 과거 급등 기사에 거의 닿지 않는다.
  `sort=sim` + **원인 맥락어**를 붙여야 닿는다 (ADR 0001).
- 원칙: 출처 없는 숫자 금지, 계산은 코드, 지어내기 방지.

## 결정 (`trend_agent/agent.py`)

1. **도구 1개 `search_news(query)`** — Claude가 맥락어를 바꿔가며 재검색, 코드가
   `sort=sim` 500건을 받아 **급등 기간 −2일 ~ +2일** pubDate로 거른 뒤 최대 15건만 보여준다. 검색 최대 5회
   (넘으면 `is_error` 결과로 "지금까지 본 기사로 답하라").
   - 기사에는 코드가 `a1, a2…` id를 붙인다. 같은 링크는 같은 id.
   - 기간 내 기사가 0건이면 **기간 밖 제목 5개를 힌트로** 준다 (id 없음 = 인용 불가).
     라이브: "최저임금", "깐부치킨"은 키워드만으로 기간 내 0건, "최저임금 결정"/"깐부치킨 젠슨황"은 100건+.
     단서가 없으면 Claude가 맥락어를 지어낼 수밖에 없어서 추가.
2. **최종 출력은 structured output** `{status: found|unknown, cause, citations[id]}`.
   코드가 검증: id가 실제로 보여준 기사인지, 날짜가 기간 안인지, 중복 아닌지. 탈락 id는 `rejected`에 기록.
   - 검색량 숫자는 Claude에게 쓰지 말라고 하고, 사람용 문장(`render`)에서 **탐지 결과 값만** 코드가 넣는다.
3. **근거 없으면 "원인 불명"** — `found`인데 유효 인용이 0개면 코드가 `unknown`으로 바꾼다.
   채점에서는 오답 (`cause_hit`는 `found`일 때만 검사).
4. **모델 기본 Sonnet 5.5**, effort `medium`. 정답셋으로 Haiku 5.5와 비교 (`scripts/eval_cause.py --model`).
   - Sonnet은 서버측 거절 폴백(`fallbacks: "default"`)을 켬. 거절되면 `unknown`.
   - 시스템+도구 프롬프트는 고정 → 자동 프롬프트 캐싱 (`cache_control`).

### 채점

- `scripts/eval_cause.py`: 검수 완료 + `cause_eval` 사례. 탐지가 놓친 사례는 Claude를 부르지 않고 오답 (end-to-end),
  탐지된 것 중 적중률도 함께 출력. 결과는 `eval/results/<model>-<effort>.json`.
- **비상계엄(martial-1203)은 원인 채점 제외** (`cause_eval: false`): 당시 기사 도달 0건이라 측정 불가.
  → 원인 채점 대상 37건.

## 기각한 대안

- 코드가 미리 기사를 모아 한 번에 넣기: 맥락어를 사람이/코드가 알아야 해서 과거 급등에 못 닿음.
- 웹 검색 서버 도구: 출처를 네이버 뉴스 pubDate로 검증하는 원칙과 맞지 않음.
- LLM 채점: 흔들림 (ADR 0003).

## 남은 확인

- [ ] 실제 키로 `python scripts/explain_live.py 태풍` 라이브 확인
- [ ] `python scripts/eval_cause.py` (Sonnet) / `--model claude-haiku-5-5` 결과·비용 기록
