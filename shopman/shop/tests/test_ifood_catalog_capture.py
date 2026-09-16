"""Captura sem banco, com HTTP simulado e evidência completa para revisão."""

import copy
import hashlib
import json
import os
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.services import ifood_catalog_capture as capture
from shopman.shop.services.ifood_catalog_review import validate_review_snapshot

M = "00000000-0000-4000-8000-000000000001"
C = "00000000-0000-4000-8000-000000000002"
K = "00000000-0000-4000-8000-000000000003"


@pytest.fixture
def configured(settings):
    settings.SHOPMAN_IFOOD = {"merchant_id": M, "api_base": capture.OFFICIAL_BASE, "timeout": 5}


@pytest.fixture
def responses():
    catalogs = [{"catalogId": C, "context": ["DEFAULT"]}]
    categories = [{"id": K, "items": [{"id": "item", "productId": "product"}]}]
    detail = {"categoryId": K, "items": [{"id": "item", "productId": "product", "price": {"value": 12.34}}],
              "products": [{"id": "product", "name": "Pão", "unknown": "preservado"}], "options": [], "optionGroups": []}
    return [catalogs, categories, detail, copy.deepcopy(detail), copy.deepcopy(categories), copy.deepcopy(catalogs)]


def response(body, status=200):
    raw = json.dumps(body, ensure_ascii=False).encode()
    result = Mock(status_code=status)
    result.iter_content.return_value = [raw]
    return result


def run_capture(responses):
    with patch.object(capture.ifood_auth, "get_access_token", return_value="fixture-token") as auth, patch.object(capture.requests, "get", side_effect=[response(row) for row in responses]) as get:
        raw = capture.capture_catalog(merchant_id=M, catalog_id=C, context="DEFAULT")
    auth.assert_called_once_with(force=True)
    assert all(call.kwargs['allow_redirects'] is False for call in get.call_args_list)
    assert all(call.args[0].startswith(capture.OFFICIAL_BASE + '/catalog/v2.0/') for call in get.call_args_list)
    return json.loads(raw, parse_float=Decimal)


def test_complete_snapshot_is_accepted_and_preserves_raw_hashes(configured, responses):
    snapshot = run_capture(responses)
    validate_review_snapshot(snapshot)
    assert snapshot['source'] == 'api_capture'
    assert snapshot['category_items'][0]['products'][0]['unknown'] == 'preservado'
    assert snapshot['category_items'][0]['items'][0]['price']['value'] == Decimal('12.34')
    for receipt in snapshot['provenance']['responses']:
        assert receipt['sha256'] == hashlib.sha256(receipt['raw_body'].encode()).hexdigest()
        assert 'fixture-token' not in json.dumps(receipt)
    assert len(snapshot['provenance']['responses']) == 6


@pytest.mark.parametrize('field,value', [('merchant_id', C), ('api_base', 'https://attacker.invalid'),
    ('api_base', 'http://merchant-api.ifood.com.br'), ('api_base', 'https://merchant-api.ifood.com.br@attacker.invalid'),
    ('timeout', 1000)])
def test_invalid_scope_never_authenticates(settings, configured, field, value):
    settings.SHOPMAN_IFOOD[field] = value
    with patch.object(capture.ifood_auth, 'get_access_token') as auth:
        with pytest.raises(capture.CaptureError):
            capture.capture_catalog(merchant_id=M, catalog_id=C, context='DEFAULT')
    auth.assert_not_called()


@pytest.mark.parametrize('change', [
    lambda rows: rows[0][0].update(context=['OTHER']),
    lambda rows: rows[3]['items'][0]['price'].update(value=99),
    lambda rows: rows[4][0].update(items=[]),
    lambda rows: rows[2].update(items=[]),
])
def test_changed_or_incomplete_capture_rejected(configured, responses, change):
    change(responses)
    with pytest.raises(capture.CaptureError):
        run_capture(responses)


@pytest.mark.parametrize('status', [302, 401, 429, 500])
def test_redirect_and_http_errors_are_safe(configured, status):
    with patch.object(capture.ifood_auth, 'get_access_token', return_value='fixture-token'), patch.object(capture.requests, 'get', return_value=response({'secret': 'DO-NOT-PRINT'}, status)):
        with pytest.raises(capture.CaptureError) as error:
            capture.capture_catalog(merchant_id=M, catalog_id=C, context='DEFAULT')
    assert 'DO-NOT-PRINT' not in str(error.value)
    assert 'fixture-token' not in str(error.value)


