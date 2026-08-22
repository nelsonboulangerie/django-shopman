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


def trust_station(client, terminal_ref: str = "balcao") -> str:
    """Faz deste ``client`` uma ESTAÇÃO reconhecida — e nada além disso.

    É o balcão depois de provisionado: um cookie de confiança de dispositivo,
    sem ninguém logado. Um teste que quer "a loja de manhã, travada" começa
    aqui, e a diferença entre isto e ``force_login`` é o assunto inteiro da D1
    Parte B — a estação abre a antessala, a pessoa abre o resto.

    Devolve o ``terminal_ref`` para o teste conferir o que a tela recebe.
    """
    from shopman.doorman.models import SubjectType, TrustedDevice

    from shopman.backstage.station_trust import station_cookie_name

    _, raw_token = TrustedDevice.create_for(
        subject_type=SubjectType.STATION,
        subject_id=terminal_ref,
        user_agent="teste",
        ip_address="127.0.0.1",
    )
    client.cookies[station_cookie_name(terminal_ref)] = raw_token
    return terminal_ref
