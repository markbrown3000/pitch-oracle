// Pitch Oracle tennis model, version 2 (tuned on a replay of 2024-26 ATP and WTA matches).
// node tennis.js <atp.csv> <wta.csv> <feed.json> <kalshi.json> <state.json> <form_atp.json> <form_wta.json> <outdir> [nowISO] [--draws draws.json]
//  atp/wta.csv  Tennis Abstract Elo: line 1 "asof,YYYY-MM-DD", then rank,player,age,elo,hElo,cElo,gElo
//  feed.json    {"games":[...]} from fetch_sports_data tennis scores (singles kept)
//  markets.json {"matches":[{src:"kalshi"|"poly", tour:"atp"|"wta"|"chal"|"w125", tournament, start (UTC ISO), p1, p2, price1, price2, status}]} ({"matches":[]} if none)
//  state.json   current tennis/state ({} first time); form_*.json current tennis/form_atp and tennis/form_wta
// Writes <outdir>/state.json, <outdir>/form_atp.json, <outdir>/form_wta.json.
const fs = require("fs"), path = require("path");
const argv = process.argv.slice(2); let drawsF = null;
{ const di = argv.indexOf("--draws"); if (di >= 0) { drawsF = argv[di + 1]; argv.splice(di, 2); } }
const [atpF, wtaF, feedF, kalF, stateF, fAtpF, fWtaF, outDir, nowArg] = argv;
if (!outDir) { console.error("usage: node tennis.js atp.csv wta.csv feed.json kalshi.json state.json form_atp.json form_wta.json outdir [nowISO]"); process.exit(1); }
const NOW = nowArg ? new Date(nowArg) : new Date();
const readJ = (f, d) => { try { return JSON.parse(fs.readFileSync(f, "utf8") || "null") ?? d; } catch (e) { return d; } };

// ---------- tuned settings (see "replay" notes on the page) ----------
const W = {
  // with a market price:   logit(p) = mkt*logit(market) + elo*logit(elo) + form*matchesLast7Diff + lay*layoffDiff
  market: { atp: { mkt: 0.95, elo: 0.15, form: 0.08, lay: -0.06 }, wta: { mkt: 0.95, elo: 0.15, form: 0.08, lay: 0 } },
  // without one:           logit(p) = elo*logit(elo) + games*logit(games model) + form*... + lay*...
  noMarket: { atp: { elo: 0.85, games: 0.15, form: 0.10, lay: -0.05 }, wta: { elo: 0.9, games: 0, form: 0.13, lay: -0.035 } },
};
const INDOOR = { atp: 0.09, wta: 0.15 }; // share of (indoor-hard minus outdoor-hard) rating gap added on indoor hard courts
const K_NUDGE = 24, KEEP_SCORED_DAYS = 14, VOID_AFTER_DAYS = 3;

// ---------- names ----------
const norm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[-'.’]/g, " ").replace(/[^a-z ]/g, "").replace(/\s+/g, " ").trim();
const keyOf = s => norm(s).split(" ").filter(Boolean).sort().join(" ");
const feedName = n => { const i = String(n).indexOf(","); return i < 0 ? String(n).trim() : (n.slice(i + 1).trim() + " " + n.slice(0, i).trim()); };
// form key = surname squashed + first initial, built from "Last, First" (feed) or a full name with a known surname
const formKeyLF = (last, first) => norm(last).replace(/ /g, "") + " " + (norm(first)[0] || "");
const formKeyFeed = n => { const i = String(n).indexOf(","); return i < 0 ? null : formKeyLF(n.slice(0, i), n.slice(i + 1)); };

// ---------- ratings ----------
function loadElo(file) {
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/).filter(l => l.trim());
  let asof = null, i = 0;
  if (/^asof/i.test(lines[0])) { asof = lines[0].split(",")[1].trim(); i = 1; }
  const head = lines[i].split(",").map(h => h.trim().toLowerCase()); i++;
  const col = n => head.indexOf(n);
  const P = {}, alt = {};
  for (; i < lines.length; i++) {
    const c = lines[i].split(",");
    const r = { name: c[col("player")].trim(), rank: +c[col("rank")], elo: +c[col("elo")], hard: +c[col("helo")], clay: +c[col("celo")], grass: +c[col("gelo")] };
    if (!r.name || !isFinite(r.elo)) continue;
    const k = keyOf(r.name); P[k] = r;
    const t = norm(r.name).split(" "); const ak = t[t.length - 1] + "|" + t[0][0];
    alt[ak] = alt[ak] ? "dup" : k;
  }
  return { asof, P, alt, n: Object.keys(P).length };
}
const ELO = { atp: loadElo(atpF), wta: loadElo(wtaF) };
const eloAsof = [ELO.atp.asof, ELO.wta.asof].filter(Boolean).sort()[0] || null;
function findElo(list, name) {
  const E = ELO[list]; const k = keyOf(name);
  if (E.P[k]) return E.P[k];
  const t = norm(name).split(" "); const a = E.alt[t[t.length - 1] + "|" + (t[0] || " ")[0]];
  return a && a !== "dup" ? E.P[a] : null;
}

