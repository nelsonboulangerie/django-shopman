"""Excluir a conta tem de alcançar o PEDIDO, não só o cadastro.

O defeito (P0, medido em 20/08 no banco do seed): `anonymize_customer` não tinha
uma única referência a `Order`, `Session` ou `handle_ref`. Depois de "Excluir
minha conta" pela tela, os 29 pedidos do titular continuavam com o telefone em
`orderman_order.handle_ref`, em texto puro — e o telefone É a identidade desta
loja, porque é o único login. Quem tivesse acesso ao Admin, ao banco ou a um
relatório re-identificava a pessoa e reconstruía tudo que ela comprou.

E a tela afirmava o contrário, por escrito, no exato gesto do art. 18 da LGPD.

Por que a suíte não pegou: `test_anonymize_lgpd.py` cobria bem a FONTE DE VERDADE
do cadastro (ContactPoint, document, metadata, identidades) e nunca criou um
pedido. O teste vizinho afirmava algo mais fraco do que a tela prometia.

O teste principal aqui não confere campo a campo: varre TODA coluna textual e
JSON do banco atrás do telefone e do nome. É a mesma prova que se faz no
staging, e ela não tem como ficar desatualizada quando alguém acrescentar uma
tabela nova.
"""

from __future__ import annotations

import pytest
from django.db import connection, transaction
from shopman.guestman.models import Customer
from shopman.orderman.exceptions import CommitError
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services import CommitService

from shopman.shop.models import Channel
from shopman.shop.services.account import anonymize_customer

pytestmark = pytest.mark.django_db

PHONE = "+5543991234567"
FIRST_NAME = "Marina"
LAST_NAME = "Kobayashi"
ADDRESS = "Rua das Flores 123 - Centro - Londrina"


def _customer():
    return Customer.objects.create(
        ref="CLI-ANON-ORD",
        first_name=FIRST_NAME,
        last_name=LAST_NAME,
        phone=PHONE,
        email="marina@example.com",
    )


def _order_for(customer, *, channel_ref="web", origin="whatsapp"):
    """Um pedido pelo caminho real: Session com PII → CommitService → Order.

    Importa passar pelo commit de verdade, porque é o `CommitService` que copia
    a chave `customer` de `session.data` para `order.data` E sela a cópia
    integral de `session.data` dentro de `order.snapshot["data"]`. Um pedido
    montado à mão não teria a segunda cópia, e o teste passaria sem tocar no
    lugar onde o PII se escondia.
    """
    Channel.objects.get_or_create(ref=channel_ref, defaults={"name": channel_ref})
    session = Session.objects.create(
        session_key=generate_session_key(),
        channel_ref=channel_ref,
        state="open",
        handle_type="phone",
        handle_ref=customer.phone,
        items=[{"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"}],
        data={
            "customer": {
                "ref": customer.ref,
                "name": f"{FIRST_NAME} {LAST_NAME}",
                "phone": customer.phone,
                "email": customer.email,
            },
            "customer_ref": customer.ref,
            "fulfillment_type": "delivery",
            "delivery_address": ADDRESS,
            "delivery_address_structured": {"route": "Rua das Flores", "street_number": "123"},
            "delivery_fee_q": 500,
            "order_notes": f"Entregar para {FIRST_NAME}, tocar a campainha",
            "origin_channel": origin,
        },
    )
    result = CommitService.commit(
        session_key=session.session_key,
        channel_ref=channel_ref,
        idempotency_key=generate_idempotency_key(),
    )
    order = Order.objects.get(ref=result.order_ref)
    if not order.handle_ref:
        Order.objects.filter(pk=order.pk).update(handle_type="phone", handle_ref=customer.phone)
        order.refresh_from_db()
    return order


