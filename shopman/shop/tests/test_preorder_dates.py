from datetime import date, timedelta

from shopman.shop.services import preorder_dates


def test_date_refusal_rejects_a_day_before_today():
    today = date(2026, 10, 17)

    refusal = preorder_dates.date_refusal(today - timedelta(days=1), today=today)

    assert refusal == "Não é possível encomendar para uma data passada."
