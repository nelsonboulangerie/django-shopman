"""Revisão local: intenção, isolamento de escopo, imutabilidade e zero publicação."""

import copy
import hashlib
import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.backstage.projections.catalog_bindings import build_catalog_binding_review
from shopman.backstage.services import catalog_bindings as service
from shopman.shop.models import CatalogBinding, CatalogSnapshot, CatalogSyncState, Channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator():
    user = User.objects.create_user('catalog-reviewer', is_staff=True)
    user.user_permissions.add(Permission.objects.get(content_type__app_label='shop', codename='manage_catalog'))
    return user


@pytest.fixture
def channel():
    return Channel.objects.create(ref='review-channel', name='Canal de revisão')


@pytest.fixture
def products():
    return [Product.objects.create(sku=sku, name=name, unit='un', base_price_q=900)
            for sku, name in [('SKU-A', 'Exemplo A'), ('SKU-B', 'Exemplo B')]]


@pytest.fixture
def raw():
    return json.dumps({'schema_version': 1, 'merchant_id': 'merchant-A', 'catalog_id': 'catalog-A',
        'context': 'DEFAULT', 'captured_at': '2026-09-15T12:00:00Z', 'source': 'imported_file',
        'categories': [{'id': 'category-A', 'items': [{'id': 'item-A', 'productId': 'product-A'}]}],
        'category_items': [{'categoryId': 'category-A', 'items': [{'id': 'item-A', 'productId': 'product-A',
            'externalCode': 'SKU-A', 'price': {'value': '12.34567890123456789'}, 'status': 'AVAILABLE',
            'contextModifiers': [{'catalogContext': 'DEFAULT', 'itemContextId': 'context-item-A', 'status': 'UNAVAILABLE'}]}],
            'products': [{'id': 'product-A', 'name': 'Nome remoto', 'description': 'Descrição remota', 'imagePath': 'merchant/photo.png'}]}]}, ensure_ascii=False, indent=2)


@pytest.fixture
def snapshot(channel, raw, operator):
    return service.import_snapshot(channel_ref=channel.ref, raw_json=raw, actor=operator)


def url(channel, operation):
    return f'/api/v1/backstage/catalog/channels/{channel.ref}/{operation}/'


def board(channel, user, snapshot=None):
    return build_catalog_binding_review(channel_ref=channel.ref, snapshot_id=snapshot.pk if snapshot else None, user=user)


def post(client, channel, operation, data, *, key=None):
    if operation == 'snapshots' and 'base_revision' not in data:
        actor = User.objects.get(pk=client.session['_auth_user_id'])
        data = {**data, 'base_revision': service.import_revision(channel, actor)}
    return client.post(url(channel, operation), data, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))


def binding_body(channel, operator, snapshot, sku='SKU-A'):
    item = board(channel, operator, snapshot).items[0]
    return {'snapshot_id': snapshot.pk, 'item_id': item.item_id, 'sku': sku,
            'base_revision': item.base_revision, 'expected_actor_id': operator.pk}


def test_import_preserves_original_and_replay_is_single_audited_write(client, channel, raw, operator):
    client.force_login(operator)
    key = str(uuid.uuid4())
    data = {'raw_json': raw, **board(channel, operator).import_action.payload_schema}
    assert len(data['base_revision']) == 64
    first = post(client, channel, 'snapshots', data, key=key)
    assert first.status_code == 200
    assert post(client, channel, 'snapshots', data, key=key).json()['replayed'] is True
    evidence = CatalogSnapshot.objects.get()
    assert evidence.raw_json == raw
    assert evidence.sha256 == hashlib.sha256(raw.encode()).hexdigest()
    assert evidence.item_count == 1
    assert LogEntry.objects.filter(object_id=str(evidence.pk), content_type__model='catalogsnapshot').count() == 1
    recovered = client.get(url(channel, 'snapshots'), {'idempotency_key': key})
    assert recovered.json()['snapshot_id'] == evidence.pk
    assert client.get(url(channel, 'snapshots'), {'idempotency_key': 'unknown'}).status_code == 202
    assert post(client, channel, 'snapshots', {**data, 'raw_json': raw + '\n'}, key=key).status_code == 409


def test_review_keeps_remote_details_and_never_selects_candidate(channel, operator, products, snapshot):
    projection = board(channel, operator, snapshot)
    item, = projection.items
    assert (item.name, item.description, item.image_path) == ('Nome remoto', 'Descrição remota', 'merchant/photo.png')
    assert (item.price, item.status) == ('12.34567890123456789', 'UNAVAILABLE')
    assert [candidate.sku for candidate in item.candidates] == ['SKU-A']
    assert item.binding is None
    assert item.binding_action.payload_schema['base_revision'] == item.base_revision
    assert item.binding_action.payload_schema['snapshot_id'] == snapshot.pk
    assert item.binding_action.idempotency == 'required'
    assert projection.import_action.payload_schema['expected_actor_id'] == operator.pk
    assert len(projection.import_action.payload_schema['base_revision']) == 64
    assert not CatalogBinding.objects.exists()


