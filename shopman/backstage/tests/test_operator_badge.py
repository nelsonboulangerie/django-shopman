"""Crachá do operador: codificação Code-128, projection e emissão pelo Admin.

O que este arquivo protege, em ordem de gravidade: um código de barras errado é um
crachá que não abre o PDV e ninguém descobre por quê (o leitor simplesmente não bipa);
um token que vaza deixa de ser credencial; e uma emissão sem permissão dá crachá a
quem não devia.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.presentation.barcode import (
    _PATTERNS,
    BarcodeError,
    code128_svg,
    code128_width_mm,
    encode_code128_b,
)
from shopman.backstage.projections.operator_badge import build_operator_badge

User = get_user_model()

TOKEN = "8b52e12e9827"  # 12 hex: o que `issue_badge` sorteia

# Entrada do vetor de ouro. NÃO é o `TOKEN` de propósito: ela tem 24 caracteres
# porque foi ESSA string que se conferiu, símbolo a símbolo, contra o `zint`.
#
# O crachá encolheu para 12 caracteres depois (largura de barra no papel), e a
# tentação era regerar o vetor para o token novo — mas um vetor de ouro gerado
# pelo próprio código sob teste não prova nada: viraria "meu código concorda
# comigo". A evidência independente vale pela string que foi verificada, e o
# comprimento do crachá é outra decisão.
GOLDEN_INPUT = "8b52e12e9827c01382e7b808"

# Vetor de ouro: a saída para GOLDEN_INPUT, conferida contra o `zint` (implementação
# independente, símbolo 60 = Code 128 com Set C suprimido — a mesma estratégia daqui).
# START, dados e dígito verificador bateram símbolo a símbolo em 84 casos. Se este
# vetor mudar, alguém mexeu na codificação e o crachá impresso para de ser lido.
GOLDEN = (
    "11010010000111010011001001000011011011100100110011100101011001000010011100110110"
    "01110010101100100001110010110011101001100110011100101110110111010000101100100111"
    "01100100111001101100101110011101001100110011100101011001000011101101110100100001"
    "10111010011001001110110011101001100111010111101100011101011"
)


class TestCode128:
    def test_golden_vector(self):
        assert encode_code128_b(GOLDEN_INPUT) == GOLDEN

    def test_starts_with_set_b_and_ends_with_stop(self):
        bits = encode_code128_b(TOKEN)
        start_b, stop = _PATTERNS[104], _PATTERNS[106]
        assert bits.startswith(_widths_to_bits(start_b))
        assert bits.endswith(_widths_to_bits(stop))

    def test_symbol_layout_is_11_modules_plus_13_for_stop(self):
        """Todo símbolo tem 11 módulos; só o STOP tem 13. É a régua do padrão."""
        bits = encode_code128_b(TOKEN)
        assert len(bits) == 11 * (1 + len(TOKEN) + 1) + 13

    def test_round_trip_decodes_back_to_the_token(self):
        """Decodificar de volta é o que um leitor faz — se não voltar, o crachá é papel."""
        assert _decode(encode_code128_b(TOKEN)) == TOKEN

    @pytest.mark.parametrize(
        "data", ["a", "abcdef", "Nelson Boulangerie", "0000000000000000000000000", TOKEN]
    )
    def test_round_trip_survives_varied_data(self, data):
        assert _decode(encode_code128_b(data)) == data

    def test_checksum_is_position_weighted(self):
        """Trocar dois caracteres de lugar TEM de mudar o verificador.

        É o ponto do dígito ponderado: sem ele uma leitura embaralhada passaria como
        válida e o PDV destravaria para a pessoa errada.
        """
        assert encode_code128_b("ab") != encode_code128_b("ba")

    def test_rejects_characters_outside_the_subset(self):
        with pytest.raises(BarcodeError):
            encode_code128_b("café")  # 'é' não existe no Code-128 B
        with pytest.raises(BarcodeError):
            encode_code128_b("")

    def test_svg_carries_the_quiet_zone(self):
        """Zona muda comida = leitor não acha o começo. É o erro de impressão clássico."""
        svg = code128_svg(TOKEN, module_mm=0.25, quiet_modules=10)
        assert 'width="46.7500mm"' in svg
        # A primeira barra começa depois dos 10 módulos de margem clara.
        assert '<rect x="2.5000"' in svg

    def test_width_fits_a_card_sized_badge(self):
        """Tem que caber num crachá tamanho cartão (85,6mm). Se passar, não cabe.

        É o guarda que amarra as duas pontas do mesmo orçamento: comprimento do
        token e largura da barra. Foi ele que reprovou quando a barra subiu para
        0,4233mm com o token ainda em 24 caracteres — e estava certo, porque
        135mm não vai no bolso de ninguém.
        """
        assert code128_width_mm(TOKEN) <= 85.6


class TestBadgeProjection:
    def test_builds_a_printable_badge(self):
        badge = build_operator_badge(
            operator_name="Ana Costa", operator_username="ana", token=TOKEN
        )
        assert badge.operator_name == "Ana Costa"
        assert badge.token == TOKEN
        assert badge.barcode_svg.startswith("<svg")
        assert badge.width_mm == pytest.approx(79.2, abs=0.1)

    def test_falls_back_to_username_when_there_is_no_name(self):
        badge = build_operator_badge(operator_name="  ", operator_username="ana", token=TOKEN)
        assert badge.operator_name == "ana"


@pytest.fixture
def _shop(db):
    """Sem Shop o OnboardingMiddleware manda todo /admin/ para o formulário do Shop."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Loja")


