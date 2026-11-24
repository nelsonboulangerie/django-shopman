"""O experimento de experiência no registro de regras (R4 do release, OC-20).

``RuleConfig.rule_path = "shopman.shop.rules.experience.ExperienceRule"`` aponta para
cá porque só ``shopman.shop.rules.*`` está na lista de módulos que o motor aceita
importar. A política (o que é um experimento válido) mora em
``shopman.shop.policies.experience``, onde política nova nasce.
"""

from __future__ import annotations

from shopman.shop.policies.experience import ExperienceRule as ExperienceRule
