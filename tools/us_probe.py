# One-off: saves ESPN scoreboards and Kalshi game markets for NHL/NBA/NFL to probe/ to design the parser.
import json, os, re, time, urllib.request
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle)"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read().decode("utf-8", "replace")
    except Exception as e: return "ERROR " + repr(e)
for sp, lg in [("hockey", "nhl"), ("basketball", "nba"), ("football", "nfl")]:
    open(f"probe/espn_{lg}_today.json", "w").write(get(f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/scoreboard"))
    open(f"probe/espn_{lg}_past.json", "w").write(get(f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/scoreboard?dates=20261101-20261108&limit=300"))
    time.sleep(1)
s = get("https://api.elections.kalshi.com/trade-api/v2/series?category=Sports")
try:
    ser = [x for x in json.loads(s).get("series", []) if re.search(r"NHL|NBA|NFL", x.get("ticker", "") + x.get("title", ""))]
    open("probe/kalshi_series_us.json", "w").write(json.dumps([{k: x.get(k) for k in ("ticker", "title", "frequency")} for x in ser], indent=1))
except Exception as e: open("probe/kalshi_series_us.json", "w").write("ERROR " + repr(e) + s[:500])
for t in ["KXNHLGAME", "KXNBAGAME", "KXNFLGAME"]:
    open(f"probe/kalshi_{t}_open.json", "w").write(get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={t}&status=open&with_nested_markets=true&limit=50"))
    open(f"probe/kalshi_{t}_settled.json", "w").write(get(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={t}&status=settled&limit=200"))
    time.sleep(1)
print(sorted((f, os.path.getsize("probe/" + f)) for f in os.listdir("probe")))
