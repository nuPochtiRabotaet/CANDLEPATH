import copy
import pytest
from moex_intelligence.crypto.preferences import DEFAULTS,load,save
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.paper import Paper

def test_persistent_defaults_reset_isolated(tmp_path):
 s=Store(tmp_path/'x.db');p=Paper(s);before=p.state();d=load(s);assert d['intensity']==85
 d.update(glow=False,markers=False,intensity=40);save(s,d);assert load(Store(s.path))==d
 assert p.state()==before;save(s,DEFAULTS);assert load(s)==DEFAULTS

@pytest.mark.parametrize('key,value',[('intensity',86),('intensity',-5),('intensity',True),('glow',1),('width',5),('fast_color','javascript:alert(1)'),('version',2)])
def test_reject_invalid_settings(tmp_path,key,value):
 s=Store(tmp_path/'x.db');d=copy.deepcopy(DEFAULTS);d[key]=value
 with pytest.raises(ValueError):save(s,d)
 assert load(s)==DEFAULTS
