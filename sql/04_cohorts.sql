CREATE OR REPLACE TABLE cohorts AS
WITH grouped AS (
 SELECT snapshot, 'engagement' AS dimension, engagement_band AS cohort,
 count(*) AS eligible, count(is_churn) AS labeled,
 count(*) FILTER (WHERE label_status = 'incomplete_followup') AS censored,
 count(*) FILTER (WHERE label_status = 'ambiguous_followup') AS ambiguous,
 count(*) FILTER (WHERE is_churn = 0) AS renewers,
 count(*) FILTER (WHERE is_churn = 1) AS churners
 FROM snapshots GROUP BY snapshot, engagement_band
 UNION ALL
 SELECT snapshot, 'observed_tenure', tenure_band,
 count(*), count(is_churn),
 count(*) FILTER (WHERE label_status = 'incomplete_followup'),
 count(*) FILTER (WHERE label_status = 'ambiguous_followup'),
 count(*) FILTER (WHERE is_churn = 0), count(*) FILTER (WHERE is_churn = 1)
 FROM snapshots GROUP BY snapshot, tenure_band
)
SELECT *, renewers::DOUBLE / nullif(labeled, 0) AS renewal_rate FROM grouped;