@pytest.mark.django_db
@pytest.mark.usefixtures("_shop")
class TestIssueBadgeFromAdmin:
    def _manager(self):
        user = User.objects.create_user(
            username="gerente", password="x", is_staff=True, is_superuser=True
        )
        return user

    def _operator(self):
        user = User.objects.create_user(username="ana", password="x", is_staff=True)
        PinCredential.set_for(user, "4321")
        return user

    def test_issuing_stores_only_the_digest_and_shows_the_token_once(self, client):
        manager, operator = self._manager(), self._operator()
        client.force_login(manager)
        cred = operator.pin_credential
        assert cred.badge_hash is None

        response = client.post(
            reverse("admin:doorman_pincredential_changelist"),
            {"action": "issue_badge", "_selected_action": [str(cred.pk)]},
            follow=True,
        )
        assert response.status_code == 200

        cred.refresh_from_db()
        assert cred.badge_hash, "o crachá foi emitido"
        page = response.content.decode()
        # A página mostra o token (e volta a mostrar dentro da janela)...
        token = _token_from_page(page)
        assert PinCredential.resolve_by_badge(token) == operator
        # ...e o digest guardado nunca é o token em texto.
        assert token not in cred.badge_hash

        # Recarregar DENTRO da janela repete o mesmo crachá, de propósito:
        # impressora que emperra não pode custar uma credencial. Reexibir não é
        # reemitir — o digest não muda, e quem emitiu já tinha visto o código.
        # A expiração é coberta em `test_operator_badge_reprint.py`.
        again = client.get(reverse("admin_console_operator_badge"))
        assert token in again.content.decode()
        cred.refresh_from_db()
        assert PinCredential.resolve_by_badge(token) == operator

    def test_issuing_again_invalidates_the_previous_badge(self, client):
        manager, operator = self._manager(), self._operator()
        client.force_login(manager)
        cred = operator.pin_credential

        first = PinCredential.issue_badge(operator)
        client.post(
            reverse("admin:doorman_pincredential_changelist"),
            {"action": "issue_badge", "_selected_action": [str(cred.pk)]},
            follow=True,
        )
        assert PinCredential.resolve_by_badge(first) is None

    def test_revoking_stops_the_badge_from_resolving(self, client):
        manager, operator = self._manager(), self._operator()
        client.force_login(manager)
        token = PinCredential.issue_badge(operator)

        client.post(
            reverse("admin:doorman_pincredential_changelist"),
            {"action": "revoke_badge", "_selected_action": [str(operator.pin_credential.pk)]},
            follow=True,
        )
        assert PinCredential.resolve_by_badge(token) is None

    def test_issuing_for_two_operators_at_once_is_refused(self, client):
        """Dois de uma vez esconderia um dos códigos para sempre."""
        manager = self._manager()
        first = self._operator()
        second = User.objects.create_user(username="bia", password="x", is_staff=True)
        PinCredential.set_for(second, "4321")
        client.force_login(manager)

        client.post(
            reverse("admin:doorman_pincredential_changelist"),
            {
                "action": "issue_badge",
                "_selected_action": [str(first.pin_credential.pk), str(second.pin_credential.pk)],
            },
            follow=True,
        )
        first.pin_credential.refresh_from_db()
        second.pin_credential.refresh_from_db()
        assert first.pin_credential.badge_hash is None
        assert second.pin_credential.badge_hash is None

    def test_the_page_is_closed_to_staff_without_manage_operators(self, client):
        plain = User.objects.create_user(username="balconista", password="x", is_staff=True)
        client.force_login(plain)
        response = client.get(reverse("admin_console_operator_badge"))
        assert response.status_code in (302, 403)


# ── auxiliares ───────────────────────────────────────────────────────────────

_LOOKUP = {pattern: value for value, pattern in enumerate(_PATTERNS)}


def _widths_to_bits(widths: str) -> str:
    return "".join(("1" if i % 2 == 0 else "0") * int(w) for i, w in enumerate(widths))


def _bits_to_widths(bits: str) -> str:
    out, index = [], 0
    while index < len(bits):
        run = 1
        while index + run < len(bits) and bits[index + run] == bits[index]:
            run += 1
        out.append(str(run))
        index += run
    return "".join(out)


def _decode(bits: str) -> str:
    """Decodificador mínimo — faz o papel do leitor e confere o verificador."""
    symbols = [
        _LOOKUP[_bits_to_widths(bits[i : i + 11])] for i in range(0, len(bits) - 13, 11)
    ]
    start, *data, checksum = symbols
    assert start == 104, "não começa em Set B"
    expected = (start + sum(pos * v for pos, v in enumerate(data, start=1))) % 103
    assert checksum == expected, "dígito verificador não confere"
    return "".join(chr(v + 32) for v in data)


def _token_from_page(html: str) -> str:
    import re

    match = re.search(r"\b[0-9a-f]{12}\b", html)
    assert match, "a página deveria mostrar o token uma vez"
    return match.group(0)
