"""Bounded CSV/OOXML/JSON import, explicit schema mapping and atomic preview.

No claim of support for every native broker statement layout. Unknown sections,
unsupported transactions and ambiguous duplicates must be resolved by the user.
"""
from __future__ import annotations
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from .portfolio import validate_event, ledger_state

FIELDS = ['date','kind','symbol','quantity','price','amount','fee','currency','source','external_id']
ALIASES = {
 'date':['date','дата','дата операции','дата сделки'],
 'kind':['kind','тип','операция','вид операции','тип операции'],
 'symbol':['symbol','ticker','secid','тикер','код бумаги','код ценной бумаги','isin','код isin','наименование ценной бумаги'],
 'quantity':['quantity','qty','количество','кол-во','количество бумаг'],
 'price':['price','цена','цена сделки','средняя цена','средняя цена покупки'],
 'amount':['amount','сумма','сумма операции'],
 'fee':['fee','комиссия','комиссия брокера'],
 'currency':['currency','валюта','валюта операции'],
 'source':['source','источник','примечание'],
 'external_id':['external_id','id','номер сделки','номер операции','код сделки']}
KINDS = {'deposit':'deposit','пополнение':'deposit','зачисление денежных средств':'deposit',
         'withdrawal':'withdrawal','вывод':'withdrawal','вывод денег':'withdrawal',
         'buy':'buy','покупка':'buy','покупка цб':'buy','sell':'sell','продажа':'sell','продажа цб':'sell',
         'dividend':'dividend','дивиденды':'dividend','дивиденд':'dividend',
         'coupon':'coupon','купон':'coupon'}
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def number(value):
    text = str(value).strip().replace('\u00a0','').replace('\u202f','').replace(' ','')
    if ',' in text and '.' in text: raise ValueError('Неоднозначные разделители числа: '+text)
    try: result = Decimal(text.replace(',','.'))
    except InvalidOperation as exc: raise ValueError('Некорректное число: '+text) from exc
    if not result.is_finite(): raise ValueError('Число должно быть конечным.')
    return float(result)


def quantity(value):
    n = number(value)
    if not n.is_integer(): raise ValueError('Количество должно быть целым числом бумаг, не лотов.')
    return int(n)


def day(value):
    text = str(value).strip()
    for fmt in ['%Y-%m-%d','%d.%m.%Y']:
        try: return datetime.strptime(text,fmt).date().isoformat()
        except ValueError: pass
    raise ValueError('Дата должна иметь формат ГГГГ-ММ-ДД или ДД.ММ.ГГГГ.')


def norm(value): return ' '.join(str(value).strip().lower().split())


def infer_mapping(columns):
    result = {}
    for field in FIELDS:
        candidates = [c for c in columns if norm(c) in ALIASES[field]]
        if len(candidates)==1: result[field]=candidates[0]
    return result


