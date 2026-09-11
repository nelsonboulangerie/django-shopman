from django.contrib.auth.models import Permission, User
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Channel, Shop

Shop.objects.get_or_create(name='Orders synthetic lab')
user, _ = User.objects.get_or_create(username='orders-lab', defaults={'is_staff':True,'first_name':'Operador laboratório'})
user.set_password('synthetic-lab-only-20260910')
user.save()
user.user_permissions.set(Permission.objects.filter(content_type__app_label='shop',codename__in=['manage_orders','manage_catalog']))
Channel.objects.update_or_create(ref='lab', defaults={'name':'Laboratório','is_active':True,'config':{'payment':{'timing':'external'},'confirmation':{'mode':'manual'},'fulfillment':{'timing':'external','prep_start':'operator'}}})
product, _ = Product.objects.get_or_create(sku='LAB-PROD', defaults={'name':'Produto laboratório','unit':'un','base_price_q':1000,'is_published':True,'is_sellable':True})
listing, _ = Listing.objects.get_or_create(ref='lab',defaults={'name':'Laboratório','is_active':True})
ListingItem.objects.get_or_create(product=product,listing=listing,defaults={'price_q':1000})
import json
from pathlib import Path
from uuid import uuid4

run = uuid4().hex[:8]
refs = {'advance_ref': f'LAB-ADVANCE-{run}', 'notes_ref': f'LAB-NOTES-{run}', 'cancel_ref': f'LAB-CANCEL-{run}'}
Path('.orders-lab/manifest.json').write_text(json.dumps(refs))
for ref in refs.values():
    order, created = Order.objects.get_or_create(ref=ref, defaults={'channel_ref':'lab','status':'accepted','total_q':500,'session_key':ref,'snapshot':{'items':[{'sku':'LAB-PROD','qty':'0.500','name':'Produto laboratório'}]},'data':{'fulfillment_type':'pickup','payment':{'method':'cash'},'customer':{'name':ref},'kitchen_note':'Nota inicial'}})
    if created:
        OrderItem.objects.create(order=order,line_id=ref+'-line',sku='LAB-PROD',name='Produto laboratório',qty='0.500',unit_price_q=1000,line_total_q=500)
print('Synthetic lab seeded; no external adapters enabled.')

Product.objects.get_or_create(sku='LAB-PROD-B', defaults={'name':'Produto secundário','unit':'un','base_price_q':1200,'is_published':True,'is_sellable':True})
second, _ = User.objects.get_or_create(username='orders-lab-b', defaults={'is_staff':True,'first_name':'Operadora B laboratório'})
second.set_password('synthetic-lab-only-20260910')
second.save()
second.user_permissions.set(user.user_permissions.all())
for suffix in ('advance', 'notes', 'price', 'product', 'cancel'):
    tester, _ = User.objects.get_or_create(username=f'orders-lab-{suffix}', defaults={'is_staff':True,'first_name':f'Laboratório {suffix}'})
    tester.set_password('synthetic-lab-only-20260910')
    tester.save()
    tester.user_permissions.set(user.user_permissions.all())

# New synthetic journeys: custody receipt and display selection. No worker/adapters.
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.offerman.models import Collection

active = list(Terminal.objects.filter(is_active=True))
assert len(active) <= 1, 'Synthetic browser cohort requires one unambiguous drawer.'
terminal = active[0] if active else Terminal.objects.create(ref='orders-browser-lab', label='Caixa do laboratório')
shift = cash.open_shift_for_terminal(terminal)
if shift is None:
    shift = cash.open_shift(operator=user, terminal=terminal)
cash_ref = f'LAB-CASH-{run}'
Order.objects.create(ref=cash_ref, status='dispatched', total_q=1500, channel_ref='lab',
    data={'customer': {'name': 'Acerto sintético'}, 'fulfillment_type': 'delivery', 'payment': {'method': 'cash', 'collection': 'on_delivery'}})
