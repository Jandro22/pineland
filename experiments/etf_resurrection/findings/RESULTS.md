# Autonomy-trap findings

**Headline.** If a partner force's capacity grows when it serves itself and fades
when outsiders serve for it (an *assumption* of the experiment), continued support
turns from neutral-to-mildly-helpful into harmful. The harm deepens with the
learning rate, is worst at intermediate support doses, and is reversed only by
very large support or by building the partner's own binding capacity. The
production campaign (66,576 paired worlds) is the primary evidence; the earlier
sections below are the local, smaller-scale runs that motivated and replicated it.

**Read this first:** the production campaign section near the end of this file.
Figures: `learning_response.png`, `dose_valley.png`, `mechanism_displacement.png`,
`production_phase_capability_360.png`. Limits: the learning rate is bounded, not
measured; the reference share and development dose are uncalibrated; the capability
index is constructed; nothing is validated against a real case.

---

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
logistics-cell composite near floor (use army/coverage).

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

## Local phase map across capacity levels (20 cells x 16 seeds x {no learning, 0.25}; 640 worlds; `phase_allcap_summary.csv`)
Capability effect, day +360, learning off -> learning 0.25 (p in parentheses for learning):
- **Command-constrained, all five capacity levels**: +0.086/+0.027/+0.114/+0.014/+0.053 -> -0.121 (p<.001), -0.121 (.001), -0.141 (<.001), -0.029 (n.s.), -0.051 (.011);
  only ~6% of seeds positive at the three weakest capacity levels. The trap is strongest where the partner command is weakest.
- **Balanced**: mostly mixed/null by capacity level (only 0.55 clearly negative, -0.107 n.s.): the pooled balanced effect in the one-cell runs is not capacity-robust.
- **Force-generation**: small positive without learning (+0.04..+0.08), ~0 with learning: erodes toward zero, no flip.
- **Logistics**: noisy, negative at high capacity (-0.12 at 0.80, n.s.).
=> Robust headline: the command-constrained trap holds across the capacity range; other structures are weaker and capacity-dependent.

## Production-scale spot check (1000 agents, 72 localities; command-constrained cap 0.30; 24 fresh seeds x 2; `analysis_prodscale.txt`)
Capability, continued minus withdrawn, day +360: no learning -0.048 (n.s., 11/24 positive); learning 0.25 -0.090* (5/24 positive).
- The learning-induced **harm replicates at production scale** (direction and significance of the learning arm).
- The **sign flip does not**: at this scale the no-learning baseline is already slightly negative, not positive, so the claim
  should be "learning by doing makes continued support harmful for weak-command partners" (harm of ~0.04 further),
  not "support helps then flips". One cell, 24 seeds: indicative, not a full production phase map.

## Production-scale, all four structures (1000 agents, 72 localities; one cell per structure, cap index 1; 16 fresh seeds x 2; `analysis_prod4.txt`)
Capability, continued minus withdrawn, day +360: no learning -> learning 0.25 (seeds positive /16)
| | balanced | command | forcegen | logistics |
|---|---|---|---|---|
| no learning | +0.092 (7) | +0.005 (9) | +0.051 (12) | +0.023 (1) |
| learning 0.25 | **-0.112\*** (2) | **-0.087\*** (3) | -0.078 (6) | 0.000 (0) |
At production scale the learning arm lowers the effect in three of four structures (balanced and command significant,
forcegen same direction); logistics is flat near zero. Together with the 24-seed command spot check (-0.090*) this supports:
**learning by doing turns neutral-to-mildly-helpful support into harm of ~0.08-0.2 capability for balanced and command-weak partners.**

## PRODUCTION CAMPAIGN (ARC, 66,576 paired worlds, 1000 agents, 72 localities, 64 seeds; `analysis_production.txt`, `production_*`)
Composite capability, continued minus withdrawn, day +360, pooled over the 140-cell design (2,240 worlds per structure x variant; * p<0.05):

| learning rate (per 30 d) | balanced | command | forcegen | logistics |
|---|---|---|---|---|
| 0 | +0.002 | +0.019* | +0.013* | -0.006 |
| 0.1 | -0.017* | -0.020* | +0.005 | -0.014* |
| 0.25 | -0.072* | -0.068* | -0.019* | -0.034* |
| 0.5 | -0.085* | -0.079* | -0.036* | -0.052* |
| 1.0 | -0.089* | -0.050* | -0.018* | -0.040* |

1. **A monotone dose-response in learning**, in all four structures: harm deepens with the learning rate and saturates around 0.5.
   Command and force-generation constraints flip from small gains to harm. Only 10-23% of worlds show a positive effect at 0.25-0.5.
2. **The self-reliance standard matters**: reference share 0.75 is benign (balanced +0.018, forcegen +0.019*), 0.95 is harmful in every structure (command -0.097*).
3. **Duration**: with learning 0.25 the harm is present at every withdrawal day (T=90/120/240/360), largest at T=90 in the command cell (-0.094*); no learning gives ~0.
4. **Dose is non-monotone under learning** (the "valley of dependency"): without learning, raising support dose 4x/16x gives +0.03..+0.11 / +0.34..+0.45 capability.
   With learning 0.25: 4x gives -0.206 (balanced), -0.204 (command); 16x recovers to +0.056 / -0.072. Intermediate support is the worst case:
   enough to displace the partner's own production, not enough to replace it. Learning removes 85-100% of the 16x benefit in command, forcegen, balanced.
5. **Development assistance** (5%/30d on the binding channel): without learning +0.03..+0.19 everywhere; with learning only the logistics-constrained force is still
   rescued (+0.082*), balanced is neutral (+0.010), command and forcegen stay negative (-0.027*, -0.015*): the remedy does not undo the trap for command-weak forces.
6. **Staggered exit does not rescue** under learning (all S variants negative in balanced/command/logistics).
Production scale thus confirms the local findings and, with 2,240 worlds per cell, makes the learning dose-response statistically unambiguous.
