"""Configuração de periférico do terminal do PDV.

Dataclass como source of truth do JSONField (`cashman.Terminal.metadata["hardware"]`):
o schema mora aqui, e o Admin, a projection e os testes leem daqui em vez de
cada um decorar as chaves.

**O corte de donos.** O que é fato da MÁQUINA do balcão — nome da fila CUPS,
porta, token, origens permitidas — mora no agente local, porque o servidor na DO
não tem como saber. O que é POLÍTICA da loja — adapter, endereço do agente,
pulso, se abre na venda — mora aqui, porque quem decide é o dono, pelo Admin.
Nada aparece nos dois lados: o pulso viaja no request, e o agente aplica o que
recebe sem ter opinião própria.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Sequência canônica da TM-T20: `ESC p 0 25 250` → `1B 70 00 19 FA`.
#: ⚠️ `0x19`/`0xFA` são 25 e 250 **unidades** de 2ms — ou seja 50ms e 500ms.
#: Chamar isso de "pulso 25/250ms" é atalho comum e erra pela metade; aqui os
#: números são milissegundos de verdade.
DEFAULT_PULSE_ON_MS = 50
DEFAULT_PULSE_OFF_MS = 500
DEFAULT_AGENT_URL = "http://127.0.0.1:47811"

#: `manual` = a gaveta abre com a chave, e o PDV não tem o que fazer.
#: `agent` = o agente local chuta pelo spooler.
ADAPTER_MANUAL = "manual"
ADAPTER_AGENT = "agent"
CASH_DRAWER_ADAPTERS = (ADAPTER_MANUAL, ADAPTER_AGENT)


@dataclass(frozen=True)
class CashDrawerConfig:
    """Como ESTE terminal abre a gaveta."""

    declared: bool = False
    enabled: bool = True
    adapter: str = ADAPTER_MANUAL
    agent_url: str = DEFAULT_AGENT_URL
    token: str = ""
    pulse_pin: int = 0
    pulse_on_ms: int = DEFAULT_PULSE_ON_MS
    pulse_off_ms: int = DEFAULT_PULSE_OFF_MS
    open_on_cash_sale: bool = True

    @classmethod
    def from_terminal(cls, terminal) -> CashDrawerConfig:
        metadata = dict(getattr(terminal, "metadata", None) or {})
        hardware = dict(metadata.get("hardware") or {})
        return cls.from_dict(hardware.get("cash_drawer"))

    @classmethod
    def from_dict(cls, raw) -> CashDrawerConfig:
        if not isinstance(raw, dict) or not raw:
            return cls()
        adapter = str(raw.get("adapter") or ADAPTER_MANUAL).strip().lower()
        if adapter not in CASH_DRAWER_ADAPTERS:
            adapter = ADAPTER_MANUAL
        return cls(
            declared=True,
            enabled=raw.get("enabled") is not False,
            adapter=adapter,
            agent_url=str(raw.get("agent_url") or DEFAULT_AGENT_URL).strip().rstrip("/"),
            token=str(raw.get("token") or "").strip(),
            pulse_pin=1 if raw.get("pulse_pin") in (1, "1") else 0,
            pulse_on_ms=_positive_int(raw.get("pulse_on_ms"), DEFAULT_PULSE_ON_MS),
            pulse_off_ms=_positive_int(raw.get("pulse_off_ms"), DEFAULT_PULSE_OFF_MS),
            open_on_cash_sale=raw.get("open_on_cash_sale") is not False,
        )

    @property
    def kicks_by_software(self) -> bool:
        """Este terminal tem caminho de software para abrir a gaveta?"""
        return self.declared and self.enabled and self.adapter == ADAPTER_AGENT

    @property
    def misconfigured_reason(self) -> str:
        """Por que o adapter `agent` não vai funcionar, em uma frase.

        Vazio = não há defeito conhecido daqui. "Daqui" é literal: o servidor
        não alcança a loopback do balcão, então isto pega erro de preenchimento,
        não agente caído.
        """
        if not self.kicks_by_software:
            return ""
        if not self.token:
            # O token nasce no Admin desde que o fluxo inverteu: basta salvar o
            # terminal com "Pelo agente local". Mandar colar o do instalador era
            # instrução do fluxo antigo, e mandava a pessoa para o lado errado.
            return "falta o token — salve este terminal com “Pelo agente local” para gerar um"
        if not self.agent_url:
            return "sem endereço do agente"
        return ""

    def surface_payload(self) -> dict:
        """O que a superfície precisa para chutar a gaveta.

        ⚠️ O token vai para o navegador — não tem como não ir, é o navegador que
        fala com o agente. Ele não abre nada além da gaveta daquele balcão, e a
        alternativa (mandar o comando pelo servidor) custaria uma volta à DO com
        o operador de mão esperando.
        """
        if not self.kicks_by_software:
            return {
                "adapter": self.adapter if self.declared else ADAPTER_MANUAL,
                "can_kick": False,
                "open_on_cash_sale": False,
                # A tela precisa DIZER por que não dá, em vez de esconder o card
                # e deixar o operador achando que o PDV está quebrado.
                "reason": self._unavailable_reason(),
                # Política da loja, não do aparelho: viaja nos dois ramos para o
                # contrato não mudar de forma conforme o terminal. Sem sensor
                # ninguém conta nada, e a tela já checa isso antes de olhar.
                "idle_open_alert_minutes": idle_open_alert_minutes(),
            }
        return {
            "adapter": ADAPTER_AGENT,
            "can_kick": not self.misconfigured_reason,
            "agent_url": self.agent_url,
            "token": self.token,
            "pulse": {
                "pin": self.pulse_pin,
                "on_ms": self.pulse_on_ms,
                "off_ms": self.pulse_off_ms,
            },
            "open_on_cash_sale": self.open_on_cash_sale,
            "reason": self.misconfigured_reason,
            # Quantos minutos a gaveta pode ficar aberta ENTRE vendas antes de
            # virar aviso. A trava já cuida do instante da venda; isto cobre a
            # hora morta, em que ninguém inicia venda nenhuma e a gaveta aberta
            # não seria vista por ninguém. `0` desliga.
            "idle_open_alert_minutes": idle_open_alert_minutes(),
        }

    def _unavailable_reason(self) -> str:
        """Por que este balcão não abre a gaveta por software, em uma frase."""
        if not self.declared:
            return "Gaveta não configurada neste terminal. Configure em Terminais do PDV, no gestor."
        if not self.enabled:
            return "A gaveta deste terminal está desligada na configuração."
        if self.adapter != ADAPTER_AGENT:
            return "Este balcão abre a gaveta com a chave — o PDV não tem como abrir."
        return self.misconfigured_reason or "Gaveta indisponível."


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


#: Default do aviso de gaveta aberta parada, em minutos.
#:
#: 3 minutos é a régua escolhida e ela é defensável: dar troco, conferir uma
#: nota e fechar leva segundos; uma gaveta que passa disso SEM nenhuma venda
#: começar não está em uso, está esquecida (ou aberta de propósito). Abaixo
#: disso o aviso pegaria o operador contando cédulas de boa-fé e viraria ruído;
#: bem acima, a gaveta ficaria aberta uma hora morta inteira sem ninguém saber.
DEFAULT_IDLE_OPEN_ALERT_MINUTES = 3


def idle_open_alert_minutes() -> int:
    """Minutos de gaveta aberta parada até virar aviso — editável no Admin.

    DONO ÚNICO da pergunta. Mora em ``Shop.defaults["pos"]``, ao lado do
    ``fiscal_toggle``, porque é política de PDV do estabelecimento — não regra
    de negócio avaliada num pipeline.

    ⚠️ Isto foi pedido como ``RuleConfig`` e **não** foi feito lá, de propósito:
    ``RuleConfig.rule_path`` é validado por importação, então uma régua de um
    inteiro exigiria inventar uma classe de regra que não avalia nada só para
    satisfazer o campo — jargão com aparência de arquitetura. O que o pedido
    queria (o dono muda sem deploy, e config errada não desliga a proteção
    calada) está inteiro aqui.

    Ausente cai no default. Valor inválido (texto, negativo) **também** cai no
    default, em vez de desligar o aviso: desligar proteção por erro de digitação
    é exatamente o modo de falha que não se aceita. Para desligar de propósito,
    ``0`` — que é explícito.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        defaults = (getattr(shop, "defaults", None) or {}) if shop else {}
        pos_cfg = defaults.get("pos") if isinstance(defaults, dict) else {}
        raw = (pos_cfg or {}).get("drawer_idle_alert_minutes")
    except Exception:
        logger.debug("pos_drawer_idle_lookup_failed", exc_info=True)
        return DEFAULT_IDLE_OPEN_ALERT_MINUTES
    if raw is None:
        return DEFAULT_IDLE_OPEN_ALERT_MINUTES
    if isinstance(raw, bool) or not isinstance(raw, int):
        logger.warning("drawer_idle_alert_minutes inválido (%r); usando o default.", raw)
        return DEFAULT_IDLE_OPEN_ALERT_MINUTES
    if raw < 0:
        logger.warning("drawer_idle_alert_minutes negativo (%r); usando o default.", raw)
        return DEFAULT_IDLE_OPEN_ALERT_MINUTES
    return raw
