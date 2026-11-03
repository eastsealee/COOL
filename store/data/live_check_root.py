"""실제 웹(kim-sunsang24.streamlit.app/store)을 폰 화면으로 열어 보고 상태·화면을 남김 → out/live.md, out/live_*.png"""
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
L = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(**p.devices["Galaxy S9+"]); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    import os; URL = os.environ.get("URL", "https://kim-sunsang24.streamlit.app/chaebi")
    t0 = time.time(); pg.goto(URL, timeout=120000)
    for k in range(12):
        pg.wait_for_timeout(5000)
        fr = [f.url[:100] for f in pg.frames]
        sh = [f for f in pg.frames if "store_web/index.html" in f.url]
        info = None
        if sh:
            try:
                info = sh[0].evaluate("[!!document.getElementById('splash'), document.body.className, document.getElementById('vDial').style.height, document.getElementById('msg').hidden, document.getElementById('foot').textContent.slice(0,60)]")
            except Exception as e:  # noqa: BLE001
                info = str(e)[:100]
        L.append(f"- {int(time.time() - t0)}초: 프레임 {len(fr)} · 껍데기 {info} · 본문 '{pg.inner_text('body')[:120].replace(chr(10), ' ')}'")
        pg.screenshot(path=str(OUT / f"live_{k:02d}.png"))
        if info and isinstance(info, list) and not info[0]:
            break
    L.append("- 오류: " + " | ".join(errs[:15]))
(OUT / "live.md").write_text("\n".join(L), encoding="utf-8"); print("\n".join(L))
