import numpy as np
import pytest
from moex_intelligence.crypto.coliseum_statistics import block_test,dependence,assess

def test_deterministic_blocks_detect_strong_effect_and_duplicates():
    rng=np.random.default_rng(11);a=rng.normal(0,.001,(270,3));a[:,0]+=.004;a[:,1]=a[:,0]
    g=np.repeat([1,2,3],90);r=block_test(a,g,replicates=399)
    assert r==block_test(a,g,replicates=399)
    assert r['eligible'][:2]==[True,True]
    d=dependence(a);assert d['groups'][0]==d['groups'][1] and [0,1] in d['near_duplicates']

def test_null_fwer_monte_carlo_smoke():
    # 30 seeded dependent AR(1) null experiments; uncertainty too large for certification.
    discoveries=0
    for seed in range(30):
        rng=np.random.default_rng(seed);x=rng.normal(size=(270,8))*.001
        for i in range(1,len(x)):x[i]+=.4*x[i-1]
        x[:,1]=x[:,0];r=block_test(x,np.repeat([1,2,3],90),replicates=199,seed=seed)
        discoveries+=any(r['eligible'])
    assert discoveries<=5, discoveries

def test_short_constant_nonfinite_and_fold_order():
    assert assess(np.zeros((24,3)),np.repeat([1,2,3],8))['stable_candidates']==[]
    assert not any(block_test(np.ones((180,2)),np.repeat([1,2,3],60),replicates=199)['eligible'])
    assert dependence(np.zeros((5,2)))['correlation']==[[None,None],[None,None]]
    with pytest.raises(ValueError):assess([[1,float('nan')],[2,3]],[1,1])
    with pytest.raises(ValueError):assess([[1],[2]],[2,1])

def test_strong_signal_stable_and_tail_diagnostic():
    rng=np.random.default_rng(12);x=rng.normal(.01,.001,(270,2));x[0,1]=100
    a=assess(x,np.repeat([1,2,3],90),replicates=199)
    assert 0 in a['stable_candidates']
    assert a['mean_without_best_day'][1]<.02
