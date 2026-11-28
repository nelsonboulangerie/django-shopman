"""Decide se um IP ainda pode pedir código de entrada (SMS pumping, beta 06/11)."""

from __future__ import annotations

import logging

# O Doorman já segura o número (5 por 15 min, 60 s entre envios) e o IP no
# G10 (DOORMAN.IP_RATE_LIMIT_MAX). O que faltava era o robô que troca de número
# a cada pedido: cada número novo passa pelos limites do número, e a conta do
# provedor de SMS é paga por mensagem. Estes dois tetos contam os códigos que
# este IP já pediu, em TODAS as finalidades (login, step-up da Conta e troca de
# número), na mesma tabela que o G10 já conta.
#
# Por que estes números (decisão do dono, 09/11/2026, depois do beta de
# encomendas): no 4G, muitos clientes saem pelo MESMO IP da operadora (CGNAT).
# Com 15 por hora, o 16º cliente do bairro ficava sem código e sem compra.
# 100 por hora deixa o IP compartilhado entrar; 300 por dia fecha o robô
# paciente que respeitaria o teto da hora o dia todo (100 x 24 = 2.400). O
# disparo concentrado é visto pelo aviso de volume global
# (LOGIN_CODES_GLOBAL_ALERT_PER_HOUR em services/auth.py), que chama a TI.
# Mudar é editar a constante e o teste ao lado.
LOGIN_CODES_PER_IP_PER_HOUR = 100
LOGIN_CODES_PER_IP_PER_DAY = 300


def ip_code_ceiling_refusal(ip_address: str | None):
    """Recusa (``CodeRequestResult``) quando o IP passou de um dos tetos; senão ``None``."""
    if not ip_address:
        return None
    from shopman.doorman.error_codes import ErrorCode
    from shopman.doorman.exceptions import GateError
    from shopman.doorman.gates import Gates
    from shopman.doorman.services.verification import CodeRequestResult

    for max_requests, window_minutes in (
        (LOGIN_CODES_PER_IP_PER_HOUR, 60),
        (LOGIN_CODES_PER_IP_PER_DAY, 24 * 60),
    ):
        try:
            Gates.ip_rate_limit(
                ip_address, max_requests=max_requests, window_minutes=window_minutes,
            )
        except GateError:
            from shopman.shop.services.observability import operational_event

            operational_event(
                "login_code.ip_ceiling",
                level=logging.WARNING,
                max_requests=max_requests,
                window_minutes=window_minutes,
            )
            return CodeRequestResult(
                success=False,
                error="Too many attempts from this location.",
                error_code=ErrorCode.IP_RATE_LIMIT,
            )
    return None
