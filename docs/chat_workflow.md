# Working through the project together

The real-data 1% subscriber-sample run is complete. We can keep interpretation, revisions and explanations in this chat, as with the email project.

Start by reviewing `cohort_audit.csv`, `provenance.json` and the label-status counts. The original and v2 files cover the required history for the configured snapshots. Inspect same-day transaction ordering counts, dropped invalid listening rows and capped-listening counts before broad interpretation. Remember the distinction: snapshot eligibility uses the scheduled expiry frozen from past billing state, while outcome labeling can shorten that expiry after the snapshot when cancellation records precede the first non-cancellation renewal.

Then inspect `split_audit.csv`. A model scored on January 1 can use mature November cohorts but cannot use December outcomes. A February 1 model cannot learn January outcomes. This is the most useful detail to understand and explain in interviews; a chronological split by itself would not guarantee that the labels were available when the model was trained.

Next compare each billing model against its listening-augmented counterpart in `behavior_added_value.csv`. A negative difference in log loss favors adding behavior. Read that alongside reliability curves, Brier scores and monthly top-decile capture, not a single accuracy number. Compare auto-renew and manual-renew segments, acknowledging their denominators. Weak incremental value is a legitimate result and may support a simpler model.

Finish by using `outputs/real/report.md` and `outputs/real/dashboard.html` as the real-data decision memo, retaining the proposal for a randomized intervention. Do not claim that listeners would have stayed if contacted. Numerical claims should come from the held-out real-data run.

Useful files to bring back into chat after a local run are `outputs/real/provenance.json`, `cohort_audit.csv`, `split_audit.csv`, `metrics_pooled.csv`, `metrics_auto_renew.csv`, `behavior_added_value.csv` and `report.md`. Those compact outputs are sufficient for the first interpretation pass; raw listening logs do not need to be copied here.
