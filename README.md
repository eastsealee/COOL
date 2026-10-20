# COOL — 낚시 도구 모음

하나의 Streamlit 앱에서 왼쪽 메뉴로 프로그램을 골라 씁니다.

| 폴더 | 프로그램 | 앱 주소 끝 |
|---|---|---|
| `sunsang24/` | 선상낚시 예약조회 (선상24·더피싱) | `/sunsang24` (첫 화면) |
| `lamar/` | 라마르호 예상 조과 분석 | `/lamar` |
| `mulddae/` | 물때 (물때·날씨·바람/파고) | `/mulddae` |
| `mulddae/` | 물때 시계 (24시간 원형 화면) | `/mulddae-clock` |

```
COOL/
├─ streamlit_app.py        메뉴 (Streamlit Cloud Main file — 바꾸지 않음)
├─ requirements.txt        모든 프로그램이 함께 쓰는 패키지
├─ .github/workflows/      자동 실행 (GitHub 규칙상 최상위에 있어야 함)
│   ├─ precrawl.yml        선상24 사전조회 → data 브랜치
│   └─ lamar_daily.yml     라마르 조과 매일 갱신 → lamar/data/
├─ sunsang24/
│   ├─ streamlit_app.py
│   └─ precrawl.py         streamlit_app.py의 수집 코드를 같은 폴더에서 읽어 씀
├─ lamar/
│   ├─ streamlit_app.py
│   ├─ lamar_*.py
│   └─ data/lamar_days.json
└─ mulddae/
    ├─ tide_data.py        물때·날씨 수집 + 조류세기 계산 (두 화면이 함께 씀)
    ├─ streamlit_app.py    물때 화면  + tide_view.html
    └─ dial.py             물때 시계  + dial_view.html
```

## 새 프로그램 추가
1. 새 폴더를 만들고 화면 파일을 `streamlit_app.py`로 둡니다.
2. 최상위 `streamlit_app.py`의 `pages` 목록에 `st.Page("폴더/streamlit_app.py", title=..., url_path=...)` 한 줄을 넣습니다.
3. 새 패키지가 필요하면 최상위 `requirements.txt`에 추가합니다.
