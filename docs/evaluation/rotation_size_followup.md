# Follow-up: the false-alarm rate of the rotation null

This is a separate check made by the statistical review. It is not part of
`synthetic_validation.md` and its data sets are not pooled with that file's.

## The answer in short

On 600 fresh generated data sets the rotation null gave false alarms at rates from 0.042 to
0.067 across the twelve statistics, 0.051 on average. A sound test gives 0.05. No statistic is
marked too high. `anosim_stand`, the one statistic marked too high in the main run (0.083 on 300
data sets), gave 0.042 here. So the excess in the main run looks like chance.

## Why it was run

In the main run the rotation null's rates averaged 0.059 and one of twelve was marked too high.
That run could not say whether the excess was real. No data sets were added to it, because that
would be choosing a count by a result. This check was declared before it was run, with its own
seed.

## What was declared before running

- Effect 0 (the map is unrelated to the field data), the rotation null only, 99 relabellings per
  test, the twelve statistics, the same layout and generator parameters as the main run.
- Root seed 20261014 (the main run uses 20261013), data set `k` seeded as in the main run's size
  experiment.
- Rule for reading: a rate is too high only if its whole 95% Wilson interval lies above 0.05.
- 1,000 data sets were declared at first. The count was cut to the first 600 because the machine
  was heavily loaded. The cut was made before any rate was looked at.

## Result

Share of 600 data sets with p <= 0.05. The standard error of a true rate of 0.05 on 600 data sets
is 0.009. The last column is the share with p >= 0.96, the opposite tail, which should also be
near 0.05 if the test is sound.

| statistic | rate | 95% interval | by the declared rule | opposite tail |
|---|---|---|---|---|
| `ari_drawing` | 0.067 | 0.049 to 0.090 | acceptable | 0.047 |
| `ari_labelling` | 0.050 | 0.035 to 0.070 | acceptable | 0.048 |
| `pair_stand` | 0.053 | 0.038 to 0.074 | acceptable | 0.052 |
| `pair_type` | 0.052 | 0.037 to 0.072 | acceptable | 0.055 |
| `mantel_stand` | 0.057 | 0.041 to 0.078 | acceptable | 0.053 |
| `mantel_type` | 0.043 | 0.030 to 0.063 | acceptable | 0.053 |
| `partial_mantel_stand` | 0.050 | 0.035 to 0.070 | acceptable | 0.055 |
| `partial_mantel_type` | 0.045 | 0.031 to 0.065 | acceptable | 0.060 |
| `anosim_stand` | 0.042 | 0.028 to 0.061 | acceptable | 0.052 |
| `anosim_type` | 0.045 | 0.031 to 0.065 | acceptable | 0.052 |
| `permanova_stand` | 0.047 | 0.032 to 0.067 | acceptable | 0.060 |
| `permanova_type` | 0.062 | 0.045 to 0.084 | acceptable | 0.057 |

Average of the twelve: 0.051. Every null started from exactly the stand and type labels the
statistics were observed on, and every test gave a p-value.

**Several tests at once.** In 26.8% of these data sets at least one of the twelve statistics gave
p <= 0.05, although the map knew nothing. Twelve tests read side by side without a correction
give a false alarm about one time in four. This is what Holm's correction is for.

## A second check that gave no rate

A second check was declared with it: the same, with the village forest only 50 m wider than the
hull of its plots (300 m in the main run), 200 data sets, root seed 20261015. The question was
whether the rate rises when the plots can barely be moved. It could not be answered: in all 200
data sets the rotation null could not be drawn (some village's plots found no allowed placement
within the limit on attempts), so no p-value was given. The code stopped and said so, as
designed; it did not drop a village or relax a rule. How the rotation null behaves when the
allowed placements are few but not zero is still not tested.

## How to repeat it

From the repo root, with `scripts/` on the Python path:

```
import evaluation_synthetic_validation as esv
from fmu.evaluation import synthetic
rows = [esv.run_test_dataset(20261014, (1, k), 0.0, 99, ("rotation",),
                             esv.PLOTS_PER_GROUP, synthetic.DEFAULT_PARAMS, False)
        for k in range(600)]
# rate of a statistic s: the share of rows with rows[i]["p"]["rotation"][s] <= 0.05
```

The second check is the same with `dataclasses.replace(synthetic.DEFAULT_PARAMS,
region_buffer=50.0)`, root seed 20261015 and `range(200)`.

Data sets 0 to 402 were computed before the review's two code changes and 403 to 599 after. The
changes alter a statistic by at most its last binary digit and cannot move a p-value.
