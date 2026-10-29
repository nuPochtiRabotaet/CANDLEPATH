import asyncio
import io
import json
import sqlite3
import zipfile
import pandas as pd
import pytest
from moex_intelligence.portfolio import PortfolioStore, ConflictError, ledger_state, analyze_portfolio, portfolio_curve
from moex_intelligence.portfolio_service import opening_event, quote_mark, fetch_marks, value_portfolio, advisor_context
from moex_intelligence import portfolio_import as imp

D='2026-01-01'
def deposit(amount=1000):return {'kind':'deposit','date':D,'amount':amount}
def buy(q=5,p=100):return {'kind':'buy','date':D,'symbol':'SBER','quantity':q,'price':p}
def sell(q=2):return {'kind':'sell','date':'2026-01-02','symbol':'SBER','quantity':q,'price':120}
def marks(p=120):return {'SBER':{'price':p,'as_of':'2026-01-03','source':'test'}}


def test_migrate_v04_preserves_records_and_backup(tmp_path):
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY,id TEXT UNIQUE,body TEXT NOT NULL)')
        db.execute('INSERT INTO events(id,body) VALUES (?,?)',('original-id',json.dumps(deposit())))
    store=PortfolioStore(path)
    assert store.load()==[deposit()]
    assert store.bundle()['records'][0]['id']=='original-id'
    with sqlite3.connect(str(path)+'.v04-backup') as db:
        assert db.execute('SELECT id FROM events').fetchone()[0]=='original-id'
        assert 'account_id' not in [r[1] for r in db.execute('PRAGMA table_info(events)')]
    assert PortfolioStore(path).load()==store.load()


def test_corrections_replay_ledger_and_are_not_trades(tmp_path):
    s=PortfolioStore(tmp_path/'p.db');ids=s.append_many([deposit(),buy(),sell()])
    initial=s.bundle()
    with pytest.raises(ValueError,match='cannot sell'):s.correct(ids[1],buy(q=1),expected_revision=initial['revision'])
    assert s.bundle()==initial
    s.correct(ids[1],buy(p=90),expected_revision=initial['revision'])
    state=ledger_state(s.load())
    assert len(s.load())==3 and state['cash']==790 and state['realized_pnl']==60
    assert s.audit()[0]['action']=='correct'
    with pytest.raises(ValueError,match='Insufficient'):s.delete(ids[0],expected_revision=s.bundle()['revision'])
    s.delete(ids[2],expected_revision=s.bundle()['revision'])
    assert ledger_state(s.load())['positions']['SBER']['quantity']==5


def test_revision_guards_and_account_isolation(tmp_path):
    a=PortfolioStore(tmp_path/'p.db');b=PortfolioStore(tmp_path/'p.db')
    old=b.bundle();a.append_many([deposit()])
    with pytest.raises(ConflictError):b.append_many([deposit()],expected_revision=old['revision'])
    other=PortfolioStore(tmp_path/'p.db','future-account');other.append_many([deposit(5)])
    assert len(a.load())==1 and ledger_state(other.load())['cash']==5
    with pytest.raises(ValueError):other.delete(a.bundle()['records'][0]['id'],expected_revision=other.bundle()['revision'])


def test_opening_is_not_a_historical_purchase_or_return():
    event=opening_event(D,[{'symbol':'SBER','quantity':7,'price':100}],300)
    state=ledger_state([event]);r=analyze_portfolio([event],marks(150))
    assert state['cash']==300 and r['equity']==1350
    assert r['total_pnl'] is None and r['unrealized_pnl']==350 and not r['history_complete']
    prices=pd.DataFrame({'SBER':[150,165]},index=pd.date_range(D,periods=2))
    curve,stats=portfolio_curve([event],prices)
    assert curve['daily_return'].iloc[0]==0
    assert stats['time_weighted_return_pct']==pytest.approx(105/1350*100)
    with pytest.raises(ValueError):ledger_state([event,event])
    with pytest.raises(ValueError):ledger_state([deposit(),event])


def csv_preview(data,existing=(),keys=()):
    grid=imp.read_tables(data,'alfa.csv')['CSV'];cols,rows=imp.table_rows(grid)
    return imp.preview(rows,imp.infer_mapping(cols),'alfa.csv',data,existing,keys)


CSV=('Дата;Операция;Тикер;Количество;Цена;Сумма;Комиссия;Номер сделки\n'
     '01.01.2026;Пополнение;;;;1000;0;d1\n'
     '01.01.2026;Покупка;SBER;2;100,50;;1,20;0002\n').encode('cp1251')


