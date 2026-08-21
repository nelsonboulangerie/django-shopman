"""Dois envios simultâneos do MESMO webhook: um processa, o outro é replay.

⚠️ Só roda contra PostgreSQL, e o motivo é o defeito em si. Em SQLite o
`IntegrityError` não envenena a transação; no Postgres, aborta o bloco inteiro,
e o `except` que tenta consultar depois estoura com "current transaction is
aborted". O guarda contra replay falhava exatamente na corrida que ele existe
para tratar — e por rodar só em SQLite, a suíte nunca viu.

Controle positivo (medido antes de consertar): sem o savepoint em
`claim()`, a thread perdedora morre com `TransactionManagementError` e a
asserção de "duas respostas coerentes" reprova.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection, transaction

from shopman.shop.services import webhook_idempotency as guard

requires_postgres = pytest.mark.skipif(
    "sqlite" in connection.settings_dict.get("ENGINE", ""),
    reason="a corrida só se reproduz com o abort de transação do PostgreSQL",
)

SCOPE = "efi"
KEY = "evt-corrida-1"


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_dois_claims_simultaneos_do_mesmo_evento_nao_envenenam_a_transacao():
    partida = threading.Barrier(2)
    resultados: list[guard.WebhookClaim] = []
    erros: list[BaseException] = []

    def reivindicar():
        try:
            partida.wait(timeout=10)
            with transaction.atomic():
                resultados.append(guard.claim(SCOPE, KEY))
        except BaseException as exc:  # noqa: BLE001 — o teste EXISTE para ver a exceção
            erros.append(exc)
        finally:
            connection.close()

    fios = [threading.Thread(target=reivindicar) for _ in range(2)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=20)

    # É isto que o código velho quebrava: a perdedora estourava com
    # TransactionManagementError em vez de devolver um claim.
    assert not erros, f"a corrida derrubou uma das requisições: {erros!r}"
    assert len(resultados) == 2

    # Uma processa, a outra é recusada como já-em-andamento. Nunca as duas.
    podem = [r for r in resultados if r.can_process]
    assert len(podem) == 1, "as duas requisições acharam que podiam processar o mesmo evento"
    outra = next(r for r in resultados if not r.can_process)
    assert outra.in_progress is True
    assert outra.response_code == 409

    # E a unicidade é do BANCO: uma linha só para (scope, key).
    from shopman.orderman.models import IdempotencyKey

    assert IdempotencyKey.objects.filter(scope=SCOPE, key=KEY).count() == 1
