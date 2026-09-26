"""Water-supply outcome of Utah's seeding program under the seven-season estimate, as a DISTRIBUTION, not a point.
Inputs: bootstrap samples of the placebo-corrected per-storm effect; the state's claimed 249,600 AF/yr at the 2012 DWR
implied baseline (181,700 AF = 5.7% -> the current claim implies ~4.38 M AF of target-area runoff); the seeded share of
in-plume precipitation from the panel; state cost $5M/yr. Outputs COST-ANALYSIS.md + figures/cost_distribution.png."""
import json, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
R = "data/results/multi-season"; eff = np.array(json.load(open(f"{R}/effect_bootstrap_seeded_minus_placebo.json"))["pct_effect_samples"]) / 100
panel = pd.read_parquet(f"{R}/v23-multi-panel.parquet"); panel["p"] = np.exp(panel.y)
# seeded share of precipitation at in-plume stations (what fraction of the winter's water fell during seeded events)
ip = panel[panel.in_plume]; share_by_season = ip.groupby("season").apply(lambda d: d.loc[d.seeded, "p"].sum() / d.p.sum()); s = float(share_by_season.mean()); s_2425 = float(share_by_season["2024-25"])
CLAIM_AF, CLAIM_PCT_2012, AF_2012 = 249_600, 0.057, 181_700
B = CLAIM_AF / CLAIM_PCT_2012                      # implied target-area baseline runoff (AF) if the current claim uses the 2012 percentage
COST = 5_000_000                                    # state annual appropriation (excl. $12M one-time capital and local cost shares)
rows = []
for label, share in [("2024-25 seeded share (all programs; primary)", s_2425), ("7-season mean seeded share (older seasons cover 2–3 programs → understated; lower bound)", s)]:
    af = B * share * eff                            # AF gained (or lost) per year under each bootstrap draw
    pos = af[af > 0]
    rows.append(dict(scenario=label, seeded_share=round(share, 3), af_mean=af.mean(), af_median=np.median(af), af_p10=np.percentile(af, 10), af_p90=np.percentile(af, 90),
                     p_loss=(af < 0).mean(), p_below_half_claim=(af < CLAIM_AF / 2).mean(), cost_per_af_at_mean=COST / af.mean() if af.mean() > 0 else np.inf,
                     cost_per_af_median_cond_pos=COST / np.median(pos), cost_per_af_p10_cond_pos=COST / np.percentile(pos, 90), cost_per_af_p90_cond_pos=COST / np.percentile(pos, 10)))
