import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'docs/reports/execution/orders-20260910/http_read_lab'))
import run_http_lab
run_http_lab.setup()
from django.db import transaction
from shopman.backstage.models import DeliveryDevice
from shopman.orderman.models import Order
from shopman.shop.models import Channel
assert not DeliveryDevice.objects.exists(), 'Refuse overwriting existing inventory'
with transaction.atomic():
    channel=Channel.objects.get(ref='http-lab')
    channel.config['fulfillment']={'equipment':['card_machine']}
    channel.save()
    transit=list(Order.objects.filter(status='dispatched',data__fulfillment_type='delivery').order_by('pk')[:3])
    for index in range(10):
        order=transit[index] if index<3 else None
        device=DeliveryDevice.objects.create(label=f'Maquininha sintética {index}',identification=f'HTTP-LAB-DEVICE-{index}',active=index!=9,current_order=order)
        if order:
            order.data['dispatch']={'equipment':['card_machine'],'device_ref':str(device.ref),'device_label':device.label,'equipment_out_at':'2026-09-11T12:00:00Z','equipment_out_by':'lab'}
            order.save(update_fields=['data'])
print('500 rich orders; 10 devices, 3 in transit, 6 available, 1 inactive. Synthetic only.')
