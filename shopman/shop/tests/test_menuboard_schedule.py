"""Modo automático do menuboard: janela do expediente e descanso da TV."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from shopman.shop.projections.menuboard import MenuboardProjection, build_menuboard
from shopman.shop.tests._display import display_channel

TZ = ZoneInfo("America/Sao_Paulo")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 28, hour, minute, tzinfo=TZ)  # segunda-feira


@pytest.fixture
def automatic_board(db):
    from shopman.shop.models import Shop

    shop = Shop.objects.create(
        name="Nelson Boulangerie",
        timezone="America/Sao_Paulo",
        opening_hours={
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
        },
    )
    channel = display_channel("tv", "TV", collections=[], prices_from="pdv")
    channel.shop = shop
    channel.config["display"]["automatic"] = {
        "enabled": True,
        "idle_message": "Atendimento de seg. a sáb., das 9h às 18h · Minha padaria favorita",
    }
    channel.save(update_fields=["shop", "config"])
    return channel


@pytest.mark.parametrize(
    ("instant", "sleeping"),
    [
        (_at(8, 44), True),
        (_at(8, 45), False),
        (_at(18, 14), False),
        (_at(18, 15), True),
    ],
)
def test_automatic_window_has_fifteen_minutes_on_each_side(automatic_board, instant, sleeping):
    assert build_menuboard("tv", now=instant).is_sleeping is sleeping


def test_sleep_uses_the_configured_message(automatic_board):
    board = build_menuboard("tv", now=_at(3))
    assert board.is_active is True
    assert board.is_sleeping is True
    assert board.sleep_message == "Atendimento de seg. a sáb., das 9h às 18h · Minha padaria favorita"


def test_automatic_off_keeps_an_active_board_showing_continuously(automatic_board):
    automatic_board.config["display"]["automatic"]["enabled"] = False
    automatic_board.save(update_fields=["config"])
    board = build_menuboard("tv", now=_at(3))
    assert board.is_active is True
    assert board.is_sleeping is False


def test_active_toggle_wins_over_automatic_mode(automatic_board):
    automatic_board.is_active = False
    automatic_board.save(update_fields=["is_active"])
    board = build_menuboard("tv", now=_at(12))
    assert board.is_active is False
    assert board.is_sleeping is False
    assert board.off_message


def test_closed_date_sleeps_until_next_business_window(automatic_board):
    shop = automatic_board.shop
    shop.defaults = {"closed_dates": [{"date": "2026-09-28", "label": "Feriado"}]}
    shop.save(update_fields=["defaults"])
    from shopman.shop.services.menuboard_schedule import resolve_menuboard_automatic_state

    state = resolve_menuboard_automatic_state(automatic_board, now=_at(12))
    assert state.is_sleeping is True
    assert state.wakes_at == datetime(2026, 9, 29, 8, 45, tzinfo=TZ)
    assert state.state_line == "Automático: descanso até amanhã às 8h45."


def test_missing_store_hours_fails_open(db):
    from shopman.shop.models import Shop

    shop = Shop.objects.create(name="Sem grade", opening_hours={})
    channel = display_channel("tv-sem-grade", "TV", collections=[], prices_from="pdv")
    channel.shop = shop
    channel.config["display"]["automatic"] = {"enabled": True, "idle_message": "Olá"}
    channel.save(update_fields=["shop", "config"])
    board = build_menuboard("tv-sem-grade", now=_at(3))
    assert board.is_sleeping is False


def test_sleep_screen_is_server_rendered_without_javascript(client, settings, monkeypatch):
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    monkeypatch.setattr(
        "shopman.shop.views.menuboard.build_menuboard",
        lambda ref: MenuboardProjection(
            ref=ref,
            title="",
            subtitle="",
            is_sleeping=True,
            sleep_message="Minha padaria favorita",
        ),
    )
    html = client.get("/menuboard/tv/").content.decode()
    server_block = html.split('id="menuboard-server"')[1].split('id="menuboard-root"')[0]
    assert "data-menuboard-sleep" in server_block
    assert "Minha padaria favorita" in server_block
    assert "x-show" not in server_block
