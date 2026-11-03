"""해양조사원 조석예보(고·저조)·TideBED가 몇 년 앞까지 나오는지 확인 → out/horizon.md"""
import datetime as dt, os, sys
from pathlib import Path
from urllib.parse import unquote
import requests
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
HL = "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"
TB = "https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService"
L = ["# 예보가 나오는 기간", ""]
for d in ["20261231", "20270101", "20270601", "20271103", "20271231", "20280601", "20281231", "20291231"]:
    for name, url, p in (("조석예보 보령", HL, {"obsCode": "DT_0025"}), ("TideBED 남당항", TB, {"lat": 36.5333, "lot": 126.4667, "min": 60})):
        try:
            r = requests.get(url, params={"serviceKey": KEY, "reqDate": d, "type": "json", "pageNo": 1, "numOfRows": 30, **p}, timeout=40)
            j = r.json() if r.text.lstrip().startswith("{") else {}
            b = j.get("body") or j.get("response", {}).get("body") or {}
            it = (b.get("items") or {}); it = it.get("item", it) if isinstance(it, dict) else it
            it = it if isinstance(it, list) else ([it] if it else [])
            first = it[0] if it else {}
            L.append(f"- {d} {name}: {len(it)}건 {first.get('predcDt') or first.get('obsrvnDt') or ''} {first.get('predcTdlvVl') or first.get('obsrvnHgt') or ''} {'' if it else r.text[:120]!r}")
        except Exception as e:  # noqa: BLE001
            L.append(f"- {d} {name}: 오류 {e}")
(OUT / "horizon.md").write_text("\n".join(L), encoding="utf-8"); print("\n".join(L))
