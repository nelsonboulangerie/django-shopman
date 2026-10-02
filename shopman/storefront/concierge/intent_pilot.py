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
5. ``shadow_triage``: o Jev decide, em sombra, a intenção de cada mensagem nova,
   e a decisão fica gravada ao lado da regra local (``envelope["triage_shadow"]``).
   Nada muda para o cliente. É o teste do Jev decidindo, pedido pelo dono em
   02/10/2026 (D-028); ``shadow_report`` diz onde os dois discordam.

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
    shadowed: int = 0
    shadow_skipped: str = ""


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

    try:
        result.shadowed = shadow_triage(days=retention)
    except ContenderNotConfigured as exc:
        result.shadow_skipped = str(exc)
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


# ── "Medir agora": o placar fora do relógio semanal ─────────────────────────
#
# O ciclo mede sozinho a cada ``MEASURE_EVERY``. Quando a casa quer o placar já
# (concorrente novo ligado, gabarito que cresceu), o Admin enfileira uma medição:
# são dezenas de chamadas a modelos, então roda no worker de diretivas, nunca
# dentro da requisição.

MEASURE_TOPIC = "intent_pilot.measure"
MEASURE_DEDUPE_KEY = MEASURE_TOPIC


def measurement_pending() -> bool:
    """Já há uma medição na fila ou rodando."""
    from shopman.orderman.models import Directive

    return Directive.objects.filter(
        topic=MEASURE_TOPIC, dedupe_key=MEASURE_DEDUPE_KEY, status__in=("queued", "running"),
    ).exists()


def enqueue_measurement(*, requested_by: str = "") -> bool:
    """Enfileira uma medição forçada. ``False`` quando já havia uma pendente.

    ``available_at`` no futuro: o dispatcher por signal pula a diretiva e ela fica
    para o worker. Sem isso a medição rodaria INLINE, no fim da requisição do Admin.
    """
    from shopman.shop.directives import create_deduped

    if measurement_pending():
        return False
    created = create_deduped(
        MEASURE_TOPIC,
        payload={"requested_by": requested_by[:150]},
        dedupe_key=MEASURE_DEDUPE_KEY,
        available_at=timezone.now() + timedelta(seconds=2),
    )
    return created is not None


class IntentPilotMeasureHandler:
    """Mede agora e guarda o placar. Topic: ``intent_pilot.measure``.

    Falha é terminal de propósito: repetir a medição cinco vezes seria pagar
    cinco vezes pelas mesmas chamadas. Quem pediu vê o placar não chegar e pede
    de novo.
    """

    topic = MEASURE_TOPIC

    def handle(self, *, message, ctx: dict) -> None:
        from shopman.orderman.exceptions import DirectiveTerminalError

        del ctx
        requested_by = (message.payload or {}).get("requested_by", "")
        try:
            measurement = maybe_measure(force=True)
        except Exception as exc:
            logger.exception("intent_pilot: medição pedida por %s falhou", requested_by or "?")
            raise DirectiveTerminalError(f"medição falhou: {type(exc).__name__}") from exc
        logger.info("intent_pilot: medição pedida por %s: %s", requested_by or "?", measurement.reason)


# ── Sombra: o Jev decide, a regra local decide, a casa compara ──────────────
#
# A Concierge em ``observe`` não decide nada ao vivo, e a entrada promete que
# nenhuma mensagem sai da casa no caminho do webhook. A sombra roda aqui, no
# ciclo do piloto, com o mesmo portão do comparador (``typesafe`` aprovado e
# ``JEV_API_KEY``). A decisão do Jev é a que a triagem tomaria com
# ``triage_classifier = "jev"`` (``triage.best_jev_intent``), menos a trava do
# sensível, que a sombra guarda separada para a casa ver onde ela agiria.

SHADOW_KEY = "triage_shadow"
SHADOW_BATCH = 60


