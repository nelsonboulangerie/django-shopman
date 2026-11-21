"""Gerente não tem permissão financeira. Ponto. A trava.

Dono, 21/11/2026, literal: "Isso, gerente basicamente NÃO tem permissões
financeiras. Ponto. O que teremos são exceções, extremamente pontuais, com regra
claríssima, que pode/deve ser testada/confrontada/questionada por guardrails ou
algo que o valha. Simples assim."

E sobre o B.I., no mesmo dia: "BI -> Só dono, só dono tem acesso!!! Gerente NÃO
deve ter acesso ao BI. Se for ter, um dia, será por exceção explícita, solicitada
previamente por mim, em pessoa."

Como a trava funciona:

1. :func:`_is_financial` reconhece toda permissão que toca dinheiro: o ``payman``
   inteiro, o ``cashman`` inteiro, o B.I. e os seus de-paras e o fechamento do
   dia. Permissão nova que caia nessas famílias entra na conta sozinha.
2. Cada permissão financeira que o grupo Gerente recebe do ``setup_groups`` tem de
   estar classificada numa de duas listas fechadas:

   - :data:`EXCEPTIONS`: exceção ao "nada financeiro", com a regra e a palavra do
     dono. Exceção nova só entra mudando esta lista, ou seja, revisada;
   - :data:`OPERATION_WITHOUT_AGGREGATE`: operação de balcão que ele precisa para
     trabalhar e que NÃO mostra valor somado (o fechamento cego, a assinatura do
     gerente num gesto). Cada entrada diz por que não soma, e os testes abaixo
     conferem o que é servido a ele.

   Permissão financeira fora das duas listas reprova.
3. O que é só do Dono (o B.I., a apuração do caixa, as cobranças) nunca chega ao
   Gerente, nem por classificação.

E sobre as listas do balcão, no mesmo dia, corrigindo o rumo: "Não tem problema o
gerente ver valores... Não tem problema ver o valor de um pedido no histórico. O
problema seria poder ver valores de vários registros agregados, sobretudo de
clientes diferentes, soma de um período, etc. ... não quero que eles saibam ou
que possam ter um panorama sobre o quanto está sendo faturado pela casa."

4. O valor de CADA registro é dele: o pedido, a encomenda, a conta de UM cliente.
   O que a trava confere, na seção "Nenhum agregado", é a AUSÊNCIA DE AGREGADO
   servido ao Gerente: soma do período nas encomendas, total somado no Histórico,
   a lista de contas ordenada pelo saldo (um ranking), o filtro por faixa de
   valor no Admin, a proporção do faturamento no aviso do B.I. e exportação de
   pedido, venda ou pagamento com valor.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

pytestmark = pytest.mark.django_db

#: Exceções ao "Gerente não tem permissão financeira". Cada uma: permissão →
#: (a regra, a palavra do dono). Hoje nenhuma. A primeira, estornar UM pedido
#: vendo só o valor dele, entra com o gesto que a usa (#2727, item 5).
EXCEPTIONS: dict[str, tuple[str, str]] = {}

#: Operação de balcão sem valor agregado. Não é exceção: é o trabalho dele, e
#: nenhuma destas telas mostra soma, total esperado ou lista de cobranças ao
#: Gerente (levantamento tela a tela de 21/11/2026, no PR que criou esta trava).
OPERATION_WITHOUT_AGGREGATE: dict[str, str] = {
    "backstage.perform_closing": (
        "Fecha o dia às cegas: conta o que sobrou e não vê o esperado "
        "(_blind_closing_data). No Admin, o registro do fechamento chega a ele "
        "sem o resumo do caixa (DayClosingAdmin.get_fields)."
    ),
    "backstage.view_dayclosing": (
        "A lista de fechamentos no Admin: data, quem fechou, itens e discrepâncias, sem valor."
    ),
    "cashman.adjust_shift": (
        "A assinatura do gerente num gesto (sangria, desconto, cancelamento): mostra o valor "
        "daquele gesto e mais nada. Não existe tela de ajuste com o esperado do turno."
    ),
    "cashman.manage_operators": "Operadores, PINs, crachás e postos. Nenhum valor.",
    "cashman.operate_pos": (
        "O PDV: vende, abre e fecha o turno contando às cegas (_cash_shift_result sem "
        "esperado nem diferença). As somas do período das encomendas ficam escondidas "
        "(show_money_sums=can_audit_cash); o relatório X/Z pede audit_shift."
    ),
    "cashman.view_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
    "cashman.add_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
    "cashman.change_terminal": "O cadastro dos terminais: configuração, sem valor de transação.",
}

#: Só do Dono: nem exceção, nem operação. Reprova se chegar ao Gerente ou a uma das listas.
OWNER_ONLY = frozenset({
    "backstage.view_bi",
    "backstage.view_dailysalesfact",
    "backstage.view_historicalsale",
    "backstage.view_historicalsaleitem",
    "backstage.view_biscenarioreport",
    "backstage.view_bialertevent",
    "backstage.view_bialertrule",
    "backstage.add_bialertrule",
    "backstage.change_bialertrule",
    "backstage.view_importbatch",
    "cashman.audit_shift",
    "payman.view_paymentintent",
    "payman.view_paymenttransaction",
    "payman.refund_paymentintent",
})

_BI_MODELS = (
    "bialertrule", "bialertevent", "biscenarioreport", "dailysalesfact", "historicalsale",
    "historicalsaleitem", "importbatch", "categoryalias", "productalias", "paymentmethodalias",
    "aliasbenchmarkreport",
)


def _is_financial(perm: str) -> bool:
    app, _, codename = perm.partition(".")
    if app in {"payman", "cashman"}:
        return True
    if app == "backstage":
        return (
            codename == "view_bi"
            or codename.endswith(_BI_MODELS)
            or "dayclosing" in codename
            or codename == "perform_closing"
        )
    # ``shop.view_reports`` são os relatórios da Produção: quantidade, perda e
    # qualidade, sem valor (conferido em 21/11/2026). Se ganharem dinheiro, entram aqui.
    return False


def _group_perms(name: str) -> set[str]:
    call_command("setup_groups")
    group = Group.objects.prefetch_related("permissions__content_type").get(name=name)
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()}


def _user_in(username: str, *groups: str) -> User:
    call_command("setup_groups")
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def _gerente() -> User:
    return _user_in("gerente-trava", "Gerente")


# ── A classificação ──────────────────────────────────────────────────────────


def test_toda_permissao_financeira_do_gerente_esta_classificada():
    financial = {perm for perm in _group_perms("Gerente") if _is_financial(perm)}
    unclassified = financial - set(EXCEPTIONS) - set(OPERATION_WITHOUT_AGGREGATE)

    assert not unclassified, (
        f"O grupo Gerente recebeu permissão financeira sem classificação: {sorted(unclassified)}. "
        "Gerente não tem permissão financeira (dono, 21/11/2026). Tire a permissão do grupo "
        "no descritor da instância (config/instances/) ou, com a palavra do dono, declare a "
        "exceção em EXCEPTIONS."
    )


def test_o_que_e_so_do_dono_nunca_chega_ao_gerente():
    leaked = _group_perms("Gerente") & OWNER_ONLY
    assert not leaked, f"Só do Dono e concedido ao Gerente: {sorted(leaked)}"
    assert not (OWNER_ONLY & (set(EXCEPTIONS) | set(OPERATION_WITHOUT_AGGREGATE)))


def test_cada_excecao_tem_regra_e_palavra_do_dono():
    for perm, (rule, owner_word) in EXCEPTIONS.items():
        assert _is_financial(perm), f"{perm} não é financeira: não precisa de exceção"
        assert rule.strip() and owner_word.strip(), f"Exceção {perm} sem regra ou sem a palavra do dono"


def test_as_listas_nao_guardam_permissao_que_o_gerente_nao_tem():
    """Lista que guarda o que não existe mais vira lixo e esconde a próxima exceção."""
    granted = _group_perms("Gerente")
    stale = (set(EXCEPTIONS) | set(OPERATION_WITHOUT_AGGREGATE)) - granted
    assert not stale, f"Classificadas e não concedidas ao Gerente (tire da lista): {sorted(stale)}"


def test_o_bi_e_do_dono():
    assert {"backstage.view_bi", "backstage.view_dailysalesfact", "backstage.view_bialertrule"} <= _group_perms("Dono")


# ── O que é servido ao Gerente ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "url_name", ["api-backstage-bi-sales", "api-backstage-bi-cash", "api-backstage-bi-customers"],
)
def test_o_bi_responde_403_ao_gerente(client, url_name):
    client.force_login(_gerente())
    assert client.get(reverse(url_name)).status_code == 403


def test_a_central_nao_oferece_o_bi_ao_gerente():
    from shopman.backstage.permissions import can_view_bi

    assert can_view_bi(_gerente()) is False
    assert can_view_bi(_user_in("dono-bi", "Dono")) is True


def _closing():
    from shopman.backstage.models import DayClosing

    return DayClosing.objects.create(
        date=date(2026, 11, 20),
        closed_by=User.objects.create_user("quem-fechou", password="pw"),
        data={
            "items": [{"sku": "PAO", "qty_reported": 3}],
            "cash_shift_summary": {
                "totals": {"expected_amount_q": 51230, "difference_q": -200},
                "payment_method_totals": [{"method": "pix", "amount_q": 98000}],
            },
        },
    )


def _request_as(user: User):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_o_fechamento_no_admin_chega_ao_gerente_sem_o_resumo_do_caixa():
    """O registro do fechamento guarda o esperado, a quebra e o que entrou por forma
    de pagamento, e o Admin o mostrava a quem tem ``perform_closing``."""
    from shopman.backstage.models import DayClosing

    closing = _closing()
    model_admin = admin.site._registry[DayClosing]

    fields = model_admin.get_fields(_request_as(_gerente()), closing)
    shown = model_admin.operation_data_display(closing)

    assert "data" not in fields
    assert "operation_data_display" in fields
    assert "PAO" in shown
    for money in ("cash_shift_summary", "expected_amount_q", "difference_q", "payment_method_totals", "51230"):
        assert money not in shown


def test_quem_audita_caixa_ve_o_fechamento_inteiro():
    from shopman.backstage.models import DayClosing

    dono = _user_in("dono-trava", "Dono", "Gerente")
    assert "data" in admin.site._registry[DayClosing].get_fields(_request_as(dono), _closing())


# ── Nenhum agregado (as listas do balcão) ────────────────────────────────────
#
# O valor de cada registro é dele (o pedido, a encomenda, a conta de UM cliente).
# O que não chega é a conta sobre vários: soma de período, total da lista, ranking
# de clientes pelo dinheiro, exportação com valor.

#: Chave de payload que carrega uma soma em dinheiro sobre vários registros.
_MONEY_SUM_KEY = re.compile(
    r"^(total|sum|subtotal|revenue|to_receive|grand_total)(_q|_display|_amount)?$|_(sum|revenue)_q$"
)


def _money_sums(payload: dict) -> dict:
    """As chaves de topo que somam dinheiro e vieram com valor. A contagem não conta:
    ``total`` inteiro é o número de registros (o Histórico)."""
    return {
        key: value
        for key, value in payload.items()
        if _MONEY_SUM_KEY.search(key) and value is not None and not (key == "total" and isinstance(value, int))
    }


def _order(ref: str, *, customer: str, total_q: int, status: str = "accepted", **data):
    from shopman.orderman.models import Order

    payload = {"customer": {"name": customer, "phone": "+5543999887766"}, "fulfillment_type": "pickup", **data}
    return Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=total_q, data=payload)


@pytest.mark.channels("web")
def test_as_encomendas_chegam_ao_gerente_sem_a_soma_do_periodo(client):
    """O valor de cada encomenda chega (é com ele que o balcão recebe); a soma do
    período e a de cada dia, não."""
    from django.utils import timezone

    today = timezone.localdate()
    _order("ENC-ANA", customer="Ana Souza", total_q=3600, delivery_date=today.isoformat())
    _order("ENC-BIA", customer="Bia Lima", total_q=8100, delivery_date=today.isoformat())
    _order("ENC-ANA-2", customer="Ana Souza", total_q=5000, status="completed",
           delivery_date=(today - timedelta(days=1)).isoformat())
    client.force_login(_gerente())

    period = client.get("/api/v1/backstage/pos/preorders/", {"date_from": today.isoformat(), "date_to": today.isoformat()})
    search = client.get("/api/v1/backstage/pos/preorders/search/", {"q": "ana", "include_completed": "1"})

    assert period.status_code == 200, period.content
    assert search.status_code == 200, search.content
    body = period.json()
    assert body["count"] == 2
    assert not _money_sums(body), f"soma do período servida ao Gerente: {_money_sums(body)}"
    for day in body["days"]:
        assert not _money_sums(day), f"soma do dia {day['date']} servida ao Gerente: {_money_sums(day)}"
        assert all(card["total_display"].startswith("R$") for card in day["orders"])
    assert not _money_sums(search.json()), f"soma servida ao Gerente na busca: {_money_sums(search.json())}"


@pytest.mark.channels("web")
def test_o_historico_do_gestor_nao_soma_os_pedidos(client):
    """O valor de cada pedido fechado chega; nenhuma soma sobre as linhas chega."""
    from django.utils import timezone
    from shopman.orderman.models import Order

    _order("HIST-ANA", customer="Ana Souza", total_q=3600, status="completed")
    _order("HIST-BIA", customer="Bia Lima", total_q=8100, status="completed")
    Order.objects.filter(ref__in=["HIST-ANA", "HIST-BIA"]).update(completed_at=timezone.now())
    client.force_login(_gerente())

    response = client.get("/api/v1/backstage/orders/history/")

    assert response.status_code == 200, response.content
    history = response.json()["history"]
    assert {row["ref"] for row in history["items"]} == {"HIST-ANA", "HIST-BIA"}
    assert history["total"] == 2, "o ``total`` do Histórico é a CONTAGEM de pedidos"
    assert not _money_sums(history), f"soma servida ao Gerente no Histórico: {_money_sums(history)}"
    for label in (history["total_label"], history["period_label"]):
        assert "R$" not in label, label
    for facet in history["facets"]:
        for option in facet["options"]:
            assert set(option) == {"value", "label", "count"}, f"o recorte {facet['id']} carrega mais que contagem"


def test_as_contas_na_casa_vao_pela_divida_mais_antiga_e_nunca_pelo_saldo(client):
    """A lista pelo maior saldo é um ranking de clientes pelo dinheiro."""
    from django.utils import timezone
    from shopman.guestman.models import Customer
    from shopman.payman.models import PaymentIntent

    now = timezone.now()
    for ref, name, amount_q, days_ago in (
        ("CLI-GRANDE", "Zélia", 90000, 1),
        ("CLI-ANTIGA", "Ana", 1200, 20),
        ("CLI-MEIO", "Bia", 30000, 7),
    ):
        Customer.objects.create(ref=ref, first_name=name, metadata={"house_account": True})
        PaymentIntent.objects.create(
            ref=f"PI-{ref}", order_ref=f"ORD-{ref}", method="account", status="authorized",
            amount_q=amount_q, gateway_data={"customer_ref": ref},
            authorized_at=now - timedelta(days=days_ago),
        )
    client.force_login(_gerente())

    response = client.get("/api/v1/backstage/pos/accounts/")

    assert response.status_code == 200, response.content
    refs = [row["customer_ref"] for row in response.json()["accounts"]]
    assert refs == ["CLI-ANTIGA", "CLI-MEIO", "CLI-GRANDE"], refs


def test_o_admin_de_pedidos_nao_da_ao_gerente_o_filtro_por_faixa_de_valor():
    """O filtro por faixa de ``total_q`` recorta pedidos de clientes diferentes pelo
    dinheiro. A coluna do total (o valor de cada pedido) e o filtro por data ficam."""
    from shopman.orderman.models import Order

    model_admin = admin.site._registry[Order]

    def _filter_fields(user) -> set[str]:
        return {
            entry[0] for entry in model_admin.get_list_filter(_request_as(user))
            if isinstance(entry, (tuple, list)) and entry
        }

    gerente, dono = _gerente(), _user_in("dono-admin", "Dono", "Gerente")

    assert "total_q" not in _filter_fields(gerente)
    assert "created_at" in _filter_fields(gerente)
    assert "total_display" in model_admin.get_list_display(_request_as(gerente))
    assert model_admin.date_hierarchy == "created_at"
    assert "total_q" in _filter_fields(dono)


#: Exportação que o Gerente alcança e que NÃO carrega valor de pedido, venda ou
#: pagamento. Rota nova de exportação que chegue a ele reprova até entrar aqui,
#: com o motivo (ou sair do alcance dele).
EXPORTS_WITHOUT_MONEY: dict[str, str] = {
    "api-backstage-purchase-csv": "Cadastro de insumos e fornecedores (SKU, nome, unidade, contato). Sem preço nem custo.",
    "api-backstage-production-reports": (
        "Relatórios da Produção: quantidade, perda e qualidade, sem valor (conferido em 21/11/2026)."
    ),
    "api-account-export": (
        "A exportação LGPD da loja: o CLIENTE logado baixa os PRÓPRIOS dados (AllowAny + "
        "get_authenticated_customer, com step-up). Não lê pedido de outra pessoa nem da casa."
    ),
}


def _routes():
    from django.urls import URLPattern, URLResolver, get_resolver

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern), pattern

    yield from walk(get_resolver().url_patterns)


def _is_export(route: str, view_class) -> bool:
    if re.search(r"csv|export|download|xlsx", route):
        return True
    return any(
        re.search(r"csv|spreadsheet|excel", str(getattr(renderer, "media_type", "")))
        for renderer in (getattr(view_class, "renderer_classes", None) or ())
    )


def _reaches(user: User, view_class) -> bool:
    """O Gerente passa pelas permissões da view? Pergunta às próprias classes dela."""
    from django.core.exceptions import PermissionDenied
    from rest_framework.exceptions import APIException
    from rest_framework.request import Request

    request = Request(RequestFactory().get("/"))
    request.user = user
    view = view_class()
    view.request, view.args, view.kwargs = request, (), {}
    try:
        return all(permission.has_permission(request, view) for permission in view.get_permissions())
    except (PermissionDenied, APIException):
        return False


def test_nenhuma_exportacao_com_dinheiro_alcanca_o_gerente():
    gerente = User.objects.get(pk=_gerente().pk)
    reached: dict[str, str] = {}
    for route, pattern in _routes():
        view_class = getattr(pattern.callback, "view_class", None) or getattr(pattern.callback, "cls", None)
        if view_class is None or route.startswith("admin/") or not _is_export(route, view_class):
            continue
        if not hasattr(view_class, "get_permissions"):
            continue
        if _reaches(gerente, view_class):
            reached[pattern.name or route] = route

    unclassified = set(reached) - set(EXPORTS_WITHOUT_MONEY)
    assert not unclassified, (
        f"Exportação alcançável pelo Gerente e não classificada: {sorted(unclassified)}. Exportação de "
        "pedido, venda ou pagamento com valor é agregado (dono, 21/11/2026); sem valor, declare em "
        "EXPORTS_WITHOUT_MONEY com o motivo."
    )
    stale = set(EXPORTS_WITHOUT_MONEY) - set(reached)
    assert not stale, f"Classificadas e fora do alcance do Gerente (tire da lista): {sorted(stale)}"


def test_o_aviso_do_bi_ao_balcao_nao_traz_numero_do_faturamento():
    """O aviso de dia fraco vai ao bus do operador (Gerente e Caixa leem): nem reais,
    nem a proporção do esperado. O detalhe fica no evento do B.I., que é do Dono."""
    from shopman.backstage.bi.alerts import Reading, _public_message
    from shopman.backstage.models import BIAlertRule

    rule = BIAlertRule(ref="faturamento", label="Vendas do dia", metric=BIAlertRule.Metric.DAILY_REVENUE_VS_BASELINE)
    reading = Reading(
        value=3412.0, baseline=7100.0, fired=True,
        message="14/08 (sexta) faturou R$ 3.412,00, 48% do esperado (R$ 7.100,00 na média de 4 sextas)",
    )

    public = _public_message(rule, reading)

    assert "R$" not in public and "%" not in public, public
    assert "14/08 (sexta)" in public and "abaixo do esperado" in public
