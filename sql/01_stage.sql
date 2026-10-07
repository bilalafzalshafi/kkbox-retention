-- Date-only data: transactions on snapshot day are never predictors.
-- Same-day transaction order follows reference/WSDMChurnLabeller.scala:
-- transaction date asc; plan/list/method signature desc; same signature renewal
-- before cancellation; same-signature renewals extend, cancellations shorten.
CREATE OR REPLACE TABLE transactions AS
SELECT DISTINCT msno,
 strptime(transaction_date, '%Y%m%d')::DATE AS transaction_date,
 strptime(membership_expire_date, '%Y%m%d')::DATE AS expire_date,
 payment_method_id::INTEGER AS payment_method_id,
 payment_plan_days::INTEGER AS plan_days,
 plan_list_price::DOUBLE AS list_price,
 actual_amount_paid::DOUBLE AS amount_paid,
 is_auto_renew::INTEGER AS auto_renew,
 is_cancel::INTEGER AS is_cancel,
 plan_list_price || payment_plan_days || payment_method_id AS sort_signature
FROM raw_transactions;
CREATE OR REPLACE TABLE transaction_events AS
SELECT *,
 count(*) OVER (PARTITION BY msno, transaction_date) AS same_day_events,
 row_number() OVER (
   PARTITION BY msno
   ORDER BY transaction_date, sort_signature DESC, is_cancel,
     CASE WHEN is_cancel = 0 THEN expire_date END,
     CASE WHEN is_cancel = 1 THEN expire_date END DESC
 ) AS event_order
FROM transactions;
CREATE OR REPLACE TABLE transaction_days AS
SELECT msno, transaction_date, count(*) AS states
FROM transaction_events GROUP BY msno, transaction_date;
CREATE OR REPLACE TABLE logs AS
SELECT DISTINCT msno, strptime(date, '%Y%m%d')::DATE AS activity_date,
 total_secs::DOUBLE AS raw_secs,
 least(86400.0, total_secs::DOUBLE) AS seconds
FROM raw_logs;
