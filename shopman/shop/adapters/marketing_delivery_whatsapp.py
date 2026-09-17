"""Entrega durável de campanha por WhatsApp: mensagem direta, uma por destino.

É a peça que faltava entre o ledger de Marketing (outbox → destino → tentativa) e o
ManyChat da ADR-009. Sem ela, a campanha de WhatsApp aprovada no cockpit ficava na
fila para sempre: ``SHOPMAN_MARKETING_DELIVERY_ADAPTERS`` só conhecia as plataformas
de postagem pública.

O contrato é o mesmo dos adapters de publicação (``send``/``lookup``/
``is_available``), e as regras são as do WhatsApp:

- **Nenhum atalho de segurança.** O modo ``blocked``/``canary``/``open``
  (``manychat_marketing_safety``) é conferido aqui, na última porta, antes de
  resolver contato ou gravar campo. ``notification_manychat.send`` confere de novo.
- **O que a tela mostrou é o que sai.** Corpo, link e foto vêm do artefato aprovado;
  produto, preço e disponibilidade vêm das variáveis e dos fatos SELADOS nele. O
  catálogo vivo não é lido — se o fato mudou, o ledger expira o destino antes daqui
  (``marketing_facts.validate_for_dispatch``). Só o contato (telefone, primeiro nome)
  sai do destino materializado, porque é para ele que a mensagem vai.
- **Resultado honesto.** Aceite do ManyChat é ``accepted_unconfirmed``, nunca
  "entregue"; falha depois de possível escrita é ``unknown``, sem repetição; recusa
  antes de chamar é ``failed_final`` com código; contato ocupado por outra mensagem
  com flow é o adiamento que o ledger já reagenda (``subscriber_busy``).

Nenhum log carrega telefone, nome, ``customer_ref`` ou resposta do fornecedor.
"""

from __future__ import annotations

import hmac
import logging
from typing import NoReturn

from django.conf import settings

from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
)

