"""라마르호 '오늘의 조과' 블로그 글 → 분석 데이터 한 줄 (data/lamar_days.json 형식)

lamar_update.py 가 매일 새 글을 가져와 이 모듈로 분석합니다.
(처음 586일 데이터를 만들 때 쓴 분석 방식과 같습니다.)
"""
import re
import statistics
import datetime as dt

WD = "월화수목금토일"
TIDE_CYCLE = ["7물", "8물", "9물", "10물", "11물", "12물", "13물", "조금", "무시",
              "1물", "2물", "3물", "4물", "5물", "6물"]


# ------------------------------------------------------------ 본문 정리
def clean_body(body):
    """블로그에서 문단이 겹쳐 두 번 들어간 줄을 하나로"""
    lines = [l.strip() for l in (body or "").split("\n") if l.strip()]
    out, last = [], ""
    for l in lines:
        k = re.sub(r"\s+", "", l)
        if last and k in last:
            continue
        out.append(l)
        last = k
    return "\n".join(out)


def sentences(text):
    out = []
    for line in text.split("\n"):
        for s in re.split(r"(?<=[.!?~])\s*(?=[^\s.!?~])", line):
            s = s.strip()
            if len(s) >= 6:
                out.append(s)
    return out


# ------------------------------------------------------------ 마릿수
EXCL = re.compile(r"목표|넘게|넘기|정도|까지|거뜬|생각|했다면|였다면|어제|작년|지난|예상|기록을 세워|평균|이상|이하|전날|저번|라면|면 좋|만이라도|최고기록|역대")
ANG = re.compile(r"님(?:은|이|께서는|께서|도)?\s*(?:(?:주꾸미|쭈꾸미|쭈)\s*)?(\d{1,3})\s*마리(?:[\s,]*(?:갑오징어|갑)\s*(\d{1,3})\s*마리)?")


def catches(sents):
    jj, gg = [], []
    for s in sents:
        if EXCL.search(s):
            continue
        for m in ANG.finditer(s):
            n = int(m.group(1))
            if 1 <= n <= 600:
                jj.append(n)
                if m.group(2):
                    gg.append(int(m.group(2)))
    return jj, gg


# ------------------------------------------------------------ 본문 분위기 · 날씨
POS = {"잘 나와": 2, "잘나와": 2, "폭발": 3, "대박": 3, "마릿수": 0.5, "쌍걸이": 0.6, "손맛": 1, "만족": 1.5, "최고": 1,
       "좋았": 1.5, "좋은 날": 2, "좋더라": 1, "괜찮": 1, "꾸준히": 1.2, "활성도가 좋": 2, "활성도도 좋": 2, "재미있": 1,
       "즐겁": 1, "즐거": 1, "신나": 1, "훈훈": 0.5, "라마르타임": 1.5, "올라타": 1, "씨알": 0.5, "큰 녀석": 0.8,
       "크기가 좋": 1, "크기 좋": 1, "완벽": 2, "화창": 1, "잔잔": 1.2, "장판": 1.5, "맑": 0.6, "심심할 틈": 2,
       "쉴 틈": 1.5, "틈이 없": 1.5}
NEG = {"안 나와": 2, "안나와": 2, "꽝": 0.6, "저조": 2, "몰황": 3, "어려": 1.2, "힘들": 1.2, "아쉬": 1.2, "아쉽": 1.2,
       "고전": 1.5, "부진": 1.5, "뜸하": 1.5, "뜸했": 1.5, "끊어": 1.2, "끊겼": 1.2, "떨어진": 1, "활성도가 떨어": 2,
       "활성도가 낮": 2, "밑걸림": 1, "고생": 1.2, "지옥": 2, "실망": 1.5, "답답": 1.2, "심심하": 1.5, "심심했": 1.5,
       "심심~": 1.5, "심심한": 1.2, "한숨": 1.2, "걱정": 0.6, "기상악화": 2, "철수": 1.5, "조기": 1, "탁": 0.4, "멀미": 1}
