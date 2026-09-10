from django.contrib.auth.models import User, Permission
from shopman.shop.models import Shop, Channel
from shopman.offerman.models import Product, Listing, ListingItem
from shopman.orderman.models import Order, OrderItem
Shop.objects.get_or_create(name='Orders synthetic lab')
user, _ = User.objects.get_or_create(username='orders-lab', defaults={'is_staff':True,'first_name':'Operador laboratório'})
user.set_password('synthetic-lab-only-20260910')
user.save()
user.user_permissions.set(Permission.objects.filter(content_type__app_label='shop',codename__in=['manage_orders','manage_catalog']))
Channel.objects.update_or_create(ref='lab', defaults={'name':'Laboratório','is_active':True,'config':{'payment':{'timing':'external'},'confirmation':{'mode':'manual'},'fulfillment':{'timing':'external','prep_start':'operator'}}})
product, _ = Product.objects.get_or_create(sku='LAB-PROD', defaults={'name':'Produto laboratório','unit':'un','base_price_q':1000,'is_published':True,'is_sellable':True})
listing, _ = Listing.objects.get_or_create(ref='lab',defaults={'name':'Laboratório','is_active':True})
ListingItem.objects.get_or_create(product=product,listing=listing,defaults={'price_q':1000})
from uuid import uuid4
import json
from pathlib import Path
run = uuid4().hex[:8]
refs = {'advance_ref': f'LAB-ADVANCE-{run}', 'notes_ref': f'LAB-NOTES-{run}'}
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
for suffix in ('advance', 'notes', 'price', 'product'):
    tester, _ = User.objects.get_or_create(username=f'orders-lab-{suffix}', defaults={'is_staff':True,'first_name':f'Laboratório {suffix}'})
    tester.set_password('synthetic-lab-only-20260910')
    tester.save()
    tester.user_permissions.set(user.user_permissions.all())
