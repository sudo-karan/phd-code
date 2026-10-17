# Amendment to PHASE_KEPTLAND_PREDECLARED.md: one more check beside the chance test

Written 17 Oct 2026 by Claude (chat), on Jaskaran's instruction of the same day. It amends
`odisha_script/PHASE_KEPTLAND_PREDECLARED.md` by reference: that file is not edited here (Claude
Code amends it separately for the AlphaEarth arm), and everything it fixes stands. This file adds
one check and changes nothing else: not the primary analysis, not the five scores, not the chance
test, not the Holm correction, not the other checks.

## What scores existed when this was written

- **No score of the re-run stands (`_r9`) exists.** Round 9's Task G, the re-runs and their field
  check, has not started (`docs/handoff/2026-10-17-round9.md`, Status), and the branch holds no
  `_r9` file. This file is committed and pushed before any `_r9` scoring.
- **The rehearsal exists.** The chance test has been run once, as a rehearsal, on the stands from
  before the cache fix (`odisha_script/keptland_scores/keptland_s1desc_chance_rehearsal.txt`,
  commit `f041170`). That run prompted this check: it showed that, without forced landing, the
  labelling mean of a realisation does not always average the same districts as the observed
  score. In 411 of 1,999 realisations Kendujhar's placed plots have fewer than 2 scored plots or
  fewer than 2 field types, and the mean covers three districts instead of four. The check
  answers a question about what the null's labelling mean is made of. It was not chosen from any
  score's value. The rehearsal's labelling score sat at the 40th percentile, and nothing here
  depends on that number.

## The check, declared now

**C1. The labelling mean without Kendujhar, on both sides.**

- **Statistic:** score 4 of the primary analysis, the labelling ARI as the plot-weighted mean of
  the per-district ARIs, computed over Angul, Dhenkanal and Koraput only. Kendujhar's plots are
  left out of this statistic, and only this one.
- **Both sides:** Kendujhar is left out of the observed value and of every realisation of the
  null. The null is the conditional (typed-stand) null of the primary, with the same seed, the
  same realisations and the same join of each placed plot. The three districts' ARIs in each
  realisation are exactly those that enter the primary's mean there. As in the primary, a
  district enters a realisation's mean only when it has at least 2 scored plots of at least 2
  field types there.
- **Plots, field types, join:** as the primary: the primary field types, the 30 m rule, and plots
  with no stand within 30 m left out.
- **Reported:** beside the primary's score 4, in the same results file, with its observed value,
  null median and 5th to 95th percentile, percentile, one-sided p (`(1 + #null >= observed) /
  (1 + n)`) and the number of usable realisations.
- **Not part of the primary:** C1 does not replace score 4, does not enter the Holm correction
  over the five tests, and carries no pass or fail. A difference between C1 and score 4 is read as
  what Kendujhar's 7 plots add to the labelling mean, nothing more.
- **Fixed by name:** the district left out is Kendujhar, whatever the re-run stands show. If
  another district drops out of the labelling mean in some realisations of the re-run, that is
  reported as a count, as the rehearsal reports it, and is not turned into a further check
  afterwards.

## Where it applies

To the primary analysis of the declaration: the four `_keptland_s1desc` runs, and their round 9
re-runs (`_r9`) when those are scored.

**C1 applies to every arm scored under `PHASE_KEPTLAND_PREDECLARED.md`, including the AlphaEarth
arm Claude Code adds in round 9 (Jaskaran, 17 Oct 2026, written before any AlphaEarth arm in
Odisha was configured or scored).**

## How it is run

`odisha_script/odisha_keptland_chance.py`, which writes C1 beside score 4 in the results file. The
rehearsal is re-run with it in a separate commit. That commit states whether the five scores and
their nulls are unchanged, which they must be: C1 is computed from the same realisations.
