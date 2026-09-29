"""O ciclo do piloto de intenções — a máquina faz, a casa confere.

Quatro passos, cada um com o próprio limite, e o ciclo inteiro roda sozinho no
``maintenance_worker`` (``run_intent_pilot``):

1. ``ensure_categories``: o vocabulário existe (idempotente, nunca sobrescreve).
2. ``sample_messages``: sorteia mensagens de entrada recentes que ainda não
   estão na amostra. Teto por dia e teto de fila aberta, para a equipe nunca
   receber mais do que confere.
3. ``propose_labels``: um modelo forte da Anthropic pré-marca as intenções
   (``sugerida``). Só com o provedor aprovado; sem chave, a fila espera a pessoa.
4. ``maybe_measure``: com gabarito suficiente e o último placar velho, mede os
   concorrentes e guarda o placar (``IntentPilotReport``) para o Admin.

**Por que a pressa é a certa:** a mensagem observada vence em dias
(``CONCIERGE_OBSERVATION_RETENTION_DAYS``, default 7) e leva a amostra junto. O
ciclo sorteia só o recente e pré-rotula na hora, para a conferência caber na
janela; o placar guardado não tem texto e fica.

**O viés declarado:** o gabarito nasce da sugestão de um modelo. A pessoa corrige
o que discorda, mas sugestão ancora. Por isso o modelo que sugere
(``AI_ASSIST_MODEL``) não entra no placar automático, que mede outros
(``DEFAULT_LLM_MODELS``), a regex e os embeddings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from shopman.storefront.concierge.intent_benchmark import (
    DEFAULT_LLM_MODELS,
    PRESENT_AT,
    ContenderNotConfigured,
    ContenderResponseError,
    LLMContender,
    Sample,
    build_contenders,
    gold_samples,
    load_categories,
    prices_for,
    render_report,
    run,
)

logger = logging.getLogger(__name__)

DAILY_SAMPLE_CAP = 40
OPEN_QUEUE_CAP = 200
PROPOSE_BATCH = 40
MIN_LABELED_TO_MEASURE = 30
MEASURE_EVERY = timedelta(days=7)

# O vocabulário inicial, (ref, nome, descrição, sensível). Nasceu da conversa com
# o dono em 23/09/2026 — os temas de fora da venda (vaga, parceria, fornecedor,
# como funciona a casa) foram pedidos dele. Continua sendo dado: o Admin manda.
DEFAULT_INTENTS = (
    # Cliente comprando ou por comprar.
    ("order", "Pedido", "Fazer, alterar ou cancelar um pedido: quer comprar algo agora ou para uma data.", False),
    (
        "product_question", "Dúvida de produto",
        "Pergunta sobre produto: o que tem hoje, sabor, ingrediente, tamanho, preço.", False,
    ),
    (
        "hours_delivery", "Horário, endereço, retirada ou entrega",
        "Pergunta onde fica a casa, que horas abre ou fecha, como retirar, se entrega, frete ou prazo.", False,
    ),
    ("order_status", "Status do pedido", "Quer saber de um pedido já feito: se saiu, quando chega, se está pronto.", False),
    ("special_order", "Encomenda especial", "Encomenda grande, personalizada ou para evento (festa, casamento, empresa).", False),
    (
        "house_info", "Como funciona a casa",
        "Dúvida sobre a casa em si: se aceita pet, mesa e reserva, wi-fi, estacionamento, acessibilidade, "
        "formas de pagamento, cardápio do salão.", False,
    ),
    # O que não pode passar batido.
    ("complaint", "Reclamação", "Reclama de pedido, produto, cobrança, atraso ou atendimento.", True),
    ("allergy", "Alergia ou restrição", "Menciona alergia, intolerância ou restrição alimentar (glúten, lactose, nozes…).", True),
    ("human", "Falar com uma pessoa", "Pede para falar com um atendente ou uma pessoa da equipe.", True),
    # Quem escreve não é cliente: vai para outra mesa da casa.
    ("job", "Vaga de emprego", "Procura emprego ou estágio, manda currículo ou pergunta se há vaga.", False),
    (
        "partnership", "Parceria ou divulgação",
        "Propõe parceria, permuta ou divulgação: influenciador, imprensa, sessão de fotos ou gravação no local.", False,
    ),
    (
        "supplier_offer", "Proposta de fornecedor",
        "Oferece produto ou serviço para a casa: fornecedor, representante, prestador.", False,
    ),
)



def ensure_categories() -> int:
    """Cria as intenções padrão que faltam. Devolve quantas criou."""
    from shopman.storefront.models import IntentCategory

    created = 0
    for position, (ref, name, description, sensitive) in enumerate(DEFAULT_INTENTS, start=1):
        _obj, was_created = IntentCategory.objects.get_or_create(
            ref=ref,
            defaults={"name": name, "description": description, "sensitive": sensitive, "position": position * 10},
        )
        created += was_created
    return created


def sample_messages(*, limit: int, days: int = 0, min_chars: int = 3) -> int:
    """Sorteia até ``limit`` mensagens de entrada com texto que ainda não estão na amostra."""
    from shopman.shop.models import ConversationMessage
    from shopman.storefront.models import MessageIntentSample

    if limit <= 0:
        return 0
    candidates = (
        ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND)
        .exclude(text="")
        .filter(intent_sample__isnull=True)
    )
    if days:
        candidates = candidates.filter(created_at__gte=timezone.now() - timedelta(days=days))
    picked = [
        message_id
        for message_id, text in candidates.order_by("?").values_list("id", "text")[: limit * 3]
        if len((text or "").strip()) >= min_chars
    ][:limit]
    MessageIntentSample.objects.bulk_create([MessageIntentSample(message_id=pk) for pk in picked])
    return len(picked)


def propose_labels(*, limit: int = PROPOSE_BATCH, model: str | None = None, contender=None) -> int:
    """Pré-marca as amostras ``a rotular``. Devolve quantas viraram ``sugerida``.

    Levanta ``ContenderNotConfigured`` se o provedor não estiver aprovado ou não
    houver chave — o chamador decide se isso é silêncio ou erro.
    """
    from shopman.storefront.models import IntentCategory, MessageIntentSample, SampleStatus

    contender = contender or LLMContender(model=model or settings.AI_ASSIST_MODEL)
    categories = load_categories()
    if not categories:
        return 0
    by_ref = {category.ref: category for category in IntentCategory.objects.filter(active=True)}
    proposed = 0
    pending = (
        MessageIntentSample.objects.filter(status=SampleStatus.PENDING)
        .select_related("message")
        .order_by("id")[:limit]
    )
    for sample in pending:
        try:
            prediction = contender.predict(Sample(sample.pk, sample.redacted_text(), frozenset()), categories)
        except ContenderResponseError as exc:
            logger.warning("intent_pilot: sugestão ilegível na amostra %s: %s", sample.pk, exc)
            continue
        except Exception as exc:  # rede, cota: a amostra espera o próximo ciclo
            logger.warning("intent_pilot: provedor falhou na amostra %s: %s", sample.pk, type(exc).__name__)
            break
        sample.intents.set([by_ref[ref] for ref, confidence in prediction.intents.items() if confidence >= PRESENT_AT])
        sample.status = SampleStatus.PROPOSED
        sample.suggested_by = getattr(contender, "model", contender.name)[:60]
        sample.save(update_fields=["status", "suggested_by"])
        proposed += 1
    return proposed


@dataclass
class Measurement:
    report: object | None  # IntentPilotReport ou None
    reason: str


def maybe_measure(*, force: bool = False, llm_models=DEFAULT_LLM_MODELS) -> Measurement:
    """Mede e guarda o placar quando há gabarito e o último está velho."""
    from shopman.storefront.models import IntentPilotReport

    samples = gold_samples()
    if len(samples) < MIN_LABELED_TO_MEASURE and not force:
        return Measurement(None, f"gabarito com {len(samples)} de {MIN_LABELED_TO_MEASURE} mensagens conferidas")
    if not samples:
        return Measurement(None, "gabarito vazio")
    last = IntentPilotReport.objects.order_by("-created_at").first()
    if last and not force and timezone.now() - last.created_at < MEASURE_EVERY:
        return Measurement(None, f"último placar de {last.created_at:%d/%m}; o próximo sai em até 7 dias")
    categories = load_categories()
    contenders, skipped = build_contenders(("regex", "embed", "llm", "jev"), llm_models=list(llm_models))
    prices, _unpriced = prices_for(contenders)
    boards = run(samples, categories, contenders, prices=prices)
    report = IntentPilotReport.objects.create(
        samples=len(samples),
        contenders=", ".join(board.contender for board in boards)[:240],
        skipped="\n".join(f"{name}: {reason}" for name, reason in skipped),
        report=render_report(boards, samples, categories),
    )
    return Measurement(report, "medido")


@dataclass
class CycleResult:
    categories_created: int = 0
    sampled: int = 0
    proposed: int = 0
    proposal_skipped: str = ""
    measurement: str = ""


def run_cycle(*, now=None) -> CycleResult:
    """Um ciclo inteiro. Cada passo respeita o próprio teto; nenhum depende de console."""
    from shopman.storefront.models import MessageIntentSample, SampleStatus

    now = now or timezone.now()
    result = CycleResult(categories_created=ensure_categories())

    retention = _retention_days()
    today = MessageIntentSample.objects.filter(created_at__date=timezone.localdate(now)).count()
    open_queue = MessageIntentSample.objects.filter(status__in=[SampleStatus.PENDING, SampleStatus.PROPOSED]).count()
    room = min(DAILY_SAMPLE_CAP - today, OPEN_QUEUE_CAP - open_queue)
    if room > 0:
        result.sampled = sample_messages(limit=room, days=retention)

    try:
        result.proposed = propose_labels()
    except ContenderNotConfigured as exc:
        result.proposal_skipped = str(exc)

    result.measurement = maybe_measure().reason
    return result


def _retention_days() -> int:
    """A menor janela de observação configurada (default 7): sortear mais velho é sortear o que vai sumir."""
    windows = []
    connections = (getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}).get("connections", {}) or {}
    for connection in connections.values():
        observation = ((connection or {}).get("options") or {}).get("observation") or {}
        try:
            days = int(observation.get("retention_days"))
        except (TypeError, ValueError):
            continue
        if 1 <= days <= 30:
            windows.append(days)
    return min(windows) if windows else 7
