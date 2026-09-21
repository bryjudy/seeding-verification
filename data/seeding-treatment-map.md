# Utah Cloud Seeding — Treatment Timeline & Target/Control Map

Compiled 2026-07-17. This is the treatment-assignment backbone for the statistical
analysis. Machine-readable version: `seeding_treatment.json`.

## Sources

- Griffith, Solak & Yorty (NAWC), "30+ Winter Seasons of Operational Cloud Seeding
  in Utah" (AMS paper 138877) — per-area operational history 1974–2007, suspension
  criteria, generator network. https://ams.confex.com/ams/pdfpapers/138877.pdf
- Utah DWR cloud seeding page + 2024-25 seasonal reports list (program areas:
  Book Cliffs/Tavaputs, Cache Valley UAV, East Shore, High Uintas, Northern Utah,
  Six Creeks, Southern & Central Utah, Western Uintas). https://water.utah.gov/cloudseeding/
- 2023 Utah Legislature: $12M one-time + $5M/yr; expansion to ~170 generators
  statewide, remote network.
- NAWC/DWR evaluations: target/control estimates of +5–20% April 1 SWE;
  DWR 2000 assessment ≈ 249,600 acre-ft/yr average, ~$1.02/acre-ft.

## Treatment timeline (winter seasons)

| Area (mountains) | Counties (approx) | Seeded |
|---|---|---|
| Central & Southern Utah (Wasatch Plateau, Tushars, Pahvants, Markagunt, etc.) | Beaver, Emery, Garfield, Iron, Juab, Millard, Piute, Sanpete, Sevier, Washington, Wayne | 1973-74 → present, **suspended 1983-84 through 1986-87** (wet years) |
| Early southern Utah experiment | (southern UT) | 1951–1955 only |
| Northern Utah (Box Elder + Cache mtns) | Box Elder, Cache | 1988-89 → present ("most winters") |
| East Salt Lake County (central Wasatch) | Salt Lake | 1987-88 → 1994-95, then Alta/Snowbird-area program active again by 2007-08 → present |
| Western Uintas | Summit, Wasatch, (Duchesne edge) | 1988-89→1992-93, 1994-95, 2000-01 → present |
| High Uintas (south slopes) | Duchesne, Uintah | 2000-01 → present |
| La Sal Mtns | Grand, San Juan | a few winters (late 70s/early 80s per county matrix) |
| **2023 expansion (new areas)** | | |
| Book Cliffs / Tavaputs | Carbon, Grand, Uintah | ~2023-24 → present |
| East Shore (Wasatch above Davis/Weber) | Davis, Weber, Morgan | ~2023-24 → present |
| Six Creeks (SLC Wasatch) | Salt Lake | ~2023-24 → present |
| Cache Valley (UAV) | Cache | ~2024-25 → present |

⚠️ Exact first seasons of the 2023-expansion areas need confirmation from the
individual DWR seasonal report PDFs (listed on the DWR page) — encoded as
`confidence: "medium"` in the JSON.

## Endogeneity warnings (bake into any analysis)

1. **Suspension criteria**: seeding is SUSPENDED when snowpack is far above average
   (200%/180%/160%/150% of avg on Jan/Feb/Mar/Apr 1) and was suspended statewide
   1983–87 (very wet). Treatment is therefore anti-correlated with natural snow:
   naive seeded-vs-unseeded comparisons are biased *against* finding an effect,
   pre/post designs around 1983-87 are biased in complicated ways. Use controls to
   absorb the weather, and treat suspension years explicitly.
2. **Storm-day operations**: generators only run on seedable storm days; a
   winter-total analysis dilutes per-storm effects (expected winter-scale signal
   from the literature: ~3–15%).
3. **Neighboring-state programs** (must NOT be used as controls):
   - Colorado: San Juans, Grand Mesa, Gunnison, Vail/Summit — long-running.
   - Nevada: DRI programs — Tahoe/Carson, Ruby Mtns, Spring Mtns.
   - Wyoming: Medicine Bow/Sierra Madre + Wind River (pilot 2005-14, operational after).
   - Idaho: Idaho Power — Payette (2003→), Boise/Wood (2008→), Upper Snake (2018→).
   - Arizona: SRP Mogollon Rim programs (historical + recent).
   Candidate cleaner controls: NM ranges (Sangre de Cristo/Jemez — largely unseeded),
   AZ San Francisco Peaks (verify), NV Toiyabe/Toquima (verify), CO Front Range
   north of I-70 (verify), ID Sawtooths outside Idaho Power targets (verify).
   Control validity is per-station and needs the verify pass.

## Analysis designs this map supports

- **Design A — long-run target/control**: central/southern UT stations vs verified
  never-seeded controls, 1979→present, regression of log winter precip / Apr 1 SWE
  on control-region weather + seeding on/off (1983-87 break gives within-target
  off years, with the wet-year caveat).
- **Design B — staggered adoption event study**: areas turning on at known dates
  (1989 N.Utah, 2001 High Uintas, 2023-24 expansion areas) vs not-yet-treated +
  never-treated stations. The 2023 expansion is the cleanest natural experiment
  (40+ yrs pre-period) but has only ~3 post winters so far.
- **Design C — downwind (extra-area)**: stations 50–300 km downwind (E/NE) of
  long-seeded target areas vs similar-distance crosswind stations. This is the
  novel "does Utah seeding change other regions" question; nobody has a modern
  answer.
