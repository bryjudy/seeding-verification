"""Parse 'Storm Dates and Number of Generators Used' tables from DWR/NAWC seasonal reports (text dumps in
data/dwr-jennings/annual_txt) for all seasons -> data/seeded-storms-multi.csv (same schema as 2024-25 file)."""
import re, glob, os, pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__)); TXT = f"{ROOT}/data/dwr-jennings/annual_txt"
MONTHS = {m: i for i, m in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"], 1)}
PROG = [("aerial", None), ("northern utah", "northern_utah"), ("western uintas", "western_uintas"), ("six creeks", "six_creeks"), ("east shore", "east_shore")]
def program_of(fn):
    f = fn.lower().replace("_", " ")
    for k, v in PROG:
        if k in f: return v
    return None
def season_of(fn):
    m = re.search(r"(20\d\d)-(20\d\d)", fn); return int(m.group(1)), int(m.group(2))
ROW = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]+\.?\s*\d{1,2}(?:\s*[-–]\s*(?:[A-Za-z]+\.?\s*)?\d{1,2})?)\s+(.*)$")
NUM = re.compile(r"[\d,]*\.?\d+")
def parse_dates(s, y1, y2):
    s = s.replace("–", "-").replace("Dec.", "December").replace("Jan.", "January").replace("Feb.", "February").replace("Mar.", "March").replace("Nov.", "November").replace("Apr.", "April").replace("Oct.", "October")
    m = re.match(r"([A-Za-z]+)\s*(\d{1,2})(?:\s*-\s*(?:([A-Za-z]+)\s*)?(\d{1,2}))?", s.strip())
    if not m: return None
    m1, d1, m2, d2 = m.group(1).lower(), int(m.group(2)), (m.group(3) or m.group(1)).lower(), m.group(4)
    if m1 not in MONTHS or m2 not in MONTHS: return None
    def yr(mon): return y1 if MONTHS[mon] >= 9 else y2
    a = pd.Timestamp(yr(m1), MONTHS[m1], d1); b = pd.Timestamp(yr(m2), MONTHS[m2], int(d2)) if d2 else a
    if b < a: b = a
    return a.date(), b.date()
rows = []
for p in sorted(glob.glob(f"{TXT}/*.txt")):
    fn = os.path.basename(p); prog = program_of(fn); y1, y2 = season_of(fn)
    if not prog: continue
    lines = open(p, errors="replace").read().split("\n")
    # scan for the first run of storm rows numbered 1,2,3,... (>=5 rows) anywhere in the file
    cands = []
    for i, l in enumerate(lines):
        m = ROW.match(l)
        if m: cands.append((i, int(m.group(1)), m.group(2), m.group(3)))
    runs, cur = [], []
    for c in cands:
        if cur and c[1] == cur[-1][1] + 1 and c[0] - cur[-1][0] < 80: cur.append(c)
        elif c[1] == 1: cur = [c]
        else: cur = []
        if len(cur) >= 5 and (not runs or runs[-1] is not cur): runs.append(cur)
    got = 0
    if runs:
        best = max(runs, key=len)
        for i, no, dates, rest in best:
            d = parse_dates(dates, y1, y2)
            if not d: continue
            nums = [float(x.replace(",", "")) for x in NUM.findall(rest)]
            if len(nums) >= 4: n_sites, hours = int(nums[0] + nums[2]), nums[1] + nums[3]
            elif len(nums) == 3: n_sites, hours = int(nums[0]), nums[1] + nums[2]   # sites, manual h, remote h
            elif len(nums) == 2: n_sites, hours = int(nums[0]), nums[1]
            elif len(nums) == 1: n_sites, hours = None, nums[0]
            else: continue   # e.g. "Snowbird only"
            rows.append(dict(season=f"{y1}-{str(y2)[2:]}", program=prog, storm_no=no, date_start=d[0], date_end=d[1], n_sites=n_sites, seeding_hours=hours)); got += 1
    starts = runs
    print(f"{fn[:60]:60s} {prog:15s} storms {got}" + ("" if runs else "  (NO STORM TABLE FOUND)"))
df = pd.DataFrame(rows).drop_duplicates(["season", "program", "storm_no"]).sort_values(["season", "program", "storm_no"])
df.to_csv(f"{ROOT}/data/seeded-storms-multi.csv", index=False)
print("\n", df.groupby(["season", "program"]).agg(storms=("storm_no", "size"), hours=("seeding_hours", "sum")).round(1).to_string())