def _xlsx_tables(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        if sum(f.file_size for f in z.infolist())>40_000_000 or len(z.infolist())>500:
            raise ValueError('Слишком большой распакованный XLSX.')
        main = ET.fromstring(z.read('xl/workbook.xml'))
        rel = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']:r.attrib['Target'] for r in rel if r.attrib.get('TargetMode')!='External'}
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        date_styles=set()
        if 'xl/styles.xml' in z.namelist():
            styles=ET.fromstring(z.read('xl/styles.xml'))
            custom={int(f.attrib['numFmtId']):f.attrib.get('formatCode','').lower() for f in styles.findall('s:numFmts/s:numFmt',NS)}
            for i,xf in enumerate(styles.findall('s:cellXfs/s:xf',NS)):
                num=int(xf.attrib.get('numFmtId','0'))
                if num in set(range(14,23))|{27,30,36,45,46,47,50,57} or any(ch in custom.get(num,'') for ch in ['yy','dd']): date_styles.add(i)
        props=main.find('s:workbookPr',NS)
        epoch=datetime(1904,1,1) if props is not None and props.attrib.get('date1904') in {'1','true'} else datetime(1899,12,30)
        result = {}
        for sheet in main.findall('s:sheets/s:sheet',NS):
            rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=targets[rid]
            path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if not path.startswith('xl/'): raise ValueError('Некорректная ссылка листа XLSX.')
            tree=ET.fromstring(z.read(path)); grid=[];cells=0
            for row in tree.findall('s:sheetData/s:row',NS):
                values=[]
                for c in row.findall('s:c',NS):
                    cells+=1
                    if cells>100000: raise ValueError('Слишком много ячеек XLSX.')
                    letters=re.match(r'[A-Z]+',c.attrib.get('r','A1')).group()
                    col=0
                    for letter in letters: col=col*26+ord(letter)-64
                    if col>100: raise ValueError('Не более 100 колонок.')
                    while len(values)<col: values.append('')
                    if c.find('s:f',NS) is not None: value='__FORMULA_UNSUPPORTED__'
                    elif c.attrib.get('t')=='inlineStr': value=''.join(c.find('s:is',NS).itertext())
                    else:
                        node=c.find('s:v',NS);value='' if node is None else node.text or ''
                        if c.attrib.get('t')=='s': value=strings[int(value)]
                        elif c.attrib.get('t')=='e': value='__CELL_ERROR__'
                        elif value and int(c.attrib.get('s','0')) in date_styles:
                            value=(epoch+timedelta(days=float(value))).date().isoformat()
                    values[col-1]=value
                grid.append(values)
                if len(grid)>5100: raise ValueError('Не более 5000 строк плюс заголовки.')
            result[sheet.attrib['name']]=grid
        return result
    except (zipfile.BadZipFile,KeyError,ET.ParseError,IndexError,AttributeError) as exc:
        raise ValueError('Не удалось прочитать таблицы XLSX.') from exc


def read_tables(data, filename):
    if not isinstance(data,bytes) or len(data)>10_000_000: raise ValueError('Файл должен быть не больше 10 МБ.')
    ext=filename.rsplit('.',1)[-1].lower()
    if ext=='xlsx': return _xlsx_tables(data)
    if ext!='csv': raise ValueError('Для таблиц поддерживаются CSV и XLSX. Старый XLS/PDF не распознаётся.')
    try:
        try: text=data.decode('utf-8-sig')
        except UnicodeDecodeError: text=data.decode('cp1251')
    except UnicodeDecodeError as exc:raise ValueError('Нужна кодировка UTF-8 или Windows-1251.') from exc
    try: dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    try:grid=list(csv.reader(io.StringIO(text),dialect))
    except csv.Error as exc:raise ValueError('Не удалось разобрать CSV: '+str(exc)) from exc
    if len(grid)>5100 or any(len(r)>100 for r in grid): raise ValueError('Не более 5000 строк плюс заголовки и 100 колонок.')
    return {'CSV':grid}


def table_rows(grid, header_row=0):
    if not 0<=header_row<len(grid): raise ValueError('Строка заголовка за пределами таблицы.')
    columns=[str(c).strip() for c in grid[header_row]]
    if not columns or any(not c for c in columns) or len(set(columns))!=len(columns):
        raise ValueError('Заголовки должны быть непустыми и уникальными. Выберите строку начала нужной таблицы.')
    rows=[]
    for i,values in enumerate(grid[header_row+1:],header_row+2):
        if not any(str(v).strip() for v in values): continue
        if len(values)>len(columns): raise ValueError(f'Строка {i}: больше значений, чем заголовков.')
        rows.append((i,dict(zip(columns,values+['']*(len(columns)-len(values))))))
    if len(rows)>5000: raise ValueError('Не более 5000 операций.')
    return columns, rows


def economic_key(event):
    keys=['date','kind','symbol','quantity','price','amount','fee','currency','holdings']
    canonical={k:event[k] for k in keys if k in event}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def preview(rows, mapping, filename, data, existing=(), imported_keys=(), *, mode='operations', opening_date=None, opening_cash=0, symbol_map=None):
    """Every nonblank row is shown, including errors. Nothing is saved here."""
    sha=hashlib.sha256(data).hexdigest(); candidates=[];errors=[];warnings=[]
    used=[v for v in mapping.values() if v]
    if len(set(used))!=len(used): raise ValueError('Одна колонка не может заполнять несколько полей.')
    required={'symbol','quantity','price'} if mode=='positions' else {'date','kind'}
    if not required<=set(k for k,v in mapping.items() if v): raise ValueError('Не сопоставлены обязательные колонки: '+', '.join(sorted(required)))
    known=set(imported_keys); seen=set();existing_econ={economic_key(validate_event(e)) for e in existing}
    holdings=[];symbol_map=symbol_map or {}
    for line,row in rows:
        try:
            def get(key,default=''): return str(row.get(mapping.get(key,''),default)).strip()
            raw_symbol=get('symbol')
            symbol=symbol_map.get(raw_symbol,raw_symbol)
            if any(get(k) in {'__FORMULA_UNSUPPORTED__','__CELL_ERROR__'} for k in mapping):
                raise ValueError('Формулы и ошибки ячеек не импортируются. Сохраните проверенные значения.')
            if mode=='positions':
                currency=get('currency','RUB') or 'RUB'
                if currency.upper() not in {'RUB','SUR','RUR','₽'}: raise ValueError('Поддерживаются только рубли.')
                holdings.append({'symbol':symbol,'quantity':quantity(get('quantity')),'price':number(get('price'))})
                continue
            kind=KINDS.get(norm(get('kind')))
            if not kind: raise ValueError('Неизвестная операция: '+get('kind'))
            currency=get('currency','RUB') or 'RUB'
            if currency.upper() not in {'RUB','SUR','RUR','₽'}: raise ValueError('Поддерживаются только рубли.')
            e={'date':day(get('date')), 'kind':kind, 'fee':number(get('fee','0') or '0'), 'currency':'RUB'}
            if kind in {'buy','sell'}: e.update(symbol=symbol,quantity=quantity(get('quantity')),price=number(get('price')))
            else:
                e['amount']=number(get('amount'))
                if kind in {'dividend','coupon'}: e.update(symbol=symbol,source=get('source') or filename)
            e=validate_event(e)
            external=get('external_id')
            # Provider transaction ids are keyed by kind to permit a trade id reused for a separate income record.
            key='alfa:'+e['kind']+':'+e['date']+':'+external if external else 'file:'+sha+':'+str(line)
            if external: e['external_id']=external
            econ=economic_key(e)
            duplicate=key in known or key in seen
            possible=not duplicate and (econ in existing_econ or econ in {c['economic_key'] for c in candidates})
            e.update(import_key=key,import_file=filename)
            candidates.append({'line':line,'event':e,'duplicate':duplicate,'possible_duplicate':possible,'economic_key':econ})
            seen.add(key)
        except (ValueError,KeyError,TypeError,OverflowError) as exc: errors.append({'line':line,'error':str(exc)})
    if mode=='positions':
        try:
            e=validate_event({'kind':'opening','date':str(opening_date),'amount':opening_cash,'holdings':holdings})
            e.update(import_key='opening:'+sha,import_file=filename)
            candidates=[{'line':0,'event':e,'duplicate':e['import_key'] in known,'possible_duplicate':False,'economic_key':economic_key(e)}]
        except (ValueError,KeyError,TypeError) as exc: errors.append({'line':0,'error':str(exc)})
    if any(c['possible_duplicate'] for c in candidates): warnings.append('Есть возможные повторы без надёжного номера операции. Проверьте строки; автоматически они не исключаются.')
    return {'candidates':candidates,'errors':errors,'warnings':warnings,'file_sha256':sha}


def selected_events(result, exclude=(), confirm_possible=False):
    if result['errors']: raise ValueError('Исправьте все ошибки файла перед импортом. Частичный импорт ошибочного отчёта отключён.')
    chosen=[c for c in result['candidates'] if not c['duplicate'] and c['line'] not in exclude]
    if any(c['possible_duplicate'] for c in chosen) and not confirm_possible:
        raise ValueError('Подтвердите возможные повторы или исключите их.')
    events=[c['event'] for c in chosen]
    if not events: raise ValueError('Нет новых выбранных записей.')
    return events


def preview_json(data):
    if len(data)>10_000_000: raise ValueError('Не более 10 МБ.')
    try: events=json.loads(data.decode('utf-8-sig'))
    except (ValueError,UnicodeDecodeError,RecursionError) as exc: raise ValueError('Некорректный JSON журнала.') from exc
    if not isinstance(events,list) or not 1<=len(events)<=5000: raise ValueError('Нужен JSON-массив из 1–5000 событий.')
    return [validate_event(e) for e in events]
