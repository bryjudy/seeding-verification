"""Multi-season rerun of the storm-level evaluation (v2 event construction + v2.3 per-generator plume design), pooled
across all seasons in data/seeded-storms-multi.csv. Reuses: run_storm_analysis_local.pull_state (SNOTEL via AWDB, now per
season window), fetch_storm_winds.fetch_uv (HRRR 700 mb, byte-range), storm_core.analyze_storms (per-season event windows),
and the v2.3 fixed-effects fit. Designed to run on a cloud VM (winds ≈ GBs).  Usage: python multi_season.py [--skip-winds]"""
import json, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np, pandas as pd, requests
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE))
import run_storm_analysis_local as rl, fetch_storm_winds as fw
from storm_core import analyze_storms
SEASON_WINDOW = lambda s: (f"{s[:4]}-10-15", f"20{s[-2:]}-05-05")
storms_all = pd.read_csv(HERE / "data" / "seeded-storms-multi.csv"); gens = pd.read_csv(HERE / "data" / "generators-2024-25.csv")
seasons = sorted(storms_all.season.unique()); print("seasons", seasons, flush=True)

# ---- 1. SNOTEL daily PREC for each season window (AWDB, cached per season) ----
def pull_state_window(state, d0, d1, tag):
    mfile = rl.CACHE / f"stations_{state}.parquet"; dfile = rl.CACHE / f"daily_{state}_{tag}.parquet"
    if dfile.exists() and mfile.exists(): return pd.read_parquet(mfile), pd.read_parquet(dfile)
    meta, _ = rl.pull_state(state) if not mfile.exists() else (pd.read_parquet(mfile), None)
    rows = []; trips = list(meta["triplet"])
    for b in range(0, len(trips), 15):
        batch = trips[b:b + 15]
        for attempt in range(4):
            try:
                r = requests.get(f"{rl.API}/data", params={"stationTriplets": ",".join(batch), "elements": "PREC", "duration": "DAILY", "beginDate": d0, "endDate": d1}, timeout=180); r.raise_for_status(); break
            except Exception:
                if attempt == 3: raise
                time.sleep(4 * (attempt + 1))
        for st in r.json():
            for el in st.get("data", []):
                for v in el.get("values", []):
                    if v.get("value") is not None: rows.append((st["stationTriplet"], "PREC", v["date"], v["value"]))
        time.sleep(0.3)
    daily = pd.DataFrame(rows, columns=["triplet", "element", "date", "value"]); daily.to_parquet(dfile); return meta, daily

# ---- 2. HRRR winds for every program-storm window in every season (cache shared) ----
def winds_for(storms):
    cents = fw.centroids(); progs = sorted(cents); pts = [cents[p] for p in progs]
    cache = json.loads(fw.CACHE.read_text()) if fw.CACHE.exists() else {}
    hours = set()
    for _, w in storms.iterrows():
        t = datetime.fromisoformat(str(w.date_start)); d1 = datetime.fromisoformat(str(w.date_end)) + timedelta(days=1)
        while t < d1: hours.add((t.strftime("%Y%m%d"), t.hour)); t += timedelta(hours=6)
    todo = [h for h in sorted(hours) if f"{h[0]}T{h[1]:02d}" not in cache]; print(f"HRRR hours needed {len(hours)}, to fetch {len(todo)}", flush=True)
    for n, (date, hour) in enumerate(todo):
        try: uv = fw.fetch_uv(date, hour, pts)
        except Exception as e: uv = None
        cache[f"{date}T{hour:02d}"] = uv
        if n % 25 == 0: fw.CACHE.write_text(json.dumps(cache)); print(f"  {n}/{len(todo)}", flush=True)
    fw.CACHE.write_text(json.dumps(cache))
    rows = []
    for _, w in storms.iterrows():
        if w.program not in progs: continue
        pi = progs.index(w.program); t = datetime.fromisoformat(str(w.date_start)); d1 = datetime.fromisoformat(str(w.date_end)) + timedelta(days=1); us, vs = [], []
        while t < d1:
            uv = cache.get(f"{t.strftime('%Y%m%d')}T{t.hour:02d}")
            if uv and uv[pi]: us.append(uv[pi][0]); vs.append(uv[pi][1])
            t += timedelta(hours=6)
        if us:
            u, v = np.mean(us), np.mean(vs); rows.append(dict(program=w.program, date_start=str(w.date_start), date_end=str(w.date_end), wind_dir_from_deg=round((np.degrees(np.arctan2(-u, -v))) % 360, 1), wind_speed_ms=round(float(np.hypot(u, v)), 1), n_hours=len(us)))
    return pd.DataFrame(rows)

