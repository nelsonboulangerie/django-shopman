"""Performance contracts for the optional operator template context."""

from __future__ import annotations

from unittest.mock import patch

from django.template import engines
from django.test import RequestFactory


def test_operator_context_processor_is_not_global(settings):
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]

    assert "shopman.backstage.context_processors.operator" not in processors


def test_rendering_a_request_template_does_not_build_operator_context(
    db, django_user_model, django_assert_num_queries
):
    """Templates pay no operator KPIs/alerts cost unless a view opts in."""
    request = RequestFactory().get("/admin/")
    request.user = django_user_model.objects.create_user("template-staff", is_staff=True)
    template = engines["django"].from_string("{{ operator|default:'absent' }}")

    with patch("shopman.backstage.context_processors.build_operator_context") as build:
        with django_assert_num_queries(0):
            rendered = template.render({}, request=request)

    assert rendered == "absent"
    build.assert_not_called()


def test_operator_context_processor_remains_available_for_explicit_opt_in():
    """Removing the global registration does not remove the reusable module."""
    from shopman.backstage import context_processors

    request = RequestFactory().get("/operator/")
    sentinel = object()
    with patch.object(context_processors, "build_operator_context", return_value=sentinel) as build:
        assert context_processors.operator(request) == {"operator": sentinel}

    build.assert_called_once_with(request)
