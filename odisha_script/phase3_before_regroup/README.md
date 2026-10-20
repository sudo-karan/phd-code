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
2. **They show that the regroup changed nothing else.** Against the final files, the only result
   rows that differ are the 3 hectare labelling rows (the two headline ones, the four by district
   and the row under the unconditional null), the labelling rows of the comparison of the two
   stand sizes, those two tests' p-values in the correction table and their places in it (and, in
   `_ft-allrows`, the Holm p of 3 hectare labelling, 1.000 here and 0.477 in the final file), and
   the 3 hectare percentile in the closing "Labelling sits at pctile" sentence. Every 10 hectare
   row and every 3 hectare row that depends only on where the stand boundaries are is identical.

   The other lines that differ are not results. Since 19 Oct 2026 (round 13, review C29) this is
   the full list, from `diff` of each file here against the final file of the same name as
   committed in `a4a29b9`:
   - the two "for scale (not a test)" lines, which the final files print and these do not (added
     to the script afterwards);
   - the header of the per-district rows, twice in each file (10 and 3 hectares): here
     "(descriptive: each district is 1-12 villages)", in the final files "(descriptive, not
     tests: each district is 1-8 villages)";
   - two closing sentences, reworded: "indistinguishable from a randomly placed stand map"
     became "inside the null's central 90%, so this test cannot tell it from a randomly placed
     stand map", and "neither ceiling groups or labels" became "neither ceiling can be SHOWN to
     group or label";
   - in `_excl0` only, "1 of the 20 villages in the AOIs hold only excluded plots" became
     "holds";
   - the two run-time lines, `[10 ha] rotation nulls: ...` and `[3 ha] rotation nulls: ...`:
     here they carry the seconds each null took; the final files no longer do (`a4a29b9`).

   `diff` marks 42 lines (`<` or `>`) in each file, 44 in `_excl0`; every one is in one of the
   lists above.

They cannot be regenerated from the current stand files. The 6-type stand files are in git at
`cff45d9`, the merge of PR #40.