def test_csv_russian_decimal_and_transactional_import(tmp_path):
    result=csv_preview(CSV);assert not result['errors']
    events=imp.selected_events(result)
    assert events[1]['price']==100.5 and events[1]['external_id']=='0002'
    assert ledger_state(events)['cash']==pytest.approx(797.8)
    s=PortfolioStore(tmp_path/'p.db');s.append_many(events)
    again=csv_preview(CSV,s.load(),s.imported_keys())
    assert all(c['duplicate'] for c in again['candidates'])
    with pytest.raises(ValueError,match='Нет новых'):imp.selected_events(again)
    # Removing a row is a correction; importing the original file must not revive it.
    s.delete(s.bundle()['records'][1]['id'],expected_revision=s.bundle()['revision'])
    assert csv_preview(CSV,s.load(),s.imported_keys())['candidates'][1]['duplicate']


@pytest.mark.parametrize('row',[
 '01.01.2026;Сплит;SBER;2;100;;0;x',
 '01.01.2026;Покупка;SBER;1,5;100;;0;x',
 '01.01.2026;Пополнение;;;;-100;0;x',
 '01.01.2026;Покупка;SBER;2;nan;;0;x',
 '33.01.2026;Покупка;SBER;2;100;;0;x',
])
def test_bad_report_rows_are_visible_and_block_entire_import(row):
    data=CSV.split(b'\n')[0]+b'\n'+row.encode('cp1251')
    result=csv_preview(data)
    assert result['errors']
    with pytest.raises(ValueError):imp.selected_events(result)


def test_ambiguous_duplicates_require_a_choice_and_exclusion_replays():
    data=b'date,kind,symbol,quantity,price,amount\n2026-01-01,deposit,,,,1000\n2026-01-01,buy,SBER,2,100,\n2026-01-01,buy,SBER,2,100,\n'
    result=csv_preview(data)
    assert result['candidates'][2]['possible_duplicate']
    with pytest.raises(ValueError):imp.selected_events(result)
    assert len(imp.selected_events(result,exclude=[4]))==2
    assert len(imp.selected_events(result,confirm_possible=True))==3
    with pytest.raises(ValueError):ledger_state(imp.selected_events(result,exclude=[2],confirm_possible=True))


def minimal_xlsx(formula=False):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Сделки" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        cells=['date','kind','amount']
        head=''.join(f'<c r="{chr(65+i)}1" t="inlineStr"><is><t>{v}</t></is></c>' for i,v in enumerate(cells))
        last='<f>10*10</f><v>100</v>' if formula else '<v>100</v>'
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">{head}</row><row r="2"><c r="A2" s="1"><v>46023</v></c><c r="B2" t="inlineStr"><is><t>deposit</t></is></c><c r="C2">{last}</c></row></sheetData></worksheet>')
    return buf.getvalue()


def test_xlsx_dates_sheets_and_formula_refusal():
    data=minimal_xlsx();grid=imp.read_tables(data,'alfa.xlsx')['Сделки'];cols,rows=imp.table_rows(grid)
    assert rows[0][1]['date']=='2026-01-01'
    r=imp.preview(rows,imp.infer_mapping(cols),'alfa.xlsx',data)
    assert imp.selected_events(r)[0]['amount']==100
    bad=minimal_xlsx(True);cols,rows=imp.table_rows(imp.read_tables(bad,'alfa.xlsx')['Сделки'])
    assert imp.preview(rows,imp.infer_mapping(cols),'alfa.xlsx',bad)['errors']


def test_opening_position_import_and_json_restore():
    data='Тикер;Количество;Средняя цена\nSBER;7;100,5\n'.encode()
    cols,rows=imp.table_rows(imp.read_tables(data,'p.csv')['CSV'])
    r=imp.preview(rows,imp.infer_mapping(cols),'p.csv',data,mode='positions',opening_date=D,opening_cash=50)
    event=imp.selected_events(r)[0]
    assert event['kind']=='opening' and event['holdings'][0]['quantity']==7
    assert ledger_state(imp.preview_json(json.dumps([event]).encode()))['cash']==50


def quote(bond=False):
    return {'instrument':{'name':'Test','asset_type':'bond' if bond else 'equity','currency':'SUR'},
            'currency':'SUR','security':{'FACEVALUE':1000,'ACCRUEDINT':12,'FACEUNIT':'SUR'},'marketdata':{},
            'last_price':95 if bond else 120,'source':'MOEX fixture','retrieved_at_utc':'2026-01-03T10:00:00Z'}


def test_dirty_bond_marks_and_no_substitute_for_missing_last_or_fx():
    assert quote_mark(quote(True))['price']==962
    for field,value in [('last_price',None),('currency','USD')]:
        q=quote();q[field]=value
        with pytest.raises(ValueError):quote_mark(q)
    q=quote(True);del q['security']['ACCRUEDINT']
    with pytest.raises(ValueError):quote_mark(q)
    q=quote(True);q['security']['FACEUNIT']='USD'
    with pytest.raises(ValueError):quote_mark(q)


