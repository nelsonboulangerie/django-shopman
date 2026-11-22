"""Sonda da central de entregas pelo Admin: a mesma sonda do console, no processo que tem os segredos.

## Por que existe

A rodada de homologação da TaOn (#2489) depende de duas ferramentas de linha de
comando: ``courier_machine_probe`` (lê a conta, os avisos e as corridas, e
escreve só com ``--write`` e o id repetido) e ``machine_register_webhook``.
Nenhuma das duas roda pelo console da DigitalOcean: o console não recebe as
variáveis ``SECRET``, então a credencial chega vazia (o mesmo motivo do botão de
e-mail do Diagnóstico), e o token de deploy não tem permissão de ``exec``.

O processo que tem a credencial é o que serve o Admin. Por isso a sonda sai
daqui, chamando os MESMOS comandos com ``call_command``: as travas (escrita só
com o id da corrida repetido, uma escrita por vez) e a máscara do laudo (nada de
nome, telefone, placa, endereço ou token) são as deles, e não uma cópia.

## O que ela NÃO faz

Não decide nada sobre pedido nem corrida da casa: lê e escreve na TaOn, como o
comando. O que a TaOn devolve chega ao app pelo caminho de sempre (aviso ou
batida do polling).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from django.core.management import call_command
from django.core.management.base import CommandError

logger = logging.getLogger(__name__)

#: Mais que isto e a requisição do Admin passa do tempo: cada corrida são dez leituras.
MAX_RIDES = 3

#: As escritas que a tela oferece, com o rótulo e o que o campo "valor" significa.
WRITE_ACTIONS = {
    "cancel": ("Cancelar a corrida", "o motivo (número da TaOn)"),
    "attach": ("Agrupar corridas nesta", "os ids das corridas a agrupar, separados por vírgula"),
    "remove_stop": ("Tirar uma parada", "o id da parada"),
    "boost": ("Impulsionar (gasta)", "o valor em reais, de 2,00 a 100,00"),
}

#: Cadastrar os avisos não tem corrida: a confirmação é a palavra abaixo.
REGISTER_WEBHOOKS = "register_webhooks"
REGISTER_CONFIRMATION = "CADASTRAR"


@dataclass(frozen=True)
class CourierProbeResult:
    ok: bool
    report: str
    wrote: bool


def _run(command: str, *args, **options) -> tuple[bool, str]:
    out = io.StringIO()
    try:
        call_command(command, *args, stdout=out, stderr=out, **options)
    except CommandError as exc:
        text = out.getvalue()
        return False, f"{text}\n{exc}".strip()
    except Exception as exc:  # o erro é o resultado da sonda
        logger.warning("courier_probe: %s falhou", command, exc_info=True)
        return False, f"{out.getvalue()}\n{type(exc).__name__}: {exc}".strip()
    return True, out.getvalue().strip()


def rides_from(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").replace(";", ",").split(",") if part.strip()]


def read(*, rides: list[str], window: int = 0, recent: int = 0) -> CourierProbeResult:
    """Só leitura: conta, avisos cadastrados, categorias, janela e corridas."""
    ok, report = _run(
        "courier_machine_probe", ride=list(rides)[:MAX_RIDES], window=int(window or 0), recent=int(recent or 0),
    )
    return CourierProbeResult(ok=ok, report=report, wrote=False)


def webhooks(public_base: str) -> CourierProbeResult:
    """Só leitura: os avisos cadastrados na TaOn, com o token mascarado."""
    ok, report = _run("machine_register_webhook", public_base, list=True)
    return CourierProbeResult(ok=ok, report=report, wrote=False)


def register_webhooks(public_base: str) -> CourierProbeResult:
    """ESCREVE na TaOn: cadastra os avisos que faltam (o comando pula o que já existe)."""
    ok, report = _run("machine_register_webhook", public_base)
    return CourierProbeResult(ok=ok, report=report, wrote=True)


def write(*, ride: str, action: str, value: str, confirm: str) -> CourierProbeResult:
    """ESCREVE na TaOn, pelas travas do comando: uma corrida, uma escrita, o id repetido."""
    if action not in WRITE_ACTIONS:
        return CourierProbeResult(ok=False, report=f"Escrita desconhecida: {action}.", wrote=False)
    value = str(value or "").strip()
    try:
        if action == "cancel":
            parsed: object = int(value)
        elif action == "boost":
            parsed = float(value.replace(",", "."))
        else:
            parsed = value
    except ValueError:
        return CourierProbeResult(
            ok=False, report=f"O valor precisa ser {WRITE_ACTIONS[action][1]}. Nada foi enviado.", wrote=False,
        )
    if parsed in ("", None):
        return CourierProbeResult(
            ok=False, report=f"Falta o valor: {WRITE_ACTIONS[action][1]}. Nada foi enviado.", wrote=False,
        )
    ok, report = _run(
        "courier_machine_probe", ride=[ride], write=True, confirm=str(confirm or "").strip(), **{action: parsed},
    )
    return CourierProbeResult(ok=ok, report=report, wrote=ok)


__all__ = [
    "CourierProbeResult",
    "MAX_RIDES",
    "REGISTER_CONFIRMATION",
    "REGISTER_WEBHOOKS",
    "WRITE_ACTIONS",
    "read",
    "register_webhooks",
    "rides_from",
    "webhooks",
    "write",
]