WEATHER = {
    "바람": r"바람이 (?:많이|강하게|세게|거세|엄청|꽤)|강풍|돌풍|바람(?:에|이)\s*(?:고생|힘들)|칼바람",
    "파도/너울": r"파도|너울|울렁|롤링|요동",
    "비": r"비가|빗방울|소나기|비 (?:오|내리)|우비",
    "안개": r"안개|해무",
    "맑음/잔잔": r"화창|맑은|맑았|잔잔|장판|날씨가 (?:좋|너무 좋)|바다가 (?:좋|잔잔)",
    "더위": r"더위|더웠|덥|땡볕|폭염",
    "추위": r"추위|추웠|춥|쌀쌀|칼바람|한기",
    "물색 탁함": r"물색이 (?:탁|안 좋|좋지)|탁한|뻘물|흙탕",
    "배 많음": r"배들(?:이|로)|선단|많은 배|배가 많",
}
WPEN = {"바람": 18, "파도/너울": 12, "비": 8, "안개": 5, "더위": 5, "추위": 6, "물색 탁함": 8, "배 많음": 3}

# ------------------------------------------------------------ 시간대별 조황
LUNCH = re.compile(r"점심|식사(?!.{0,3}(?:대접|자리))|밥\s*(?:을\s*)?먹")
AM = re.compile(r"오전|아침|새벽|초반|첫\s*포인트|처음에는|시작(?:부터|하자마자)|출항(?:하자|후)")
PM = re.compile(r"오후|후반|막판|마지막\s*포인트|입항\s*(?:전|직전)|철수\s*전|해가\s*(?:지|기울)")
BEFORE_L = re.compile(r"점심\s*(?:전|때까지|먹기\s*전|시간\s*전)|식사\s*(?:전|하기\s*전)")
AFTER_L = re.compile(r"점심\s*(?:후|이후|먹고|을\s*먹고|을\s*먹은|식사\s*후|을\s*마치)|식사\s*(?:후|를?\s*마치|하고)|밥\s*먹고")
LT = re.compile(r"라마르\s*타임")
SEG_CATCH = re.compile(r"나와|나오|나온|잡아|잡으|잡히|입질|활성도|마릿수|폭발|뜸|끊|쌍걸이|올라|반응|타\s*주|붙|조용|살아나|터지|쏟아")
POSW = ["잘 잡", "묵직", "늘어나", "웃었", "웃게", "웃고", "웃으", "피딩", "손맛", "좋은 시간", "잘 나와", "잘 나오", "잘 나온",
        "잘나와", "폭발", "쏟아", "터지", "터졌", "살아나", "살아났", "올라타", "쌍걸이", "꾸준히", "계속 나", "연신",
        "마릿수를 올", "마릿수를 쭉", "좋았", "좋아졌", "좋더라", "괜찮", "활성도가 좋", "활성도도 좋", "활성도가 올라",
        "반응이 좋", "입질이 들어", "나와주", "나와줬", "나와주기", "나와주었", "잡아올리", "신나", "대박", "최고", "만회",
        "역전", "집중"]
NEGW = ["울었", "울게", "울고", "삐끗", "줄어들", "줄어드", "살아나질", "살아나지", "안 나와", "안 나오", "안 나왔", "안나와",
        "안나오", "뜸", "끊어", "끊겼", "끊기", "조용", "저조", "답답", "심심", "떨어", "고전", "부진", "못 잡", "못잡", "없었",
        "없더라", "없네", "안 타", "아쉬", "아쉽", "힘들", "어려", "꽝", "반응이 없", "입질이 없", "한 마리씩", "드문드문",
        "가뭄", "실망", "울었"]
NEGMARK = re.compile(r"지\s*않|지\s*못|않던|않았|않네|않더|않고|않는|안\s*되|안되|안\s*나|안나|못\s*잡|못\s*하|못했|끊|뜸|조용|없었|없더|없네|입질이 없|멈추|멈췄|가뭄|드문|꽝")


def _polarity(s):
    w = 0.3 if "님" in s else 1.0
    p = sum(s.count(x) for x in POSW)
    n = sum(s.count(x) for x in NEGW)
    if NEGMARK.search(s):
        n = n + p + 1
        p = 0
    return p * w, n * w


