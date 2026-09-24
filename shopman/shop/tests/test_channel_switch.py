"""O toggle "Ativo" de todo canal: período, motivo, horário da loja e o que desligar faz.

Decisão do dono (22/09/2026): um toggle só por card, para canal de venda e feed.
Mexer nele abre um modal com período ("por 30 minutos", "por 1 hora", "por hoje",
"sem prazo" ou um período no calendário) e motivo; no fim do período o canal volta
sozinho. O calendário da loja sempre prevalece no sentido de FECHAR: o toggle só
fecha mais. Estes testes travam o serviço (``channel_switch``) e os efeitos por
tipo de canal: commit recusado, TV com tela preta, feed fora de estoque. (A home
da loja online avisando mora em ``storefront/tests/test_home_ordering_off.py``.)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.orderman.exceptions import ValidationError

from shopman.shop.models import Channel, Shop
from shopman.shop.services import channel_switch, sessions
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")
WEEK = {
    day: {"open": "09:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
}
TUESDAY_10H = datetime(2026, 12, 22, 10, 0, tzinfo=TZ)
TUESDAY_20H = datetime(2026, 12, 22, 20, 0, tzinfo=TZ)
TUESDAY_7H = datetime(2026, 12, 22, 7, 0, tzinfo=TZ)


@pytest.fixture
def shop():
    return Shop.objects.create(name="Nelson", timezone="America/Sao_Paulo", opening_hours=WEEK)


@pytest.fixture
def web(shop):
    return Channel.objects.create(ref="web", name="Loja online")


def _person(username, name=""):
    first, _, last = name.partition(" ")
    return get_user_model().objects.create_user(username=username, first_name=first, last_name=last, is_staff=True)


# ── Período e volta sozinho ───────────────────────────────────────────────────


def test_desligar_por_30_minutos_vale_na_hora_e_volta_sozinho_pelo_relogio(web):
    channel_switch.request_switch("web", False, period="30m", reason="Loja cheia", actor=None, now=TUESDAY_10H)
    web.refresh_from_db()

    assert web.is_active is False
    assert channel_switch.effective_active(web, now=TUESDAY_10H + timedelta(minutes=29)) is False
    # Sem esperar o worker: quem decide lê o relógio.
    assert channel_switch.effective_active(web, now=TUESDAY_10H + timedelta(minutes=30)) is True
    assert web.is_active is False  # o carimbo ainda é o de antes


def test_o_worker_carimba_o_fim_do_periodo_e_o_card_conta_que_foi_o_relogio(web):
    channel_switch.request_switch("web", False, period="1h", reason="Loja cheia", actor=None, now=TUESDAY_10H)

    changed = channel_switch.apply_due(now=TUESDAY_10H + timedelta(minutes=61))

    web.refresh_from_db()
    assert changed == 1
    assert web.is_active is True
    assert channel_switch.state_line(web, now=TUESDAY_10H + timedelta(minutes=62)) == (
        "Religado hoje às 11h, no fim do período."
    )
    # Rodar de novo não muda nada nem conta de novo.
    assert channel_switch.apply_due(now=TUESDAY_10H + timedelta(minutes=70)) == 0


def test_sem_prazo_fica_ate_alguem_religar(web):
    channel_switch.request_switch("web", False, period="open", reason="Férias", actor=None, now=TUESDAY_10H)
    web.refresh_from_db()

    assert channel_switch.effective_active(web, now=TUESDAY_10H + timedelta(days=40)) is False
    assert channel_switch.apply_due(now=TUESDAY_10H + timedelta(days=40)) == 0


def test_periodo_no_calendario_no_futuro_e_agendamento(web):
    start = datetime(2026, 12, 24, 0, 0, tzinfo=TZ)
    end = datetime(2027, 1, 4, 0, 0, tzinfo=TZ)
    channel_switch.request_switch(
        "web", False, period="custom", starts_at=start, ends_at=end, reason="Férias", actor=None, now=TUESDAY_10H
    )
    web.refresh_from_db()

    assert web.is_active is True  # ainda não começou
    assert channel_switch.effective_active(web, now=start + timedelta(minutes=1)) is False
    assert channel_switch.effective_active(web, now=end) is True
    assert channel_switch.scheduled_line(web, now=TUESDAY_10H) == (
        "Desliga qui. 24/12 às 0h até seg. 4/1 às 0h (agendado): Férias."
    )
    channel_switch.apply_due(now=start + timedelta(minutes=1))
    web.refresh_from_db()
    assert web.is_active is False


def test_periodo_no_calendario_recusa_fim_antes_do_inicio_e_periodo_longo_demais(web):
    with pytest.raises(channel_switch.ChannelSwitchError, match="depois do início"):
        channel_switch.request_switch(
            "web", False, period="custom", starts_at=TUESDAY_10H + timedelta(days=2),
            ends_at=TUESDAY_10H + timedelta(days=1), reason="Férias", actor=None, now=TUESDAY_10H,
        )
    with pytest.raises(channel_switch.ChannelSwitchError, match="sem prazo"):
        channel_switch.request_switch(
            "web", False, period="custom", starts_at=TUESDAY_10H,
            ends_at=TUESDAY_10H + timedelta(days=120), reason="Férias", actor=None, now=TUESDAY_10H,
        )


def test_desligar_exige_motivo_e_ligar_nao(web):
    with pytest.raises(channel_switch.ChannelSwitchError, match="motivo"):
        channel_switch.request_switch("web", False, period="1h", reason="  ", actor=None, now=TUESDAY_10H)
    channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None, now=TUESDAY_10H)
    channel_switch.request_switch("web", True, period="open", actor=None, now=TUESDAY_10H + timedelta(minutes=5))
    web.refresh_from_db()
    assert web.is_active is True


def test_por_hoje_termina_no_fechamento_da_loja(web):
    record = channel_switch.request_switch("web", False, period="today", reason="Loja cheia", actor=None, now=TUESDAY_10H)

    assert record.ends_at == datetime(2026, 12, 22, 18, 0, tzinfo=TZ)


# ── O horário da loja sempre prevalece no sentido de fechar ───────────────────


def test_ligar_com_a_loja_fechada_nao_oferece_periodo_curto(web):
    web.is_active = False
    web.save(update_fields=["is_active"])

    options = {o.key: o for o in channel_switch.period_options(web, target=True, now=TUESDAY_20H)}

    assert not options["30m"].enabled and "loja está fechada" in options["30m"].reason
    assert not options["1h"].enabled
    assert not options["today"].enabled  # a loja não abre mais hoje
    assert options["open"].enabled and options["custom"].enabled
    with pytest.raises(channel_switch.ChannelSwitchError, match="fechada"):
        channel_switch.request_switch("web", True, period="1h", actor=None, now=TUESDAY_20H)


def test_ligar_por_hoje_antes_de_abrir_diz_o_horario_da_loja(web):
    web.is_active = False
    web.save(update_fields=["is_active"])

    options = {o.key: o for o in channel_switch.period_options(web, target=True, now=TUESDAY_7H)}

    assert options["today"].enabled
    assert options["today"].label == "Por hoje (das 9h às 18h)"


def test_canal_ligado_com_a_loja_fechada_diz_que_e_o_horario(web):
    assert channel_switch.closed_by_shop(web, now=TUESDAY_20H) == "Fechado pelo horário da loja"
    assert channel_switch.closed_by_shop(web, now=TUESDAY_10H) == ""


def test_feriado_diz_o_nome_do_fechamento(shop, web):
    shop.defaults = {"closed_dates": [{"date": "2026-12-25", "label": "Natal"}]}
    shop.save(update_fields=["defaults"])

    christmas = datetime(2026, 12, 25, 10, 0, tzinfo=TZ)
    assert channel_switch.closed_by_shop(web, now=christmas) == "Fechado pelo calendário da loja: Natal"


def test_canal_de_exibicao_nao_segue_o_horario(shop):
    """O feed é buscado de madrugada: seguir o horário zeraria o catálogo toda noite."""
    tv = display_channel("tv", "TV", collections=[], prices_from="pdv")

    assert channel_switch.closed_by_shop(tv, now=TUESDAY_20H) == ""
    options = {o.key: o for o in channel_switch.period_options(tv, target=True, now=TUESDAY_20H)}
    assert options["30m"].enabled


# ── Trilha: quem, quando, por quê, quem autorizou ─────────────────────────────


def test_gesto_fica_no_canal_e_no_log_do_admin(web):
    ana = _person("ana", "Ana Souza")
    joyce = _person("joyce", "Joyce Lima")

    channel_switch.request_switch(
        "web", False, period="1h", reason="Desfalque na equipe", actor=ana, approved_by=joyce, now=TUESDAY_10H
    )

    web.refresh_from_db()
    record = web.config["activation"]
    assert (record["by"], record["approved_by"], record["reason"]) == ("Ana Souza", "Joyce Lima", "Desfalque na equipe")
    entry = LogEntry.objects.get(object_id=str(web.pk))
    assert entry.user == ana
    message = json.loads(entry.change_message)
    assert message["action"] == "channel.switch" and message["approved_by"] == "joyce"
    assert channel_switch.state_line(web, now=TUESDAY_10H) == (
        "Desligado por Ana Souza (autorizado por Joyce Lima) hoje às 10h: Desfalque na equipe. "
        "Volta a ligar hoje às 11h."
    )


def test_revisao_velha_nao_grava(web):
    stale = channel_switch.revision(web)
    channel_switch.request_switch("web", False, period="1h", reason="Loja cheia", actor=None, now=TUESDAY_10H)

    with pytest.raises(channel_switch.ChannelSwitchConflict):
        channel_switch.request_switch("web", True, period="open", actor=None, expected_revision=stale, now=TUESDAY_10H)


# ── O que desligar faz, por tipo de canal ─────────────────────────────────────


def test_canal_de_venda_desligado_recusa_o_commit(web):
    """A trava de verdade mora no commit: POST direto, aba antiga e PDV chegam aqui."""
    channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None)

    with pytest.raises(ValidationError) as refused:
        sessions.commit_session(session_key="qualquer", channel_ref="web", idempotency_key="k-1")

    assert refused.value.code == "channel_off"
    assert refused.value.message == "Loja online não está recebendo pedidos agora."


def test_canal_de_venda_ligado_segue_para_o_commit(web):
    from shopman.orderman.exceptions import SessionError

    # Sem sessão, quem recusa é o Core — a trava do canal deixou passar.
    with pytest.raises(SessionError):
        sessions.commit_session(session_key="inexistente", channel_ref="web", idempotency_key="k-2")


@pytest.fixture
def tv(shop):
    collection = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    product = Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=800, is_published=True, is_sellable=True,
        image_url="https://cdn.test/pao.jpg",
    )
    CollectionItem.objects.create(collection=collection, product=product)
    return display_channel("tv-cafe", "TV do Café", collections=["paes"], prices_from="pdv")


def test_tv_desligada_vira_tela_preta_sem_produto(client, tv, django_user_model):
    from shopman.shop.projections.menuboard import OFF_MESSAGE, build_menuboard

    channel_switch.request_switch("tv-cafe", False, period="open", reason="Férias", actor=None)

    board = build_menuboard("tv-cafe")
    assert board.is_active is False and board.groups == () and board.off_message == OFF_MESSAGE

    client.force_login(django_user_model.objects.create_user("gestor", password="x", is_staff=True))
    page = client.get("/menuboard/tv-cafe/")
    assert page.status_code == 200  # não é 404: a TV troca para a tela preta
    html = page.content.decode()
    assert "data-menuboard-off" in html and OFF_MESSAGE in html
    assert "Pão" not in html
    data = client.get("/menuboard/tv-cafe/data/").json()
    assert data["is_active"] is False and data["groups"] == []


def test_feed_desligado_sai_com_tudo_fora_de_estoque(client, shop, settings):
    # Sem a base da loja o feed responde 404 de propósito (#955): o link do item é da loja.
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://www.loja.test"
    collection = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    product = Product.objects.create(
        sku="BAGUETE", name="Baguete", unit="un", base_price_q=1300, is_published=True, is_sellable=True,
        image_url="https://cdn.test/baguete.jpg",
    )
    CollectionItem.objects.create(collection=collection, product=product)
    display_channel("google", "Google", collections=["vitrine"], fmt="google_merchant", prices_from="web")

    channel_switch.request_switch("google", False, period="open", reason="Férias", actor=None)

    resp = client.get("/feed/google.xml")
    assert resp.status_code == 200  # 404 faria a plataforma seguir anunciando a última leitura
    items = ET.fromstring(resp.content).find("channel").findall("item")
    assert len(items) == 1  # o item continua: sumir apagaria o produto na plataforma
    assert items[0].find("{http://base.google.com/ns/1.0}availability").text == "out_of_stock"


# ── Notificação comum (sino) só na mudança ────────────────────────────────────


def _gestor(username="gestor"):
    from django.contrib.auth.models import Permission

    user = _person(username, "Pablo Valentini")
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    return user


def test_mudanca_de_estado_vira_notificacao_para_quem_gerencia_pedidos(web, django_capture_on_commit_callbacks):
    from shopman.shop.models import UserNotification

    gestor = _gestor()
    ana = _person("ana", "Ana Souza")
    with django_capture_on_commit_callbacks(execute=True):
        channel_switch.request_switch("web", False, period="30m", reason="Loja cheia", actor=ana, now=TUESDAY_10H)

    (notification,) = UserNotification.objects.filter(user=gestor)
    assert notification.title == "Canal desligado: Loja online"
    assert notification.message == "Por Ana Souza: Loja cheia. Volta a ligar hoje às 10h30."
    assert notification.is_actionable is False


def test_fim_do_periodo_notifica_uma_vez_e_o_worker_repetido_nao(web, django_capture_on_commit_callbacks):
    from shopman.shop.models import UserNotification

    gestor = _gestor()
    channel_switch.request_switch("web", False, period="1h", reason="Loja cheia", actor=None, now=TUESDAY_10H)
    UserNotification.objects.all().delete()

    with django_capture_on_commit_callbacks(execute=True):
        channel_switch.apply_due(now=TUESDAY_10H + timedelta(minutes=61))
        channel_switch.apply_due(now=TUESDAY_10H + timedelta(minutes=70))

    (notification,) = UserNotification.objects.filter(user=gestor)
    assert notification.title == "Canal religado: Loja online"
    assert notification.message == "Fim do período (hoje às 11h)."


def test_agendamento_notifica_como_agendamento(web, django_capture_on_commit_callbacks):
    from shopman.shop.models import UserNotification

    gestor = _gestor()
    start = datetime(2026, 12, 24, 0, 0, tzinfo=TZ)
    with django_capture_on_commit_callbacks(execute=True):
        channel_switch.request_switch(
            "web", False, period="custom", starts_at=start, ends_at=start + timedelta(days=2),
            reason="Férias", actor=_person("joyce", "Joyce"), now=TUESDAY_10H,
        )

    (notification,) = UserNotification.objects.filter(user=gestor)
    assert notification.title == "Desligamento agendado: Loja online"
    assert notification.message == "Desliga qui. 24/12 às 0h até sáb. 26/12 às 0h. Por Joyce: Férias."


# ── PDV: sem toggle, e nada de canal recusa venda no balcão ───────────────────


def test_pdv_nao_tem_toggle_e_nunca_recusa_venda_por_estado_de_canal(shop):
    """Decisão do dono (22/09): o balcão é a loja física; parar de vender é fechar o caixa.

    Mesmo com o canal PDV marcado inativo (pelo Admin, por um gesto antigo), a trava
    de canal deixa passar — quem recusa, sem sessão, é o Core.
    """
    from shopman.orderman.exceptions import SessionError

    pdv = Channel.objects.create(ref="pdv", name="PDV", is_active=False)

    assert channel_switch.is_switchable(pdv) is False
    with pytest.raises(channel_switch.ChannelSwitchError, match="fechar o caixa"):
        channel_switch.request_switch("pdv", False, period="open", reason="Férias", actor=None)
    channel_switch.ensure_accepting_orders("pdv")  # não levanta
    with pytest.raises(SessionError):
        sessions.commit_session(session_key="inexistente", channel_ref="pdv", idempotency_key="k-pdv")