const games = readJ(feedF, {}); const feed = Array.isArray(games) ? games : (games.games || []);
const kal = readJ(kalF, {}); const kalshi = Array.isArray(kal) ? kal : (kal.matches || []);
const S = readJ(stateF, {}) || {};
const FORM = { atp: readJ(fAtpF, null) || { tour: "atp", p: {} }, wta: readJ(fWtaF, null) || { tour: "wta", p: {} } };
const state = {
  picks: S.picks || {}, record: S.record || {}, surfaces: S.surfaces || {},
  adj: S.adj && S.adj.eloAsof === eloAsof ? S.adj : { eloAsof, d: {}, seen: [] },
  formSeen: S.formSeen || [], train: S.train || [], tuning: S.tuning || {},
};

// ---------- classification ----------
const SLAM = /(australian open|roland garros|french open|wimbledon|us open)/i;
const CLAY = /(roland garros|french open|monte carlo|madrid|rome|internazionali|barcelona|hamburg|buenos aires|rio de janeiro|santiago|estoril|munich|geneva|lyon|bastad|gstaad|kitzbuhel|umag|bucharest|marrakech|houston|charleston|bogota|rabat|palermo|strasbourg|parma|iasi|prague|portoroz|warsaw|lausanne|budapest|bad gastein|grado|salzburg|braunschweig|heilbronn|perugia|sassuolo|trieste|todi|genova|san marino|biella|cordenons)/i;
const CLAY_COUNTRY = /(argentina|brazil|chile|peru|colombia|uruguay|paraguay|bolivia|ecuador)/i;
const GRASS = /(wimbledon|queen|london|halle|hertogenbosch|eastbourne|mallorca|newport|berlin|bad homburg|birmingham|nottingham|ilkley|surbiton|libema)/i;
// indoor hard events (by name and month)
const INDOOR_EV = [[/paris/i, [10, 11]], [/turin|atp finals|nitto/i, [11]], [/basel/i, [10]], [/vienna/i, [10]], [/stockholm/i, [10]], [/metz|moselle/i, [11]],
  [/antwerp|brussels/i, [10]], [/rotterdam/i, [2]], [/marseille/i, [2]], [/montpellier/i, [1, 2]], [/dallas/i, [2]], [/sofia/i, [11]], [/astana/i, [10]],
  [/linz/i, [1, 2, 10]], [/ostrava/i, [10]], [/cluj/i, [2]], [/st\.? petersburg/i, [2, 10]], [/davis cup|billie jean/i, [9, 11]], [/riyadh|wta finals/i, [11]],
  [/tokyo/i, [10]], [/jiujiang/i, []], [/athens/i, [11]], [/belgrade/i, [11]]];
