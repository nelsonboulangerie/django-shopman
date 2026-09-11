from pathlib import Path
import os, subprocess, psycopg
root=Path.cwd()
name='orders_device_migration_lab_6e1e'
with psycopg.connect('host=127.0.0.1 port=55439 user=orders_lab dbname=postgres',autocommit=True) as conn:
    assert not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone(), 'Refuse existing target'
    conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
env=os.environ.copy(); env['DATABASE_URL']=f'postgresql://orders_lab@127.0.0.1:55439/{name}'; env['REDIS_URL']=''; env['SENTRY_DSN']=''
python='/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python'
def run(args,expected=0,input=None):
    result=subprocess.run([python,'.orders-lab/run_script.py','manage.py',*args],env=env,text=True,input=input,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(result.stdout,flush=True)
    assert result.returncode==expected,(args,result.returncode)
run(['migrate','--noinput'])
run(['migrate','backstage','0060','--noinput'])
run(['migrate','backstage','0061','--noinput'])
run(['shell'],input="from shopman.backstage.models import DeliveryDevice\nDeliveryDevice.objects.create(label='Synthetic rollback',identification='ROLLBACK-LAB')\n")
run(['migrate','backstage','0060','--noinput'],expected=1)
with psycopg.connect(f'host=127.0.0.1 port=55439 user=orders_lab dbname={name}') as conn:
    assert conn.execute('SELECT count(*) FROM backstage_deliverydevice').fetchone()[0]==1
    assert conn.execute("SELECT count(*) FROM django_migrations WHERE app='backstage' AND name='0061_delivery_device'").fetchone()[0]==1
print('PASS: empty schema round trip; populated inventory rollback refused; row and migration retained. Isolated database preserved.',flush=True)
