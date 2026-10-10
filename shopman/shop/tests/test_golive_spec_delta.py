"""O delta do dia D: a lista do script, a do runbook e a das travas andam juntas.

A virada é trocar chaves no spec do app vivo (D-029). Três lugares sabem quais
são: o `scripts/golive_spec_delta.py` (confere), o
`docs/runbooks/go-live-delta-do-spec.md` (explica) e as travas de produção
(`scripts/check_production_contract.py`, os checks de deploy). Se uma lista
ganhar uma chave e as outras não, a virada fica pela metade sem ninguém ver;
estes testes reprovam essa deriva.

O script vive fora da árvore do pacote, então é carregado por caminho.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import check_production_contract as contract
from scripts import golive_spec_delta as delta

_ROOT = Path(__file__).resolve().parents[3]
_RUNBOOK = _ROOT / "docs" / "runbooks" / "go-live-delta-do-spec.md"
_COMPONENTS = ("web-operator", "web-storefront", "directive-worker", "release")


def _env(key: str, value: str, *, secret: bool = False) -> dict:
    entry = {"key": key, "scope": "RUN_TIME", "value": value}
    if secret:
        entry["type"] = "SECRET"
    return entry


def _spec(app_envs: list[dict], *, component_envs: dict[str, list[dict]] | None = None) -> dict:
    component_envs = component_envs or {}
    commands = {
        "web-operator": "daphne -b 0.0.0.0 -p 8000 config.asgi:application",
        "web-storefront": "daphne -b 0.0.0.0 -p 8000 config.asgi:application",
        "directive-worker": "python manage.py process_directives --watch",
        "release": "sh -c 'python manage.py check --deploy'",
    }
    kinds = {"web-operator": "services", "web-storefront": "services", "directive-worker": "workers", "release": "jobs"}
    spec: dict = {"name": "shopman-nelson", "envs": app_envs, "services": [], "workers": [], "jobs": []}
    for name in _COMPONENTS:
        spec[kinds[name]].append({"name": name, "run_command": commands[name], "envs": component_envs.get(name, [])})
    # Um Nuxt sem run_command: não roda Django e não é conferido.
    spec["services"].append({"name": "storefront-nuxt", "envs": [_env("SHOPMAN_ENVIRONMENT", "staging")]})
    return spec


_SECRETS_TODAY = {
    key: f"EV[1:antes-{key}]"
    for key in (
        "EFI_CLIENT_ID",
        "EFI_CLIENT_SECRET",
        "EFI_CERTIFICATE_PEM_BASE64",
        "EFI_PIX_KEY",
        "EFI_WEBHOOK_TOKEN",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "FOCUS_NFE_TOKEN",
        "GOOGLE_MAPS_BROWSER_API_KEY",
        "GOOGLE_MAPS_SERVER_API_KEY",
        "DJANGO_SECRET_KEY",
        "DOORMAN_ACCESS_LINK_API_KEY",
        "COMTELE_API_KEY",
    )
}

_COMMON = [
    _env("DJANGO_DEBUG", "false"),
    _env("DJANGO_SECURE_SSL_REDIRECT", "true"),
    _env("SHOPMAN_CARD_ADAPTER", "shopman.shop.adapters.payment_stripe"),
    _env("SHOPMAN_FISCAL_ADAPTER", "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"),
    _env("SHOPMAN_FISCAL_EMISSION_RESOLVER", "shopman.shop.fiscal_resolvers.on_request_or_tax_id"),
    _env("SHOPMAN_EXPOSE_DEBUG_OTP", "false"),
    _env("SHOPMAN_STAGING_AUTOPILOT", "false"),
    _env("DJANGO_ALLOWED_HOSTS", "api.boulangerie.com.br,admin.boulangerie.com.br"),
    _env("CSRF_TRUSTED_ORIGINS", "https://api.boulangerie.com.br"),
    _env("DATABASE_URL", "${postgres.shopman-staging-pool.DATABASE_URL}"),
    _env("REDIS_URL", "${cache.REDIS_URL}"),
    _env("SHOPMAN_OPERATOR_COOKIE_DOMAIN", ".boulangerie.com.br"),
    _env("COMTELE_ROUTE", "17"),
    _env("EMAIL_HOST", "smtp.gmail.com"),
]

_HMAC = {
    name: [_env("SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY", "EV[1:hmac]", secret=True)]
    for name in ("web-operator", "web-storefront", "release")
}


def _today() -> dict:
    """O vivo de 10/10, reduzido ao que a tabela olha."""
    envs = [
        *_COMMON,
        _env("SHOPMAN_ENVIRONMENT", "staging"),
        _env("SHOPMAN_PIX_ADAPTER", "shopman.shop.adapters.payment_mock"),
        _env("EFI_SANDBOX", "true"),
        _env("SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", "true"),
        _env("SHOPMAN_EXPOSE_MOCK_CAPTURE", "true"),
        _env("SHOPMAN_MOCK_PIX_AUTO_CONFIRM", "false"),
        _env("SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS", "8"),
        _env("STRIPE_PUBLISHABLE_KEY", "pk_test_abc"),
        *[_env(key, value, secret=True) for key, value in _SECRETS_TODAY.items()],
    ]
    return _spec(envs, component_envs=_HMAC)


def _dia_d() -> dict:
    """O vivo depois da gravação única do dono."""
    rotated = {
        "EFI_CLIENT_ID",
        "EFI_CLIENT_SECRET",
        "EFI_CERTIFICATE_PEM_BASE64",
        "EFI_WEBHOOK_TOKEN",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "FOCUS_NFE_TOKEN",
    }
    envs = [
        *_COMMON,
        _env("SHOPMAN_ENVIRONMENT", "production"),
        _env("SHOPMAN_PIX_ADAPTER", "shopman.shop.adapters.payment_efi"),
        _env("EFI_SANDBOX", "false"),
        _env("STRIPE_PUBLISHABLE_KEY", "pk_live_abc"),
        _env("FOCUS_NFE_ENVIRONMENT", "producao"),
        _env("SHOPMAN_ADMIN_REQUIRE_2FA", "true"),
        _env("SHOPMAN_GO_LIVE", "true"),
        *[
            _env(key, f"EV[1:depois-{key}]" if key in rotated else value, secret=True)
            for key, value in _SECRETS_TODAY.items()
        ],
    ]
    return _spec(envs, component_envs=_HMAC)


def _status(findings) -> dict[str, str]:
    return {finding.row.key: finding.status for finding in findings}


# ---------------------------------------------------------------------------
# Hoje × dia D
# ---------------------------------------------------------------------------


def test_spec_de_hoje_lista_tudo_o_que_falta_virar():
    status = _status(delta.evaluate(_today()))

    virar = {key for key, value in status.items() if value == "virar"}
    assert virar == {
        "SHOPMAN_ENVIRONMENT",
        "SHOPMAN_PIX_ADAPTER",
        "EFI_SANDBOX",
        "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
        "SHOPMAN_EXPOSE_MOCK_CAPTURE",
        "STRIPE_PUBLISHABLE_KEY",
        "FOCUS_NFE_ENVIRONMENT",
        "SHOPMAN_ADMIN_REQUIRE_2FA",
        "SHOPMAN_GO_LIVE",
    }
    # Sem baseline, segredo presente não é "trocado": é sem prova, e conta como pendência.
    assert status["STRIPE_SECRET_KEY"] == "sem_prova"
    assert status["SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS"] == "limpeza"
    _, code = delta.render(delta.evaluate(_today()), etapa="dia-d", has_baseline=False)
    assert code == 1


def test_spec_do_dia_d_com_baseline_fecha_em_zero():
    findings = delta.evaluate(_dia_d(), baseline_spec=_today())

    assert {f.row.key: f.status for f in findings if f.status != "ok"} == {}
    text, code = delta.render(findings, etapa="dia-d", has_baseline=True)
    assert code == 0
    assert "Nada obrigatório pendente" in text


def test_segredo_com_o_mesmo_cifrado_do_baseline_nao_foi_trocado():
    after = _dia_d()
    for entry in after["envs"]:
        if entry["key"] == "STRIPE_SECRET_KEY":
            entry["value"] = _SECRETS_TODAY["STRIPE_SECRET_KEY"]

    status = _status(delta.evaluate(after, baseline_spec=_today()))

    assert status["STRIPE_SECRET_KEY"] == "virar"


def test_override_de_componente_e_virada_pela_metade():
    spec = _dia_d()
    for component in spec["workers"]:
        if component["name"] == "directive-worker":
            component["envs"].append(_env("SHOPMAN_ENVIRONMENT", "staging"))

    findings = delta.evaluate(spec, baseline_spec=_today())
    by_key = {f.row.key: f for f in findings}

    assert by_key["SHOPMAN_ENVIRONMENT"].status == "virar"
    assert by_key["SHOPMAN_ENVIRONMENT"].partial is True
    assert by_key["SHOPMAN_ENVIRONMENT"].where == {"directive-worker": "staging"}
    text, _ = delta.render(findings, etapa="dia-d", has_baseline=True)
    assert "só em: directive-worker=staging" in text


def test_componente_nuxt_nao_e_conferido():
    # O storefront-nuxt do _spec declara staging; se fosse conferido, o dia D reprovaria.
    findings = delta.evaluate(_dia_d(), baseline_spec=_today())
    assert _status(findings)["SHOPMAN_ENVIRONMENT"] == "ok"


def test_hmac_so_e_cobrado_onde_o_check_roda():
    status = _status(delta.evaluate(_dia_d(), baseline_spec=_today()))
    # directive-worker não tem a chave, e não é cobrado.
    assert status["SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY"] == "ok"


def test_ensaio_do_pix_real_confere_so_o_que_o_ensaio_pede():
    findings = delta.evaluate(_today(), etapa="ensaio-pix")
    status = _status(findings)

    assert "STRIPE_SECRET_KEY" not in status
    assert {key for key, value in status.items() if value != "ok"} == {
        "SHOPMAN_PIX_ADAPTER",
        "SHOPMAN_EXPOSE_MOCK_CAPTURE",
    }
    assert status["SHOPMAN_ENVIRONMENT"] == "ok"  # o ensaio segue em staging
    assert status["EFI_SANDBOX"] == "ok"  # e a Efí, em sandbox


def test_valor_de_segredo_nunca_sai_na_tela():
    for spec, baseline in ((_today(), None), (_dia_d(), _today())):
        text, _ = delta.render(
            delta.evaluate(spec, baseline_spec=baseline), etapa="dia-d", has_baseline=baseline is not None
        )
        assert "EV[" not in text
        assert "<segredo>" in text


def test_spec_sem_componente_django_e_erro_de_leitura(tmp_path, capsys):
    path = tmp_path / "vivo.yaml"
    path.write_text("name: x\nservices:\n- name: storefront-nuxt\n", encoding="utf-8")

    assert delta.main(["--live-spec", str(path)]) == 2
    assert "não consegui ler o spec" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# As três listas andam juntas
# ---------------------------------------------------------------------------


def test_toda_trava_do_contrato_de_producao_esta_na_tabela():
    keys = {row.key for row in delta.DELTA}
    required = {
        *contract.FORBIDDEN_FLAGS,
        "SHOPMAN_ENVIRONMENT",
        "DJANGO_DEBUG",
        "DJANGO_SECURE_SSL_REDIRECT",
        "DJANGO_ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "DATABASE_URL",
        "REDIS_URL",
        # Ambiente do provedor (E022) e o que só o dia D liga.
        "EFI_SANDBOX",
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "FOCUS_NFE_ENVIRONMENT",
        "SHOPMAN_ADMIN_REQUIRE_2FA",
        "SHOPMAN_GO_LIVE",
    }
    assert required - keys == set()
    # Os adapters do contrato também, com o mesmo destino.
    rules = {row.key: row.dia_d for row in delta.DELTA}
    for key, expected in contract.PRODUCTION_ADAPTERS.items():
        assert key in rules, key
        assert rules[key].value == expected, key


def test_runbook_e_script_listam_as_mesmas_chaves_na_mesma_ordem():
    text = _RUNBOOK.read_text(encoding="utf-8")
    table = text.split("## A tabela", 1)[1].split("## Por que não dá", 1)[0]
    documented = re.findall(r"^\| `([A-Z0-9_]+)` \|", table, flags=re.MULTILINE)

    assert documented == [row.key for row in delta.DELTA]


def test_toda_linha_cai_num_check_do_production_readiness_alvo():
    # Ferramenta única: o modo alvo do production-readiness agrupa esta mesma
    # tabela em quatro checks. Grupo desconhecido seria linha que o gate não vê.
    assert {row.grupo for row in delta.DELTA} == {"profile", "money", "cutover", "in_place"}
