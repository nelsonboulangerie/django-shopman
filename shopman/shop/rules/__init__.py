"""Shopman rules — configurable pricing and validation rules via admin.

- engine.py: loads, caches, and registers active RuleConfigs
- pricing.py: D1, Promotion, Employee, HappyHour rule wrappers
- validation.py: BusinessHours, MinimumOrder validators
"""


class BaseRule:
    """Marker base class for all configurable RuleConfig rule classes.

    Every class referenced in RuleConfig.rule_path must inherit from this.
    Ensures the whitelist + import check in RuleConfig.clean() can verify
    legitimacy without relying on naming conventions alone.
    """

    code: str = ""
    label: str = ""
    rule_type: str = ""
    #: ``RuleConfig.channels`` vazio quer dizer "todos os canais" — salvo quando a
    #: regra declara ``channels_required``: aí vazio quer dizer "nenhum", e ela só
    #: vale onde estiver listada (``engine.get_channel_rule_params``).
    channels_required: bool = False
