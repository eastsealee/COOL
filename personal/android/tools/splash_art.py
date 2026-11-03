"""쭈갑과물때 시작화면 그림 도구 (주꾸미·갑오징어·거품 등) — make_splash.py가 불러 씀"""
import math, random, asyncio
W, H = 480, 1040

def page(svg):
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#08131d}}
svg{{display:block}}text{{font-family:'Noto Sans KR','Noto Sans CJK KR',sans-serif}}</style></head><body>{svg}</body></html>"""

def tapered(pts, w0, w1):
    """중심선 점들 → 끝이 가늘어지는 다리 모양 다각형"""
    L, R = [], []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        x2, y2 = pts[min(i + 1, n - 1)]; x1, y1 = pts[max(i - 1, 0)]
        dx, dy = x2 - x1, y2 - y1; d = math.hypot(dx, dy) or 1
        nx, ny = -dy / d, dx / d
        w = (w0 + (w1 - w0) * (i / (n - 1)) ** 0.8) / 2
        L.append((x + nx * w, y + ny * w)); R.append((x - nx * w, y - ny * w))
    poly = L + R[::-1]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in poly) + "Z", L

def curl(x, y, ang, length, bend, curl_amt, steps=40):
    pts = []; a = ang
    for i in range(steps):
        t = i / (steps - 1)
        pts.append((x, y))
        a += (bend + curl_amt * t ** 2.2) / steps
        x += math.cos(a) * length / steps; y += math.sin(a) * length / steps
    return pts

def octopus(cx, cy, s=1.0, rot=0, body="#ff8a5b", dark="#b9512f", seed=1):
    """주꾸미: 둥근 머리 + 눈 옆 금테 무늬 + 말려 올라가는 8개 다리"""
    r = random.Random(seed); g = []
    uid = f"oc{seed}"
    g.append(f"<defs><radialGradient id='{uid}' cx='40%' cy='30%' r='75%'><stop offset='0' stop-color='#ffd0b3'/><stop offset='.35' stop-color='{body}'/><stop offset='1' stop-color='{dark}'/></radialGradient></defs>")
    arms = []
    for k in range(8):
        base = math.pi / 2 + (k - 3.5) * 0.36
        side = 1 if k >= 4 else -1
        pts = curl(math.cos(base) * 22, 46 + math.sin(base) * 6, base, r.uniform(150, 200), side * r.uniform(-.6, .4), side * r.uniform(2.6, 4.2))
        path, edge = tapered(pts, 22, 2.2)
        arms.append((k, path, edge))
    # 뒤쪽 다리 먼저
    for k, path, edge in sorted(arms, key=lambda a: abs(a[0] - 3.5), reverse=True):
        g.append(f"<path d='{path}' fill='url(#{uid})' stroke='{dark}' stroke-width='1'/>")
        for j in range(3, len(edge) - 6, 3):
            x, y = edge[j]; rr = 3.2 * (1 - j / len(edge)) + .8
            g.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{rr:.1f}' fill='#ffe3d1' opacity='.85'/>")
    # 머리(몸통)
    g.append(f"<path d='M-46 30 C-60 -40 -38 -96 0 -98 C38 -96 60 -40 46 30 C30 52 -30 52 -46 30Z' fill='url(#{uid})' stroke='{dark}' stroke-width='1.2'/>")
    for _ in range(26):
        x, y = r.uniform(-34, 34), r.uniform(-84, 20)
        g.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r.uniform(1,3):.1f}' fill='{dark}' opacity='.35'/>")
    # 눈 + 금테
    for ex in (-24, 24):
        g.append(f"<circle cx='{ex*1.25}' cy='30' r='12' fill='none' stroke='#ffd166' stroke-width='3.2'/>")
        g.append(f"<ellipse cx='{ex}' cy='18' rx='11' ry='12' fill='#fff4e6' stroke='{dark}' stroke-width='1.2'/><ellipse cx='{ex}' cy='19' rx='5' ry='7' fill='#1a1020'/><circle cx='{ex+2}' cy='15' r='2.2' fill='#fff'/>")
    return f"<g transform='translate({cx} {cy}) rotate({rot}) scale({s})'>{''.join(g)}</g>"

def cuttlefish(cx, cy, s=1.0, rot=0, body="#a596ff", dark="#5b4bc4", seed=2):
    """갑오징어: 타원 몸통 + 테두리 지느러미 + 등 줄무늬 + W 동공 + 짧은 다리 8개 + 긴 촉완 2개 (위에서 본 모습)"""
    r = random.Random(seed); g = []; uid = f"cf{seed}"
    g.append(f"<defs><radialGradient id='{uid}' cx='45%' cy='35%' r='75%'><stop offset='0' stop-color='#e9e4ff'/><stop offset='.45' stop-color='{body}'/><stop offset='1' stop-color='{dark}'/></radialGradient>"
             f"<clipPath id='{uid}c'><ellipse cx='0' cy='-40' rx='58' ry='108'/></clipPath></defs>")
    # 촉완 2개 (길게)
    for side in (-1, 1):
        pts = curl(side * 10, 92, math.pi / 2 + side * .25, 200, side * -.5, side * 1.4)
        path, _ = tapered(pts, 7, 3)
        g.append(f"<path d='{path}' fill='{body}' stroke='{dark}' stroke-width='.8'/>")
        ex, ey = pts[-1]
        g.append(f"<ellipse cx='{ex:.1f}' cy='{ey:.1f}' rx='8' ry='14' transform='rotate({math.degrees(math.atan2(pts[-1][1]-pts[-4][1], pts[-1][0]-pts[-4][0]))-90:.0f} {ex:.1f} {ey:.1f})' fill='{body}' stroke='{dark}'/>")
    # 다리 8개 (짧고 굵게)
    for k in range(8):
        base = math.pi / 2 + (k - 3.5) * 0.2
        side = 1 if k >= 4 else -1
        pts = curl(math.cos(base) * 26, 88, base, r.uniform(70, 95), side * r.uniform(.2, .6), side * r.uniform(.4, 1.2), 24)
        path, edge = tapered(pts, 14, 2)
        g.append(f"<path d='{path}' fill='url(#{uid})' stroke='{dark}' stroke-width='.9'/>")
    # 지느러미 (몸통 둘레 물결)
    fin = []
    for i in range(0, 361, 4):
        a = math.radians(i); w = 1 + .06 * math.sin(a * 14)
        fin.append(f"{68*w*math.cos(a):.1f},{-40+118*w*math.sin(a):.1f}")
    g.append(f"<polygon points='{' '.join(fin)}' fill='{body}' opacity='.45' stroke='{body}' stroke-width='1.2'/>")
    # 몸통 + 얼룩말 줄무늬
    g.append(f"<ellipse cx='0' cy='-40' rx='58' ry='108' fill='url(#{uid})' stroke='{dark}' stroke-width='1.4'/>")
    stripes = []
    for k in range(13):
        y = -138 + k * 15
        d = f"M-60 {y} " + " ".join(f"Q {-45+j*30} {y+(-7 if j%2 else 7)} {-30+j*30} {y}" for j in range(4))
        stripes.append(f"<path d='{d}' fill='none' stroke='#f6f2ff' stroke-opacity='.55' stroke-width='{3.2 if k%2 else 1.6}'/>")
    g.append(f"<g clip-path='url(#{uid}c)'>{''.join(stripes)}</g>")
    # 머리 + 눈 (W 모양 동공)
    g.append(f"<ellipse cx='0' cy='78' rx='40' ry='26' fill='url(#{uid})' stroke='{dark}' stroke-width='1.2'/>")
    for ex in (-30, 30):
        g.append(f"<ellipse cx='{ex}' cy='72' rx='12' ry='10' fill='#f3e7b8' stroke='{dark}' stroke-width='1.2'/>"
                 f"<path d='M{ex-7} 71 Q {ex-4} 76 {ex-1.5} 72.5 Q {ex} 77 {ex+1.5} 72.5 Q {ex+4} 76 {ex+7} 71 Q {ex} 67 {ex-7} 71Z' fill='#1a1020'/>"
                 f"<circle cx='{ex+3}' cy='68' r='1.8' fill='#fff'/>")
    return f"<g transform='translate({cx} {cy}) rotate({rot}) scale({s})'>{''.join(g)}</g>"

def stars(n, ymax, seed=1):
    r = random.Random(seed)
    return "".join(f"<circle cx='{r.uniform(0,W):.1f}' cy='{r.uniform(0,ymax):.1f}' r='{r.uniform(.3,1.2):.2f}' fill='#fff' opacity='{r.uniform(.15,.7):.2f}'/>" for _ in range(n))

def bubbles(n, y0, y1, seed=5, col="#bff1ff"):
    r = random.Random(seed)
    return "".join(f"<circle cx='{r.uniform(10,470):.1f}' cy='{r.uniform(y0,y1):.1f}' r='{r.uniform(2,8):.1f}' fill='none' stroke='{col}' stroke-opacity='{r.uniform(.2,.55):.2f}' stroke-width='1.2'/>" for _ in range(n))

def title_block(y, sub, align="middle", x=240, size=50):
    return (f"<text x='{x}' y='{y}' text-anchor='{align}' font-size='{size}' font-weight='900' fill='#fff' letter-spacing='-1'>"
            f"<tspan fill='#ff9a6b'>쭈</tspan><tspan fill='#b7a9ff'>갑</tspan>과물때</text>"
            f"<text x='{x}' y='{y+40}' text-anchor='{align}' font-size='15' font-weight='500' fill='#c7d3df' letter-spacing='3'>{sub}</text>")

def tide_line(y, amp, col="#4cc3e6", op=.9, w=3):
    d = " ".join(f"{'M' if i==0 else 'L'}{i*4} {y-amp*math.cos(i*4/W*2*math.pi*1.6+.5):.1f}" for i in range(W // 4 + 1))
    return f"<path d='{d}' fill='none' stroke='{col}' stroke-width='{w}' opacity='{op}'/>"

# 1. 쭈갑 듀오 — 밤바다, 둘이 마주 봄, 아래 물때 곡선
def duo():
    return f"""<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}'>
