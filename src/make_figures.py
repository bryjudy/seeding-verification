"""Render figures/ from data/. uv run --with matplotlib --with pandas --with pyarrow --with numpy python src/make_figures.py"""

import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
DATA, RES, OUT = HERE / "data", HERE / "data" / "results", HERE / "figures"
OUT.mkdir(exist_ok=True)

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2, INK3, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983", "#e8e7e3"
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"], "font.size": 11,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1, "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0,
})


def title(fig, t, sub, width=115):
    fig.text(0.02, 0.965, t, fontsize=15, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.02, 0.915, "\n".join(textwrap.wrap(sub, width)), fontsize=10.5, color=INK2, ha="left", va="top", linespacing=1.4)


def fig_selection_bias():
    storm = json.loads((RES / "storm-results-2024-25.json").read_text())
    v23 = json.loads((RES / "v23-per-generator-results.json").read_text())
    rows = [
        ("Design 1: seeded vs unseeded storms,\nfar controls (how operators evaluate)", 69.0, (-9.9, 220.8), INK3),
        ("   same, Central/Southern program only", 335.0, (None, None), INK3),
        ("Design 2: same-sector near-miss controls", storm["pooled"]["effect_pct"], tuple(storm["pooled"]["ci95"]), ORANGE),
        ("   placebo: seeding windows shifted +10 days", 0.2, (-16.7, 20.7), INK3),
        ("Design 3: wind-rotation, per-generator plumes", v23["plume_SEEDED"]["pct_effect"], tuple(v23["plume_SEEDED"]["pct_ci95"]), BLUE),
        ("   placebo: unseeded storms in-plume", v23["plume_UNSEEDED"]["pct_effect"], tuple(v23["plume_UNSEEDED"]["pct_ci95"]), INK3),
    ]
    fig, ax = plt.subplots(figsize=(11, 6.2))
    fig.subplots_adjust(top=0.80, bottom=0.12, left=0.40, right=0.96)
    title(fig, "The same season, three designs: +335% shrinks to +1.5%",
          "Estimated effect of seeding on storm-total precipitation at exposed SNOTEL stations, Utah winter 2024-25. "
          "Bars are 95% bootstrap CIs over storm events. Each design removes a channel of operator storm selection.")
    y = np.arange(len(rows))[::-1]
    ax.axvspan(3, 15, color=AQUA, alpha=0.12, zorder=0)
    ax.text(9, -0.62, "operators claim 3-15%", ha="center", color=INK2, fontsize=9)
    ax.axvline(0, color=INK3, lw=1, zorder=1)
    for yi, (lab, est, (lo, hi), c) in zip(y, rows):
        if lo is not None:
            ax.plot([lo, hi], [yi, yi], color=c, lw=2.5, solid_capstyle="round", zorder=2)
            ax.text(est, yi + 0.2, f"{est:+.1f}%  [{lo:+.0f}, {hi:+.0f}]", ha="center", va="bottom", color=INK, fontsize=10)
        else:
            ax.annotate("", xy=(238, yi), xytext=(200, yi), arrowprops=dict(arrowstyle="-|>", color=c, lw=2))
            ax.text(198, yi + 0.2, f"{est:+.0f}%, off the chart", ha="right", va="bottom", color=INK, fontsize=10)
        if est < 300:
            ax.plot(est, yi, "o", ms=12, color=SURFACE, zorder=3)
            ax.plot(est, yi, "o", ms=9, color=c, zorder=4)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=10)
    ax.tick_params(axis="y", pad=8)
    ax.set_xlim(-40, 240)
    ax.set_ylim(-0.8, len(rows) - 0.3)
    ax.set_xlabel("effect on storm-total precipitation (%)")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT / "selection_bias_progression.png", dpi=180)
    plt.close(fig)


