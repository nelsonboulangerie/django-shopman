"""O corpus anonimizado de aprendizado conversacional (dono, 20/11/2026, #2851).

Copia as mensagens dos clientes para ``storefront.ConversationCorpusEntry`` sem nada que
ligue à pessoa (ver o model). Roda no ``maintenance_worker`` ANTES da limpeza de
retenção, para a observação ser copiada antes de vencer.

Duas fontes:

- a observação passiva (``automation_eligible=False``): o texto já vem redigido da
  captura; o resultado é ``observed`` (a Concierge não respondia), e a intenção, a da
  triagem em sombra quando houve;
- a conversa atendida (contrato v3, entrada já respondida): o resultado sai dos recibos
  da resposta do turno (``envelope["receipts"]``: verificar, equipe, pedido), e a
  intenção, a da triagem gravada na entrada. O texto passa pela redação da captura.

Toda mensagem passa pela segunda limpeza (``anonymize``). A origem ganha a marca
``envelope["corpus_copied"]``: é a única ligação, e ela fica do lado da pessoa (some com
a retenção), nunca do lado do corpus.

Conferência: as primeiras ``SAMPLE_PER_WEEK`` cópias de cada semana vão para o curador
(``shop.review_conversation_observations``, no Admin). Achado de dado pessoal pausa a
cópia até o curador apagar a linha.
"""

from __future__ import annotations

import logging
import re

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Quantas cópias por semana vão para a conferência humana.
SAMPLE_PER_WEEK = 20
#: Teto de cópias por ciclo do worker.
BATCH = 500
COPIED_KEY = "corpus_copied"

# ── A segunda limpeza ─────────────────────────────────────────────────

_SECOND_PASS = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[e-mail omitido]"),
    ("link", re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE), "[link omitido]"),
    # Placa antiga (ABC-1234) e Mercosul (ABC1D23).
    ("plate", re.compile(r"\b[A-Za-z]{3}-?\d[A-Za-z0-9]\d{2}\b"), "[placa omitida]"),
    # Data (12/03, 12/03/2026) e horário exato (14h30, 14:30, 9h).
    ("date", re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"), "[data omitida]"),
    ("time", re.compile(r"\b\d{1,2}(?:[:h]\d{2}|h)\b", re.IGNORECASE), "[horário omitido]"),
    # Número longo (telefone, protocolo, CEP, conta), com ou sem separador.
    ("long_number", re.compile(r"(?<![\w\]])\d[\d .()/-]{3,}\d(?![\w\[])"), "[número omitido]"),
)
#: Palavra com inicial maiúscula no meio da frase: nome próprio (de gente, rua, bairro).
_CAPITALIZED = re.compile(r"\b([A-ZÀ-Ý][a-zà-ÿ]{2,})\b")
#: O que vem antes da palavra quando ela abre a frase (maiúscula de começo, não nome).
_SENTENCE_START = re.compile(r"(?:^|[.!?:]\s*|\n\s*)$")


def anonymize(text: str) -> tuple[str, tuple[str, ...]]:
    """A segunda passada sobre o texto já redigido: (texto, categorias aplicadas)."""
    from .observation_privacy import _PRODUCT_NOUNS

    found: list[str] = []
    for category, pattern, replacement in _SECOND_PASS:
        text, count = pattern.subn(replacement, text)
        if count:
            found.append(category)

    def name(match: re.Match) -> str:
        word = match.group(1)
        before = text[: match.start()]
        if _SENTENCE_START.search(before) or word.casefold() in _PRODUCT_NOUNS:
            return word
        return "[nome omitido]"

    renamed = _CAPITALIZED.sub(name, text)
    if renamed != text:
        found.append("proper_name")
    return renamed, tuple(found)


# ── A cópia ───────────────────────────────────────────────────────────


def paused() -> bool:
    """Achado de dado pessoal na conferência pausa a cópia até o curador tratar."""
    from shopman.storefront.models.corpus import ConversationCorpusEntry, CorpusReview

    return ConversationCorpusEntry.objects.filter(review=CorpusReview.PERSONAL_DATA).exists()