# ---- 3. per season: event construction (storm_core) -> event winds + per-event seeded flags ----
skip_w = "--skip-winds" in sys.argv
panel_inputs = []
for s in seasons:
    d0, d1 = SEASON_WINDOW(s); st = storms_all[storms_all.season == s].copy(); st = st[st.program.isin(gens.program.unique())]
    if st.empty: continue
    metas, dailies = zip(*[pull_state_window(x, d0, d1, s) for x in rl.STATES]); meta = pd.concat(metas, ignore_index=True).dropna(subset=["lat", "lon"]); daily = pd.concat(dailies, ignore_index=True)
    winds = None if skip_w else winds_for(st)
    res = analyze_storms(meta, daily, gens, st, winds, d0=d0, d1=d1)
    per_event = pd.DataFrame(res.pop("per_storm"), columns=["program", "e0", "e1", "seeded", "exp_mean_in", "ctl_mean_in"])
    # event winds: reuse storm winds for seeded events; unseeded events need their own -> fetch by window
    ev = per_event[["program", "e0", "e1"]].rename(columns={"e0": "date_start", "e1": "date_end"})
    evw = None if skip_w else winds_for(ev).rename(columns={"date_start": "e0", "date_end": "e1"})
    (HERE / "data" / f"storm-results-{s}.json").write_text(json.dumps(res, indent=1)); per_event.to_csv(HERE / "data" / f"storm-per-event-{s}.csv", index=False)
    if evw is not None: evw.to_csv(HERE / "data" / f"event-winds-{s}.csv", index=False)
    print(s, "events", len(per_event), "seeded", int(per_event.seeded.sum()), "v2 result:", {k: v for k, v in res.items() if k in ("pct_effect", "pct_ci95", "n_seeded", "n_unseeded")}, flush=True)
    panel_inputs.append((s, meta, daily, per_event, evw))

