"""Standalone, offline HTML scorecard. All results loaded from audited pipeline outputs."""
import html
import json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from .build import resolve

COLORS=['#407f78','#d58550','#6c77af','#c55f78','#959ca5']

def plot(fig):
    fig.update_layout(template='plotly_white',font=dict(family='Arial',color='#233b44'),
       paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
       margin=dict(l=48,r=20,t=35,b=55),height=330,legend=dict(orientation='h',y=-.22),
       colorway=COLORS)
    return fig.to_html(full_html=False,include_plotlyjs=False,config={'displayModeBar':False,'responsive':True})

def table(frame):
    return '<div class="scroll">'+frame.to_html(index=False,border=0,escape=True,float_format=lambda x:f'{x:,.4f}')+'</div>'

def display_cohorts(frame):
    frame = frame.copy()
    if 'ambiguous' in frame.columns and frame['ambiguous'].fillna(0).eq(0).all():
        frame = frame.drop(columns=['ambiguous'])
    return frame

def report(cfg):
    out=resolve(cfg['output'])
    metrics=pd.read_csv(out/'metrics_pooled.csv');monthly=pd.read_csv(out/'metrics.csv')
    cohorts=pd.read_csv(out/'cohorts.csv');curves=pd.read_csv(out/'calibration.csv')
    delta=pd.read_csv(out/'behavior_added_value.csv');audit=pd.read_csv(out/'cohort_audit.csv')
    splits=pd.read_csv(out/'split_audit.csv');candidate=json.loads((out/'candidate.json').read_text())
    provenance=json.loads((out/'provenance.json').read_text())
    status='KKBOX · OBSERVATIONAL BACKTEST'
    description='A monthly churn prediction task with snapshot eligibility frozen from past billing state and outcomes built from cancellation-adjusted renewal gaps. Results describe the audited customer sample and observed periods; intervention effects require randomization.'
    outcome_note='Eligibility uses the scheduled expiry from the latest officially ordered pre-snapshot transaction. Outcomes then look forward: cancellations can shorten that expiry before the first later non-cancellation transaction, and renewal requires the resulting gap to be less than 30 days. A gap of 30 days or more is churn.'
    sections=[]
    for month in sorted(monthly.snapshot.unique()):
        m=monthly[monthly.snapshot==month]
        fig=go.Figure()
        for _,r in m.iterrows():
            fig.add_trace(go.Bar(name=r.model,x=[r.model],y=[r.log_loss],hovertemplate='%{x}<br>Log loss %{y:.4f}<extra></extra>'))
        fig.update_layout(showlegend=False,yaxis_title='Log loss · lower is better',xaxis_tickangle=-15)
        cal=go.Figure();cal.add_trace(go.Scatter(x=[0,1],y=[0,1],name='Perfect calibration',mode='lines',line=dict(color='#aab6bc',dash='dot')))
        for name,g in curves[curves.snapshot==month].groupby('model'):
            cal.add_trace(go.Scatter(x=g.predicted,y=g.observed,mode='lines+markers',name=name,
               customdata=g[['n','churners']].to_numpy(),hovertemplate='Predicted %{x:.1%}<br>Observed %{y:.1%}<br>n=%{customdata[0]} · churners=%{customdata[1]}<extra>%{fullData.name}</extra>'))
        cal.update_xaxes(title='Predicted churn',range=[0,1],tickformat='.0%');cal.update_yaxes(title='Observed churn',range=[0,1],tickformat='.0%')
        g=cohorts[(cohorts.snapshot==month)&(cohorts.dimension=='engagement')].copy()
        order={'0 days':0,'1–7 days':1,'8–21 days':2,'22–28 days':3}
        g['order']=g.cohort.map(order);g=g.sort_values('order')
        eng=go.Figure(go.Bar(x=g.cohort,y=g.renewal_rate,customdata=g[['renewers','labeled']].to_numpy(),
            marker_color='#407f78',hovertemplate='%{x}<br>Renewed %{y:.1%}<br>%{customdata[0]} / %{customdata[1]}<extra></extra>'))
        eng.update_yaxes(range=[0,1],tickformat='.0%',title='Renewers / labeled subscribers');eng.update_xaxes(title='Active listening days in prior 28 days')
        cap=go.Figure(go.Bar(x=m.model,y=m.recall_at_10,customdata=m[['captured','churners','selected']].to_numpy(),
            marker_color='#6c77af',hovertemplate='%{x}<br>Capture %{y:.1%}<br>%{customdata[0]} / %{customdata[1]} churners<br>%{customdata[2]} selected<extra></extra>'))
        cap.update_yaxes(range=[0,1],tickformat='.0%',title='Fraction of eventual churners captured');cap.update_xaxes(tickangle=-15)
        cohort_display = display_cohorts(cohorts[cohorts.snapshot==month].drop(columns=['snapshot']))
        sections.append(f'''<section class="month" data-month="{month}"><div class="grid"><article><h2>Does listening add predictive value?</h2><p>Identical cohort and split for every model.</p>{plot(fig)}</article><article><h2>Can we trust the probabilities?</h2><p>Fixed 10-point probability bins; hover for denominators.</p>{plot(cal)}</article><article><h2>Renewal and engagement</h2><p>Descriptive association; activity does not establish a causal effect.</p>{plot(eng)}</article><article><h2>The highest-risk 10%</h2><p>Capacity is rounded up; score ties use a fixed subscriber hash.</p>{plot(cap)}</article></div><article><h2>Who is in each cohort?</h2>{table(cohort_display)}</article></section>''')
    display=metrics.copy();display['recall_at_10']=display.recall_at_10.map(lambda v:f'{v:.1%}')
    body=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Before the silence · Retention study</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#edf2f1;color:#203943;font:15px/1.6 Arial,sans-serif}}main{{max-width:1260px;margin:auto;padding:42px 28px 70px}}.eyebrow{{letter-spacing:.13em;text-transform:uppercase;font-size:12px;font-weight:bold;color:#4e7372}}h1{{font-size:clamp(32px,5vw,55px);letter-spacing:-.04em;line-height:1.05;margin:14px 0}}h2{{font-size:18px;margin:0 0 5px}}p{{margin:8px 0;color:#536972}}.intro{{max-width:800px}}.notice{{padding:15px 20px;background:#fff1dc;border-left:4px solid #ca884a;margin:28px 0}}.cards,.grid{{display:grid;gap:18px;grid-template-columns:repeat(2,minmax(0,1fr))}}.cards{{grid-template-columns:repeat(4,minmax(0,1fr));margin:24px 0}}article,.card{{background:#fff;border:1px solid #dce5e3;border-radius:12px;padding:22px;min-width:0;margin-bottom:18px}}.card b{{font-size:24px;display:block;line-height:1.4}}.card span{{color:#60747b;font-size:12px}}.toolbar{{display:flex;justify-content:space-between;align-items:center;margin:30px 0 18px}}select{{background:#fff;border:1px solid #9fb7b2;border-radius:7px;padding:10px;font:inherit;color:inherit}}table{{border-collapse:collapse;width:100%;font-size:12px;text-align:left}}th{{background:#eff4f3;color:#44615f;font-weight:600}}th,td{{padding:10px;border-bottom:1px solid #e8eeec;white-space:nowrap;text-align:left}}.scroll{{overflow:auto}}a{{color:#256e64}}footer{{margin-top:24px;font-size:12px;color:#60747b}}.month[hidden]{{display:none}}@media(max-width:800px){{main{{padding:25px 15px}}.grid{{grid-template-columns:1fr}}.cards{{grid-template-columns:repeat(2,1fr)}}article{{padding:15px}}}}</style>
