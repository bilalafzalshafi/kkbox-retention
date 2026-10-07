-- Monthly version of the reference labeller's renewal-gap rule.
-- Cancellations can shorten the expiry; the first later non-cancellation renews
-- only when its gap from the adjusted expiry is < 30 days.
CREATE OR REPLACE TEMP TABLE labels_month AS
WITH ordered AS (
 SELECT e.msno, e.snapshot, e.expire_date AS frozen_expire, t.transaction_date,
   t.expire_date, t.is_cancel, t.event_order,
   min(t.expire_date) FILTER (WHERE t.is_cancel = 1)
     OVER (PARTITION BY e.msno, e.snapshot ORDER BY t.event_order
       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_cancel_expire
 FROM eligible e LEFT JOIN transaction_events t ON e.msno = t.msno
   AND t.transaction_date >= e.snapshot AND t.transaction_date <= e.outcome_deadline
),
first_renewal AS (
 SELECT msno, snapshot,
   date_diff('day', least(frozen_expire, coalesce(prior_cancel_expire, frozen_expire)), transaction_date) AS renewal_gap,
   row_number() OVER (PARTITION BY msno, snapshot ORDER BY event_order) AS rn
 FROM ordered
 WHERE is_cancel = 0
)
SELECT e.msno, e.snapshot,
 CASE WHEN f.renewal_gap < 30 THEN 0 ELSE 1 END AS is_churn
FROM eligible e LEFT JOIN first_renewal f ON e.msno = f.msno AND e.snapshot = f.snapshot AND f.rn = 1;
INSERT INTO snapshots
SELECT f.*, CASE WHEN f.outcome_deadline <= $observed_through
 THEN l.is_churn ELSE NULL END AS is_churn,
 CASE WHEN f.outcome_deadline > $observed_through THEN 'incomplete_followup'
      ELSE 'observed' END AS label_status
FROM features_month f JOIN labels_month l USING(msno, snapshot);