def test_binding_and_rebinding_only_change_local_binding(client, channel, operator, products, snapshot):
    listing = Listing.objects.create(ref=channel.ref, name='Oferta local')
    offer = ListingItem.objects.create(listing=listing, product=products[0], price_q=999)
    client.force_login(operator)
    before = list(Product.objects.values()), list(ListingItem.objects.values()), Directive.objects.count(), CatalogSyncState.objects.count()
    body = binding_body(channel, operator, snapshot)
    key = str(uuid.uuid4())
    with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP proibido')), patch('shopman.shop.handlers.catalog_projection._enqueue_project', side_effect=AssertionError('Publicação proibida')):
        response = post(client, channel, 'bindings', body, key=key)
        assert response.status_code == 200, response.content
        assert post(client, channel, 'bindings', body, key=key).json()['replayed']
        assert post(client, channel, 'bindings', {**body, 'sku': 'SKU-B'}).status_code == 409
        updated = binding_body(channel, operator, snapshot, sku='SKU-B')
        assert post(client, channel, 'bindings', updated).status_code == 200
    binding = CatalogBinding.objects.get()
    assert binding.product == products[1]
    assert binding.revision == 2
    assert binding.external_product_ref == 'product-A'
    assert binding.item_context_ref == 'context-item-A'
    assert LogEntry.objects.filter(content_type__model='catalogbinding').count() == 2
    assert (list(Product.objects.values()), list(ListingItem.objects.values()), Directive.objects.count(), CatalogSyncState.objects.count()) == before
    assert offer.pk
    assert client.get(url(channel, 'bindings'), {'idempotency_key': key}).json()['sku'] == 'SKU-A'


def test_same_product_can_bind_multiple_remote_items(channel, operator, products, raw):
    parsed = json.loads(raw)
    item = copy.deepcopy(parsed['category_items'][0]['items'][0])
    item['id'] = 'item-B'
    parsed['category_items'][0]['items'].append(item)
    parsed['categories'][0]['items'].append({'id': 'item-B', 'productId': 'product-A'})
    snap = service.import_snapshot(channel_ref=channel.ref, raw_json=json.dumps(parsed), actor=operator)
    for row in board(channel, operator, snap).items:
        service.bind_item(channel_ref=channel.ref, snapshot_id=snap.pk, item_id=row.item_id, sku='SKU-A', base_revision=row.base_revision, actor=operator)
    assert CatalogBinding.objects.filter(product=products[0]).count() == 2


def test_scope_collision_across_channels_is_not_transferred(channel, operator, products, snapshot, raw):
    first = board(channel, operator, snapshot).items[0]
    service.bind_item(channel_ref=channel.ref, snapshot_id=snapshot.pk, item_id=first.item_id, sku='SKU-A', base_revision=first.base_revision, actor=operator)
    other = Channel.objects.create(ref='other', name='Outro canal')
    other_snapshot = service.import_snapshot(channel_ref=other.ref, raw_json=raw, actor=operator)
    row = board(other, operator, other_snapshot).items[0]
    assert not row.can_bind
    with pytest.raises(service.CatalogBindingConflict, match='outro canal'):
        service.bind_item(channel_ref=other.ref, snapshot_id=other_snapshot.pk, item_id=row.item_id, sku='SKU-B', base_revision=row.base_revision, actor=operator)
    original = CatalogBinding.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogBinding.objects.create(channel=other, product=products[1], snapshot=other_snapshot,
            confirmed_by=operator, **service.scope(snapshot), resource_id=original.resource_id,
            external_product_ref='product-A', category_ref='category-A')
    assert CatalogBinding.objects.get().channel == channel


def test_snapshot_scope_and_actor_mismatch_are_rejected(client, channel, operator, products, snapshot):
    client.force_login(operator)
    other = Channel.objects.create(ref='other')
    body = binding_body(channel, operator, snapshot)
    assert post(client, other, 'bindings', body).status_code == 400
    assert post(client, channel, 'bindings', {**body, 'expected_actor_id': True}).status_code == 409
    assert post(client, channel, 'bindings', {**body, 'item_id': 'not-in-snapshot'}).status_code == 400
    assert client.get(url(other, 'review'), {'snapshot_id': snapshot.pk}).status_code == 400
    assert not CatalogBinding.objects.exists()