<defs><radialGradient id='bg' cx='50%' cy='40%' r='80%'><stop offset='0' stop-color='#173550'/><stop offset='.6' stop-color='#0b1a28'/><stop offset='1' stop-color='#050c14'/></radialGradient>
<radialGradient id='gl1' cx='50%' cy='50%' r='50%'><stop offset='0' stop-color='#ff8a5b' stop-opacity='.35'/><stop offset='1' stop-color='#ff8a5b' stop-opacity='0'/></radialGradient>
<radialGradient id='gl2' cx='50%' cy='50%' r='50%'><stop offset='0' stop-color='#a596ff' stop-opacity='.35'/><stop offset='1' stop-color='#a596ff' stop-opacity='0'/></radialGradient></defs>
<rect width='{W}' height='{H}' fill='url(#bg)'/>{stars(70, 260, 4)}
<circle cx='150' cy='420' r='170' fill='url(#gl1)'/><circle cx='340' cy='470' r='180' fill='url(#gl2)'/>
{octopus(175, 380, .82, 10, seed=1)}
{cuttlefish(348, 420, .85, -14, seed=2)}
{bubbles(16, 160, 700, 7)}
{tide_line(800, 26, '#2a6f8f', .5, 1.5)}{tide_line(790, 30)}
<circle cx='{W*0.5/1.6/2:.0f}' cy='760' r='0' fill='none'/>
{title_block(895, '주꾸미 · 갑오징어 · 물때')}
</svg>"""

# 2. 주꾸미 포스터 — 따뜻한 주황 바탕, 크게 한 마리
def octo_poster():
    return f"""<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}'>