PLATFORM = "whatsapp"
EVENT = "announcement_published"
#: O mesmo convite dos outros dois caminhos que mandam este evento (onda legada e
#: teste sandbox): o flow aprovado lê ``{{cta}}`` do perfil do contato.
CTA = "Garanta o seu:"
#: Variáveis seladas no conteúdo aprovado que o flow pode ler — o vocabulário de
#: ``campaign.available_variables`` menos o nome do cliente, que vem do destino. O que
#: não estiver no artefato sai VAZIO (``MARKETING_FLOW_FIELDS``), nunca herdado.
SEALED_VARIABLES = (
    "product_name",
    "product_sku",
    "price",
    "available_qty",
    "availability_phrase",
    "product_image_url",
    "store_name",
    "hashtags",
    "quality",
    "time",
)
ACCEPTED_CODE = "whatsapp_flow_accepted"
OUTCOME_UNKNOWN_CODE = "whatsapp_outcome_unknown"
logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Flag de plataforma + credencial ManyChat + saída externa permitida.

    O modo de segurança NÃO entra aqui de propósito: a prontidão mostra o motivo exato
    dele (``manychat_custom_fields_unverified``, ensaio etc.), e o ``send`` recusa na
    última porta.
    """

    if not getattr(settings, "SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED", False):
        return False
    from shopman.shop.adapters import notification_manychat
    from shopman.shop.adapters._external import inert

    return bool(
        notification_manychat.is_available()
        and not inert("SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG")
    )


def send(*, artifact, target_key: str, idempotency_token: str) -> ProviderOutcome:
    """Uma mensagem com flow para o destino desta tentativa, no máximo."""

    if not is_available():
        _refuse("whatsapp_delivery_disabled", target_key)
    if getattr(artifact, "platform", "") != PLATFORM:
        _refuse("whatsapp_artifact_mismatch", target_key)

    target = _sending_target(
        artifact=artifact,
        target_key=target_key,
        idempotency_token=idempotency_token,
    )
    member = target.member
    customer = member.customer if member is not None and member.customer_id else None
    customer_ref = str(customer.ref) if customer is not None else ""

    from shopman.shop.services import manychat_marketing_safety

    refusal = manychat_marketing_safety.recipient_refusal(customer_ref)
    if refusal:
        _refuse(refusal, target_key)

    _require_sealed_flow(artifact, target_key)
    phone = _recipient_phone(target, customer=customer, target_key=target_key)
    context = {
        **sealed_context(target.artifact, artifact),
        # ``customer_ref`` não vira campo no ManyChat (denylist do adapter): é o que a
        # porta do ``notification_manychat`` confere contra a lista do ensaio.
        "customer_ref": customer_ref,
        "customer_name": (getattr(customer, "first_name", "") or "").strip(),
    }

    from shopman.shop.adapters import notification_manychat

    try:
        result = notification_manychat.send(
            recipient=phone,
            template=EVENT,
            context=context,
        )
    except Exception:
        # Pode ter escrito campo ou disparado o flow antes de falhar: nunca repetir.
        logger.warning(
            "marketing.whatsapp_delivery_unknown target=%s", _short(target_key)
        )
        raise ProviderCallFailure(ProviderOutcomeKind.UNKNOWN, OUTCOME_UNKNOWN_CODE) from None

    if isinstance(result, dict):
        code = str(result.get("error") or "")
        if manychat_marketing_safety.is_flow_deferral(code):
            # Nada foi escrito: outra mensagem com flow ainda assenta neste contato.
            logger.info(
                "marketing.whatsapp_delivery_deferred code=%s target=%s",
                code,
                _short(target_key),
            )
            raise ProviderCallFailure(
                ProviderOutcomeKind.NOT_ATTEMPTED,
                code,
                _retry_after(result.get("retry_after_seconds")),
            )
        result = result.get("success") is True
    if result is True:
        logger.info(
            "marketing.whatsapp_delivery_accepted target=%s artifact=%s",
            _short(target_key),
            str(getattr(artifact, "artifact_hash", ""))[:12],
        )
        # Assinante não é recibo: nenhum identificador do ManyChat vira receipt.
        return ProviderOutcome(
            kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
            code=ACCEPTED_CODE,
            retryable=False,
        )
    # ``False`` sai antes do ``sendFlow`` (contato não resolvido, modo fechado entre
    # as duas portas) ou de uma recusa explícita dele: nada foi aceito.
    _refuse("whatsapp_provider_refused", target_key)


def lookup(
    *, target_key: str, idempotency_token: str, provider_receipt_ref: str
) -> ProviderOutcome:
    """O ManyChat não tem recibo consultável: incerteza continua incerteza."""

    del idempotency_token, provider_receipt_ref
    logger.info("marketing.whatsapp_lookup_unavailable target=%s", _short(target_key))
    raise ProviderCallFailure(
        ProviderOutcomeKind.NOT_ATTEMPTED,
        "whatsapp_lookup_unavailable",
    )


def sealed_context(content_artifact, resolved) -> dict[str, str]:
    """As variáveis do flow, lidas só do que foi aprovado.

    Ordem de precedência: variáveis do conteúdo aprovado < fatos selados (conferidos
    contra o ``facts_hash`` do artefato) < corpo/link/foto resolvidos para o WhatsApp,
    que são exatamente o que a prévia mostrou.
    """

    payload = content_artifact.payload if isinstance(content_artifact.payload, dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    variables = content.get("variables") if isinstance(content.get("variables"), dict) else {}
    values: dict[str, str] = {
        name: str(variables[name])
        for name in SEALED_VARIABLES
        if isinstance(variables.get(name), (str, int, float))
    }

    raw_facts = payload.get("facts")
    if raw_facts is not None:
        from shopman.shop.services import marketing_facts

        try:
            facts = marketing_facts.from_payload(raw_facts)
        except MarketingContractError:
            _refuse("whatsapp_facts_invalid", "")
        if resolved.facts_hash and not hmac.compare_digest(
            facts.source_hash, resolved.facts_hash
        ):
            _refuse("whatsapp_facts_mismatch", "")
        values.update(
            {
                name: value
                for name, value in facts.variable_values().items()
                if name in SEALED_VARIABLES
            }
        )
        product = dict(facts.product)
        if product.get("name") and not values.get("product_name"):
            values["product_name"] = str(product["name"])
        if product.get("sku") and not values.get("product_sku"):
            values["product_sku"] = str(product["sku"])

    if resolved.image_url:
        values["product_image_url"] = resolved.image_url
    values.update(
        {
            "body": resolved.body,
            "cta": CTA,
            "action_url": resolved.link,
            "link": resolved.link,
        }
    )
    return values


def _sending_target(*, artifact, target_key: str, idempotency_token: str):
    """O destino que o ledger acabou de pôr em ``sending`` para esta tentativa.

    O adapter recebe só a impressão digital protegida e o token da tentativa. As duas
    precisam apontar para o MESMO destino, e o artefato aprovado dele precisa ter o
    hash do que chegou aqui — senão nada sai.
    """

    from shopman.shop.models import DeliveryTarget
    from shopman.shop.services.marketing_artifacts import (
        resolve_target_dispatch_artifact,
    )

    rows = list(
        DeliveryTarget.objects.select_related("artifact", "member__customer").filter(
            target_fingerprint=str(target_key or ""),
            platform=PLATFORM,
            state=DeliveryTarget.State.SENDING,
        )[:2]
    )
    if len(rows) != 1:
        _refuse("whatsapp_target_unresolved", target_key)
    (target,) = rows
    if not str(idempotency_token or "").startswith(f"marketing:v1:{target.ref}:attempt:"):
        _refuse("whatsapp_target_unresolved", target_key)
    try:
        approved = resolve_target_dispatch_artifact(target)
    except MarketingContractError:
        _refuse("whatsapp_artifact_mismatch", target_key)
    if not hmac.compare_digest(approved.artifact_hash, artifact.artifact_hash):
        _refuse("whatsapp_artifact_mismatch", target_key)
    return target


def _require_sealed_flow(artifact, target_key: str) -> None:
    """O flow que vai disparar é o que a aprovação selou.

    O ``notification_manychat`` lê o flow do Admin na hora do envio. Se alguém trocou
    o flow depois da aprovação, a mensagem sairia com um texto que ninguém revisou.
    """

    sealed = str(getattr(artifact, "flow_ref", "") or "").strip()
    if not sealed:
        _refuse("whatsapp_flow_not_sealed", target_key)
    from shopman.shop.models import NotificationTemplate

    current = (
        NotificationTemplate.objects.filter(event=EVENT, is_active=True)
        .values_list("whatsapp_flow_ns", flat=True)
        .first()
    )
    if not hmac.compare_digest(str(current or "").strip(), sealed):
        _refuse("whatsapp_flow_changed_since_approval", target_key)


def _recipient_phone(target, *, customer, target_key: str) -> str:
    """Revalida consentimento e devolve o telefone do destino, ou recusa.

    O claim já suprimiu opt-out, falta de consentimento e idade não comprovada, e a
    abertura da chamada relê idade e conta ativa. Entre o claim e esta linha passam
    segundos; a última porta relê o consentimento para não mandar a quem saiu agora.
    """

    from django.utils import timezone
    from shopman.utils.phone import normalize_phone

    member = target.member
    if member is None:
        _refuse("delivery_identity_unavailable", target_key)
    reasons = frozenset(member.reasons or [])
    is_alert_delivery = bool("alerts" in reasons and member.subscription_ref)

    if customer is not None:
        if not customer.is_active:
            _refuse("customer_inactive", target_key)
        try:
            from shopman.guestman import ConsentService

            status = ConsentService.get_customer_statuses(PLATFORM, {customer.ref}).get(
                customer.ref, ""
            )
        except Exception:
            logger.warning(
                "marketing.whatsapp_consent_unavailable target=%s", _short(target_key)
            )
            raise ProviderCallFailure(
                ProviderOutcomeKind.FAILED_RETRYABLE, "consent_unavailable"
            ) from None
        if status == "opted_out":
            _refuse("global_optout", target_key)
        if not is_alert_delivery and status != "opted_in":
            _refuse("missing_consent", target_key)
        phone = normalize_phone(customer.phone or "")
    elif member.subscription_ref:
        from shopman.shop.adapters.audience_sources import active_alert_subscriptions

        subscriptions = active_alert_subscriptions(
            {member.subscription_ref}, now=timezone.now()
        )
        if not subscriptions:
            _refuse("subscription_inactive", target_key)
        phone = normalize_phone(subscriptions[0].contact_phone or "")
    else:
        _refuse("delivery_identity_unavailable", target_key)
    if not phone:
        _refuse("whatsapp_recipient_contact_missing", target_key)
    return phone


def _refuse(code: str, target_key: str) -> NoReturn:
    """Recusa antes do fornecedor: falha final, com o motivo, sem nada escrito."""

    logger.warning(
        "marketing.whatsapp_delivery_refused code=%s target=%s", code, _short(target_key)
    )
    raise ProviderCallFailure(ProviderOutcomeKind.FAILED_FINAL, code)


def _retry_after(value) -> int | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return seconds if 0 < seconds <= 86_400 else None


def _short(target_key: str) -> str:
    return str(target_key or "")[:12]
