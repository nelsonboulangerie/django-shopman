"""No Gestor, o gerente é SELECIONADO, como no PDV — não digitado.

Medido em 21/09/2026, cancelando pedido do iFood durante a homologação: o diálogo
canônico (``OperatorManagerAuth``) chegava sem lista e caía no campo livre. O
gerente tinha de digitar o próprio nome no meio de um prazo de oito minutos, e
nome digitado erra — o servidor resolve a assinatura por ``username``.
"""
import pytest

from shopman.backstage.projections import order_queue


@pytest.fixture
def gerentes(db):
    from django.contrib.auth.models import Permission, User

    perm = Permission.objects.get(codename="adjust_shift")
    joyce = User.objects.create_user("joyce", first_name="Joyce", last_name="Nogueira", is_staff=True)
    joyce.user_permissions.add(perm)
    pablo = User.objects.create_user("pablo", first_name="Pablo", is_staff=True)
    pablo.user_permissions.add(perm)
    return joyce, pablo


@pytest.mark.django_db
def test_detalhe_do_pedido_traz_a_lista_de_quem_assina(gerentes):
    joyce, pablo = gerentes

    options = order_queue._approver_options(pablo)

    assert {"username": "joyce", "name": "Joyce Nogueira"} in options


@pytest.mark.django_db
def test_quem_opera_nao_aparece_para_se_autorizar(gerentes):
    """A segunda assinatura existe para haver duas pessoas."""
    joyce, pablo = gerentes

    assert all(o["username"] != "pablo" for o in order_queue._approver_options(pablo))


@pytest.mark.django_db
def test_lista_publica_so_nome_e_username(gerentes):
    """Lida por qualquer sessão de gestor: o que ela publica vira superfície."""
    joyce, pablo = gerentes

    for option in order_queue._approver_options(pablo):
        assert set(option) == {"username", "name"}