<defs><linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#2a1410'/><stop offset='.5' stop-color='#3d1c14'/><stop offset='1' stop-color='#120807'/></linearGradient>
<radialGradient id='sp' cx='50%' cy='45%' r='55%'><stop offset='0' stop-color='#ff8a5b' stop-opacity='.45'/><stop offset='1' stop-color='#ff8a5b' stop-opacity='0'/></radialGradient></defs>
<rect width='{W}' height='{H}' fill='url(#bg)'/>
<circle cx='240' cy='430' r='260' fill='url(#sp)'/>
<circle cx='240' cy='430' r='200' fill='none' stroke='#ffb38a' stroke-opacity='.25' stroke-width='1.5' stroke-dasharray='3 7'/>
{octopus(240, 380, 1.45, 0, seed=3)}
{bubbles(14, 120, 760, 9, '#ffd2b8')}
<text x='240' y='130' text-anchor='middle' font-size='14' font-weight='700' fill='#ffb38a' letter-spacing='6'>JJUKKUMI</text>
{title_block(880, '오늘 주꾸미 물때는?')}
</svg>"""

# 3. 갑오징어 포스터 — 보라 바탕, 크게 한 마리
def cuttle_poster():
    return f"""<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}'>
<defs><linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#15122e'/><stop offset='.5' stop-color='#1d1842'/><stop offset='1' stop-color='#080716'/></linearGradient>
<radialGradient id='sp' cx='50%' cy='45%' r='55%'><stop offset='0' stop-color='#a596ff' stop-opacity='.45'/><stop offset='1' stop-color='#a596ff' stop-opacity='0'/></radialGradient></defs>
<rect width='{W}' height='{H}' fill='url(#bg)'/>
<circle cx='240' cy='440' r='260' fill='url(#sp)'/>
<circle cx='240' cy='440' r='205' fill='none' stroke='#c9c0ff' stroke-opacity='.25' stroke-width='1.5' stroke-dasharray='3 7'/>
{cuttlefish(240, 400, 1.35, 0, seed=4)}
{bubbles(14, 120, 760, 13, '#d9d3ff')}
<text x='240' y='130' text-anchor='middle' font-size='14' font-weight='700' fill='#c9c0ff' letter-spacing='6'>GABOJINGEO</text>
{title_block(880, '오늘 갑오징어 물때는?')}
</svg>"""

# 4. 물속 쭈갑 — 빛줄기 아래 함께 헤엄
def underwater():
    r = random.Random(11)
    rays = "".join(f"<polygon points='{x},0 {x+w},0 {x+w*3+160},{H} {x-40},{H}' fill='#bff1ff' opacity='{r.uniform(.03,.07):.3f}'/>" for x, w in [(r.uniform(-60, 420), r.uniform(18, 50)) for _ in range(7)])
    sand = "".join(f"<ellipse cx='{r.uniform(0,480):.0f}' cy='{r.uniform(985,1040):.0f}' rx='{r.uniform(10,40):.0f}' ry='{r.uniform(3,8):.0f}' fill='#2b4a52' opacity='.6'/>" for _ in range(20))
    return f"""<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}'>
<defs><linearGradient id='w' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#1f6680'/><stop offset='.4' stop-color='#0f3047'/><stop offset='1' stop-color='#071520'/></linearGradient></defs>
<rect width='{W}' height='{H}' fill='url(#w)'/>{rays}
<path d='M0 60 q 40 -14 80 0 t 80 0 t 80 0 t 80 0 t 80 0 t 80 0' fill='none' stroke='#bff1ff' stroke-opacity='.35' stroke-width='2'/>
{title_block(190, '주꾸미 · 갑오징어 물때')}
{cuttlefish(330, 470, .8, 28, seed=6)}
{octopus(150, 760, .78, -12, seed=5)}
{bubbles(30, 260, 980, 21)}
<path d='M0 990 Q 120 960 240 985 T 480 975 L480 1040 L0 1040Z' fill='#13303a'/>{sand}
</svg>"""