<script>{get_plotlyjs()}</script></head><body><main><div class="eyebrow">A SQL-first retention study</div><h1>Before the silence.</h1><p class="intro">Can listening behavior warn us before subscribers leave? Compare billing information with recent engagement, then test whether outreach helps.</p>
<div class="notice"><strong>{status}</strong><p>{description}</p></div>
<article><h2>Implemented outcome</h2><p>{outcome_note}</p></article>
<div class="cards"><div class="card"><span>Evaluation months</span><b>{len(cfg['test_months'])}</b><span>{' · '.join(cfg['test_months'])}</span></div><div class="card"><span>Held-out subscriber snapshots</span><b>{int(metrics.n.iloc[0]):,}</b><span>Subscribers may recur across months</span></div><div class="card"><span>Audience capacity</span><b>10%</b><span>Ranked separately each month</span></div><div class="card"><span>Source customer sample</span><b>1 / {cfg['sample_modulus']}</b><span>Deterministic hash; all history retained</span></div></div>
<article><h2>The central comparison</h2><p>Negative differences favor adding listening features. Intervals resample subscribers across test months, conditional on the fitted models. They exclude model-training and future-month uncertainty.</p>{table(delta[['comparison','delta_log_loss','ci_low','ci_high','subscribers']])}</article>
<div class="toolbar"><h2>Inspect a held-out month</h2><label>Month <select id="month">{''.join('<option>'+m+'</option>' for m in sorted(monthly.snapshot.unique()))}</select></label></div>{''.join(sections)}
<article><h2>Across held-out months</h2><p>Log loss and Brier score are weighted by cohort size. Capture adds monthly captured churners and divides by all monthly churners.</p>{table(display)}</article>
<article><h2>Could these models have been trained on time?</h2><p>A whole historical monthly cohort becomes usable only after every frozen in-month expiry has passed its last valid renewal day. With the gap &lt; 30 rule, the last valid renewal day is expiry plus 29 days.</p>{table(splits)}</article>
<article><h2>Population audit</h2><p>Same-day billing rows are resolved using the official deterministic ordering, not excluded. Unknown outcomes stay unknown. Observed tenure measures time since the first transaction in the supplied history.</p>{table(audit)}</article>
<article><h2>The decision that prediction cannot make</h2><p>The validation-selected candidate is <strong>{html.escape(candidate['model'])}</strong>. Freeze its audience, randomize subscribers 1:1 to a supportive reminder or usual service, and compare renewal under intention to treat. Risk ranking alone cannot show that contact improves retention.</p><p>The latest scored audience is {candidate['score_month']}: {candidate['selected']:,} selected from {candidate['audience']:,} eligible subscribers. Do not use an unvalidated backtest as a live contact list.</p></article>
<footer>Primary data reference: <a href="https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data">KKBOX challenge</a>. Reproducible definitions, source file sizes, optional hashes, SQL, monthly outputs, and intervention design are in the project package. This monthly business population is not a Kaggle leaderboard reproduction.</footer></main><script>
function chooseMonth(){{const selected=document.getElementById('month').value;document.querySelectorAll('.month').forEach(s=>{{s.hidden=s.dataset.month!==selected;if(!s.hidden)s.querySelectorAll('.plotly-graph-div').forEach(g=>Plotly.Plots.resize(g));}});}}document.getElementById('month').addEventListener('change',chooseMonth);chooseMonth();
</script></body></html>'''
    (out/'dashboard.html').write_text(body)
    txt=f'''# Can listening behavior warn us before subscribers leave?

