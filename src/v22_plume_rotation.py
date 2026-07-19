"""v2.2 — plume-rotation test (the anti-selection design).

Panel: stations within RING_KM of each program's generator centroid × detected
storm events. Exposure rotates storm-by-storm with that storm's own 700mb wind:
  in_plume(station, event) = |bearing(centroid→station) − downwind(event)| ≤ 50°

Model (pooled, two-way FE):
  log precip_se = station FE + event FE
                  + b1·cos(rel) + b2·sin(rel)        <- smooth wind-anisotropy
                  + β_s·[in_plume & seeded] + β_u·[in_plume & unseeded]
Real seeding: β_s > 0, β_u ≈ 0. Orographic anisotropy loads on cos/sin and on
BOTH β's equally; storm selection can't rotate with the wind at all.

Inference: bootstrap over events. Needs data/event-winds-2024-25.csv
(fetch_storm_winds.py) and the cached local SNOTEL pull.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
RING_KM = 60.0
PLUME_DEG = 50.0


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_storm_analysis import pull_state, STATES

    metas, dailies = [], []
    for s in STATES:
        m, d = pull_state(s)
        metas.append(m)
        dailies.append(d)
    meta = pd.concat(metas, ignore_index=True).dropna(subset=["lat", "lon"])
    daily = pd.concat(dailies, ignore_index=True)

    gens = pd.read_csv(HERE / "data" / "generators-2024-25.csv")
    cents = gens.groupby("program")[["lat", "lon"]].mean()
    evw = pd.read_csv(HERE / "data" / "event-winds-2024-25.csv")
    per_event = pd.read_csv(HERE / "data" / "storm-per-event-2024-25.csv")
    seeded_map = {(r["program"], r["e0"]): bool(r["seeded"])
                  for _, r in per_event.iterrows()}

    prec = daily[daily["element"] == "PREC"].copy()
    prec["date"] = pd.to_datetime(prec["date"])
    prec = prec.sort_values(["triplet", "date"])
    prec["dp"] = prec.groupby("triplet")["value"].diff()
    prec.loc[(prec["dp"] < 0) | (prec["dp"] > 8), "dp"] = np.nan
    dp = prec.pivot_table(index="date", columns="triplet", values="dp")
    meta = meta.set_index("triplet")

    def hav_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dl = np.radians(lon2) - np.radians(lon1)
        a = (np.sin((p2 - p1) / 2) ** 2
             + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2)
        return 2 * R * np.arcsin(np.sqrt(a))

    def bearing(lat1, lon1, lat2, lon2):
        dl = np.radians(lon2 - lon1)
        y = np.sin(dl) * np.cos(np.radians(lat2))
        x = (np.cos(np.radians(lat1)) * np.sin(np.radians(lat2))
             - np.sin(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.cos(dl))
        return np.degrees(np.arctan2(y, x)) % 360

    rows = []
    for prog, c in cents.iterrows():
        pw = evw[evw["program"] == prog]
        if not len(pw):
            continue
        trips = [t for t in dp.columns if t in meta.index]
        la = meta.loc[trips, "lat"].astype(float).to_numpy()
        lo = meta.loc[trips, "lon"].astype(float).to_numpy()
        dist = hav_km(c["lat"], c["lon"], la, lo)
        brg = bearing(c["lat"], c["lon"], la, lo)
        sel = dist <= RING_KM
        ring_trips = np.array(trips)[sel]
        ring_brg = brg[sel]
        for _, ev in pw.iterrows():
            e0, e1 = pd.Timestamp(ev["e0"]), pd.Timestamp(ev["e1"])
            w = dp.loc[(dp.index >= e0) & (dp.index <= e1 + pd.Timedelta(days=1)),
                       list(ring_trips)].sum(axis=0, min_count=1)
            downwind = (ev["wind_dir_from_deg"] + 180.0) % 360.0
            rel = (ring_brg - downwind + 180) % 360 - 180
            seeded = seeded_map.get((prog, ev["e0"]))
            if seeded is None:
                continue
            for t, b, r_ in zip(ring_trips, w.to_numpy(), rel):
                if np.isfinite(b) and b > 0.01:
                    rows.append((f"{prog}:{t}", f"{prog}:{ev['e0']}",
                                 np.log(b), np.radians(r_),
                                 abs(r_) <= PLUME_DEG, seeded))
    df = pd.DataFrame(rows, columns=["sid", "eid", "y", "rel",
                                     "in_plume", "seeded"])
    print(f"panel: {len(df)} station-events, {df['sid'].nunique()} stations, "
          f"{df['eid'].nunique()} program-events")

    def fit(d):
        d = d.copy()
        X = np.column_stack([
            np.cos(d["rel"]), np.sin(d["rel"]),
            (d["in_plume"] & d["seeded"]).astype(float),
            (d["in_plume"] & ~d["seeded"]).astype(float),
        ])
        y = d["y"].to_numpy().astype(float)
        # two-way within transform (iterated demeaning over sid/eid)
        Z = np.column_stack([y, X])
        sid = d["sid"].to_numpy()
        eid = d["eid"].to_numpy()
        for _ in range(30):
            Z = Z - pd.DataFrame(Z).groupby(sid).transform("mean").to_numpy()
            Z = Z - pd.DataFrame(Z).groupby(eid).transform("mean").to_numpy()
        yd, Xd = Z[:, 0], Z[:, 1:]
        beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
        return beta  # [cos, sin, plume_seeded, plume_unseeded]

    b = fit(df)
    events = df["eid"].unique()
    rng = np.random.default_rng(5)
    boots = []
    for _ in range(500):
        pick = rng.choice(events, size=len(events), replace=True)
        sub = pd.concat([df[df["eid"] == e] for e in pick])
        try:
            boots.append(fit(sub))
        except Exception:
            pass
    boots = np.array(boots)
    out = {}
    for i, name in enumerate(["cos_rel", "sin_rel", "plume_SEEDED",
                              "plume_UNSEEDED"]):
        lo_, hi_ = np.percentile(boots[:, i], [2.5, 97.5])
        est = {"coef": round(float(b[i]), 4),
               "ci95": [round(float(lo_), 4), round(float(hi_), 4)]}
        if name.startswith("plume"):
            est["pct_effect"] = round(100 * (np.exp(b[i]) - 1), 2)
            est["pct_ci95"] = [round(100 * (np.exp(lo_) - 1), 2),
                               round(100 * (np.exp(hi_) - 1), 2)]
        out[name] = est
    (HERE / "data" / "v22-plume-rotation-results.json").write_text(
        json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
