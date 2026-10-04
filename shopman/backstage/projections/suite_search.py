"""Busca da suíte: um campo, uma tecla, o alcance "toda a suíte" (SUITE-UX-V2 §2.2, FUNCTION §7).

O operador digita no campo do cabeçalho de qualquer app (ou na barra grande da Central) e a
busca devolve, AGRUPADO POR TIPO, o que ele pode abrir: pedidos, encomendas, clientes,
produtos, insumos, fornecedores, lotes, receitas, campanhas e telas. Cada resultado traz o
app de destino e o link profundo para o lugar exato (o pedido no Gestor, a encomenda no PDV,
o insumo na Base do Compras), montado a partir de ``settings.SHOPMAN_SURFACE_URLS`` pela
mesma régua da Central (``projections/hub.py``): app que o operador não abre, ou sem URL
configurada, não gera resultado — nunca link para porta fechada ou morta.

**Permissão é por tipo, com a pergunta da própria tela de destino**: o cliente só aparece para
quem abre Clientes no Gestor (``shop.manage_customers``), o produto para quem abre o Catálogo
(``shop.manage_catalog``), a receita para quem lê o caderno (``resolve_recipe_book_access``), a
tela de Caixa do B.I. para quem audita caixa. Nenhum dado pessoal além do que a tela de destino
já mostra a essa mesma pessoa (o telefone do cliente sai como a lista de Clientes o escreve).

**Nada aqui é busca nova onde já existe uma**: clientes leem ``build_customer_list`` (a busca do
Gestor, com dígitos de telefone e CPF), encomendas leem ``build_preorder_search`` (o "cliente
veio buscar" do PDV). O resto são consultas curtas por nome/ref, com teto por tipo.

O filtro "esta tela" continua sendo de cada tela (no cliente); "App" é este mesmo resultado
recortado pelo app atual (``app`` de cada resultado).

Nunca importa de ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote, urlencode

from django.db.models import Q
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.backstage.permissions import can_audit_cash, is_superuser
from shopman.backstage.projections.hub import accessible_surfaces

logger = logging.getLogger(__name__)

#: Menos que isto não é busca, é ruído (uma letra acha o catálogo inteiro).
MIN_QUERY_LENGTH = 2
#: Mais que isto é texto colado por engano; a API recusa com o campo nomeado.
MAX_QUERY_LENGTH = 80
#: Teto por tipo: a busca leva ao lugar certo, não substitui a lista do app.
PER_TYPE_LIMIT = 5
#: Pedidos olham para trás só até aqui (o Histórico do Gestor cobre o resto, com filtros).
ORDER_WINDOW_DAYS = 120


@dataclass(frozen=True)
class SuiteSearchResultProjection:
    key: str
    type: str
    #: O app de destino (``pos``, ``gestor``…), o recorte do alcance "App".
    app: str
    app_label: str
    #: "Gestor › Clientes": onde o resultado abre, escrito antes do detalhe.
    place: str
    title: str
    detail: str
    url: str
    icon: str


@dataclass(frozen=True)
class SuiteSearchGroupProjection:
    type: str
    label: str
    results: tuple[SuiteSearchResultProjection, ...]


@dataclass(frozen=True)
class SuiteSearchAppCountProjection:
    ref: str
    label: str
    count: int


@dataclass(frozen=True)
class SuiteSearchProjection:
    query: str
    #: ``False`` quando o termo é curto demais para buscar (a tela diz "digite mais").
    searched: bool
    total: int
    groups: tuple[SuiteSearchGroupProjection, ...]
    #: Quantos resultados cada app tem (o número ao lado do alcance "App").
    apps: tuple[SuiteSearchAppCountProjection, ...]


# ── Telas ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Screen:
    app: str
    label: str
    path: str
    icon: str
    keywords: str = ""
    allowed: Callable[[object], bool] | None = None


#: As telas de cada app que a busca alcança pelo nome ("caixa", "clientes", "receitas").
#: Os nomes são os do rail de cada app (``use*Sections.ts``/``*Nav.vue``).
SCREENS: tuple[_Screen, ...] = (
    _Screen("pos", "Venda", "/", "shopping-basket", "comanda balcao pdv"),
    _Screen("pos", "Encomendas", "/preorders", "calendar-clock", "retirada entrega agendado"),
    _Screen("pos", "Caixa", "/session", "wallet", "turno abrir fechar sangria suprimento"),
    _Screen("pos", "Salão", "/settings/seating", "armchair", "mesas planta"),
    _Screen("kds", "Preparo", "/", "chef-hat", "cozinha ticket estacao"),
    _Screen("kds", "Painel de retirada", "/pickup", "monitor", "tela do cliente chamada"),
    _Screen("gestor", "Pedidos", "/", "clipboard-list", "fila"),
    _Screen("gestor", "Catálogo", "/catalog", "book-open", "produtos precos colecoes"),
    _Screen("gestor", "Clientes", "/customers", "users", "cadastro"),
    _Screen("gestor", "Histórico", "/history", "history", "concluidos cancelados devolvidos"),
    _Screen("gestor", "Canais", "/feeds", "radio-tower", "ifood feed loja"),
    _Screen("gestor", "Postos", "/workstations", "monitor-smartphone", "dispositivos estacao"),
    _Screen("gestor", "Ajustes", "/settings", "settings-2", "configuracao"),
    _Screen("production", "Produção do dia", "/", "croissant", "lotes"),
    _Screen("production", "Planejamento", "/plan", "calendar-range", "plano sugestao amanha"),
    _Screen("production", "Pesagem", "/mise-en-place", "scale", "mise en place insumos"),
    _Screen("production", "Fechamento", "/close", "package-check", "fechar lote"),
    _Screen("production", "Qualidade", "/quality", "badge-check", "ressalva"),
    _Screen("production", "Receitas", "/recipes", "notebook-text", "ficha tecnica formula"),
    _Screen("production", "Relatórios", "/reports", "file-chart-column", "relatorio"),
    _Screen("production", "Timers", "/timers", "timer", "despertador"),
    _Screen("production", "Letreiro", "/board", "tower-control", "painel"),
    _Screen("purchase", "Painel", "/?view=panel", "layout-dashboard", "compras"),
    _Screen("purchase", "Comprar", "/?view=buy", "shopping-cart", "pedido de compra reposicao"),
    _Screen("purchase", "Receber", "/?view=receive", "package-open", "recebimento nota nf conferencia doca"),
    _Screen("purchase", "Base", "/?view=base", "database", "insumos fornecedores custos"),
    _Screen("marketing", "Decisões", "/", "inbox", "fila anuncio revisar"),
    _Screen("marketing", "Agendados", "/scheduled", "calendar-clock", "agenda"),
    _Screen("marketing", "Enviados", "/history", "send", "historico disparos"),
    _Screen("marketing", "Campanhas", "/campaigns", "megaphone", "gatilho"),
    _Screen("marketing", "Modelos", "/templates", "file-text", "modelos de texto"),
    _Screen("marketing", "Plataformas", "/v2?area=platforms", "radio-tower", "instagram facebook whatsapp google"),
    _Screen("bi", "Visão geral", "/", "chart-no-axes-combined", "bi numeros"),
    _Screen("bi", "Vendas", "/sales", "chart-column", "faturamento"),
    _Screen("bi", "Caixa", "/cash", "wallet", "quebra apuracao", can_audit_cash),
    _Screen("bi", "Clientes", "/customers", "users", "fieis recorrencia"),
    _Screen("bi", "Perfis", "/profiles", "id-card", "perfil"),
    _Screen("bi", "Projeção", "/forecast", "trending-up", "previsao"),
    _Screen("bi", "Cenários", "/scenarios", "flask-conical", "simulacao"),
    _Screen("bi", "Explorar", "/explore", "telescope", "explorar"),
)


# ── Montagem ───────────────────────────────────────────────────────────────


GROUPS: tuple[tuple[str, str], ...] = (
    ("orders", "Pedidos"),
    ("preorders", "Encomendas"),
    ("customers", "Clientes"),
    ("products", "Produtos"),
    ("materials", "Insumos"),
    ("suppliers", "Fornecedores"),
    ("work_orders", "Lotes"),
    ("recipes", "Receitas"),
    ("campaigns", "Campanhas"),
    ("screens", "Telas"),
)


def normalize_query(raw) -> str:
    return " ".join(str(raw or "").split())


def build_suite_search(user, raw_query) -> SuiteSearchProjection:
    """O que ``user`` pode abrir que casa com ``raw_query``, agrupado por tipo."""
    query = normalize_query(raw_query)
    if len(query) < MIN_QUERY_LENGTH:
        return SuiteSearchProjection(query=query, searched=False, total=0, groups=(), apps=())

    surfaces = accessible_surfaces(user)
    sources: tuple[tuple[str, str, Callable], ...] = (
        ("orders", "gestor", _orders),
        ("preorders", "pos", _preorders),
        ("customers", "gestor", _customers),
        ("products", "gestor", _products),
        ("materials", "purchase", _materials),
        ("suppliers", "purchase", _suppliers),
        ("work_orders", "production", _work_orders),
        ("recipes", "production", _recipes),
        ("campaigns", "marketing", _campaigns),
    )
    found: dict[str, list[SuiteSearchResultProjection]] = {}
    for kind, app, source in sources:
        if app not in surfaces:
            continue
        label, base = surfaces[app]
        try:
            found[kind] = list(source(user, query, app, label, base))[:PER_TYPE_LIMIT]
        except Exception:
            # Uma fonte que quebra não derruba a busca: as outras respondem.
            logger.warning("suite_search.source_failed kind=%s", kind, exc_info=True)
            found[kind] = []
    found["screens"] = _screens(user, query, surfaces)

    groups = tuple(
        SuiteSearchGroupProjection(type=kind, label=label, results=tuple(found[kind]))
        for kind, label in GROUPS
        if found.get(kind)
    )
    counts: dict[str, int] = {}
    for group in groups:
        for result in group.results:
            counts[result.app] = counts.get(result.app, 0) + 1
    apps = tuple(
        SuiteSearchAppCountProjection(ref=ref, label=surfaces[ref][0], count=counts.get(ref, 0))
        for ref in surfaces
    )
    return SuiteSearchProjection(
        query=query,
        searched=True,
        total=sum(len(group.results) for group in groups),
        groups=groups,
        apps=apps,
    )


# ── Fontes ─────────────────────────────────────────────────────────────────


def _join_url(base: str, path: str, query: dict[str, str] | None = None) -> str:
    url = base.rstrip("/") + "/" + path.lstrip("/")
    return f"{url}?{urlencode(query)}" if query else url


def _has(user, perm: str) -> bool:
    return is_superuser(user) or user.has_perm(perm)


def _money(value_q) -> str:
    # Espaço inquebrável: "R$" nunca fica numa linha e o valor na outra.
    return f"R$\u00a0{format_money(int(value_q or 0))}"


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _orders(user, query, app, app_label, base):
    from shopman.orderman.models import Order

    from shopman.backstage.projections.order_queue import _format_customer_display, items_summary
    from shopman.shop.services import operator_orders, order_composition

    since = timezone.now() - timedelta(days=ORDER_WINDOW_DAYS)
    orders = (
        Order.objects.filter(created_at__gte=since)
        .filter(
            Q(ref__icontains=query)
            | Q(external_ref__icontains=query)
            | Q(data__customer__name__icontains=query)
        )
        .order_by("-created_at")
        .prefetch_related("items")[:PER_TYPE_LIMIT]
    )
    for order in orders:
        customer = _format_customer_display(((order.data or {}).get("customer") or {}).get("name", ""))
        short = operator_orders.short_ref(order.ref)
        summary = items_summary(order_composition.effective_items(order))
        detail = " · ".join(
            part
            for part in (
                order.get_status_display().capitalize(),
                summary,
                _money(order_composition.effective_total_q(order)),
            )
            if part
        )
        yield SuiteSearchResultProjection(
            key=f"order:{order.ref}",
            type="orders",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Pedidos",
            title=f"{short} · {customer}" if customer else f"Pedido {short}",
            detail=detail,
            url=_join_url(base, quote(order.ref, safe="")),
            icon="clipboard-list",
        )


def _preorders(user, query, app, app_label, base):
    from shopman.backstage.projections.preorders import build_preorder_search

    for card in build_preorder_search(query).open[:PER_TYPE_LIMIT]:
        when = " ".join(part for part in (card.commitment_date_display, card.window_start and f"às {card.window_start}") if part)
        detail = " · ".join(part for part in (f"{card.fulfillment_label} {when}".strip(), card.total_display) if part)
        yield SuiteSearchResultProjection(
            key=f"preorder:{card.ref}",
            type="preorders",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Encomendas",
            title=f"Encomenda de {card.customer_name}" if card.customer_name else f"Encomenda {card.ref}",
            detail=detail,
            url=_join_url(base, f"preorders/{quote(card.ref, safe='')}"),
            icon="calendar-clock",
        )


def _customers(user, query, app, app_label, base):
    if not _has(user, "shop.manage_customers"):
        return
    from shopman.backstage.projections.customers import build_customer_list

    for row in build_customer_list(query).items[:PER_TYPE_LIMIT]:
        yield SuiteSearchResultProjection(
            key=f"customer:{row.ref}",
            type="customers",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Clientes",
            title=row.name,
            detail=" · ".join(part for part in (row.orders_label, row.phone_display) if part),
            url=_join_url(base, f"customers/{quote(row.ref, safe='')}"),
            icon="user",
        )


def _products(user, query, app, app_label, base):
    if not _has(user, "shop.manage_catalog"):
        return
    from shopman.offerman.models import Product

    products = Product.objects.filter(Q(name__icontains=query) | Q(sku__icontains=query)).order_by("name")
    for product in products[:PER_TYPE_LIMIT]:
        price = _money(product.base_price_q) + (" por kg" if product.unit == "kg" else "")
        yield SuiteSearchResultProjection(
            key=f"product:{product.sku}",
            type="products",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Catálogo",
            title=product.name,
            detail=" · ".join(("produto", product.sku, price)),
            url=_join_url(base, "catalog", {"sku": product.sku}),
            icon="croissant",
        )


def _materials(user, query, app, app_label, base):
    from shopman.buyman.models import Material

    materials = Material.objects.filter(is_active=True).filter(Q(name__icontains=query) | Q(sku__icontains=query))
    for material in materials.order_by("name")[:PER_TYPE_LIMIT]:
        yield SuiteSearchResultProjection(
            key=f"material:{material.sku}",
            type="materials",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Base",
            title=material.name,
            detail=" · ".join(("insumo", material.sku, f"em {material.get_unit_display()}")),
            url=_join_url(base, "/", {"view": "base", "material": material.sku}),
            icon="package",
        )


def _suppliers(user, query, app, app_label, base):
    from shopman.buyman.models import Supplier

    suppliers = Supplier.objects.filter(is_active=True).filter(
        Q(name__icontains=query) | Q(trade_name__icontains=query) | Q(ref__icontains=query)
    )
    for supplier in suppliers.order_by("name")[:PER_TYPE_LIMIT]:
        title = supplier.trade_name or supplier.name
        yield SuiteSearchResultProjection(
            key=f"supplier:{supplier.ref}",
            type="suppliers",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Base",
            title=title,
            detail=" · ".join(part for part in ("fornecedor", supplier.name if supplier.name != title else "") if part),
            url=_join_url(base, "/", {"view": "base", "supplier": supplier.ref}),
            icon="truck",
        )


def _work_orders(user, query, app, app_label, base):
    from shopman.craftsman.models import WorkOrder

    work_orders = (
        WorkOrder.objects.exclude(status=WorkOrder.Status.VOID)
        .filter(Q(ref__icontains=query) | Q(recipe__name__icontains=query) | Q(recipe__output_sku__icontains=query))
        .select_related("recipe")
        .order_by("-target_date", "-created_at")
    )
    # O lote de hoje primeiro, depois o mais perto (amanhã antes do mês que vem; ontem
    # antes da semana passada): quem busca "croissant" quer o da bancada.
    today = timezone.localdate()
    nearest = sorted(
        work_orders[: PER_TYPE_LIMIT * 6],
        key=lambda wo: (abs((wo.target_date - today).days) if wo.target_date else 9999, wo.target_date and wo.target_date < today),
    )
    for wo in nearest[:PER_TYPE_LIMIT]:
        day = wo.target_date.strftime("%d/%m") if wo.target_date else ""
        query_params = {"q": wo.ref}
        if wo.target_date:
            query_params["date"] = wo.target_date.isoformat()
        yield SuiteSearchResultProjection(
            key=f"work_order:{wo.ref}",
            type="work_orders",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Produção do dia",
            title=f"{wo.recipe.name} · {wo.ref}",
            detail=" · ".join(part for part in (wo.get_status_display(), day and f"dia {day}") if part),
            url=_join_url(base, "/", query_params),
            icon="croissant",
        )


def _recipes(user, query, app, app_label, base):
    from shopman.craftsman.models import RecipeEntry

    from shopman.backstage.projections.recipe_book import resolve_recipe_book_access

    if not resolve_recipe_book_access(user).can_view:
        return
    entries = RecipeEntry.objects.filter(is_archived=False).filter(
        Q(name__icontains=query) | Q(ref__icontains=query) | Q(output_sku__icontains=query)
    )
    for entry in entries.order_by("name")[:PER_TYPE_LIMIT]:
        yield SuiteSearchResultProjection(
            key=f"recipe:{entry.ref}",
            type="recipes",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Receitas",
            title=entry.name,
            detail=" · ".join(part for part in ("receita", entry.get_kind_display()) if part),
            url=_join_url(base, f"recipes/{quote(entry.ref, safe='')}"),
            icon="notebook-text",
        )


def _campaigns(user, query, app, app_label, base):
    from shopman.shop.models import Campaign

    for campaign in Campaign.objects.filter(name__icontains=query).order_by("-is_active", "name")[:PER_TYPE_LIMIT]:
        yield SuiteSearchResultProjection(
            key=f"campaign:{campaign.pk}",
            type="campaigns",
            app=app,
            app_label=app_label,
            place=f"{app_label} › Campanhas",
            title=campaign.name,
            detail=" · ".join(("campanha", "ligada" if campaign.is_active else "desligada")),
            url=_join_url(base, "campaigns", {"q": campaign.name}),
            icon="megaphone",
        )


def _screens(user, query, surfaces) -> list[SuiteSearchResultProjection]:
    needle = _fold(query)
    results = []
    for screen in SCREENS:
        if screen.app not in surfaces:
            continue
        if screen.allowed is not None and not screen.allowed(user):
            continue
        app_label, base = surfaces[screen.app]
        haystack = _fold(f"{screen.label} {app_label} {screen.keywords}")
        if needle not in haystack and not all(word in haystack for word in needle.split()):
            continue
        results.append(
            SuiteSearchResultProjection(
                key=f"screen:{screen.app}:{screen.path}",
                type="screens",
                app=screen.app,
                app_label=app_label,
                place="tela",
                title=f"{app_label} › {screen.label}",
                detail="",
                url=_join_url(base, screen.path) if screen.path != "/" else base,
                icon=screen.icon,
            )
        )
    return results[: PER_TYPE_LIMIT * 2]
