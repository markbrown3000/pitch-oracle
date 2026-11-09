# Fresh football prices for the GitHub page: DraftKings' home/draw/away odds from ESPN's public scoreboards,
# for the next few days, saved to data/live_odds.json every two hours. The page matches them to its own fixtures.
# Also keeps data/live_odds_log.json: each match's first-seen and last pre-kick-off prices, to measure later
# whether fresher prices make better picks.
import json, os, time, datetime, urllib.request

UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle; football prices)"}
# our league code -> ESPN's league slug
SLUGS = {"epl": "eng.1", "championship": "eng.2", "league_one": "eng.3", "league_two": "eng.4", "national_league": "eng.5",
         "la_liga": "esp.1", "segunda": "esp.2", "serie_a": "ita.1", "serie_b": "ita.2", "bundesliga": "ger.1", "bundesliga_2": "ger.2",
         "ligue_1": "fra.1", "ligue_2": "fra.2", "scot_prem": "sco.1", "scot_champ": "sco.2", "scot_l1": "sco.3", "scot_l2": "sco.4",
         "eredivisie": "ned.1", "belgium": "bel.1", "primeira": "por.1", "super_lig": "tur.1", "greece": "gre.1",
         "austria": "aut.1", "denmark": "den.1", "switzerland": "sui.1", "poland": "pol.1", "romania": "rou.1", "norway": "nor.1",
         "sweden": "swe.1", "finland": "fin.1", "ireland": "irl.1", "brazil": "bra.1", "argentina": "arg.1", "mexico": "mex.1",
         "mls": "usa.1", "japan": "jpn.1", "china": "chn.1"}
DAYS = 8

def get(url):
    for t in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r: return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if "404" in str(e) or "400" in str(e): return None
            time.sleep(2 * (t + 1))
    return None

def dec(a):
    try: a = float(str(a).replace("+", ""))
    except Exception: return None
    if a == 0: return None
    return round(1 + a / 100, 3) if a > 0 else round(1 + 100 / -a, 3)

def main():
    now = datetime.datetime.now(datetime.timezone.utc); today = now.date()
    out = []; counts = {}
    for code, slug in SLUGS.items():
        n = priced = 0
        for k in range(DAYS):
            d = today + datetime.timedelta(days=k)
            js = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d.strftime('%Y%m%d')}")
            time.sleep(0.25)
            for e in (js or {}).get("events", []):
                try:
                    c = e["competitions"][0]; st = e["status"]["type"]
                    if st.get("state") != "pre": continue
                    side = {t["homeAway"]: t for t in c["competitors"]}
                    row = {"lg": code, "id": e["id"], "start": e["date"], "home": side["home"]["team"]["displayName"], "away": side["away"]["team"]["displayName"],
                           "homeShort": side["home"]["team"].get("shortDisplayName"), "awayShort": side["away"]["team"].get("shortDisplayName")}
                    od = (c.get("odds") or [{}])[0]; ml = od.get("moneyline") or {}
                    h = dec(((ml.get("home") or {}).get("close") or {}).get("odds")); a = dec(((ml.get("away") or {}).get("close") or {}).get("odds"))
                    dr = dec(((ml.get("draw") or {}).get("close") or {}).get("odds")) or dec((od.get("drawOdds") or {}).get("moneyLine"))
                    n += 1
                    if h and a and dr and min(h, a, dr) > 1:
                        row["dk"] = {"h": h, "d": dr, "a": a}; priced += 1
                        tot = od.get("overUnder")
                        if tot == 2.5:
                            ov = dec(((((od.get("total") or {}).get("over") or {}).get("close")) or {}).get("odds"))
                            un = dec(((((od.get("total") or {}).get("under") or {}).get("close")) or {}).get("odds"))
                            if ov and un: row["ou"] = round(100 * (1 / ov) / (1 / ov + 1 / un), 1)
                    out.append(row)
                except Exception as ex: print("skip", code, ex)
        counts[code] = (n, priced)
    # ESPN's team names per league (once a week), so the page's name matching can be checked
    try: teams = json.load(open("data/espn_teams.json"))
    except Exception: teams = {}
    if teams.get("_at", "") < (today - datetime.timedelta(days=7)).isoformat():
        for code, slug in SLUGS.items():
            js = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams")
            try: teams[code] = sorted({(t["team"]["displayName"], t["team"].get("shortDisplayName") or "") for t in js["sports"][0]["leagues"][0]["teams"]})
            except Exception: pass
            time.sleep(0.25)
        teams["_at"] = today.isoformat()
        json.dump(teams, open("data/espn_teams.json", "w"), ensure_ascii=False)
    json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "matches": out}, open("data/live_odds.json", "w"), separators=(",", ":"))
    # log: first price seen and latest price before kick-off, for the fresh-v-stale check
    try: log = json.load(open("data/live_odds_log.json"))
    except Exception: log = {}
    for r in out:
        if "dk" not in r: continue
        x = log.setdefault(r["lg"] + ":" + r["id"], {"lg": r["lg"], "start": r["start"], "home": r["home"], "away": r["away"], "first": r["dk"], "firstAt": now.strftime("%Y-%m-%dT%H:%MZ")})
        x["last"] = r["dk"]; x["lastAt"] = now.strftime("%Y-%m-%dT%H:%MZ"); x["start"] = r["start"]
    cut = (today - datetime.timedelta(days=120)).isoformat()
    log = {k: v for k, v in log.items() if v["start"][:10] >= cut}
    json.dump(log, open("data/live_odds_log.json", "w"), separators=(",", ":"))
    print("matches (upcoming, priced):", {k: v for k, v in counts.items() if v[0]})
    print("leagues with no ESPN games in the next", DAYS, "days:", [k for k, v in counts.items() if not v[0]])

if __name__ == "__main__":
    main()
