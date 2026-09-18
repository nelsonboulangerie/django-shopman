"""Backstage middleware — onboarding redirect e renovação das sessões (operador e Admin)."""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect

from shopman.backstage.services import admin_session, operator_session
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


class SessionRenewalMiddleware:
    """Renova a sessão com o uso — a de operador (7 dias parada) e a do Admin (14).

    As regras moram em :mod:`shopman.backstage.services.operator_session` e
    :mod:`shopman.backstage.services.admin_session`; aqui fica só QUANDO cada
    uma se aplica:

    - na fase de resposta, para o ``SessionMiddleware`` (mais externo) gravar a
      sessão e reemitir o cookie — e o ``OperatorSessionDomainMiddleware``
      (mais externo ainda) escopá-lo à zona de operador;
    - sob ``/admin/``, vale a regra do Admin
      (:mod:`shopman.backstage.services.admin_session`), não a de operador: o
      BFF de operador bate em ``/admin/login/`` só para buscar CSRF, e quem
      carrega a marca de operador continua seguindo a regra de lá;
    - nunca numa resposta em streaming (SSE): o proxy de eventos do BFF não
      repassa ``Set-Cookie``, e renovar ali adiantaria o banco sem o navegador
      saber — o cookie morreria antes da sessão;
    - só com cookie de sessão presente, para não tocar ``request.session`` (e
      ganhar ``Vary: Cookie``) em quem nem sessão tem.
    """

    #: Sob estes prefixos quem responde é o Admin, e a regra é a dele. Aqui não
    #: se PULA mais: pular era o que deixava a sessão do Admin com o corte seco
    #: de 14 dias a partir do login, e era essa a queixa que não passava.
    ADMIN_PREFIXES = ("/admin/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.streaming:
            return response
        if not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
            return response
        if request.path.startswith(self.ADMIN_PREFIXES):
            admin_session.renew_if_due(request)
            return response
        operator_session.renew_if_due(request)
        return response
