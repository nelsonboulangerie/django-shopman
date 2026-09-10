"""Apoio compartilhado dos testes do backstage.

Só o que mais de um arquivo precisa e nenhum fixture do pytest expressa bem.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from shopman.backstage.api.production_freshness import (
    PRODUCTION_FRESHNESS_SECONDS,
    signed_action_proof,
    signed_source_revision,
)
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


def production_mutation_post(client, path: str, data=None, **kwargs):
    """POST a production mutation with the same fresh proof as the Nuxt client.

    Existing endpoint tests focus on domain outcomes. This helper keeps their
    transport precondition explicit and centralized; tests for absent, forged,
    cross-user and cross-surface proofs deliberately call ``client.post``.
    """
    body = dict(data or {})
    if "idempotency_key" not in body:
        return client.post(path, data, **kwargs)
    if {
        "projection_generated_at",
        "source_revision",
        "fresh_until",
        "contract_version",
    }.intersection(body):
        return client.post(path, body, **kwargs)

    from shopman.craftsman.models import WorkOrder

    selected_date = None
    match = re.search(r"/production/(\d+)/", path)
    work_order_id = int(match.group(1)) if match else None
    if work_order_id is not None:
        selected_date = WorkOrder.objects.filter(pk=work_order_id).values_list("target_date", flat=True).first()

    if path.endswith("/plan/"):
        projection_kind = "board"
        selected_date = body.get("target_date")
        action_kind = "plan"
        if not body.get("position_ref"):
            from shopman.stockman.models import Position

            default_position = Position.objects.filter(is_default=True).order_by("pk").first()
            body["position_ref"] = default_position.ref if default_position else "test-position"
        action_prefix = "plan_suggested" if body.get("source") == "suggested" else "plan"
        action_target = (
            str(body["work_order_id"])
            if body.get("work_order_id")
            else f"{body.get('recipe_id')}:{selected_date}:{body['position_ref']}"
        )
        suggested_quantity = (
            f":{format(Decimal(str(body['quantity'])).normalize(), 'f')}" if action_prefix == "plan_suggested" else ""
        )
        action_ref = f"{action_prefix}:{action_target}{suggested_quantity}"
    elif path.endswith("/start/"):
        projection_kind = "board"
        action_kind = "start"
        action_ref = f"start:{work_order_id}"
    elif path.endswith("/advance-step/"):
        projection_kind = "kds"
        action_kind = "advance_step"
        action_ref = f"advance_step:{work_order_id}"
    elif path.endswith("/void/"):
        status = WorkOrder.objects.filter(pk=work_order_id).values_list("status", flat=True).first()
        projection_kind = "board" if status == WorkOrder.Status.PLANNED else "kds"
        action_kind = "void"
        action_ref = f"void:{work_order_id}"
    elif path.endswith("/oven/arm/"):
        projection_kind = "qc"
        action_kind = "oven_arm"
        action_ref = f"oven_arm:{work_order_id}"
    elif path.endswith("/oven/conclude/"):
        projection_kind = "qc"
        action_kind = "oven_conclude"
        action_ref = f"oven_conclude:{work_order_id}"
    elif path.endswith("/quick-finish/"):
        projection_kind = "qc"
        action_kind = "quick_finish"
        action_ref = f"quick_finish:{body.get('recipe_id')}"
    else:
        projection_kind = "qc"
        action_kind = "finish"
        action_ref = f"finish:{work_order_id}"
        selected_date = selected_date or timezone.localdate()
    selected_date = selected_date or timezone.localdate()

    now = timezone.now().replace(microsecond=0)
    fresh_until = now + timedelta(seconds=PRODUCTION_FRESHNESS_SECONDS)
    selected_date_ref = selected_date.isoformat() if hasattr(selected_date, "isoformat") else str(selected_date or "")
    subject_ref = f"user:{client.session.get('_auth_user_id', '')}"
    source_revision = signed_source_revision(
        # A successful mutation refreshes the Nuxt projection before the next
        # gesture. Model that new snapshot deterministically per attempt while
        # keeping a retry of the same idempotency key on the same proof.
        digest=hashlib.sha256(
            f"test-projection:{body.get('idempotency_key', '')}".encode(),
        ).hexdigest(),
        generated_at=now,
        fresh_until=fresh_until,
        projection_kind=projection_kind,
        selected_date=selected_date_ref,
        subject_ref=subject_ref,
    )
    action_proof = signed_action_proof(
        action_ref=action_ref,
        action_kind=action_kind,
        href=path,
        expected_rev=body.get("expected_rev"),
        source_revision=source_revision,
        projection_generated_at=now,
        fresh_until=fresh_until,
        contract_version=1,
        projection_kind=projection_kind,
        selected_date=selected_date_ref,
        subject_ref=subject_ref,
    )
    body.update(
        projection_generated_at=now.isoformat(),
        source_revision=source_revision,
        fresh_until=fresh_until.isoformat(),
        contract_version=1,
        action_ref=action_ref,
        action_proof=action_proof,
    )
    return client.post(path, body, **kwargs)