function tourOf(t) {
  if (!/singles/i.test(t) || /doubles|utr|itf|junior|wheelchair|exhibition|boys|girls/i.test(t)) return null;
  if (/atp challenger/i.test(t)) return "chal";
  if (/wta 125/i.test(t)) return "w125";
  if (/\bwta\b|women|ladies/i.test(t)) return "wta";
  return "atp";
}
const cleanName = t => String(t).replace(/,?\s*(men|women)'?s?\s*singles.*$/i, "").replace(/,?\s*singles.*$/i, "").replace(/\s+,/g, ",").trim();
const tKey = t => norm(cleanName(t));
function surfaceOf(t, start) {
  const k = tKey(t);
  if (state.surfaces[k]) return state.surfaces[k];
  const m = new Date(start).getUTCMonth() + 1;
  if (/stuttgart/i.test(t)) return m <= 5 ? "clay" : "grass";
  if (GRASS.test(t) && m >= 6 && m <= 7) return "grass";
  if (CLAY.test(t)) return "clay";
  if (CLAY_COUNTRY.test(t) && !/davis|billie|united cup/i.test(t)) return "clay";
  if (INDOOR_EV.some(([re, ms]) => re.test(t) && ms.includes(m))) return "hardin";
  return "hard";
}
const bestOf = (t, tour) => tour === "atp" && SLAM.test(t) && !/qualif/i.test(t) ? 5 : 3;

// ---------- maths ----------
const logit = p => { p = Math.min(Math.max(p, 1e-4), 1 - 1e-4); return Math.log(p / (1 - p)); };
const inv = z => 1 / (1 + Math.exp(-z));
const pElo = (ra, rb) => 1 / (1 + Math.pow(10, (rb - ra) / 400));
const p3 = q => q * q * (3 - 2 * q), p5 = q => q * q * q * (10 - 15 * q + 6 * q * q);
function bo5(p) { let lo = 0, hi = 1; for (let i = 0; i < 50; i++) { const m = (lo + hi) / 2; if (p3(m) < p) lo = m; else hi = m; } return p5((lo + hi) / 2); }
function setFromGame(g) { const memo = {}; const f = (a, b) => { const k = a * 16 + b; if (k in memo) return memo[k];
  let v; if (a >= 6 && a - b >= 2) v = 1; else if (b >= 6 && b - a >= 2) v = 0; else if (a === 6 && b === 6) v = g; else if (a === 7 || b === 7) v = a > b ? 1 : 0;
  else v = g * f(a + 1, b) + (1 - g) * f(a, b + 1); return memo[k] = v; }; return f(0, 0); }
const listOf = tour => tour === "wta" || tour === "w125" ? "wta" : "atp";

// ---------- form (last matches, games rating, indoor rating) ----------
const day = d => new Date(d).toISOString().slice(0, 10);
const daysBetween = (a, b) => (new Date(b) - new Date(a)) / 864e5;
function formOf(list, fk) { return fk ? FORM[list].p[fk] : null; }
function formFeatures(list, fa, fb, start) {
  const last7 = f => f ? f.d.filter(x => daysBetween(x, start) >= 0 && daysBetween(x, start) <= 7).length : 0;
  const lay = f => { if (!f || !f.d.length || f.d.length < 5) return 0; const dd = daysBetween(f.d[f.d.length - 1], start); return Math.max(0, Math.min(365, dd) - 45) / 100; };
  return { form: last7(fa) - last7(fb), lay: lay(fa) - lay(fb) };
}
function recordForm(list, fk, date, gw, gl, oppFk, surf, won) {
  if (!fk) return;
  const P = FORM[list].p, prm = FORM[list].params || { g_scale: 2400, g_k: 30 };
  const f = P[fk] || (P[fk] = { d: [], g: null, hi: null, ho: null, nh: 0 });
  f.d.push(date); f.d = [...new Set(f.d)].sort().slice(-8);
  return f;
}
function updateGames(list, fw, fl, gw, gl) {
  const prm = FORM[list].params || { g_scale: 2400, g_k: 30 };
  if (!fw || !fl || fw.g == null || fl.g == null || gw + gl === 0) return;
  const e = 1 / (1 + Math.pow(10, (fl.g - fw.g) / prm.g_scale)), k = prm.g_k * (gw + gl) / 20, s = gw / (gw + gl);
  fw.g = Math.round((fw.g + k * (s - e)) * 10) / 10; fl.g = Math.round((fl.g - k * (s - e)) * 10) / 10;
}
function updateIndoor(fw, fl, surf) {
  if (!fw || !fl) return; const key = surf === "hardin" ? "hi" : surf === "hard" ? "ho" : null; if (!key || fw[key] == null || fl[key] == null) return;
  const e = pElo(fw[key], fl[key]), kw = 200 / Math.pow((surf === "hardin" ? fw.nh : 30) + 5, 0.5), kl = 200 / Math.pow((surf === "hardin" ? fl.nh : 30) + 5, 0.5);
  fw[key] = Math.round((fw[key] + kw * (1 - e)) * 10) / 10; fl[key] = Math.round((fl[key] - kl * (1 - e)) * 10) / 10;
  if (surf === "hardin") { fw.nh++; fl.nh++; }
}

// ---------- the prediction ----------
const nudge = (list, r) => (state.adj.d[list + ":" + keyOf(r.name)] || 0);
function predict(P, list, ra, rb, fa, fb, mkt) {
  const surf = P.s, tour = P.t, base = surf === "hardin" ? "hard" : surf;
  let xa = ra[base] + nudge(list, ra), xb = rb[base] + nudge(list, rb);
  if (surf === "hardin" && fa && fb && fa.hi != null && fb.hi != null && fa.ho != null && fb.ho != null)
    { xa += INDOOR[list] * (fa.hi - fa.ho); xb += INDOOR[list] * (fb.hi - fb.ho); }
  let pe = pElo(xa, xb); if (P.bo === 5) pe = bo5(pe);
  let pg = null;
  if (fa && fb && fa.g != null && fb.g != null) {
    const q = 1 / (1 + Math.pow(10, (fb.g - fa.g) / ((FORM[list].params || {}).g_scale || 2400)));
    const ps = setFromGame(Math.round(q * 1000) / 1000); pg = P.bo === 5 ? p5(ps) : p3(ps);
  }
  const ff = formFeatures(list, fa, fb, P.start);
  let z, src;
  if (mkt != null) { const w = (state.tuning[list] && state.tuning[list].market) || W.market[list]; z = w.mkt * logit(mkt) + w.elo * logit(pe) + w.form * ff.form + w.lay * ff.lay; src = "market"; }
  else { const w = (state.tuning[list] && state.tuning[list].noMarket) || W.noMarket[list]; const gw = pg != null ? w.games : 0; z = (w.elo + (w.games - gw)) * logit(pe) + (pg != null ? gw * logit(pg) : 0) + w.form * ff.form + w.lay * ff.lay; src = "ratings"; }
  return { pa: Math.round(inv(z) * 1000) / 10, pe: Math.round(pe * 1000) / 10, pg: pg == null ? null : Math.round(pg * 1000) / 10, pm: mkt == null ? null : Math.round(mkt * 1000) / 10,
    ra: Math.round(xa), rb: Math.round(xb), form: ff.form, lay: Math.round(ff.lay * 100), src };
}

// ---------- market lookup (Kalshi) ----------
const pairKey = (a, b) => [keyOf(a), keyOf(b)].sort().join(" | ");
const lastName = s => { const t = norm(s).split(" "); return t[t.length - 1]; };
const KAL = kalshi.filter(k => k.p1 && k.p2 && k.price1 > 0 && k.price2 > 0).map(k => ({ ...k, pk: pairKey(k.p1, k.p2), ln: [lastName(k.p1), lastName(k.p2)].sort().join("|") }));
// every market that lists the match (at most one price per source), averaged
function marketsFor(aName, bName) {
  const pk = pairKey(aName, bName), ln = [lastName(aName), lastName(bName)].sort().join("|");
  const bySrc = {};
  for (const k of KAL) {
    if (k.pk !== pk && k.ln !== ln) continue;
    const src = k.src || "kalshi"; if (bySrc[src] && bySrc[src].pk === pk) continue;
    if (bySrc[src] && k.pk !== pk) continue;
    bySrc[src] = k;
  }
  const out = Object.entries(bySrc).map(([src, k]) => {
    const aIs1 = keyOf(k.p1) === keyOf(aName) || lastName(k.p1) === lastName(aName);
    const pa = aIs1 ? k.price1 : k.price2, pb = aIs1 ? k.price2 : k.price1;
    return { src, p: pa / (pa + pb) };
  });
  return out;
}
function marketFor(aName, bName) { const m = marketsFor(aName, bName); return m.length ? m.reduce((a, x) => a + x.p, 0) / m.length : null; }

// ---------- flip a pick's orientation (when the feed lists the players the other way round) ----------
function flip(P) {
  [P.a, P.b] = [P.b, P.a]; [P.ra, P.rb] = [P.rb, P.ra]; [P.ka, P.kb] = [P.kb, P.ka]; [P.fa, P.fb] = [P.fb, P.fa];
  for (const k of ["pa", "pe", "pg", "pm", "m_kalshi", "m_poly"]) if (P[k] != null) P[k] = Math.round((100 - P[k]) * 10) / 10;
  if (P.form != null) P.form = -P.form; if (P.lay != null) P.lay = -P.lay;
}

let added = 0, updated = 0, scored = 0, skipped = 0, nudged = 0, live = 0, withMkt = 0, formUpd = 0;
const unrated = new Set(), seenT = {};
function price(P, list, ra, rb) {
  const fa = formOf(list, P.fa), fb = formOf(list, P.fb);
  const ms = marketsFor(P.a, P.b), mkt = ms.length ? ms.reduce((a, x) => a + x.p, 0) / ms.length : null;
  const r = predict(P, list, ra, rb, fa, fb, mkt);
  const before = P.pa; Object.assign(P, r); P.msrc = ms.map(x => x.src); if (r.pm != null) withMkt++;
  for (const x of ms) P["m_" + x.src] = Math.round(x.p * 1000) / 10;
  if (before != null && before !== P.pa) updated++;
}
const notStarted = (status, start) => status === "scheduled" && new Date(start) > NOW;

// 1) the results feed
for (const g of feed) {
  const t = g.tournament || ""; const tour = tourOf(t); if (!tour) continue;
  const list = listOf(tour);
  const A = g.teams?.[g.home]?.name ?? g.p1, B = g.teams?.[g.away]?.name ?? g.p2;
  if (!A || !B || String(A).includes("/") || String(B).includes("/")) continue;
  const an = feedName(A), bn = feedName(B), fka = formKeyFeed(A), fkb = formKeyFeed(B);
  const start = g.start_time ? new Date(g.start_time).toISOString().replace(".000", "") : g.start;
  if (start && !seenT[tKey(t)]) seenT[tKey(t)] = surfaceOf(t, start);
  const ra = findElo(list, an), rb = findElo(list, bn);
  const status = g.status || "scheduled", id = String(g.id);
  const sa = g.score?.[g.home], sb = g.score?.[g.away];
  const sets = (g.sets || []).filter(s => s.p1 || s.p2);
  const setsTxt = sets.map(s => `${s.p1}-${s.p2}`).join(" ");
  const surf = surfaceOf(t, start);

  // finished match: form (dates, games rating, indoor rating) and Elo nudges, counted once
  if (status === "final" && typeof sa === "number" && sa !== sb && !state.formSeen.includes(id)) {
    const ga = sets.reduce((x, s) => x + (+s.p1 || 0), 0), gb = sets.reduce((x, s) => x + (+s.p2 || 0), 0);
    const fa = recordForm(list, fka, day(start)), fb = recordForm(list, fkb, day(start));
    if (sa > sb) { updateGames(list, fa, fb, ga, gb); updateIndoor(fa, fb, surf); } else { updateGames(list, fb, fa, gb, ga); updateIndoor(fb, fa, surf); }
    state.formSeen.push(id); formUpd++;
    if (ra && rb && eloAsof && day(start) > eloAsof) {
      const base = surf === "hardin" ? "hard" : surf;
      const e = pElo(ra[base] + nudge(list, ra), rb[base] + nudge(list, rb)), w = sa > sb ? 1 : 0;
      const ka = list + ":" + keyOf(ra.name), kb = list + ":" + keyOf(rb.name);
      state.adj.d[ka] = Math.round(((state.adj.d[ka] || 0) + K_NUDGE * (w - e)) * 10) / 10;
      state.adj.d[kb] = Math.round(((state.adj.d[kb] || 0) - K_NUDGE * (w - e)) * 10) / 10; nudged++;
    }
  }

  let P = state.picks[id];
  if (!P) { // a pick made earlier from the market list for the same two players?
    const pk = pairKey(ra ? ra.name : an, rb ? rb.name : bn);
    const kid = Object.keys(state.picks).find(k => k.startsWith("k:") && state.picks[k].pk === pk && Math.abs(daysBetween(state.picks[k].start, start)) <= 1.5);
    if (kid) { P = state.picks[id] = state.picks[kid]; delete state.picks[kid]; if (keyOf(P.a) !== keyOf(ra ? ra.name : an)) flip(P); P.fa = fka; P.fb = fkb; P.t = tour; P.n = cleanName(t); }
  }
  if (!P) {
    if (!ra || !rb) { skipped++; if (!ra) unrated.add(an); if (!rb) unrated.add(bn); continue; }
    if (!notStarted(status, start)) continue;
    P = state.picks[id] = { t: tour, n: cleanName(t), a: ra.name, b: rb.name, start, fa: fka, fb: fkb, pk: pairKey(ra.name, rb.name) }; added++;
  }
  P.st = status; if (setsTxt) P.sc = setsTxt;
  if (status === "in_progress") live++;
  if (notStarted(status, start) && P.res == null && ra && rb) {
    Object.assign(P, { start, s: surf, bo: bestOf(t, tour), ka: ra.rank, kb: rb.rank }); price(P, list, ra, rb);
  }
  if (status === "final" && P.res == null && P.pa != null) {
    if (typeof sa === "number" && typeof sb === "number" && sa !== sb) {
      P.res = sa > sb ? "a" : "b"; P.ok = (P.pa >= 50) === (P.res === "a"); P.done = day(NOW);
      const conf = Math.max(P.pa, 100 - P.pa), band = conf >= 80 ? "80" : conf >= 70 ? "70" : conf >= 60 ? "60" : "50";
      const R = state.record; const add = k => { R[k] = R[k] || { n: 0, ok: 0, br: 0 }; R[k].n++; if (P.ok) R[k].ok++; R[k].br = Math.round((R[k].br + Math.pow((P.res === "a" ? 1 : 0) - P.pa / 100, 2)) * 1e4) / 1e4; };
      add("all"); add(P.t); add("band" + band); if (P.src) add("src_" + P.src);
      state.train.push([list === "wta" ? 1 : 0, P.pm, P.pe, P.pg, P.form || 0, P.lay || 0, P.res === "a" ? 1 : 0]);
      // how the market alone and the ratings alone would have done on the same picks
      if (P.pm != null) add2("mkt", P.pm, P.res); if (P.pe != null) add2("elo", P.pe, P.res);
      scored++;
    } else P.void = true;
  }
}
function add2(k, p, res) { const R = state.record; const key = "only_" + k; R[key] = R[key] || { n: 0, ok: 0 }; R[key].n++; if ((p >= 50) === (res === "a")) R[key].ok++; }

// 2) matches only on the market list so far (often tomorrow's, or early starts in Asia and Australia)
for (const k of kalshi) {
  if (!k.p1 || !k.p2 || !k.start || !notStarted(k.status === "upcoming" || !k.status ? "scheduled" : "x", k.start)) continue;
  const tour = ["atp", "wta", "chal", "w125"].includes(k.tour) ? k.tour : "atp", list = listOf(tour);
  const ra = findElo(list, k.p1), rb = findElo(list, k.p2);
  if (!ra || !rb) continue;
  const pk = pairKey(ra.name, rb.name);
  if (Object.values(state.picks).some(p => p.pk === pk && Math.abs(daysBetween(p.start, k.start)) <= 1.5)) {
    const id = Object.keys(state.picks).find(i => state.picks[i].pk === pk && Math.abs(daysBetween(state.picks[i].start, k.start)) <= 1.5);
    const P = state.picks[id];
    if (id.startsWith("k:") && P.res == null && notStarted("scheduled", P.start)) { P.start = k.start; price(P, list, ra, rb); }
    continue;
  }
  const t = String(k.tournament || "");
  const P = { t: tour, n: t, a: ra.name, b: rb.name, start: k.start, st: "scheduled", s: surfaceOf(t, k.start), bo: tour === "atp" && SLAM.test(t) ? 5 : 3,
    ka: ra.rank, kb: rb.rank, pk, fa: guessFk(list, ra.name), fb: guessFk(list, rb.name) };
  if (!seenT[tKey(t)]) seenT[tKey(t)] = P.s;
  const id = "k:" + day(k.start) + ":" + pk.replace(/[^a-z|]/g, "").slice(0, 60);
  state.picks[id] = P; price(P, list, ra, rb); added++;
}

function guessFk(list, full) { // "Jan Lennard Struff" -> try "struff j", then longer surnames
  const t = norm(full).split(" "); if (t.length < 2) return null;
  for (let i = t.length - 1; i >= 1; i--) { const k = t.slice(i).join("") + " " + t[0][0]; if (FORM[list].p[k]) return k; }
  return null;
}
// ---------- self-tuning from scored picks ----------
// Once enough picks are scored, refit the blend on them, pulled towards the replay's weights so it moves gently.
const TUNE_MIN = { market: 500, noMarket: 300 }, TUNE_PULL = 150;
function fitPulled(X, y, w0, lam) {
  let w = w0.slice();
  for (let it = 0; it < 30; it++) {
    const k = w.length, g = new Array(k).fill(0), H = Array.from({ length: k }, () => new Array(k).fill(0));
    for (let i = 0; i < X.length; i++) { const z = X[i].reduce((a, x, j) => a + x * w[j], 0), p = inv(z), r = p - y[i], v = p * (1 - p);
      for (let a = 0; a < k; a++) { g[a] += X[i][a] * r; for (let b = 0; b < k; b++) H[a][b] += X[i][a] * X[i][b] * v; } }
    for (let a = 0; a < k; a++) { g[a] += lam * (w[a] - w0[a]); H[a][a] += lam; }
    // solve H d = g (Gaussian elimination)
    const M = H.map((row, i) => [...row, g[i]]);
    for (let c = 0; c < k; c++) { let piv = c; for (let r = c + 1; r < k; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r; [M[c], M[piv]] = [M[piv], M[c]];
      for (let r = 0; r < k; r++) if (r !== c) { const f = M[r][c] / M[c][c]; for (let j = c; j <= k; j++) M[r][j] -= f * M[c][j]; } }
    const d = M.map((row, i) => row[k] / row[i]); w = w.map((x, i) => x - d[i]);
    if (Math.max(...d.map(Math.abs)) < 1e-6) break;
  }
  return w.map(x => Math.round(x * 1000) / 1000);
}
const tuneNotes = [];
state.train = state.train.slice(-2000);
const rowsOf = list => state.train.map(r => ({ l: r[0] ? "wta" : "atp", m: r[1], e: r[2], g: r[3], f: r[4], y: r[5], w: r[6] }));
for (const list of ["atp", "wta"]) {
  const rows = rowsOf(list).filter(r => r.l === list);
  const mk = rows.filter(r => r.m != null), nm = rows.filter(r => r.m == null);
  const T = state.tuning[list] = state.tuning[list] || {};
  if (mk.length >= TUNE_MIN.market) {
    const w0 = W.market[list], X = mk.map(r => [logit(r.m / 100), logit(r.e / 100), r.f, r.y / 100]);
    const w = fitPulled(X, mk.map(r => r.w), [w0.mkt, w0.elo, w0.form, w0.lay], TUNE_PULL);
    T.market = { mkt: w[0], elo: w[1], form: w[2], lay: w[3] }; T.marketN = mk.length; tuneNotes.push(`${list} market blend tuned on ${mk.length} picks`);
  }
  if (nm.length >= TUNE_MIN.noMarket) {
    const w0 = W.noMarket[list], X = nm.map(r => [logit(r.e / 100), r.g != null ? logit(r.g / 100) : 0, r.f, r.y / 100]);
    const w = fitPulled(X, nm.map(r => r.w), [w0.elo, w0.games, w0.form, w0.lay], TUNE_PULL);
    T.noMarket = { elo: w[0], games: w[1], form: w[2], lay: w[3] }; T.noMarketN = nm.length; tuneNotes.push(`${list} ratings-only blend tuned on ${nm.length} picks`);
  }
  if (!tuneNotes.some(n => n.startsWith(list))) tuneNotes.push(`${list}: ${mk.length}/${TUNE_MIN.market} market and ${nm.length}/${TUNE_MIN.noMarket} ratings-only picks scored before tuning starts`);
  if (!T.market && !T.noMarket) delete state.tuning[list];
}

// ---------- tournament winner chances ----------
// draws.json: [{tournament, tour:"atp"|"wta", surface:"hard"|"hardin"|"clay"|"grass", bestOf, format:"knockout", round, matches:[[p1,p2],...] in draw order}
//              or {..., format:"roundrobin", groups:[{name, players:[4 names], results:[[winner, loser],...]}]}  (top two per group to semi-finals: A1 v B2, B1 v A2)
const outrights = [];
function simPair(list, surf, bo, tour, cache) {
  return (a, b) => {
    const k = a + "|" + b; if (k in cache) return cache[k];
    const ra = findElo(list, a) || { name: a, rank: null, elo: 1500, hard: 1500, clay: 1500, grass: 1500 }, rb = findElo(list, b) || { name: b, rank: null, elo: 1500, hard: 1500, clay: 1500, grass: 1500 };
    const P = { s: surf, bo, t: tour, start: NOW.toISOString() };
    const r = predict(P, list, ra, rb, formOf(list, guessFk(list, ra.name)), formOf(list, guessFk(list, rb.name)), null);
    return cache[k] = r.pa / 100;
  };
}
let rngState = 12345; const rnd = () => (rngState = (rngState * 1103515245 + 12345) % 2147483648) / 2147483648;
for (const D of (drawsF ? (readJ(drawsF, []) || []) : [])) {
  try {
    const tour = D.tour === "wta" ? "wta" : "atp", list = listOf(tour), surf = D.surface || "hard", bo = D.bestOf || 3;
    const pw = simPair(list, surf, bo, tour, {}), N = 20000, cnt = {}, fin = {}, sf = {};
    const nameOf = x => { const r = findElo(list, x); return r ? r.name : x; };
    const bump = (o, n) => o[n] = (o[n] || 0) + 1;
    const play = (a, b) => (a === "BYE" ? b : b === "BYE" ? a : (rnd() < pw(a, b) ? a : b));
    if (D.format === "roundrobin") {
      const G = (D.groups || []).map(g => ({ ...g, players: g.players.map(nameOf), results: (g.results || []).map(r => r.map(nameOf)) }));
      for (let s = 0; s < N; s++) {
        const tops = G.map(g => {
          const wins = Object.fromEntries(g.players.map(p => [p, 0]));
          const done = new Set(g.results.map(([w, l]) => [w, l].sort().join("|")));
          g.results.forEach(([w]) => wins[w] = (wins[w] || 0) + 1);
          for (let i = 0; i < g.players.length; i++) for (let j = i + 1; j < g.players.length; j++) {
            const a = g.players[i], b = g.players[j]; if (done.has([a, b].sort().join("|"))) continue; wins[play(a, b)]++; }
          return [...g.players].sort((x, y) => wins[y] - wins[x] || rnd() - 0.5).slice(0, 2);
        });
        if (tops.length !== 2) break;
        const s1 = play(tops[0][0], tops[1][1]), s2 = play(tops[1][0], tops[0][1]);
        [tops[0][0], tops[1][1], tops[1][0], tops[0][1]].forEach(p => bump(sf, p)); bump(fin, s1); bump(fin, s2); bump(cnt, play(s1, s2));
      }
    } else {
      const first = (D.matches || []).flatMap(m => m.map(x => x === "BYE" ? "BYE" : nameOf(x)));
      for (let s = 0; s < N; s++) {
        let cur = first.slice();
        while (cur.length > 1) {
          if (cur.length === 4) cur.forEach(p => bump(sf, p)); if (cur.length === 2) cur.forEach(p => bump(fin, p));
          const nx = []; for (let i = 0; i < cur.length; i += 2) nx.push(cur[i + 1] == null ? cur[i] : play(cur[i], cur[i + 1])); cur = nx;
        }
        bump(cnt, cur[0]);
      }
    }
    const players = Object.keys({ ...cnt, ...fin, ...sf }).filter(p => p !== "BYE").map(p => ({ name: p, win: Math.round(1000 * (cnt[p] || 0) / N) / 10, final: Math.round(1000 * (fin[p] || 0) / N) / 10, sf: Math.round(1000 * (sf[p] || 0) / N) / 10 }))
      .sort((a, b) => b.win - a.win || b.final - a.final).slice(0, 16);
    outrights.push({ tournament: D.tournament, tour, surface: surf, round: D.round || (D.format === "roundrobin" ? "Round robin" : ""), format: D.format || "knockout", players, asof: NOW.toISOString() });
  } catch (e) { console.error("draw skipped (" + (D && D.tournament) + "): " + e.message); }
}

// ---------- tidy ----------
for (const [id, P] of Object.entries(state.picks)) {
  const age = daysBetween(P.start, NOW);
  if (P.void || (P.res == null && age > VOID_AFTER_DAYS) || (P.res != null && age > KEEP_SCORED_DAYS)) delete state.picks[id];
}
state.adj.seen = []; state.formSeen = state.formSeen.slice(-2500);
const out = {
  updated: NOW.toISOString(), eloAsof, model: "tennis-2", formAsof: { atp: FORM.atp.asof, wta: FORM.wta.asof },
  players: { atp: ELO.atp.n, wta: ELO.wta.n },
  picks: state.picks, record: state.record, surfaces: state.surfaces, adj: state.adj, formSeen: state.formSeen,
  train: state.train, tuning: state.tuning, outrights: drawsF ? outrights : (S.outrights || []), weights: W,
  lastRun: { added, updated, scored, live, skipped, nudged, withMarket: withMkt, formUpdates: formUpd, marketPrices: KAL.length, marketBySource: KAL.reduce((o, k) => (o[k.src || "kalshi"] = (o[k.src || "kalshi"] || 0) + 1, o), {}), unrated: [...unrated].slice(0, 30) },
};
fs.mkdirSync(outDir, { recursive: true });
const txt = JSON.stringify(out); fs.writeFileSync(path.join(outDir, "state.json"), txt);
for (const l of ["atp", "wta"]) fs.writeFileSync(path.join(outDir, `form_${l}.json`), JSON.stringify(FORM[l]));
const open = Object.values(state.picks).filter(p => p.res == null).length;
console.log(`tennis: ${added} new picks, ${updated} re-priced, ${scored} scored, ${open} open (${withMkt} priced with a market), ${live} live, ${skipped} skipped (unrated), ${formUpd} results logged · record ${state.record.all ? state.record.all.ok + "/" + state.record.all.n : "0/0"} · ${Math.round(txt.length / 1024)} KB`);
console.log("tuning: " + tuneNotes.join("; ") + (outrights.length ? " · winner chances for " + outrights.map(o => o.tournament).join(", ") : " · no draws given"));
console.log("surfaces used (key = surface; fix wrong ones via the surfaces map; hardin = indoor hard):\n" + Object.entries(seenT).map(([k, s]) => `  ${k} = ${s}`).join("\n"));
for (const [f, lim] of [[txt, 250000], [JSON.stringify(FORM.atp), 250000], [JSON.stringify(FORM.wta), 250000]]) if (f.length > lim) { console.error("ERROR: a document is over 250 KB"); process.exit(2); }
