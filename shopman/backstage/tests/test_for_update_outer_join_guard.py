"""A trava ``shopman/shop/tests/postgres_lock_rule.py`` aplica no SQLite a regra de lock do PostgreSQL.

O PostgreSQL recusa ``FOR UPDATE`` no lado anulável de um OUTER JOIN; o SQLite da
suíte ignora ``FOR UPDATE`` e deixava passar (pulso da gaveta, #1640). Estes
testes provam que a trava pega a forma do defeito, inclusive aninhada e montada em
etapas, e deixa passar a correção (``of=("self",)``) e o JOIN que é INNER.
"""

from __future__ import annotations

import pytest
from django.db import transaction

from shopman.backstage.models import KDSTicket, PrintJob
from shopman.shop.tests.postgres_lock_rule import PostgresForUpdateOuterJoinError

pytestmark = pytest.mark.django_db


def test_fk_anulavel_sem_of_reprova():
    with transaction.atomic(), pytest.raises(PostgresForUpdateOuterJoinError, match="cashman_terminal"):
        list(PrintJob.objects.select_for_update().select_related("target_terminal").filter(pk=-1))


def test_consulta_montada_em_etapas_tambem_reprova():
    query = PrintJob.objects.filter(pk=-1)
    query = query.select_related("target_terminal")
    with transaction.atomic(), pytest.raises(PostgresForUpdateOuterJoinError):
        query.select_for_update().first()


def test_of_self_trava_so_a_linha_e_passa():
    with transaction.atomic():
        assert (
            PrintJob.objects.select_for_update(of=("self",)).select_related("target_terminal").filter(pk=-1).first()
            is None
        )


def test_of_apontando_para_o_lado_anulavel_reprova():
    with transaction.atomic(), pytest.raises(PostgresForUpdateOuterJoinError):
        list(
            PrintJob.objects.select_for_update(of=("self", "target_terminal"))
            .select_related("target_terminal")
            .filter(pk=-1)
        )


def test_relacao_aninhada_anulavel_reprova():
    # ``kds_instance`` é obrigatória (INNER), mas ``print_terminal`` é anulável:
    # o segundo salto entra por OUTER JOIN e um FOR UPDATE amplo o travaria.
    with transaction.atomic(), pytest.raises(PostgresForUpdateOuterJoinError, match="cashman_terminal"):
        list(KDSTicket.objects.select_for_update().select_related("kds_instance__print_terminal").filter(pk=-1))


def test_join_obrigatorio_passa():
    with transaction.atomic():
        assert KDSTicket.objects.select_for_update().select_related("kds_instance").filter(pk=-1).first() is None
