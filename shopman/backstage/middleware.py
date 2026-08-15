"""Backstage middleware — onboarding redirect for operator surfaces."""

from __future__ import annotations

from django.shortcuts import redirect

from shopman.shop.models import Shop


class OnboardingMiddleware:
    """Manda o staff criar a loja quando ainda não existe nenhuma.

    Usa Shop.load() (singleton em cache), então custa zero query na operação
    normal.

    ⚠️ Este redirect apontava para `/gestor/setup/`, a tela do shell de operador
    HTMX — que foi aposentado no cutover headless. O alvo virou 404: uma
    instalação nova mandava o dono para lugar nenhum, justamente no primeiro
    minuto de uso. Agora aponta para o formulário do `Shop` no Admin, que é onde
    a loja de fato nasce.
    """

    #: Também serve de passe-livre: qualquer caminho sob este prefixo escapa do
    #: redirect, senão criar a loja seria um loop.
    SETUP_PATH = "/admin/shop/shop/"
    GUARDED_PREFIXES = ("/admin/",)
    SKIP_PREFIXES = ("/static/", "/media/", "/api/", "/favicon")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if not any(path.startswith(p) for p in self.GUARDED_PREFIXES):
            return self.get_response(request)

        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        if path.startswith(self.SETUP_PATH):
            return self.get_response(request)

        if not getattr(request.user, "is_staff", False):
            return self.get_response(request)

        if Shop.load() is None:
            return redirect(f"{self.SETUP_PATH}add/")

        return self.get_response(request)
