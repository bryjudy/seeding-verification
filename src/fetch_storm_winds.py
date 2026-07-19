"""Per-storm 700mb winds at each program's generator centroid, from HRRR.

For every distinct storm window in data/seeded-storms-2024-25.csv, sample the
HRRR analysis (f00) at 6-hourly synoptic times, byte-range-fetching ONLY the
UGRD/VGRD 700mb messages (~1.2MB/hour instead of ~500MB/file), decode with
eccodes, take the nearest grid point to each program's generator centroid, and
vector-average over the window.

Output: data/storm-winds-2024-25.csv
  program, date_start, date_end, wind_dir_from_deg, wind_speed_ms, n_hours
Hourly values cached in data/.wind_cache.json so re-runs are cheap.

Run locally (no Beam needed):
  uv run --with eccodes --with numpy --with requests python fetch_storm_winds.py
"""

import csv
import json
import math
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import requests

HERE = Path(__file__).resolve().parents[1]
BUCKET = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com"
CACHE = HERE / "data" / ".wind_cache.json"


def centroids():
    gens = list(csv.DictReader(open(HERE / "data" / "generators-2024-25.csv")))
    by_prog = defaultdict(list)
    for g in gens:
        by_prog[g["program"]].append((float(g["lat"]), float(g["lon"])))
    return {p: (float(np.mean([x[0] for x in v])),
                float(np.mean([x[1] for x in v])))
            for p, v in by_prog.items()}


def storm_windows():
    rows = list(csv.DictReader(open(HERE / "data" / "seeded-storms-2024-25.csv")))
    # also cover every detected event window (incl. unseeded), if available
    ev = HERE / "data" / "storm-per-event-2024-25.csv"
    if ev.exists():
        for r in csv.DictReader(open(ev)):
            rows.append({"program": r["program"], "date_start": r["e0"],
                         "date_end": r["e1"]})
    return rows


def fetch_uv(date, hour, points):
    """700mb (u, v) at each (lat, lon) point for one HRRR analysis hour."""
    import eccodes

    key = f"hrrr.{date}/conus/hrrr.t{hour:02d}z.wrfprsf00.grib2"
    idx = requests.get(f"{BUCKET}/{key}.idx", timeout=60)
    if idx.status_code != 200:
        return None
    lines = idx.text.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        f = ln.split(":")
        if f[3] == "UGRD" and f[4] == "700 mb":
            start = int(f[1])
            # VGRD:700mb is the next message; take range through the one after
            end = int(lines[i + 2].split(":")[1]) - 1 if i + 2 < len(lines) else None
            break
    if start is None:
        return None
    rng = f"bytes={start}-{end}" if end else f"bytes={start}-"
    blob = requests.get(f"{BUCKET}/{key}", headers={"Range": rng}, timeout=120)
    if blob.status_code not in (200, 206):
        return None

    out = []
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf:
        tf.write(blob.content)
        tf.flush()
        with open(tf.name, "rb") as f:
            u_id = eccodes.codes_grib_new_from_file(f)
            v_id = eccodes.codes_grib_new_from_file(f)
            if u_id is None or v_id is None:
                if u_id:
                    eccodes.codes_release(u_id)
                return None
            for lat, lon in points:
                nu = eccodes.codes_grib_find_nearest(u_id, lat, lon)[0]
                nv = eccodes.codes_grib_find_nearest(v_id, lat, lon)[0]
                out.append((nu.value, nv.value))
            eccodes.codes_release(u_id)
            eccodes.codes_release(v_id)
    return out


def main():
    cents = centroids()
    progs = sorted(cents)
    pts = [cents[p] for p in progs]

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    # distinct hours needed across all storm windows
    windows = storm_windows()
    hours_needed = set()
    for w in windows:
        d0 = datetime.fromisoformat(w["date_start"])
        d1 = datetime.fromisoformat(w["date_end"]) + timedelta(days=1)
        t = d0
        while t < d1:
            hours_needed.add((t.strftime("%Y%m%d"), t.hour))
            t += timedelta(hours=6)

    print(f"{len(windows)} program-storms, {len(hours_needed)} distinct HRRR hours")
    for n, (date, hour) in enumerate(sorted(hours_needed)):
        ck = f"{date}T{hour:02d}"
        if ck in cache:
            continue
        try:
            uv = fetch_uv(date, hour, pts)
        except Exception as e:
            print(f"  {ck}: ERROR {e}")
            uv = None
        cache[ck] = uv
        if n % 20 == 0:
            CACHE.write_text(json.dumps(cache))
            print(f"  {n}/{len(hours_needed)} hours fetched")
    CACHE.write_text(json.dumps(cache))

    # aggregate per program-storm: vector mean of (u, v)
    out_rows = []
    for w in windows:
        pi = progs.index(w["program"])
        d0 = datetime.fromisoformat(w["date_start"])
        d1 = datetime.fromisoformat(w["date_end"]) + timedelta(days=1)
        us, vs = [], []
        t = d0
        while t < d1:
            got = cache.get(f"{t.strftime('%Y%m%d')}T{t.hour:02d}")
            if got:
                us.append(got[pi][0])
                vs.append(got[pi][1])
            t += timedelta(hours=6)
        if not us:
            continue
        um, vm = float(np.mean(us)), float(np.mean(vs))
        speed = math.hypot(um, vm)
        # meteorological "from" direction
        dir_from = (math.degrees(math.atan2(-um, -vm))) % 360
        out_rows.append([w["program"], w["date_start"], w["date_end"],
                         round(dir_from, 1), round(speed, 1), len(us)])

    # event-level winds (per program x detected event), if event file exists
    ev = HERE / "data" / "storm-per-event-2024-25.csv"
    if ev.exists():
        ev_rows = []
        seen = set()
        for r in csv.DictReader(open(ev)):
            key = (r["program"], r["e0"], r["e1"])
            if key in seen:
                continue
            seen.add(key)
            pi = progs.index(r["program"])
            d0 = datetime.fromisoformat(r["e0"])
            d1 = datetime.fromisoformat(r["e1"]) + timedelta(days=1)
            us, vs = [], []
            t = d0
            while t < d1:
                got = cache.get(f"{t.strftime('%Y%m%d')}T{t.hour:02d}")
                if got:
                    us.append(got[pi][0])
                    vs.append(got[pi][1])
                t += timedelta(hours=6)
            if us:
                um, vm = float(np.mean(us)), float(np.mean(vs))
                ev_rows.append([r["program"], r["e0"], r["e1"],
                                round((math.degrees(math.atan2(-um, -vm))) % 360, 1),
                                round(math.hypot(um, vm), 1), len(us)])
        with open(HERE / "data" / "event-winds-2024-25.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["program", "e0", "e1", "wind_dir_from_deg",
                         "wind_speed_ms", "n_hours"])
            wr.writerows(ev_rows)
        print(f"wrote {len(ev_rows)} event-wind rows")

    out = HERE / "data" / "storm-winds-2024-25.csv"
    with open(out, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["program", "date_start", "date_end",
                     "wind_dir_from_deg", "wind_speed_ms", "n_hours"])
        wr.writerows(out_rows)
    print(f"wrote {len(out_rows)} rows -> {out}")
    dirs = [r[3] for r in out_rows]
    print(f"wind-from dirs: median {np.median(dirs):.0f}°, "
          f"WSW-NW share {(np.sum([(200 <= d <= 340) for d in dirs]) / len(dirs)):.0%}")


if __name__ == "__main__":
    main()