collection, _ = Collection.objects.get_or_create(ref='orders-browser-bread', defaults={'name': 'Coleção do laboratório'})
feed_ref = f'lab-tv-{run}'
Channel.objects.create(ref=feed_ref, name=f'Tela sintética {run}', commerce_policy=Channel.CommercePolicy.DISPLAY,
    config={'display': {'format': '', 'collections': [], 'prices_from': 'lab', 'rotate_seconds': 0, 'items_per_page': 0}})
refs.update(cash_ref=cash_ref, cash_shift_id=shift.pk, feed_ref=feed_ref, feed_name=f'Tela sintética {run}', collection_ref=collection.ref, collection_name=collection.name)
Path('.orders-lab/manifest.json').write_text(json.dumps(refs))
for suffix in ('cash', 'feed', 'read'):
    tester, _ = User.objects.get_or_create(username=f'orders-lab-{suffix}', defaults={'is_staff': True, 'first_name': f'Laboratório {suffix}'})
    tester.set_password('synthetic-lab-only-20260910')
    tester.save()
    tester.user_permissions.set(user.user_permissions.all())

# Product edit and exact curation use fresh resources per run.
from shopman.offerman.models import CollectionItem

edit_sku = f'LAB-EDIT-{run}'
edit_product = Product.objects.create(sku=edit_sku, name=f'Produto editável {run}', base_price_q=1100)
ListingItem.objects.create(product=edit_product, listing=listing, price_q=1100)
curation = Collection.objects.create(ref=f'lab-curation-{run}', name=f'Curadoria {run}', is_active=True)
CollectionItem.objects.create(collection=curation, product=product, sort_order=0)
CollectionItem.objects.create(collection=curation, product=edit_product, sort_order=1)
refs.update(edit_sku=edit_sku, edit_name=edit_product.name, curation_ref=curation.ref, curation_name=curation.name)
Path('.orders-lab/manifest.json').write_text(json.dumps(refs))
for suffix in ('edit', 'curation'):
    tester, _ = User.objects.get_or_create(username=f'orders-lab-{suffix}', defaults={'is_staff': True, 'first_name': f'Laboratório {suffix}'})
    tester.set_password('synthetic-lab-only-20260910')
    tester.save()
    tester.user_permissions.set(user.user_permissions.all())

refs['reject_ref'] = f'LAB-REJECT-{run}'
Order.objects.create(ref=refs['reject_ref'], channel_ref='lab', status='new', total_q=500, session_key=refs['reject_ref'], snapshot={'items': [{'sku': 'LAB-PROD', 'qty': '0.500', 'name': 'Produto laboratório'}]}, data={'fulfillment_type': 'pickup', 'payment': {'method': 'cash'}, 'customer': {'name': refs['reject_ref']}})
Path('.orders-lab/manifest.json').write_text(json.dumps(refs))

# Individually identified synthetic readers. Never import inventory from real data.
from shopman.backstage.models import DeliveryDevice

machine, _ = DeliveryDevice.objects.get_or_create(identification='ORDERS-LAB-MACHINE', defaults={'label': 'Maquininha azul laboratório'})
assert machine.current_order_id is None, 'Return the previous synthetic device before a new lab run'
Channel.objects.update_or_create(ref='device-lab', defaults={'name': 'Entrega laboratório', 'config': {'payment': {'timing': 'external'}, 'fulfillment': {'timing': 'external', 'equipment': ['card_machine']}}})
refs['device_order_ref'] = f'LAB-DEVICE-{run}'
refs['device_ref'] = str(machine.ref)
Order.objects.create(ref=refs['device_order_ref'], channel_ref='device-lab', status='ready', total_q=1000, data={'fulfillment_type': 'delivery', 'payment': {'method': 'credit', 'collection': 'on_delivery'}, 'customer': {'name': 'Entrega laboratório'}})
Path('.orders-lab/manifest.json').write_text(json.dumps(refs))
admin_user, _ = User.objects.get_or_create(username='orders-lab-admin', defaults={'is_staff': True, 'is_superuser': True})
admin_user.set_password('synthetic-lab-only-20260910')
admin_user.save()
