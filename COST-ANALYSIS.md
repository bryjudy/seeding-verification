# What does Utah get for $5M a year? — the seven-season estimate as a distribution (2026-09-26)

**Inputs.** Placebo-corrected per-storm effect from the seven-season wind-rotation design: 600 bootstrap draws, median +2.9 %,
90 % interval [-2.0, 8.5] %, P(effect < 0) = 17%. Seeded share of in-plume winter
precipitation (what fraction of the water fell during seeded storms): 74% in 2024-25, 21% seven-season mean. State claim: 249,600 AF/yr at
≈ $1/AF (Griffith et al. 2009, cited by DWR). The 2012 DWR estimate paired 181,700 AF with a 5.7 % increase, so the current claim implies
≈ 4.38 M AF of target-area runoff; we adopt that baseline. Cost: the $5M annual state appropriation only (one-time $12M capital and
local cost shares excluded — both make the numbers below worse). Runoff is assumed to scale 1:1 with precipitation, as the state's own
figures do; snowmelt runoff elasticity is typically >1, which would scale every AF figure below (and the claim) by the same factor.

**Method.** AF/yr = baseline × seeded share × per-storm effect, evaluated on every bootstrap draw. Cost per acre-foot is reported only
conditional on a positive effect, because it is undefined at zero and meaningless when the program removes water.

| scenario | seeded share | E[AF/yr] | median | 10th–90th pct | P(net water LOSS) | P(< half of claim) | $/AF at E[AF] | $/AF, median (positive draws) | $/AF 10th–90th (positive draws) |
|---|---|---|---|---|---|---|---|---|---|
| 2024-25 seeded share (all programs; primary) | 74% | 95,459 | 92,809 | -30,451 to 217,689 | 17% | 64% | $52 | $44 | $21–$182 |
| 7-season mean seeded share (older seasons cover 2–3 programs → understated; lower bound) | 21% | 26,660 | 25,920 | -8,505 to 60,797 | 17% | 100% | $188 | $157 | $76–$651 |

**State's figure for comparison:** 249,600 AF/yr → $20/AF at $5M.

## Reading
- First, a correction to the state's own arithmetic: 249,600 AF at today's $5M budget is $20/AF, not the ~$1/AF still quoted
  (that figure used 2009-10 costs of $412k). The program is 12× more expensive than when the claim was minted.
- The central estimate is not "no water": the expected gain is on the order of 95k AF/yr, about
  38% of the state's claim, at roughly $52 per acre-foot — 2–3× the state's implied cost, and still
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
