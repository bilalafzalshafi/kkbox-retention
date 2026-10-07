from pathlib import Path
import argparse
import json
from src.build import build,ROOT
from src.model import evaluate
from src.report import report

def main():
    p=argparse.ArgumentParser(description='KKBOX retention analysis using authenticated raw data')
    p.add_argument('--config',type=Path)
    p.add_argument('--report-only',action='store_true')
    args=p.parse_args()
    if args.config:
        cfg=json.loads(args.config.read_text())
    else:
        p.error('Pass --config configs/real.json')
    if not args.report_only:
        print('Building SQL snapshots ('+cfg['mode']+')',flush=True)
        frame=build(cfg)
        print(f'Fitting temporal models on {len(frame):,} snapshots',flush=True)
        evaluate(frame,cfg)
    report(cfg)
    print('Saved '+str(ROOT/cfg['output']),flush=True)

if __name__=='__main__':main()
