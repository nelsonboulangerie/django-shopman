"""Login do Admin com freio de tentativas.

O Admin respondia a senha sem limite nenhum, em dois hosts (``admin.`` e
``api.``), enquanto a MESMA credencial pelo login dos apps de operador
(``OperatorLoginView``) já tinha 5/min por conta e 30/min por IP. Era o caminho
sem freio para chutar a senha de staff — e de superusuário.

Mesmos números e mesma régua do login de operador, pelo mesmo motivo:

- **por conta (5/min):** ataque a uma conta, venha de quantos IPs vier;
- **por IP (30/min):** quem varre usernames. Generoso porque os dispositivos da
  loja saem pelo mesmo NAT.

O IP é o ``auth.client_ip`` (``RATELIMIT_IP_META_KEY``): conta o
X-Forwarded-For pela DIREITA com ``DOORMAN_TRUSTED_PROXY_DEPTH``, onde quem
escreve é a borda da plataforma. O valor que o cliente forja entra pela ponta
esquerda e não escolhe bucket. Foi a falta dessa prova que segurou o #655; ela
existe desde 17/09 (#763/#768, medida no alpha com XFF forjado direto no
``api.``), e o ``admin.`` passa pela mesma borda até o mesmo componente.

Estourado o limite, a senha nem chega a ser conferida: a resposta é 429 antes de
``authenticate()``, então nem a senha certa abre sessão dentro da janela.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit

RETRY_AFTER_SECONDS = 60


def _username_key(group, request) -> str:
    """O bucket da conta-alvo. ``casefold`` para "Admin" e "admin" não serem dois."""
    return str(request.POST.get("username") or "").strip().casefold() or "anon"


@never_cache
@ratelimit(key="ip", rate="30/m", method="POST", block=False)
@ratelimit(key=_username_key, rate="5/m", method="POST", block=False)
def admin_login(request, extra_context=None):
    if getattr(request, "limited", False):
        response = HttpResponse(
            "Muitas tentativas de entrar no Admin. Aguarde um minuto e tente de novo.",
            status=429,
            content_type="text/plain; charset=utf-8",
        )
        response["Retry-After"] = str(RETRY_AFTER_SECONDS)
        return response
    return admin.site.login(request, extra_context=extra_context)
