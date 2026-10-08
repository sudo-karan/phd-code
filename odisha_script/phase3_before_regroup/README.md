# Chance tests run before the regroup: 3 hectare stands with 6 stand types

**These are not the results.** The results are `../odisha_phase3_3_results*.txt`, and the
write-up is `../PHASE3_STATUS.md`.

The four files here are outputs of `odisha_phase3_3_significance.py` run on 2026-10-07, while
the 3 hectare stand files were still PR #40's: the same stand outlines as now, but with **6
stand types** where the final files have 5. The field types are the new ones (and, in
`_ft-allrows`, PR #40's).

| File | Analysis |
|---|---|
| `odisha_phase3_3_results.txt` | primary field types |
| `odisha_phase3_3_results_excl0.txt` | check S1, without the no-tree type |
| `odisha_phase3_3_results_ft-k4.txt` | check S2, four field types |
| `odisha_phase3_3_results_ft-allrows.txt` | check S3, PR #40's field types (this one reproduces PR #40's own results file) |

Their headers call themselves "the PRIMARY analysis" or name their check. That was true of the
options they were run with, not of the stand types: the plan fixes 5 stand types for the
3 hectare stands, so none of these is the planned analysis.

They are kept for two reasons.

1. **They are the only record of 3 hectare labelling on 6 stand types under each analysis.**
   `PHASE3_STATUS.md`, "What the number of stand types does", compares them with the final
   5-type results.
2. **They show that the regroup changed nothing else.** Against the final files, the only rows
   that differ are the 3 hectare labelling rows (the two headline ones and the four by district),
   the labelling rows of the comparison of the two stand sizes, and those tests' places in the
   correction table. Every 10 hectare row and every 3 hectare row that depends only on where the
   stand boundaries are is identical. (The final files also print two "for scale" lines and
   reworded closing sentences, added to the script afterwards, and different run times.)

They cannot be regenerated from the current stand files. The 6-type stand files are in git at
`cff45d9`, the merge of PR #40.
