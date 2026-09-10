"""As três ações de estado do Admin: quem alcança, e por qual método.

O Unfold monta as URLs de ``actions_row`` embrulhadas **apenas** em
``admin_site.admin_view`` — que é ``is_active and is_staff``, e **zero permissão de
modelo**. O decorador só confere permissão quando recebe ``permissions=``, e nenhuma
ação do repositório usava. Somando: **qualquer staff** alcançava estorno, liberação
de reserva e execução de diretiva pela URL, mesmo sem ver a tela.

E nenhuma delas conferia o método. ``actions_row`` é renderizada como ``<a href>``,
então o corpo executava em **GET** — e ``SESSION_COOKIE_SAMESITE = "Lax"`` **envia**
o cookie em navegação top-level GET. Um link mandado num WhatsApp, clicado pelo gestor
logado, disparava a ação e redirecionava para a lista como se nada tivesse acontecido.

Este arquivo cobre as duas metades, para as três ações:

- **quem** — staff sem a permissão do modelo leva 403;
- **como** — GET só desenha o diálogo; o efeito acontece no POST.

⚠️ O que este arquivo NÃO prova, de propósito: que a fronteira de dinheiro do RBAC
está fechada. O ``setup_groups`` diz que "payman é do Dono", e o Gerente continua
reexecutando um directive de tópico ``payment.refund`` pela tela de Diretivas. Isso é
decisão do dono (pergunta 1 do WP-09) e cai na onda 4.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.orderman.models import Directive
from shopman.payman.models import PaymentIntent
from shopman.payman.service import PaymentService
from shopman.stockman.models import Hold, HoldStatus

from shopman.shop.models import Shop


@pytest.fixture
def _loja(db):
    return Shop.objects.create(name="Loja")


def _staff(username: str, *perms: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)


# ── Os três alvos, com o estado que a ação mudaria ───────────────────────────


def _intent_capturado(amount_q: int = 10000) -> PaymentIntent:
    intent = PaymentService.create_intent(f"ORD-GATE{PaymentIntent.objects.count()}", amount_q, "pix")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return PaymentService.get(intent.ref)


def _hold_ativo() -> Hold:
    """Reserva ATIVA, montada direto no modelo.

    O que se prova aqui é o portão do Admin, não a mecânica do estoque — passar
    pelo `stock.hold` traria a política de disponibilidade para dentro de um teste
    de permissão, e o dia em que ela mudasse este arquivo quebraria por um motivo
    que não tem nada a ver com o que ele guarda.
    """
    from decimal import Decimal

    from shopman.stockman.models import Position, PositionKind, Quant

    posicao, _ = Position.objects.get_or_create(
        ref="gate-vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    quant = Quant.objects.create(sku="SKU-GATE", position=posicao, _quantity=Decimal("10"))
    return Hold.objects.create(
        sku="SKU-GATE",
        quant=quant,
        quantity=Decimal("1"),
        target_date=timezone.localdate(),
        status=HoldStatus.PENDING,
    )


def _directive_em_fila() -> Directive:
    return Directive.objects.create(topic="payment.refund", payload={}, status="queued")


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
@pytest.mark.parametrize(
    ("nome", "url", "permissao"),
    [
        ("refund", "/admin/payman/paymentintent/{pk}/refund/", "payman.view_paymentintent"),
        ("release_hold", "/admin/stockman/hold/{pk}/release-hold/", "stockman.view_hold"),
    ],
)
def test_staff_sem_a_permissao_do_modelo_nao_alcanca_a_URL(client, nome, url, permissao):
    """Hoje executava: `admin_view` só pergunta se a pessoa é da casa."""
    alvo = {"refund": _intent_capturado, "release_hold": _hold_ativo}[nome]()
    client.force_login(_staff(f"sem-perm-{nome}"))

    resposta = client.get(url.format(pk=alvo.pk))

    assert resposta.status_code == 403, (
        f"{nome}: staff sem {permissao} alcançou a ação de estado pela URL"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_GET_nao_estorna_mais_e_so_desenha_o_dialogo(client):
    """O link clicado no WhatsApp: cookie Lax vai junto, e antes o dinheiro voltava."""
    intent = _intent_capturado(10000)
    client.force_login(_staff("dono-ish", "payman.view_paymentintent"))

    resposta = client.get(f"/admin/payman/paymentintent/{intent.pk}/refund/")

    assert resposta.status_code == 200
    assert PaymentService.refunded_total(intent.ref) == 0, "GET estornou"


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_POST_confirmado_estorna(client):
    """E o caminho legítimo continua funcionando — senão o conserto seria uma trava."""
    intent = _intent_capturado(10000)
    client.force_login(_staff("dono-ish2", "payman.view_paymentintent"))

    resposta = client.post(
        f"/admin/payman/paymentintent/{intent.pk}/refund/", {"_form_submitted": "true"}
    )

    assert resposta.status_code in (200, 302)
    assert PaymentService.refunded_total(intent.ref) == 10000


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_GET_nao_libera_mais_a_reserva(client):
    hold = _hold_ativo()
    client.force_login(_staff("cozinha-ish", "stockman.view_hold"))

    resposta = client.get(f"/admin/stockman/hold/{hold.pk}/release-hold/")

    assert resposta.status_code == 200
    assert Hold.objects.get(pk=hold.pk).status == hold.status, "GET liberou a reserva"


@pytest.mark.django_db
def test_o_admin_de_diretivas_nao_oferece_execucao():
    """O Admin da casa não OPERA — e forçar diretiva é operação.

    Decisão do dono em 11/07/2026: Admin é CRUD, config, relatórios e auditoria;
    execução operacional é exclusiva das superfícies Nuxt, e página Admin de
    operação é GET-only por desenho. Mesmo corte que fez o console de produção
    virar leitura (commit `01cf765f`), com os POSTs REMOVIDOS em vez de
    repermissionados.

    A remoção custa zero capacidade: a fila roda sozinha (`process_directives`),
    directive que esgota tentativas vira `OperatorAlert` (`check_directive_health`,
    exigido pela ADR-003), e a emergência tem `manage.py process_directives`.

    ⚠️ A asserção é sobre a ROTA e a OFERTA, não sobre um status HTTP: o Admin do
    Django casa `<path:object_id>`, então a URL antiga vira "diretiva com id
    '1/execute-row' não existe" e termina em 200 na changelist. Um teste de status
    aqui passaria por acidente mesmo com o botão de volta.
    """
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[Directive]

    oferecidas = (
        list(getattr(model_admin, "actions", None) or [])
        + list(getattr(model_admin, "actions_row", None) or [])
        + list(getattr(model_admin, "actions_detail", None) or [])
        + list(getattr(model_admin, "actions_submit_line", None) or [])
    )
    assert not [nome for nome in oferecidas if "execute" in str(nome)], (
        f"o Admin voltou a oferecer execução de diretiva: {oferecidas}"
    )

    caminhos = [str(getattr(u, "pattern", "")) for u in model_admin.get_urls()]
    assert not [c for c in caminhos if "execute" in c], (
        f"a rota de executar diretiva voltou ao Admin: {caminhos}"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_a_maquinaria_de_executar_diretiva_saiu_junto():
    """Zero-residuals: o helper que rodava o handler não fica órfão no arquivo."""
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[Directive]

    assert not hasattr(model_admin, "_execute_directive"), (
        "`_execute_directive` ficou para trás — código que ninguém chama, "
        "pronto para alguém religar sem ler a régua."
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_a_tela_de_diretivas_continua_inteira_como_auditoria(client):
    """Remover a execução não pode custar a LEITURA — é para isso que a tela existe.

    Assert-positivo do outro lado da decisão: a régua tira operação do Admin e
    mantém CRUD, relatórios e auditoria.
    """
    directive = _directive_em_fila()
    client.force_login(User.objects.create_superuser("auditor-diretiva", "a@test.com", "pw"))

    assert client.get("/admin/orderman/directive/").status_code == 200
    assert client.get(f"/admin/orderman/directive/{directive.pk}/change/").status_code == 200
    # O histórico é auditoria, e continua alcançável.
    assert client.get(f"/admin/orderman/directive/{directive.pk}/history-action/").status_code in (200, 302)


# ── Import de catálogo ───────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_caixa_nao_importa_catalogo(client):
    """O mixin devolve True quando o código de permissão não é definido.

    E o projeto não definia — `import_export/admin.py:127`. Um usuário do grupo
    Caixa POSTava um CSV em /admin/offerman/product/import/ e reescrevia preço,
    publicação e vendabilidade de TODO o catálogo por SKU, sem dry-run visível para
    o gestor e sem trilha agregada.
    """
    client.force_login(_staff("caixa-ish", "offerman.view_product"))

    assert client.get("/admin/offerman/product/import/").status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_quem_edita_o_catalogo_importa(client):
    """O recorte reusa a permissão que já existe: importar é editar em massa.

    Gerente e Admin de Catálogo têm `change_product`; Caixa e Cozinha não. Zero
    mudança em `setup_groups`.
    """
    client.force_login(_staff("gerente-cat", "offerman.view_product", "offerman.change_product"))

    assert client.get("/admin/offerman/product/import/").status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("_loja")
def test_exportar_e_ler(client):
    """Exportar continua alcançável por quem já podia LER o catálogo."""
    client.force_login(_staff("cozinha-cat", "offerman.view_product"))

    assert client.get("/admin/offerman/product/export/").status_code == 200


# ── A chave do 2FA ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_chave_do_TOTP_nao_aparece_na_tela_do_dispositivo():
    """`OTP_ADMIN_HIDE_SENSITIVE_DATA` era `False` — o default da django-otp.

    Quem lê a chave de outro usuário gera os códigos dele, o que ANULA o step-up de
    2FA como controle de segurança: o segundo fator vira o primeiro, para quem já
    está dentro. Hoje só superusuário alcança a tela, mas o hub de configurações já
    oferece o card — a intenção é abrir.
    """
    from django.contrib import admin as django_admin
    from django_otp.plugins.otp_totp.models import TOTPDevice

    dono = User.objects.create_superuser("totp-dono", "t@test.com", "pw")
    dispositivo = TOTPDevice.objects.create(user=dono, name="celular", confirmed=True)
    model_admin = django_admin.site._registry[TOTPDevice]

    campos = {
        campo
        for _titulo, opcoes in model_admin.get_fieldsets(None, dispositivo)
        for campo in opcoes["fields"]
    }

    assert "key" not in campos, "o segredo TOTP está na tela"
    assert "qrcode_link" not in campos, "o QR de enrollment está na tela"


@pytest.mark.django_db
def test_os_titulos_do_TOTP_estao_em_portugues():
    """A tradução vive num `get_fieldsets`, e não num atributo `fieldsets`.

    O `TOTPDeviceAdmin` do django_otp sobrescreve `get_fieldsets()` e ignora
    `self.fieldsets` — então o atributo que existia aqui era código morto, e a tela
    seguiu em inglês desde sempre. Ninguém percebeu porque a tela é superusuário-only.
    """
    from django.contrib import admin as django_admin
    from django_otp.plugins.otp_totp.models import TOTPDevice

    model_admin = django_admin.site._registry[TOTPDevice]

    titulos = [titulo for titulo, _opcoes in model_admin.get_fieldsets(None, None)]

    assert "Identificação" in titulos
    assert "Identity" not in titulos


# ── Recado para a onda 4 ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_permissions_change_mataria_duas_das_tres_acoes():
    """⚠️ A onda 4 NÃO pode simplesmente trocar `["view"]` por `["change"]`.

    O WP-09 planeja apertar as três ações para a permissão certa. Duas delas não
    aceitam a forma curta: os admins de `PaymentIntent` e `Hold` sobrescrevem
    `has_change_permission` para `False` **incondicionalmente** — são modelos que
    não se editam à mão —, e o decorador do Unfold chama o MÉTODO quando a permissão
    vem sem ponto. A ação morreria até para superusuário.

    A forma que funciona é a pontuada (`permissions=["stockman.change_hold"]`), que
    o Unfold confere direto com `request.user.has_perm`.

    Este teste guarda o fato, não o desenho: se algum dia esses admins passarem a
    permitir change, ele avisa que a nota nos dois arquivos ficou velha.
    """
    from django.contrib import admin as django_admin
    from shopman.stockman.models import Hold as HoldModel

    class _Superusuario:
        user = User(is_active=True, is_staff=True, is_superuser=True)

    for modelo in (PaymentIntent, HoldModel):
        model_admin = django_admin.site._registry[modelo]
        assert model_admin.has_change_permission(_Superusuario()) is False, (
            f"{modelo.__name__}: `has_change_permission` deixou de ser sempre False — "
            "a nota sobre a onda 4 nos admins do payman e do stockman precisa ser revista."
        )
        assert model_admin.has_view_permission(_Superusuario()) is True
