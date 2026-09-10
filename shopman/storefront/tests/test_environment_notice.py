"""A loja de teste precisa dizer que é de teste — e a de verdade, calar.

A loja do alpha é indistinguível da real: mesma marca, mesmo cardápio, mesmo
checkout. Sem aviso, um amigo convidado para experimentar faz um pedido achando
que vai receber pão, e o operador recebe um pedido achando que é de mentira.

O eixo que estes testes guardam é o do SILÊNCIO EM PRODUÇÃO: uma tarja que
aparece na loja de verdade é pior que tarja nenhuma — assusta cliente pagante.
"""

from __future__ import annotations

import pytest

from shopman.storefront.presentation.home import _environment_notice

pytestmark = pytest.mark.django_db


class TestOAmbienteDitaAFrase:
    def test_staging_avisa(self, settings):
        settings.SHOPMAN_ENVIRONMENT = "staging"

        assert _environment_notice() == "Ambiente de testes"

    def test_desenvolvimento_avisa(self, settings):
        settings.SHOPMAN_ENVIRONMENT = "development"

        assert _environment_notice() == "Ambiente de desenvolvimento"

    def test_producao_CALA(self, settings):
        """O eixo que importa: a loja de verdade não carrega tarja."""
        settings.SHOPMAN_ENVIRONMENT = "production"

        assert _environment_notice() == ""

    def test_maiuscula_e_espaco_nao_enganam(self, settings):
        """O valor vem de env digitada à mão; " Staging " é a mesma coisa."""
        settings.SHOPMAN_ENVIRONMENT = "  STAGING  "

        assert _environment_notice() == "Ambiente de testes"

    def test_ambiente_DESCONHECIDO_cala(self, settings):
        """Falha para o lado SILENCIOSO, e é deliberado.

        Aqui o dano é o alarme falso: um valor digitado errado
        ("prod", "produção") não pode fazer a loja de verdade anunciar que é
        teste para cliente pagante. É o oposto da regra de dinheiro e promessa,
        onde a omissão tem que ser restritiva.
        """
        for valor in ("prod", "produção", "", "qualquer-coisa"):
            settings.SHOPMAN_ENVIRONMENT = valor
            assert _environment_notice() == "", f"{valor!r} acendeu a tarja"

    def test_sem_a_variavel_definida_cala(self, settings):
        del settings.SHOPMAN_ENVIRONMENT

        assert _environment_notice() == ""


def test_a_frase_viaja_no_public_config(client, settings):
    """Contrato: a tela lê daqui, e é o mesmo lugar de onde já lê o DDD e o
    WhatsApp — sem interruptor próprio para a tarja."""
    from shopman.shop.models import Shop

    Shop.objects.create(name="Nelson", brand_name="Nelson")
    settings.SHOPMAN_ENVIRONMENT = "staging"

    resposta = client.get("/api/v1/storefront/home/")

    assert resposta.status_code == 200
    config = resposta.json()["home"]["public_config"]
    assert config["environment_notice"] == "Ambiente de testes"
