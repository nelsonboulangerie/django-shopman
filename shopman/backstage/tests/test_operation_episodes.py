"""O sistema nota; o operador só explica.

Ninguém lembra de anotar às 17h que faltou luz às 14h, e formulário em branco
todo dia vira campo morto — pior que não ter, porque a ausência de registro
passaria a ser lida como "não houve nada". Então o registro é automático e a
pergunta é dirigida: o sistema diz o que mediu e oferece as opções.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order

from shopman.backstage.models import (
    EpisodeStatus,
    OperationEpisode,
    OperationEpisodeKind,
)
from shopman.backstage.services import episodes
from shopman.backstage.services.business_day import stamp_day

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    from shopman.shop.models import Shop

    shop = Shop.objects.create(name="Nelson")
    shop.opening_hours = {
        name: {"open": "09:00", "close": "18:00"}
        for name in (
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        )
    }
    shop.save()
    return shop


@pytest.fixture
def ontem(loja):
    day = timezone.localdate() - timedelta(days=1)
    stamp_day(day)
    return day


@pytest.fixture
def motivos(db):
    OperationEpisodeKind.objects.create(
        ref="falta-de-energia", label="Faltou energia", affects_demand=True
    )
    OperationEpisodeKind.objects.create(
        ref="evento-na-regiao", label="Evento na região", affects_demand=False
    )


def _venda(day, hora: int, ref: str) -> None:
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="completed", total_q=1000
    )
    tz = timezone.get_current_timezone()
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.datetime(day.year, day.month, day.day, hora, 0, tzinfo=tz)
    )


class TestDetection:
    def test_sales_silence_becomes_a_question(self, ontem):
        """Vendeu, parou por horas, voltou: alguma coisa aconteceu no meio."""
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")

        episodes.detect_for_day(ontem)

        episode = OperationEpisode.objects.get(detector="sales_silence")
        assert episode.needs_answer
        assert episode.kind is None, "o sistema nunca chuta o motivo"
        assert "10:00" in episode.detected_signal and "15:00" in episode.detected_signal

    def test_slow_morning_is_not_an_episode(self, ontem):
        """Sem venda ANTES do silêncio, é só a manhã começando devagar."""
        _venda(ontem, 16, "UNICA")
        _venda(ontem, 17, "OUTRA")

        episodes.detect_for_day(ontem)

        assert not OperationEpisode.objects.filter(detector="sales_silence").exists()

    def test_day_of_business_with_no_sales_at_all(self, ontem):
        episodes.detect_for_day(ontem)

        episode = OperationEpisode.objects.get(detector="no_sales_at_all")
        assert "sem nenhuma venda" in episode.detected_signal

    def test_planned_batch_that_never_happened(self, ontem):
        recipe = Recipe.objects.create(
            ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("10")
        )
        WorkOrder.objects.create(
            ref="WO-1", recipe=recipe, output_sku="PAO",
            quantity=Decimal("20"), status=WorkOrder.Status.PLANNED, target_date=ontem,
        )

        episodes.detect_for_day(ontem)

        episode = OperationEpisode.objects.get(detector="missed_batch")
        assert "Pão" in episode.detected_signal

    def test_detecting_twice_does_not_ask_twice(self, ontem):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")

        episodes.detect_for_day(ontem)
        episodes.detect_for_day(ontem)

        assert OperationEpisode.objects.filter(detector="sales_silence").count() == 1

    def test_closed_day_raises_nothing(self, loja):
        """Dia sem expediente não tem silêncio a explicar."""
        day = timezone.localdate() - timedelta(days=2)
        loja.defaults = {"closed_dates": [{"date": day.isoformat(), "label": "Feriado"}]}
        loja.save()
        stamp_day(day)

        episodes.detect_for_day(day)

        assert not OperationEpisode.objects.exists()


class TestAnswering:
    def test_answering_records_what_happened(self, ontem, motivos):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episode = OperationEpisode.objects.get()

        episodes.answer(episode.pk, kind_ref="falta-de-energia", actor="marina")

        episode.refresh_from_db()
        assert episode.status == EpisodeStatus.CONFIRMED
        assert episode.kind.ref == "falta-de-energia"
        assert episode.resolved_by == "marina"

    def test_saying_nothing_happened_dismisses_it(self, ontem, motivos):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episode = OperationEpisode.objects.get()

        episodes.answer(episode.pk, kind_ref="", actor="marina")

        episode.refresh_from_db()
        assert episode.status == EpisodeStatus.DISMISSED
        assert episode.affects_demand is False


class TestConsequence:
    """O registro tem consequência: dia atípico não ensina demanda."""

    def test_unanswered_episode_still_protects_the_forecast(self, ontem):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)

        # Ninguém explicou — mas o sinal existiu, e é mais seguro não aprender
        # com um dia estranho do que aprender errado.
        assert ontem in episodes.disrupted_days(since=ontem, until=ontem)

    def test_kind_that_did_not_hurt_sales_keeps_the_day(self, ontem, motivos):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episode = OperationEpisode.objects.get()

        episodes.answer(episode.pk, kind_ref="evento-na-regiao", actor="marina")

        assert ontem not in episodes.disrupted_days(since=ontem, until=ontem)

    def test_disrupted_day_leaves_the_production_sample(self, ontem, motivos):
        """A ponta que dá sentido a tudo: o dia ruim não vira previsão."""
        from shopman.shop.services.production import untrustworthy_days

        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episodes.answer(
            OperationEpisode.objects.get().pk,
            kind_ref="falta-de-energia", actor="marina",
        )

        assert ontem in untrustworthy_days(days=28)


class TestTheQuestionOnlyShowsWhenThereIsASignal:
    def test_closing_asks_nothing_on_a_normal_day(self, ontem, motivos):
        from shopman.backstage.projections.closing import build_day_closing

        projection = build_day_closing()

        assert projection.has_pending_episodes is False
        assert projection.episode_options == ()

    def test_closing_asks_with_options_when_something_happened(self, motivos, loja):
        from shopman.backstage.projections.closing import build_day_closing

        hoje = timezone.localdate()
        stamp_day(hoje)
        _venda(hoje, 10, "ANTES")
        _venda(hoje, 15, "DEPOIS")
        episodes.detect_for_day(hoje)

        projection = build_day_closing()

        assert projection.has_pending_episodes
        assert projection.pending_episodes[0].signal
        assert projection.pending_episodes[0].window_display == "10:00 → 15:00"
        assert {o.ref for o in projection.episode_options} == {
            "falta-de-energia", "evento-na-regiao",
        }


def _operador_de_fechamento():
    """Operador com a permissão do fechamento — é lá que a pergunta aparece."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import DayClosing

    user = get_user_model().objects.create_user(
        "marina", password="x", is_staff=True
    )
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(DayClosing),
            codename="perform_closing",
        )
    )
    return user


class TestEndpoint:
    def test_operator_answers_through_the_api(self, ontem, motivos, client):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episode = OperationEpisode.objects.get()

        client.force_login(_operador_de_fechamento())

        response = client.post(
            f"/api/v1/backstage/closing/episodes/{episode.pk}/",
            {"kind_ref": "falta-de-energia"},
            content_type="application/json",
        )

        assert response.status_code == 200
        episode.refresh_from_db()
        assert episode.status == EpisodeStatus.CONFIRMED

    def test_unknown_kind_is_rejected_with_the_field(self, ontem, motivos, client):
        _venda(ontem, 10, "ANTES")
        _venda(ontem, 15, "DEPOIS")
        episodes.detect_for_day(ontem)
        episode = OperationEpisode.objects.get()

        client.force_login(_operador_de_fechamento())

        response = client.post(
            f"/api/v1/backstage/closing/episodes/{episode.pk}/",
            {"kind_ref": "invencionice"},
            content_type="application/json",
        )

        assert response.status_code == 404
        assert response.json()["field"] == "kind_ref"