def _sweep(needles: tuple[str, ...]) -> list[str]:
    """Onde no banco INTEIRO ainda aparece cada agulha.

    Introspecção em vez de lista de tabelas escrita à mão: uma tabela nova que
    passe a guardar o telefone entra na varredura sozinha. Casta tudo para texto
    (portável entre sqlite e Postgres) e pula a coluna que não aceitar o cast.
    """
    hits: list[str] = []
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        for table in tables:
            try:
                columns = [c.name for c in connection.introspection.get_table_description(cursor, table)]
            except Exception:
                continue
            for column in columns:
                for needle in needles:
                    sql = (
                        f"SELECT count(*) FROM {connection.ops.quote_name(table)} "
                        f"WHERE CAST({connection.ops.quote_name(column)} AS TEXT) LIKE %s"
                    )
                    try:
                        with transaction.atomic():
                            cursor.execute(sql, [f"%{needle}%"])
                            found = cursor.fetchone()[0]
                    except Exception:
                        continue
                    if found:
                        hits.append(f"{table}.{column} <- {needle!r} x{found}")
    return hits


def test_a_varredura_do_banco_nao_acha_mais_o_titular():
    """A prova do dono: excluir pela tela e varrer o banco inteiro."""
    customer = _customer()
    for _ in range(3):
        _order_for(customer)

    antes = _sweep((PHONE, FIRST_NAME))
    assert any("orderman_order" in hit for hit in antes), (
        f"controle positivo: o teste tem de VER o telefone antes de apagar, senão não prova nada. Achados: {antes}"
    )

    anonymize_customer(customer)

    depois = _sweep((PHONE, FIRST_NAME, LAST_NAME, ADDRESS))
    assert depois == [], f"PII sobreviveu à exclusão: {depois}"


def test_o_pedido_troca_o_telefone_por_um_pseudonimo_estavel():
    customer = _customer()
    order_a = _order_for(customer)
    order_b = _order_for(customer)

    anonymize_customer(customer)

    order_a.refresh_from_db()
    order_b.refresh_from_db()
    assert order_a.handle_ref == order_b.handle_ref, "o histórico do titular tem de continuar agrupado"
    assert order_a.handle_ref.startswith("ANON-")
    assert order_a.handle_type == "anonymized"
    # O pseudônimo não pode ser derivado do telefone: sha256 de número brasileiro
    # é reversível por força bruta, e seria o número com outra roupa.
    import hashlib

    assert hashlib.sha256(PHONE.encode()).hexdigest()[:12] not in order_a.handle_ref


def test_o_pedido_perde_o_pii_e_guarda_a_compra():
    customer = _customer()
    order = _order_for(customer)

    anonymize_customer(customer)
    order.refresh_from_db()

    for key in ("customer", "delivery_address", "delivery_address_structured", "order_notes"):
        assert key not in order.data, key
        assert key not in (order.snapshot or {}).get("data", {}), f"snapshot.{key}"
    # O que descreve a COMPRA fica: é dele que vivem a obrigação fiscal e o B.I.;
    # o ref do titular, embora interno, continua correlacionável e sai.
    assert "customer_ref" not in order.data
    assert order.data.get("fulfillment_type") == "delivery"
    assert order.snapshot["items"]
    assert order.total_q > 0