{status}

{description}

Implemented outcome: {outcome_note}

The implementation completed SQL snapshot construction, complete-cohort temporal training, four billing/listening model comparisons, calibration, monthly top-decile capture, and a subscriber-cluster bootstrap of incremental log loss. Data mode: {cfg['mode']}. No randomized retention effect has been measured.

The validation-selected candidate is {candidate['model']}; the final test months were not used to select it. The default real-data configuration samples one out of every {cfg['sample_modulus']} subscribers by hash and retains all records for each sampled subscriber. Source file sizes, optional hashes and the exact config are in provenance.json.

{metrics.to_string(index=False)}

Incremental behavioral value (negative log-loss difference favors listening):

{delta.to_string(index=False)}

These intervals describe the observed test months conditional on fixed fitted models. Repeated users are resampled as clusters. The result is not a causal effect of listening, and the bootstrap does not quantify future month drift.

All outcome rates use labeled subscriber snapshots as their denominator; cohort tables additionally report eligible, censored, renewal and churn counts. The late March cohort is scored, but its incomplete follow-up is not treated as observed churn. See docs/analysis_plan.md for the snapshot eligibility freeze, cancellation-adjusted outcome definition and timing boundaries.

Interpret findings for this sampled and filtered population; inspect exclusion rates before generalizing.
'''
    (out/'report.md').write_text(txt)
