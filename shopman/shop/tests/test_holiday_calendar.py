from datetime import date

from shopman.shop.services.holiday_calendar import (
    configured_regional_holidays,
    decision_for_day,
    official_brazil_holidays,
    upcoming_holidays,
)


def test_official_calendar_contains_recent_national_holidays():
    holidays = {item.day: item.label for item in official_brazil_holidays(2026)}

    assert holidays[date(2026, 1, 1)] == "Confraternização Universal"
    assert holidays[date(2026, 4, 3)] == "Paixão de Cristo"
    assert holidays[date(2026, 11, 20)] == "Dia Nacional de Zumbi e da Consciência Negra"
    assert holidays[date(2026, 12, 25)] == "Natal"


def test_regional_holidays_are_explicit_tenant_configuration():
    defaults = {
        "holiday_calendar": {
            "regional": [
                {"date": "2026-12-10", "label": "Aniversário da cidade", "scope": "city"},
                {"date": "inválida", "label": "Ignorar"},
            ]
        }
    }

    configured = configured_regional_holidays(defaults)

    assert len(configured) == 1
    assert configured[0].day == date(2026, 12, 10)
    assert configured[0].label == "Aniversário da cidade"
    assert configured[0].scope == "city"


def test_upcoming_window_and_decision_status():
    suggestions = upcoming_holidays(
        start=date(2026, 11, 1),
        end=date(2026, 12, 31),
        defaults={},
    )

    assert [item.day for item in suggestions] == [
        date(2026, 11, 2),
        date(2026, 11, 15),
        date(2026, 11, 20),
        date(2026, 12, 25),
    ]
    assert decision_for_day(
        date(2026, 12, 25),
        [{"date": "2026-12-25", "closed": False, "open": "09:00", "close": "13:00"}],
    ) == "special"
    assert decision_for_day(date(2026, 11, 2), []) == "pending"
