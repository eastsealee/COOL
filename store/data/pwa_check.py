"""홈 화면 앱(PWA) 확인: 매니페스트·아이콘·서비스워커 → out/pwa.md"""
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
U = "https://eastsealee.github.io/COOL/"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(**p.devices["Galaxy S9+"]); pg = ctx.new_page()
    pg.goto(U, timeout=120000); pg.wait_for_timeout(8000)
    r = pg.evaluate("""async()=>{const m=document.querySelector('link[rel=manifest]');const j=m?await (await fetch(m.href)).json():null;
      const regs=navigator.serviceWorker?await navigator.serviceWorker.getRegistrations():[];
      const ic=await Promise.all((j?j.icons:[]).map(async i=>{const r=await fetch(new URL(i.src,m.href));return i.src+' '+r.status}));
      return {manifest:j&&j.name, display:j&&j.display, icons:ic, sw:regs.length, ctrl:!!navigator.serviceWorker.controller}}""")
    (OUT / "pwa.md").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8"); print(r)
