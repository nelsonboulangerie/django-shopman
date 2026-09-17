"""Backstage middleware — onboarding redirect e renovação da sessão de operador."""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect

from shopman.backstage.services import operator_session
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

        if path in {"/admin/2fa/verify/", "/admin/2fa/enroll/", "/admin/login/", "/admin/logout/"}:
            return self.get_response(request)

        if path.startswith(self.SETUP_PATH):
            return self.get_response(request)

        if not getattr(request.user, "is_staff", False):
            return self.get_response(request)

        if Shop.load() is None:
            return redirect(f"{self.SETUP_PATH}add/")

        return self.get_response(request)


class OperatorSessionRenewalMiddleware:
    """Renova a sessão dos apps de operador com o uso (7 dias parada ⇒ expira).

    A regra mora em :mod:`shopman.backstage.services.operator_session`; aqui fica
    só QUANDO ela se aplica:

    - na fase de resposta, para o ``SessionMiddleware`` (mais externo) gravar a
      sessão e reemitir o cookie — e o ``OperatorSessionDomainMiddleware``
      (mais externo ainda) escopá-lo à zona de operador;
    - nunca sob ``/admin/``: o Admin guarda o comportamento padrão do Django, e o
      BFF de operador bate em ``/admin/login/`` só para buscar CSRF;
    - nunca numa resposta em streaming (SSE): o proxy de eventos do BFF não
      repassa ``Set-Cookie``, e renovar ali adiantaria o banco sem o navegador
      saber — o cookie morreria antes da sessão;
    - só com cookie de sessão presente, para não tocar ``request.session`` (e
      ganhar ``Vary: Cookie``) em quem nem sessão tem.
    """

    SKIP_PREFIXES = ("/admin/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.streaming:
            return response
        if request.path.startswith(self.SKIP_PREFIXES):
            return response
        if not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
            return response
        operator_session.renew_if_due(request)
        return response
