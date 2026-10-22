"""쭈갑과물때 앱 시작화면(assets/splash.html) 만들기 — '물속 쭈갑' 그림에 움직임을 넣음
실행: python android/tools/make_splash.py  → android/app/src/main/assets/splash.html
- 주꾸미·갑오징어: 위아래로 둥실 (서로 다른 박자)
- 거품: 아래에서 위로 올라가며 사라짐 / 빛줄기: 천천히 일렁임 / 수면 물결: 옆으로 흐름
"""
import math, random
from pathlib import Path
from splash_art import W, H, octopus, cuttlefish, title_block

OUT = Path(__file__).resolve().parent.parent / "app" / "src" / "main" / "assets" / "splash.html"
r = random.Random(11)

rays = "".join(
    f"<polygon class='ray' style='animation-delay:-{r.uniform(0,6):.1f}s;animation-duration:{r.uniform(5,9):.1f}s' "
    f"points='{x:.0f},0 {x+w:.0f},0 {x+w*3+160:.0f},{H} {x-40:.0f},{H}' fill='#bff1ff' opacity='{r.uniform(.04,.08):.3f}'/>"
    for x, w in [(r.uniform(-60, 420), r.uniform(18, 50)) for _ in range(7)])
bubbles = "".join(
    f"<circle class='bub' style='animation-duration:{r.uniform(5,11):.1f}s;animation-delay:-{r.uniform(0,11):.1f}s' "
    f"cx='{r.uniform(10,470):.1f}' cy='{r.uniform(420,1000):.1f}' r='{r.uniform(2,8):.1f}' fill='none' stroke='#bff1ff' "
    f"stroke-opacity='{r.uniform(.25,.6):.2f}' stroke-width='1.2'/>" for _ in range(34))
sand = "".join(f"<ellipse cx='{r.uniform(0,480):.0f}' cy='{r.uniform(985,1040):.0f}' rx='{r.uniform(10,40):.0f}' "
               f"ry='{r.uniform(3,8):.0f}' fill='#2b4a52' opacity='.6'/>" for _ in range(20))
wave = lambda y, op, w: (f"<path class='wave' d='M-160 {y} " + " ".join(f"q 40 -14 80 0 t 80 0" for _ in range(6)) +
                         f"' fill='none' stroke='#bff1ff' stroke-opacity='{op}' stroke-width='{w}'/>")

svg = f"""<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid slice' xmlns='http://www.w3.org/2000/svg'>
<defs><linearGradient id='w' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#1f6680'/><stop offset='.4' stop-color='#0f3047'/><stop offset='1' stop-color='#071520'/></linearGradient></defs>
<rect x='-200' y='-200' width='{W+400}' height='{H+400}' fill='url(#w)'/>
<g>{rays}</g>
{wave(60, .35, 2)}{wave(84, .18, 1.5)}
<g class='title'>{title_block(190, '주꾸미 · 갑오징어 물때')}</g>
<g class='bob gg'>{cuttlefish(330, 470, .8, 28, seed=6)}</g>
<g class='bob jj'>{octopus(150, 760, .78, -12, seed=5)}</g>
<g>{bubbles}</g>
<path d='M-200 990 Q 120 960 240 985 T 680 975 L680 1240 L-200 1240Z' fill='#13303a'/>{sand}
</svg>"""

html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>쭈갑과물때</title>
<style>
html,body{{margin:0;height:100%;background:#071520;overflow:hidden}}
svg{{position:fixed;inset:0;width:100%;height:100%;display:block}}
text{{font-family:'Noto Sans KR','Noto Sans CJK KR','Samsung Sans',sans-serif}}
.bob{{transform-box:view-box;animation:bob 3s ease-in-out infinite}}
.jj{{animation-duration:2.6s}}
.gg{{animation-duration:3.3s;animation-delay:-1.1s}}
@keyframes bob{{0%,100%{{transform:translateY(-14px)}}50%{{transform:translateY(16px)}}}}
.bub{{transform-box:fill-box;animation:rise 8s linear infinite}}
@keyframes rise{{0%{{transform:translateY(0);opacity:0}}12%{{opacity:1}}100%{{transform:translateY(-420px);opacity:0}}}}
.ray{{animation:shine 7s ease-in-out infinite}}
@keyframes shine{{0%,100%{{opacity:.03}}50%{{opacity:.1}}}}
.wave{{animation:flow 4s linear infinite}}
@keyframes flow{{from{{transform:translateX(0)}}to{{transform:translateX(160px)}}}}
.title{{animation:fadein .9s ease-out both}}
@keyframes fadein{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
#wait{{position:fixed;left:0;right:0;bottom:calc(2.2% + env(safe-area-inset-bottom,0px));text-align:center;color:#bfe6f2;
  font:500 14px 'Noto Sans KR',sans-serif;letter-spacing:.06em;opacity:0;transition:opacity .6s}}
#wait.on{{opacity:.85}}
#wait i{{display:inline-block;width:6px;height:6px;margin:0 3px;border-radius:50%;background:#bfe6f2;animation:dot 1.2s infinite}}
#wait i:nth-child(2){{animation-delay:.2s}}#wait i:nth-child(3){{animation-delay:.4s}}
@keyframes dot{{0%,100%{{opacity:.2}}50%{{opacity:1}}}}
@media (prefers-reduced-motion:reduce){{.bob,.bub,.ray,.wave,#wait i{{animation:none}}}}
</style></head><body>
{svg}
<div id="wait">물때 불러오는 중 <i></i><i></i><i></i></div>
<script>setTimeout(function(){{document.getElementById('wait').classList.add('on')}},2500)</script>
</body></html>
"""
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print("written", OUT, len(html))
