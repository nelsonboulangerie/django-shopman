"""Campanha exclusiva de grupo: o Marketing é o dono de ``campaign_refs``.

Um grupo de clientes (``guestman.PriceTier``) pode ter a vantagem tipada
``exclusive_notifications`` (``guestman.PriceTierAdvantage``). A lista
``config["campaign_refs"]`` dessa vantagem diz quais campanhas são EXCLUSIVAS do
grupo. A chave é escrita aqui, pelo Marketing; o Gestor aceita a chave mas não a
oferece na tela, e chave ausente no payload dele não é tocada.

Três regras, e todas falham fechado:

1. **Declarar exclusividade restringe.** Campanha que aparece no ``campaign_refs`` de
   algum grupo só alcança membros dos grupos que a declaram, qualquer que seja o
   público escolhido (``audience.resolve(..., campaign_id=...)``).
2. **Vantagem desligada não abre a porta.** Se o grupo desligou os avisos exclusivos
   (``is_active=False``), os membros dele saem do envio, mas a campanha continua
   exclusiva: ela nunca vira campanha para todo mundo porque alguém desligou um
   interruptor no Gestor.
3. **Cada dono mexe só no que é seu.** Gravar a exclusividade de uma campanha
   acrescenta ou retira apenas a referência DELA; as outras campanhas do mesmo grupo,
   a prioridade e o ``is_active`` (do Gestor) ficam como estavam.

A referência da campanha é a identidade que o Marketing já usa nos comprovantes e na
projeção v2: ``campaign:<pk>``.

Resolução em lote: uma consulta lê todas as vantagens ``exclusive_notifications``
(uma linha por grupo, no máximo), sem N+1 por campanha ou por cliente.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction

KIND = "exclusive_notifications"
CONFIG_KEY = "campaign_refs"


class CampaignExclusivityError(ValueError):
    """Grupo escolhido que não existe. ``detail`` é frase pronta para o gestor."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class Exclusivity:
    """A exclusividade de uma campanha, lida de uma vez."""

    #: Grupos que declaram a campanha (vantagem ligada ou não). Vazio = não é exclusiva.
    declared: tuple[str, ...] = ()
    #: Dos declarados, os que têm os avisos exclusivos LIGADOS: só os membros deles recebem.
    reachable: frozenset[str] = frozenset()

    @property
    def is_exclusive(self) -> bool:
        return bool(self.declared)


def campaign_ref(campaign_id: int) -> str:
    return f"campaign:{int(campaign_id)}"


def _refs(config) -> list[str]:
    raw = (config or {}).get(CONFIG_KEY) if isinstance(config, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(ref) for ref in raw if str(ref or "").strip()]


def _advantage_rows():
    from shopman.guestman.models import PriceTierAdvantage

    return PriceTierAdvantage.objects.filter(kind=KIND).values_list(
        "tier__ref", "is_active", "config"
    )


def declared_by_campaign() -> dict[str, tuple[str, ...]]:
    """``{"campaign:<pk>": (grupo, ...)}`` para todas as campanhas, numa consulta só.

    É o que a lista de campanhas projeta: N campanhas custam UMA leitura, não N.
    """
    by_campaign: dict[str, set[str]] = {}
    for tier_ref, _is_active, config in _advantage_rows():
        for ref in _refs(config):
            by_campaign.setdefault(ref, set()).add(tier_ref)
    return {ref: tuple(sorted(tiers)) for ref, tiers in by_campaign.items()}


def for_campaign(campaign_id: int | None) -> Exclusivity:
    """A exclusividade de UMA campanha. ``None`` (anúncio sem campanha) = não exclusiva."""
    if not campaign_id:
        return Exclusivity()
    ref = campaign_ref(campaign_id)
    declared: set[str] = set()
    reachable: set[str] = set()
    for tier_ref, is_active, config in _advantage_rows():
        if ref in _refs(config):
            declared.add(tier_ref)
            if is_active:
                reachable.add(tier_ref)
    return Exclusivity(declared=tuple(sorted(declared)), reachable=frozenset(reachable))


def clean_tier_refs(value) -> list[str]:
    """Os grupos escolhidos, sem repetição e na ordem. Recusa grupo que não existe."""
    from shopman.guestman.models import PriceTier

    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise CampaignExclusivityError("Escolha os grupos como uma lista.")
    cleaned: list[str] = []
    for item in value:
        ref = str(item or "").strip()
        if ref and ref not in cleaned:
            cleaned.append(ref)
    if cleaned:
        known = set(PriceTier.objects.filter(ref__in=cleaned).values_list("ref", flat=True))
        if len(known) != len(cleaned):
            raise CampaignExclusivityError("Um dos grupos escolhidos não existe mais.")
    return cleaned


def set_exclusive_tiers(campaign_id: int, tier_refs: Iterable[str]) -> tuple[str, ...]:
    """Gravar os grupos que têm a campanha como exclusiva. Devolve os grupos gravados.

    Acrescenta ``campaign:<pk>`` no ``campaign_refs`` dos grupos escolhidos e retira
    só essa referência dos que deixaram de ser escolhidos. Grupo escolhido que ainda
    não tem a vantagem ganha a linha, ligada (escolher o grupo É declarar o aviso
    exclusivo); linha que já existe mantém ``is_active`` e ``priority``, que são do
    Gestor. Lista vazia = a campanha deixa de ser exclusiva.
    """
    from shopman.guestman.models import PriceTier, PriceTierAdvantage

    ref = campaign_ref(campaign_id)
    wanted = clean_tier_refs(list(tier_refs))
    with transaction.atomic():
        rows = {
            advantage.tier.ref: advantage
            for advantage in PriceTierAdvantage.objects.select_for_update()
            .select_related("tier")
            .filter(kind=KIND)
        }
        for tier_ref, advantage in rows.items():
            refs = _refs(advantage.config)
            has = ref in refs
            keep = tier_ref in wanted
            if has == keep:
                continue
            config = dict(advantage.config or {})
            config[CONFIG_KEY] = [*refs, ref] if keep else [r for r in refs if r != ref]
            advantage.config = config
            advantage.save(update_fields=["config", "updated_at"])
        missing = [tier_ref for tier_ref in wanted if tier_ref not in rows]
        for tier in PriceTier.objects.filter(ref__in=missing):
            PriceTierAdvantage.objects.create(
                tier=tier, kind=KIND, is_active=True, config={CONFIG_KEY: [ref]}
            )
    return tuple(sorted(wanted))
