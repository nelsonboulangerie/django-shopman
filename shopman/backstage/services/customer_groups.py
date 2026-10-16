"""Mutações dos grupos comerciais na superfície Gestor."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from shopman.backstage.services.exceptions import CustomerGroupMutationError
from shopman.shop.models import Channel, Promotion
from shopman.shop.services import customer_groups as domain_service
from shopman.shop.services.customer_groups import ADVANTAGE_KINDS

_FIELDS = {
    "ref", "name", "description", "listingRef", "priority", "isDefault",
    "discountType", "discountValue", "channelRefs", "pickupOnly",
    "discountKind", "rounding", "savingsMessage", "advantages",
}
_DISCOUNT_TYPES = {"", Promotion.PERCENT, Promotion.FIXED}

#: As chaves que cada tipo de vantagem aceita. Tipadas em
#: ``docs/reference/data-schemas.md``; chave fora daqui é recusada em vez de ignorada.
_ADVANTAGE_FIELDS: dict[str, set[str]] = {
    "free_shipping": {"kind", "isActive", "priority", "minOrderQ"},
    "exclusive_collections": {"kind", "isActive", "priority", "collectionRefs"},
    "exclusive_notifications": {"kind", "isActive", "priority", "campaignRefs"},
}
#: Teto por vantagem: a lista de refs é escolhida na tela, não importada em massa.
_ADVANTAGE_REF_LIMIT = 50


def _error(detail: str, *, field: str = "", code: str = "invalid_payload") -> CustomerGroupMutationError:
    return CustomerGroupMutationError(detail, field=field, code=code)


def _text(data: dict, key: str, *, max_length: int | None = None) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise _error("Use texto neste campo.", field=key)
    result = str(value).strip()
    if max_length and len(result) > max_length:
        raise _error(f"Use no máximo {max_length} caracteres.", field=key)
    return result


def _boolean(data: dict, key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise _error("Escolha sim ou não.", field=key)
    return value


def _priority(value) -> int:
    if isinstance(value, bool):
        raise _error("Informe uma prioridade inteira.", field="priority")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise _error("Informe uma prioridade inteira.", field="priority") from None
    if result < -9999 or result > 9999:
        raise _error("Use uma prioridade entre -9999 e 9999.", field="priority")
    return result


def _discount_value(kind: str, value) -> Decimal:
    if not kind:
        return Decimal("0")
    try:
        result = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise _error("Informe o valor do desconto.", field="discountValue") from None
    if not result.is_finite() or result <= 0:
        raise _error("Informe um valor maior que zero.", field="discountValue")
    if kind == Promotion.PERCENT and (result > 100 or result != result.to_integral_value()):
        raise _error("Use um percentual inteiro, de 1 a 100.", field="discountValue")
    if kind == Promotion.FIXED and (result > Decimal("999999.99") or result.as_tuple().exponent < -2):
        raise _error("Use um valor em reais com no máximo duas casas decimais.", field="discountValue")
    return result


def _channels(value) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _error("Escolha os canais disponíveis.", field="channelRefs")
    refs = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    if Channel.objects.filter(ref__in=refs).count() != len(refs):
        raise _error("Um dos canais escolhidos não está mais disponível.", field="channelRefs")
    return refs


def _listing(ref: str) -> str:
    if not ref:
        return ""
    from shopman.offerman.models import Listing

    if not Listing.objects.filter(ref=ref, is_active=True).exists():
        raise _error("Escolha uma lista de preço ativa.", field="listingRef")
    return ref


def _min_order_q(value) -> int:
    """Pedido mínimo do frete grátis, em centavos. Vazio = zero, que é "sempre"."""
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        raise _error("Informe o valor mínimo em reais.", field="minOrderQ")
    text = str(value).strip()
    if not text:
        return 0
    try:
        amount = Decimal(text.replace(".", "").replace(",", ".")) if "," in text else Decimal(text)
    except (InvalidOperation, ValueError):
        raise _error("Informe o valor mínimo em reais.", field="minOrderQ") from None
    if not amount.is_finite() or amount < 0 or amount > Decimal("999999.99"):
        raise _error("Informe um valor mínimo entre zero e 999.999,99.", field="minOrderQ")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise _error("Use no máximo duas casas decimais no valor mínimo.", field="minOrderQ")
    return int(cents)


def _advantage_refs(value, *, empty_detail: str, limit_detail: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _error(empty_detail, field="refs")
    refs = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    if len(refs) > _ADVANTAGE_REF_LIMIT:
        raise _error(limit_detail, field="refs")
    return refs


def _advantage(item: dict, saved: dict) -> dict:
    """Traduz UMA vantagem do payload para o ``config`` tipado que o domínio grava.

    Chave de ``config`` AUSENTE não é tocada: quem edita esta tela escolhe as coleções
    e o pedido mínimo, e não os avisos exclusivos, que são do Marketing. Substituir o
    ``config`` inteiro apagaria o que veio de outro dono.

    A recusa aponta sempre ``advantages``, porque é o campo do formulário que a tela
    destaca; o detalhe diz qual tipo falhou.
    """
    kind = _text(item, "kind")
    if kind not in ADVANTAGE_KINDS:
        raise _error("Escolha um tipo de vantagem disponível.", field="advantages")
    unknown = sorted(set(item) - _ADVANTAGE_FIELDS[kind])
    if unknown:
        raise _error(
            f"Campo desconhecido na vantagem {kind}: {unknown[0]}.", field="advantages",
        )
    config: dict = dict(saved)
    if kind == "free_shipping":
        if "minOrderQ" in item:
            config["min_order_q"] = _min_order_q(item["minOrderQ"])
        config.setdefault("min_order_q", 0)
    elif kind == "exclusive_collections":
        if "collectionRefs" in item:
            from shopman.offerman.models import Collection

            refs = _advantage_refs(
                item["collectionRefs"],
                empty_detail="Escolha as coleções como uma lista.",
                limit_detail=f"Escolha no máximo {_ADVANTAGE_REF_LIMIT} coleções por grupo.",
            )
            if Collection.objects.filter(ref__in=refs, is_active=True).count() != len(refs):
                raise _error("Uma das coleções escolhidas não está mais disponível.", field="collectionRefs")
            config["collection_refs"] = refs
        config.setdefault("collection_refs", [])
    else:
        if "campaignRefs" in item:
            config["campaign_refs"] = _advantage_refs(
                item["campaignRefs"],
                empty_detail="Escolha os avisos como uma lista.",
                limit_detail=f"Escolha no máximo {_ADVANTAGE_REF_LIMIT} avisos por grupo.",
            )
        config.setdefault("campaign_refs", [])
    return {
        "kind": kind,
        "priority": _priority(item.get("priority", 0)),
        "is_active": _boolean(item, "isActive"),
        "config": config,
    }


def _advantages(value, saved: dict[str, dict] | None = None) -> list[dict]:
    """O conjunto de vantagens tipadas do grupo. Lista vazia = nenhuma ligada."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise _error("Envie as vantagens como uma lista.", field="advantages")
    parsed: list[dict] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise _error("Cada vantagem precisa ser um objeto.", field="advantages")
        try:
            kind = _text(item, "kind")
            advantage = _advantage(item, saved.get(kind, {}))
        except CustomerGroupMutationError as exc:
            raise _error(exc.detail, field="advantages", code=exc.code) from exc
        if advantage["kind"] in seen:
            raise _error("Cada tipo de vantagem aparece uma vez por grupo.", field="advantages")
        seen.add(advantage["kind"])
        parsed.append(advantage)
    return parsed


