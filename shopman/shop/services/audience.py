"""AudienceResolver — quem merece saber, e antes de quem.

Cruza um evento operacional (fornada, reposição) com o que já sabemos do
cliente para achar a audiência quente de um SKU: quem favoritou, quem pediu
para ser avisado, quem compra sempre. Nunca a lista toda.

Três invariantes:

1. **Consentimento é lei, e tem um dono só.** Sem ``CommunicationConsent`` com
   status ``opted_in`` no canal de entrega, ninguém recebe. Sem exceção (LGPD e,
   antes disso, confiança). A única porta lateral é a assinatura de alerta por
   SKU, que já É um consentimento explícito daquele produto.

   O dono é o ``CommunicationConsent`` do guestman — o mesmo registro que o
   cliente escreve ao mexer nos canais na tela da conta, e que carrega base
   legal, IP e data de revogação. Consultado pela API pública
   (``ConsentService``), nunca por model interno de contrib.
2. **Um destinatário por telefone.** As três regras se sobrepõem muito; o
   telefone normalizado é a chave de dedupe, então ninguém recebe em dobro.
3. **VIP primeiro é vantagem, não exclusão.** O atraso do grupo geral é uma
   janela de privilégio, e todo mundo acaba recebendo.

O envio sai em **ondas** (``AudienceResult.waves()``): o VIP abre, o geral vem
depois do atraso configurado, e quem tem hora habitual conhecida
(``CustomerInsight.preferred_hour``) pode ser adiado até ela — nunca além da
janela da regra, porque fornada quente não espera o dia inteiro.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Canal de entrega cujo consentimento é exigido. A audiência existe para ser
#: alcançada, e hoje o alcance é a onda de WhatsApp (``handlers.campaign._send_to``).
#: Consentir WhatsApp não é consentir SMS: quando outro canal de entrega entrar,
#: ele passa a exigir o consentimento do próprio canal, não deste.
DELIVERY_CONSENT_CHANNEL = "whatsapp"

#: RFM + tier que valem tratamento VIP (mesma régua do ``CustomerInsight.is_vip``).
VIP_RFM_SEGMENTS = ("champion", "loyal_customer")
VIP_LOYALTY_TIERS = ("gold", "platinum")

#: Como as regras se combinam. ``any`` = união (somar regra ALARGA o alcance);
#: ``all`` = interseção (somar regra ESTREITA).
#:
#: A união era o único comportamento, e ela não consegue dizer "leais QUE são atacado":
#: pedir as duas coisas devolvia a soma das duas, 5 pessoas em vez de 2. Recorte é
#: exatamente o que faz uma campanha valer a pena, então faltava o essencial.
#:
#: É um interruptor, não uma árvore booleana: continua sem AND/OR aninhado e sem
#: construtor de expressão (ADR-020 §7). Quem precisar de árvore está construindo um CDP,
#: e a resposta continua sendo não.
MATCH_ANY = "any"
MATCH_ALL = "all"
MATCH_MODES = (MATCH_ANY, MATCH_ALL)


@dataclass(frozen=True)
class Recipient:
    """Um destinatário resolvido. ``phone`` é a identidade (e a chave de dedupe)."""

    phone: str
    customer_ref: str = ""
    #: UUID do cliente, quando conhecido. É o que o `AccessLink` exige para cunhar um link
    #: pessoal (`customer_id`), e vem de graça: quem resolve o destinatário já carregou o
    #: `Customer`. Vazio para assinante ANÔNIMO de alerta (só telefone) — e esse é o caso
    #: que legitimamente recebe link sem identidade, porque não há identidade a pôr nele.
    customer_uuid: str = ""
    #: Primeiro nome, para o template poder cumprimentar. Vazio quando o
    #: destinatário veio de assinatura anônima (só telefone) — é por isso que o
    #: template de alerta NÃO tem variável de nome: a Meta exige toda variável
    #: preenchida, e "Olá, !" seria pior do que não cumprimentar.
    first_name: str = ""
    reasons: frozenset = frozenset()  # favorites | alerts | bought
    is_vip: bool = False
    #: Hora habitual de compra (0-23), de ``CustomerInsight.preferred_hour``.
    #: ``None`` para quem ainda não tem padrão — esse recebe na hora.
    preferred_hour: int | None = None


@dataclass(frozen=True)
class Wave:
    """Uma leva de envio: quem recebe, e daqui a quantos minutos.

    ``key`` é o identificador estável que viaja na Directive. O handler de
    despacho volta com ele em ``select_wave`` para reconstruir a lista, porque
    entre a criação do post e o envio a audiência muda.
    """

    key: str
    recipients: tuple[Recipient, ...] = ()
    delay_minutes: int = 0


@dataclass(frozen=True)
class AudienceResult:
    """Audiência resolvida, já dividida em ondas."""

    general: tuple[Recipient, ...] = ()
    vip: tuple[Recipient, ...] = ()
    vip_delay_minutes: int = 0
    preferred_hour_window_hours: int = 0
    counts: dict = field(default_factory=dict)
    #: Como as regras foram combinadas (``any`` união, ``all`` interseção). Viaja no
    #: resumo porque um "2 destinatários" sem isto é indecifrável depois: o gestor não
    #: tem como saber se a lista era pequena ou se ele mesmo a estreitou.
    match: str = MATCH_ANY

    @property
    def total(self) -> int:
        return len(self.general) + len(self.vip)

    def all_recipients(self) -> tuple[Recipient, ...]:
        return tuple(self.vip) + tuple(self.general)

    def waves(self, *, now=None) -> tuple[Wave, ...]:
        """Planejar as levas de envio. Determinístico para um dado ``now``.

        Duas dimensões se combinam: o grupo (VIP abre, geral espera
        ``vip_delay_minutes``) e a hora habitual de cada pessoa. Quem não tem
        hora habitual utilizável fica na leva-base do seu grupo; quem tem sai
        numa leva própria daquela hora.

        A **estrutura** das ondas vem da config; a **participação**, da
        resolução no envio. Por isso a onda-base de cada grupo sai sempre,
        mesmo vazia agora: entre este planejamento e o disparo a fila do "me
        avise" cresce, e um VIP que só se qualifica depois ainda encontra a
        onda VIP esperando por ele. Colapsar o split porque a lista está vazia
        neste instante jogaria fora justamente o privilégio que a regra pede.

        Só as ondas de hora habitual dependem de gente existir, porque elas
        nascem das pessoas que já estão na lista.
        """
        now = now or timezone.localtime()
        groups = (
            [("vip", self.vip, 0), ("general", self.general, self.vip_delay_minutes)]
            if self.vip_delay_minutes > 0
            else [("all", self.all_recipients(), 0)]
        )

        waves: list[Wave] = []
        for name, recipients, base_delay in groups:
            # A chave None (onda-base) existe sempre; as de hora, só com gente.
            buckets: dict[int | None, list[Recipient]] = {None: []}
            for recipient in recipients:
                deferral = _defer_minutes(
                    recipient.preferred_hour,
                    now=now,
                    window_hours=self.preferred_hour_window_hours,
                )
                # A hora habitual só adia; nunca antecipa o que o grupo já deve.
                key = recipient.preferred_hour if deferral > base_delay else None
                buckets.setdefault(key, []).append(recipient)

            for hour, members in sorted(buckets.items(), key=lambda kv: (kv[0] is not None, kv[0])):
                if hour is None:
                    waves.append(Wave(key=name, recipients=tuple(members), delay_minutes=base_delay))
                    continue
                if not members:
                    continue
                delay = _defer_minutes(
                    hour, now=now, window_hours=self.preferred_hour_window_hours
                )
                waves.append(
                    Wave(key=f"{name}@{hour}", recipients=tuple(members), delay_minutes=delay)
                )
        return tuple(waves)

    def summary(self) -> dict:
        """Resumo persistível em ``Announcement.audience`` (só números, sem PII).

        ⚠️ As contagens por regra são de ANTES da combinação: elas dizem quanta gente
        cada regra achou por si. Com ``match="all"``, o ``total`` é menor que qualquer
        uma delas, e é assim que se lê o recorte — "leais 5, atacado 2, total 2" conta a
        história inteira num relance.
        """
        return {
            **self.counts,
            "match": self.match,
            "vip_count": len(self.vip),
            "general_count": len(self.general),
            "vip_delay_minutes": self.vip_delay_minutes,
            "wave_count": len(self.waves()),
            "total": self.total,
        }


def resolve(rules: dict | None = None, *, sku: str = "") -> AudienceResult:
    """Resolver a audiência segundo as regras da Campaign.

    ``sku`` é OPCIONAL porque campanha manual não tem evento nem SKU: o gestor decide
    agora e escolhe para quem. As regras que dependem do evento (``favorites``,
    ``alerts``, ``bought_within_days`` sem SKU escolhido) simplesmente não resolvem
    ninguém sem ele, e isso é resposta normal — não erro.

    Args:
        rules: ``Campaign.audience_rules``. Vocabulário FECHADO e PLANO:

            Por evento (exigem ``sku``): ``favorites`` (bool), ``alerts`` (bool),
            ``bought_within_days`` (int).

            Escolhidos pelo gestor: ``customer_refs``, ``price_tiers``, ``tags``,
            ``rfm_segments``,
            ``churn_risk_min``, ``bought_skus``/``bought_collections`` (com
            ``bought_within_days``), ``birthday_today``.

            Combinação: ``match`` — ``any`` (união, padrão) ou ``all`` (interseção).

            Entrega: ``vip_first_minutes``, ``preferred_hour_window_hours``.
        sku: SKU do evento, quando houver.

    Returns:
        ``AudienceResult`` vazio quando nenhuma regra está ligada ou ninguém passa no
        consentimento. Audiência vazia é resposta normal, não erro.
    """
    rules = rules or {}
    by_phone: dict[str, Recipient] = {}
    counts: dict[str, int] = {}
    #: Os motivos que REALMENTE rodaram. É por eles que a interseção se define, não pelas
    #: chaves pedidas: regra ligada que não pôde rodar (``favorites`` sem SKU) não vira
    #: exigência, senão o disparo manual de uma campanha de evento zeraria calado.
    applied: list[str] = []

    def apply(found: list, *, reason: str, count_key: str) -> None:
        counts[count_key] = len(found)
        applied.append(reason)
        _merge(by_phone, found, reason=reason)

    if sku and rules.get("favorites"):
        apply(_favorites(sku), reason="favorites", count_key="favorites_count")

    if sku and rules.get("alerts"):
        apply(_pending_alerts(sku), reason="alerts", count_key="alerts_count")
        # Fica ao lado do ``alerts_count`` sempre que a regra roda, porque é o
        # que faz o ZERO dizer o que é. "Ninguém para avisar" tem duas causas
        # que a tela mostrava igual: ninguém pediu, ou pediram e a fila já foi
        # servida (assinatura consumida por uma chegada de estoque, por
        # exemplo). Sem este número o gestor precisa do banco para entender.
        counts["alerts_notified_count"] = _notified_alerts_count(sku)

    days = int(rules.get("bought_within_days") or 0)
    if sku and days > 0:
        apply(_bought_within_days(sku, days), reason="bought", count_key="bought_count")

    # ── Públicos escolhidos pelo gestor ──────────────────────────────
    if rules.get("customer_refs"):
        apply(
            _chosen_customers(rules.get("customer_refs")),
            reason="chosen", count_key="chosen_count",
        )

    if rules.get("price_tiers"):
        apply(
            _by_price_tiers(rules.get("price_tiers")),
            reason="price_tiers", count_key="price_tiers_count",
        )

    if rules.get("tags"):
        apply(_by_tags(rules.get("tags")), reason="tags", count_key="tags_count")

    if rules.get("rfm_segments"):
        apply(_by_rfm_segments(rules.get("rfm_segments")), reason="rfm", count_key="rfm_count")

    if rules.get("churn_risk_min"):
        apply(
            _by_churn_risk(rules.get("churn_risk_min")),
            reason="churn_risk", count_key="churn_risk_count",
        )

    chosen_skus = rules.get("bought_skus") or []
    chosen_collections = rules.get("bought_collections") or []
    if (chosen_skus or chosen_collections) and days > 0:
        # ⚠️ Motivo PRÓPRIO, distinto do ``bought`` do evento. Compartilhar o motivo
        # faria a interseção aceitar "comprou o SKU da fornada" como se fosse "comprou o
        # SKU que o gestor escolheu" — duas perguntas satisfeitas por uma resposta.
        apply(
            _bought(skus=chosen_skus, collections=chosen_collections, days=days),
            reason="bought_chosen", count_key="bought_chosen_count",
        )

    if rules.get("birthday_today"):
        apply(_birthday_today(), reason="birthday", count_key="birthday_count")

    mode = _match_mode(rules)
    if mode == MATCH_ALL:
        by_phone = _narrow_to_all(by_phone, applied)

    recipients = _filter_opted_in(by_phone.values())
    window = max(int(rules.get("preferred_hour_window_hours") or 0), 0)

    vip_delay = int(rules.get("vip_first_minutes") or 0)
    if vip_delay <= 0:
        return AudienceResult(
            general=tuple(recipients),
            preferred_hour_window_hours=window,
            counts=counts,
            match=mode,
        )

    vips = tuple(r for r in recipients if r.is_vip)
    general = tuple(r for r in recipients if not r.is_vip)
    return AudienceResult(
        general=general,
        vip=vips,
        vip_delay_minutes=vip_delay,
        preferred_hour_window_hours=window,
        counts=counts,
        match=mode,
    )


def _match_mode(rules: dict) -> str:
    """Modo de combinação, com o padrão de sempre quando a chave não está lá.

    Valor desconhecido cai na UNIÃO e registra o aviso: alargar demais é visível na
    contagem antes de enviar; estreitar por engano viraria "0 destinatários", que o
    gestor leria como "não tem ninguém" em vez de "escrevi errado".
    """
    mode = str(rules.get("match") or MATCH_ANY).strip().lower()
    if mode not in MATCH_MODES:
        logger.warning("audience.match_mode_unknown value=%r", rules.get("match"))
        return MATCH_ANY
    return mode


def _narrow_to_all(by_phone: dict[str, Recipient], applied: list[str]) -> dict[str, Recipient]:
    """Interseção: manter só quem satisfaz TODAS as regras que rodaram.

    Uma regra só (ou nenhuma) torna a interseção idêntica à união, e devolver o mesmo
    dicionário evita fingir que houve recorte.
    """
    required = set(applied)
    if len(required) <= 1:
        return by_phone
    return {phone: r for phone, r in by_phone.items() if required <= r.reasons}


def select_wave(rules: dict | None, wave_key: str, *, sku: str = "", now=None) -> tuple[Recipient, ...]:
    """Os destinatários de uma onda, resolvidos agora.

    Contrato de despacho: a Directive carrega só ``wave_key``, e quem envia
    volta aqui. Onda que sumiu (ninguém mais se encaixa) devolve tupla vazia,
    que é resposta normal, não erro.
    """
    result = resolve(rules, sku=sku)
    for wave in result.waves(now=now):
        if wave.key == wave_key:
            return wave.recipients
    return ()


def _defer_minutes(preferred_hour, *, now, window_hours: int) -> int:
    """Minutos até a hora habitual do cliente, ou 0 para enviar já.

    Adia só para frente e só dentro da janela: hora que já passou hoje não
    empurra a mensagem para amanhã (a novidade teria envelhecido), e hora
    distante demais também não. Fora desses limites, enviar agora é melhor
    que enviar tarde.
    """
    if preferred_hour is None or window_hours <= 0:
        return 0
    try:
        hour = int(preferred_hour)
    except (TypeError, ValueError):
        return 0
    if not 0 <= hour <= 23:
        return 0

    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    minutes = int((target - now).total_seconds() // 60)
    if minutes <= 0 or minutes > window_hours * 60:
        return 0
    return minutes


# ── Regras de audiência ──────────────────────────────────────────────


def _favorites(sku: str) -> list[Recipient]:
    """F8 — quem marcou este produto como favorito."""
    try:
        from shopman.shop.adapters import audience_sources

        refs = audience_sources.favorite_customer_refs(sku)
    except Exception:
        logger.warning("audience.favorites_failed sku=%s", sku, exc_info=True)
        return []
    return _recipients_for_refs(refs)


def _pending_alerts(sku: str) -> list[Recipient]:
    """F9 — quem pediu explicitamente para ser avisado sobre este SKU.

    A assinatura já é opt-in daquele produto, então dispensa o opt-in geral
    de marketing (``_filter_opted_in`` respeita isso). Anônimo entra só com
    telefone, sem ``customer_ref``.
    """
    try:
        from shopman.shop.adapters import audience_sources

        rows = audience_sources.pending_alert_contacts(sku)
    except Exception:
        logger.warning("audience.alerts_failed sku=%s", sku, exc_info=True)
        return []

    out = []
    for phone, customer_ref in rows:
        phone = (phone or "").strip()
        if not phone:
            continue
        customer_ref = (customer_ref or "").strip()
        is_vip, preferred_hour = _profile(customer_ref)
        out.append(
            Recipient(
                phone=phone,
                customer_ref=customer_ref,
                is_vip=is_vip,
                preferred_hour=preferred_hour,
            )
        )
    return out


def _notified_alerts_count(sku: str) -> int:
    """Quantos assinantes deste SKU já foram avisados — o contexto do zero.

    Falha para 0: número que não veio não se inventa, e 0 aqui só apaga a
    explicação extra, nunca inventa audiência.
    """
    try:
        from shopman.shop.adapters import audience_sources

        return max(int(audience_sources.notified_alert_count(sku)), 0)
    except Exception:
        logger.warning("audience.alerts_notified_failed sku=%s", sku, exc_info=True)
        return 0


def _bought_within_days(sku: str, days: int) -> list[Recipient]:
    """F10 — quem comprou este SKU dentro da janela de ``days``.

    Lê ``CustomerInsight.favorite_products`` (já agregado pelo Guestman) em vez
    de varrer o histórico de pedidos: o insight é o índice desse cruzamento.
    """
    try:
        from shopman.guestman.contrib.insights.models import CustomerInsight

        insights = list(
            CustomerInsight.objects.filter(favorite_products__isnull=False)
            .select_related("customer")
        )
    except Exception:
        logger.warning("audience.bought_lookup_failed sku=%s", sku, exc_info=True)
        return []

    cutoff = timezone.localdate() - timedelta(days=days)
    out = []
    for insight in insights:
        if not _bought_recently(insight, sku=sku, cutoff=cutoff):
            continue
        customer = insight.customer
        phone = (getattr(customer, "phone", "") or "").strip()
        if not phone:
            continue
        out.append(
            Recipient(
                phone=phone,
                customer_ref=getattr(customer, "ref", "") or "",
                customer_uuid=str(getattr(customer, "uuid", "") or ""),
                first_name=(getattr(customer, "first_name", "") or "").strip(),
                is_vip=bool(getattr(insight, "is_vip", False)),
                preferred_hour=getattr(insight, "preferred_hour", None),
            )
        )
    return out


# ── Públicos escolhidos pelo gestor (disparo manual) ─────────────────
#
# Estes resolvedores são IRMÃOS dos de evento acima: devolvem `Recipient`, passam pelo
# mesmo `_merge` e pelo mesmo filtro de consentimento. Nenhum model novo — o
# `CustomerInsight` já é o motor de segmentação, e construir um segundo seria criar o
# terceiro dono de um fato que já tem dois.
#
# `audience_rules` é vocabulário FECHADO e PLANO: sem AND/OR aninhado, sem construtor
# de segmento arbitrário. No dia em que alguém precisar de árvore booleana, o que está
# sendo construído é um CDP, e a resposta é não.


def _chosen_customers(refs) -> list[Recipient]:
    """"Estes clientes" — o gestor escolheu um por um na tela."""
    cleaned = [str(r).strip() for r in (refs or []) if str(r).strip()]
    return _recipients_for_refs(cleaned)


def _by_price_tiers(tier_refs) -> list[Recipient]:
    """"Só o atacado" — por ``PriceTier.ref``."""
    cleaned = [str(r).strip() for r in (tier_refs or []) if str(r).strip()]
    if not cleaned:
        return []
    try:
        from shopman.guestman.models import Customer

        refs = list(
            Customer.objects.filter(price_tier__ref__in=cleaned, is_active=True)
            .exclude(phone="")
            .values_list("ref", flat=True)
        )
    except Exception:
        logger.warning("audience.price_tiers_failed", exc_info=True)
        return []
    return _recipients_for_refs(refs)


def _by_tags(tag_slugs) -> list[Recipient]:
    """"Os corredores" — por ``CustomerTag.slug``.

    A etiqueta é o único público que o operador cria SOZINHO, sem esperar cálculo nem
    deploy: RFM e churn são derivados, faixa de preço é comercial, aniversário é dado
    cadastral. Etiqueta é o que ele sabe da pessoa e o sistema não tem como saber.

    Casa por ``slug`` (que é como a etiqueta viaja na regra) ou por ``name``, porque o
    operador digita "Sem glúten" e o slug é "sem-gluten": exigir o slug faria a regra
    salvar limpa e alcançar ninguém.
    """
    cleaned = [str(t).strip() for t in (tag_slugs or []) if str(t).strip()]
    if not cleaned:
        return []
    try:
        from django.db.models import Q
        from shopman.guestman.models import Customer

        refs = list(
            Customer.objects.filter(
                Q(tags__slug__in=cleaned) | Q(tags__name__in=cleaned), is_active=True
            )
            .exclude(phone="")
            .values_list("ref", flat=True)
            .distinct()
        )
    except Exception:
        logger.warning("audience.tags_failed", exc_info=True)
        return []
    return _recipients_for_refs(refs)


def _by_rfm_segments(segments) -> list[Recipient]:
    """"Champions e loyal" — por ``CustomerInsight.rfm_segment``."""
    cleaned = [str(s).strip() for s in (segments or []) if str(s).strip()]
    if not cleaned:
        return []
    try:
        from shopman.guestman.contrib.insights.models import CustomerInsight

        refs = list(
            CustomerInsight.objects.filter(rfm_segment__in=cleaned)
            .select_related("customer")
            .values_list("customer__ref", flat=True)
        )
    except Exception:
        logger.warning("audience.rfm_failed", exc_info=True)
        return []
    return _recipients_for_refs([r for r in refs if r])


def _by_churn_risk(minimum) -> list[Recipient]:
    """Win-back: quem está com risco de evasão acima do piso (0..1)."""
    try:
        floor = Decimal(str(minimum))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("audience.churn_risk_invalid value=%r", minimum)
        return []
    if floor <= 0:
        return []
    try:
        from shopman.guestman.contrib.insights.models import CustomerInsight

        refs = list(
            CustomerInsight.objects.filter(churn_risk__gte=floor)
            .select_related("customer")
            .values_list("customer__ref", flat=True)
        )
    except Exception:
        logger.warning("audience.churn_risk_failed", exc_info=True)
        return []
    return _recipients_for_refs([r for r in refs if r])


def _birthday_today() -> list[Recipient]:
    """Aniversariantes de hoje — espelha ``Promotion.birthday_only``.

    Compara dia e mês, nunca o ano: 29 de fevereiro em ano comum simplesmente não cai
    hoje, e é isso que se espera.
    """
    today = timezone.localdate()
    try:
        from shopman.guestman.models import Customer

        refs = list(
            Customer.objects.filter(
                birthday__month=today.month, birthday__day=today.day, is_active=True
            )
            .exclude(phone="")
            .values_list("ref", flat=True)
        )
    except Exception:
        logger.warning("audience.birthday_failed", exc_info=True)
        return []
    return _recipients_for_refs(refs)


def _bought(*, skus, collections, days: int) -> list[Recipient]:
    """"Interesse genuíno de consumo específico": quem comprou X na janela.

    Generaliza o ``_bought_within_days`` do disparo por evento, que estava preso ao SKU
    do evento. Aqui o gestor escolhe os SKUs, ou coleções — que resolvem para SKUs pelo
    offerman, porque coleção inteligente é regra e não lista.
    """
    wanted = {str(s).strip() for s in (skus or []) if str(s).strip()}
    coll_refs = [str(c).strip() for c in (collections or []) if str(c).strip()]
    if coll_refs:
        try:
            from shopman.offerman.models import Collection

            for coll in Collection.objects.filter(ref__in=coll_refs):
                wanted.update(coll.product_queryset().values_list("sku", flat=True))
        except Exception:
            logger.warning("audience.bought_collections_failed", exc_info=True)
    if not wanted:
        return []

    seen: dict[str, Recipient] = {}
    for sku in sorted(wanted):
        for recipient in _bought_within_days(sku, days):
            seen.setdefault(recipient.phone, recipient)
    return list(seen.values())


def _bought_recently(insight, *, sku: str, cutoff) -> bool:
    """A entrada do insight é recente o bastante para entrar na janela?

    ⚠️ Aqui vivia um defeito de produção. Esta função lia ``ultimo_pedido``, uma
    chave que **nenhum escritor grava**: o Guestman monta a entrada com
    ``last_order_at`` (ver ``insights/service.py::_calculate_favorite_products``).
    O ``.get()`` devolvia ``None`` sempre, e o fallback tratava ``None`` como
    "conta" — então a janela **nunca filtrou ninguém**. Uma campanha configurada
    para "quem comprou nos últimos 7 dias" alcançava todo mundo que já comprou
    algum dia, com custo por mensagem de WhatsApp e desgaste de audiência.

    O teste não pegava porque fabricava ``ultimo_pedido`` à mão — espelhava a
    suposição do LEITOR em vez da saída do ESCRITOR. Mesma família do
    ``broadcast_optin`` sem escritor que a F1 consertou: chave sem dono.

    E o fallback mudou de sinal. Entrada sem data agora fica **fora** da janela:
    o sentido de "comprou nos últimos N dias" é uma janela, e contar o que não
    tem data como dentro dela desmancha justamente o que o operador pediu. O
    escritor sempre grava a data, então isto só alcança lixo.
    """
    for entry in insight.favorite_products or []:
        if not isinstance(entry, dict) or entry.get("sku") != sku:
            continue
        last = _as_date(entry.get("last_order_at"))
        return last is not None and last >= cutoff
    return False


# ── Opt-in ───────────────────────────────────────────────────────────


def _filter_opted_in(recipients, *, channel: str = DELIVERY_CONSENT_CHANNEL) -> list[Recipient]:
    """Manter só quem consentiu — no canal de entrega ou por assinatura de SKU."""
    recipients = list(recipients)
    refs = {r.customer_ref for r in recipients if r.customer_ref}
    opted_in = _opted_in_refs(refs, channel=channel)

    kept = []
    for recipient in recipients:
        if "alerts" in recipient.reasons:
            kept.append(recipient)  # a assinatura por SKU é o próprio consentimento
            continue
        if recipient.customer_ref and recipient.customer_ref in opted_in:
            kept.append(recipient)
    return kept


def _opted_in_refs(customer_refs: set[str], *, channel: str) -> set[str]:
    """Refs com consentimento ativo no canal. Ausência e revogação valem opt-out.

    Uma consulta, pela API pública do guestman. Falha de leitura devolve conjunto
    vazio de propósito: na dúvida ninguém recebe, porque o erro seguro aqui é não
    enviar.
    """
    if not customer_refs:
        return set()
    try:
        from shopman.guestman import ConsentService

        marketable = set(ConsentService.get_marketable_customers(channel))
    except Exception:
        logger.warning("audience.consent_lookup_failed channel=%s", channel, exc_info=True)
        return set()

    return {ref for ref in customer_refs if ref in marketable}


# ── Helpers ──────────────────────────────────────────────────────────


def _recipients_for_refs(customer_refs: list[str]) -> list[Recipient]:
    refs = [ref for ref in customer_refs if ref]
    if not refs:
        return []
    try:
        from shopman.guestman.models import Customer

        customers = list(
            Customer.objects.filter(ref__in=refs, is_active=True)
            .exclude(phone="")
            .select_related("insight")
        )
    except Exception:
        logger.warning("audience.customer_lookup_failed", exc_info=True)
        return []

    out = []
    for customer in customers:
        is_vip, preferred_hour = _profile(customer.ref, customer=customer)
        out.append(
            Recipient(
                phone=customer.phone,
                customer_ref=customer.ref,
                customer_uuid=str(getattr(customer, "uuid", "") or ""),
                first_name=(getattr(customer, "first_name", "") or "").strip(),
                is_vip=is_vip,
                preferred_hour=preferred_hour,
            )
        )
    return out


def _profile(customer_ref: str, *, customer=None) -> tuple[bool, int | None]:
    """``(is_vip, preferred_hour)`` de um cliente, numa passada só.

    As duas respostas saem do mesmo ``CustomerInsight``, então lê-las juntas
    evita repetir a consulta para cada destinatário.
    """
    if not customer_ref:
        return False, None
    try:
        if customer is None:
            from shopman.guestman.models import Customer

            customer = Customer.objects.filter(ref=customer_ref).first()
        if customer is None:
            return False, None

        insight = getattr(customer, "insight", None)
        preferred_hour = getattr(insight, "preferred_hour", None) if insight else None

        if insight is not None and insight.rfm_segment in VIP_RFM_SEGMENTS:
            return True, preferred_hour

        from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

        tier = (
            LoyaltyAccount.objects.filter(customer=customer)
            .values_list("tier", flat=True)
            .first()
        )
        return tier in VIP_LOYALTY_TIERS, preferred_hour
    except Exception:
        logger.debug("audience.profile_failed ref=%s", customer_ref, exc_info=True)
        return False, None


def _merge(by_phone: dict, found: list, *, reason: str) -> None:
    """Somar destinatários deduplicando por telefone e acumulando os motivos."""
    for recipient in found:
        existing = by_phone.get(recipient.phone)
        if existing is None:
            by_phone[recipient.phone] = Recipient(
                phone=recipient.phone,
                customer_ref=recipient.customer_ref,
                customer_uuid=recipient.customer_uuid,
                first_name=recipient.first_name,
                reasons=frozenset({reason}),
                is_vip=recipient.is_vip,
                preferred_hour=recipient.preferred_hour,
            )
            continue
        by_phone[recipient.phone] = Recipient(
            phone=existing.phone,
            # Um match anônimo (só telefone) não apaga o vínculo já conhecido.
            customer_ref=existing.customer_ref or recipient.customer_ref,
            customer_uuid=existing.customer_uuid or recipient.customer_uuid,
            first_name=existing.first_name or recipient.first_name,
            reasons=existing.reasons | {reason},
            is_vip=existing.is_vip or recipient.is_vip,
            # Idem para a hora habitual: a primeira conhecida vale.
            preferred_hour=(
                existing.preferred_hour
                if existing.preferred_hour is not None
                else recipient.preferred_hour
            ),
        )


def _as_date(value):
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        return None