T = pd.DataFrame(rows)
claim_cost = COST / CLAIM_AF
md = f"""# What does Utah get for $5M a year? — the seven-season estimate as a distribution (2026-09-26)

**Inputs.** Placebo-corrected per-storm effect from the seven-season wind-rotation design: 600 bootstrap draws, median +2.9 %,
90 % interval [{100*np.percentile(eff,5):.1f}, {100*np.percentile(eff,95):.1f}] %, P(effect < 0) = {(eff<0).mean():.0%}. Seeded share of in-plume winter
precipitation (what fraction of the water fell during seeded storms): {s_2425:.0%} in 2024-25, {s:.0%} seven-season mean. State claim: 249,600 AF/yr at
≈ $1/AF (Griffith et al. 2009, cited by DWR). The 2012 DWR estimate paired 181,700 AF with a 5.7 % increase, so the current claim implies
≈ {B/1e6:.2f} M AF of target-area runoff; we adopt that baseline. Cost: the $5M annual state appropriation only (one-time $12M capital and
local cost shares excluded — both make the numbers below worse). Runoff is assumed to scale 1:1 with precipitation, as the state's own
figures do; snowmelt runoff elasticity is typically >1, which would scale every AF figure below (and the claim) by the same factor.

**Method.** AF/yr = baseline × seeded share × per-storm effect, evaluated on every bootstrap draw. Cost per acre-foot is reported only
conditional on a positive effect, because it is undefined at zero and meaningless when the program removes water.

| scenario | seeded share | E[AF/yr] | median | 10th–90th pct | P(net water LOSS) | P(< half of claim) | $/AF at E[AF] | $/AF, median (positive draws) | $/AF 10th–90th (positive draws) |
|---|---|---|---|---|---|---|---|---|---|
""" + "\n".join(f"| {r.scenario} | {r.seeded_share:.0%} | {r.af_mean:,.0f} | {r.af_median:,.0f} | {r.af_p10:,.0f} to {r.af_p90:,.0f} | {r.p_loss:.0%} | {r.p_below_half_claim:.0%} | ${r.cost_per_af_at_mean:,.0f} | ${r.cost_per_af_median_cond_pos:,.0f} | ${r.cost_per_af_p10_cond_pos:,.0f}–${r.cost_per_af_p90_cond_pos:,.0f} |" for r in T.itertuples()) + f"""

**State's figure for comparison:** 249,600 AF/yr → ${claim_cost:,.0f}/AF at $5M.

## Reading
- First, a correction to the state's own arithmetic: 249,600 AF at today's $5M budget is ${claim_cost:,.0f}/AF, not the ~$1/AF still quoted
  (that figure used 2009-10 costs of $412k). The program is 12× more expensive than when the claim was minted.
- The central estimate is not "no water": the expected gain is on the order of {T.af_mean.iloc[0]/1000:,.0f}k AF/yr, about
  {T.af_mean.iloc[0]/CLAIM_AF:.0%} of the state's claim, at roughly ${T.cost_per_af_at_mean.iloc[0]:,.0f} per acre-foot — 2–3× the state's implied cost, and still
  cheaper than most new supply (Bear River development and Lake Powell pipeline studies run to hundreds of dollars per acre-foot).
- But roughly one draw in six has the program *removing* water from the target areas, and about two-thirds of the draws deliver less
  than half the claimed volume. On the 10th-percentile draw the state pays $5M and loses ~30k AF.
- The policy statement this supports: the program is plausibly cheap water and possibly no water; the claimed yield is unsupported;
  the spread between 'loses water' and 'cheap water' is wide enough that a proper evaluation — randomizing a fraction of seedable storms
  to no-seed — would be worth more than a year of the program's budget in decision value.

## Caveats
Baseline runoff is inferred from the state's own 2012 pairing, not measured; the seeded share is from in-plume SNOTEL stations, not
basin-wide; per-storm precipitation effects are translated to runoff 1:1; costs exclude capital and local shares. Every one of these
assumptions is stated so it can be replaced. Code: `src/cost_per_acre_foot.py`.
"""
open("COST-ANALYSIS.md", "w").write(md); print(md[:2400])
fig, ax = plt.subplots(1, 2, figsize=(11, 4)); af = B * s_2425 * eff
ax[0].hist(af / 1000, bins=40, color="#4477aa", alpha=0.85); ax[0].axvline(0, color="k", lw=1); ax[0].axvline(CLAIM_AF / 1000, color="#cc6677", ls="--", label="state claim 249,600 AF"); ax[0].axvline(af.mean() / 1000, color="k", ls=":", label=f"expected {af.mean()/1000:,.0f}k AF")
ax[0].set_xlabel("acre-feet gained (or lost) per year, thousands"); ax[0].set_title(f"Water outcome distribution — P(loss) = {(af<0).mean():.0%}", fontsize=10); ax[0].legend(fontsize=8)
pos = af[af > 0]; ax[1].hist(np.clip(COST / pos, 0, 400), bins=40, color="#44aa77", alpha=0.85); ax[1].axvline(claim_cost, color="#cc6677", ls="--", label=f"state: ${claim_cost:,.0f}/AF"); ax[1].set_xlabel(r"\$ per acre-foot (positive draws only; clipped at \$400)"); ax[1].set_title("Cost per acre-foot, conditional on a gain", fontsize=10); ax[1].legend(fontsize=8)
plt.tight_layout(); fig.savefig("figures/cost_distribution.png", dpi=130); print("figure written")
