"""Perfil de implantação: leitura de linha, códigos de inelegibilidade e o perfil de teste.

A forma do perfil é o contrato ``DeploymentProfile`` (F1). Aqui mora como o
núcleo LÊ o perfil: que linha vale, que código sai quando não vale. O perfil de
teste (``test_profile.build_test_profile``) liga todos os movimentos com os
valores padrão do plano, decisão 5; é perfil de teste, não o de casa nenhuma.
"""

from .codes import IneligibilityCode, unknown_code
from .lines import LineReading, find_line, read_line

__all__ = ["IneligibilityCode", "LineReading", "find_line", "read_line", "unknown_code"]
