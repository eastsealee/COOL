# 데이터 출처 비교 테스트 — 2026-10-31 09:52 KST

## A. 물때(만조·간조) — 보령 조위관측소 실측 기준, 지난 14일
실측 조위를 받지 못해 비교 불가 (raw/khoa_obs_* 확인)

### 남당항 — 바다타임(356) vs 해양조사원 TideBED(남당항 좌표) 예측 차이, 오늘부터 7일
TideBED 0 · 바다타임 27 — 비교 불가 (raw/khoa_bed_* 확인)

## A-2. 해양조사원 실측·예측 동시 조회 — 보령, 지난 7일
받지 못함 (raw/khoa_obspre_*, raw/page_15142507_* 확인)

## B. 바람 — 기상청 보령 관측소(ASOS 235) 실측 기준
하루 전에 낸 예보 vs 실제 (방향은 실측 2m/s 이상일 때만, '방향 적중' = 45° 안)

**바로 비교 (Open-Meteo가 보관한 지난 14일 '하루 전 예보')**

| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |
|---|---|---|---|---|---|
| 기상청 전구모델 GDPS (Open-Meteo) | – | – | – | – | 0 |
| 기상청 국지모델 LDPS (Open-Meteo) | – | – | – | – | 0 |
| Open-Meteo 기본 모델 (예전 앱) | 2.4 m/s | +2.3 m/s | 29° | 81% | 336 |
| GFS (윈드파인더 무료 예보) | 2.3 m/s | +2.1 m/s | 27° | 84% | 336 |

**매일 쌓은 예보로 비교 (며칠 지나야 숫자가 생김)**

| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |
|---|---|---|---|---|---|
| 기상청 단기예보 API (직접) | 1.6 m/s | +1.3 m/s | 30° | 81% | 194 |
| Open-Meteo 기상청 모델 (지금 앱 v10.21) | – | – | – | – | 0 |
| Open-Meteo 기본 모델 (예전 앱) | 2.5 m/s | +2.4 m/s | 26° | 79% | 194 |
| GFS (윈드파인더 무료 예보) | 2.2 m/s | +2.0 m/s | 28° | 81% | 194 |

- 기상청 단기예보 API는 매일 쌓은 예보로만 비교 가능 — 현재 쌓인 비교 194시간, 며칠 더 돌리면 늘어남
- 참고: 기상청 단기예보에는 파고(WAV)도 있음 — 원산도 격자 10/31 09시 풍속 6.8m/s 풍향 342° 파고 0.5m

## C. 기상청 중기 해상예보 (3~10일 뒤) — 받아지는지만 확인
서해중부 해상: regId=12A20000, wf4Am=맑음, wf4Pm=맑음, wf5Am=구름많음, wf5Pm=구름많음, wf6Am=맑음, wf6Pm=맑음, wf7Am=맑음, wf7Pm=맑음, wf8=맑음, wf9=맑음, wf10=맑음, wh4AAm=0.5, wh4APm=0.5

## 진행 기록
- obs_20261017: https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService (503) 항목 없음  '{\n  "OpenAPI_ServiceResponse": {\n    "cmmMsgHeader": {\n      "errMsg": "SERVICETIMEOUT_ERROR",\n      "returnAuthMsg": "서'
- obs_20261017 요청 실패 https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService: https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService: HTTPSConnectionPool(host='apis.data.go.kr', port=443): Read timed out. (read timeout=30)
- hl_20261017: https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService (503) 항목 없음  '{\n  "OpenAPI_ServiceResponse": {\n    "cmmMsgHeader": {\n      "errMsg": "SERVICETIMEOUT_ERROR",\n      "returnAuthMsg": "서'
- hl_20261017 요청 실패 https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService: https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService: HTTPSConnectionPool(host='apis.data.go.kr', port=443): Read timed out. (read timeout=30)
- 첫날 두 API 모두 응답 없음 → 나머지 날짜 생략
- 실측 0점 → 만조·간조 0개 / 해양조사원 예보 0 / 바다타임 54
- bed_20261031: https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService (503) 항목 없음  '{\n  "OpenAPI_ServiceResponse": {\n    "cmmMsgHeader": {\n      "errMsg": "SERVICETIMEOUT_ERROR",\n      "returnAuthMsg": "서'
- bed_20261031: https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService (503) 항목 없음  '{\n  "OpenAPI_ServiceResponse": {\n    "cmmMsgHeader": {\n      "errMsg": "SERVICETIMEOUT_ERROR",\n      "returnAuthMsg": "서'
- 보령 ASOS 336시간 NORMAL_SERVICE
- 단기예보 asos 격자 53,100 발표 10-31 08시 → 72시간 NORMAL_SERVICE
- 단기예보 wonsando 격자 50,101 발표 10-31 08시 → 72시간 NORMAL_SERVICE
- 단기예보 namdang 격자 51,104 발표 10-31 08시 → 72시간 NORMAL_SERVICE
- Open-Meteo 하루 전 예보: kma_gdps 0시간, kma_ldps 0시간, best_match 360시간, gfs_seamless 360시간