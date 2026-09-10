"""Diagnósticos sintéticos de lacunas atuais, NÃO critérios de aceite positivos."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.response import Response
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import IdempotencyKey

from shopman.backstage.api.operations import _cash_idempotent, _open_cash_shift_for_request, _terminal_do_pedido
from shopman.backstage.services import pos

pytestmark = pytest.mark.django_db(transaction=True)

@pytest.fixture
def runtime():
    Terminal.objects.all().delete()
    actor = User.objects.create_user('pdv-probe', is_staff=True)
    shifts = {}
    for ref in ['A', 'B']:
        Terminal.objects.create(ref=ref, label=ref)
        shifts[ref] = pos.open_cash_shift(operator=actor, terminal_ref=ref)
    return actor, shifts

def test_runtime_mismatch(runtime):
    actor, shifts = runtime
    request = SimpleNamespace(user=actor, data={'terminal_ref': 'A'}, COOKIES={})
    with patch('shopman.backstage.station_trust.station_ref', return_value='B'):
        selected = _terminal_do_pedido(request)
        default = _open_cash_shift_for_request(request)
        pos.register_cash_movement(operator=actor, terminal_ref=selected,
                                   movement_type='suprimento', amount_raw='10,00')
    entry = Entry.objects.get(kind=Entry.Kind.CASH_IN)
    print(json.dumps({'probe':'F01/F02','station':'B','selected':selected,
                      'sale_helper_shift_terminal':default.terminal.ref,
                      'entry_terminal':entry.shift.terminal.ref,'amount_q':entry.amount_q}))
    assert selected == 'A' and default == shifts['A'] and entry.shift == shifts['A']

def test_receipt_crash_and_expired_replay(runtime):
    actor, shifts = runtime
    request = SimpleNamespace(user=actor, data={'client_request_id':'pdv-probe-crash'})
    def execute():
        pos.register_cash_movement(operator=actor, terminal_ref='A',
                                   movement_type='suprimento', amount_raw='10,00')
        return Response({'ok':True})
    original = IdempotencyKey.save
    def crash(self, *args, **kwargs):
        if self.status == 'done':
            raise RuntimeError('synthetic failure saving receipt')
        return original(self, *args, **kwargs)
    with patch.object(IdempotencyKey, 'save', crash), pytest.raises(RuntimeError):
        _cash_idempotent(request, acao='pdv_probe', executar=execute)
    claim = IdempotencyKey.objects.get(key='pdv-probe-crash')
    first_count = Entry.objects.filter(kind=Entry.Kind.CASH_IN).count()
    assert first_count == 1 and claim.status == 'in_progress'
    IdempotencyKey.objects.filter(pk=claim.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    response = _cash_idempotent(request, acao='pdv_probe', executar=execute)
    last_count = Entry.objects.filter(kind=Entry.Kind.CASH_IN).count()
    print(json.dumps({'probe':'F05','first_effects':first_count,'claim_after_crash':claim.status,
                      'effects_after_expired_replay':last_count,'response':response.status_code}))
    assert last_count == 2

def test_changed_payload_and_actor_replay(runtime):
    actor, shifts = runtime
    request = SimpleNamespace(user=actor,data={'client_request_id':'pdv-probe-replay','amount':'10,00'})
    def execute():
        pos.register_cash_movement(operator=request.user, terminal_ref='A',
                                        movement_type='suprimento', amount_raw=request.data['amount'])
        return Response({'amount':request.data['amount']})
    first=_cash_idempotent(request,acao='pdv_probe',executar=execute)
    request.user=User.objects.create_user('pdv-probe-other',is_staff=True)
    request.data['amount']='20,00'
    replay=_cash_idempotent(request,acao='pdv_probe',executar=execute)
    print(json.dumps({'probe':'F04','first':first.data,'changed_actor_payload_replay':replay.data,
                      'effects':Entry.objects.filter(kind=Entry.Kind.CASH_IN).count()}))
    assert replay.data == {'amount':'10,00'}