def test_partial_market_failure_hides_total_and_context():
    class Engine:
        async def research_quote(self,symbol):
            if symbol=='MISSING':raise ValueError('no quote')
            return quote()
    market=asyncio.run(fetch_marks(['SBER','MISSING'],Engine()))
    events=[deposit(),buy(),{'kind':'buy','date':D,'symbol':'MISSING','quantity':1,'price':100}]
    result=value_portfolio(events,market)
    assert result['snapshot'] is None and 'MISSING' in result['errors']
    assert advisor_context(result['snapshot'],'SBER') is None
    ready=value_portfolio([deposit(),buy()],{'marks':marks(),'errors':{}})
    assert advisor_context(ready['snapshot'],'SBER')=={'equity':1100.,'cash':500.,'asset_value':600.,'funding':'existing_cash'}


def test_opening_and_same_day_deposit_do_not_double_count_flow():
    events=[opening_event(D,[{'symbol':'SBER','quantity':2,'price':50}],100),deposit(500)]
    prices=pd.DataFrame({'SBER':[100.,100.]},index=pd.date_range(D,periods=2))
    curve,stats=portfolio_curve(events,prices)
    assert stats['time_weighted_return_pct']==0
    assert curve['equity'].iloc[0]==800 and curve['external_flow'].iloc[0]==800


def test_large_csv_cell_is_a_validation_error_not_an_uncaught_parser_crash():
    with pytest.raises(ValueError):imp.read_tables(b'column\n'+b'x'*200000,'bad.csv')


async def test_price_refresh_invalidates_only_quote_cache():
    from moex_intelligence.data import DataEngine
    import time
    engine=DataEngine()
    engine._cache={('quote','SBER','TQBR','shares'):(time.monotonic(),{'a':1}),
                   ('history','SBER','2026-01-01','2026-01-02','TQBR','shares'):(time.monotonic(),{'a':2})}
    engine.clear_quotes(['SBER'])
    assert len(engine._cache)==1 and next(iter(engine._cache))[0]=='history'


async def test_identifier_resolution_uses_isin_or_exact_name_without_guessing():
    from moex_intelligence.portfolio_service import resolve_symbols
    class Engine:
        async def describe(self,symbol):
            if symbol!='SBER':raise ValueError('unknown')
            return {'symbol':'SBER','name':'Сбербанк','asset_type':'equity'}
        async def search(self,q,limit):
            return {'results':[{'secid':'SBER','isin':'RU0009029540','shortname':'Сбербанк'},
                              {'secid':'SBERP','isin':'RU0009029557','shortname':'Сбербанк-п'}]}
    r=await resolve_symbols(['RU0009029540','Сбербанк','Сбер'],Engine())
    assert r['resolved']['RU0009029540']['symbol']=='SBER'
    assert r['resolved']['Сбербанк']['symbol']=='SBER'
    assert 'Сбер' in r['errors']
    raw='date,kind,isin,quantity,price\n2026-01-01,buy,RU0009029540,7,100\n'.encode()
    cols,rows=imp.table_rows(imp.read_tables(raw,'a.csv')['CSV'])
    preview=imp.preview(rows,imp.infer_mapping(cols),'a.csv',raw,symbol_map={'RU0009029540':'SBER'})
    assert imp.selected_events(preview)[0]['symbol']=='SBER'


async def test_closed_market_uses_explicitly_dated_close_never_cost_or_prevprice():
    class Closed:
        async def research_quote(self,s):
            q=quote();q['last_price']=None;q['security']['PREVPRICE']=9999
            return q
        async def frame(self,*args):
            return pd.DataFrame({'CLOSE':[123.]},index=pd.to_datetime(['2026-01-02'])), {
                'symbol':'SBER','name':'Sber','asset_type':'equity','currency':'SUR','source':'dated real history fixture','retrieved_at_utc':'2026-01-03T12:00:00Z'}
    r=await fetch_marks(['SBER'],Closed())
    assert r['marks']['SBER']['price']==123
    assert r['marks']['SBER']['observed_as_of']=='2026-01-02'
    assert 'не текущая котировка' in r['marks']['SBER']['valuation_basis']


async def test_bond_historical_fallback_requires_dated_accrued_interest():
    class Closed:
        async def research_quote(self,s):
            q=quote(True);q['last_price']=None
            return q
        async def frame(self,*args):
            return pd.DataFrame({'CLOSE':[95.],'FACEVALUE':[1000.]},index=pd.to_datetime(['2026-01-02'])), {
                'symbol':'BOND','name':'Bond','asset_type':'bond','currency':'SUR','source':'history','retrieved_at_utc':'2026-01-03T12:00:00Z'}
    r=await fetch_marks(['BOND'],Closed())
    assert not r['marks'] and 'BOND' in r['errors']
