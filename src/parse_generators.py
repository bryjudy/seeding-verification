"""Parse generator-site tables out of the 2024-25 NAWC/DWR seasonal report texts
(data/reports-2024-25/*.txt, extracted with pdftotext -layout) into one dataset:
data/generators-2024-25.csv  (program, site_id, name, lat, lon, elev_ft).

Formats: older programs use degree-decimal-minutes (40°41.11' 112°40.10', with
typos: spaces, missing degree signs/quotes); 2023-expansion programs use decimal
degrees. Book Cliffs' report has town names only (added manually w/ approx coords).
"""

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPORTS = HERE / "data" / "reports-2024-25"

DEGMIN = re.compile(r"(\d{2,3})\s*°\s*(\d{1,2}\.\d+)\s*[''’]?")
# typo form in a few rows: degree sign missing but minutes carry a quote (40 12.40')
DEGMIN_TYPO = re.compile(r"\b(\d{2,3})\s+(\d{1,2}\.\d+)\s*[''’]")
DECIMAL = re.compile(r"(-?\d{2,3}\.\d{3,})")
ELEV = re.compile(r"\b([3-9]\d{3}|10\d{3})\b")

FILES = {
    "central_southern_tooele": "cs2425.txt",
    "western_uintas": "Western-Uintas-2024-25.txt",
    "high_uintas": "High-Uintas-2024-25.txt",
    "northern_utah": "Northern-Utah-Seasonal-Report-2024-2025-.txt",
    "six_creeks": "Six-Creeks-Report-2024-25.txt",
    "east_shore": "eastshore.txt",
    "cache_valley_uav": "Cache-Valley-UAV-Seasonal-Report-2024-2025.txt",
}

SITE_ID = re.compile(r"^\s*((?:TO|CU|SU|WU|HU|BE|CV|W|BC)-?\d+R?\*?|Remote)\b")


def parse_line(line):
    """Returns (lat, lon, elev) if the line looks like a site row, else None."""
    dm = DEGMIN.findall(line) + DEGMIN_TYPO.findall(line)
    lat = lon = None
    for d, m in dm:
        v = int(d) + float(m) / 60
        if 36.5 <= v <= 42.5 and lat is None:
            lat = v
        elif 108.5 <= v <= 115 and lon is None:
            lon = -v
    if lat is None or lon is None:
        lat = lon = None
        dec = [float(x) for x in DECIMAL.findall(line)]
        for v in dec:
            if 36.5 <= v <= 42.5 and lat is None:
                lat = v
            elif -115 <= v <= -108.5 and lon is None:
                lon = v
    if lat is None or lon is None:
        return None
    stripped = DEGMIN.sub(" ", line)
    stripped = DECIMAL.sub(" ", stripped)
    elevs = [int(e) for e in ELEV.findall(stripped)]
    return lat, lon, (elevs[0] if elevs else None)


def parse_name(line):
    m = SITE_ID.match(line)
    sid = m.group(1) if m else ""
    rest = line[m.end():] if m else line
    # name = leading non-numeric words
    name = re.split(r"\s{2,}|\d", rest.strip(), maxsplit=1)[0].strip()
    return sid, name


def main():
    rows, seen = [], set()
    for program, fname in FILES.items():
        text = (REPORTS / fname).read_text(errors="ignore")
        for line in text.splitlines():
            got = parse_line(line)
            if not got:
                continue
            lat, lon, elev = got
            key = (round(lat, 3), round(lon, 3))
            if key in seen:
                continue
            seen.add(key)
            sid, name = parse_name(line)
            rows.append([program, sid, name, round(lat, 5), round(lon, 5), elev])

    # Book Cliffs: names only in the report; approx town coordinates.
    for sid, name, lat, lon in [
        ("Remote", "Emma Park Rd (non-op 2024-25)", 39.775, -110.581),
        ("BC-1", "Price BC", 39.599, -110.810),
        ("BC-2", "Price", 39.606, -110.796),
        ("BC-3", "Wellington East", 39.526, -110.690),
        ("BC-4", "East Carbon", 39.548, -110.415),
        ("BC-5", "Green River", 38.996, -110.160),
    ]:
        rows.append(["book_cliffs", sid, name + " [town-approx]", lat, lon, None])

    out = HERE / "data" / "generators-2024-25.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["program", "site_id", "name", "lat", "lon", "elev_ft"])
        w.writerows(rows)
    by_prog = {}
    for r in rows:
        by_prog[r[0]] = by_prog.get(r[0], 0) + 1
    print(f"wrote {len(rows)} sites -> {out}")
    for p, n in sorted(by_prog.items()):
        print(f"  {p}: {n}")


if __name__ == "__main__":
    main()
