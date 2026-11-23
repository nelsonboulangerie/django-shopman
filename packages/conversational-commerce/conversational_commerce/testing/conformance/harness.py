"""Arnês de forma das portas: o que toda implementação de cada porta tem de cumprir.

Os mesmos testes rodam contra os falsos (``tests/ports/``) e contra o
adaptador real, que fornece o seu ``HarnessEnv`` (contexto confiável e
entradas que existem no sistema dele) e chama ``run_checks``. Não depende de
pytest: devolve a lista de falhas, e quem chama decide como reprovar.

Isto é a FORMA da porta (tipos, capacidades, garantias mínimas observáveis).
O comportamento do núcleo sobre as portas são os testes K, de cada WP.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from conversational_commerce.contracts import (
    ActionCommand,
    ActionReceipt,
    Commitment,
    Episode,
    Estimate,
    ExposureEvent,
    InteractionEvent,
    Known,
    MetricRef,
    OutcomeEvent,
    Producer,
    Quantity,
    TermsDocument,
    Unavailable,
    Understanding,
    Unknown,
    Window,
    command_content_hash,
    compute_hash,
)
from conversational_commerce.contracts.common import IDENTITY_LADDER
from conversational_commerce.ports import (
    PORTS,
    Budget,
    Capabilities,
    EffectState,
    InterpretRequest,
    KnownCost,
    ModelRequest,
    PortError,
    PreparedMessage,
    PromiseReading,
    StaffQuestion,
    StaffTicket,
    Transition,
    TrustedContext,
    WorkItem,
)

PRODUCER = Producer(name="conformance-harness", version="1")
INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class HarnessEnv:
    """O que o adaptador fornece para o arnês rodar sobre o sistema dele."""

    ctx: TrustedContext
    clock: Any  # ClockPort: o arnês tira instantes e ids dele
    raw_message: Mapping[str, Any] = field(default_factory=dict)
    item_ref: str = ""
    cart_ref: str = ""
    other_subject: str = ""
    policy_id: str = ""
    currency: str = "XTS"
    # Devolve termos vigentes do carrinho (normalmente, ``commerce_read.quote``).
    fresh_terms: Callable[[], TermsDocument] | None = None
    # Recebimento (``set_fulfillment``), opcional: um recebimento que o sistema aceita no ``cart_ref``
    # (``date``, ``mode``, ``window`` e/ou ``time``) e uma referência de janela que ele não oferece.
    # Sem ``fulfillment``, a checagem do recebimento não roda: a casa que não liga o movimento não o executa.
    fulfillment: Mapping[str, str] | None = None
    unknown_window: str = ""


@dataclass(frozen=True, slots=True)
class CheckFailure:
    port: str
    check: str
    message: str


class AllowGuard:
    """Guarda que deixa passar e registra o estado que viu (para o arnês conferir que foi chamada)."""

    def __init__(self) -> None:
        self.seen: list[EffectState] = []

    def verify(self, state: EffectState) -> None:
        self.seen.append(state)


class RefuseGuard:
    def __init__(self, code: str = "authority_revoked") -> None:
        self.code = code
        self.seen: list[EffectState] = []

    def verify(self, state: EffectState) -> None:
        self.seen.append(state)
        raise PortError(self.code, "recusado pelo arnês")


def _envelope(env: HarnessEnv, prefix: str, **extra: Any) -> dict[str, Any]:
    return {"id": env.clock.new_id(prefix), "tenant": env.ctx.tenant, "environment": env.ctx.environment,
            "trace_id": env.clock.new_id("trace"), "occurred_at": env.clock.now(), "producer": PRODUCER, **extra}


def _command(env: HarnessEnv, terms: TermsDocument, *, key: str, parameters: Mapping[str, Any]) -> ActionCommand:
    targets = (env.cart_ref,)
    return ActionCommand(
        **_envelope(env, "cmd", episode_id="harness-episode"),
        command_id=env.clock.new_id("command"),
        decision_id="harness-decision",
        grant_id="harness-grant",
        action="commit_order",
        targets=targets,
        parameters=parameters,
        terms_hash=terms.hash,
        expected_versions={},
        expected_ownership_epoch=0,
        idempotency={"scope": "harness", "key": key},
        content_hash=command_content_hash(action="commit_order", targets=targets, parameters=parameters,
                                          terms_hash=terms.hash),
        deadline=_later(env),
    )


def _later(env: HarnessEnv, seconds: int = 600) -> str:
    """Um instante ``seconds`` depois do agora do relógio da porta (só pela ``ClockPort``)."""
    moment = datetime.strptime(env.clock.now(), INSTANT_FORMAT).replace(tzinfo=UTC) + timedelta(seconds=seconds)
    return moment.strftime(INSTANT_FORMAT)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_error(code: str, action: Callable[[], Any]) -> None:
    try:
        action()
    except PortError as error:
        _expect(error.code == code, f"esperado PortError {code}, veio {error.code}")
    else:
        raise AssertionError(f"esperado PortError {code}, não houve erro")


# ── checagens comuns ─────────────────────────────────────────────────────────


def check_capabilities(name: str, port: Any, env: HarnessEnv) -> None:
    protocol, required = PORTS[name]
    _expect(isinstance(port, protocol), f"não implementa {protocol.__name__}")
    capabilities = port.capabilities()
    _expect(isinstance(capabilities, Capabilities), "capabilities() não devolve Capabilities")
    _expect(capabilities.port == name, f"capabilities().port é {capabilities.port}, esperado {name}")
    missing = sorted(set(required) - set(capabilities.operations))
    _expect(not missing, f"operações não declaradas: {missing}")


# ── por porta ────────────────────────────────────────────────────────────────


def check_channel(port: Any, env: HarnessEnv) -> None:
    event = port.normalize(env.ctx, env.raw_message, env.clock.now())
    _expect(isinstance(event, InteractionEvent), "normalize não devolve InteractionEvent")
    _expect((event.tenant, event.environment) == (env.ctx.tenant, env.ctx.environment),
            "o evento não leva o inquilino e o ambiente do contexto confiável")
    for evidence in event.identity_evidence:
        _expect(IDENTITY_LADDER.index(evidence.assurance) <= IDENTITY_LADDER.index("transported"),
                "o canal promoveu identidade sem prova (acima de transported)")
    prepared = PreparedMessage(decision_id="harness-decision", content_hash="sha256:" + "0" * 64,
                               recipient="harness-recipient", binding=event.channel_binding, body_ref="harness:body")
    first = port.send(env.ctx, prepared, "harness-key-1")
    again = port.send(env.ctx, prepared, "harness-key-1")
    _expect(isinstance(first, ExposureEvent), "send não devolve ExposureEvent")
    _expect(first.id == again.id, "mesma chave de envio duplicou a exposição")
    _expect(first.state in ("submitted", "accepted", "unknown", "delivered"), f"estado inicial {first.state}")
    status = port.delivery_status(env.ctx, first.id)
    _expect(isinstance(status, ExposureEvent) and status.decision_id == first.decision_id,
            "delivery_status não devolve a exposição da mesma decisão")
    if not port.capabilities().guarantees.get("read_receipts", False):
        _expect(status.state != "read", "canal sem leitura informou leitura")


def check_model(port: Any, env: HarnessEnv) -> None:
    request = ModelRequest(purpose="interpret", budget=Budget(max_calls=5, max_spend={"amount_minor": 0,
                                                                                      "currency": env.currency}),
                           data_class="redacted")
    understanding, consumption = port.interpret(env.ctx, InterpretRequest(
        request=request, event_id="harness-event", content_ref="text:what are the hours", allowed_acts=("ask_hours",)))
    _expect(isinstance(understanding, Understanding), "interpret não devolve Understanding")
    _expect(understanding.event_id == "harness-event", "o entendimento não aponta o evento lido")
    _expect(isinstance(consumption.cost, KnownCost | Unavailable), "consumo sem custo conhecido nem Unavailable")
    _expect_error("object_forbidden", lambda: port.interpret(env.ctx, InterpretRequest(
        request=ModelRequest(purpose="interpret", budget=request.budget, data_class="personal"),
        event_id="harness-event", content_ref="text:x", allowed_acts=())))


def check_commerce_read(port: Any, env: HarnessEnv) -> None:
    fact = port.read_item(env.ctx, env.item_ref)
    _expect(isinstance(fact, Known | Unknown), "read_item não devolve Fact")
    if isinstance(fact, Known):
        _expect(fact.source != "", "fato sem fonte")
    reading = port.promise(env.ctx, env.item_ref, Quantity(value="1", unit="unit"), env.clock.now())
    _expect(isinstance(reading, PromiseReading), "promise não devolve PromiseReading")
    terms = port.quote(env.ctx, env.cart_ref)
    _expect(isinstance(terms, TermsDocument) and terms.hash == compute_hash(terms), "cotação sem hash que confere")
    _expect(isinstance(port.scarcity(env.ctx, env.item_ref), Estimate | Unavailable),
            "scarcity não devolve Estimate nem Unavailable")
    if env.other_subject:
        _expect_error("object_forbidden", lambda: port.read_customer(env.ctx, env.other_subject))


def check_commerce_execute(port: Any, env: HarnessEnv) -> None:
    _expect("atomic_effect_guard" in port.capabilities().guarantees,
            "o executor não declara se chama a guarda na unidade atômica do efeito")
    if env.fresh_terms is None:
        raise AssertionError("HarnessEnv.fresh_terms é obrigatório para o executor")
    terms = env.fresh_terms()
    guard = AllowGuard()
    command = _command(env, terms, key="harness-exec-1", parameters={"note": "a"})
    receipt = port.execute(env.ctx, command, guard)
    _expect(isinstance(receipt, ActionReceipt), "execute não devolve ActionReceipt")
    _expect(guard.seen, "o executor não chamou a guarda")
    again = port.execute(env.ctx, command, guard)
    _expect(again.id == receipt.id, "mesma chave e mesmo conteúdo não devolveram o mesmo recibo")
    other = _command(env, terms, key="harness-exec-1", parameters={"note": "b"})
    _expect_error("idempotency_conflict", lambda: port.execute(env.ctx, other, guard))
    located = port.locate(env.ctx, "harness", "harness-exec-1")
    _expect(located is not None and located.id == receipt.id, "locate não acha o recibo pela chave")
    refused = port.execute(env.ctx, _command(env, env.fresh_terms(), key="harness-exec-2", parameters={}),
                           RefuseGuard())
    _expect((refused.status, refused.effect) == ("failure", "not_applied"), "guarda recusou e houve efeito")
    check_set_fulfillment(port, env)


def _fulfillment_command(env: HarnessEnv, *, key: str, parameters: Mapping[str, Any]) -> ActionCommand:
    targets = (env.cart_ref,)
    return ActionCommand(
        **_envelope(env, "cmd", episode_id="harness-episode"),
        command_id=env.clock.new_id("command"),
        decision_id="harness-decision",
        grant_id="harness-grant",
        action="set_fulfillment",
        targets=targets,
        parameters=parameters,
        expected_versions={},
        expected_ownership_epoch=0,
        idempotency={"scope": "harness", "key": key},
        content_hash=command_content_hash(action="set_fulfillment", targets=targets, parameters=parameters,
                                          terms_hash=None),
        deadline=_later(env),
    )


def check_set_fulfillment(port: Any, env: HarnessEnv) -> None:
    """O comando ``set_fulfillment``: aplica o que foi dito, o recibo aponta o recebimento, a janela
    desconhecida é recusada sem efeito com ``fulfillment_window_unknown``, e a forma inválida com
    ``invalid_fulfillment``."""
    if env.fulfillment is None:
        return
    guard = AllowGuard()
    command = _fulfillment_command(env, key="harness-fulfillment-1", parameters=dict(env.fulfillment))
    receipt = port.execute(env.ctx, command, guard)
    _expect(guard.seen, "o executor não chamou a guarda no recebimento")
    _expect((receipt.status, receipt.effect) == ("success", "applied"), "recebimento válido não foi aplicado")
    for name, value in env.fulfillment.items():
        _expect(receipt.domain_refs.get(name) == value, f"o recibo não aponta o {name} aplicado")
    _expect(port.execute(env.ctx, command, guard).id == receipt.id,
            "mesma chave e mesmo conteúdo não devolveram o mesmo recibo do recebimento")
    if env.unknown_window:
        unknown = port.execute(env.ctx, _fulfillment_command(env, key="harness-fulfillment-2",
                                                             parameters={"window": env.unknown_window}), guard)
        _expect((unknown.status, unknown.effect) == ("failure", "not_applied"), "janela desconhecida foi aplicada")
        _expect(unknown.error.code == "fulfillment_window_unknown", "janela desconhecida sem o código estável")
    malformed = port.execute(env.ctx, _fulfillment_command(env, key="harness-fulfillment-3",
                                                           parameters={"date": "tomorrow"}), guard)
    _expect((malformed.status, malformed.effect) == ("failure", "not_applied"), "data fora de ISO foi aplicada")
    _expect(malformed.error.code == "invalid_fulfillment", "data fora de ISO sem o código estável")


def check_staff(port: Any, env: HarnessEnv) -> None:
    ticket = port.ask(env.ctx, StaffQuestion(episode_id="harness-episode", question="Is it available?",
                                             respond_by=_later(env)))
    _expect(isinstance(ticket, StaffTicket), "ask não devolve StaffTicket")
    _expect(ticket.accepted_by is None, "roteado não é aceito: ask não pode nomear quem aceitou")
    commitment = Commitment(**_envelope(env, "cmt", episode_id="harness-episode"), commitment_id="harness-c1",
                            type="promise", obligation="answer the question", owner="staff-queue",
                            deadline={"status": "set", "at": _later(env), "rule_ref": "harness"},
                            fulfillment_criterion="customer receives the answer", state="open")
    _expect(port.open_or_update(env.ctx, commitment).owner, "compromisso sem dono")
    handback = port.return_conversation(env.ctx, "harness-episode", 7)
    _expect(handback.new_epoch == 7, "devolução não registra a época nova")
    _expect_error("revision_conflict", lambda: port.return_conversation(env.ctx, "harness-episode", 7))


def check_store(port: Any, env: HarnessEnv) -> None:
    event = InteractionEvent(**_envelope(env, "evt", episode_id="harness-ep"), channel_binding={"channel": "harness", "conversation_ref": "c"},
                             actor="customer", event_identity={"id": "harness-msg-1", "assurance": "verified"},
                             type="message")
    first, created = port.record_event_once(env.ctx, event)
    duplicate = InteractionEvent(**{**_envelope(env, "evt")}, channel_binding=event.channel_binding,
                                 actor="customer", event_identity=event.event_identity, type="message")
    second, created_again = port.record_event_once(env.ctx, duplicate)
    _expect(created and not created_again and second.id == first.id, "a mesma identidade de evento gravou duas vezes")
    episode = Episode(**_envelope(env, "eprec", episode_id="harness-ep"), state="active", version=1,
                      ownership={"owner": "automation", "epoch": 0}, opened_at=env.clock.now())
    work = WorkItem(work_id="harness-work-1", kind="harness", payload={}, due_at=env.clock.now())
    port.commit_transition(env.ctx, Transition(episode=episode, expected_version=0), (event,), (work,))
    loaded = port.load_episode(env.ctx, "harness-ep")
    _expect(loaded is not None and loaded.version == 1, "load_episode não devolve o que foi confirmado")
    claim = port.claim_work(env.ctx, "harness", 60)
    _expect(claim is not None and claim.work.work_id == work.work_id, "a caixa de saída não entrega o trabalho gravado")
    port.complete_work(env.ctx, work.work_id)
    _expect(port.claim_work(env.ctx, "harness", 60) is None, "trabalho concluído voltou da caixa de saída")
    _expect_error("revision_conflict", lambda: port.commit_transition(
        env.ctx, Transition(episode=episode, expected_version=0), (), ()))
    latest = port.latest_record(env.ctx, "harness-ep", InteractionEvent.SCHEMA)
    _expect(latest is not None and latest.id == event.id, "latest_record não devolve o último registro do episódio")
    _expect(port.latest_episode(env.ctx, "harness-subject") is None, "latest_episode inventou episódio")
    other_tenant = TrustedContext(tenant=f"{env.ctx.tenant}-other", environment=env.ctx.environment)
    _expect(port.load_episode(other_tenant, "harness-ep") is None, "um inquilino leu o episódio de outro")


def check_clock(port: Any, env: HarnessEnv) -> None:
    first, second = port.now(), port.now()
    _expect(second >= first, "o relógio voltou")
    _expect(port.new_id("h") != port.new_id("h"), "new_id repetiu")
    handle = port.schedule(first, WorkItem(work_id="harness-timer", kind="harness", payload={}, due_at=first))
    _expect(port.cancel(handle) is True, "cancel não achou o agendamento")
    _expect(isinstance(port.business_hours(first), Known | Unknown), "business_hours não devolve Fact")


def check_outcomes(port: Any, env: HarnessEnv) -> None:
    window = Window(start=env.clock.now(), end=_later(env))
    outcome = port.harvest(env.ctx, MetricRef(id="harness_metric", definition_version="1"), "harness-subject", window)
    _expect(isinstance(outcome, OutcomeEvent), "harvest não devolve OutcomeEvent")
    _expect(outcome.observation == "censored" and outcome.value is None,
            "janela ainda aberta: resultado censurado, sem valor (N21)")


CHECKS: dict[str, Callable[[Any, HarnessEnv], None]] = {
    "channel": check_channel,
    "model": check_model,
    "commerce_read": check_commerce_read,
    "commerce_execute": check_commerce_execute,
    "staff": check_staff,
    "store": check_store,
    "clock": check_clock,
    "outcomes": check_outcomes,
}


def run_checks(name: str, port: Any, env: HarnessEnv) -> list[CheckFailure]:
    """Roda a checagem de capacidades e a da porta; devolve as falhas (vazio é verde)."""
    failures = []
    for label, check in (("capabilities", lambda p, e: check_capabilities(name, p, e)), (name, CHECKS[name])):
        try:
            check(port, env)
        except Exception as error:  # noqa: BLE001 - porta quebrada é falha do arnês, nunca exceção solta
            failures.append(CheckFailure(name, label, f"{type(error).__name__}: {error}"))
    return failures