def segments(text, title=""):
    ss = sentences(text)
    if not ss:
        return None
    n = len(ss)
    cand = [i for i, s in enumerate(ss) if LUNCH.search(s) and "후식" not in s and 0.25 * n <= i <= 0.85 * n]
    li = cand[0] if cand else None
    seg = {k: [0, 0, 0] for k in ["오전", "점심전", "점심후", "오후", "라마르타임"]}
    phase, lt_left = "오전", 0
    split = li if li is not None else len(ss) // 2
    for i, s in enumerate(ss):
        if i >= split:
            phase = "오후"
        tags = set()
        if AM.search(s) and not PM.search(s):
            tags.add("오전")
        if PM.search(s) and not AM.search(s):
            tags.add("오후")
        if AM.search(s) and PM.search(s):
            parts = re.split(r"(?=오후|후반|막판)", s, maxsplit=1)
            if len(parts) == 2:
                for part, lab in ((parts[0], "오전"), (parts[1], "오후")):
                    if SEG_CATCH.search(part):
                        p, q = _polarity(part)
                        seg[lab][0] += p
                        seg[lab][1] += q
                        seg[lab][2] += 1
                continue
        if not tags:
            tags.add(phase)
        if BEFORE_L.search(s) or (li is not None and li - 4 <= i < li):
            tags.add("점심전")
        if AFTER_L.search(s) or (li is not None and li < i <= li + 5):
            tags.add("점심후")
        if LT.search(s):
            lt_left = 3
        if lt_left > 0:
            tags.add("라마르타임")
            lt_left -= 1
        explicit = (AM.search(s) or PM.search(s) or LT.search(s)) and re.search(r"웃|울|좋|나쁘|아쉬|최고|대박|꽝|나와|나오|잡", s)
        if not SEG_CATCH.search(s) and not explicit:
            continue
        p, q = _polarity(s)
        if explicit and "님" not in s:
            p, q = p * 2, q * 2
        for t in tags:
            seg[t][0] += p
            seg[t][1] += q
            seg[t][2] += 1
    t = title

    def tadd(keys, p, q):
        for k in keys:
            seg[k][0] += p
            seg[k][1] += q
            seg[k][2] += 1

    TP = r"꾸준|잘 나|폭발|웃|좋|완벽|대박|시원|만족|피딩"
    TN = r"심심|답답|괴롭|울|꽝|힘들|없던|못|아쉬|고전|저조"
    if "하루종일" in t:
        if re.search(TP, t):
            tadd(["오전", "오후"], 2, 0)
        if re.search(TN, t):
            tadd(["오전", "오후"], 0, 2)
    m = re.search(r"오전[^,.]*?(웃|좋|잘|폭발)|오전[^,.]*?(울|심심|안|못)", t)
    if m:
        tadd(["오전"], 3 if m.group(1) else 0, 0 if m.group(1) else 3)
    m = re.search(r"오후[^,.]*?(웃|좋|잘|폭발|피딩)|오후[^,.]*?(울|심심|안|못)", t)
    if m:
        tadd(["오후"], 3 if m.group(1) else 0, 0 if m.group(1) else 3)
    if LT.search(t):
        if re.search(r"없|못|아쉬", t):
            tadd(["라마르타임"], 0, 3)
        else:
            tadd(["라마르타임", "오후"], 3, 0)
    out = {}
    for k, (p, q, c) in seg.items():
        out[k] = None if c == 0 or p + q < 0.5 else round((p + 0.7) / (p + q + 1.4) * 100)
    return out


# ------------------------------------------------------------ 본문 발췌
KW = {"활성도": 3, "입질": 2, "나와": 2, "나오": 1.5, "폭발": 3, "뜸": 3, "끊": 2, "마릿수": 1.5, "물때": 2, "사리": 2,
      "조금": 0.5, "물색": 2.5, "수온": 2.5, "바람": 2, "파도": 2, "비가": 1.5, "안개": 2, "날씨": 1.5, "오전": 1,
      "오후": 1, "포인트": 0.8, "조류": 2, "물살": 2, "라마르타임": 2.5, "쌍걸이": 0.5, "잡": 0.7}
BAD = re.compile(r"님|\?|ㅋㅋ|ㅎㅎ|사진|간식|감사|선물|안녕하세요|최선장입니다|내일|예약")


def key_sentences(text):
    ss, seen = [], set()
    for s in sentences(text):
        k = re.sub(r"\s", "", s)
        if k not in seen:
            seen.add(k)
            ss.append(s)

    def choose(th):
        cand = [(sum(w for kk, w in KW.items() if kk in s), i, s) for i, s in enumerate(ss)
                if not BAD.search(s) and 15 <= len(s) <= 95]
        cand = [c for c in cand if c[0] >= th]
        return [s for _, _, s in sorted(sorted(cand, reverse=True)[:3], key=lambda x: x[1])]

    return choose(3) or choose(1.5)


