"""As escritas da sonda da central de entregas pelo Admin: prévia, confirmação e registro.

A leitura mora em ``courier_probe``. Aqui ficam as sondas que MUDAM a conta da
casa na TaOn (cancelar, agrupar, tirar parada, impulsionar, cadastrar avisos),
e por isso cada uma passa por três portas:

1. **Prévia.** Antes de mandar, a tela mostra o endereço, o corpo e o custo
   estimado do que vai sair. A prévia não chama a rede.
2. **Confirmação na página.** O envio repete o número da corrida (as travas do
   próprio ``courier_machine_probe``: uma corrida, uma escrita, o id repetido).
   Cadastrar avisos não tem corrida: a confirmação é a palavra ``CADASTRAR``.
3. **Registro.** Toda chamada, aceita ou recusada, vira uma entrada no
   histórico da Loja no Admin (``LogEntry``): quem, quando, o que foi mandado e
   o laudo que voltou (já mascarado pelo comando, sem credencial).

O ``PUT`` da v2 (editar a corrida em andamento) não está aqui: ele substitui
todas as paradas, e mandá-lo errado muda o destino de uma entrega (#3325).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.admin.models import CHANGE, LogEntry

from shopman.backstage.services.courier_probe import CourierProbeResult, run_command

logger = logging.getLogger(__name__)

REGISTER_WEBHOOKS = "register_webhooks"
REGISTER_CONFIRMATION = "CADASTRAR"

#: O teto do registro: o laudo de uma escrita são poucas linhas, mas o histórico não é arquivo.
MAX_RECORDED_REPORT = 4000

#: Cada escrita: rótulo, o que o campo "valor" significa, e o custo estimado (estimado, nunca medido).
WRITES = {
    "cancel": {
        "label": "Cancelar a corrida",
        "value": "o motivo (número da TaOn)",
        "cost": "Antes do aceite, nada (estimado, não medido). Depois do aceite a central pode cobrar taxa de cancelamento.",
    },
    "attach": {
        "label": "Agrupar corridas nesta",
        "value": "os números das corridas a agrupar, separados por vírgula",
        "cost": "A central recalcula o valor da corrida que agrupa (estimado, não medido).",
    },
    "remove_stop": {
        "label": "Tirar uma parada",
        "value": "o id da parada (lido no laudo da corrida)",
        "cost": "A central recalcula o valor da corrida sem a parada (estimado, não medido).",
    },
    "boost": {
        "label": "Impulsionar",
        "value": "o valor em reais, de 2,00 a 100,00",
        "cost": "Gasta o valor do impulso, uma vez por corrida.",
    },
    REGISTER_WEBHOOKS: {
        "label": "Cadastrar os avisos que faltam",
        "value": "nada",
        "cost": "Nada. O comando pula o tipo que já está cadastrado.",
    },
}


@dataclass(frozen=True)
class WritePreview:
    """O que vai sair para a TaOn, antes de sair."""

    ok: bool
    action: str
    label: str
    ride: str
    value: str
    request: str
    cost: str
    confirmation_hint: str
    problem: str = ""


def _parse(action: str, value: str):
    value = str(value or "").strip()
    if action == "cancel":
        return int(value)
    if action == "boost":
        amount = float(value.replace(",", "."))
        if not 2 <= amount <= 100:
            raise ValueError
        return amount
    if action == "attach":
        ids = [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        if not ids:
            raise ValueError
        return ",".join(str(i) for i in ids)
    if not value:
        raise ValueError
    return value


def preview(*, action: str, rides: list[str], value: str, public_base: str) -> WritePreview:
    """Monta a prévia. Não chama a rede."""
    spec = WRITES.get(action)
    if spec is None:
        return WritePreview(False, action, action, "", "", "", "", "", problem=f"Escrita desconhecida: {action}.")
    if action == REGISTER_WEBHOOKS:
        return WritePreview(
            ok=True, action=action, label=spec["label"], ride="", value="",
            request=(
                f"GET /listarWebhook e, para cada tipo que faltar (status, posicao), POST /cadastrarWebhook "
                f"com a URL {public_base}/api/webhooks/machine/?token=(o token do app, mascarado)"
            ),
            cost=spec["cost"], confirmation_hint=f"Escreva {REGISTER_CONFIRMATION}.",
        )
    if len(rides) != 1:
        return WritePreview(False, action, spec["label"], "", value, "", spec["cost"], "",
                            problem="A escrita pede exatamente uma corrida. Nada foi enviado.")
    ride = rides[0]
    try:
        parsed = _parse(action, value)
    except ValueError:
        return WritePreview(False, action, spec["label"], ride, value, "", spec["cost"], "",
                            problem=f"O valor precisa ser {spec['value']}. Nada foi enviado.")
    request = {
        "cancel": f"POST /api/integracao/cancelar com id_mch={ride} e motivo_id={parsed}",
        "attach": f"POST /api/v2/integracao/entregas/{ride}/agrupar com solicitacoes_agrupadas=[{parsed}]",
        "remove_stop": f"DELETE /api/v2/integracao/entregas/{ride}/paradas/{parsed}",
        "boost": f"POST /api/v2/integracao/entregas/{ride}/impulsionar com valor={parsed:.2f}",
    }[action]
    request += f"; depois, GET /solicitacaoStatus da corrida {ride} (leitura)"
    return WritePreview(
        ok=True, action=action, label=spec["label"], ride=ride, value=str(value).strip(),
        request=request, cost=spec["cost"], confirmation_hint=f"Repita o número da corrida: {ride}.",
    )


def send(*, user, shop, action: str, rides: list[str], value: str, confirm: str, public_base: str) -> CourierProbeResult:
    """Manda a escrita pelas travas do comando e registra a chamada no histórico da Loja."""
    shown = preview(action=action, rides=rides, value=value, public_base=public_base)
    if not shown.ok:
        return CourierProbeResult(ok=False, report=shown.problem)
    confirm = str(confirm or "").strip()
    if action == REGISTER_WEBHOOKS:
        if confirm.upper() != REGISTER_CONFIRMATION:
            return CourierProbeResult(
                ok=False, report=f"Para cadastrar, escreva {REGISTER_CONFIRMATION} na confirmação. Nada foi enviado.",
            )
        ok, report = run_command("machine_register_webhook", public_base)
    else:
        ok, report = run_command(
            "courier_machine_probe", ride=[shown.ride], write=True, confirm=confirm,
            **{action: _parse(action, value)},
        )
    _record(user=user, shop=shop, shown=shown, ok=ok, report=report)
    return CourierProbeResult(ok=ok, report=report)


def _record(*, user, shop, shown: WritePreview, ok: bool, report: str) -> None:
    message = (
        f"Sonda da central de entregas, escrita: {shown.label}. "
        f"Mandado: {shown.request}. "
        f"Resultado: {'respondeu' if ok else 'recusou ou falhou'}.\n"
        f"{report[:MAX_RECORDED_REPORT]}"
    )
    logger.info(
        "diagnostics.courier_probe_write user=%s action=%s ride=%s ok=%s",
        user.pk, shown.action, shown.ride, ok,
    )
    if shop is not None:
        LogEntry.objects.log_actions(user.pk, [shop], CHANGE, change_message=message)


__all__ = ["REGISTER_CONFIRMATION", "REGISTER_WEBHOOKS", "WRITES", "WritePreview", "preview", "send"]
