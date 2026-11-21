"""A lista FECHADA de remédios que o acionador pode chamar.

Cada remédio é um gesto que o domínio JÁ oferece a uma pessoa (o mesmo botão do
Gestor), idempotente no próprio domínio e com as travas dele. O acionador só:

1. pergunta ao remédio se este alerta é dele agora (:class:`Verdict`);
2. aciona o gesto, com o ator ``watchman:incidentes``;
3. confere depois, por FATO do domínio, se resolveu.

Entra aqui só o que o domínio, sozinho, deixou parado à espera de alguém. O que
ele já repete sozinho (os sweeps do ``maintenance_worker``, o retry da Directive,
a regravação do iFood quando a loja diverge) não entra: acionar de novo não
ganharia nada.

NUNCA entram: credencial, dinheiro (estorno, captura, corrida), apagar dado,
reseed, configuração de produção, infraestrutura.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone

ACTOR = "watchman:incidentes"


@dataclass(frozen=True)
class Verdict:
    """O que fazer com o alerta agora.

    - ``act``: acionar já;
    - ``wait``: o domínio ainda está tentando; voltar em ``until``;
    - ``no``: fica com gente, pelo ``reason``;
    - ``judge``: a regra não decide; ``evidence`` vai ao classificador (W3).
    """

    kind: str
    reason: str = ""
    until: datetime | None = None
    evidence: str = ""


class RemedyRefused(Exception):
    """O domínio recusou o gesto (estado mudou, nada a refazer)."""


@dataclass(frozen=True)
class Remedy:
    key: str
    label: str
    alert_type: str
    #: Teto por alvo (pedido) em 24 h, contando só gestos acionados.
    max_attempts: int
    #: Quanto esperar depois de acionar antes de conferir.
    verify_after: timedelta
    #: Desistir de conferir depois disto: "não resolveu".
    verify_within: timedelta
    check: Callable[..., Verdict]
    apply: Callable[..., str]
    confirm: Callable[..., bool | None]
    #: Quando a regra diz ``judge``: as duas opções que o classificador pode escolher.
    judge_criteria: dict[str, str] = field(default_factory=dict)
    judge_act_reason: str = ""
    judge_people_reason: str = ""


def _order(ref: str):
    from shopman.orderman.models import Order

    return Order.objects.filter(ref=ref).first() if ref else None


# ── A1: reprocessar a NFC-e já solicitada ───────────────────────────────────────


def _latest_fiscal_directive(order_ref: str):
    from shopman.orderman.models import Directive

    from shopman.shop.directives import FISCAL_EMIT_NFCE

    return (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order_ref)
        .order_by("-created_at", "-pk")
        .first()
    )


def check_fiscal(alert) -> Verdict:
    order = _order(alert.order_ref)
    if order is None:
        return Verdict("no", "alerta sem pedido encontrado")
    if (order.data or {}).get("nfce_access_key"):
        return Verdict("no", "NFC-e já autorizada")
    directive = _latest_fiscal_directive(order.ref)
    if directive is None:
        return Verdict("no", "nenhuma emissão solicitada")
    if directive.status in {"queued", "running"}:
        return Verdict("wait", "a emissão ainda está na fila", until=timezone.now() + timedelta(minutes=5))
    if directive.status != "failed":
        return Verdict("no", f"emissão em estado {directive.status}")
    answer = str((directive.payload or {}).get("emitter_answer") or "").strip()
    if answer:
        # O emissor respondeu e recusou: pode ser cadastro (gente) ou indisponibilidade
        # que a SEFAZ devolve como rejeição. A regra não separa; o classificador lê.
        return Verdict("judge", "o emissor recusou a nota", evidence=f"Resposta do emissor: {answer[:400]}")
    return Verdict("act", "falha transitória que esgotou a janela do domínio")


def apply_fiscal(alert) -> str:
    from shopman.backstage.services.exceptions import OrderError
    from shopman.backstage.services.orders import requeue_fiscal_emission

    order = _order(alert.order_ref)
    if order is None:
        raise RemedyRefused("pedido não encontrado")
    try:
        directive = requeue_fiscal_emission(order, actor=ACTOR)
    except OrderError as exc:
        raise RemedyRefused(str(exc)) from exc
    return f"emissão de volta à fila (tarefa {directive.pk})"


def confirm_fiscal(action) -> bool | None:
    order = _order(action.target)
    if order is None:
        return False
    if (order.data or {}).get("nfce_access_key"):
        return True
    directive = _latest_fiscal_directive(order.ref)
    if directive is not None and directive.status == "failed" and directive.updated_at > action.created_at:
        return False
    return None


# ── A2: reenviar ao iFood o aceite que não chegou ────────────────────────────────

#: Antes do prazo do iFood, a folga para o ``confirm`` sair e ser lido.
ACCEPT_MARGIN = timedelta(seconds=60)


def check_ifood_accept(alert) -> Verdict:
    from shopman.shop.services import ifood_accept_sync

    order = _order(alert.order_ref)
    if order is None:
        return Verdict("no", "alerta sem pedido encontrado")
    sync = ifood_accept_sync.state_for(order)
    if sync.state in {"sent", "confirmed"}:
        return Verdict("no", "o iFood já recebeu o aceite")
    if not sync.failed:
        return Verdict("no", "não há envio de aceite pendente")
    now = timezone.now()
    deadline = ifood_accept_sync.deadline(order)
    if deadline is not None and deadline <= now:
        return Verdict("no", "o prazo do iFood já passou: conferir no iFood se o pedido segue ativo")
    from shopman.orderman.models import Directive

    directive = Directive.objects.filter(pk=sync.directive_id).first() if sync.directive_id else None
    if directive is not None and directive.status == "running":
        return Verdict("wait", "o aceite está saindo agora", until=now + timedelta(seconds=15))
    if directive is not None and directive.status == "queued":
        # O domínio ainda vai tentar. Só adiantar se a próxima tentativa dele cair
        # depois do prazo; senão, voltar logo depois dela para conferir.
        latest_useful = deadline - ACCEPT_MARGIN if deadline is not None else None
        if latest_useful is None or directive.available_at <= latest_useful:
            return Verdict("wait", "o domínio ainda vai tentar", until=directive.available_at + timedelta(seconds=20))
    return Verdict("act", "o domínio parou de tentar antes do prazo do iFood")


def apply_ifood_accept(alert) -> str:
    from shopman.shop.services import ifood_accept_sync

    order = _order(alert.order_ref)
    if order is None:
        raise RemedyRefused("pedido não encontrado")
    revision = ifood_accept_sync.state_for(order).revision
    try:
        directive = ifood_accept_sync.retry(order, actor=ACTOR, expected_revision=revision)
    except ifood_accept_sync.AcceptRetryRefused as exc:
        raise RemedyRefused(str(exc)) from exc
    return f"aceite de volta à fila (tarefa {directive.pk})"


def confirm_ifood_accept(action) -> bool | None:
    from shopman.shop.services import ifood_accept_sync

    order = _order(action.target)
    if order is None:
        return False
    sync = ifood_accept_sync.state_for(order)
    if sync.state in {"sent", "confirmed"}:
        return True
    if sync.directive_status == "failed":
        return False
    return None


REMEDIES: tuple[Remedy, ...] = (
    Remedy(
        key="fiscal_requeue",
        label="Reprocessar a NFC-e",
        alert_type="fiscal_emit_failed",
        max_attempts=3,
        verify_after=timedelta(minutes=5),
        verify_within=timedelta(minutes=90),
        check=check_fiscal,
        apply=apply_fiscal,
        confirm=confirm_fiscal,
        judge_criteria={
            "act": (
                "Indisponibilidade passageira dita como recusa: SEFAZ ou emissor fora do ar, serviço "
                "paralisado, tempo esgotado, consumo indevido, lote em processamento. Reprocessar a "
                "mesma nota resolve."
            ),
            "people": (
                "Problema de cadastro ou de regra fiscal: NCM, CFOP, CST, GTIN, CPF ou CNPJ inválido, "
                "certificado, valor ou totais que não fecham, duplicidade. Reprocessar sem mudar nada "
                "falha de novo."
            ),
        },
        judge_act_reason="o emissor recusou por indisponibilidade passageira",
        judge_people_reason="a recusa do emissor é de cadastro ou regra fiscal: pede o cadastro ou o contador",
    ),
    Remedy(
        key="ifood_accept_retry",
        label="Reenviar o aceite ao iFood",
        alert_type="ifood_accept_not_delivered",
        max_attempts=3,
        verify_after=timedelta(seconds=30),
        verify_within=timedelta(minutes=10),
        check=check_ifood_accept,
        apply=apply_ifood_accept,
        confirm=confirm_ifood_accept,
    ),
)

BY_ALERT_TYPE: dict[str, Remedy] = {remedy.alert_type: remedy for remedy in REMEDIES}
BY_KEY: dict[str, Remedy] = {remedy.key: remedy for remedy in REMEDIES}
