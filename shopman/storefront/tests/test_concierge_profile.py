"""O perfil da Nice no framework de comércio conversacional (N3).

O que estes testes seguram:

- o perfil valida pelo contrato estrito do framework (``DeploymentProfile``), com as 21
  linhas do plano do adaptador, cada uma com dono, data e estado;
- K39 no perfil real: linha ausente (P12, P13) ou fora de ``approved`` (P08) torna a ação
  inelegível com o código da linha, e linha que perde o valor (P09 a P11) também;
  ``inform_limitation`` e ``handoff`` seguem admissíveis;
- o teto do desconto vem do ``ChannelConfig`` do canal da Concierge, nunca de constante;
- nenhuma linha nova lê ``settings`` direto (ADR-042): os valores passam pelos acessores.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from conversational_commerce.catalog import evaluate_move
from conversational_commerce.catalog.situation import Situation
from conversational_commerce.contracts import DeploymentProfile
from conversational_commerce.profile import IneligibilityCode, read_line
from conversational_commerce.testing.conformance import conformance

from shopman.shop.models import Channel, Shop
from shopman.storefront.concierge import profile, profile_lines

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
NOW = "2026-11-19T12:00:00.000000Z"
ALWAYS = ("inform_limitation", "handoff")


@pytest.fixture
def shop():
    Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie", short_name="Nelson")
    return Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={})


def _set_cap(percent) -> None:
    channel = Channel.objects.get(ref=CHANNEL)
    channel.config = {**(channel.config or {}), "pricing": {"concierge_discount_max_percent": percent}}
    channel.save(update_fields=["config"])


def _config(**overrides):
    base = {"channel_ref": CHANNEL, "operation_mode": "assist", "read_only": True,
            "connections": {"primary": {"channel": CHANNEL, "provider": "manychat", "options": {
                "stable_event_identity_verified": False, "identity_link_enabled": False,
                "observation": {"retention_days": "7"}}}}}
    return {**base, **overrides}


def _profile(**kwargs) -> DeploymentProfile:
    return profile.build_profile(config=_config(), occurred_at=NOW, **kwargs)


def _situation(**fields) -> Situation:
    base = {"now": NOW, "channel": CHANNEL, "identity": "transported", "event_assurance": "provider_claimed",
            "reading_count": 1, "request_kind": "query", "missing_required_field": False,
            "answer_changes_decision": True, "question_open_for_need": False, "requested_move_ineligible": True,
            "reply_only_courtesy": False, "handoff_reason": "customer_request"}
    return Situation(**{**base, **fields})


def _without(built: DeploymentProfile, line_id: str) -> DeploymentProfile:
    lines = tuple(dataclasses.replace(line, setting={"status": "absent", "reason": "test"}, state="proposed",
                                      decided_at=None) if line.id == line_id else line for line in built.lines)
    return dataclasses.replace(built, lines=lines)


def test_the_profile_validates_with_the_twenty_two_lines(shop):
    built = _profile()
    assert isinstance(built, DeploymentProfile) and built.environment == "shadow"
    assert built.tenant == "nelson-boulangerie"
    # P22: #3380; P23 a P28: a auditoria das linhas que o motor lê (23/11).
    assert [state.plan_id for state in profile_lines.LINES] == [f"P{n:02d}" for n in range(1, 29)]
    assert {line.id for line in built.lines} == {state.line_id for state in profile_lines.LINES}
    for state in profile_lines.LINES:
        line = next(line for line in built.lines if line.id == state.line_id)
        assert line.owner == state.owner
        if state.state == "absent":
            assert line.setting.status == "absent" and line.state == "proposed"
        else:
            assert line.state == state.state and line.decided_at == state.decided_at
    # O contrato não aceita linha aprovada sem data nem ausente aprovada: a montagem passou por ele.
    assert built.house_rules_ref.endswith("house_rules.RULES")
    assert tuple(read_line(built, "house_rules").value) == profile.house_rule_ids()


def test_the_discount_cap_comes_from_the_channel_config(shop):
    assert read_line(_profile(), "commerce.discount_cap_percent").value == "2.5"  # o padrão do ChannelConfig
    _set_cap(1.75)
    assert read_line(_profile(), "commerce.discount_cap_percent").value == "1.75"
    _set_cap(0)
    assert read_line(_profile(), "commerce.discount_cap_percent").value == "0"


def test_the_live_mode_and_channel_are_measured_not_assumed(shop):
    built = profile.build_profile(config=_config(read_only=False, operation_mode="observe"), occurred_at=NOW)
    assert read_line(built, "live.mode").value["read_only"] is False
    assert read_line(built, "live.mode").value["operation_mode"] == "observe"
    assert read_line(built, "channel.capabilities").value["stable_event_identity_verified"] is False
    assert built.privacy.retention_days == {"observation": 7}
    broken = profile.build_profile(config=_config(connections={}), occurred_at=NOW)
    assert broken.privacy.retention_days == {}  # retenção sem valor válido fica fora, nunca vira zero


@conformance("K39", scope="adapter")
@pytest.mark.parametrize(("move", "line_id", "code"), [
    ("recommend", "commerce.recommend", IneligibilityCode.PROFILE_LINE_ABSENT),  # P13 ausente
    ("present_terms", "commerce.order_in_conversation", IneligibilityCode.PROFILE_LINE_NOT_APPROVED),  # P08
    ("change_cart", "commerce.order_in_conversation", IneligibilityCode.PROFILE_LINE_NOT_APPROVED),
    ("set_fulfillment", "commerce.order_in_conversation", IneligibilityCode.PROFILE_LINE_NOT_APPROVED),
    ("commit_order", "commerce.order_in_conversation", IneligibilityCode.PROFILE_LINE_NOT_APPROVED),
])
def test_k39_on_the_real_profile_lines_without_decision_keep_the_action_ineligible(shop, move, line_id, code):
    built = _profile()
    assert built.actions[move].line_ref == line_id
    evaluation = evaluate_move(move, _situation(), built)
    assert not evaluation.eligible and code in evaluation.blocked_by
    for always in ALWAYS:
        assert evaluate_move(always, _situation(), built).eligible, always


@pytest.mark.parametrize(("move", "line_id"), [("grant_discount", "commerce.discount_cap_percent"),
                                               ("cancel_order", "commerce.cancel_order"),
                                               ("amend_order", "commerce.amend_order")])
def test_k39_the_three_approved_mandates_fall_with_their_line(shop, move, line_id):
    """P09 a P11 estão aprovadas (dono, 18/11); sem a linha, a ação cai com o código dela."""
    built = _profile()
    assert read_line(built, line_id).usable
    evaluation = evaluate_move(move, _situation(), _without(built, line_id))
    assert IneligibilityCode.PROFILE_LINE_ABSENT in evaluation.blocked_by
    for always in ALWAYS:
        assert evaluate_move(always, _situation(), _without(built, line_id)).eligible


def test_compensation_has_no_mandate_and_verify_waits_for_the_concierge(shop):
    built = _profile()
    assert read_line(built, "commerce.compensation").code == IneligibilityCode.PROFILE_LINE_ABSENT  # P12
    assert "verify_with_staff" not in built.actions  # entra com o WP-05 da Concierge
    assert evaluate_move("verify_with_staff", _situation(), built).blocked_by[0] == \
        IneligibilityCode.PROFILE_ACTION_ABSENT


def test_the_profile_reads_once_by_model_and_spends_only_through_the_house_brake(shop):
    """P04 (D-040): uma leitura pela IA por turno; o gasto é do freio da casa, nunca do teto do motor."""
    built = _profile()
    assert built.limits.max_model_calls == 1 and built.limits.max_spend.amount_minor == 0


def test_no_new_file_reads_settings_directly():
    """ADR-042: configuração de loja passa pelos acessores, nunca por ``settings`` num arquivo novo."""
    here = Path(profile.__file__).parent
    for name in ("profile.py", "profile_lines.py"):
        text = (here / name).read_text(encoding="utf-8")
        assert not re.search(r"\bsettings\.|os\.environ", text), name


# ── #3380: a validade da concessão (sem ela, nenhum efeito executa) ────────────────────


def _with_order_line_approved(built):
    """A P08 aprovada SÓ no teste: ligá-la no ar continua dependendo do Pablo."""
    import dataclasses

    lines = tuple(dataclasses.replace(line, state="approved", decided_at=line.decided_at or NOW)
                  if line.id == "commerce.order_in_conversation" else line for line in built.lines)
    return dataclasses.replace(built, lines=lines)


def _line_grant(built):
    from conversational_commerce.authority import issue_line_grant
    from conversational_commerce.contracts import IdentityEvidence

    record = {"id": "grant-1", "tenant": built.tenant, "environment": "live", "trace_id": "t-1", "cause_id": None,
              "occurred_at": NOW, "producer": {"name": "test", "version": "1"}, "episode_id": "ep-1"}
    return issue_line_grant(record=record, grant_id="g-1", subject="conversation:1", action="change_cart",
                            targets=("sess-1",), identity_evidence=(IdentityEvidence(
                                kind="transport_subject", ref="5543999990000", assurance="transported"),),
                            profile=built, now=NOW)


def test_the_grant_validity_line_is_engineering_600_seconds(shop):
    line = read_line(_profile(), "grant.validity_seconds")
    assert line.usable and line.value == 600
    assert next(lin for lin in _profile().lines if lin.id == "grant.validity_seconds").owner == "engineering"


def test_with_the_grant_validity_line_an_effect_gets_its_grant(shop):
    grant = _line_grant(_with_order_line_approved(_profile()))
    assert grant.action == "change_cart" and grant.valid_until > NOW


def test_without_the_grant_validity_line_nothing_executes(shop):
    import dataclasses

    from conversational_commerce.authority import GrantRefused

    built = _with_order_line_approved(_profile())
    without = dataclasses.replace(built, lines=tuple(lin for lin in built.lines if lin.id != "grant.validity_seconds"))
    with pytest.raises(GrantRefused) as refused:
        _line_grant(without)
    assert refused.value.code == "profile_line_absent"



# ── as linhas que o motor lê (auditoria de 23/11) ───────────────────────────────────────────────


def _lines_the_engine_reads() -> set[str]:
    """Toda linha que o pacote lê pelo perfil: as constantes passadas a ``read_line`` e as ``line_ref`` das ações.

    Mecânico, pelo código-fonte do pacote: uma leitura nova sem linha declarada na Nice reprova aqui, antes de
    chegar ao ar (a P22 e a P23 só apareceram no ar, porque o perfil de teste do pacote tem todas).
    """
    import conversational_commerce

    root = Path(conversational_commerce.__file__).parent
    constants: dict[str, str] = {}
    names: set[str] = set()
    for source in root.rglob("*.py"):
        if "tests" in source.parts or source.name == "test_profile.py":
            continue
        text = source.read_text(encoding="utf-8")
        constants.update(re.findall(r'^([A-Z_]+_LINE) = "([^"]+)"', text, flags=re.MULTILINE))
        names.update(re.findall(r"read_line\(\s*[\w.]+\s*,\s*([A-Za-z_][\w.]*)\s*\)", text))
    names.discard("line_id")  # a própria definição
    names.discard("rule.line_ref")  # as line_ref das ações, conferidas abaixo pelo perfil
    unknown = sorted(name for name in names if name not in constants)
    assert not unknown, f"leitura de linha que a auditoria não resolve: {unknown}"
    return {constants[name] for name in names}


def test_every_line_the_engine_reads_is_declared(shop):
    """Toda linha que o motor lê tem estado no perfil da Nice: com valor, ou ausente de propósito, com motivo."""
    built = _profile()
    declared = {line.id: line for line in built.lines}
    read = _lines_the_engine_reads()
    assert {"episode.inactivity_window_seconds", "effect.reconciliation_deadline_seconds",
            "grant.validity_seconds"} <= read  # a varredura acha as leituras conhecidas
    refs = {rule.line_ref for rule in built.actions.values() if getattr(rule, "line_ref", None)}
    missing = sorted((read | refs) - set(declared))
    assert not missing, f"linha que o motor lê e a Nice não declara: {missing}"
    for line_id in read | refs:
        state = profile_lines.BY_LINE_ID.get(line_id)
        assert state is not None, line_id
        if state.state == "absent":
            assert state.absent_reason, f"{line_id}: ausente sem motivo"


def test_with_the_inactivity_line_the_next_message_continues_the_episode(shop):
    from conversational_commerce.contracts import Producer
    from conversational_commerce.engine.turn import INACTIVITY_LINE
    from conversational_commerce.workflow.correlation import correlate
    from conversational_commerce.workflow.machine import open_episode

    line = read_line(_profile(), INACTIVITY_LINE)
    assert line.usable and line.value == 86400
    assert profile_lines.BY_LINE_ID[INACTIVITY_LINE].owner == "engineering"
    episode = open_episode(record_id="eprec-1", episode_id="ep-1", tenant="t", environment="live", trace_id="tr",
                           at="2026-11-23T10:00:00.000000Z", producer=Producer(name="t", version="1"),
                           subject="binding:whatsapp:1")
    later = "2026-11-23T10:05:00.000000Z"  # a próxima mensagem, cinco minutos depois
    kept = correlate(subject="binding:whatsapp:1", now=later, episodes=[episode], inactivity_seconds=line.value)
    assert kept.action == "continue"
    # Sem a linha (janela 0, como era): cada mensagem abria um episódio, e a pergunta no ar morria.
    lost = correlate(subject="binding:whatsapp:1", now=later, episodes=[episode], inactivity_seconds=0)
    assert lost.action == "open_new"


def test_the_reconciliation_deadline_is_fifteen_minutes_not_one_second(shop):
    from conversational_commerce.ledger.receipts import deadline_seconds

    built = _profile()
    assert deadline_seconds(built) == 900
    without = dataclasses.replace(built, lines=tuple(
        lin for lin in built.lines if lin.id != "effect.reconciliation_deadline_seconds"))
    assert deadline_seconds(without) is None  # e o recibo pendente prometia "até" daqui a 1 segundo