def shadow_triage(*, limit: int = SHADOW_BATCH, days: int = 0, contender=None) -> int:
    """Grava a decisão da regra e a do Jev nas mensagens novas. Devolve quantas.

    Levanta ``ContenderNotConfigured`` sem aprovação ou sem chave. Falha do
    provedor para o lote: as que faltaram ficam para o próximo ciclo.
    """
    from shopman.shop.models import ConversationMessage
    from shopman.storefront.concierge import triage
    from shopman.storefront.concierge.intent_benchmark import JevContender

    if limit <= 0:
        return 0
    contender = contender or JevContender(timeout=10.0)
    candidates = (
        ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND)
        .exclude(text="")
        .exclude(envelope__has_key=SHADOW_KEY)
    )
    if days:
        candidates = candidates.filter(created_at__gte=timezone.now() - timedelta(days=days))
    done = 0
    for message in candidates.order_by("-id")[:limit]:
        try:
            prediction = triage.jev_scores(message.text, contender=contender)
        except ContenderResponseError as exc:
            logger.warning("intent_pilot: sombra ilegível na mensagem %s: %s", message.pk, exc)
            continue
        except Exception as exc:  # rede, cota: o lote para e o próximo ciclo segue
            logger.warning("intent_pilot: Jev falhou na sombra (%s)", type(exc).__name__)
            break
        rules_intent, rules_source = triage.classify_rules(message.text)
        jev_intent = triage.best_jev_intent(prediction.intents)
        stamp = {
            "rules": rules_intent,
            "rules_source": rules_source,
            "jev": jev_intent,
            "jev_scores": {ref: round(p, 3) for ref, p in prediction.intents.items()},
            "latency_ms": round(prediction.latency_ms),
            "model": getattr(contender, "model", ""),
            "at": timezone.now().isoformat(),
        }
        envelope = {**(message.envelope or {}), SHADOW_KEY: stamp}
        ConversationMessage.objects.filter(pk=message.pk).update(envelope=envelope)
        done += 1
    return done


def shadow_report(*, days: int = 7, examples: int = 15) -> str:
    """Onde o Jev e a regra local concordam e discordam, em texto para o dono ler."""
    import statistics
    from collections import Counter

    from shopman.shop.models import ConversationMessage
    from shopman.storefront.concierge import triage
    from shopman.storefront.concierge.observation_privacy import redact_observation_text

    rows = list(
        ConversationMessage.objects.filter(
            kind=ConversationMessage.Kind.INBOUND,
            envelope__has_key=SHADOW_KEY,
            created_at__gte=timezone.now() - timedelta(days=days),
        )
        .order_by("-id")
        .values_list("id", "text", "envelope")
    )
    if not rows:
        return f"Nenhuma mensagem com sombra do Jev nos últimos {days} dias."
    label = triage.DEFAULT_LABELS
    agree = 0
    pairs: Counter = Counter()
    sensitive_lost, sensitive_gained, jev_blank = [], [], 0
    latencies = []
    disagreements = []
    for pk, text, envelope in rows:
        shadow = envelope[SHADOW_KEY]
        rules_intent, jev_intent = shadow.get("rules", ""), shadow.get("jev", "")
        latencies.append(shadow.get("latency_ms") or 0)
        if not jev_intent:
            jev_blank += 1
        if rules_intent == jev_intent:
            agree += 1
            continue
        pairs[(rules_intent, jev_intent or "(nenhuma)")] += 1
        rules_sensitive = rules_intent in triage.SENSITIVE or rules_intent == "special_order"
        if rules_sensitive:
            sensitive_lost.append(pk)
        elif jev_intent in triage.SENSITIVE:
            sensitive_gained.append(pk)
        said = redact_observation_text(str(text or "")).text
        disagreements.append((pk, rules_intent, jev_intent, " ".join(said.split())[:120]))

    total = len(rows)
    lines = [
        f"Sombra do Jev, últimos {days} dias: {total} mensagens.",
        f"Mesma intenção que a regra local: {agree} ({agree * 100 // total}%).",
        f"Jev sem nenhuma intenção acima do corte: {jev_blank} (aí vale a regra).",
        f"Tempo do Jev: mediana {statistics.median(latencies):.0f} ms, pior {max(latencies):.0f} ms.",
        f"Regra viu sensível e o Jev não ({len(sensitive_lost)}): ao vivo a regra vence, nada se perde.",
        f"Jev viu sensível e a regra não ({len(sensitive_gained)}): ao vivo o Jev escalaria estas.",
        "",
        "Discordâncias mais comuns (regra → Jev):",
    ]
    for (rules_intent, jev_intent), count in pairs.most_common(10):
        lines.append(f"  {count:>3}  {label.get(rules_intent, rules_intent)} → {label.get(jev_intent, jev_intent)}")
    if disagreements:
        lines += ["", f"Exemplos (até {examples}; texto redigido):"]
        for pk, rules_intent, jev_intent, text in disagreements[:examples]:
            lines.append(f"  #{pk}  regra: {rules_intent}  Jev: {jev_intent or '(nenhuma)'}  \"{text}\"")
    return "\n".join(lines)

