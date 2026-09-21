"""v2.3 — plume rotation with PER-GENERATOR geometry (fixes v2.2's centroid crudeness).

For each station × event: in_plume = ANY generator of the program with
bearing(gen→station) within ±PLUME_DEG of the event's downwind direction and
distance 5–45 km (AgI transport range). Smooth-anisotropy control = continuous
exposure score max_g[cos(Δbearing)·exp(−dist/40km)] so the dummy identifies the
sharp plume edge beyond any smooth wind-aligned orographic gradient.

Same two-way FE (station, program-event) + event bootstrap as v2.2.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
PLUME_DEG = 40.0
D_LO, D_HI = 5.0, 45.0
RING_KM = 70.0  # panel = stations within this of any program generator


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
    evw = pd.read_csv(HERE / "data" / "event-winds-2024-25.csv")
    per_event = pd.read_csv(HERE / "data" / "results" / "storm-per-event-2024-25.csv")
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

    trips = [t for t in dp.columns if t in meta.index]
    sla = meta.loc[trips, "lat"].astype(float).to_numpy()
    slo = meta.loc[trips, "lon"].astype(float).to_numpy()
    trips = np.array(trips)

    rows = []
    for prog, pg in gens.groupby("program"):
        pw = evw[evw["program"] == prog]
        if not len(pw):
            continue
        gla = pg["lat"].to_numpy()
        glo = pg["lon"].to_numpy()
        D = hav_km(sla[:, None], slo[:, None], gla[None, :], glo[None, :])
        B = bearing(gla[None, :], glo[None, :], sla[:, None], slo[:, None])
        near = (D.min(axis=1) <= RING_KM)
        idx = np.where(near)[0]
        for _, ev in pw.iterrows():
            seeded = seeded_map.get((prog, ev["e0"]))
            if seeded is None:
                continue
            e0, e1 = pd.Timestamp(ev["e0"]), pd.Timestamp(ev["e1"])
            w = dp.loc[(dp.index >= e0) & (dp.index <= e1 + pd.Timedelta(days=1)),
                       list(trips[idx])].sum(axis=0, min_count=1).to_numpy()
            downwind = (ev["wind_dir_from_deg"] + 180.0) % 360.0
            dB = np.abs((B[idx] - downwind + 180) % 360 - 180)
            in_plume = ((dB <= PLUME_DEG) & (D[idx] >= D_LO)
                        & (D[idx] <= D_HI)).any(axis=1)
            score = (np.cos(np.radians(dB)) * np.exp(-D[idx] / 40.0)).max(axis=1)
            for k, t in enumerate(trips[idx]):
                if np.isfinite(w[k]) and w[k] > 0.01:
                    rows.append((f"{prog}:{t}", f"{prog}:{ev['e0']}",
                                 float(np.log(w[k])), float(score[k]),
                                 bool(in_plume[k]), seeded))

    df = pd.DataFrame(rows, columns=["sid", "eid", "y", "score",
                                     "in_plume", "seeded"])
    print(f"panel: {len(df)} obs, {df['sid'].nunique()} stations, "
          f"{df['eid'].nunique()} program-events, "
          f"in-plume share {(df['in_plume'].mean()):.2f}")

    def fit(d):
        X = np.column_stack([
            d["score"].to_numpy(),
            (d["in_plume"] & d["seeded"]).astype(float),
            (d["in_plume"] & ~d["seeded"]).astype(float),
        ])
        Z = np.column_stack([d["y"].to_numpy(), X])
        sid = d["sid"].to_numpy()
        eid = d["eid"].to_numpy()
        for _ in range(30):
            Z = Z - pd.DataFrame(Z).groupby(sid).transform("mean").to_numpy()
            Z = Z - pd.DataFrame(Z).groupby(eid).transform("mean").to_numpy()
        beta, *_ = np.linalg.lstsq(Z[:, 1:], Z[:, 0], rcond=None)
        return beta

    b = fit(df)
    events = df["eid"].unique()
    rng = np.random.default_rng(5)
    boots = []
    for _ in range(400):
        pick = rng.choice(events, size=len(events), replace=True)
        sub = pd.concat([df[df["eid"] == e] for e in pick])
        try:
            boots.append(fit(sub))
        except Exception:
            pass
    boots = np.array(boots)
    out = {}
    for i, name in enumerate(["exposure_score", "plume_SEEDED",
                              "plume_UNSEEDED"]):
        lo_, hi_ = np.percentile(boots[:, i], [2.5, 97.5])
        est = {"coef": round(float(b[i]), 4),
               "ci95": [round(float(lo_), 4), round(float(hi_), 4)]}
        if name.startswith("plume"):
            est["pct_effect"] = round(100 * (np.exp(b[i]) - 1), 2)
            est["pct_ci95"] = [round(100 * (np.exp(lo_) - 1), 2),
                               round(100 * (np.exp(hi_) - 1), 2)]
        out[name] = est
    (HERE / "data" / "results" / "v23-per-generator-results.json").write_text(
        json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
