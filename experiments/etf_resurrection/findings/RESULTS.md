# Autonomy-trap results (local campaigns, 300 agents, 34 localities, 16 seeds, day +360)

Effect = continued support minus withdrawn, paired by seed (Wilcoxon). Raw tables: `analysis_*.txt`, `branch_outcomes*.csv`.

## Findings
1. **No learning: support helps modestly** (command +0.042*, forcegen +0.046*, balanced +0.060 n.s., logistics -0.024 n.s.).
2. **With use-it-or-lose-it learning (rate 0.25, reference share 0.9) the command cell flips**
   to -0.076* (16% of seeds positive); balanced -0.070*, logistics -0.070*. Figure: `trap_signflip.png`.
3. **The flip is conditional** (`analysis_robust.txt`): it needs fast learning (>=0.5) or a strict
   self-reliance standard (reference share >=0.95). At rate 0.1 or share <=0.8 the effect is
   null-to-positive. Government control barely moves in any setting: the trap is in partner capability.
4. **Duration does not deepen the trap** (command cell flips at T=90/240/360 with similar size);
   long substitution in the logistics cell drives coverage/army to the floor.
5. **Staggered exit is mostly null**; only keeping the binding channel (command) helps (+0.126 coverage*).
6. **Building the binding capacity (development assistance) rescues logistics-constrained forces**
   (capability +0.28..0.35*, army +0.40..0.48*), but not the command cell under learning.

## Anchoring the learning rate (plausibility, not identification)
In the harness a fully substituted channel's capacity index falls as exp(-rate*(ref-share)/month).
- rate 0.25, share 0: -0.22 per month; ~59% lost in 4 months; floor (0.25) in ~6 months.
- SIGAR 22-22-IP: ANDSF sustainment was contractor-built; within weeks to months of contractor exit
  about 60% of Black Hawks were grounded -> consistent with rate ~0.25 (rate 0.1 gives ~30% lost
  in 4 months; 0.5 gives ~83%).
- RAND MG-1253 (29 cases): effectiveness tracks inputs; no quantitative dependency rate.
Caveat: the SIGAR figure is withdrawal-driven decay, not learning-by-doing proper, so this bounds
the rate to a plausible 0.1-0.5 band rather than identifying it. Conclusions are therefore stated
as a threshold in (rate, standard), with 0.25/0.9 as the central scenario.

## Limits
Single mid-capacity cell per constraint type, 300-agent scale; development dose uncalibrated;
logistics-cell composite near floor (use army/coverage); pre-existing failing test
`test_binding_constraint_assay` untouched.

## Development-dose sweep (learning 0.25; capability, continued minus withdrawn; `analysis_devsweep.txt`)
| dev rate /30d | balanced | command | forcegen | logistics |
|---|---|---|---|---|
| 0.0125 | -0.084 | -0.077* | -0.015 | -0.125 |
| 0.025 | -0.046 | -0.038 | -0.005 | +0.115 |
| 0.05 (earlier run) | see analysis_360 | -0.067* | | +0.28..0.35* |
| 0.1 | +0.061 | -0.029 | -0.013 | +0.334* (army +0.63*) |
| 0.2 | +0.142* (army +0.30*) | -0.022 | -0.013 | +0.062* |
- The rescue is dose-dependent: too little assistance leaves the trap in place (all cells negative at 0.0125);
  the balanced force needs the most (positive only from 0.1, significant at 0.2).
- Logistics peaks near 0.1 and shrinks at 0.2 (the withdrawn branch catches up on its own: diminishing returns).
- Command-constrained forces are never rescued by the development channel at any dose tested: the trap there is robust.
- So the "remedy" claim is a dose threshold, not an arbitrary single-dose artefact; the absolute dose scale is still uncalibrated.

## Fresh-seed confirmation (64 new seeds per cell, 512 worlds, withdrawal day 120; `analysis_confirm64.txt`)
Capability, continued minus withdrawn, day +360 (seeds positive / 64):
| | balanced | command | forcegen | logistics |
|---|---|---|---|---|
| no learning | +0.020 (32) | +0.035 (36) | +0.033 (40) | +0.002 (8) |
| learning 0.25 | **-0.103\*** (20) | **-0.108\*** (8) | -0.011 (29) | -0.028 (8) |
The command-cell sign flip replicates on unseen seeds (+0.035 -> -0.108*, 56% -> 13% of seeds positive);
the balanced cell flip now also significant. Coverage: logistics -0.155*, balanced -0.116*.
