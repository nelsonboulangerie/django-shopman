"""Quem pode abrir um menuboard — e por que ele deixou de ser público.

O menuboard é superfície **interna**: uma TV na parede da loja. O feed XML é
superfície **pública**, porque Google e Meta precisam buscá-lo. Eram as duas
servidas sem nenhuma autenticação, e a ADR-018 §5.1 fecha a primeira.

O motivo não é higiene: ``display.prices_from`` do menuboard aponta para o PDV (a TV
está fisicamente na loja e tem de concordar com o balcão). No dia em que o
renderizador passar a ler esse ponteiro, um menuboard aberto **publica uma segunda
tabela de preços** a quem tiver a URL. No Brasil, publicidade suficientemente
precisa vincula o fornecedor: preço alcançável publicamente é preço a honrar. Por
isso a trava entra **antes** da troca da fonte de preço, nunca depois.

Agrava o caso o SSE: ``/menuboard/<ref>/events/`` inscreve quem chamar no canal
``stock-catalog``, entregando o ritmo operacional da loja — o que está esgotando,
quando a fornada entra.

Duas credenciais valem, porque TV na parede e gente são coisas diferentes:

1. **Sessão de staff** — para quem confere no computador. Também é o que
   **autoriza** a TV: ao abrir o quadro logado, a resposta grava a confiança
   daquele dispositivo (ver ``ensure_display_trust``).
2. **Dispositivo confiável** (``TrustedDevice`` com ``subject_type="display"``) —
   para a TV. Cookie HttpOnly, sem credencial na URL, revogável por dispositivo no
   Admin, com ``label``/``ip_address``/``last_used_at`` para auditoria.

A confiança de dispositivo do ``doorman`` foi generalizada para isto (§3.1:
``handle_type`` + ``handle_ref``). A alternativa que existiu por meia hora aqui era
um token assinado na URL — descartada porque não tinha revogação (exigia rotacionar
``SECRET_KEY``), não tinha auditoria, e punha credencial em histórico de navegador.

``SHOPMAN_MENUBOARD_PUBLIC=true`` reabre tudo — escotilha explícita, default
fechado, para o estado seguro ser o default.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden

DISPLAY_SUBJECT = "display"


def _is_public() -> bool:
    return bool(getattr(settings, "SHOPMAN_MENUBOARD_PUBLIC", False))


def _is_staff(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user is not None and getattr(user, "is_staff", False))


def menuboard_access_denied(request, ref: str):
    """``None`` quando pode entrar; uma 403 explicativa quando não pode."""
    if _is_public() or _is_staff(request):
        return None

    from shopman.doorman.services.device_trust import DeviceTrustService

    if DeviceTrustService.check(request, DISPLAY_SUBJECT, ref):
        return None

    return HttpResponseForbidden(
        "Menuboard é superfície interna. Abra uma vez com sessão de operador nesta "
        "tela para autorizá-la — o dispositivo fica confiável e não pede mais nada."
    )


def ensure_display_trust(request, response, ref: str):
    """Operador logado abrindo o quadro AUTORIZA aquele dispositivo.

    É o provisionamento inteiro: alguém do balcão abre a URL na TV, entra uma vez,
    e o cookie durável fica. Nada de token em URL, nada de digitar a cada 14 dias.

    Só grava quando ainda não há confiança, para não criar uma linha de
    ``TrustedDevice`` por visita.
    """
    if not _is_staff(request):
        return response

    from shopman.doorman.services.device_trust import DeviceTrustService

    if DeviceTrustService.check(request, DISPLAY_SUBJECT, ref):
        return response

    DeviceTrustService.trust(
        response=response,
        subject_type=DISPLAY_SUBJECT,
        subject_id=ref,
        request=request,
    )
    return response
