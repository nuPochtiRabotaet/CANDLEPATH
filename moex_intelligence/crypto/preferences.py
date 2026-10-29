"""Local UI preferences, isolated from financial state."""
import copy,json,re
DEFAULTS={'version':1,'ribbon':True,'glow':True,'markers':True,'ema':True,'st':False,'volume':True,'entry':True,'sl':True,'tp':True,
          'intensity':85,'width':1,'line_opacity':85,'fast_color':'#31f3a2','slow_color':'#e2c36f'}

def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULTS):raise ValueError('Invalid overlay settings schema')
    if type(value['version']) is not int or value['version']!=1:raise ValueError('Unsupported overlay settings')
    for key in ('ribbon','glow','markers','ema','st','volume','entry','sl','tp'):
        if type(value[key]) is not bool:raise ValueError('Invalid layer flag')
    for key,low,high,step in [('intensity',0,100,5),('width',1,4,1),('line_opacity',20,100,1)]:
        if type(value[key]) is not int or not low<=value[key]<=high or value[key]%step:raise ValueError('Invalid style setting')
    for key in ('fast_color','slow_color'):
        if not isinstance(value[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value[key]):raise ValueError('Invalid color')
    return copy.deepcopy(value)

def load(store):
    with store.connect() as db:row=db.execute('SELECT body FROM ui_preferences WHERE id=?',('overlay-v1',)).fetchone()
    try:return validate(json.loads(row[0])) if row else copy.deepcopy(DEFAULTS)
    except (ValueError,TypeError):return copy.deepcopy(DEFAULTS)

def save(store,value):
    checked=validate(value)
    with store.connect() as db:db.execute('INSERT OR REPLACE INTO ui_preferences VALUES(?,?)',('overlay-v1',json.dumps(checked)))
    return checked