# ---- 4. pooled v2.3 per-generator plume fit across seasons ----
if not skip_w:
    import v23_per_generator as v23
    rows = []
    for s, meta, daily, per_event, evw in panel_inputs:
        seeded_map = {(r["program"], r["e0"]): bool(r["seeded"]) for _, r in per_event.iterrows()}
        prec = daily[daily["element"] == "PREC"].copy(); prec["date"] = pd.to_datetime(prec["date"]); prec = prec.sort_values(["triplet", "date"]); prec["dp"] = prec.groupby("triplet")["value"].diff(); prec.loc[(prec["dp"] < 0) | (prec["dp"] > 8), "dp"] = np.nan
        dp = prec.pivot_table(index="date", columns="triplet", values="dp"); m = meta.set_index("triplet"); trips = np.array([t for t in dp.columns if t in m.index]); sla = m.loc[trips, "lat"].astype(float).to_numpy(); slo = m.loc[trips, "lon"].astype(float).to_numpy()
        def hav(lat1, lon1, lat2, lon2):
            p1, p2 = np.radians(lat1), np.radians(lat2); dl = np.radians(lon2) - np.radians(lon1); return 2 * 6371 * np.arcsin(np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))
        def bear(lat1, lon1, lat2, lon2):
            dl = np.radians(lon2 - lon1); y = np.sin(dl) * np.cos(np.radians(lat2)); x = np.cos(np.radians(lat1)) * np.sin(np.radians(lat2)) - np.sin(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.cos(dl); return np.degrees(np.arctan2(y, x)) % 360
        for prog, pg in gens.groupby("program"):
            pw = evw[evw.program == prog]
            if not len(pw): continue
            gla, glo = pg.lat.to_numpy(), pg.lon.to_numpy(); D = hav(sla[:, None], slo[:, None], gla[None, :], glo[None, :]); B = bear(gla[None, :], glo[None, :], sla[:, None], slo[:, None]); idx = np.where(D.min(axis=1) <= v23.RING_KM)[0]
            for _, ev in pw.iterrows():
                seeded = seeded_map.get((prog, ev.e0))
                if seeded is None: continue
                e0, e1 = pd.Timestamp(ev.e0), pd.Timestamp(ev.e1); w = dp.loc[(dp.index >= e0) & (dp.index <= e1 + pd.Timedelta(days=1)), list(trips[idx])].sum(axis=0, min_count=1).to_numpy()
                dB = np.abs((B[idx] - ((ev.wind_dir_from_deg + 180) % 360) + 180) % 360 - 180); in_pl = ((dB <= v23.PLUME_DEG) & (D[idx] >= v23.D_LO) & (D[idx] <= v23.D_HI)).any(axis=1); score = (np.cos(np.radians(dB)) * np.exp(-D[idx] / 40.0)).max(axis=1)
                for k, t in enumerate(trips[idx]):
                    if np.isfinite(w[k]) and w[k] > 0.01: rows.append((f"{prog}:{t}", f"{s}:{prog}:{ev.e0}", float(np.log(w[k])), float(score[k]), bool(in_pl[k]), seeded, s))
    df = pd.DataFrame(rows, columns=["sid", "eid", "y", "score", "in_plume", "seeded", "season"]); print(f"pooled panel: {len(df)} obs, {df.sid.nunique()} stations, {df.eid.nunique()} program-events over {df.season.nunique()} seasons", flush=True)
    def fit(d):
        X = np.column_stack([d.score.to_numpy(), (d.in_plume & d.seeded).astype(float), (d.in_plume & ~d.seeded).astype(float)]); Z = np.column_stack([d.y.to_numpy(), X]); sid, eid = d.sid.to_numpy(), d.eid.to_numpy()
        for _ in range(30): Z = Z - pd.DataFrame(Z).groupby(sid).transform("mean").to_numpy(); Z = Z - pd.DataFrame(Z).groupby(eid).transform("mean").to_numpy()
        return np.linalg.lstsq(Z[:, 1:], Z[:, 0], rcond=None)[0]
    b = fit(df); events = df.eid.unique(); rng = np.random.default_rng(5); boots = []
    for _ in range(400):
        pick = rng.choice(events, size=len(events), replace=True); sub = pd.concat([df[df.eid == e] for e in pick])
        try: boots.append(fit(sub))
        except Exception: pass
    boots = np.array(boots); out = {"seasons": seasons, "n_obs": len(df), "n_events": int(df.eid.nunique()), "n_seeded_events": int(df[df.seeded].eid.nunique())}
    for i, name in enumerate(["exposure_score", "plume_SEEDED", "plume_UNSEEDED"]):
        lo, hi = np.percentile(boots[:, i], [2.5, 97.5]); est = {"coef": round(float(b[i]), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}
        if name.startswith("plume"): est["pct_effect"] = round(100 * (np.exp(b[i]) - 1), 2); est["pct_ci95"] = [round(100 * (np.exp(lo) - 1), 2), round(100 * (np.exp(hi) - 1), 2)]
        out[name] = est
    # per-season plume_SEEDED for a stability check
    per = {}
    for s in seasons:
        d = df[df.season == s]
        if d.eid.nunique() > 10:
            bs = fit(d); per[s] = round(100 * (np.exp(bs[1]) - 1), 2)
    out["plume_SEEDED_pct_by_season"] = per; df.to_parquet(HERE / "data" / "v23-multi-panel.parquet", index=False)
    (HERE / "data" / "v23-multi-season-results.json").write_text(json.dumps(out, indent=2)); print(json.dumps(out, indent=2))