# ------------------------------------------------------------ 한 글 분석
def lunar_mul(d):
    from korean_lunar_calendar import KoreanLunarCalendar
    c = KoreanLunarCalendar()
    c.setSolarDate(d.year, d.month, d.day)
    return f"{c.lunarMonth}/{c.lunarDay}", TIDE_CYCLE[(c.lunarDay - 1) % 15]


def analyze_post(date_iso, title, link, raw_body):
    """블로그 글 하나 → lamar_days.json 한 줄 (catch_pct·score는 finalize()에서 계산)"""
    body = clean_body(raw_body)
    d = dt.date.fromisoformat(date_iso)
    ss = sentences(body)
    pos = sum(w * body.count(k) for k, w in POS.items()) + 2 * sum(w * title.count(k) for k, w in POS.items())
    neg = sum(w * body.count(k) for k, w in NEG.items()) + 2 * sum(w * title.count(k) for k, w in NEG.items())
    if body:
        sent = (pos + 3) / (pos + neg + 6) * 100
    else:
        p = sum(w * title.count(k) for k, w in POS.items())
        q = sum(w * title.count(k) for k, w in NEG.items())
        sent = (p + 1) / (p + q + 2) * 100
    tags = [k for k, rx in WEATHER.items() if re.search(rx, body + " " + title)]
    wpen = sum(WPEN.get(k, 0) for k in tags) - (12 if "맑음/잔잔" in tags else 0)
    weather = max(0, min(100, 75 - wpen))
    jj, gg = catches(ss)
    species = []
    if re.search(r"주꾸미|쭈꾸미|쭈", title + body):
        species.append("주꾸미")
    if re.search(r"갑오징어|쭈갑|갑쭈", title + body):
        species.append("갑오징어")
    lunar, mul = lunar_mul(d)
    seg = segments(body, title) or {}
    r = dict(
        date=date_iso, wd=WD[d.weekday()], title=title, link=link,
        sent=round(sent), weather=weather, tags=tags, species=species, lunar=lunar, mul=mul,
        jj_n=len(jj),
        jj_med=statistics.median(jj) if len(jj) >= 3 else None,
        jj_max=max(jj) if len(jj) >= 3 else None,
        jj_min=min(jj) if len(jj) >= 3 else None,
        gg_med=statistics.median(gg) if gg else None,
        gg_max=max(gg) if gg else None,
        gg_min=min(gg) if gg else None,
        am=seg.get("오전"), pre_lunch=seg.get("점심전"), post_lunch=seg.get("점심후"), pm=seg.get("오후"),
        lt=seg.get("라마르타임"),
        key=key_sentences(body),
        _hasbody=bool(body),
    )
    segs = [v for v in (r["am"], r["pm"]) if v is not None]
    r["seg_avg"] = round(statistics.mean(segs)) if segs else None
    parts = []
    if r["jj_med"] is not None:
        parts.append(f"손님 {len(jj)}명 기록 기준 주꾸미 중앙값 {r['jj_med']:g}마리(최고 {r['jj_max']}마리)"
                     + (f", 갑오징어 최고 {r['gg_max']}마리" if r["gg_max"] else ""))
    r["stats"] = " / ".join(parts)
    return r


def finalize(rows):
    """전체 데이터 기준으로 조과 백분위(같은 달 비교)와 산출 근거·기본 점수를 다시 계산"""
    by_m = {}
    for r in rows:
        if r.get("jj_med") is not None:
            by_m.setdefault(r["date"][5:7], []).append(r["jj_med"])

    def pct(v, arr):
        return 100 * sum(1 for a in arr if a < v) / len(arr) + 50 * sum(1 for a in arr if a == v) / len(arr)

    for r in rows:
        r["catch_pct"] = round(pct(r["jj_med"], by_m[r["date"][5:7]])) if r.get("jj_med") is not None else None
        hasbody = r.pop("_hasbody", r.get("basis") != "제목만")
        if not hasbody:
            r["basis"], r["score"] = "제목만", round(r["sent"])
            continue
        body_part = r["sent"] if r.get("seg_avg") is None else (r["sent"] + r["seg_avg"]) / 2
        if r["catch_pct"] is not None:
            r["basis"] = "조과+본문+날씨" + ("+시간대" if r.get("seg_avg") is not None else "")
            r["score"] = round(0.5 * r["catch_pct"] + 0.3 * body_part + 0.2 * r["weather"])
        else:
            r["basis"] = "본문+날씨" + ("+시간대" if r.get("seg_avg") is not None else "")
            r["score"] = round(0.6 * body_part + 0.4 * r["weather"])
    return rows
