"""
Production configuration — contrato único + cascata + validação.

Equivalente de ``ChannelConfig`` para o domínio de produção: todo knob que
governa sugestão, alertas e vínculo pedido↔produção vive aqui, lido de
``Shop.defaults["production"]`` com defaults sensatos. Nenhum consumidor lê
constantes hardcoded ou chaves cruas de JSONField.

Cascata: ``Shop.defaults["production"]`` → defaults deste dataclass.
(Produção é da loja, não do canal — não há nível de canal.)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class ProductionConfig:
    """
    Configuração de produção da loja.

    suggestion    — como a sugestão de produção é calculada?
    alerts        — quando o operador é avisado na tela?
    weight        — como a ficha vira o peso que o cliente lê na etiqueta?
    notifications — quais alertas também viram notificação (email/console)?
    order_match   — como pedidos confirmados se vinculam a WorkOrders?
    panel         — o painel de previsão (aeroporto) da equipe de loja.
    """

    # ── 1. Sugestão ──

    @dataclass
    class Suggestion:
        seasons: dict = field(default_factory=dict)
        # {"hot": [10, 11, 12, 1, 2, 3], "mild": [4, 5, 9], "cold": [6, 7, 8]}
        # Mês corrente resolve a estação; a lista de meses filtra o histórico
        # de demanda do craft.suggest(). Vazio = sem filtro sazonal.
        high_demand_multiplier: str | None = None
        # Decimal-string (ex: "1.2") aplicada em sexta/sábado. None = desligado.
        safety_stock_percent: str | None = None
        # Decimal-string (ex: "0.20") — margem sobre (demanda + committed).
        # None = default do Core (CRAFTSMAN["SAFETY_STOCK_PERCENT"]).

        @property
        def high_demand_multiplier_decimal(self) -> Decimal | None:
            return _decimal_or_none(self.high_demand_multiplier)

        @property
        def safety_stock_percent_decimal(self) -> Decimal | None:
            return _decimal_or_none(self.safety_stock_percent)

        def season_months_for(self, month: int) -> list[int] | None:
            """Meses da estação que contém ``month`` (None = sem filtro)."""
            for months in (self.seasons or {}).values():
                if isinstance(months, list) and month in months:
                    return [int(m) for m in months]
            return None

    # ── 2. Alertas ──

    @dataclass
    class Alerts:
        low_yield_threshold: str = "0.80"
        # Yield (finished/started) abaixo disto → OperatorAlert production_low_yield.
        default_max_started_minutes: int = 240
        # Janela padrão de produção em andamento; Recipe.meta["max_started_minutes"]
        # sobreescreve por receita.
        late_check_cadence_minutes: int = 15
        # Cadência do heartbeat production.late_check (0 = desligado).

        @property
        def low_yield_threshold_decimal(self) -> Decimal:
            return Decimal(self.low_yield_threshold)

    # ── 2b. Episódios que atrapalharam o dia ──

    @dataclass
    class Episodes:
        """Quando um silêncio de vendas vira pergunta no fechamento.

        A régua é da casa, não do código: numa padaria de bairro duas horas
        paradas no meio da tarde já é sinal de que algo houve; num dia de jogo
        grande, a rua inteira some por mais tempo e isso é normal. Quem sabe é
        quem opera — por isso o número mora na configuração.

        ``0`` desliga o detector de silêncio (os outros seguem).
        """

        sales_silence_minutes: int = 120

    # ── 2c. O peso que o cliente lê ──

    @dataclass
    class Weight:
        """Como a massa crua da ficha vira o peso anunciado da peça assada.

        O cliente não se importa de levar mais do que o rótulo diz; importa-se
        de levar menos. Por isso o anunciado é **piso**, e não média::

            assado esperado = cru por unidade × (1 − perda de forno)
            anunciado       = arredonda PARA BAIXO (assado × (1 − folga))

        ``default_bake_loss_pct`` é o número da casa (~12%) e é **estimativa
        não auditada**: ele nunca passou pela balança com a peça pronta. Ficha
        que declarar o próprio ``bake_loss_pct`` sobrescreve; ficha que
        declarar ``bake_loss_source="weighed"`` com autor e data é a única que
        conta como conferida.

        ``default_slack_pct`` é a folga de segurança sobre o assado esperado,
        conservadora de propósito: o dono quer que a peça de 90 g mire ~96 g no
        forno, e é essa distância que absorve variação de massa, de forno e de
        divisão sem transformar o rótulo em promessa falsa.
        """

        default_bake_loss_pct: str = "12"
        default_slack_pct: str = "5"

        @property
        def default_bake_loss_pct_decimal(self) -> Decimal:
            return Decimal(self.default_bake_loss_pct)

        @property
        def default_slack_pct_decimal(self) -> Decimal:
            return Decimal(self.default_slack_pct)

    # ── 3. Notificações ──

    @dataclass
    class Notifications:
        enabled: bool = False
        # Desligado por padrão: alerta de produção sempre aparece na tela
        # (OperatorAlert); notificação ativa (email/console via directive)
        # é opt-in para não virar ruído.
        severities: list[str] = field(default_factory=lambda: ["error"])
        # Severidades que notificam quando enabled. Default: só crítico
        # (estoque insuficiente); ampliar para ["error", "warning"] cobre
        # atraso/yield/esquecimento.

    # ── 4. Painel de previsão ──

    @dataclass
    class Panel:
        delay_tolerance_minutes: int = 15
        # Margem além do horário previsto antes de marcar ATRASADO. 15 avisa
        # a equipe antes do cliente perguntar; 30 esconde o problema demais.
        confirmed_ttl_minutes: int = 30
        # Quanto tempo um lote CONFIRMADO permanece no painel após a chegada
        # (depois disso o pão é assunto da gôndola, não do quadro).

    # ── Campos ──

    suggestion: Suggestion = field(default_factory=Suggestion)
    alerts: Alerts = field(default_factory=Alerts)
    episodes: Episodes = field(default_factory=Episodes)
    weight: Weight = field(default_factory=Weight)
    notifications: Notifications = field(default_factory=Notifications)
    panel: Panel = field(default_factory=Panel)
    order_match: str = "first_planned"
    # "first_planned" | "earliest_target" | "manual" — estratégia de vínculo
    # pedido confirmado → WorkOrder (production_order_sync).

    # ── Serialização ──

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProductionConfig:
        if not isinstance(data, dict):
            raise ValueError("production deve ser um dict")
        return cls(
            suggestion=_safe_init(cls.Suggestion, data.get("suggestion", {}), "production.suggestion"),
            alerts=_safe_init(cls.Alerts, data.get("alerts", {}), "production.alerts"),
            episodes=_safe_init(cls.Episodes, data.get("episodes", {}), "production.episodes"),
            weight=_safe_init(cls.Weight, data.get("weight", {}), "production.weight"),
            notifications=_safe_init(
                cls.Notifications,
                data.get("notifications", {}),
                "production.notifications",
            ),
            panel=_safe_init(cls.Panel, data.get("panel", {}), "production.panel"),
            order_match=data.get("order_match", cls.order_match),
        )

    @classmethod
    def defaults(cls) -> dict:
        return cls().to_dict()

    # ── Cascata ──

    @classmethod
    def load(cls) -> ProductionConfig:
        """Config resolvida da loja: ``Shop.defaults["production"]`` ← defaults."""
        from shopman.shop.config import deep_merge
        from shopman.shop.models import Shop

        base = cls.defaults()
        shop = Shop.load()
        overrides = (shop.defaults or {}).get("production") if shop else None
        if overrides is not None and not isinstance(overrides, dict):
            raise ValueError("Shop.defaults.production deve ser um dict")
        if overrides is not None:
            base = deep_merge(base, overrides)

        config = cls.from_dict(base)
        config.validate()
        return config

    # ── Validação ──

    def validate(self):
        if not isinstance(self.suggestion.seasons, dict):
            raise ValueError("production.suggestion.seasons deve ser um dict")
        assigned_months: set[int] = set()
        for season, months in self.suggestion.seasons.items():
            if not isinstance(months, list) or not all(
                isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12 for m in months
            ):
                raise ValueError(f"production.suggestion.seasons[{season!r}] deve ser lista de meses 1-12")
            if len(months) != len(set(months)):
                raise ValueError(f"production.suggestion.seasons[{season!r}] não pode repetir meses")
            overlap = assigned_months.intersection(months)
            if overlap:
                raise ValueError("production.suggestion.seasons não pode atribuir o mesmo mês a mais de uma estação")
            assigned_months.update(months)
        _require_decimal_or_none(
            self.suggestion.high_demand_multiplier,
            "production.suggestion.high_demand_multiplier",
            minimum=Decimal("0"),
        )
        _require_decimal_or_none(
            self.suggestion.safety_stock_percent,
            "production.suggestion.safety_stock_percent",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        threshold = _require_decimal_or_none(self.alerts.low_yield_threshold, "production.alerts.low_yield_threshold")
        if threshold is None or not (Decimal("0") <= threshold <= Decimal("1")):
            raise ValueError("production.alerts.low_yield_threshold deve estar entre 0 e 1")
        if not _is_int(self.alerts.default_max_started_minutes) or self.alerts.default_max_started_minutes <= 0:
            raise ValueError("production.alerts.default_max_started_minutes deve ser > 0")
        if not _is_int(self.alerts.late_check_cadence_minutes) or self.alerts.late_check_cadence_minutes < 0:
            raise ValueError("production.alerts.late_check_cadence_minutes deve ser >= 0")

        if not _is_int(self.episodes.sales_silence_minutes) or self.episodes.sales_silence_minutes < 0:
            raise ValueError("production.episodes.sales_silence_minutes deve ser >= 0")

        # Perda e folga são percentuais de uma fração que sobra: em 100% não
        # sobra peça nenhuma, e o anunciado viraria zero — promessa de nada.
        bake_loss = _require_decimal_or_none(
            self.weight.default_bake_loss_pct, "production.weight.default_bake_loss_pct"
        )
        if bake_loss is None or not (Decimal("0") <= bake_loss < Decimal("100")):
            raise ValueError("production.weight.default_bake_loss_pct deve estar entre 0 e 100 (exclusive)")
        slack = _require_decimal_or_none(self.weight.default_slack_pct, "production.weight.default_slack_pct")
        if slack is None or not (Decimal("0") <= slack < Decimal("100")):
            raise ValueError("production.weight.default_slack_pct deve estar entre 0 e 100 (exclusive)")

        if not isinstance(self.notifications.enabled, bool):
            raise ValueError("production.notifications.enabled deve ser booleano")
        severities = self.notifications.severities
        if not isinstance(severities, list) or not all(
            severity in ("info", "warning", "error", "critical") for severity in severities
        ):
            raise ValueError("production.notifications.severities deve ser lista de info|warning|error|critical")
        if len(severities) != len(set(severities)):
            raise ValueError("production.notifications.severities não pode conter duplicatas")
        if self.notifications.enabled and not severities:
            raise ValueError(
                "production.notifications.severities deve informar ao menos uma severidade "
                "quando notificações estão ativas"
            )

        if not _is_int(self.panel.delay_tolerance_minutes) or self.panel.delay_tolerance_minutes < 0:
            raise ValueError("production.panel.delay_tolerance_minutes deve ser >= 0")
        if not _is_int(self.panel.confirmed_ttl_minutes) or self.panel.confirmed_ttl_minutes < 0:
            raise ValueError("production.panel.confirmed_ttl_minutes deve ser >= 0")

        if self.order_match not in ("first_planned", "earliest_target", "manual"):
            raise ValueError(f"production.order_match inválido: {self.order_match}")


def _safe_init(cls, data: dict, label: str):
    """Instancia um dataclass filtrando campos desconhecidos."""
    import dataclasses

    if not isinstance(data, dict):
        raise ValueError(f"{label} deve ser um dict")
    valid_fields = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decimal_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _require_decimal_or_none(
    value,
    label: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal | None:
    try:
        parsed = _decimal_or_none(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} deve ser um decimal válido") from exc
    if parsed is not None and not parsed.is_finite():
        raise ValueError(f"{label} deve ser um decimal finito")
    if parsed is not None:
        if minimum is not None and parsed < minimum:
            raise ValueError(f"{label} deve ser >= {minimum}")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"{label} deve ser <= {maximum}")
    return parsed
