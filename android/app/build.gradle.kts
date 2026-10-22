plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 앱이 여는 주소 — Streamlit 앱 주소가 바뀌면 여기만 고치면 됨
val appUrl = "https://kim-sunsang24.streamlit.app/mulddae-clock"

android {
    namespace = "com.eastsealee.mulddae"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.eastsealee.mulddae"
        minSdk = 26
        targetSdk = 35
        // 빌드할 때마다 버전 번호가 올라가야 폰에서 '업데이트'로 설치됨 (GitHub Actions 실행 번호 사용)
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "1.0." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
        buildConfigField("String", "APP_URL", "\"$appUrl\"")
    }

    signingConfigs {
        // 개인용 앱 서명 키 (저장소에 함께 둠 — 같은 키로 서명해야 덮어쓰기 업데이트가 됨)
        create("release") {
            storeFile = file("../keystore/mulddae.jks")
            storePassword = "mulddae-clock"
            keyAlias = "mulddae"
            keyPassword = "mulddae-clock"
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