def test_exclusao_limpa_texto_pessoal_das_tres_copias_do_meta_do_item():
    """OrderItem, Session.items e snapshot não podem divergir na exclusão."""
    import json

    from shopman.storefront.services.account_export import build_account_export

    customer = _customer()
    order = _order_for(customer)
    session = Session.objects.get(session_key=order.session_key, channel_ref=order.channel_ref)
    order_item = order.items.get(line_id="L1")
    session_item = session.session_items.get(line_id="L1")

    sentinels = {
        "order_item": "PII-ORDER-ITEM-MARINA",
        "session_item": "PII-SESSION-ITEM-MARINA",
        "snapshot_item": "PII-SNAPSHOT-ITEM-MARINA",
    }

    def meta_with(personal_text):
        return {
            "customer_note": personal_text,
            "gift_wrap": True,
            "_disc": {"type": "manual", "amount_q": 100},
            "fiscal": {"ncm": "19059090"},
            "customization": {
                "choice_ref": "SIZE-L",
                "price_delta_q": 200,
                "note": personal_text,
                "text": personal_text,
                "message": personal_text,
            },
        }

    order_item.meta = meta_with(sentinels["order_item"])
    order_item.save(update_fields=["meta"])
    session_item.meta = meta_with(sentinels["session_item"])
    session_item.save(update_fields=["meta"])
    snapshot = dict(order.snapshot)
    snapshot_items = [dict(item) for item in snapshot["items"]]
    snapshot_items[0]["meta"] = meta_with(sentinels["snapshot_item"])
    snapshot["items"] = snapshot_items
    Order.objects.filter(pk=order.pk).update(snapshot=snapshot)

    before = _sweep(tuple(sentinels.values()))
    assert any("orderman_orderitem.meta" in hit for hit in before)
    assert any("orderman_sessionitem.meta" in hit for hit in before)
    assert any("orderman_order.snapshot" in hit for hit in before)

    artifact = build_account_export(customer)
    exported = json.load(artifact)
    artifact.close()
    exported_order_item = next(row for row in exported["order_items"] if row["order_ref"] == order.ref)
    exported_session_item = next(
        row for row in exported["order_session_items"] if row["session_id"] == session.pk
    )
    exported_order = next(row for row in exported["orders"] if row["ref"] == order.ref)
    assert sentinels["order_item"] in str(exported_order_item["meta"])
    assert sentinels["session_item"] in str(exported_session_item["meta"])
    assert sentinels["snapshot_item"] in str(exported_order["snapshot_items"][0]["meta"])

    anonymize_customer(customer)

    order.refresh_from_db()
    order_item.refresh_from_db()
    session_item.refresh_from_db()
    expected_commercial = {
        "gift_wrap": True,
        "_disc": {"type": "manual", "amount_q": 100},
        "fiscal": {"ncm": "19059090"},
        "customization": {"choice_ref": "SIZE-L", "price_delta_q": 200},
    }
    assert order_item.meta == expected_commercial
    assert session_item.meta == expected_commercial
    assert order.snapshot["items"][0]["meta"] == expected_commercial
    assert _sweep(tuple(sentinels.values())) == []


def test_exportacao_e_exclusao_alinham_eventos_e_alerta_de_cancelamento():
    import json

    from shopman.backstage.models import OperatorAlert
    from shopman.storefront.services.account_export import build_account_export

    customer = _customer()
    order = _order_for(customer)
    session = Session.objects.get(session_key=order.session_key, channel_ref=order.channel_ref)
    sentinels = {
        "order_note": "PII-ORDER-EVENT-NOTE",
        "order_reason": "PII-ORDER-EVENT-REASON",
        "session_from": "PII-SESSION-FROM-REF",
        "session_to": "PII-SESSION-TO-REF",
        "session_text": "PII-SESSION-FREE-TEXT",
    }
    protocol = "SC-20260916-KEEP1234"

    note_event = order.emit_event(
        "operator_comment",
        actor="operator:test",
        payload={"note": sentinels["order_note"], "operational_code": "handover"},
    )
    reason_event = order.emit_event(
        "customer_cancellation_requested",
        actor="customer:self-service",
        payload={"protocol": protocol, "reason": sentinels["order_reason"]},
    )
    renamed_event = session.emit_event(
        "tab_renamed",
        actor="operator:test",
        payload={
            "from_ref": sentinels["session_from"],
            "to_ref": sentinels["session_to"],
            "count": 2,
        },
    )
    free_text_event = session.emit_event(
        "manual_context",
        actor="operator:test",
        payload={
            "note": sentinels["session_text"],
            "reason": sentinels["session_text"],
            "text": sentinels["session_text"],
            "message": sentinels["session_text"],
            "sku": "CROIS-01",
        },
    )
    alert = OperatorAlert.objects.create(
        type="customer_cancellation_requested",
        severity="warning",
        audience="orders",
        order_ref=order.ref,
        message=(
            f"O cliente solicitou análise de cancelamento do pedido {order.ref}. "
            f"Protocolo {protocol}. Abra o pedido para decidir o cancelamento e eventual estorno. "
            f"Motivo informado: {sentinels['order_reason']}"
        ),
    )
    OperatorAlert.objects.create(
        type="payment_failed",
        severity="error",
        order_ref=order.ref,
        message="alerta operacional fora do footprint de cancelamento",
    )
    before = _sweep((sentinels["order_reason"],))
    assert any("orderman_orderevent.payload" in hit for hit in before)
    assert any("backstage_operatoralert.message" in hit for hit in before)

    artifact = build_account_export(customer)
    exported = json.load(artifact)
    artifact.close()
    order_events = {row["type"]: row for row in exported["order_events"]}
    session_events = {row["type"]: row for row in exported["order_session_events"]}
    assert order_events["operator_comment"]["payload"] == {"note": sentinels["order_note"]}
    assert order_events["customer_cancellation_requested"]["payload"] == {
        "protocol": protocol,
        "reason": sentinels["order_reason"],
    }
    assert session_events["tab_renamed"]["payload"] == {
        "from_ref": sentinels["session_from"],
        "to_ref": sentinels["session_to"],
        "count": 2,
    }
    assert session_events["manual_context"]["payload"] == {
        "sku": "CROIS-01",
        "note": sentinels["session_text"],
        "reason": sentinels["session_text"],
        "text": sentinels["session_text"],
        "message": sentinels["session_text"],
    }
    assert len(exported["order_cancellation_alerts"]) == 1
    exported_alert = exported["order_cancellation_alerts"][0]
    assert exported_alert["protocol"] == protocol
    assert exported_alert["reason"] == sentinels["order_reason"]
    assert "message" not in exported_alert

    anonymize_customer(customer)

    note_event.refresh_from_db()
    reason_event.refresh_from_db()
    renamed_event.refresh_from_db()
    free_text_event.refresh_from_db()
    alert.refresh_from_db()
    assert note_event.payload == {"operational_code": "handover"}
    assert reason_event.payload == {"protocol": protocol}
    assert renamed_event.payload == {"count": 2}
    assert free_text_event.payload == {"sku": "CROIS-01"}
    assert protocol in alert.message
    assert "Motivo informado:" not in alert.message
    assert _sweep(tuple(sentinels.values())) == []


