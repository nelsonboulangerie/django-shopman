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
from shopman.shop.mailers import DIAGNOSTICS_ALIAS

pytestmark = pytest.mark.django_db

SMTP = "django.core.mail.backends.smtp.EmailBackend"
#: Remetente entregável. O default do projeto é `noreply@shopman.local`, e a
#: guarda de remetente o recusa de propósito: `.local` é TLD reservado a mDNS
#: (RFC 6762), sem SPF nem DMARC possíveis. Cenário que quer SMTP de pé precisa
#: declarar um remetente que exista — senão testa a armadilha, não o caminho.
REMETENTE_REAL = "nelson@nelsonboulangerie.com.br"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


def mailers(backend: str, **options) -> dict:
    """O `MAILERS` de um cenário — os DOIS aliases que a casa declara.

    ⚠️ `override_settings(MAILERS=...)` TROCA o dicionário inteiro, não faz
    merge. Um cenário que declarasse só o `default` faria o botão de teste
    levantar `MailerDoesNotExist` ao pedir o alias `diagnostics`.

    O `diagnostics` fica sempre em memória, e isso separa os dois eixos que o
    teste precisa separar: o `default` DESCREVE o canal (é ele que
    `is_available` lê para liberar ou recusar o botão) e o `diagnostics`
    TRANSPORTA. Sem essa separação não dá para testar o caminho feliz — a casa
    trata locmem como inerte de propósito, então um `default` em memória faria
    o próprio botão recusar o envio, e recusar certo.

    ⚠️ `OPTIONS` só vai preenchida para SMTP, como em `config/settings.py`: com
    `MAILERS`, uma option que o backend não conhece levanta `InvalidMailer`
    ("Unknown options ..."). O mundo dos settings antigos engolia; este não.
    """
    return {
        "default": {"BACKEND": backend, "OPTIONS": options},
        DIAGNOSTICS_ALIAS: {"BACKEND": LOCMEM},
    }


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


@override_settings(MAILERS=mailers(CONSOLE))
def test_console_e_inerte_e_a_projecao_diz_isso():
    """Console imprime e devolve sucesso — o pior tipo de mentira."""
    email = build_diagnostics().email
    assert email.entrega is False
    assert "inerte" in email.motivo.lower()


@override_settings(MAILERS=mailers(SMTP, host=""))
def test_smtp_sem_host_nao_entrega():
    email = build_diagnostics().email
    assert email.entrega is False
    assert "EMAIL_HOST" in email.motivo


@override_settings(
    MAILERS=mailers(SMTP, host="smtp.gmail.com"),
    DEFAULT_FROM_EMAIL="nelson@nelsonboulangerie.com.br",
)
def test_smtp_com_host_e_remetente_real_entrega():
    assert build_diagnostics().email.entrega is True


@override_settings(
    MAILERS=mailers(SMTP, host="smtp.gmail.com"),
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


@override_settings(MAILERS=mailers(SMTP, host="smtp.gmail.com", password="segredo"))
def test_a_senha_nunca_sai_da_projecao():
    """Só o FATO de existir senha viaja; o valor, nunca."""
    email = build_diagnostics().email
    assert email.has_password is True
    assert "segredo" not in repr(email)


# ── A tela ───────────────────────────────────────────────────────────────────


def test_a_tela_exige_login(client, url):
    resposta = client.get(url)
    assert resposta.status_code in {302, 403}


@override_settings(MAILERS=mailers(LOCMEM))
def test_a_tela_abre_e_mostra_a_prontidao(client, gestor, url):
    client.force_login(gestor)
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert "diagnostics" in resposta.context


# ── O botão ──────────────────────────────────────────────────────────────────


@pytest.fixture
def smtp_de_mentira():
    """`default` de SMTP real (para `is_available` liberar) + envio em memória.

    Nenhum monkeypatch: o alias `diagnostics` do `mailers()` já é o transporte
    em memória, e é por ele que a view envia (`send(using=...)`).
    """
    with override_settings(
        MAILERS=mailers(SMTP, host="smtp.gmail.com"),
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
    with override_settings(
        MAILERS=mailers(SMTP, host="smtp.gmail.com", password="senha-de-app-secreta"),
        DEFAULT_FROM_EMAIL=REMETENTE_REAL,
    ):
        client.post(url, follow=True)
    assert "senha-de-app-secreta" not in mail.outbox[0].body


@override_settings(MAILERS=mailers(CONSOLE))
def test_com_canal_inerte_o_botao_recusa_em_vez_de_fingir(client, gestor, url):
    """Enviar por um backend que sempre 'funciona' provaria nada."""
    client.force_login(gestor)
    mail.outbox.clear()
    resposta = client.post(url, follow=True)
    assert len(mail.outbox) == 0
    avisos = [str(m) for m in resposta.context["messages"]]
    assert any("inerte" in a.lower() for a in avisos)


@override_settings(MAILERS=mailers(LOCMEM))
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
    MAILERS=mailers(SMTP, host="smtp.invalido.local"), DEFAULT_FROM_EMAIL=REMETENTE_REAL
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


def test_o_botao_tem_teto_de_espera_MENOR_que_o_do_worker():
    """Sem teto, uma porta bloqueada pendura o clique por minutos.

    O sintoma de saída de rede bloqueada não é recusa — é silêncio.

    ⚠️ A garantia mudou de lugar junto com o código: ela era "a view passa
    `timeout=` para `get_connection()`" e passou a ser "o alias `diagnostics`
    declara um teto menor que o do `default`". Medir a chamada não prova mais
    nada — a view não passa timeout nenhum, quem carrega o teto é o alias.
    """
    from config.settings import _mailer_options

    do_worker = _mailer_options(SMTP)["timeout"]
    do_botao = _mailer_options(SMTP, timeout=_teto_do_botao())["timeout"]

    assert do_botao <= 30
    assert do_botao < do_worker, (
        "o botão tem alguém olhando a tela; o worker, não. Igualar os dois "
        "devolve o clique pendurado que este teto existe para evitar."
    )


def _teto_do_botao() -> int:
    from config.settings import _EMAIL_TIMEOUT_DIAGNOSTICO

    return _EMAIL_TIMEOUT_DIAGNOSTICO


def test_os_dois_aliases_existem_em_settings():
    """A view pede `using=DIAGNOSTICS_ALIAS`; settings tem de ter esse alias.

    ⚠️ Vale de verdade dentro da suíte: o `setup_test_environment()` do Django
    troca o BACKEND de todo alias por locmem, mas PRESERVA as chaves. Alias que
    sumisse de settings sumiria aqui também — e o botão levantaria
    `MailerDoesNotExist` só na tela do gestor.
    """
    from django.conf import settings

    assert DIAGNOSTICS_ALIAS in settings.MAILERS
    assert "default" in settings.MAILERS


def test_settings_tem_teto_de_espera_para_o_worker():
    """O botão tem o teto dele; a fila de directives precisa do próprio.

    ⚠️ A pergunta vai ao módulo de settings, não a `settings.MAILERS`, e por um
    motivo: o `setup_test_environment()` do Django reescreve TODO alias de
    `MAILERS` para `{"BACKEND": locmem}` — sem `OPTIONS`. Perguntar ao
    `settings` durante a suíte mediria o ambiente de teste e responderia que não
    há teto nenhum. O que interessa é o que o deploy monta quando o backend é
    SMTP, que é o único caso em que existe socket para pendurar.
    """
    from config.settings import _mailer_options

    timeout = _mailer_options(SMTP)["timeout"]
    assert timeout
    assert timeout <= 60
