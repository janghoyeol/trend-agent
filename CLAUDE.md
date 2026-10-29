# trend-agent — 프로젝트 브리핑

> 이전 세션에서 기획을 마친 내용입니다. 새 세션은 이 문서를 기준으로 이어서 진행합니다.

## 0. 개발자 배경 / 협업 방식

- 개발자: 장호열 (GitHub `janghoyeol`). 포트폴리오 사이트 https://showcase.hoyeol.workers.dev/ 에 올릴 프로젝트.
- 기존 작품: air/corp/realty/stat-agent (공공 API + Claude tool-use, 숫자마다 출처), 직접 학습한 분류기 2종, curiosity-feed(네이버뉴스 사용), 창작 시뮬레이션 2종.
- **코드를 한 번에 다 짜지 말고, 설계 선택지와 트레이드오프를 먼저 설명하고 합의한 뒤 구현.**
- 주요 설계 결정은 `docs/decisions/NNNN-title.md` 짧은 ADR로 기록.
- 가능하면 정답셋/테스트를 먼저 만들고 구현 (TDD식).

## 1. 한 줄 정의

검색 급등을 **코드로 탐지**하고, 그 원인을 **뉴스 출처와 함께** 설명하는 에이전트.
목표 소개 문구: "원인이 알려진 급등 사례 N개 기준 원인 적중률 X%."

## 2. 흐름

```
키워드 입력
  → [Gate] 성인 검색어 판별 (LLM 호출 전 무료 API로 필터 — 비용/리스크 게이팅)
  → 검색어트렌드 일별 추이 조회
  → 급등일 탐지 (코드: 이동평균 + z-score 등, LLM 없음)
  → 급등일 전후 뉴스 매칭 (pubDate로 필터)
  → Claude tool-use로 원인 후보를 기사 출처와 함께 설명
```

부가 기능(시간 남으면): 검색량 대결 게임(Higher or Lower), 하루 1회 미리 계산해 캐시.

## 3. 원칙 (showcase 공통)

- 출처 없는 숫자는 쓰지 않는다.
- 계산은 모델이 암산하지 않고 코드로 한다.
- 고정 정답셋으로 정확도를 측정한다.
- "됐다"고 말하기 전에 **실제 키로 라이브 호출**해서 확인한다 (설계만 하면 꼭 숨은 버그가 있었음).
- 키는 `.env` / 배포 플랫폼 secrets로만. 채팅에 키를 올리지 않는다.
- 특정 라이브러리가 막히면(예: httpx 403) 다른 표준 라이브러리로 바꿔보는 건 정상적인 트러블슈팅.

## 4. NAVER API HUB — 확인된 사실

- 콘솔: `ncloud.com` → NAVER API HUB (developers.naver.com 아님).
- Base URL: `https://naverapihub.apigw.ntruss.com`
- 인증 헤더: `X-NCP-APIGW-API-KEY-ID`(Client ID), `X-NCP-APIGW-API-KEY`(Client Secret)
- 키는 클라우드 환경변수 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`로 주입되어 있음.

| API | 경로 | 상태 |
|---|---|---|
| 뉴스 검색 | `GET /search/v1/news` | 라이브 확인됨. `query`(필수), `display` 1~100, `start` 1~1000(범위 밖 400 SE02/SE03), `sort` sim/date. title/description에 `<b>` 태그·HTML 엔티티, 본문 없음. `pubDate` RFC 822 KST (`Thu, 29 Oct 2026 13:01:00 +0900`). 일 25,000회 |
| 검색어트렌드 | `POST /search-trend/v1/search` | 실제 키로 401 "이 Application에서 활성화되어 있지 않습니다" → **NCP 콘솔에서 Application에 API 활성화 필요**. body 형식·한도 미확인 |
| 성인 검색어 판별 | `GET /search/v1/adult` | 검색어트렌드와 동일한 401 (미활성화). 응답 형식 미확인 |

예전 데이터랩 스펙(검증 전 가정): body에 `startDate`, `endDate`, `timeUnit`(date/week/month), `keywordGroups`(최대 5그룹), 선택 `device`/`gender`/`ages`. 성인 판별 응답 `{"adult": "0"|"1"}`.

알려진 제약:
- 검색어트렌드는 절대 검색량이 아닌 **상대지수(구간 최대 = 100)** → "3배"가 아니라 "상대지수 30→100"으로 표현.
- 뉴스 API는 날짜 필터가 없고 `start` 상한 1000 → 쿼리당 최신 1,099건까지만. 실측(sort=date): 아이폰 ≈6일, 날씨 ≈1일 → **최근 급등만** 원인 매칭 가능, 인기 키워드는 수 일. UI에 키워드별 커버 기간 표기. (ADR 0001)

## 5. 진행 상황 / 다음 할 일

- [x] 레포 생성, README, `.env.example`, `scripts/probe_naver.py`
- [ ] **0단계 (진행 중)**: `python scripts/probe_naver.py` 라이브 실행 → 아래 4가지 확정 후 이 문서 4절, README, `docs/decisions/0001-naver-api-specs.md`에 기록
  - 2026-10-29: 4번 확정. 1~3번은 NCP 콘솔에서 검색어트렌드·성인 판별 API를 Application에 활성화한 뒤 재실행 필요.
  1. 검색어트렌드 body 형식이 예전 데이터랩과 같은지
  2. 일 단위 데이터를 얼마나 과거까지 받을 수 있는지 (급등 탐지 기준선 길이)
  3. 성인 검색어 판별 응답 형식
  4. ~~뉴스 `pubDate` 형식과 `start=1000` 근처 동작~~ ✅ (ADR 0001)
- [ ] 1단계: 급등 탐지 로직 설계 — 선택지/트레이드오프 설명 후 합의
- [ ] 2단계: 정답셋 먼저 — 원인이 확실한 최근 급등 사례 20~30개 라벨링
- [ ] 3단계: 에이전트 조립 (Gate → 트렌드 → 탐지 → 뉴스 매칭 → Claude 설명)
- [ ] 배포 + showcase 등록 (스택 후보: Python, FastAPI, Claude tool-use — 기존 에이전트들과 동일)
