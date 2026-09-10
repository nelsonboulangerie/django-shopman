"""A tela que prova o e-mail — e as três coisas que a fazem ser segura.

A prova de envio morava no console da DigitalOcean, que **não recebe as envs
`SECRET`**: a senha chega vazia e o erro fala de `SECRET_KEY`, não de e-mail.
O processo que tem os segredos é o que serve o Admin, então a prova passou a
sair de dentro dele.
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from shopman.backstage.projections.diagnostics import build_diagnostics

pytestmark = pytest.mark.django_db

SMTP = "django.core.mail.backends.smtp.EmailBackend"
#: Remetente entregável. O default do projeto é `noreply@shopman.local`, e a
#: guarda de remetente o recusa de propósito: `.local` é TLD reservado a mDNS
#: (RFC 6762), sem SPF nem DMARC possíveis. Cenário que quer SMTP de pé precisa
#: declarar um remetente que exista — senão testa a armadilha, não o caminho.
REMETENTE_REAL = "nelson@nelsonboulangerie.com.br"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


@pytest.fixture(autouse=True)
def _shop():
    """Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


@pytest.fixture
def gestor(django_user_model):
    return django_user_model.objects.create_superuser(
        username="gestor", email="gestor@boulangerie.com.br", password="x"
    )


@pytest.fixture
def url():
    return reverse("admin_console_diagnostics")


# ── A projeção ───────────────────────────────────────────────────────────────


@override_settings(EMAIL_BACKEND=CONSOLE)
def test_console_e_inerte_e_a_projecao_diz_isso():
    """Console imprime e devolve sucesso — o pior tipo de mentira."""
    email = build_diagnostics().email
    assert email.entrega is False
    assert "inerte" in email.motivo.lower()


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="")
def test_smtp_sem_host_nao_entrega():
    email = build_diagnostics().email
    assert email.entrega is False
    assert "EMAIL_HOST" in email.motivo


@override_settings(
    EMAIL_BACKEND=SMTP,
    EMAIL_HOST="smtp.gmail.com",
    DEFAULT_FROM_EMAIL="nelson@nelsonboulangerie.com.br",
)
def test_smtp_com_host_e_remetente_real_entrega():
    assert build_diagnostics().email.entrega is True


@override_settings(
    EMAIL_BACKEND=SMTP,
    EMAIL_HOST="smtp.gmail.com",
    DEFAULT_FROM_EMAIL="noreply@shopman.local",
)
def test_smtp_de_pe_com_remetente_reservado_nao_entrega_e_a_tela_diz_por_que():
    """O SMTP de pé com remetente `.local` é fail-open por outra porta.

    O relay ACEITA, `send_mail` não levanta, `send()` devolve True — e esse True
    encerra a cadeia antes do SMS e do WhatsApp. `.local` é TLD reservado a mDNS
    (RFC 6762): sem DNS público, logo sem SPF nem DMARC.

    A tela tem de dizer que o problema é o REMETENTE. Antes deste caso o motivo
    caía no `else` e acusava "backend inerte" para um SMTP configurado — mandando
    o operador conferir exatamente onde o problema não está.
    """
    email = build_diagnostics().email
    assert email.entrega is False
    assert "remetente" in email.motivo.lower()
    assert "inerte" not in email.motivo.lower()


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.gmail.com", EMAIL_HOST_PASSWORD="segredo")
def test_a_senha_nunca_sai_da_projecao():
    """Só o FATO de existir senha viaja; o valor, nunca."""
    email = build_diagnostics().email
    assert email.has_password is True
    assert "segredo" not in repr(email)


# ── A tela ───────────────────────────────────────────────────────────────────


def test_a_tela_exige_login(client, url):
    resposta = client.get(url)
    assert resposta.status_code in {302, 403}


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_tela_abre_e_mostra_a_prontidao(client, gestor, url):
    client.force_login(gestor)
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert "diagnostics" in resposta.context


# ── O botão ──────────────────────────────────────────────────────────────────