def test_a_sessao_recebe_o_mesmo_tratamento():
    customer = _customer()
    _order_for(customer)

    anonymize_customer(customer)

    for session in Session.objects.all():
        assert "customer" not in (session.data or {})
        assert session.handle_ref != PHONE


def test_o_telefone_reciclado_nao_abre_o_historico_antigo():
    """Quem receber o número depois não pode enxergar os pedidos de antes.

    Não é hipótese remota: operadora recicla número. Trocar só o VALOR do handle
    e deixar `handle_type="phone"` manteria o pedido casando com o filtro de
    identidade por telefone.
    """
    from shopman.shop.services.customer_orders import customer_identity_filter

    customer = _customer()
    _order_for(customer)
    anonymize_customer(customer)

    query = customer_identity_filter(customer_ref="CLI-OUTRO", phone=PHONE)
    assert Order.objects.filter(query).count() == 0


def test_exclusao_nao_altera_pedido_com_dono_canonico_diferente():
    current = _customer()
    previous = Customer.objects.create(ref="CLI-ANTERIOR", first_name="Outra pessoa")
    alien = Order.objects.create(
        ref="ORDER-OUTRO-DONO",
        channel_ref="web",
        handle_type="phone",
        handle_ref=current.phone,
        status="completed",
        data={
            "customer_ref": previous.ref,
            "customer": {"ref": previous.ref, "phone": current.phone},
        },
    )

    anonymize_customer(current)

    alien.refresh_from_db()
    assert alien.handle_type == "phone"
    assert alien.handle_ref == PHONE
    assert alien.data["customer_ref"] == previous.ref


def test_commit_recusa_sessao_antiga_de_customer_inativo() -> None:
    customer = _customer()
    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})
    session = Session.objects.create(
        session_key=generate_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref=customer.phone,
        items=[{"sku": "CROIS-01", "qty": 1, "unit_price_q": 500, "line_id": "L1"}],
        data={
            "customer_ref": customer.ref,
            "customer": {"ref": customer.ref, "phone": customer.phone},
        },
    )
    customer.is_active = False
    customer.save(update_fields=["is_active"])

    with pytest.raises(CommitError) as caught:
        CommitService.commit(
            session_key=session.session_key,
            channel_ref="web",
            idempotency_key=generate_idempotency_key(),
        )

    assert caught.value.code == "customer_inactive"
    assert not Order.objects.filter(session_key=session.session_key).exists()


