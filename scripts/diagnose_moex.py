"""Bounded, read-only MOEX diagnostics. Never prints proxy URLs or credentials."""
from __future__ import annotations
import argparse,asyncio,json,os,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import httpx

HOST='iss.moex.com';URL='https://iss.moex.com/iss.json?iss.meta=off'


def probe_process(code,timeout):
    try:
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=timeout)
        if result.returncode:return {'passed':False,'error_type':'ProbeFailure','detail':result.stdout.strip()[:500]}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:return {'passed':False,'error_type':'Timeout','detail':f'Не завершено за {timeout} секунд.'}
    except (ValueError,OSError) as exc:return {'passed':False,'error_type':type(exc).__name__}


def diagnostics():
    dns=probe_process("import socket,json\ntry:\n socket.getaddrinfo('iss.moex.com',443);print(json.dumps({'passed':True}))\nexcept Exception as e:print(json.dumps({'passed':False,'error_type':type(e).__name__,'errno':getattr(e,'errno',None)}))",4)
    tls=probe_process("import socket,ssl,json\ntry:\n s=socket.create_connection(('iss.moex.com',443),timeout=3)\n with ssl.create_default_context().wrap_socket(s,server_hostname='iss.moex.com') as t:print(json.dumps({'passed':True,'version':t.version()}))\nexcept Exception as e:print(json.dumps({'passed':False,'error_type':type(e).__name__,'errno':getattr(e,'errno',None)}))",5)
    request=probe_process("import httpx,json\ntry:\n r=httpx.get('https://iss.moex.com/iss.json?iss.meta=off',timeout=5,follow_redirects=False);r.raise_for_status();body=r.json();print(json.dumps({'passed':isinstance(body,dict),'http_status':r.status_code}))\nexcept Exception as e:print(json.dumps({'passed':False,'error_type':type(e).__name__}))",7)
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'python':platform.python_version(),
            'proxy_environment_present':any(os.environ.get(k) for k in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']),
            'dns_direct':dns,'tls_direct':tls,'http_environment_route':request,
            'interpretation':'DNS и TLS проверяют прямой маршрут, HTTP учитывает системный proxy. Ограничение прямой сети не доказывает ошибку ISS или приложения. SSL-проверка не отключается.'}


async def quotes():
    from moex_intelligence.lab_data import load_asset
    from moex_intelligence.provenance import describe_price
    async def one(symbol):
        result=await load_asset(symbol,cache=None)
        asset=result['asset']
        return {'symbol':symbol,'passed':asset is not None,'error':result.get('error'),
                'price':asset['unit_price'] if asset else None,'lot':asset['lot_size'] if asset else None,
                'provenance':describe_price(asset) if asset else None,'source':'actual MOEX request; no cache/demo fallback'}
    return await asyncio.gather(*(one(s) for s in ['SBER','SBMX','SU26238RMFS4']))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='.runtime/moex-diagnostic.json');parser.add_argument('--quotes',action='store_true');args=parser.parse_args()
    report=diagnostics()
    if args.quotes:report['quotes']=asyncio.run(quotes())
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for key in ['dns_direct','tls_direct','http_environment_route']:print(key+': '+('PASS' if report[key]['passed'] else 'НЕ ПРОШЛО · '+report[key].get('error_type','неизвестно')))
    for item in report.get('quotes',[]):print(item['symbol']+': '+('PASS' if item['passed'] else 'НЕ ПОЛУЧЕНА КОТИРОВКА'))
    print('Отчёт: '+str(output.resolve()))


if __name__=='__main__':main()
