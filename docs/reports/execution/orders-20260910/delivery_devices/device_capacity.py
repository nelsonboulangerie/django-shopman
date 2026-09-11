"""Finite local-only read assay; terminates only its own child processes."""
import json, os, socket, subprocess, time
from pathlib import Path
root=Path.cwd()
assert root.name=='django-shopman-orders-execution-20260910'
python='/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python'
node='/opt/homebrew/opt/node@22/bin/node'
env=os.environ.copy();env['PATH']='/opt/homebrew/opt/node@22/bin:'+env['PATH']
children=[]; logs=[]
def spawn(args,logname,extra=None,cwd=None):
    log=open(root/'.orders-lab'/logname,'w');logs.append(log)
    child=subprocess.Popen(args,cwd=cwd or root,env={**env,**(extra or {})},stdout=log,stderr=subprocess.STDOUT)
    children.append(child)
    return child
ports=[8015,8016,8017,8018,8019,8020,3005]
for port in ports:
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1',port))!=0, f'Port {port} already occupied; not taking ownership'
try:
    spawn([python,'docs/reports/execution/orders-20260910/http_read_lab/run_http_lab.py','serve'],'device-perf-8015.txt')
    for port in ports[1:6]:
        spawn([python,'docs/reports/execution/orders-20260910/process_read_lab/serve.py',str(port)],f'device-perf-{port}.txt')
    spawn([node,'.output/server/index.mjs'],'device-nitro.txt',extra={'NUXT_APP_BASE_URL':'/','NUXT_DJANGO_BASE_URL':'http://127.0.0.1:8015','NUXT_PUBLIC_DJANGO_BASE_URL':'http://127.0.0.1:8015','HOST':'127.0.0.1','PORT':'3005'},cwd=root/'surfaces/orders-nuxt')
    deadline=time.monotonic()+60
    for port in ports:
        while True:
            assert all(c.poll() is None for c in children),'A reader failed to prepare'
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',port))==0: break
            assert time.monotonic()<deadline,'Reader preparation timeout'
            time.sleep(.2)
    print('Local readers ready; 500 rich orders and 10 physical device fixtures.',flush=True)
    with open(root/'.orders-lab/device-process-measure.txt','w') as out:
        result=subprocess.run([python,'docs/reports/execution/orders-20260910/process_read_lab/measure.py','5'],cwd=root,env={**env,'ORDERS_PERF_SAMPLES':'60'},stdout=out,stderr=subprocess.STDOUT)
        assert result.returncode==0,'Backend assay failed'
    (root/'.orders-lab/device-process-result.json').write_bytes((root/'.orders-lab/process-read-result.json').read_bytes())
    print('Backend distributions recorded; starting browser read/context checks.',flush=True)
    with open(root/'.orders-lab/device-browser-performance.txt','w') as out:
        result=subprocess.run(['npx','playwright','test','-c','playwright.performance.config.ts'],cwd=root/'surfaces/orders-nuxt',env={**env,'ORDERS_PERF_LAB':'1','ORDERS_PERF_N':'500'},stdout=out,stderr=subprocess.STDOUT)
        assert result.returncode==0,'Browser assay failed'
    print('Read and context assays completed. No mutation or real effects.',flush=True)
finally:
    for child in children:
        if child.poll() is None: child.terminate()
    for child in children:
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill();child.wait()
    for log in logs: log.close()