def test_commit_recusa_ref_e_telefone_de_clientes_diferentes() -> None:
    referenced = Customer.objects.create(
        ref="CLI-IDENTITY-REF",
        first_name="Referência",
        phone="+5543991234501",
    )
    phone_owner = Customer.objects.create(
        ref="CLI-IDENTITY-PHONE",
        first_name="Telefone",
        phone="+5543991234502",
    )
    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})
    session = Session.objects.create(
        session_key=generate_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref=phone_owner.phone,
        items=[{"sku": "CROIS-01", "qty": 1, "unit_price_q": 500, "line_id": "L1"}],
        data={
            "customer_ref": referenced.ref,
            "customer": {"ref": referenced.ref, "phone": phone_owner.phone},
        },
    )

    with pytest.raises(CommitError) as caught:
        CommitService.commit(
            session_key=session.session_key,
            channel_ref="web",
            idempotency_key=generate_idempotency_key(),
        )

    assert caught.value.code == "customer_identity_mismatch"
    assert not Order.objects.filter(session_key=session.session_key).exists()


def test_o_perfil_de_rfm_nao_sobrevive():
    from shopman.guestman import CustomerInsight, InsightService

    customer = _customer()
    _order_for(customer)
    InsightService.recalculate(customer.ref)
    assert CustomerInsight.objects.filter(customer=customer).exists()

    anonymize_customer(customer)

    assert not CustomerInsight.objects.filter(customer=customer).exists()


def test_a_loja_apaga_o_que_e_dela():
    """Favoritos e aviso de reposição vivem em `storefront` e ficavam para trás."""
    from shopman.storefront.models import CustomerFavorite, StockAlertSubscription
    from shopman.storefront.services import stock_alerts

    customer = _customer()
    CustomerFavorite.objects.create(customer_ref=customer.ref, sku="CROIS-01")
    stock_alerts.subscribe("CROIS-01", customer=customer, adult_declared=True)

    anonymize_customer(customer)

    assert not CustomerFavorite.objects.filter(customer_ref=customer.ref).exists()
    assert not StockAlertSubscription.objects.filter(contact_phone=PHONE).exists()


def test_rodar_duas_vezes_nao_estoura():
    customer = _customer()
    _order_for(customer)
    anonymize_customer(customer)
    anonymize_customer(customer)
    assert _sweep((PHONE,)) == []


def test_exportacao_e_exclusao_nao_reivindicam_legado_so_por_telefone():
    """Telefone atual não prova autoria de pedido histórico ownerless."""
    import json

    from shopman.storefront.services.account_export import build_account_export

    customer = _customer()
    order = _order_for(customer)
    # Pedido "órfão": identificado só pelo telefone, sem customer_ref no data.
    orphan = _order_for(customer)
    data = dict(orphan.data)
    data.pop("customer_ref", None)
    data.pop("customer", None)
    Order.objects.filter(pk=orphan.pk).update(data=data)

    artifact = build_account_export(customer)
    exported = json.load(artifact)
    artifact.close()
    refs = {row["ref"] for row in exported["orders"]}
    assert order.ref in refs
    assert orphan.ref not in refs
    assert exported["customer"]["phone"] == PHONE

    anonymize_customer(customer)
    orphan.refresh_from_db()
    assert orphan.handle_ref == PHONE
    assert orphan.data == data


def test_o_lado_do_login_tambem_esquece_o_telefone():
    """Dois vazamentos que só a varredura acha, e só depois de um login real.

    Medido em 20/08 excluindo a conta pela tela: sobravam o telefone dentro de
    `CustomerUser.metadata` e o telefone em cada `VerificationCode` emitido para
    ele, incluindo o código que a pessoa acabou de usar para provar que era ela
    antes de mandar apagar tudo.
    """
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import CustomerUser, VerificationCode

    customer = _customer()
    user = get_user_model().objects.create_user(username="cli-anon-ord", first_name=FIRST_NAME)
    CustomerUser.objects.create(user=user, customer_id=customer.uuid, metadata={"phone": PHONE})
    VerificationCode.objects.create(
        customer_id=customer.uuid,
        target_value=PHONE,
        purpose=VerificationCode.Purpose.LOGIN,
    )

    anonymize_customer(customer)

    assert _sweep((PHONE, FIRST_NAME)) == []