def _revision(tier) -> str:
    return tier.updated_at.isoformat()


def _assert_revision(tier, data: dict) -> None:
    expected = _text(data, "expectedRevision")
    if not expected:
        raise _error("Atualize o grupo antes de salvar.", field="expectedRevision", code="revision_required")
    if expected != _revision(tier):
        raise _error(
            "O grupo mudou desde que você abriu. Atualize e confira antes de salvar.",
            field="expectedRevision", code="group_changed",
        )


def _validate_payload(data: dict, *, creating: bool, saved_advantages: dict[str, dict] | None = None) -> dict:
    if not isinstance(data, dict):
        raise _error("O grupo precisa ser um objeto.")
    unknown = sorted(set(data) - _FIELDS - {"expectedRevision"})
    if unknown:
        raise _error(f"Campo desconhecido: {unknown[0]}.", field=unknown[0])
    ref = _text(data, "ref", max_length=50).lower()
    if creating and (not ref or not re.fullmatch(r"[-a-z0-9_]+", ref)):
        raise _error("Use letras minúsculas, números e hífen no código.", field="ref")
    name = _text(data, "name", max_length=200)
    if not name:
        raise _error("Informe o nome do grupo.", field="name")
    discount_type = _text(data, "discountType")
    if discount_type not in _DISCOUNT_TYPES:
        raise _error("Escolha um tipo de desconto disponível.", field="discountType")
    discount_value = _discount_value(discount_type, data.get("discountValue", ""))
    discount_kind = _text(data, "discountKind", max_length=40)
    if discount_type and not discount_kind:
        raise _error("Informe o tipo usado pelo B.I., como equipe ou parceiro.", field="discountKind")
    return {
        "ref": ref,
        "name": name,
        "description": _text(data, "description"),
        "listing_ref": _listing(_text(data, "listingRef", max_length=50)),
        "priority": _priority(data.get("priority", 0)),
        "is_default": _boolean(data, "isDefault"),
        "discount_type": discount_type,
        "discount_value": discount_value,
        "channel_refs": _channels(data.get("channelRefs", [])),
        "pickup_only": _boolean(data, "pickupOnly"),
        "discount_kind": discount_kind,
        "rounding": _boolean(data, "rounding", True),
        "savings_message": _text(data, "savingsMessage", max_length=500),
        # Ausente = não mexer. Presente = o conjunto COMPLETO dos tipos do grupo.
        "advantages": (
            _advantages(data["advantages"], saved_advantages or {}) if "advantages" in data else None
        ),
    }


