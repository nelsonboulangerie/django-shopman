"""Tests for shopman.utils admin utilities."""



class TestUnfoldBadge:
    """unfold_badge() XSS safety and behavior."""

    def test_basic_badge(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = unfold_badge("Active", "green")
        assert "Active" in str(result)
        assert "green" in str(result)

    def test_html_in_text_is_escaped(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge('<script>alert("xss")</script>'))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_in_text_with_angle_brackets(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge("test<br>break"))
        assert "<br>" not in result
        assert "&lt;br&gt;" in result

    def test_unknown_color_falls_back_to_the_neutral_badge(self):
        """Cor desconhecida não inventa cor: cai no badge neutro do Unfold.

        A asserção antiga era `bg-base-100`, classe da tabela de cores que este
        módulo COPIAVA do Unfold. Agora quem desenha é `unfold/helpers/label.html`,
        e o neutro dele é `bg-base-500/8` — o que o teste garante é a intenção
        (neutro, sem semântica de cor), não o valor que o Unfold escolheu.
        """
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge("Test", "nonexistent_color"))

        assert "bg-base-500/8" in result
        for semantic in ("bg-red-100", "bg-green-100", "bg-blue-100", "bg-orange-100"):
            assert semantic not in result

    def test_badge_numeric_renders_the_value_with_its_color(self):
        """Número sai no badge, com a cor pedida.

        A asserção antiga exigia ausência de `uppercase`, porque a variante
        numérica existia só para tirar a caixa alta. Isso nunca mudou um pixel:
        dígitos e sinais não têm caixa. Sobrou o que importa — o valor aparece e a
        cor é a semântica certa do Unfold.
        """
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge_numeric

        result = str(unfold_badge_numeric("42", "blue"))

        assert "42" in result
        assert "bg-blue-100" in result

    def test_badge_numeric_xss(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge_numeric

        result = str(unfold_badge_numeric('<img src=x onerror="alert(1)">'))
        assert "<img" not in result
        assert "&lt;img" in result


class TestAutofillInlineMixin:
    """AutofillInlineMixin with special characters in mapping."""

    def test_mixin_has_autofill_fields_default(self):
        from shopman.utils.admin.mixins import AutofillInlineMixin

        assert AutofillInlineMixin.autofill_fields == {}

    def test_mapping_with_special_characters(self):
        import json

        mapping = {"unit_price_q": "base_price_q", "desc": 'value "with" quotes'}
        serialized = json.dumps(mapping)
        parsed = json.loads(serialized)
        assert parsed["desc"] == 'value "with" quotes'

    def test_mapping_with_unicode(self):
        import json

        mapping = {"descricao": "descricao_completa", "preco": "preco_unitario"}
        serialized = json.dumps(mapping, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["descricao"] == "descricao_completa"

    def test_empty_mapping_no_js_injection(self):
        from shopman.utils.admin.mixins import AutofillInlineMixin

        mixin = AutofillInlineMixin()
        assert not mixin.autofill_fields


class TestEnrichedAutocompleteJsonView:
    """EnrichedAutocompleteJsonView enriches results from ModelAdmin config."""

    def test_includes_extra_fields_from_model_admin(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.base_price_q = 500
        type(obj).__name__ = "Product"

        model_admin = MagicMock()
        model_admin.autocomplete_extra_fields = ["base_price_q"]

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert result["base_price_q"] == 500

    def test_no_extra_fields_when_not_declared(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.pk = 1
        obj.__str__ = lambda self: "Test Object"

        model_admin = MagicMock(spec=[])

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert "base_price_q" not in result

    def test_skips_missing_attributes(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock(spec=["pk", "__str__"])
        obj.pk = 1
        obj.__str__ = lambda self: "Test"

        model_admin = MagicMock()
        model_admin.autocomplete_extra_fields = ["nonexistent_field"]

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert "nonexistent_field" not in result

    def test_unregistered_model_returns_standard_result(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.pk = 42
        obj.__str__ = lambda self: "Unregistered"

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {}

        result = view.serialize_result(obj, "pk")
        assert "id" in result
        assert "text" in result


class TestWithoutUnfold:
    """O Unfold é sugerido, não obrigatório: sem ele, nada pode explodir.

    Estes pacotes são instaláveis num Django Admin puro. Os helpers desenham com
    os templates do Unfold quando ele existe e caem para HTML simples quando não
    existe — nunca para classe de um tema ausente, que seria estilo quebrado em
    vez de estilo nenhum.
    """

    def _sem_unfold(self, monkeypatch):
        from django.template import TemplateDoesNotExist

        from shopman.utils.contrib.admin_unfold import badges, render

        def explode(*args, **kwargs):
            raise TemplateDoesNotExist("unfold não instalado")

        monkeypatch.setattr(badges, "render_to_string", explode)
        monkeypatch.setattr(render, "render_to_string", explode)

    def test_badge_degrades_to_plain_text(self, monkeypatch):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        self._sem_unfold(monkeypatch)
        result = str(unfold_badge("Ativo", "green"))

        assert "Ativo" in result
        assert "bg-green" not in result, "classe de tema ausente é pior que sem estilo"

    def test_badge_still_escapes_without_unfold(self, monkeypatch):
        """O fallback não pode abrir buraco de XSS que o caminho normal fecha."""
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        self._sem_unfold(monkeypatch)
        result = str(unfold_badge('<script>alert("xss")</script>'))

        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_link_degrades_to_plain_anchor(self, monkeypatch):
        from shopman.utils.contrib.admin_unfold.render import unfold_link

        self._sem_unfold(monkeypatch)
        result = str(unfold_link("/admin/x/", "Abrir", new_tab=True))

        assert 'href="/admin/x/"' in result
        assert "Abrir" in result
        assert 'target="_blank"' in result

    def test_link_escapes_text_without_unfold(self, monkeypatch):
        from shopman.utils.contrib.admin_unfold.render import unfold_link

        self._sem_unfold(monkeypatch)
        result = str(unfold_link("/x/", '<img src=x onerror="alert(1)">'))

        assert "<img" not in result
        assert "&lt;img" in result
