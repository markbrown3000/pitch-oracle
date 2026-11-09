# Builds data/snooker.json for the Snooker tab, with the darts engine (tools/darts.py and darts_model.py):
# each player is rated from the frames they win and lose, newer matches counting more.
# Events come from Wikipedia: every event linked from the current and previous snooker season pages.
import os, re, sys, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(__file__))
import darts as E

E.UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle; snooker tab)"}
E.SKIP = ("Women", "Seniors", "Amateur", "Under-", "qualifying", "Q School", "World Cup", "snooker season", "SEA Games", "Pink Ribbon", "Shoot Out", "Championship League", "Six-red", "6-Red", "World Games")
E.STATE = "data/snooker_state.json"; E.OUT = "data/snooker.json"; E.MATCHES = "data/snooker_matches.json"
E.USE_MC = False
E.POLY_TAG = "snooker"
E.on_stage = lambda ev: True
# tuned on 2026 results (950 matches): prior 0.4 beat 0.6 and 0.9; recency 240 days beat 120 and 400
E.KW = dict(avg_w=0.0, half_life=240, prior_sd=0.4, k_avg=0.0, stage_sd=0.0)
E.KEEP = lambda t: not re.search(r"season|SEA Games|Pink Ribbon", t)

def titles(today):
    y = today.year
    # seasons run August to May: the current one and the one before
    s0 = y if today.month >= 7 else y - 1
    names = [f"{a}–{str(a + 1)[2:]} snooker season" for a in (s0 - 1, s0)]
    pages = E.fetch(names); out = set()
    for txt in pages.values():
        out |= set(re.findall(r"\[\[((?:20\d\d) [^\]|#]+)", txt))
    return sorted(t for t in out if not any(s in t for s in E.SKIP) and s0 - 1 <= int(t[:4]) <= s0 + 1)
E.titles = titles

if __name__ == "__main__":
    E.main()
