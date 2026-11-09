# Daily check that every Pitch Oracle updater is still working. Prints "ALL OK" or one line per problem.
# Uses GitHub's public API for the repo's workflow runs, and the timestamps inside the data files.
import json, sys, datetime, urllib.request
REPO = "markbrown3000/pitch-oracle"
now = datetime.datetime.now(datetime.timezone.utc)
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PitchOracle health check", "Accept": "application/vnd.github+json"}), timeout=30) as r: return json.loads(r.read())
def ts(s): return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
problems = []
# 1. each scheduled workflow: last run recent and successful (hours = longest normal gap plus slack)
WF = {"Update football data": 5, "Update live football odds": 4, "Update darts data": 4, "Update snooker data": 5, "Update US sports data": 4, "Update tennis data": 3}
runs = get(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100").get("workflow_runs", [])
for name, hours in WF.items():
    rs = [r for r in runs if r["name"] == name and r["status"] == "completed"]
    if not rs: problems.append(f"{name}: no recent runs found (GitHub may have paused scheduled runs; press Run workflow on the Actions tab)"); continue
    last = rs[0]; age = (now - ts(last["created_at"])).total_seconds() / 3600
    if last["conclusion"] != "success":
        fails = 0
        for r in rs:
            if r["conclusion"] == "success": break
            fails += 1
        problems.append(f"{name}: last run {last['conclusion']} ({fails} in a row) {age:.0f}h ago")
    elif age > hours: problems.append(f"{name}: hasn't run for {age:.0f} hours")
# 2. data freshness inside the files (they change on every successful run)
def updated(path, field="updated"):
    try: return ts(json.load(open(path))[field])
    except Exception: return None
for path, hours, label in [("data/darts.json", 6, "Darts"), ("data/snooker.json", 8, "Snooker"), ("data/us.json", 6, "US sports"), ("data/live_odds.json", 6, "Live football odds"), ("data/tennis.json", 6, "Tennis"), ("data/fd_rows.json", 8, "Football results file")]:
    t = updated(path, "made" if path.endswith("fd_rows.json") else "updated")
    if t is None: problems.append(f"{label}: {path} missing or unreadable")
    elif (now - t).total_seconds() / 3600 > hours: problems.append(f"{label}: data last refreshed {(now - t).total_seconds() / 3600:.0f} hours ago")
# 3. the site is up
try:
    with urllib.request.urlopen(urllib.request.Request("https://markbrown3000.github.io/pitch-oracle/", headers={"User-Agent": "PitchOracle health check"}), timeout=30) as r:
        if r.status != 200: problems.append(f"Website: answered {r.status}")
except Exception as e: problems.append(f"Website: couldn't be reached ({e})")
print("ALL OK" if not problems else "\n".join(problems))
