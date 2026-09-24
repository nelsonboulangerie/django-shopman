"""`MAILERS` é o único lugar onde a configuração de e-mail mora — e a trava disso.

O Django 6.1 deprecou todos os `EMAIL_*` e o Django 7 os remove. A migração já
foi feita; este arquivo existe para ela não voltar sozinha, porque o jeito como
ela voltaria é **calado**.

## Por que uma varredura, e não só testes de unidade

Com `MAILERS` definido, `settings.EMAIL_BACKEND` levanta `AttributeError`
(`django/conf/__init__.py`). Só que a casa inteira escreve
`getattr(settings, "EMAIL_BACKEND", "")` — e `getattr` com default **engole** o
`AttributeError` e devolve `""`. Ou seja: a linha que voltasse não quebraria. Ela
passaria a ler vazio, para sempre, em silêncio.

E o lugar onde ela cairia é o pior possível. `notification_email.is_available()`
existe para fechar um fail-open de Tier 1: canal inerte que se declara
disponível encerra a cadeia de fallback antes do SMS e do WhatsApp, e o cliente
não recebe o link de pagamento enquanto o log diz "Email sent". Um `EMAIL_HOST`
lido como `""` por um `getattr` que ninguém releu reabre exatamente esse buraco.

Um teste que mede só o comportamento de hoje não pega isso: pega o arquivo que
alguém escrever amanhã, e é para ele que a varredura serve.

## A irmã, e o que fica de fora

Os NOMES DAS VARIÁVEIS DE AMBIENTE seguem `EMAIL_BACKEND`, `EMAIL_HOST`, etc. —
são o contrato do spec de deploy, e `os.environ.get("EMAIL_HOST")` é legítimo.
A varredura recusa a leitura do SETTING, não a do ambiente; por isso ela procura
`settings.EMAIL_` e não `EMAIL_`. Prosa também fica de fora: explicar a
deprecação exige escrever o nome dela.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.test import override_settings

from shopman.shop.mailers import DIAGNOSTICS_ALIAS, default_mailer

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


# ── O leitor ─────────────────────────────────────────────────────────────────


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": SMTP,
            "OPTIONS": {
                "host": "smtp.sendgrid.net",
                "port": 587,
                "use_tls": True,
                "username": "nelson@boulangerie.com.br",
                "password": "segredo",
                "timeout": 15,
            },
        }
    }
)
def test_le_a_entrada_inteira():
    mailer = default_mailer()
    assert mailer.backend == SMTP
    assert mailer.host == "smtp.sendgrid.net"
    assert mailer.port == 587
    assert mailer.use_tls is True
    assert mailer.username == "nelson@boulangerie.com.br"
    assert mailer.timeout_seconds == 15


@override_settings(
    MAILERS={"default": {"BACKEND": SMTP, "OPTIONS": {"password": "segredo"}}}
)
def test_a_senha_nunca_sai_do_leitor():
    mailer = default_mailer()
    assert mailer.has_password is True
    assert "segredo" not in repr(mailer)


@override_settings(MAILERS={"default": {"BACKEND": CONSOLE}})
def test_entrada_sem_options_nao_estoura():
    """O caso que a suíte inteira vive.

    O `setup_test_environment()` do Django reescreve TODO alias para
    `{"BACKEND": locmem}` — sem `OPTIONS`. Um leitor que fizesse
    `entrada["OPTIONS"]["host"]` levantaria `KeyError` na suíte e em lugar
    nenhum além dela.
    """
    mailer = default_mailer()
    assert mailer.backend == CONSOLE
    assert mailer.host == ""
    assert mailer.port == 0
    assert mailer.has_password is False


@override_settings(MAILERS={"default": {"OPTIONS": {"host": "smtp.exemplo.test"}}})
def test_entrada_sem_backend_significa_SMTP_nao_console():
    """⚠️ O default do Django para `BACKEND` ausente é SMTP, não o de console.

    Adivinhar console aqui seria o fail-open de volta pela porta dos fundos: a
    casa trata console como inerte, então o canal se declararia indisponível
    para uma configuração de SMTP que na verdade vai tentar sair.
    """
    assert default_mailer().backend == SMTP


@override_settings(MAILERS={})
def test_sem_alias_default_o_canal_falha_FECHADO():
    """Sem entrada `default`, o resultado é "SMTP sem host" — e não entrega.

    É o estado certo: `is_available()` devolve `False` e a cadeia segue para SMS
    e WhatsApp. Um default de console diria "inerte" com a mesma conclusão, mas
    pela razão errada; um default entregável mentiria.
    """
    from shopman.shop.adapters import notification_email

    mailer = default_mailer()
    assert mailer.backend == SMTP
    assert mailer.host == ""
    assert notification_email.is_available() is False


def test_os_dois_aliases_da_casa_estao_declarados():
    """A view de diagnóstico pede `using=DIAGNOSTICS_ALIAS`.

    ⚠️ Vale dentro da suíte porque o `setup_test_environment()` troca o BACKEND
    de cada alias mas PRESERVA as chaves. Alias que sumisse de `settings`
    sumiria aqui — e o botão levantaria `MailerDoesNotExist` só na tela.
    """
    from django.conf import settings

    assert "default" in settings.MAILERS
    assert DIAGNOSTICS_ALIAS in settings.MAILERS


# ── A varredura ──────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[3]

ROOTS = ("shopman", "packages", "config")

#: Ler o SETTING deprecado, em qualquer das formas que a casa usa. A leitura do
#: AMBIENTE (`os.environ.get("EMAIL_HOST")`) é legítima e não casa com nenhuma.
PROIBIDO = re.compile(
    r"""settings\.EMAIL_[A-Z_]+          # settings.EMAIL_HOST
      | getattr\(\s*settings\s*,\s*["']EMAIL_   # getattr(settings, "EMAIL_HOST", "")
      | override_settings\([^)]*\bEMAIL_[A-Z_]+\s*=   # override_settings(EMAIL_BACKEND=...)
    """,
    re.VERBOSE,
)

#: Os dois arquivos que PRECISAM escrever o nome, porque são os que o recusam e
#: o que explica a migração. Allowlist nominal de propósito: lista que cresce
#: sem ninguém olhar é como a regra morre.
PODEM_CITAR = (
    "shopman/shop/tests/test_mailers.py",
    "shopman/shop/mailers.py",
)


def _fontes() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if "migrations" in path.parts or "build" in path.parts:
                continue
            relative = path.relative_to(REPO).as_posix()
            if relative in PODEM_CITAR:
                continue
            files.append(path)
    return files


FONTES = _fontes()


@pytest.mark.parametrize("path", FONTES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_ninguem_le_o_setting_deprecado(path: Path) -> None:
    # ⚠️ Comentário fica de fora, e `config/segue` dentro por causa disso: o
    # `settings.py` é o arquivo que MAIS precisa da trava e é também o que
    # explica a deprecação em prosa. Allowlistá-lo inteiro para acomodar três
    # linhas de comentário desarmaria a guarda justamente onde ela importa.
    offenders = [
        f"linha {lineno}: {line.strip()}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if PROIBIDO.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == [], (
        f"{path.relative_to(REPO)}: os `EMAIL_*` somem no Django 7, e com `MAILERS` "
        f"definido lê-los devolve vazio CALADO. Use `shopman.shop.mailers."
        f"default_mailer()` (ou declare `MAILERS` no teste): {offenders}"
    )


def test_a_varredura_le_mesmo_o_repositorio() -> None:
    """Varredura que não varre nada passa sempre."""
    assert len(FONTES) > 1000, f"a varredura achou só {len(FONTES)} arquivos"
