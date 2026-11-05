"""Research-only synchronized block max-statistic; no execution permissions."""
import numpy as np

VERSION='block-max-0.2.1'

def validate(matrix, folds):
    x=np.asarray(matrix,dtype=float);g=np.asarray(folds)
    if x.ndim!=2 or not x.shape[1] or len(g)!=len(x) or not np.isfinite(x).all():
        raise ValueError('Finite aligned daily matrix and fold labels required')
    if len(x)<2 or any(g[i]<g[i-1] for i in range(1,len(g))):raise ValueError('Chronological folds required')
    return x,g

def block_test(matrix,folds,*,block=7,replicates=1999,seed=20261105):
    x,g=validate(matrix,folds)
    if type(block)!=int or block<1 or type(replicates)!=int or replicates<199:raise ValueError('Invalid bootstrap policy')
    groups=[np.flatnonzero(g==k) for k in np.unique(g)]
    if any(len(a)<2*block for a in groups):return {'status':'INSUFFICIENT_SAMPLE','block':block}
    rng=np.random.default_rng(seed);center=x-x.mean(axis=0);means=np.empty((replicates,x.shape[1]))
    # Resample all strategies with identical indices; never bridge fold resets.
    for b in range(replicates):
        idx=[]
        for a in groups:
            starts=rng.integers(0,len(a),size=(len(a)+block-1)//block)
            idx.extend(a[((starts[:,None]+np.arange(block))%len(a)).ravel()[:len(a)]])
        means[b]=center[idx].mean(axis=0)
    se=means.std(axis=0,ddof=1);valid=se>1e-14
    scores=np.divide(means,se,out=np.zeros_like(means),where=valid)
    maximum=np.maximum(0,scores.max(axis=1));observed=np.divide(x.mean(axis=0),se,out=np.zeros_like(se),where=valid)
    adjusted=(1+(maximum[:,None]>=observed).sum(axis=0))/(replicates+1)
    adjusted[~valid]=1
    critical=float(np.quantile(np.abs(scores).max(axis=1),.95,method='higher'))
    lower=x.mean(axis=0)-critical*se;upper=x.mean(axis=0)+critical*se
    # Degenerate vectors cannot earn a passing significance label.
    return dict(status='EXPERIMENTAL_BOOTSTRAP',block=block,replicates=replicates,
        mean=x.mean(axis=0).tolist(),lower=lower.tolist(),upper=upper.tolist(),
        adjusted_p=adjusted.tolist(),eligible=(valid&(lower>0)&(adjusted<=.05)).tolist())

def dependence(matrix):
    x=np.asarray(matrix,float)
    if x.ndim!=2 or len(x)<2 or not np.isfinite(x).all():raise ValueError('Aligned finite observations required')
    centered=x-x.mean(0);norm=np.linalg.norm(centered,axis=0);valid=norm>1e-14
    z=np.divide(centered,norm,out=np.zeros_like(centered),where=valid)
    corr=np.clip(z.T@z,-1,1);parent=list(range(x.shape[1]));duplicates=[]
    def root(a):
        while parent[a]!=a:a=parent[a]
        return a
    for a in range(x.shape[1]):
        for b in range(a):
            same=np.allclose(x[:,a],x[:,b],rtol=0,atol=1e-12)
            if same:duplicates.append([b,a])
            if same or (valid[a] and valid[b] and corr[a,b]>=.95):parent[root(a)]=root(b)
    return dict(correlation=[[float(corr[i,j]) if valid[i] and valid[j] else None for j in range(x.shape[1])] for i in range(x.shape[1])],
        groups=[root(i) for i in range(x.shape[1])],near_duplicates=duplicates,
        interpretation='Dependence clusters, not proof of independent hypotheses')

def assess(matrix,folds,*,replicates=1999):
    x,g=validate(matrix,folds);dep=dependence(x)
    tests=[block_test(x,g,block=b,replicates=replicates) for b in (3,7,14)]
    enough=len(x)>=180 and all(sum(g==k)>=30 for k in np.unique(g))
    stable=np.ones(x.shape[1],bool)
    for test in tests:
        stable &= np.asarray(test.get('eligible',[False]*x.shape[1]),bool)
    # Removing best day is a tail concentration diagnostic, not a replacement test.
    no_best=(x.sum(0)-x.max(0))/(len(x)-1)
    return dict(version=VERSION,status='EXPERIMENTAL' if enough else 'INSUFFICIENT_SAMPLE',
        observations=len(x),tests=tests,dependence=dep,mean_without_best_day=no_best.tolist(),
        stable_candidates=np.flatnonzero(stable & enough).tolist(),statistically_validated=False)