def test_output_is_private_new_and_not_written_when_capture_fails(tmp_path, configured, responses):
    tmp_path.chmod(0o700)
    target = tmp_path / 'snapshot.json'
    with patch('shopman.shop.management.commands.capture_ifood_catalog.capture_catalog', side_effect=capture.CaptureError('Falha segura')):
        with pytest.raises(CommandError):
            call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(target))
    assert list(tmp_path.iterdir()) == []
    raw = capture._encode_json(run_capture(responses)).encode()
    with patch('shopman.shop.management.commands.capture_ifood_catalog.capture_catalog', return_value=raw) as collect:
        call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(target))
        assert target.read_bytes() == raw
        assert os.stat(target).st_mode & 0o777 == 0o600
        with pytest.raises(CommandError, match='existe'):
            call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(target))
    collect.assert_called_once()


def test_public_destination_and_symlink_rejected_before_auth(tmp_path, configured):
    tmp_path.chmod(0o755)
    with patch.object(capture.ifood_auth, 'get_access_token') as auth:
        with pytest.raises(CommandError):
            call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(tmp_path / 'new.json'))
    auth.assert_not_called()


def test_response_size_limit(configured, monkeypatch):
    monkeypatch.setattr(capture, 'MAX_RESPONSE', 2)
    with patch.object(capture.ifood_auth, 'get_access_token', return_value='fixture-token'), patch.object(capture.requests, 'get', return_value=response([{'catalogId': C}])):
        with pytest.raises(capture.CaptureError, match='tamanho'):
            capture.capture_catalog(merchant_id=M, catalog_id=C, context='DEFAULT')


@pytest.mark.django_db
def test_numeric_code_never_becomes_text_candidate_in_prepare(configured, responses, tmp_path):
    from io import StringIO

    from shopman.offerman.models import Product

    from shopman.shop.models import Channel

    Channel.objects.create(ref='ifood', name='Fixture')
    Product.objects.create(sku='1.25', name='Exemplo', unit='un')
    for index in (2, 3):
        responses[index]['items'][0]['externalCode'] = 1.25
    snapshot = run_capture(responses)
    assert snapshot['category_items'][0]['items'][0]['externalCode'] == Decimal('1.25')
    path = tmp_path / 'snapshot.json'
    path.write_text(capture._encode_json(snapshot))
    output = StringIO()
    call_command('prepare_ifood_catalog_review', snapshot=str(path), channel='ifood', stdout=output)
    report = json.loads(output.getvalue())
    assert report['items'][0]['local_candidates'] == []


@pytest.mark.parametrize('contexts', [None, 'DEFAULT_SUFFIX', [True], [None]])
def test_context_shape_rejected(configured, responses, contexts):
    responses[0][0]['context'] = contexts
    with pytest.raises(capture.CaptureError):
        run_capture(responses)


def test_destination_created_during_capture_is_never_overwritten(tmp_path):
    tmp_path.chmod(0o700)
    target = tmp_path / 'snapshot.json'

    def raced_capture(**kwargs):
        target.write_bytes(b'prior evidence')
        return b'{"completed":true}'

    with patch('shopman.shop.management.commands.capture_ifood_catalog.capture_catalog', side_effect=raced_capture):
        with pytest.raises(CommandError):
            call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(target))
    assert target.read_bytes() == b'prior evidence'
    assert list(tmp_path.iterdir()) == [target]


def test_existing_symlink_is_rejected_before_capture(tmp_path):
    tmp_path.chmod(0o700)
    evidence = tmp_path / 'original.json'
    evidence.write_bytes(b'prior evidence')
    target = tmp_path / 'snapshot.json'
    target.symlink_to(evidence)
    with patch('shopman.shop.management.commands.capture_ifood_catalog.capture_catalog') as collect:
        with pytest.raises(CommandError, match='existe'):
            call_command('capture_ifood_catalog', merchant_id=M, catalog_id=C, context='DEFAULT', output=str(target))
    collect.assert_not_called()
    assert evidence.read_bytes() == b'prior evidence'
