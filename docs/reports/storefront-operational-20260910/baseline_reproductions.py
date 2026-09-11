from types import SimpleNamespace
from unittest.mock import patch
import pytest
from django.test import RequestFactory
from django.utils import timezone
from shopman.orderman.models import Order,OrderItem
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.shop.services import remote_mutations
from shopman.storefront.services.pickup_slots import get_slots
pytestmark=pytest.mark.django_db

def test_x_header_is_ignored():
    req=RequestFactory().post('/', HTTP_X_IDEMPOTENCY_KEY='intention-A')
    assert remote_mutations.idempotency_key_from_request(req,fallback='fallback')=='fallback'

def test_checkout_retry_cannot_recover_committed_order(client):
    _seed_surface()
    assert client.put('/api/v1/cart/skus/PAO-FRANCES/',{'qty':1},content_type='application/json').status_code==200
    payload=with_baseline(client,{'name':'Ana','phone':'+5543999990001','fulfillment_type':'pickup','delivery_time_slot':get_slots()[-1]['ref'],'delivery_date':timezone.localdate().isoformat(),'payment_method':'cash','idempotency_key':'checkout-audit-one'})
    first=client.post('/api/v1/checkout/',payload,content_type='application/json')
    assert first.status_code==201, first.content
    second=client.post('/api/v1/checkout/',payload,content_type='application/json')
    assert second.status_code==400,second.content
    assert second.json()['detail']=='Sua sacola está vazia.'
    assert Order.objects.filter(ref=first.json()['order_ref']).count()==1

def test_new_reorder_intent_is_replayed_without_changing_cart(client):
    _seed_surface()
    o=Order.objects.create(ref='AUDIT-REORDER',channel_ref='web',status='completed',total_q=100,data={})
    OrderItem.objects.create(order=o,line_id='1',sku='PAO-FRANCES',name='Pao',qty=1,unit_price_q=100,line_total_q=100)
    with patch('shopman.storefront.services.orders.get_accessible_order',return_value=o):
        one=client.post(f'/api/v1/orders/{o.ref}/reorder/',{'mode':'append'},content_type='application/json',HTTP_X_IDEMPOTENCY_KEY='first')
        assert one.status_code==200,one.content
        assert client.put('/api/v1/cart/skus/PAO-FRANCES/',{'qty':0},content_type='application/json').status_code==200
        two=client.post(f'/api/v1/orders/{o.ref}/reorder/',{'mode':'append'},content_type='application/json',HTTP_X_IDEMPOTENCY_KEY='second')
        assert two.status_code==200,two.content
        actual=client.get('/api/v1/storefront/cart/').json()['cart']
        assert two.json()['cart']['is_empty'] is False
        assert actual['is_empty'] is True

def test_post_commit_defaults_failure_is_absent_from_result(client):
    _seed_surface()
    assert client.put('/api/v1/cart/skus/PAO-FRANCES/',{'qty':1},content_type='application/json').status_code==200
    payload=with_baseline(client,{'name':'Ana','phone':'+5543999990001','fulfillment_type':'pickup','delivery_time_slot':get_slots()[-1]['ref'],'delivery_date':timezone.localdate().isoformat(),'payment_method':'cash','idempotency_key':'side-effect'})
    with patch('shopman.shop.services.checkout.save_defaults',side_effect=RuntimeError('synthetic failure')):
        result=client.post('/api/v1/checkout/',payload,content_type='application/json')
    assert result.status_code==201,result.content
    assert set(result.json())=={'order_ref','status','next_url'}

def test_notification_toggle_replay_reverses_choice():
    from shopman.guestman.services import customer as customers
    from shopman.shop.services.account import toggle_notification_consent
    c=customers.create(ref='AUDIT-C',first_name='Ana',phone='+5543999990001')
    assert 'whatsapp' in toggle_notification_consent(c.ref,'whatsapp')
    assert 'whatsapp' not in toggle_notification_consent(c.ref,'whatsapp')

def test_stock_notice_dispatch_does_not_check_global_optout():
    from shopman.guestman.services import customer as customers
    from shopman.guestman import ConsentService
    from shopman.storefront.services import stock_alerts
    from shopman.shop.protocols import NotificationResult
    c=customers.create(ref='AUDIT-S',first_name='Ana',phone='+5543999990002')
    sub=stock_alerts.subscribe('AUDIT-SKU',customer=c,alert_type='stock_back')
    ConsentService.revoke_consent(c.ref,'whatsapp')
    with patch('shopman.shop.notifications.notify',return_value=NotificationResult(success=True)) as send, patch.object(stock_alerts,'_image_url',return_value=''):
        assert stock_alerts._deliver(sub,product_name='Produto') is True
    assert send.call_count==1

def test_edit_between_price_check_and_commit_changes_confirmed_total(client):
    from shopman.shop.services import checkout
    _seed_surface()
    assert client.put('/api/v1/cart/skus/PAO-FRANCES/',{'qty':1},content_type='application/json').status_code==200
    payload=with_baseline(client,{'name':'Ana','phone':'+5543999990001','fulfillment_type':'pickup','delivery_time_slot':get_slots()[-1]['ref'],'delivery_date':timezone.localdate().isoformat(),'payment_method':'cash','idempotency_key':'race-total'})
    original=checkout._ensure_total_matches
    def concurrent_edit(session_key,channel_ref,expected):
        original(session_key,channel_ref,expected)
        changed=client.put('/api/v1/cart/skus/PAO-FRANCES/',{'qty':2},content_type='application/json')
        assert changed.status_code==200,changed.content
    with patch.object(checkout,'_ensure_total_matches',side_effect=concurrent_edit):
        result=client.post('/api/v1/checkout/',payload,content_type='application/json')
    assert result.status_code==201,result.content
    order=Order.objects.get(ref=result.json()['order_ref'])
    assert order.total_q > payload['expected_total_q'],(order.total_q,payload)
