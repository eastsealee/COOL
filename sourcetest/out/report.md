# 데이터 출처 비교 테스트 — 2026-10-27 01:11 KST

## A. 물때(만조·간조) — 보령 조위관측소 실측 기준, 지난 14일
| 예측 출처 | 시간 오차(평균) | 시간 오차(최대) | 높이 오차(평균) | 높이 치우침 | 비교 수 |
|---|---|---|---|---|---|
| 바다타임 보령(지금 앱) | 7분 | 26분 | 17cm | -12cm | 53 |
| 해양조사원 조석예보 | 7분 | 26분 | 17cm | -12cm | 53 |

※ 높이는 관측소 기준면이 서로 다를 수 있어 '치우침'이 크면 기준면 차이, 평균 오차에서 치우침을 뺀 값이 실제 정확도
- 치우침 뺀 높이 오차: 바다타임 13cm · 해양조사원 13cm
- 하루 평균 ▲▼ 변화량(조류세기 계산값) 차이: 평균 0cm (바다타임−해양조사원 +0cm, 14일)

### 남당항 — 바다타임(356) vs 해양조사원 TideBED(남당항 좌표) 예측 차이, 오늘부터 7일
| 비교 | 시간 차이(평균) | 시간 차이(최대) | 높이 차이(평균) | 높이 치우침 | 비교 수 |
|---|---|---|---|---|---|
| 바다타임 − TideBED | 15분 | 103분 | 56cm | +51cm | 20 |

## A-2. 해양조사원 실측·예측 동시 조회 — 보령, 지난 7일
받지 못함 (raw/khoa_obspre_*, raw/page_15142507_* 확인)

## B. 바람 — 기상청 보령 관측소(ASOS 235) 실측 기준
하루 전에 낸 예보 vs 실제 (방향은 실측 2m/s 이상일 때만, '방향 적중' = 45° 안)

**바로 비교 (Open-Meteo가 보관한 지난 14일 '하루 전 예보')**

| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |
|---|---|---|---|---|---|
| 기상청 전구모델 GDPS (Open-Meteo) | – | – | – | – | 0 |
| 기상청 국지모델 LDPS (Open-Meteo) | – | – | – | – | 0 |
| Open-Meteo 기본 모델 (예전 앱) | 2.3 m/s | +2.2 m/s | 30° | 84% | 322 |
| GFS (윈드파인더 무료 예보) | 2.1 m/s | +2.0 m/s | 29° | 83% | 322 |

**매일 쌓은 예보로 비교 (며칠 지나야 숫자가 생김)**

| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |
|---|---|---|---|---|---|
| 기상청 단기예보 API (직접) | 1.1 m/s | +0.5 m/s | 37° | 72% | 84 |
| Open-Meteo 기상청 모델 (지금 앱 v10.21) | – | – | – | – | 0 |
| Open-Meteo 기본 모델 (예전 앱) | 1.8 m/s | +1.7 m/s | 28° | 78% | 84 |
| GFS (윈드파인더 무료 예보) | 1.3 m/s | +1.0 m/s | 36° | 72% | 84 |

- 기상청 단기예보 API는 매일 쌓은 예보로만 비교 가능 — 현재 쌓인 비교 84시간, 며칠 더 돌리면 늘어남
- 참고: 기상청 단기예보에는 파고(WAV)도 있음 — 원산도 격자 10/27 00시 풍속 6.8m/s 풍향 322° 파고 0.5m

## C. 기상청 중기 해상예보 (3~10일 뒤) — 받아지는지만 확인
서해중부 해상: regId=12A20000, wf5Am=맑음, wf5Pm=맑음, wf6Am=흐림, wf6Pm=흐리고 비, wf7Am=맑음, wf7Pm=맑음, wf8=맑음, wf9=맑음, wf10=맑음, wh5AAm=1.0, wh5APm=0.5, wh5BAm=2.0, wh5BPm=1.5

## 진행 기록
- obs_20261013: https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService type → 144건, 필드 ['obsvtrNm', 'lat', 'lot', 'obsrvnDt', 'bscTdlvHgt', 'tdlvHgt'], 예: {'obsvtrNm': '보령', 'lat': 36.40638, 'lot': 126.48611, 'obsrvnDt': '2026-10-13 00:00', 'bscTdlvHgt': 151.0, 'tdlvHgt': 127.6}
- hl_20261013: https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService type → 4건, 필드 ['obsvtrNm', 'lot', 'lat', 'predcDt', 'predcTdlvVl', 'extrSe'], 예: {'obsvtrNm': '보령', 'lot': 126.48611, 'lat': 36.40638, 'predcDt': '2026-10-13 04:31', 'predcTdlvVl': 691.0, 'extrSe': '1'}
- 실측 2016점 → 만조·간조 53개 / 해양조사원 예보 54 / 바다타임 54
- bed_20261027: https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService type → 144건, 필드 ['obsvtrNm', 'lot', 'lat', 'obsrvnDt', 'obsrvnHgt', 'm2TdlvAmp', 'm2TdlvTlag', 's2TdlvAmp', 's2TdlvTlag', 'k1TdlvAmp', 'k1TdlvTlag', 'o1TdlvAmp', 'o1TdlvTlag', 'slctdDt', 'slctdHgt', 'm2TconstAmp', 'm2TconstTlag', 's2TconstAmp', 's2TconstTlag', 'k1TconstAmp', 'k1TconstTlag', 'o1TconstAmp', 'o1TconstTlag', 'jogo', 'josi', 'msl'], 예: {'obsvtrNm': '방포항', 'lot': 126.3253, 'lat': 36.5022, 'obsrvnDt': '2026-10-27 00:00', 'obsrvnHgt': 212.38, 'm2TdlvAmp': 209.1, 'm2TdlvTlag': 96.4, 's2TdlvAmp': 83.3, 's2TdlvTlag': 148.6, 'k1TdlvAmp': 35.2, 'k1TdlvTlag': 286.8, 'o1TdlvAmp': 27.8, 'o1TdlvTlag': 248.7, 'slctdDt': '2026-10-26 23:59', 'slctdHgt': '229', 'm2TconstAmp': 234.912, 'm2TconstTlag': 95.444, 's2TconstAmp': 92.799, 's2TconstTlag': 150.222, 'k1TconstAmp': 36.138, 'k1TconstTlag': 286.947, 'o1TconstAmp': 26.29, 'o1TconstTlag': 248.877, 'jogo': '1.120762653898769', 'josi': '-1분', 'msl': 390.139}
- 보령 ASOS 322시간 NORMAL_SERVICE
- 단기예보 asos 격자 53,100 발표 10-26 23시 → 81시간 NORMAL_SERVICE
- 단기예보 wonsando 격자 50,101 발표 10-26 23시 → 81시간 NORMAL_SERVICE
- 단기예보 namdang 격자 51,104 발표 10-26 23시 → 81시간 NORMAL_SERVICE
- Open-Meteo 하루 전 예보: kma_gdps 0시간, kma_ldps 0시간, best_match 360시간, gfs_seamless 360시간