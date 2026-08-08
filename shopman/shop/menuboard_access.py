"""Quem pode abrir um menuboard — e por que ele deixou de ser público.

O menuboard é superfície **interna**: uma TV na parede da loja. O feed XML é
superfície **pública**, porque Google e Meta precisam buscá-lo. Eram as duas
servidas sem nenhuma autenticação, e a ADR-018 §5.1 fecha a primeira.

O motivo não é higiene: ``display.prices_from`` do menuboard aponta para o PDV
(decisão do dono — a TV está fisicamente na loja e tem de concordar com o balcão).
No dia em que o renderizador passar a ler esse ponteiro, um menuboard aberto
**publica uma segunda tabela de preços** a quem tiver a URL. No Brasil, publicidade
suficientemente precisa vincula o fornecedor: preço alcançável publicamente é preço
a honrar. Por isso a trava entra **antes** da troca da fonte de preço, nunca depois.

Agrava o caso o SSE: ``/menuboard/<ref>/events/`` inscreve quem chamar no canal
``stock-catalog``, entregando o ritmo operacional da loja — o que está esgotando,
quando a fornada entra.

Duas credenciais são aceitas, porque TV na parede e gente são coisas diferentes:

1. **Sessão de staff** — para quem abre no computador para conferir.
2. **Token de quiosque** (``?k=``) — para a TV. Assinado, carrega a ref do próprio
   quadro (token de um quadro não abre outro) e não expira, porque display na parede
   não faz login a cada 14 dias. Gerado por ``manage.py menuboard_token <ref>``.

Limitação assumida: revogar um token exige rotacionar ``SECRET_KEY``. É aceitável
para um quadro de preços interno e está documentado aqui em vez de escondido.

``SHOPMAN_MENUBOARD_PUBLIC=true`` reabre tudo — escotilha explícita, default
fechado, para o estado seguro ser o default.
"""

from __future__ import annotations

from django.conf import settings
from django.core import signing
from django.http import HttpResponseForbidden

#: Salt dedicado: token de menuboard não vale para mais nada assinado no projeto.
KIOSK_SALT = "shopman.menuboard.kiosk"

#: Parâmetro de query que a TV carrega na URL.
KIOSK_PARAM = "k"


def make_kiosk_token(ref: str) -> str:
    """Token durável para UM quadro. Sem timestamp: display não renova sozinho."""
    return signing.Signer(salt=KIOSK_SALT).sign(str(ref).strip())


def kiosk_token_is_valid(ref: str, token: str) -> bool:
    """O token é válido **e** é deste quadro?"""
    if not token:
        return False
    try:
        signed_ref = signing.Signer(salt=KIOSK_SALT).unsign(token)
    except signing.BadSignature:
        return False
    return signed_ref == str(ref).strip()


def menuboard_access_denied(request, ref: str):
    """``None`` quando pode entrar; uma 403 explicativa quando não pode."""
    if getattr(settings, "SHOPMAN_MENUBOARD_PUBLIC", False):
        return None

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_staff", False):
        return None

    if kiosk_token_is_valid(ref, request.GET.get(KIOSK_PARAM, "")):
        return None

    return HttpResponseForbidden(
        "Menuboard é superfície interna. Abra com sessão de operador, ou use a URL "
        "de quiosque gerada por `manage.py menuboard_token <ref>`."
    )