def fig_map():
    gens = pd.read_csv(DATA / "generators-2024-25.csv")
    st = pd.concat([pd.read_parquet(p) for p in (DATA / ".local_snotel").glob("stations_*.parquet")])
    winds = pd.read_csv(DATA / "storm-winds-2024-25.csv")
    fig, ax = plt.subplots(figsize=(8.5, 9.5))
    fig.subplots_adjust(top=0.86, bottom=0.06, left=0.08, right=0.97)
    title(fig, "181 seeding generators across eight Utah programs",
          "Generator sites for all eight Utah programs, parsed from the 2024-25 DWR/NAWC seasonal reports (no public GIS layer existed). "
          "Arrows: mean 700 hPa wind during that program's seeded storms (HRRR). Gray dots: SNOTEL stations.", width=95)
    ax.plot(st["lon"], st["lat"], "o", ms=3.5, color=INK3, alpha=0.55, zorder=2)
    ax.plot(gens["lon"], gens["lat"], "o", ms=6.5, color=SURFACE, zorder=3)
    ax.plot(gens["lon"], gens["lat"], "o", ms=5, color=ORANGE, zorder=4)
    # Utah outline (approx rectangle with the NE notch)
    ut = [(-114.05, 37.0), (-114.05, 42.0), (-111.05, 42.0), (-111.05, 41.0), (-109.05, 41.0), (-109.05, 37.0), (-114.05, 37.0)]
    ax.plot([p[0] for p in ut], [p[1] for p in ut], color=INK3, lw=1, zorder=1)
    for prog, g in gens.groupby("program"):
        w = winds[winds["program"] == prog]
        if len(w) == 0:
            continue
        u = np.mean(np.sin(np.radians(w["wind_dir_from_deg"] + 180)))
        v = np.mean(np.cos(np.radians(w["wind_dir_from_deg"] + 180)))
        cx, cy = g["lon"].mean(), g["lat"].mean()
        ax.annotate("", xy=(cx + 0.55 * u, cy + 0.45 * v), xytext=(cx, cy),
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2), zorder=5)
        off = {"six_creeks": (-0.75, -0.05), "western_uintas": (0.1, -0.45), "high_uintas": (0.2, 0.2),
               "east_shore": (-0.7, 0.1), "northern_utah": (-0.7, 0.05), "book_cliffs": (0.0, -0.35),
               "central_southern_tooele": (-0.6, -0.3), "cache_valley_uav": (0.3, 0.15)}.get(prog, (-0.1, -0.2))
        ax.text(cx + off[0], cy + off[1], prog.replace("_", " ").replace(" tooele", "").replace(" uav", ""), fontsize=9, color=INK, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.85))
    ax.set_xlim(-114.6, -108.4); ax.set_ylim(36.6, 42.4)
    ax.set_aspect(1 / np.cos(np.radians(39.5)))
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.plot([], [], "o", color=ORANGE, label="seeding generator (181)")
    ax.plot([], [], "o", color=INK3, label="SNOTEL station")
    ax.plot([], [], "-", color=BLUE, lw=2, label="mean seeded-storm wind")
    ax.legend(loc="lower left", frameon=False, fontsize=9.5)
    fig.savefig(OUT / "generators_map.png", dpi=180)
    plt.close(fig)


def fig_seasonal_panel():
    p = RES / "seasonal-panel-results.json"
    if not p.exists():
        print("seasonal panel results missing; skipping")
        return
    r = json.loads(p.read_text())
    est = r["imputation_estimator_log_winter_prec"]
    rows = [("all Utah cohorts (overall)", est["overall_pct"], tuple(est["overall_ci95"]), BLUE)]
    names = {"northern_utah_box_elder_cache": "Northern Utah", "western_uintas": "Western Uintas", "high_uintas_south": "High Uintas",
             "east_salt_lake_wasatch": "East Salt Lake", "east_shore_wasatch": "East Shore", "book_cliffs_tavaputs": "Book Cliffs",
             "utah_other": "2023 expansion, other"}
    for a, d in sorted(est["by_cohort"].items(), key=lambda kv: -kv[1]["n"]):
        rows.append((f"{names.get(a, a)} ({d['first_winter']}→, {d['stations']} stn)", d["pct"], tuple(d["ci95"]), INK3))
    rows.append((f"pre-adoption placebo (8 winters early)", r["placebo_pre8yr_pct"], (None, None), ORANGE))
    fig, ax = plt.subplots(figsize=(11, 6.4))
    fig.subplots_adjust(top=0.80, bottom=0.12, left=0.34, right=0.96)
    pn = r["panel"]
    title(fig, f"{pn['winters'][1] - pn['winters'][0] + 1} winters of snowpack data cannot see the claimed effect",
          f"Seasonal target/control estimate of seeding on Nov-Mar precipitation, {pn['stations']} SNOTEL stations in 7 states, "
          f"{pn['station_winters']:,} station-winters ({pn['winters'][0]}-{pn['winters'][1]}). Station + winter fixed effects fit on "
          f"untreated observations; 95% winter-cluster bootstrap CIs. Green band: the 3-15% operators claim.")
    y = np.arange(len(rows))[::-1]
    ax.axvspan(3, 15, color=AQUA, alpha=0.12, zorder=0)
    ax.axvline(0, color=INK3, lw=1)
    for yi, (lab, e, (lo, hi), c) in zip(y, rows):
        if lo is not None:
            ax.plot([max(lo, -40), min(hi, 40)], [yi, yi], color=c, lw=2.5, solid_capstyle="round", zorder=2)
        ax.plot(e, yi, "o", ms=12, color=SURFACE, zorder=3); ax.plot(e, yi, "o", ms=9, color=c, zorder=4)
        t = f"{e:+.1f}%" + (f"  [{lo:+.0f}, {hi:+.0f}]" if lo is not None else "")
        ax.text(41, yi, t, va="center", color=INK, fontsize=10)
    ax.set_yticks(y, [r_[0] for r_ in rows], fontsize=10)
    ax.set_xlim(-40, 60); ax.set_xticks([-40, -20, 0, 20, 40])
    ax.set_xlabel("effect on winter precipitation (%)")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT / "seasonal_panel.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    fig_selection_bias()
    fig_map()
    fig_seasonal_panel()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
