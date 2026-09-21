"""Dark 16:9 social card. uv run --with matplotlib python src/make_x_card.py"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parents[1]
RES = HERE / "data" / "results"
SURF, INK, INK2, INK3, GRID = "#1a1a19", "#ffffff", "#c3c2b7", "#8a8983", "#2e2e2c"
BLUE, ORANGE, AQUA = "#3987e5", "#d95926", "#199e70"
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1, "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0,
})
storm = json.loads((RES / "storm-results-2024-25.json").read_text())
v23 = json.loads((RES / "v23-per-generator-results.json").read_text())
sp = json.loads((RES / "seasonal-panel-results.json").read_text()) if (RES / "seasonal-panel-results.json").exists() else None

fig = plt.figure(figsize=(16, 9))
fig.text(0.05, 0.92, "Does Utah's cloud seeding add the 3-15% it claims?", fontsize=32, color=INK, va="top", fontweight="bold")
fig.text(0.05, 0.835, "Same season, same gauges, three research designs. Each one removes a way for operators' storm selection to\n"
         "masquerade as a seeding effect. The naive number is +335%. The selection-robust number is +1.5%, indistinguishable from zero.",
         fontsize=14.5, color=INK2, va="top", linespacing=1.5)

rows = [
    ("naive: seeded vs unseeded storms\n(how programs are evaluated)", 335.0, None, INK3),
    ("near-miss controls, same downwind sector", storm["pooled"]["effect_pct"], storm["pooled"]["ci95"], ORANGE),
    ("plume rotates with each storm's wind,\nper generator (selection-robust)", v23["plume_SEEDED"]["pct_effect"], v23["plume_SEEDED"]["pct_ci95"], BLUE),
]
ax = fig.add_axes([0.33, 0.13, 0.63, 0.42])
y = np.arange(len(rows))[::-1]
ax.axvspan(3, 15, color=AQUA, alpha=0.25, zorder=0)
ax.text(9, -0.75, "claimed 3-15%", ha="center", color=INK2, fontsize=11)
ax.axvline(0, color=INK3, lw=1)
for yi, (lab, est, ci, c) in zip(y, rows):
    if ci:
        ax.plot(ci, [yi, yi], color=c, lw=4, solid_capstyle="round", zorder=2)
        ax.plot(est, yi, "o", ms=16, color=SURF, zorder=3); ax.plot(est, yi, "o", ms=12, color=c, zorder=4)
        ax.text(est, yi + 0.22, f"{est:+.1f}%   [{ci[0]:+.0f}, {ci[1]:+.0f}]", ha="center", va="bottom", color=INK, fontsize=14, fontweight="bold")
    else:
        ax.annotate("", xy=(118, yi), xytext=(60, yi), arrowprops=dict(arrowstyle="-|>", color=c, lw=3))
        ax.text(60, yi + 0.22, f"{est:+.0f}%  (off the chart)", ha="left", va="bottom", color=INK, fontsize=14, fontweight="bold")
ax.set_yticks(y, [r[0] for r in rows], fontsize=13)
ax.set_xlim(-20, 120); ax.set_ylim(-0.95, len(rows) - 0.4)
ax.set_xticks([0, 25, 50, 75, 100]); ax.tick_params(labelsize=12)
ax.set_xlabel("effect on storm-total precipitation at exposed SNOTEL gauges, winter 2024-25 (%)", fontsize=12)
ax.grid(axis="y", visible=False)

tiles = [("generator sites mapped", "181"), ("seeded storm periods", "203"), ("generator-hours", "17,143"), ("SNOTEL gauges", "546")]
if sp:
    p = sp["panel"]; e = sp["imputation_estimator_log_winter_prec"]
    tiles.append((f"{p['winters'][1]-p['winters'][0]+1}-winter seasonal effect", f"{e['overall_pct']:+.1f}%"))
for i, (lab, val) in enumerate(tiles):
    xx = 0.05 + i * 0.185
    fig.text(xx, 0.735, val, fontsize=26, color=INK, va="top", fontweight="bold")
    fig.text(xx, 0.672, lab, fontsize=11.5, color=INK2, va="top")
fig.text(0.05, 0.04, "github.com/bryjudy/seeding-verification   ·   paper, data, code, MIT   ·   all inputs public: Utah DWR reports, NOAA HRRR, USDA SNOTEL", fontsize=11.5, color=INK3)
fig.savefig(HERE / "figures" / "x_card.png", dpi=150)
print("wrote figures/x_card.png")
