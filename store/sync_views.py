"""개인 버전 화면을 플레이스토어 버전으로 복사 (화면 코드는 한 곳에서만 고치고, 고친 뒤 이걸 실행)
python store/sync_views.py
- personal/mulddae/dial_component → store/web/views/dial   (물때 시계·조류 레이더·입질 확률·지도)
- personal/chaebi/rig_component   → store/web/views/rig    (채비 계산기)
- personal/android/.../splash.html → store/web/splash.html (첫 화면)
store 화면에서는 D.store=true 를 넘겨 예약조회·라마르 같은 개인용 기능을 숨김
"""
import shutil
from pathlib import Path

R = Path(__file__).resolve().parents[1]
W = R / "store" / "web"
for src, dst in ((R / "personal/mulddae/dial_component", W / "views/dial"), (R / "personal/chaebi/rig_component", W / "views/rig")):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
shutil.copy(R / "personal/android/app/src/main/assets/splash.html", W / "splash.html")
# 채비 계산기: model.js를 화면 파일 안에 넣음 (따로 받다가 실패하면 화면이 비는 문제 방지)
rig = W / "views/rig/index.html"
t = rig.read_text(encoding="utf-8")
t = t.replace('<script src="model.js"></script>', "<script>\n" + (W / "views/rig/model.js").read_text(encoding="utf-8") + "\n</script>")
rig.write_text(t, encoding="utf-8")
print("복사 완료")
