import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from shopman.orderman.models import Order, OrderItem, Session, Directive
from shopman.backstage.models import KDSInstance, KDSTicket

ref = 'LAB-PHASE-' + uuid4().hex[:8]
KDSInstance.objects.get_or_create(ref='lab-picking', defaults={'name':'Separação sintética','type':'picking','sound_enabled':False})
Session.objects.create(session_key=ref, channel_ref='lab')
order = Order.objects.create(ref=ref, status='accepted', channel_ref='lab', session_key=ref, total_q=500, data={'fulfillment_type':'pickup','payment':{'method':'cash'}})
OrderItem.objects.create(order=order, line_id=ref+'-line', sku='LAB-PROD', name='Produto laboratório', qty='0.500', unit_price_q=1000, line_total_q=500)
with patch('shopman.orderman.dispatch._on_commit_callback'):
    order.transition_status('preparing', actor='operator:orders-lab')
task = Directive.objects.get(topic='order.lifecycle_phase', payload__order_ref=ref)
assert task.status == 'queued'
assert not KDSTicket.objects.filter(session_key=ref).exists()
Path('.orders-lab/phase-manifest.json').write_text(json.dumps({'ref':ref, 'task':task.pk}))
os._exit(17)  # expected abrupt application-process exit after the local commit
