# Sources and implementation references

The [official KKBOX competition data page](https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data) is the required source of raw data and its current access terms. The competition data endpoint required authentication during this build. The local files were inspected before running: original listening logs cover 2015-01-01 through 2017-02-28 and v2 listening logs cover 2017-03-01 through 2017-03-31; transaction v2 extends transaction coverage through 2017-03-31.

[Gregory's competition paper](https://arxiv.org/pdf/1802.03396) describes the challenge's renewal-within-30-days concept and prediction framework. This project uses a monthly business population with all prior history, while adopting the supplied official labeller's deterministic same-day ordering and renewal-gap boundary: gap `< 30` renews and gap `>= 30` churns. Results are not directly comparable to leaderboard performance.

Implementation references are [DuckDB CSV loading](https://duckdb.org/docs/stable/data/csv/overview), [scikit-learn preprocessing](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html) and [XGBoost's Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html). Installed versions, source file sizes, optional source hashes and code hashes are recorded in each run's provenance.
