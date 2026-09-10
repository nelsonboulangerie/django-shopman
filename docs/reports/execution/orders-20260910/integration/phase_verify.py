import json
from pathlib import Path
from decimal import Decimal
from shopman.orderman.models import Directive, Order
from shopman.backstage.models import KDSTicket
manifest = json.loads(Path('.orders-lab/phase-manifest.json').read_text())
order = Order.objects.get(ref=manifest['ref'])
task = Directive.objects.get(pk=manifest['task'])
tickets = list(KDSTicket.objects.filter(session_key=order.session_key))
assert task.status == 'done'
assert order.data['lifecycle']['on_preparing'] == 'done'
assert len(tickets) == 1
assert Decimal(str(tickets[0].items[0]['qty'])) == Decimal('0.500')
print(json.dumps({'order': order.ref, 'status':order.status, 'phase':task.status, 'attempts':task.attempts, 'tickets':len(tickets), 'qty':str(tickets[0].items[0]['qty'])}))
