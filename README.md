# COOL — 낚시 도구 모음 (두 가지 버전)

| 폴더 | 버전 | 누가 쓰나 | 어떻게 실행 |
|---|---|---|---|
| `personal/` | **나만 쓰는 버전** — 지금 쓰는 모든 기능 | KIM 개인 | Streamlit 웹(kim-sunsang24.streamlit.app) + 개인용 안드로이드 APK |
| `store/` | **플레이스토어 버전** — 공공 API 자료만 쓰는 상용 앱 | 일반 사용자 | 화면을 앱 안에 넣은 안드로이드 앱 (Streamlit 없이) |

```
COOL/
├─ streamlit_app.py        개인 버전 메뉴 (Streamlit Cloud Main file — 위치 바꾸지 않음)
├─ requirements.txt        개인 버전 패키지
├─ .github/workflows/      자동 실행 (GitHub 규칙상 최상위에 있어야 함)
├─ sourcetest/             자료 출처 비교 테스트 (두 버전 공통 참고용)
├─ personal/               ── 나만 쓰는 버전 ──
│   ├─ sunsang24/          선상낚시 예약조회 (선상24·더피싱)        /sunsang24
│   ├─ lamar/              라마르호 예상 조과 분석                 /lamar
│   ├─ mulddae/            물때 시계 (+ 조류·수온·섬 자료 만드는 스크립트) /mulddae-clock
│   ├─ chaebi/             채비 계산기                            /chaebi
│   └─ android/            개인용 앱 '쭈갑과물때' (웹 화면을 감싼 APK)
└─ store/                  ── 플레이스토어 버전 ── (store/README.md)
```

- 웹 주소와 개인용 앱은 그대로예요. 폴더만 `personal/` 아래로 옮겼어요.
- 매일·매시간 도는 자료(조류예보 `currents`, 실측 수온 `sst` 브랜치)는 두 버전이 같이 써요.
