-- Parameters: snapshot DATE, declared logs_start DATE. Never use future events.
CREATE OR REPLACE TEMP TABLE snapshot_candidates AS
WITH history AS (
 SELECT *, min(transaction_date) OVER (PARTITION BY msno) AS first_observed_transaction,
 row_number() OVER (PARTITION BY msno ORDER BY event_order DESC) AS rn
 FROM transaction_events WHERE transaction_date < $snapshot
)
SELECT msno, $snapshot::DATE AS snapshot, transaction_date AS last_transaction,
 expire_date, same_day_events, payment_method_id, plan_days, list_price, amount_paid,
 auto_renew, is_cancel,
 date_diff('day', first_observed_transaction, $snapshot) AS observed_tenure_days,
 date_diff('day', transaction_date, $snapshot) AS billing_recency_days,
 date_diff('day', $snapshot, expire_date) AS days_to_expiry,
 -- Renewal gap must be < 30; the latest expiry in-month matures 30 days after month-end.
 (last_day($snapshot::DATE) + INTERVAL 30 DAY)::DATE AS cohort_available_at,
 (expire_date + INTERVAL 29 DAY)::DATE AS outcome_deadline
FROM history WHERE rn = 1;
CREATE OR REPLACE TEMP TABLE eligible AS
SELECT * FROM snapshot_candidates
WHERE expire_date >= snapshot
 AND expire_date < snapshot + INTERVAL 1 MONTH AND plan_days > 0;
CREATE OR REPLACE TEMP TABLE features_month AS
WITH listening AS (
 SELECT e.msno,
 count(DISTINCT l.activity_date) FILTER (WHERE l.seconds > 0 AND l.activity_date >= e.snapshot - INTERVAL 28 DAY) AS active_days_28,
 coalesce(sum(l.seconds) FILTER (WHERE l.activity_date >= e.snapshot - INTERVAL 28 DAY), 0) AS seconds_28,
 coalesce(sum(l.seconds) FILTER (WHERE l.activity_date >= e.snapshot - INTERVAL 14 DAY), 0) AS seconds_recent_14,
 coalesce(sum(l.seconds) FILTER (WHERE l.activity_date >= e.snapshot - INTERVAL 28 DAY AND l.activity_date < e.snapshot - INTERVAL 14 DAY), 0) AS seconds_previous_14,
 max(l.activity_date) FILTER (WHERE l.seconds > 0) AS last_activity,
 count(*) FILTER (WHERE l.raw_secs > 86400 AND l.activity_date >= e.snapshot - INTERVAL 28 DAY) AS capped_days_28
 FROM eligible e LEFT JOIN logs l ON e.msno = l.msno AND l.activity_date < e.snapshot
 GROUP BY e.msno
)
SELECT e.* EXCLUDE(same_day_events), l.* EXCLUDE(msno, last_activity),
 seconds_recent_14 - seconds_previous_14 AS seconds_change_14,
 coalesce(date_diff('day', last_activity, e.snapshot), date_diff('day', $logs_start, e.snapshot) + 1) AS days_since_activity,
 (last_activity IS NULL)::INTEGER AS activity_recency_censored,
 ln(1 + seconds_28) AS log_seconds_28,
 ln(1 + seconds_recent_14) - ln(1 + seconds_previous_14) AS log_listening_change,
 CASE WHEN observed_tenure_days < 90 THEN 'Under 90 observed days'
      WHEN observed_tenure_days < 365 THEN '90–364 observed days'
      ELSE '365+ observed days' END AS tenure_band,
 CASE WHEN active_days_28 = 0 THEN '0 days'
      WHEN active_days_28 <= 7 THEN '1–7 days'
      WHEN active_days_28 <= 21 THEN '8–21 days'
      ELSE '22–28 days' END AS engagement_band
FROM eligible e JOIN listening l USING(msno);
