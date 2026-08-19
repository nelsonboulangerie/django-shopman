"""Apoio compartilhado dos testes do backstage.

Só o que mais de um arquivo precisa e nenhum fixture do pytest expressa bem.
"""

from __future__ import annotations

from shopman.backstage.models import ImportBatch


def historical_batch(source: str = "yooga") -> ImportBatch:
    """Um lote para pendurar vendas históricas de fixture.

    Toda venda histórica tem proveniência declarada (FK obrigatória); um teste
    que só quer "existir venda no passado" não precisa inventar arquivo nem
    hash — ganha um lote de fixture por origem, reutilizado dentro do teste.
    """
    batch, _ = ImportBatch.objects.get_or_create(
        source=source,
        notes="fixture de teste",
        defaults={"status": ImportBatch.Status.DONE},
    )
    return batch


def install_bi_vocabularies() -> None:
    """Os de-paras de categoria e de forma de pagamento, como o seed os instala.

    As regras saíram do código e viraram linhas (``CategoryAlias``,
    ``PaymentMethodAlias``); ``migrate`` cria as tabelas vazias, e é o
    ``setup_bi_reference``/``seed`` que as enche. Um teste que exercita a
    leitura de categoria ou de forma de pagamento do histórico chama isto — a
    mesma lista, um lugar só.
    """
    from config.management.commands.seed import Command as Seed

    Seed()._seed_bi_aliases()