def _apply(tier, values: dict) -> None:
    tier.name = values["name"]
    tier.description = values["description"]
    tier.listing_ref = values["listing_ref"]
    tier.priority = values["priority"]
    tier.is_default = values["is_default"]
    tier.metadata = domain_service.metadata_with_group_settings(
        tier.metadata or {},
        discount_kind=values["discount_kind"],
        rounding=values["rounding"],
        savings_message=values["savings_message"],
    )
    try:
        tier.full_clean()
        tier.save()
    except ValidationError as exc:
        messages = getattr(exc, "message_dict", {})
        field = next(iter(messages), "")
        detail = str((messages.get(field) or ["Confira os dados do grupo."])[0])
        raise _error(detail, field={"listing_ref": "listingRef", "is_default": "isDefault"}.get(field, field)) from exc
    domain_service.sync_group_discount(
        tier,
        discount_type=values["discount_type"],
        discount_value_q=domain_service.discount_value_q(values["discount_type"], values["discount_value"]),
        channel_refs=values["channel_refs"],
        pickup_only=values["pickup_only"],
    )
    if values["advantages"] is not None:
        domain_service.sync_group_advantages(tier, values["advantages"])
        # A revisão do grupo cobre a configuração INTEIRA, e as vantagens moram em
        # outra tabela. Sem este toque, salvar só as vantagens devolveria a mesma
        # revisão de antes e a próxima aba sobrescreveria o grupo em silêncio.
        tier.save(update_fields=["updated_at"])


@transaction.atomic
def create_group(data: dict):
    from shopman.guestman.models import PriceTier

    values = _validate_payload(data, creating=True)
    tier = PriceTier(ref=values["ref"])
    try:
        _apply(tier, values)
    except IntegrityError as exc:
        raise _error("Já existe um grupo com este código.", field="ref", code="ref_conflict") from exc
    return tier


@transaction.atomic
def update_group(ref: str, data: dict):
    from shopman.guestman.models import PriceTier

    tier = PriceTier.objects.select_for_update().filter(ref=ref).first()
    if tier is None:
        raise _error("Grupo não encontrado.", code="not_found")
    _assert_revision(tier, data)
    saved_advantages = {
        advantage.kind: dict(advantage.config or {}) for advantage in tier.advantages.all()
    }
    values = _validate_payload(data, creating=False, saved_advantages=saved_advantages)
    requested_ref = values.pop("ref")
    if requested_ref and requested_ref != tier.ref:
        raise _error(
            "O código não muda depois da criação, porque identifica preços e promoções.",
            field="ref", code="immutable_ref",
        )
    _apply(tier, values)
    return tier
