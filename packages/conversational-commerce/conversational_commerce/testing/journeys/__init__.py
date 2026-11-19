"""Jornadas de referência como dados roteirizados (v2 10): J1 e J2 no F7, J4 no F8, J3 e J5 no F9.

Cada jornada é uma sequência de passos: a mensagem que chega, o que o leitor
roteirizado "entende" dela, e o que se espera do turno (movimentos escolhidos,
trechos do texto, estado do episódio). Passo que não é mensagem do cliente (a
equipe responde, J3) traz ``act``. ``run_journey`` roda os passos sobre os
falsos; um adaptador roda a mesma jornada sobre as portas dele.
"""

from .runner import JourneyStep, ScriptedModel, StepResult, run_journey

__all__ = ["JourneyStep", "ScriptedModel", "StepResult", "run_journey"]
