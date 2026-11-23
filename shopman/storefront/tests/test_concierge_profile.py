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


def test_the_profile_validates_with_the_twenty_one_lines(shop):
    built = _profile()
    assert isinstance(built, DeploymentProfile) and built.environment == "shadow"
    assert built.tenant == "nelson-boulangerie"
    assert [state.plan_id for state in profile_lines.LINES] == [f"P{n:02d}" for n in range(1, 22)]
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


def test_the_profile_never_spends_and_never_calls_a_model_in_shadow(shop):
    """Gasto zero, e nenhuma chamada a modelo.

    O teto de uma chamada ao leitor do turno existe para a leitura da casa (``LocalReader``)
    entregar ao motor os campos do pedido (DEV-2026-076). Essa porta não chama modelo: ela diz
    isso na capacidade e conta zero chamadas no consumo. Trocar o leitor por um que chama modelo
    tem de reprovar aqui.
    """
    from shopman.storefront.concierge.ports import LocalReader

    built = _profile()
    assert built.limits.max_spend.amount_minor == 0
    assert built.limits.max_model_calls <= 1
    assert LocalReader().capabilities().guarantees["calls_model"] is False


def test_no_new_file_reads_settings_directly():
    """ADR-042: configuração de loja passa pelos acessores, nunca por ``settings`` num arquivo novo."""
    here = Path(profile.__file__).parent
    for name in ("profile.py", "profile_lines.py"):
        text = (here / name).read_text(encoding="utf-8")
        assert not re.search(r"\bsettings\.|os\.environ", text), name
