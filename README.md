# KKBOX retention project

Status: real-data 1% subscriber-sample analysis completed locally. The reusable SQL and Python pipeline, dashboard, report, audits and proposed intervention plan are in place. No synthetic data or demonstration results are used.

Raw data comes from https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data and remains local under `data/raw/`. Reproduce the current run with `python run.py --config configs/real.json`; regenerate only the dashboard/report with `python run.py --config configs/real.json --report-only`. The default config samples one out of every 100 subscribers by deterministic hash while retaining complete histories for sampled subscribers.

Primary outputs are in `outputs/real/`: `report.md`, `dashboard.html`, cohort and split audits, pooled/monthly metrics, calibration, predictions and the latest scored audience. The implemented monthly target freezes snapshot eligibility from the latest officially ordered pre-snapshot transaction whose scheduled expiry falls in the snapshot month. The outcome then looks forward: later cancellations can shorten the expiry used for the renewal-gap calculation before the first later non-cancellation transaction. Renewal requires gap `< 30`; gap `>= 30` is churn.
