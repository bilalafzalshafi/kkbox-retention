"""SQL-first feature/label construction. All paths resolve from project root."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import importlib.metadata
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def sql(name):
    return (ROOT / 'sql' / name).read_text()

def execute_script(con, text, parameters=None):
    parameters = parameters or {}
    for statement in con.extract_statements(text):
        con.execute(statement.query, {k: parameters[k] for k in statement.named_parameters})

def literal(value):
    return "'" + str(value).replace("'", "''") + "'"

def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p

def validate_config(cfg):
    if cfg['mode'] != 'real':
        raise ValueError('mode must be real')
    if not cfg.get('coverage_confirmed'):
        raise ValueError('Confirm complete date coverage from source documentation; set coverage_confirmed=true only after checking the files. Max dates alone cannot prove completeness.')
    dates = ['transactions_start','observed_through','logs_start','logs_through','snapshot_start','snapshot_end']
    for key in dates:
        dt.date.fromisoformat(cfg[key])
    if cfg['logs_start'] > cfg['snapshot_start'] or cfg['snapshot_start'] > cfg['snapshot_end']:
        raise ValueError('Invalid snapshot/log coverage')
    if pd.Timestamp(cfg['snapshot_start']) - pd.Timedelta(days=28) < pd.Timestamp(cfg['logs_start']):
        raise ValueError('First snapshot requires 28 complete prior listening days')
    if pd.Timestamp(cfg['snapshot_end']) - pd.Timedelta(days=1) > pd.Timestamp(cfg['logs_through']):
        raise ValueError('Last snapshot exceeds listening coverage')
    if cfg['transactions_start'] >= cfg['snapshot_start'] or cfg['observed_through'] < cfg['snapshot_end']:
        raise ValueError('Transaction coverage cannot support requested snapshots')
    for month in [cfg['snapshot_start'], cfg['snapshot_end'], *cfg['validation_months'], *cfg['test_months']]:
        if dt.date.fromisoformat(month).day != 1:
            raise ValueError('Snapshots must be first of month')
    if not cfg['validation_months'] or not cfg['test_months']:
        raise ValueError('Validation and test months required')
    validation_ready = max(pd.Timestamp(m) + pd.offsets.MonthEnd(0) + pd.Timedelta(days=30) for m in cfg['validation_months'])
    if validation_ready > min(pd.Timestamp(m) for m in cfg['test_months']):
        raise ValueError('Validation labels unavailable at first test origin')
    modulus, remainder = cfg['sample_modulus'], cfg['sample_remainder']
    if not isinstance(modulus,int) or modulus < 1 or not 0 <= remainder < modulus:
        raise ValueError('Invalid deterministic subscriber sample')

def raw_view(con, name, paths, cfg):
    paths = [resolve(p) for p in paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError('Missing raw files: ' + ', '.join(missing))
    arr = '[' + ','.join(literal(p) for p in paths) + ']'
    # Same deterministic customer sample in every source and period. Read all history.
    con.execute(f'''CREATE OR REPLACE VIEW {name} AS SELECT *
        FROM read_csv({arr}, header=true, all_varchar=true, union_by_name=true)
        WHERE md5_number_lower(msno) % {cfg['sample_modulus']} = {cfg['sample_remainder']}''')

def build(cfg):
    validate_config(cfg)
    out = resolve(cfg['output']); out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(out / 'retention.duckdb'))
    con.execute(f"SET memory_limit={literal(cfg['memory_limit'])}")
    con.execute('SET threads=4')
    con.execute(f"SET temp_directory={literal(out / 'spill')}")
    for name,key in [('raw_transactions','transactions'),('raw_logs','logs')]:
        raw_view(con,name,cfg[key],cfg)
    con.execute(sql('01_stage.sql'))
    invalid = con.execute('''SELECT count(*) FROM transactions WHERE msno IS NULL
        OR transaction_date IS NULL OR expire_date IS NULL OR auto_renew NOT IN (0,1)
        OR is_cancel NOT IN (0,1) OR auto_renew IS NULL OR is_cancel IS NULL
        OR plan_days IS NULL OR plan_days < 0 OR payment_method_id IS NULL
        OR amount_paid IS NULL OR list_price IS NULL OR NOT isfinite(amount_paid) OR NOT isfinite(list_price)''').fetchone()[0]
    if invalid:
        raise ValueError(f'{invalid} invalid transaction rows; audit source before modeling')
    invalid_logs = con.execute('''SELECT count(*) FROM logs WHERE msno IS NULL OR activity_date IS NULL
        OR raw_secs IS NULL OR NOT isfinite(raw_secs) OR raw_secs < 0''').fetchone()[0]
    if invalid_logs:
        con.execute('''DELETE FROM logs WHERE msno IS NULL OR activity_date IS NULL
            OR raw_secs IS NULL OR NOT isfinite(raw_secs) OR raw_secs < 0''')
    conflicts = con.execute('''SELECT count(*) FROM (SELECT msno, activity_date FROM logs GROUP BY 1,2 HAVING count(*) > 1)''').fetchone()[0]
    if conflicts:
        raise ValueError(f'Logs: {conflicts} conflicting user-days after dropping {invalid_logs} invalid rows. Resolve source overlap before modeling.')
    # Source rows may cover more than the declared observation interval; trim explicitly.
    con.execute('DELETE FROM transactions WHERE transaction_date < ? OR transaction_date > ?', [cfg['transactions_start'],cfg['observed_through']])
    con.execute('DELETE FROM transaction_events WHERE transaction_date < ? OR transaction_date > ?', [cfg['transactions_start'],cfg['observed_through']])
    con.execute('DELETE FROM transaction_days WHERE transaction_date < ? OR transaction_date > ?', [cfg['transactions_start'],cfg['observed_through']])
    con.execute('DELETE FROM logs WHERE activity_date < ? OR activity_date > ?', [cfg['logs_start'],cfg['logs_through']])
    stats = con.execute(f'''SELECT (SELECT count(*) FROM transactions) transactions,
       (SELECT count(*) FROM transaction_events) transaction_events,
       (SELECT count(*) FROM logs) log_rows,
       {invalid_logs} AS invalid_log_rows_dropped,
       (SELECT count(*) FROM logs WHERE raw_secs > 86400) capped_log_rows,
       (SELECT count(*) FROM transaction_days WHERE states > 1) same_day_transaction_days''').df().to_dict('records')[0]
    if not stats['transactions'] or not stats['log_rows']:
        raise ValueError('No data after sampling / date filters')
    audit = []
    for i, month in enumerate(pd.date_range(cfg['snapshot_start'],cfg['snapshot_end'],freq='MS')):
        params = {'snapshot': month.date(), 'logs_start':dt.date.fromisoformat(cfg['logs_start'])}
        execute_script(con, sql('02_snapshot.sql'), params)
        if i == 0:
            con.execute('''CREATE OR REPLACE TABLE snapshots AS SELECT *, NULL::INTEGER is_churn,
                NULL::VARCHAR label_status FROM features_month WHERE false''')
        execute_script(con, sql('03_labels.sql'), {'observed_through':dt.date.fromisoformat(cfg['observed_through'])})
        row = con.execute('''SELECT count(*) AS prior_subscribers,
            count(*) FILTER (WHERE same_day_events > 1) AS latest_state_from_same_day_ordering,
            count(*) FILTER (WHERE expire_date >= snapshot AND expire_date < snapshot + INTERVAL 1 MONTH AND plan_days > 0) AS eligible,
            count(*) FILTER (WHERE NOT (expire_date >= snapshot AND expire_date < snapshot + INTERVAL 1 MONTH AND plan_days > 0)) AS outside_population
            FROM snapshot_candidates''').df().to_dict('records')[0]
        row['snapshot'] = month.strftime('%Y-%m-%d'); audit.append(row)
    con.execute(sql('04_cohorts.sql'))
    frame = con.execute('SELECT * FROM snapshots ORDER BY snapshot, msno').df()
    if frame.duplicated(['msno','snapshot']).any():
        raise AssertionError('Duplicate snapshots')
    if (frame.last_transaction >= frame.snapshot).any():
        raise AssertionError('Future billing feature')
    con.execute(f"COPY snapshots TO {literal(out / 'snapshots.parquet')} (FORMAT PARQUET)")
    con.execute('SELECT * FROM cohorts ORDER BY snapshot, dimension, cohort').df().to_csv(out / 'cohorts.csv',index=False)
    pd.DataFrame(audit).to_csv(out / 'cohort_audit.csv',index=False)
    provenance = {'mode':cfg['mode'],'config':cfg,'source_files':[], 'staging':stats,
        'software': {name:importlib.metadata.version(name) for name in ['duckdb','numpy','pandas','scikit-learn','xgboost','plotly']},
        'code_sha256': {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['src','sql'] for p in sorted((ROOT/folder).glob('*')) if p.suffix in ['.py','.sql']}}
    for file in cfg['transactions'] + cfg['logs']:
        p=resolve(file)
        record = {'path':file,'bytes':p.stat().st_size}
        if cfg.get('hash_sources'):
            with p.open('rb') as f:
                record['sha256'] = hashlib.file_digest(f,'sha256').hexdigest()
        else:
            record['sha256'] = None
            record['hash_skipped_reason'] = 'hash_sources=false avoids a repeated full scan of multi-gigabyte inputs'
        provenance['source_files'].append(record)
    (out / 'provenance.json').write_text(json.dumps(provenance,indent=2,default=str))
    con.close()
    return frame