def _outcome_of(message) -> str | None:
    """O resultado do turno da entrada atendida, pelos recibos da resposta; None sem resposta."""
    from shopman.shop.models import ConversationMessage
    from shopman.storefront.models.corpus import CorpusOutcome

    from . import house_rules

    if not message.automation_eligible:
        return CorpusOutcome.OBSERVED
    reply = (
        ConversationMessage.objects.filter(
            conversation_id=message.conversation_id,
            kind=ConversationMessage.Kind.REPLY,
            envelope__turn_fence=message.consumed_by,
        )
        .order_by("pk")
        .first()
    )
    if reply is None:
        return None
    envelope = reply.envelope or {}
    receipts = set(envelope.get("receipts") or ())
    if envelope.get("purpose") == "handoff_ack" or house_rules.HANDOFF in receipts:
        return CorpusOutcome.TEAM
    if house_rules.ORDER in receipts:
        return CorpusOutcome.ORDER
    if house_rules.VERIFY in receipts:
        return CorpusOutcome.VERIFYING
    return CorpusOutcome.UNDERSTOOD


def _intent_of(message) -> str:
    envelope = message.envelope or {}
    shadow = envelope.get("triage_shadow") or {}
    stamped = envelope.get("triage") or {}
    return str(shadow.get("jev") or shadow.get("rules") or stamped.get("intent") or "")[:40]


def _candidates():
    from django.db.models import Q

    from shopman.shop.models import ConversationMessage

    return (
        ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND)
        .exclude(text="")
        # A chave ausente compara como NULL: ``exclude(chave=True)`` tiraria tudo.
        .exclude(envelope__has_key=COPIED_KEY)
        .filter(
            Q(automation_eligible=False, envelope__processing_mode="observe")
            | Q(automation_eligible=True, envelope__version=3, consumed_by__isnull=False)
        )
        .select_related("binding", "conversation")
        .order_by("pk")
    )


def copy(*, now=None, limit: int = BATCH) -> dict:
    """Copia o que falta para o corpus. Nunca levanta; pausada, não copia nada."""
    from shopman.shop.models import ConversationMessage
    from shopman.storefront.models.corpus import ConversationCorpusEntry, CorpusReview

    from .observation_privacy import redact_observation_text

    if paused():
        return {"copied": 0, "paused": True}
    now = now or timezone.now()
    week = now.strftime("%G-W%V")
    sampled = ConversationCorpusEntry.objects.filter(sample_week=week).exclude(review=CorpusReview.NOT_SAMPLED).count()
    copied = skipped = 0
    for message in _candidates()[: max(1, int(limit))]:
        outcome = _outcome_of(message)
        if outcome is None:
            skipped += 1  # o turno ainda não respondeu: copia no próximo ciclo
            continue
        categories = list((message.envelope or {}).get("redactions") or ())
        text = message.text
        if message.automation_eligible:
            # A conversa atendida guarda o texto como veio: a primeira limpeza é aqui, com o
            # nome que a conversa conhece. A observação já foi redigida na captura.
            known = str(getattr(message.conversation, "customer_name", "") or "")
            first = redact_observation_text(text, names=[known] if known else ())
            text, categories = first.text, [*categories, *first.categories]
        text, second = anonymize(text)
        local = timezone.localtime(message.created_at)
        review = CorpusReview.PENDING if sampled < SAMPLE_PER_WEEK else CorpusReview.NOT_SAMPLED
        try:
            with transaction.atomic():
                ConversationCorpusEntry.objects.create(
                    text=text,
                    redactions=sorted(set(categories) | set(second)),
                    intent=_intent_of(message),
                    outcome=outcome,
                    channel=str(getattr(message.binding, "transport_channel", "") or "")[:20],
                    weekday=local.weekday(),
                    hour_band=local.hour - local.hour % 3,
                    sample_week=week,
                    review=review,
                )
                envelope = {**(message.envelope or {}), COPIED_KEY: True}
                ConversationMessage.objects.filter(pk=message.pk).update(envelope=envelope)
        except Exception:
            logger.warning("concierge.corpus.copy_failed", exc_info=True)
            continue
        copied += 1
        if review == CorpusReview.PENDING:
            sampled += 1
    return {"copied": copied, "skipped": skipped, "paused": False}
