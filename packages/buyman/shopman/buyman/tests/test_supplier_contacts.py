import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from shopman.buyman.models import Supplier, SupplierContact

pytestmark = pytest.mark.django_db

Role = SupplierContact.Role


@pytest.fixture
def supplier():
    return Supplier.objects.create(
        ref="tamura",
        name="INDUSTRIA E COMERCIO DE PRODUTOS ALIMENTICIOS TAMURA LTDA",
        trade_name="Tamura",
        email="central@tamura.com.br",
    )


class TestSupplierDisplayName:
    def test_trade_name_wins_over_legal_name(self, supplier):
        assert supplier.display_name == "Tamura"
        assert str(supplier) == "Tamura"

    def test_falls_back_to_legal_name_then_ref(self):
        only_legal = Supplier.objects.create(ref="moinho", name="Moinho SP LTDA")
        assert only_legal.display_name == "Moinho SP LTDA"
        nameless = Supplier.objects.create(ref="sem-nome", name="")
        assert nameless.display_name == "sem-nome"


class TestContactInvariants:
    def test_contact_needs_email_or_phone(self, supplier):
        with pytest.raises(ValidationError):
            SupplierContact(supplier=supplier, name="Fantasma", role=Role.SALES).save()

    def test_check_constraint_guards_the_database_too(self, supplier):
        # Escrita crua, sem passar pelo save(): a invariante é do banco.
        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierContact.objects.bulk_create(
                [SupplierContact(supplier=supplier, name="Fantasma", role=Role.SALES)]
            )

    def test_first_of_a_role_becomes_primary(self, supplier):
        marcelo = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="marcelo@tamura.com.br",
        )
        assert marcelo.is_primary is True

    def test_first_of_each_role_is_independent(self, supplier):
        SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        rita = SupplierContact.objects.create(
            supplier=supplier, name="Rita", role=Role.FINANCE, email="r@tamura.com.br",
        )
        assert rita.is_primary is True

    def test_promoting_demotes_the_previous_one_of_the_same_role(self, supplier):
        marcelo = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        juliana = SupplierContact.objects.create(
            supplier=supplier, name="Juliana", role=Role.SALES, email="j@tamura.com.br",
        )
        assert juliana.is_primary is False

        juliana.is_primary = True
        juliana.save()

        marcelo.refresh_from_db()
        assert marcelo.is_primary is False
        assert SupplierContact.objects.get(pk=juliana.pk).is_primary is True

    def test_inactive_contact_cannot_be_primary(self, supplier):
        contact = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        contact.is_active = False
        with pytest.raises(ValidationError):
            contact.save()

    def test_phone_is_normalized_and_email_lowercased(self, supplier):
        contact = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES,
            email="  Marcelo@Tamura.com.BR ", phone="(43) 99999-8888",
        )
        assert contact.email == "marcelo@tamura.com.br"
        assert contact.phone == "+5543999998888"

    def test_first_name_is_what_greets(self, supplier):
        contact = SupplierContact(supplier=supplier, name="Marcelo Tanaka", email="m@t.com")
        assert contact.first_name == "Marcelo"


class TestPickAndResolve:
    def test_asked_role_wins(self, supplier):
        SupplierContact.objects.create(
            supplier=supplier, name="Geral", role=Role.GENERAL, email="g@tamura.com.br",
        )
        marcelo = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        assert SupplierContact.resolve(supplier, Role.SALES) == marcelo

    def test_falls_back_to_general_but_never_to_another_role(self, supplier):
        geral = SupplierContact.objects.create(
            supplier=supplier, name="Geral", role=Role.GENERAL, email="g@tamura.com.br",
        )
        SupplierContact.objects.create(
            supplier=supplier, name="Rita", role=Role.FINANCE, email="r@tamura.com.br",
        )
        assert SupplierContact.resolve(supplier, Role.SALES) == geral

        geral.is_active = False
        geral.is_primary = False
        geral.save()
        # Sobrou só o financeiro: pedido de compra NÃO cai nele.
        assert SupplierContact.resolve(supplier, Role.SALES) is None

    def test_primary_wins_inside_the_role(self, supplier):
        SupplierContact.objects.create(
            supplier=supplier, name="Ana", role=Role.SALES, email="a@tamura.com.br",
        )
        juliana = SupplierContact.objects.create(
            supplier=supplier, name="Juliana", role=Role.SALES, email="j@tamura.com.br",
            is_primary=True,
        )
        assert SupplierContact.resolve(supplier, Role.SALES) == juliana

    def test_requires_discards_who_lacks_that_reach(self, supplier):
        SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, phone="43999998888",
        )
        ana = SupplierContact.objects.create(
            supplier=supplier, name="Ana", role=Role.SALES, email="ana@tamura.com.br",
        )
        assert SupplierContact.resolve(supplier, Role.SALES, requires="email") == ana

    def test_inactive_is_never_picked(self, supplier):
        marcelo = SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        marcelo.is_primary = False
        marcelo.is_active = False
        marcelo.save()
        assert SupplierContact.resolve(supplier, Role.SALES) is None

    def test_pick_reads_a_loaded_list_without_touching_the_database(self, supplier, django_assert_num_queries):
        SupplierContact.objects.create(
            supplier=supplier, name="Marcelo", role=Role.SALES, email="m@tamura.com.br",
        )
        rows = list(supplier.contacts.all())
        with django_assert_num_queries(0):
            assert SupplierContact.pick(rows, Role.SALES).name == "Marcelo"
