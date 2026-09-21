"""Run the storm-level analysis entirely locally (Beam-free).

Pulls just winter 2024-25 daily PREC for all SNOTEL stations in the 7 states
straight from the public AWDB API (cached in data/.local_snotel/), then runs
storm_core.analyze_storms. Writes data/results/storm-results-2024-25.json.

  uv run --with pandas --with pyarrow --with numpy --with requests \
      python run_storm_analysis.py
"""

import json
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parents[1]
CACHE = HERE / "data" / ".local_snotel"
API = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
STATES = ["UT", "CO", "NV", "WY", "ID", "AZ", "NM"]


def pull_state(state):
    mfile = CACHE / f"stations_{state}.parquet"
    dfile = CACHE / f"daily_{state}.parquet"
    if mfile.exists() and dfile.exists():
        return pd.read_parquet(mfile), pd.read_parquet(dfile)
    r = requests.get(f"{API}/stations",
                     params={"stationTriplets": f"*:{state}:SNTL",
                             "activeOnly": "false"}, timeout=120)
    r.raise_for_status()
    meta = pd.DataFrame([{
        "triplet": s["stationTriplet"], "name": s.get("name"), "state": state,
        "lat": s.get("latitude"), "lon": s.get("longitude"),
        "elev_ft": s.get("elevation"), "county": s.get("countyName"),
    } for s in r.json()])

    rows = []
    trips = list(meta["triplet"])
    for b in range(0, len(trips), 15):
        batch = trips[b:b + 15]
        for attempt in range(4):
            try:
                r = requests.get(f"{API}/data", params={
                    "stationTriplets": ",".join(batch),
                    "elements": "PREC", "duration": "DAILY",
                    "beginDate": "2024-10-14", "endDate": "2025-05-06",
                }, timeout=180)
                r.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(4 * (attempt + 1))
        for st in r.json():
            for el in st.get("data", []):
                for v in el.get("values", []):
                    if v.get("value") is not None:
                        rows.append((st["stationTriplet"], "PREC",
                                     v["date"], v["value"]))
        time.sleep(0.4)
    daily = pd.DataFrame(rows, columns=["triplet", "element", "date", "value"])
    CACHE.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(mfile)
    daily.to_parquet(dfile)
    return meta, daily


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from storm_core import analyze_storms

    metas, dailies = [], []
    for s in STATES:
        m, d = pull_state(s)
        metas.append(m)
        dailies.append(d)
        print(f"{s}: {len(m)} stations, {len(d)} obs")
    meta = pd.concat(metas, ignore_index=True)
    daily = pd.concat(dailies, ignore_index=True)

    gens = pd.read_csv(HERE / "data" / "generators-2024-25.csv")
    storms = pd.read_csv(HERE / "data" / "seeded-storms-2024-25.csv")
    winds = pd.read_csv(HERE / "data" / "storm-winds-2024-25.csv")

    res = analyze_storms(meta, daily, gens, storms, winds)
    per_storm = res.pop("per_storm")
    pd.DataFrame(per_storm, columns=[
        "program", "e0", "e1", "seeded", "exp_mean_in", "ctl_mean_in"]
    ).to_csv(HERE / "data" / "results" / "storm-per-event-2024-25.csv", index=False)
    out = HERE / "data" / "results" / "storm-results-2024-25.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
