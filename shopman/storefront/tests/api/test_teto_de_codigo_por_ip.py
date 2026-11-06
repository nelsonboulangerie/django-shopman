"""Tetos de envio de código por IP e aviso de volume global (SMS pumping, beta 06/11).

Na UI, com o limite por minuto ligado, seis números diferentes pedidos do mesmo IP
em 90 s receberam código. Os limites do Doorman seguram o NÚMERO; o robô que troca
de número a cada pedido só é segurado por um teto do IP na hora e no dia, contado
sobre os códigos já gravados.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import VerificationCode

from shopman.shop.services import auth as auth_service

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings):
    # O 5/min do django-ratelimit é outra trava; aqui se mede só o teto do IP.
    settings.RATELIMIT_ENABLE = False


def _codes_from(ip: str, count: int, *, age: timedelta = timedelta(minutes=1)) -> None:
    for index in range(count):
        code = VerificationCode.objects.create(
            code_hash=f"hash-{ip}-{age}-{index}",
            target_value=f"+55439999{index:05d}",
            ip_address=ip,
        )
        VerificationCode.objects.filter(pk=code.pk).update(created_at=timezone.now() - age)


@pytest.fixture
def doorman_calls(monkeypatch):
    calls = []

    class FakeAuthService:
        @staticmethod
        def request_code(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(success=True, delivery_method="sms", expires_at="")

    monkeypatch.setattr("shopman.doorman.get_auth_service", lambda: FakeAuthService)
    return calls


def test_ip_abaixo_do_teto_da_hora_segue_para_o_doorman(doorman_calls):
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_HOUR - 1)

    result = auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert result.success is True
    assert len(doorman_calls) == 1


def test_ip_no_teto_da_hora_e_recusado_sem_enviar(doorman_calls):
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_HOUR)

    result = auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert result.success is False
    assert result.error_code == ErrorCode.IP_RATE_LIMIT
    assert doorman_calls == []


def test_teto_da_hora_e_por_ip(doorman_calls):
    _codes_from("198.51.100.9", auth_service.LOGIN_CODES_PER_IP_PER_HOUR)

    result = auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert result.success is True


def test_ip_paciente_esbarra_no_teto_do_dia(doorman_calls):
    # Fora da janela da hora, dentro do dia: o robô que respeita o teto da hora.
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_DAY, age=timedelta(hours=3))

    result = auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert result.success is False
    assert result.error_code == ErrorCode.IP_RATE_LIMIT
    assert doorman_calls == []


def test_codigo_de_ontem_nao_conta_no_teto_do_dia(doorman_calls):
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_DAY, age=timedelta(hours=25))

    result = auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert result.success is True


def test_troca_de_numero_tambem_respeita_o_teto(doorman_calls):
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_HOUR)

    result = auth_service.request_contact_verification_code(
        phone="+5543999990001", delivery_method="whatsapp", ip_address=IP, customer_uuid=None,
    )

    assert result.success is False
    assert result.error_code == ErrorCode.IP_RATE_LIMIT
    assert doorman_calls == []


def test_tela_entrar_recebe_muitas_tentativas_com_ip_real(monkeypatch, doorman_calls):
    from shopman.storefront.api import auth as auth_api

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    _codes_from(IP, auth_service.LOGIN_CODES_PER_IP_PER_HOUR)

    response = Client().post(
        "/api/v1/auth/request-code/",
        data={"target": "43999997777", "delivery_method": "sms"},
        content_type="application/json",
        REMOTE_ADDR=IP,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Muitas tentativas deste local. Tente mais tarde."
    assert doorman_calls == []


def test_volume_global_acima_do_limiar_avisa_a_ti_uma_vez(doorman_calls):
    from shopman.backstage.models import OperatorAlert

    # Muitos IPs, cada um abaixo do teto: só o volume global denuncia.
    for index in range(auth_service.LOGIN_CODES_GLOBAL_ALERT_PER_HOUR + 1):
        _codes_from(f"10.0.{index // 200}.{index % 200}", 1)

    auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)
    auth_service.request_code(phone="+5543999990002", delivery_method="sms", ip_address=IP)

    alerts = OperatorAlert.objects.filter(type=auth_service.LOGIN_CODE_VOLUME_ALERT_TYPE)
    assert alerts.count() == 1
    alert = alerts.get()
    assert alert.severity == "critical"
    assert str(auth_service.LOGIN_CODES_GLOBAL_ALERT_PER_HOUR) in alert.message


def test_volume_global_no_limiar_nao_avisa(doorman_calls):
    from shopman.backstage.models import OperatorAlert

    for index in range(auth_service.LOGIN_CODES_GLOBAL_ALERT_PER_HOUR):
        _codes_from(f"10.1.{index // 200}.{index % 200}", 1)

    auth_service.request_code(phone="+5543999990001", delivery_method="sms", ip_address=IP)

    assert not OperatorAlert.objects.filter(type=auth_service.LOGIN_CODE_VOLUME_ALERT_TYPE).exists()
