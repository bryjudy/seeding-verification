"""Design 0: 45-winter seasonal panel benchmark (staggered-adoption imputation estimator).

Pulls daily WTEQ + PREC for every SNOTEL station in UT and the six surrounding
states from the public USDA AWDB API (1979-10-01 -> present; cached per state in
data/.snotel_archive/, ~15-30 min on the first run), builds a station x winter
panel of Nov-Mar precipitation and Apr 1 SWE, then:

  1. fits station + winter fixed effects on UNTREATED observations only
     (out-of-state controls without their own seeding programs, plus Utah
     cohorts' pre-adoption winters; suspension winters excluded as endogenous),
  2. reads each treated station-winter's effect as observed minus imputed,
  3. aggregates overall / by cohort / by event time, CIs by winter-cluster bootstrap,
  4. runs a pre-adoption placebo (fake adoption 8 winters early),
  5. computes the classic double ratio for the always-seeded Central/Southern
     program around the 1983-87 statewide suspension.

Writes data/results/seasonal-panel-results.json and data/results/seasonal-panel.parquet.

  uv run --with pandas --with pyarrow --with numpy --with requests python src/run_seasonal_panel.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parents[1]
CACHE = HERE / "data" / ".snotel_archive"
API = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
STATES = ["UT", "CO", "NV", "WY", "ID", "AZ", "NM"]
BEGIN, END = "1979-10-01", "2026-07-16"


def pull_state(state):
    mfile, dfile = CACHE / f"stations_{state}.parquet", CACHE / f"daily_{state}.parquet"
    if mfile.exists() and dfile.exists():
        return pd.read_parquet(mfile), pd.read_parquet(dfile)
    r = requests.get(f"{API}/stations", params={"stationTriplets": f"*:{state}:SNTL",
                                                "activeOnly": "false"}, timeout=120)
    r.raise_for_status()
    meta = pd.DataFrame([{
        "triplet": s["stationTriplet"], "name": s.get("name"), "state": state,
        "lat": s.get("latitude"), "lon": s.get("longitude"),
        "elev_ft": s.get("elevation"), "county": s.get("countyName"),
    } for s in r.json()])
    rows = []
    trips = list(meta["triplet"])
    for b in range(0, len(trips), 10):
        batch = trips[b:b + 10]
        for attempt in range(5):
            try:
                r = requests.get(f"{API}/data", params={
                    "stationTriplets": ",".join(batch), "elements": "WTEQ,PREC",
                    "duration": "DAILY", "beginDate": BEGIN, "endDate": END}, timeout=600)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt == 4:
                    raise
                print(f"  retry {state} batch {b}: {e!r}", flush=True)
                time.sleep(6 * (attempt + 1))
        for st in r.json():
            trip = st["stationTriplet"]
            for el in st.get("data", []):
                code = el.get("stationElement", {}).get("elementCode")
                for v in el.get("values", []):
                    if v.get("value") is not None:
                        rows.append((trip, code, v["date"], v["value"]))
        print(f"  {state}: {b + len(batch)}/{len(trips)} stations, {len(rows):,} rows", flush=True)
        time.sleep(0.5)
    df = pd.DataFrame(rows, columns=["triplet", "element", "date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    CACHE.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(mfile)
    df.to_parquet(dfile)
    return meta, df


def main(min_years=15):
    treat = json.loads((HERE / "data" / "seeding_treatment.json").read_text())
    metas, dailies = [], []
    for s in STATES:
        print(f"== {s}", flush=True)
        m, d = pull_state(s)
        metas.append(m); dailies.append(d)
    meta = pd.concat(metas, ignore_index=True)
    daily = pd.concat(dailies, ignore_index=True)
    meta["county"] = meta["county"].str.upper().str.strip()
    print(f"archive: {meta.shape[0]} stations, {len(daily):,} daily obs", flush=True)

    d = daily
    d["y"] = d["date"].dt.year; d["m"] = d["date"].dt.month; d["dd"] = d["date"].dt.day
    d["wy"] = d["y"] + (d["m"] >= 10).astype(int)
    prec = d[d["element"] == "PREC"]
    mar = (prec[(prec["m"] == 3) & (prec["dd"] >= 25)].groupby(["triplet", "wy"])["value"].max().rename("prec_mar"))
    oct_ = (prec[(prec["m"] == 10) & (prec["dd"] >= 25)].groupby(["triplet", "wy"])["value"].max().rename("prec_oct"))
    winter = pd.concat([mar, oct_], axis=1).dropna()
    winter["winter_prec"] = winter["prec_mar"] - winter["prec_oct"]
    winter = winter[winter["winter_prec"] > 0.5]
    wteq = d[(d["element"] == "WTEQ") & (((d["m"] == 3) & (d["dd"] >= 29)) | ((d["m"] == 4) & (d["dd"] <= 3)))]
    apr1 = wteq.groupby(["triplet", "wy"])["value"].mean().rename("apr1_swe")
    panel = winter.join(apr1).reset_index().merge(
        meta[["triplet", "state", "county", "lat", "lon", "elev_ft"]], on="triplet", how="left")
    panel = panel[(panel["wy"] >= 1981) & (panel["wy"] <= 2026)]

    area_by_name = {a["name"]: a for a in treat["areas"]}

    def assign_area(row):
        if row["state"] != "UT":
            return None
        for a in treat["areas"]:
            if a["counties"] == ["*"] or row["county"] in a["counties"]:
                return a["name"]
        return None

    panel["area"] = panel.apply(assign_area, axis=1)
    blocked = {(ex["state"], c) for ex in treat["excluded_control_regions"] for c in ex["counties_blocklist"]}
    panel["is_blocked_control"] = [(s, c) in blocked for s, c in zip(panel["state"], panel["county"])]

    def seeded(area, wy):
        if not isinstance(area, str):
            return 0
        sw = area_by_name[area]["seeded_winters"]
        if wy < sw["start"] or (sw["end"] and wy > sw["end"]):
            return 0
        return -1 if wy in sw["gaps"] else 1

    panel["seeded"] = [seeded(a, w) for a, w in zip(panel["area"], panel["wy"])]
    panel["role"] = "excluded"
    panel.loc[(panel["state"] != "UT") & (~panel["is_blocked_control"]), "role"] = "control"
    staggered = [a["name"] for a in treat["areas"] if a["seeded_winters"]["start"] >= 1981]
    panel.loc[panel["area"].isin(staggered), "role"] = "cohort"
    panel.loc[panel["area"] == "central_southern_utah", "role"] = "always"
    ok = panel.groupby("triplet")["wy"].transform("count") >= min_years
    panel = panel[ok].copy()
    panel["logp"] = np.log(panel["winter_prec"])
    fit_mask = (panel["role"] == "control") | ((panel["role"] == "cohort") & (panel["seeded"] == 0))

    def fit_fe(df_fit, tol=1e-9, iters=200):
        y = df_fit["logp"].to_numpy(); trip = df_fit["triplet"].to_numpy(); wy = df_fit["wy"].to_numpy()
        gv = np.zeros(len(y)); a = g = None
        for _ in range(iters):
            s = pd.Series(y - gv).groupby(trip).mean(); a = s.to_dict(); av = s.reindex(trip).to_numpy()
            s2 = pd.Series(y - av).groupby(wy).mean(); gnew = s2.to_dict(); gv_new = s2.reindex(wy).to_numpy()
            done = np.max(np.abs(gv_new - gv)) < tol
            gv, g = gv_new, gnew
            if done:
                break
        return a, g

    alpha, gamma = fit_fe(panel[fit_mask])
    tr = panel[(panel["role"] == "cohort") & (panel["seeded"] == 1)].copy()
    tr = tr[tr["triplet"].isin(alpha) & tr["wy"].isin(gamma)]
    tr["tau"] = tr["logp"] - tr["triplet"].map(alpha) - tr["wy"].map(gamma)

    pct = lambda x: round(100 * (np.exp(x) - 1), 2)
    point = {"overall_pct": pct(tr["tau"].mean()), "n_obs": int(len(tr)), "by_cohort": {}}
    for a, grp in tr.groupby("area"):
        point["by_cohort"][a] = {"pct": pct(grp["tau"].mean()), "n": int(len(grp)),
                                 "stations": int(grp["triplet"].nunique()),
                                 "first_winter": int(area_by_name[a]["seeded_winters"]["start"])}
    years = sorted(panel["wy"].unique()); rng = np.random.default_rng(7); boots = []
    for _ in range(400):
        wts = pd.Series(rng.choice(years, size=len(years), replace=True)).value_counts()
        tw = tr["wy"].map(wts).fillna(0)
        if tw.sum() > 0:
            boots.append(100 * (np.exp(np.average(tr["tau"], weights=tw)) - 1))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    point["overall_ci95"] = [round(float(lo), 2), round(float(hi), 2)]
    # per-cohort winter-cluster bootstrap CIs
    for a, grp in tr.groupby("area"):
        bs = []
        yrs = sorted(grp["wy"].unique())
        for _ in range(400):
            wts = pd.Series(rng.choice(yrs, size=len(yrs), replace=True)).value_counts()
            tw = grp["wy"].map(wts).fillna(0)
            if tw.sum() > 0:
                bs.append(100 * (np.exp(np.average(grp["tau"], weights=tw)) - 1))
        l, h = np.percentile(bs, [2.5, 97.5])
        point["by_cohort"][a]["ci95"] = [round(float(l), 2), round(float(h), 2)]

    tr["rel"] = [w - area_by_name[a]["seeded_winters"]["start"] for a, w in zip(tr["area"], tr["wy"])]
    ev = {int(k): pct(v) for k, v in tr.groupby("rel")["tau"].mean().items()}

    plc_parts = []
    pre = panel[(panel["role"] == "cohort") & (panel["seeded"] == 0)]
    for a in staggered:
        start = area_by_name[a]["seeded_winters"]["start"]
        plc_parts.append(pre[(pre["area"] == a) & (pre["wy"] >= start - 8) & (pre["wy"] < start)])
    plc = pd.concat(plc_parts)
    alpha2, gamma2 = fit_fe(panel[fit_mask & ~panel.index.isin(plc.index)])
    plc = plc[plc["triplet"].isin(alpha2) & plc["wy"].isin(gamma2)]
    placebo_pct = pct((plc["logp"] - plc["triplet"].map(alpha2) - plc["wy"].map(gamma2)).mean())

    t_on = panel[(panel["role"] == "always") & (panel["seeded"] == 1)]
    t_off = panel[(panel["role"] == "always") & (panel["seeded"] == -1)]
    c_all = panel[panel["role"] == "control"]
    c_on = c_all[c_all["wy"].isin(t_on["wy"].unique())]; c_off = c_all[c_all["wy"].isin(t_off["wy"].unique())]
    dr = (t_on["winter_prec"].mean() / c_on["winter_prec"].mean()) / (t_off["winter_prec"].mean() / c_off["winter_prec"].mean())

    results = {
        "panel": {"stations": int(panel["triplet"].nunique()), "station_winters": int(len(panel)),
                  "winters": [int(panel["wy"].min()), int(panel["wy"].max())],
                  "control_stations": int(panel[panel["role"] == "control"]["triplet"].nunique()),
                  "cohort_stations": int(panel[panel["role"] == "cohort"]["triplet"].nunique()),
                  "daily_obs": int(len(daily))},
        "imputation_estimator_log_winter_prec": point,
        "event_study_pct_by_rel_year": ev,
        "placebo_pre8yr_pct": placebo_pct,
        "central_southern_double_ratio": round(float(dr), 4),
        "double_ratio_caveat": "suspension winters 1984-87 were wet by construction; ratio biased toward showing a seeding effect",
    }
    out = HERE / "data" / "results"
    out.mkdir(exist_ok=True)
    (out / "seasonal-panel-results.json").write_text(json.dumps(results, indent=2))
    panel.drop(columns=["is_blocked_control"]).to_parquet(out / "seasonal-panel.parquet")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
