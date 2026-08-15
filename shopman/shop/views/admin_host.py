"""A raiz do host do Admin cai no Admin.

`admin.boulangerie.com.br/admin` é redundante: o host já diz o que é. Quem
digita o endereço espera chegar, não repetir a palavra no caminho.

Vale só no host canônico. Na raiz dos OUTROS hosts (a API do operador, por
exemplo) nada muda — lá `/` não é porta de Admin, e transformar em redirect
seria inventar comportamento onde ninguém pediu.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect


def admin_host_root(request: HttpRequest) -> HttpResponse:
    canonical = (getattr(settings, "SHOPMAN_ADMIN_HOST", "") or "").strip().lower()
    host = request.get_host().split(":")[0].lower()
    if canonical and host == canonical:
        return HttpResponseRedirect("/admin/")
    # Sem host canônico configurado, ou noutro host: segue 404 como antes.
    raise Http404
