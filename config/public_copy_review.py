"""A copy pública que precisa do aval do dono ANTES do go-live.

Ordem do Pablo em 17/09/2026: a FAQ e as copies que o cliente lê "estão erradas,
precisam de revisão" e "DEVEM ser corrigidas antes de ir GO-live, como bloqueio
mesmo"; o sitemap é consolidado ANTES de ir ao Search Console.

Cada item fica pendente até ganhar ``approved_by`` e ``approved_at``. O
``make production-readiness`` reprova enquanto houver pendente; no alpha, o
mesmo check só avisa. Aprovar é editar ESTE arquivo num PR, com o nome de quem
aprovou e a data: o aval fica no histórico, junto do texto que ele aprovou.
"""

from __future__ import annotations

PUBLIC_COPY_REVIEW: tuple[dict[str, str], ...] = (
    {
        "id": "faq_initial",
        "title": "FAQ inicial revisada e publicada",
        "detail": (
            "14 respostas de `apply_search_presence.PUBLIC_FAQ`, todas nascem como rascunho. "
            "Revisar o texto no Admin → Perguntas frequentes e publicar as aprovadas. Quatro "
            "dependem de decisão de negócio: cancelamento, CPF na nota do pedido online, iFood "
            "e fidelidade."
        ),
        "approved_by": "",
        "approved_at": "",
    },
    {
        "id": "copy_contradictions",
        "title": "Contradições da copy resolvidas",
        "detail": (
            "Encomenda: a copy da home diz até 7 dias (HOME_*), o canal permite 30 "
            "(max_preorder_days). Prazo do Pix: 10 minutos na configuração, 15 na documentação. "
            "'100% fermentação natural' não vale para croissant e brioche (fermento biológico)."
        ),
        "approved_by": "",
        "approved_at": "",
    },
    {
        "id": "search_texts",
        "title": "Textos de busca e compartilhamento aprovados",
        "detail": (
            "Admin → Busca e compartilhamento: título e descrição da home, descrições do "
            "cardápio e da FAQ, imagem do cartão de link. Os propostos estão em "
            "`apply_search_presence.SEARCH_FIELDS`."
        ),
        "approved_by": "",
        "approved_at": "",
    },
    {
        "id": "opening_hours",
        "title": "Horário real de volta no Admin",
        "detail": (
            "Segunda a sábado, 9h às 18h. O alpha está com horário ampliado para testes, e o "
            "horário vai para os dados estruturados do Google e para a resposta da FAQ."
        ),
        "approved_by": "",
        "approved_at": "",
    },
    {
        "id": "sitemap_consolidated",
        "title": "Sitemap consolidado",
        "detail": (
            "Conferir as URLs, prioridades e a presença da FAQ e das páginas legais em "
            "/sitemap.xml do www.nelsonboulangerie.com.br."
        ),
        "approved_by": "",
        "approved_at": "",
    },
    {
        "id": "sitemap_submitted",
        "title": "Sitemap enviado ao Search Console",
        "detail": (
            "Só depois do sitemap consolidado. Propriedade de domínio nelsonboulangerie.com.br, "
            "URL https://www.nelsonboulangerie.com.br/sitemap.xml."
        ),
        "approved_by": "",
        "approved_at": "",
    },
)


def pending_items(review=PUBLIC_COPY_REVIEW) -> list[dict[str, str]]:
    return [
        item
        for item in review
        if not (str(item.get("approved_by") or "").strip() and str(item.get("approved_at") or "").strip())
    ]
