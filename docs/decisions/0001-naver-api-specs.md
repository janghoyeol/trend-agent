# 0001. NAVER API HUB 스펙 (라이브 확인)

- 상태: 진행 중 (뉴스 확정 / 검색어트렌드·성인 판별 미확정)
- 확인일: 2026-10-29, `scripts/probe_naver.py` 실제 키로 실행

## 뉴스 검색 `GET /search/v1/news` — 확정

- `pubDate`: RFC 822, KST. 예: `Thu, 29 Oct 2026 13:01:00 +0900`
  → `email.utils.parsedate_to_datetime`으로 파싱.
- 파라미터 한도: `start` 1~1000, `display` 1~100. 범위 밖이면 HTTP 400
  (`SE03` Invalid start / `SE02` Invalid display).
- 따라서 한 쿼리로 닿는 최대 범위는 **최신 1,099건** (start=1000, display=100).
- 결과 없음: HTTP 200, `total: 0`, `items: []`.
- `sort=date` 기준 start=1000 위치의 가장 오래된 기사 (2026-10-29 측정):

  | 키워드 | total | 닿는 범위 |
  |---|---|---|
  | 아이폰 | 787,917 | 약 6일 (10-23까지) |
  | 날씨 | 3,885,457 | 약 1일 (10-28까지) |

### 결정 / 영향

- 기사량이 많은 키워드일수록 원인 매칭 가능 기간이 **수 일**로 짧다.
  "최근 급등만 매칭 가능"은 예상보다 강한 제약 → UI에 키워드별 실제 커버 기간
  (가장 오래된 pubDate)을 표시한다.
- 급등일이 커버 범위 밖이면 "기사 범위 밖"으로 정직하게 반환하고 원인을 추측하지 않는다.
- 범위 확장 대안(1단계에서 논의): `sort=sim` + 쿼리에 날짜/맥락어 추가,
  급등일 당일 배치 수집·캐시(하루 1회 미리 계산과 결합).

## 검색어트렌드 `POST /search-trend/v1/search` — 미확정

- 실제 키로 호출 시 HTTP 401:
  `{"error":{"errorCode":401,"message":"요청한 API는 이 Application에서 활성화되어 있지 않습니다."}}`
- 키 자체는 유효(뉴스 200). NCP 콘솔에서 해당 Application에 API를 활성화해야 함.

## 성인 검색어 판별 `GET /search/v1/adult` — 미확정

- 검색어트렌드와 동일한 401 (Application에 미활성화).
