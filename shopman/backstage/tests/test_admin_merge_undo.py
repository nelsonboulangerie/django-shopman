"""Desfazer a unificação de cadastros pela tela — a janela de 24h com uma porta.

O merge é reversível por 24h desde sempre (``MergeService.undo``), mas o desfazer
só existia pelo shell do Django. Este arquivo guarda a porta: que ela desfaz
dentro do prazo, que ela RECUSA com frase de gente fora dele, que ela não engana
sobre a fidelidade, e que quem não é gestor nem vê nem executa.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
from shopman.guestman.contrib.merge.service import MergeService
from shopman.guestman.models import ContactPoint, Customer, PriceTier

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/customer_merge/mergeaudit/"


def _undo_url(audit: MergeAudit) -> str:
    return f"{CHANGELIST}{audit.pk}/undo/"


@pytest.fixture
def _loja():
    """Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja."""
    return Shop.objects.create(name="Nelson")


@pytest.fixture
def tier():
    return PriceTier.objects.create(ref="regular", name="Regular", is_default=True, priority=0)


@pytest.fixture
def unificados(tier):
    """Dois cadastros da MESMA pessoa, já unificados — como o balcão os deixa."""
    source = Customer.objects.create(
        ref="SRC-UNDO",
        first_name="Maria",
        last_name="Souza",
        phone="+5543911111111",
        price_tier=tier,
    )
    target = Customer.objects.create(
        ref="TGT-UNDO",
        first_name="Maria",
        last_name="Silva",
        phone="+5543922222222",
        price_tier=tier,
    )
    result = MergeService.merge(source, target, {"staff_override": True}, actor="pdv:fran")
    return MergeAudit.objects.get(pk=result.audit_id)


def _usuario(username: str, *perms: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)  # recarrega: cache de permissão


def _gestor(username: str = "gerente") -> User:
    return _usuario(username, "customer_merge.view_mergeaudit", "shop.manage_customers")


# ── 1. Dentro da janela: os cadastros voltam ao que eram ─────────────────────


def test_desfazer_dentro_da_janela_devolve_os_dois_cadastros(client, _loja, unificados):
    """O caso que dá nome à tela: unificou errado, desfez, e a vida segue."""
    telefone_do_absorvido = "+5543911111111"
    assert not Customer.objects.get(ref="SRC-UNDO").is_active
    assert ContactPoint.objects.filter(
        value_normalized=telefone_do_absorvido, customer__ref="TGT-UNDO"
    ).exists()

    client.force_login(_gestor())
    resposta = client.post(_undo_url(unificados), {"_form_submitted": "true"})

    assert resposta.status_code in (200, 302)
    assert Customer.objects.get(ref="SRC-UNDO").is_active, "o cadastro absorvido não voltou"
    assert ContactPoint.objects.filter(
        value_normalized=telefone_do_absorvido, customer__ref="SRC-UNDO"
    ).exists(), "o telefone não voltou para o dono"
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.REVERTED
    assert unificados.reverted_by == "admin:gerente"


def test_pelo_dialogo_HTMX_a_resposta_manda_o_navegador_navegar(client, _loja, unificados):
    """Sem isto a mensagem nunca chega em quem clicou.

    O diálogo do Unfold posta por HTMX com ``hx-select="#dialog-form"``. Um
    redirect comum é seguido pelo próprio HTMX, que não acha esse seletor na
    changelist e ESVAZIA o modal: o desfazer acontece, a mensagem é gravada, e a
    tela não muda nem mostra nada. ``HX-Redirect`` é o que fecha a promessa.
    """
    client.force_login(_gestor("gerente-htmx"))

    resposta = client.post(
        _undo_url(unificados), {"_form_submitted": "true"}, headers={"hx-request": "true"}
    )

    assert resposta.status_code == 204
    assert resposta["HX-Redirect"] == CHANGELIST
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.REVERTED


def test_a_recusa_pelo_dialogo_HTMX_tambem_navega(client, _loja, unificados):
    """A recusa é justamente a mensagem que não pode ficar presa numa resposta."""
    MergeAudit.objects.filter(pk=unificados.pk).update(
        merged_at=timezone.now() - timedelta(hours=MergeAudit.UNDO_WINDOW_HOURS + 1)
    )
    client.force_login(_gestor("gerente-htmx-2"))

    resposta = client.post(
        _undo_url(unificados), {"_form_submitted": "true"}, headers={"hx-request": "true"}
    )

    assert resposta.status_code == 204
    assert resposta["HX-Redirect"] == CHANGELIST
    texto = client.get(CHANGELIST).content.decode()
    assert "prazo" in texto.lower() and "manual" in texto.lower()


def test_GET_nao_desfaz_nada_e_so_desenha_o_dialogo(client, _loja, unificados):
    """O link clicado num WhatsApp: cookie Lax vai junto, e nada pode acontecer."""
    client.force_login(_gestor())

    resposta = client.get(_undo_url(unificados))

    assert resposta.status_code == 200
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.COMPLETED, "GET desfez a unificação"
    assert not Customer.objects.get(ref="SRC-UNDO").is_active


# ── 2. Fora da janela: recusa com frase de gente ─────────────────────────────


def test_fora_da_janela_recusa_com_frase_de_gente(client, _loja, unificados):
    """Prazo vencido não é exceção crua nem 500: é uma frase que diz o que fazer."""
    MergeAudit.objects.filter(pk=unificados.pk).update(
        merged_at=timezone.now() - timedelta(hours=MergeAudit.UNDO_WINDOW_HOURS + 1)
    )

    client.force_login(_gestor())
    resposta = client.post(_undo_url(unificados), {"_form_submitted": "true"}, follow=True)

    assert resposta.status_code == 200
    texto = resposta.content.decode()
    assert "prazo" in texto.lower()
    assert "manual" in texto.lower(), "a recusa não diz o que resta fazer"
    assert "UNDO_FAILED" not in texto, "o código do Core vazou para a tela"
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.COMPLETED
    assert not Customer.objects.get(ref="SRC-UNDO").is_active


# ── 3. Duas vezes: a segunda tem mensagem própria ────────────────────────────


def test_desfazer_duas_vezes_recusa_com_mensagem_propria(client, _loja, unificados):
    """Dois gestores na mesma linha, ou um duplo-clique: a segunda vez explica."""
    client.force_login(_gestor())
    client.post(_undo_url(unificados), {"_form_submitted": "true"})

    resposta = client.post(_undo_url(unificados), {"_form_submitted": "true"}, follow=True)

    texto = resposta.content.decode()
    assert "já foi desfeita" in texto, f"a segunda recusa não tem frase própria: {texto[:0]}"
    assert "admin:gerente" in texto, "a recusa não diz quem desfez"
    assert "UNDO_FAILED" not in texto
    # E o estado não regrediu: continua desfeita uma vez só.
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.REVERTED
    assert Customer.objects.get(ref="SRC-UNDO").is_active


# ── 4. A tela conta o prazo e não engana sobre a fidelidade ──────────────────


def test_a_lista_mostra_quanto_tempo_ainda_resta(client, _loja, unificados):
    """O prazo é o dado mais perecível da tela: quem olha a lista já o vê."""
    client.force_login(_gestor())

    texto = client.get(CHANGELIST).content.decode()

    assert "SRC-UNDO" in texto and "TGT-UNDO" in texto
    assert "faltam" in texto, "a lista não diz quanto tempo resta"


def test_a_lista_mostra_prazo_encerrado_quando_a_janela_fechou(client, _loja, unificados):
    MergeAudit.objects.filter(pk=unificados.pk).update(
        merged_at=timezone.now() - timedelta(hours=MergeAudit.UNDO_WINDOW_HOURS + 1)
    )
    client.force_login(_gestor())

    texto = client.get(CHANGELIST).content.decode()

    assert "prazo encerrado" in texto
    assert "faltam" not in texto


def test_o_dialogo_avisa_que_a_fidelidade_nao_volta_antes_de_confirmar(client, _loja, unificados):
    """A metade que o ``undo`` NÃO faz precisa ser lida antes do clique, não depois."""
    client.force_login(_gestor())

    texto = client.get(_undo_url(unificados)).content.decode()

    assert "fidelidade" in texto.lower(), "o diálogo não fala da fidelidade"
    assert "NÃO volta" in texto
    assert "faltam" in texto and "até" in texto, "o diálogo não mostra o prazo restante"


# ── 5. Quem não é gestor não vê nem executa ──────────────────────────────────


def test_quem_nao_tem_a_leitura_nao_abre_a_tela(client, _loja, unificados):
    client.force_login(_usuario("caixa-sem-nada"))

    assert client.get(CHANGELIST).status_code == 403


def test_quem_so_le_a_trilha_nao_desfaz(client, _loja, unificados):
    """Abrir a tela e AGIR são duas perguntas — e esta pessoa só respondeu a primeira."""
    client.force_login(_usuario("conferente", "customer_merge.view_mergeaudit"))

    assert client.get(CHANGELIST).status_code == 200
    assert client.post(_undo_url(unificados), {"_form_submitted": "true"}).status_code == 403
    unificados.refresh_from_db()
    assert unificados.status == MergeStatus.COMPLETED


def test_quem_so_le_a_trilha_nao_ve_o_botao_de_desfazer(client, _loja, unificados):
    """Placa de aberto em porta trancada é pior que porta que falta."""
    client.force_login(_usuario("conferente-2", "customer_merge.view_mergeaudit"))

    texto = client.get(CHANGELIST).content.decode()

    assert "Desfazer unificação" not in texto


def test_o_gestor_ve_o_botao(client, _loja, unificados):
    """Contrapeso: sem ele, um filtro fechado demais passaria verde escondendo tudo."""
    client.force_login(_gestor("gerente-2"))

    assert "Desfazer unificação" in client.get(CHANGELIST).content.decode()


# ── A tela é trilha: não se edita, não se apaga ──────────────────────────────


def test_a_auditoria_nao_se_edita_nem_se_apaga(client, _loja, unificados):
    """Editar a auditoria à mão apagaria o rastro que ela existe para guardar."""
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[MergeAudit]
    request = type("R", (), {"user": _gestor("gerente-3"), "method": "GET"})()

    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
