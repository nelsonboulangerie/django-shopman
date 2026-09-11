"""Same five-reader contract; prepare browser only after backend readers stop."""
import os, socket, subprocess, time
from pathlib import Path
root=Path.cwd(); assert root.name=='django-shopman-orders-execution-20260910'
python='/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python'
node='/opt/homebrew/opt/node@22/bin/node'
env={**os.environ,'PATH':'/opt/homebrew/opt/node@22/bin:'+os.environ['PATH']}
children=[]; logs=[]
def snapshot(label):
    with open(root/'.orders-lab'/f'device-host-{label}.txt','w') as out:
        for args in (['sysctl','vm.swapusage'],['uptime'],['memory_pressure']):
            subprocess.run(args,stdout=out,stderr=subprocess.STDOUT)
def start(args,port,label,cwd=None,extra=None):
    with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',port))!=0
    log=open(root/'.orders-lab'/f'device-phased-{label}.txt','w'); logs.append(log)
    child=subprocess.Popen(args,cwd=cwd or root,env={**env,**(extra or {})},stdout=log,stderr=subprocess.STDOUT); children.append(child)
    deadline=time.monotonic()+60
    while True:
        assert child.poll() is None
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0: break
        assert time.monotonic()<deadline
        time.sleep(.2)
def stop():
    for child in children:
        if child.poll() is None: child.terminate()
    for child in children:
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: child.kill(); child.wait()
    children.clear()
    for log in logs: log.close()
    logs.clear()
try:
    snapshot('baseline-before')
    for port in range(8016,8021): start([python,'.orders-lab/device_baseline_reader.py',str(port)],port,'baseline-'+str(port))
    with open(root/'.orders-lab/device-baseline-measure.txt','w') as out:
        subprocess.run([python,'docs/reports/execution/orders-20260910/process_read_lab/measure.py','5'],env={**env,'ORDERS_PERF_SAMPLES':'60'},stdout=out,stderr=subprocess.STDOUT,check=True)
    (root/'.orders-lab/device-baseline-result.json').write_bytes((root/'.orders-lab/process-read-result.json').read_bytes())
    print('Baseline read-only comparison complete.',flush=True)
finally:
    stop(); snapshot('baseline-after')
