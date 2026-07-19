# seeding-verification

**Storm-Level Independent Verification of Operational Cloud Seeding: Evidence
from Utah's 2024–25 Winter Season** — paper, data, and fully reproducible
analysis code. Every input is public (Utah DWR seasonal reports, NOAA HRRR on
AWS Open Data, USDA NRCS SNOTEL); the full pipeline runs on a laptop.

📄 Paper: [`paper/seeding-verification-2026.pdf`](paper/seeding-verification-2026.pdf)

## Headline results (winter 2024-25)

| Design | Effect on storm-total precip | 95% CI |
|---|---|---|
| 1. Seeded vs unseeded storms, far controls (naive) | +69% | [−10, +221] |
| 2. Same-sector near-miss controls | +24.2% | [+3.7, +49.7] |
| — placebo (seeding windows shifted +10 days) | +0.2% | [−16.7, +20.7] |
| 3. **Wind-rotation, per-generator plumes (most robust)** | **+1.5%** | **[−9.6, +13.1]** |
| — built-in placebo (unseeded events) | −8.4% | [−26.8, +10.3] |

The progression +335% (largest program, naive) → +24% → +1.5% measures how
much of a naive "seeding effect" is **operator storm selection** — storms are
seeded exactly when conditions favor the targets. The most selection-robust
design finds a small positive point estimate consistent with both the physical
literature (3–15%) and zero; per-storm effects >15–20% are excluded. One
season cannot resolve further; 4–9 seasons of operations records would.

## Datasets released (new, machine-readable)

| File | Contents |
|---|---|
| `data/generators-2024-25.csv` | 181 seeding generator sites w/ coordinates, all 8 Utah programs (parsed from DWR/NAWC report PDFs; no public GIS layer existed) |
| `data/seeded-storms-2024-25.csv` | 203 seeded storm periods: dates, sites used, generator-hours (17,143 hrs total, 7 ground programs) |
| `data/storm-winds-2024-25.csv` | Per seeded storm: mean 700hPa wind at the program's generator network (HRRR) |
| `data/event-winds-2024-25.csv` | Same, for every detected precipitation event (incl. unseeded) |
| `data/results/` | All estimation outputs (JSON) + per-event panel |
| `data/reports-2024-25/` | Text extracts of the source DWR seasonal reports (provenance) |

## Reproduce

Requires [uv](https://docs.astral.sh/uv/). SNOTEL data (~10 min first run) and
HRRR wind extraction (~30 min first run) are pulled from public APIs and
cached locally.

```bash
# 1. (Re)build generator sites from the report text extracts
uv run --with numpy python src/parse_generators.py

# 2. Per-storm 700hPa winds from the HRRR archive (byte-range GRIB2 + eccodes)
uv run --with eccodes --with numpy --with requests python src/fetch_storm_winds.py

# 3. Designs 1-2 (+ pooled, placebo): near-miss storm-level analysis
uv run --with pandas --with pyarrow --with numpy --with requests \
    python src/run_storm_analysis.py

# 4. Design 3: wind-rotation with per-generator plume geometry
uv run --with pandas --with pyarrow --with numpy --with requests \
    python src/v23_per_generator.py
```

Build the paper: `cd paper && tectonic main.tex`.

## Method in one paragraph

AgI plumes travel downwind, so a station's exposure changes storm-by-storm
with each storm's own wind. Design 3 estimates
`log(precip) ~ station FE + event FE + smooth wind-alignment score +
in-plume×seeded + in-plume×unseeded`, where in-plume means some generator lies
5–45 km upwind within ±40° of that event's HRRR wind. The unseeded in-plume
term is a built-in placebo (no AgI released) and must be zero. Operators
choose *when* to seed, but they cannot rotate a precipitation enhancement
around their generators in step with the wind — which is why this design
resists the selection bias that inflates conventional evaluations.

## License

MIT for code. Constructed datasets are derived from U.S. public-domain federal
data and Utah state public records; cite the paper if you use them.

## Citation

> Judy, B. (2026). Storm-Level Independent Verification of Operational Cloud
> Seeding: Evidence from Utah's 2024–25 Winter Season.