def test_receipts_are_scoped_by_actor_and_operation(client, channel, operator, raw):
    client.force_login(operator)
    key = str(uuid.uuid4())
    assert post(client, channel, 'snapshots', {'raw_json': raw, 'expected_actor_id': operator.pk}, key=key).status_code == 200
    assert client.get(url(channel, 'bindings'), {'idempotency_key': key}).status_code == 202
    other_user = User.objects.create_superuser('other-reviewer', password='fixture')
    client.force_login(other_user)
    assert client.get(url(channel, 'snapshots'), {'idempotency_key': key}).status_code == 202


def test_snapshot_is_immutable_and_references_are_protected(snapshot, products, operator, channel):
    snapshot.raw_json = '{}'
    with pytest.raises(ValidationError):
        snapshot.save()
    with pytest.raises(ValidationError):
        CatalogSnapshot.objects.filter(pk=snapshot.pk).update(raw_json='{}')
    with pytest.raises(ValidationError):
        CatalogSnapshot.objects.filter(pk=snapshot.pk).delete()
    with pytest.raises(ProtectedError):
        channel.delete()
    snapshot.refresh_from_db()
    row = board(channel, operator, snapshot).items[0]
    service.bind_item(channel_ref=channel.ref, snapshot_id=snapshot.pk, item_id=row.item_id, sku='SKU-A', base_revision=row.base_revision, actor=operator)
    with pytest.raises(ProtectedError):
        products[0].delete()


def test_audit_failure_rolls_back_binding_and_receipt(client, channel, operator, products, snapshot):
    client.force_login(operator)
    before_receipts = IdempotencyKey.objects.count()
    with patch.object(LogEntry.objects.__class__, 'log_actions', side_effect=RuntimeError('audit unavailable')):
        with pytest.raises(RuntimeError):
            post(client, channel, 'bindings', binding_body(channel, operator, snapshot))
    assert not CatalogBinding.objects.exists()
    assert IdempotencyKey.objects.count() == before_receipts


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"price":NaN}', '[]', '{}'])
def test_invalid_snapshot_is_not_imported(channel, operator, raw):
    with pytest.raises(service.CatalogBindingError):
        service.import_snapshot(channel_ref=channel.ref, raw_json=raw, actor=operator)
    assert not CatalogSnapshot.objects.exists()


def test_decimal_code_stays_numeric_and_has_no_candidate(channel, operator, products, raw):
    value = json.loads(raw)
    value['category_items'][0]['items'][0]['externalCode'] = 1.25
    encoded = json.dumps(value)
    snapshot = service.import_snapshot(channel_ref=channel.ref, raw_json=encoded, actor=operator)
    parsed, _ = service.parse_snapshot(snapshot.raw_json)
    assert parsed['category_items'][0]['items'][0]['externalCode'] == Decimal('1.25')
    assert board(channel, operator, snapshot).items[0].candidates == ()


def test_permission_required_for_all_routes(client, channel):
    user = User.objects.create_user('no-catalog-permission', is_staff=True)
    client.force_login(user)
    for operation in ('review', 'snapshots', 'bindings'):
        assert client.get(url(channel, operation)).status_code == 403
    assert post(client, channel, 'snapshots', {}).status_code == 403
    assert post(client, channel, 'bindings', {}).status_code == 403


def test_new_snapshot_requires_review_and_old_receipt_cannot_confirm_it(client, channel, operator, products, snapshot, raw):
    client.force_login(operator)
    key = str(uuid.uuid4())
    old_body = binding_body(channel, operator, snapshot)
    assert post(client, channel, 'bindings', old_body, key=key).status_code == 200
    assert board(channel, operator, snapshot).items[0].needs_review is False
    changed = json.loads(raw)
    changed['categories'][0]['id'] = 'category-B'
    changed['categories'][0]['items'][0]['productId'] = 'product-B'
    detail = changed['category_items'][0]
    detail['categoryId'] = 'category-B'
    detail['items'][0]['productId'] = 'product-B'
    detail['products'][0]['id'] = 'product-B'
    new_snapshot = service.import_snapshot(channel_ref=channel.ref, raw_json=json.dumps(changed), actor=operator)
    row = board(channel, operator, new_snapshot).items[0]
    assert row.needs_review is True
    assert row.binding.snapshot_id == snapshot.pk
    assert row.product_ref == 'product-B'
    assert row.category_ref == 'category-B'
    assert post(client, channel, 'bindings', old_body, key=key).json()['replayed'] is True
    assert board(channel, operator, new_snapshot).items[0].needs_review is True
    assert post(client, channel, 'bindings', binding_body(channel, operator, new_snapshot)).status_code == 200
    assert board(channel, operator, new_snapshot).items[0].needs_review is False