@pytest.fixture
def smtp_de_mentira(monkeypatch):
    """Config de SMTP real (para `is_available` liberar) + conexão em memória.

    ⚠️ Não dá para testar o caminho feliz com `EMAIL_BACKEND=locmem`: a casa
    trata locmem como **inerte** de propósito (`notification_email.is_available`),
    então o próprio botão recusa o envio — e recusa certo. A disponibilidade e o
    transporte são eixos separados, e o teste tem de separá-los também.
    """
    monkeypatch.setattr(
        "shopman.backstage.admin_console.diagnostics.get_connection",
        lambda **kwargs: mail.get_connection(backend=LOCMEM),
    )
    with override_settings(
        EMAIL_BACKEND=SMTP,
        EMAIL_HOST="smtp.gmail.com",
        DEFAULT_FROM_EMAIL=REMETENTE_REAL,
    ):
        mail.outbox.clear()
        yield


def test_o_teste_vai_para_quem_esta_logado(client, gestor, url, smtp_de_mentira):
    """Nunca há campo de destinatário: teste que vai para cliente é incidente."""
    client.force_login(gestor)
    client.post(url, follow=True)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["gestor@boulangerie.com.br"]


def test_o_corpo_nao_carrega_segredo(client, gestor, url, smtp_de_mentira):
    client.force_login(gestor)
    with override_settings(EMAIL_HOST_PASSWORD="senha-de-app-secreta"):
        client.post(url, follow=True)
    assert "senha-de-app-secreta" not in mail.outbox[0].body


@override_settings(EMAIL_BACKEND=CONSOLE)
def test_com_canal_inerte_o_botao_recusa_em_vez_de_fingir(client, gestor, url):
    """Enviar por um backend que sempre 'funciona' provaria nada."""
    client.force_login(gestor)
    mail.outbox.clear()
    resposta = client.post(url, follow=True)
    assert len(mail.outbox) == 0
    avisos = [str(m) for m in resposta.context["messages"]]
    assert any("inerte" in a.lower() for a in avisos)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_usuario_sem_email_recebe_explicacao(client, url, django_user_model):
    sem_email = django_user_model.objects.create_superuser(
        username="sem-email", email="", password="x"
    )
    client.force_login(sem_email)
    mail.outbox.clear()
    resposta = client.post(url, follow=True)
    assert len(mail.outbox) == 0
    assert any("e-mail cadastrado" in str(m) for m in resposta.context["messages"])


@override_settings(
    EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.invalido.local", DEFAULT_FROM_EMAIL=REMETENTE_REAL
)
def test_falha_de_envio_mostra_o_erro_inteiro(client, gestor, url, monkeypatch):
    """Porta fechada, senha errada e SPF ausente são sintomas diferentes.

    Esconder a mensagem transformaria os três no mesmo 'não funcionou' — e é
    justamente a mensagem que diz qual dos três é.
    """
    def explode(*args, **kwargs):
        raise OSError("Connection timed out")

    monkeypatch.setattr(
        "shopman.backstage.admin_console.diagnostics.EmailMessage.send", explode
    )
    client.force_login(gestor)
    resposta = client.post(url, follow=True)
    avisos = [str(m) for m in resposta.context["messages"]]
    assert any("Connection timed out" in a for a in avisos)
    assert any("OSError" in a for a in avisos)


def test_o_envio_usa_timeout_curto(client, gestor, url, monkeypatch):
    """Sem teto, uma porta bloqueada pendura o clique por minutos.

    O sintoma de saída de rede bloqueada não é recusa — é silêncio. Ver
    `EMAIL_TIMEOUT` em settings, que fecha o mesmo buraco para o worker.
    """
    capturado = {}

    def fake_get_connection(**kwargs):
        capturado.update(kwargs)
        return mail.get_connection(backend=LOCMEM)

    monkeypatch.setattr(
        "shopman.backstage.admin_console.diagnostics.get_connection", fake_get_connection
    )
    with override_settings(
        EMAIL_BACKEND=SMTP,
        EMAIL_HOST="smtp.gmail.com",
        DEFAULT_FROM_EMAIL=REMETENTE_REAL,
    ):
        client.force_login(gestor)
        client.post(url, follow=True)

    assert capturado.get("timeout") is not None
    assert capturado["timeout"] <= 30


def test_settings_tem_teto_de_espera_para_o_worker():
    """O botão tem o teto dele; a fila de directives precisa do próprio."""
    from django.conf import settings

    assert getattr(settings, "EMAIL_TIMEOUT", None)
    assert settings.EMAIL_TIMEOUT <= 60
