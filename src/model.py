"""Rolling-origin backtest with complete-cohort label availability."""
import json
import hashlib
import math
import warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from sklearn.exceptions import ConvergenceWarning
from xgboost import XGBClassifier
import joblib
from .build import resolve

BILLING_NUM=['plan_days','list_price','amount_paid','observed_tenure_days','billing_recency_days','days_to_expiry','auto_renew','is_cancel']
BEHAVIOR=['active_days_28','log_seconds_28','days_since_activity','activity_recency_censored','log_listening_change']
CATEGORICAL=['payment_method_id']
SPECS={'Billing logistic':('lr',False), 'Listening logistic':('lr',True),
       'Billing XGBoost':('xgb',False), 'Listening XGBoost':('xgb',True)}

def training_at(frame, origin):
    origin=pd.Timestamp(origin)
    return frame.loc[(frame.snapshot < origin) & (frame.cohort_available_at <= origin) & frame.is_churn.notna()].copy()

def pipeline(kind, behavior, parameter, seed):
    numeric=BILLING_NUM+(BEHAVIOR if behavior else [])
    pre=ColumnTransformer([
        ('numeric',Pipeline([('missing',SimpleImputer(strategy='median',add_indicator=True)),('scale',StandardScaler())]),numeric),
        ('category',Pipeline([('missing',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),CATEGORICAL)
    ])
    if kind=='lr':
        classifier=LogisticRegression(C=parameter,max_iter=3000,random_state=seed)
    else:
        classifier=XGBClassifier(n_estimators=160,max_depth=parameter,learning_rate=.04,min_child_weight=10,
           subsample=.85,colsample_bytree=.9,reg_lambda=5,objective='binary:logistic',eval_metric='logloss',
           tree_method='hist',n_jobs=2,random_state=seed)
    return Pipeline([('features',pre),('model',classifier)])

def ranked(frame):
    f=frame.copy()
    f['tie']=f.msno.map(lambda s:hashlib.sha256(str(s).encode()).hexdigest())
    return f.sort_values(['probability','tie'],ascending=[False,True],kind='stable')

def metric(frame):
    y=frame.is_churn.astype(int).to_numpy();p=np.clip(frame.probability.to_numpy(),1e-7,1-1e-7)
    selected=ranked(frame).head(math.ceil(.1*len(frame)))
    captured=int(selected.is_churn.sum()); churners=int(y.sum())
    bins=np.minimum((p*10).astype(int),9)
    ece=sum(np.mean(bins==b)*abs(y[bins==b].mean()-p[bins==b].mean()) for b in np.unique(bins))
    return dict(n=len(y),churners=churners,churn_rate=float(y.mean()),log_loss=float(log_loss(y,p,labels=[0,1])),
        brier=float(brier_score_loss(y,p)),roc_auc=float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,
        mean_predicted=float(p.mean()),ece=float(ece),selected=len(selected),captured=captured,
        recall_at_10=captured/churners if churners else None,precision_at_10=captured/len(selected),
        selected_fraction=len(selected)/len(y))

def calibration(frame):
    f=frame.copy();f['bin']=np.minimum((f.probability*10).astype(int),9)
    g=f.groupby('bin').agg(n=('is_churn','size'),churners=('is_churn','sum'),predicted=('probability','mean'),observed=('is_churn','mean')).reset_index()
    # Descriptive binomial interval; no claim of independence across pooled repeat snapshots.
    z=1.96;n=g.n;v=g.observed;den=1+z*z/n
    center=(v+z*z/(2*n))/den;half=z*np.sqrt(v*(1-v)/n+z*z/(4*n*n))/den
    g['low']=center-half;g['high']=center+half
    return g

def paired_bootstrap(predictions,reps,seed):
    """Resample subscribers jointly across months; fixed fitted predictions, no refitting."""
    rng=np.random.default_rng(seed);records=[]
    for baseline,extended in [('Billing logistic','Listening logistic'),('Billing XGBoost','Listening XGBoost')]:
        a=predictions[predictions.model==baseline]
        b=predictions[predictions.model==extended]
        z=a.merge(b,on=['msno','snapshot','is_churn'],suffixes=('_a','_b'),validate='one_to_one')
        y=z.is_churn.to_numpy()
        for col in ['a','b']:
            p=np.clip(z['probability_'+col],1e-7,1-1e-7)
            z['loss_'+col]=-(y*np.log(p)+(1-y)*np.log(1-p))
        cluster=z.groupby('msno').agg(a=('loss_a','sum'),b=('loss_b','sum'),n=('is_churn','size'))
        sums=(cluster.b-cluster.a).to_numpy();counts=cluster.n.to_numpy();boot=[]
        for _ in range(reps):
            ids=rng.integers(0,len(cluster),size=len(cluster))
            boot.append(float(sums[ids].sum()/counts[ids].sum()))
        records.append({'comparison':extended+' minus '+baseline,'delta_log_loss':float(sums.sum()/counts.sum()),
            'ci_low':float(np.quantile(boot,.025)),'ci_high':float(np.quantile(boot,.975)),
            'subscribers':len(cluster),'snapshots':len(z),'bootstrap_reps':reps,
            'interpretation':'Negative favors listening; subscriber-cluster interval conditional on fitted predictions and observed months.'})
    return pd.DataFrame(records)

def evaluate(frame,cfg):
    out=resolve(cfg['output']);chosen={};tuning=[];splits=[];predictions=[]
    # Drop unknown labels only for historical fitting/evaluation, never for audience scoring.
    for name,(kind,behavior) in SPECS.items():
        for parameter in ([.1,1.] if kind=='lr' else [2,4]):
            fold_losses=[];fold_sizes=[]
            for origin in cfg['validation_months']:
                train=training_at(frame,origin)
                val=frame[(frame.snapshot==origin)&frame.is_churn.notna()]
                if len(train)<cfg['min_training_rows'] or train.is_churn.nunique()<2 or not len(val):
                    raise ValueError(f'Insufficient mature training or validation rows at {origin}')
                estimator=pipeline(kind,behavior,parameter,cfg['seed'])
                with warnings.catch_warnings():
                    warnings.simplefilter('error',ConvergenceWarning)
                    estimator.fit(train,train.is_churn.astype(int))
                loss=log_loss(val.is_churn.astype(int),estimator.predict_proba(val)[:,1],labels=[0,1])
                fold_losses.append(loss);fold_sizes.append(len(val))
                tuning.append(dict(model=name,parameter=parameter,validation_month=origin,n=len(val),log_loss=loss))
            score=float(np.average(fold_losses,weights=fold_sizes))
            if name not in chosen or score<chosen[name]['validation_log_loss']:
                chosen[name]={'parameter':parameter,'validation_log_loss':score}
    for origin in cfg['test_months']:
        train=training_at(frame,origin)
        audience=frame[frame.snapshot==origin]
        if not len(audience) or (audience.label_status=='incomplete_followup').any():
            raise ValueError(f'Cannot evaluate incomplete or empty test cohort {origin}')
        test=audience[audience.is_churn.notna()]
        if len(train)<cfg['min_training_rows'] or train.is_churn.nunique()<2 or not len(test):
            raise ValueError(f'Insufficient training/test data at {origin}')
        splits.append(dict(origin=origin,train_rows=len(train),train_subscribers=train.msno.nunique(),
           latest_train_snapshot=str(train.snapshot.max().date()),latest_label_available=str(train.cohort_available_at.max().date()),
           audience_rows=len(audience),evaluation_rows=len(test),unknown_label_rows=len(audience)-len(test),
           repeat_subscriber_fraction=float(test.msno.isin(train.msno).mean())))
        for name,(kind,behavior) in SPECS.items():
            estimator=pipeline(kind,behavior,chosen[name]['parameter'],cfg['seed'])
            with warnings.catch_warnings():
                warnings.simplefilter('error',ConvergenceWarning)
                estimator.fit(train,train.is_churn.astype(int))
            p=test[['msno','snapshot','is_churn','auto_renew','engagement_band','tenure_band']].copy()
            p['probability']=estimator.predict_proba(test)[:,1];p['model']=name
            predictions.append(p)
            # Local models only; never load an untrusted pickle/joblib model.
            model_dir=out/'models';model_dir.mkdir(exist_ok=True)
            joblib.dump(estimator,model_dir/(origin+'_'+name.replace(' ','_')+'.joblib'))
        p=test[['msno','snapshot','is_churn','auto_renew','engagement_band','tenure_band']].copy()
        p['probability']=float(train.is_churn.mean());p['model']='Historical prevalence';predictions.append(p)
    pred=pd.concat(predictions,ignore_index=True)
    rows=[];curves=[];segments=[]
    for (name,origin),g in pred.groupby(['model','snapshot']):
        row=metric(g);row.update(model=name,snapshot=str(origin.date()));rows.append(row)
        curve=calibration(g);curve['model']=name;curve['snapshot']=str(origin.date());curves.append(curve)
        for auto,h in g.groupby('auto_renew'):
            row=metric(h);row.update(model=name,snapshot=str(origin.date()),auto_renew=int(auto));segments.append(row)
    metrics=pd.DataFrame(rows)
    # Pooled capture sums the monthly top deciles; never rank all months together.
    pooled=[]
    for name,g in metrics.groupby('model'):
        pooled.append(dict(model=name,n=int(g.n.sum()),churners=int(g.churners.sum()),
            log_loss=float(np.average(g.log_loss,weights=g.n)),brier=float(np.average(g.brier,weights=g.n)),
            recall_at_10=float(g.captured.sum()/g.churners.sum()) if g.churners.sum() else None,
            selected=int(g.selected.sum()),captured=int(g.captured.sum())))
    pd.DataFrame(pooled).to_csv(out/'metrics_pooled.csv',index=False)
    metrics.to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(segments).to_csv(out/'metrics_auto_renew.csv',index=False)
    pd.concat(curves).to_csv(out/'calibration.csv',index=False)
    pred.to_csv(out/'predictions.csv',index=False)
    pd.DataFrame(splits).to_csv(out/'split_audit.csv',index=False)
    pd.DataFrame(tuning).to_csv(out/'tuning.csv',index=False)
    paired_bootstrap(pred,cfg['bootstrap_reps'],cfg['seed']).to_csv(out/'behavior_added_value.csv',index=False)
    (out/'model_selection.json').write_text(json.dumps(chosen,indent=2))
    # Freeze the deployment candidate by validation loss, before inspecting test performance.
    candidate=min(chosen,key=lambda name:chosen[name]['validation_log_loss'])
    origin=frame.snapshot.max();train=training_at(frame,origin);audience=frame[frame.snapshot==origin]
    kind,behavior=SPECS[candidate]
    estimator=pipeline(kind,behavior,chosen[candidate]['parameter'],cfg['seed'])
    estimator.fit(train,train.is_churn.astype(int))
    scores=audience[['msno','snapshot','expire_date']].copy();scores['probability']=estimator.predict_proba(audience)[:,1]
    scores=ranked(scores).drop(columns='tie');scores['risk_rank']=np.arange(1,len(scores)+1)
    scores['selected_top_10']=scores.risk_rank<=math.ceil(.1*len(scores));scores.to_csv(out/'latest_audience.csv',index=False)
    (out/'candidate.json').write_text(json.dumps({'model':candidate,'chosen_using':'validation log loss only',
        'score_month':str(origin.date()),'training_rows':len(train),'audience':len(scores),
        'selected':int(scores.selected_top_10.sum())},indent=2))
    return pred,metrics