def test_import_revision_and_conflicting_intention_headers_are_rejected(client, channel, operator, raw):
    client.force_login(operator)
    assert post(client, channel, 'snapshots', {'raw_json': raw, 'expected_actor_id': operator.pk, 'base_revision': '0' * 64}).status_code == 409
    assert post(client, channel, 'snapshots', {'raw_json': raw, 'expected_actor_id': operator.pk, 'idempotency_key': 'body-key'}, key='header-key').status_code == 409
    assert not CatalogSnapshot.objects.exists()


def test_invalid_context_is_visible_but_cannot_be_bound(client, channel, operator, products, raw):
    client.force_login(operator)
    parsed = json.loads(raw)
    parsed['category_items'][0]['items'][0]['contextModifiers'] = None
    snap = service.import_snapshot(channel_ref=channel.ref, raw_json=json.dumps(parsed), actor=operator)
    row = board(channel, operator, snap).items[0]
    assert row.can_bind is False
    assert row.binding_action.enabled is False
    assert row.needs_review is True
    assert post(client, channel, 'bindings', binding_body(channel, operator, snap)).status_code == 400
    assert not CatalogBinding.objects.exists()


def test_audit_failure_rolls_back_import_and_receipt(client, channel, operator, raw):
    client.force_login(operator)
    before = IdempotencyKey.objects.count()
    data = {'raw_json': raw, **board(channel, operator).import_action.payload_schema}
    with patch.object(LogEntry.objects.__class__, 'log_actions', side_effect=RuntimeError('audit unavailable')):
        with pytest.raises(RuntimeError):
            post(client, channel, 'snapshots', data)
    assert not CatalogSnapshot.objects.exists()
    assert IdempotencyKey.objects.count() == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('same_item', [True, False], ids=['same-item-different-skus', 'same-sku-different-items'])
def test_postgres_parallel_confirmations_keep_binding_audit_and_receipts_consistent(operator, channel, products, raw, same_item):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection, connections
    from django.test import Client

    if connection.vendor != 'postgresql':
        pytest.skip('Exige locks reais e conexões independentes no PostgreSQL.')
    parsed = json.loads(raw)
    if not same_item:
        second = copy.deepcopy(parsed['category_items'][0]['items'][0])
        second['id'] = 'item-B'
        parsed['category_items'][0]['items'].append(second)
        parsed['categories'][0]['items'].append({'id': 'item-B', 'productId': 'product-A'})
    snapshot = service.import_snapshot(channel_ref=channel.ref, raw_json=json.dumps(parsed), actor=operator)
    rows = board(channel, operator, snapshot).items
    choices = [
        (rows[0], 'SKU-A'),
        (rows[0], 'SKU-B') if same_item else (rows[1], 'SKU-A'),
    ]
    barrier = Barrier(2)
    keys = [str(uuid.uuid4()), str(uuid.uuid4())]

    def confirm(index):
        close_old_connections()
        try:
            client = Client()
            actor = User.objects.get(pk=operator.pk)
            client.force_login(actor)
            row, sku = choices[index]
            payload = {'snapshot_id': snapshot.pk, 'item_id': row.item_id, 'sku': sku,
                       'base_revision': row.base_revision, 'expected_actor_id': actor.pk}
            barrier.wait(timeout=10)
            response = post(client, channel, 'bindings', payload, key=keys[index])
            receipt = client.get(url(channel, 'bindings'), {'idempotency_key': keys[index]})
            assert receipt.status_code == response.status_code
            assert receipt.json()['outcome'] == response.json()['outcome']
            replay = post(client, channel, 'bindings', payload, key=keys[index])
            assert replay.status_code == response.status_code
            assert replay.json()['replayed'] is True
            return response.status_code, sku, response.json()
        finally:
            connections.close_all()

    with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP proibido')):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(confirm, index) for index in range(2)]
            results = [future.result(timeout=25) for future in futures]
    if same_item:
        assert sorted(status for status, _, _ in results) == [200, 409]
        winner = next(sku for status, sku, _ in results if status == 200)
        binding = CatalogBinding.objects.get()
        assert binding.product.sku == winner
        assert binding.revision == 1
        assert LogEntry.objects.filter(content_type__model='catalogbinding').count() == 1
    else:
        assert [status for status, _, _ in results] == [200, 200]
        assert CatalogBinding.objects.filter(product=products[0], revision=1).count() == 2
        assert LogEntry.objects.filter(content_type__model='catalogbinding').count() == 2
    receipts = IdempotencyKey.objects.filter(key__in=keys)
    assert receipts.count() == 2
    assert set(receipts.values_list('status', flat=True)) == {'done'}
    for entry in LogEntry.objects.filter(content_type__model='catalogbinding'):
        audit = json.loads(entry.change_message)
        persisted = CatalogBinding.objects.get(pk=entry.object_id)
        assert audit['after']['sku'] == persisted.product.sku
        assert audit['after']['revision'] == persisted.revision
        assert audit['after']['snapshot_id'] == snapshot.pk
