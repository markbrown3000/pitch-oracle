# One-off: saves Mastercaller TV-event pages to probe/ so their format can be inspected.
import os, re, urllib.request, time
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; PitchOracle/1.0; +https://github.com/markbrown3000/pitch-oracle)"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read().decode("utf-8", "replace")
    except Exception as e: return "ERROR " + repr(e)
for t in ["grand-slam-of-darts", "players-championship-finals", "pdc-world-championship"]:
    h = get(f"https://mastercaller.com/tournaments/{t}"); open(f"probe/{t}.html", "w").write(h); time.sleep(2)
    slugs = sorted(set(re.findall(rf'/tournaments/{t}/(20\d\d[^"/]*)"', h)))
    print(t, slugs[-4:])
    for s in slugs[-2:]:
        for sub in ("", "/results", "/schedule", "/draw"):
            open(f"probe/{t}_{s}{sub.replace('/', '_')}.html", "w").write(get(f"https://mastercaller.com/tournaments/{t}/{s}{sub}")); time.sleep(2)
