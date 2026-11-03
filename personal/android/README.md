# 쭈갑과물때 안드로이드 앱

Streamlit 물때 시계(`https://kim-sunsang24.streamlit.app/mulddae-clock`)를 전체 화면으로 여는 앱입니다.

- 받기: https://github.com/eastsealee/COOL/releases/download/android-latest/mulddae-clock.apk
- `android/` 아래 파일을 고쳐 main에 올리면 GitHub Actions가 새 APK를 만들어 같은 주소에 올립니다.
- 앱 주소가 바뀌면 `app/build.gradle.kts`의 `appUrl`만 고칩니다.
- 서명 키(`keystore/mulddae.jks`)는 업데이트 설치에 필요하므로 지우거나 바꾸지 않습니다.
