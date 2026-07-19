"""Pure-pandas core of the storm-level seeding analysis (v2 design).

Shared by the local runner (run_storm_analysis_local.py) and the Beam version.
See beam_storm_analysis.py docstring for the design rationale.
"""

import json

import numpy as np
import pandas as pd

EXPOSED_KM = 40.0
NEARMISS_LO, NEARMISS_HI = 55.0, 130.0  # same-sector "near-miss" controls
CONTROL_KM = 90.0                        # legacy far-control distance
MIN_EVENT_IN = 0.15
SECTOR_DEG = 55.0


def analyze_storms(meta, daily, gens, storms, winds,
                   d0="2024-10-15", d1="2025-05-05"):
    gens = gens.copy()
    gens["lat"] = gens["lat"].astype(float)
    gens["lon"] = gens["lon"].astype(float)
    storms = storms.copy()
    storms["date_start"] = pd.to_datetime(storms["date_start"])
    storms["date_end"] = pd.to_datetime(storms["date_end"])

    downwind = {}
    if winds is not None and len(winds):
        winds = winds.copy()
        winds["wind_dir_from_deg"] = winds["wind_dir_from_deg"].astype(float)
        for p, grp in winds.groupby("program"):
            th = np.radians(grp["wind_dir_from_deg"].to_numpy())
            mfrom = np.degrees(np.arctan2(np.sin(th).mean(),
                                          np.cos(th).mean())) % 360
            downwind[p] = (mfrom + 180.0) % 360.0

    prec = daily[daily["element"] == "PREC"].copy()
    prec["date"] = pd.to_datetime(prec["date"])
    prec = prec[(prec["date"] >= d0) & (prec["date"] <= d1)]
    prec = prec.sort_values(["triplet", "date"])
    prec["dp"] = prec.groupby("triplet")["value"].diff()
    prec.loc[(prec["dp"] < 0) | (prec["dp"] > 8), "dp"] = np.nan
    dp = prec.pivot_table(index="date", columns="triplet", values="dp")

    meta = meta.dropna(subset=["lat", "lon"]).set_index("triplet")
    trips = [t for t in dp.columns if t in meta.index]
    slat = meta.loc[trips, "lat"].astype(float).to_numpy()
    slon = meta.loc[trips, "lon"].astype(float).to_numpy()
    glat = gens["lat"].to_numpy()
    glon = gens["lon"].to_numpy()

    def hav_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dl = np.radians(lon2) - np.radians(lon1)
        a = (np.sin((p2 - p1) / 2) ** 2
             + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2)
        return 2 * R * np.arcsin(np.sqrt(a))

    D = hav_km(slat[:, None], slon[:, None], glat[None, :], glon[None, :])

    dlon = np.radians(glon[None, :] * 0 + slon[:, None] - glon[None, :])
    y = np.sin(dlon) * np.cos(np.radians(slat))[:, None]
    x = (np.cos(np.radians(glat))[None, :] * np.sin(np.radians(slat))[:, None]
         - np.sin(np.radians(glat))[None, :]
         * np.cos(np.radians(slat))[:, None] * np.cos(dlon))
    brg = np.degrees(np.arctan2(y, x)) % 360
    east_of = slon[:, None] > glon[None, :]

    programs = sorted(gens["program"].unique())
    exposed, nearmiss = {}, {}
    any_exposed = np.zeros(len(trips), dtype=bool)
    for p in programs:
        gi = (gens["program"] == p).to_numpy()
        if p in downwind:
            ang = np.abs((brg[:, gi] - downwind[p] + 180) % 360 - 180)
            in_sector = ang <= SECTOR_DEG
        else:
            in_sector = east_of[:, gi]
        exposed[p] = ((D[:, gi] <= EXPOSED_KM) & in_sector).any(axis=1)
        any_exposed |= exposed[p]
    for p in programs:
        gi = (gens["program"] == p).to_numpy()
        if p in downwind:
            ang = np.abs((brg[:, gi] - downwind[p] + 180) % 360 - 180)
            in_sector = ang <= SECTOR_DEG
        else:
            in_sector = east_of[:, gi]
        near = ((D[:, gi] >= NEARMISS_LO) & (D[:, gi] <= NEARMISS_HI)
                & in_sector).any(axis=1)
        # near-miss must not be inside ANY program's plume
        nearmiss[p] = near & ~any_exposed
    control_mask = ~(D <= CONTROL_KM).any(axis=1)

    trips_arr = np.array(trips)
    ctl_trips = trips_arr[control_mask]

    # Utah-local storm catalog: events defined by the union of exposed +
    # near-miss stations (storms relevant to the target regions)
    local_trips = trips_arr[any_exposed
                            | np.any([nearmiss[p] for p in programs], axis=0)]
    ctl_daily = dp[local_trips].mean(axis=1)
    stormy = ctl_daily > MIN_EVENT_IN
    events, cur = [], None
    for d, s in stormy.items():
        if s and cur is None:
            cur = [d, d]
        elif s:
            cur[1] = d
        elif cur:
            events.append(tuple(cur))
            cur = None
    if cur:
        events.append(tuple(cur))

    def storm_total(trip_list, e0, e1):
        w = dp.loc[(dp.index >= e0) & (dp.index <= e1 + pd.Timedelta(days=1)),
                   trip_list]
        return w.sum(axis=0, min_count=1)

    results = {}
    per_storm_rows = []
    for p in programs:
        exp_trips = trips_arr[exposed[p]]
        nm_trips = trips_arr[nearmiss[p]]
        if len(exp_trips) < 3 or len(nm_trips) < 3:
            results[p] = {"skipped": f"{len(exp_trips)} exposed / "
                                     f"{len(nm_trips)} near-miss stations"}
            continue
        ps = storms[storms["program"] == p]
        rows = []
        for e0, e1 in events:
            seeded = bool(((ps["date_start"] <= e1 + pd.Timedelta(days=1)) &
                           (ps["date_end"] >= e0 - pd.Timedelta(days=1))).any())
            te = storm_total(list(exp_trips), e0, e1)
            tc = storm_total(list(nm_trips), e0, e1)
            me, mc = te.mean(), tc.mean()
            if mc and mc > 0.05 and me and me > 0:
                rows.append((seeded, float(np.log(me / mc)), float(mc)))
                per_storm_rows.append([p, str(e0.date()), str(e1.date()),
                                       seeded, round(float(me), 3),
                                       round(float(mc), 3)])
        rows = pd.DataFrame(rows, columns=["seeded", "logR", "ctl_size"])
        if rows["seeded"].nunique() < 2:
            results[p] = {"skipped": "no seeded/unseeded contrast"}
            continue
        eff = (rows[rows["seeded"]]["logR"].mean()
               - rows[~rows["seeded"]]["logR"].mean())
        rng = np.random.default_rng(11)
        boots = []
        for _ in range(2000):
            b = rows.sample(len(rows), replace=True,
                            random_state=int(rng.integers(1e9)))
            if b["seeded"].nunique() == 2:
                boots.append(b[b["seeded"]]["logR"].mean()
                             - b[~b["seeded"]]["logR"].mean())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        results[p] = {
            "effect_pct": round(100 * (np.exp(eff) - 1), 2),
            "ci95": [round(100 * (np.exp(lo) - 1), 2),
                     round(100 * (np.exp(hi) - 1), 2)],
            "n_storms_seeded": int(rows["seeded"].sum()),
            "n_storms_unseeded": int((~rows["seeded"]).sum()),
            "n_exposed_stations": int(len(exp_trips)),
            "n_nearmiss_stations": int(len(nm_trips)),
        }

    # pooled estimate across programs (storm-program obs, bootstrap over events)
    psr = pd.DataFrame(per_storm_rows, columns=[
        "program", "e0", "e1", "seeded", "exp_mean", "ctl_mean"])
    psr["logR"] = np.log(psr["exp_mean"] / psr["ctl_mean"])
    pooled = None
    if psr["seeded"].nunique() == 2:
        eff = (psr[psr["seeded"]]["logR"].mean()
               - psr[~psr["seeded"]]["logR"].mean())
        ev_ids = sorted(psr["e0"].unique())
        rng = np.random.default_rng(13)
        boots = []
        for _ in range(2000):
            pick = rng.choice(ev_ids, size=len(ev_ids), replace=True)
            wts = pd.Series(pick).value_counts()
            w = psr["e0"].map(wts).fillna(0)
            s1 = psr["seeded"] & (w > 0)
            s0 = ~psr["seeded"] & (w > 0)
            if s1.any() and s0.any():
                boots.append(np.average(psr[s1]["logR"], weights=w[s1])
                             - np.average(psr[s0]["logR"], weights=w[s0]))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        pooled = {"effect_pct": round(100 * (np.exp(eff) - 1), 2),
                  "ci95": [round(100 * (np.exp(lo) - 1), 2),
                           round(100 * (np.exp(hi) - 1), 2)],
                  "n_obs": int(len(psr))}

    return {"events_detected": len(events),
            "downwind_deg_by_program": {k: round(v, 1)
                                        for k, v in downwind.items()},
            "pooled": pooled,
            "programs": results,
            "per_storm": per_storm_rows}
