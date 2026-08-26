"""
DANFE NFC-e na TELA — a nota aberta para consulta, renderizada no servidor.

Monta o DANFE (Documento Auxiliar da NFC-e) a partir do resultado guardado em
``order.data`` (chave, protocolo, QR, itens) + os dados do emitente (``Shop``).

**Há um documento só, e duas maneiras de olhar para ele.** A via que vai para o
cliente é a BOBINA, composta em ESC/POS por ``backstage.services.receipt_escpos
.danfe_nfce()`` e impressa pelo agente do terminal — é ela que tem largura,
chave agrupada, QR da SEFAZ e o carimbo de homologação no formato conforme. Esta
página é a mesma nota em formato de leitura: abrir, conferir, ler a chave, e (com
o link do provedor) alcançar a via hospedada pelo Focus, que é a do contador.

Enquanto não havia saída conforme, esta tela se anunciava como "prévia interna" e
oferecia um botão de imprimir. As duas coisas saíram: A4 não é DANFE, e a
hierarquia "prévia × oficial" descrevia um mundo com duas notas que nunca
existiu. Quem imprime é o terminal.

Não é um read-model multi-superfície (por isso não vive em ``shop/projections/``):
é um documento com um único consumidor — este template — e por isso formata
dinheiro/aparência aqui, no lado da apresentação. Gated a staff. Em HOMOLOGAÇÃO
carimba "SEM VALOR FISCAL" (obrigatório), igual à bobina.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import render
from django.views import View
from shopman.utils.monetary import format_money

logger = logging.getLogger(__name__)


def _money(value_q: int | None) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _format_chave(key: str) -> str:
    """44 dígitos da chave de acesso em grupos de 4 (padrão do DANFE)."""
    digits = "".join(ch for ch in str(key or "") if ch.isdigit())
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def _qr_svg(content: str) -> str:
    """QR inline (SVG) a partir da URL de consulta da NFC-e. Vazio se não der."""
    if not content:
        return ""
    try:
        import qrcode
        import qrcode.image.svg

        img = qrcode.make(content, image_factory=qrcode.image.svg.SvgPathImage, border=1)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception:
        logger.debug("danfe: falha ao gerar QR inline", exc_info=True)
        return ""


_PAYMENT_LABELS = {
    "pix": "PIX",
    "card": "Cartão",
    "credit": "Cartão de crédito",
    "debit": "Cartão de débito",
    "cash": "Dinheiro",
    "external": "Pago no canal",
    # Faltavam, e o fallback `.title()` punha "Mixed" e "Account" — em inglês,
    # num documento fiscal, na tela e na bobina (as duas leem este mesmo rótulo).
    "mixed": "Pagamento misto",
    "account": "Conta da casa",
}


@dataclass(frozen=True)
class DanfeItem:
    seq: int
    sku: str
    name: str
    qty: str
    unit: str
    unit_price_display: str
    total_display: str


@dataclass(frozen=True)
class DanfeDocument:
    order_ref: str
    emitted: bool  # já tem NFC-e emitida guardada?
    is_homolog: bool
    environment_label: str  # "Homologação" | "Produção"
    status: str

    # emitente (Shop)
    shop_name: str
    shop_legal_name: str
    shop_cnpj: str
    shop_address: str

    # documento
    number: str
    series: str
    key: str
    chave_grouped: str
    protocol: str

    # itens + totais
    items: tuple[DanfeItem, ...] = field(default_factory=tuple)
    item_count: int = 0
    total_display: str = "R$ 0,00"
    payment_label: str = ""

    # consumidor
    customer_name: str = ""
    #: O documento QUE SAIU NA NOTA, formatado. Vazio = consumidor não
    #: identificado — e aí a tela diz isso, em vez de fabricar um nome.
    customer_tax_id_display: str = ""

    # QR + links
    qr_svg: str = ""
    danfe_url: str = ""
    consult_url: str = ""


def _format_tax_id(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return ""


def _consumer_name(data: dict) -> str:
    """O nome do consumidor — ou nada, nunca um nome fabricado.

    O PDV batiza um cliente que só deu CPF como "Cliente Doc 6789" (os quatro
    últimos dígitos), para o CRM ter o que listar. Esse apelido interno estava
    vazando para a linha do consumidor no documento: quem pediu CPF na nota lia
    um pedaço do próprio número onde deveria estar o nome — e não tinha como
    saber se o CPF entrou. Nome de fachada não vai para documento: aqui, ou há
    nome de gente, ou o documento fala pelo CPF.
    """
    name = str((data.get("customer") or {}).get("name") or "").strip()
    lowered = name.lower()
    if not name or lowered == "cliente" or lowered.startswith("cliente doc "):
        return ""
    return name


def _shop_address(shop) -> str:
    if shop is None:
        return ""
    parts = [
        getattr(shop, "address_line", "") or getattr(shop, "address", "") or "",
        getattr(shop, "city", "") or "",
        getattr(shop, "state", "") or "",
    ]
    return " · ".join(p for p in parts if p)


def build_danfe(order_ref: str) -> DanfeDocument | None:
    """Monta o DANFE de um pedido. ``None`` se o pedido não existe."""
    from django.conf import settings
    from shopman.orderman.models import Order

    from shopman.shop.models import Shop

    order = Order.objects.filter(ref=order_ref).prefetch_related("items").first()
    if order is None:
        return None

    data = order.data or {}
    shop = Shop.objects.first()

    env = str((getattr(settings, "SHOPMAN_FOCUS_NFE", {}) or {}).get("environment", "homologacao")).lower()
    is_homolog = "prod" not in env

    key = str(data.get("nfce_access_key") or "")
    qr_content = str(data.get("nfce_qrcode_url") or "")

    items: list[DanfeItem] = []
    for i, it in enumerate(order.items.all(), start=1):
        qty = it.qty.normalize() if hasattr(it.qty, "normalize") else it.qty
        items.append(
            DanfeItem(
                seq=i,
                sku=it.sku,
                name=it.name,
                qty=str(qty),
                unit=(getattr(it, "unit", "") or "UN"),
                unit_price_display=_money(it.unit_price_q),
                total_display=_money(it.line_total_q),
            )
        )

    payment = data.get("payment") or {}
    payment_method = str(payment.get("method") or "")
    payment_label = _PAYMENT_LABELS.get(payment_method, payment_method.title() or "—")

    return DanfeDocument(
        order_ref=order.ref,
        emitted=bool(key),
        is_homolog=is_homolog,
        environment_label="Homologação" if is_homolog else "Produção",
        status=str(data.get("nfce_status") or ("autorizado" if key else "não emitida")),
        shop_name=(getattr(shop, "brand_name", "") or getattr(shop, "name", "") or "") if shop else "",
        shop_legal_name=(getattr(shop, "legal_name", "") or "") if shop else "",
        shop_cnpj=(getattr(shop, "document", "") or "") if shop else "",
        shop_address=_shop_address(shop),
        number=str(data.get("nfce_number") or ""),
        series=str(data.get("nfce_series") or ""),
        key=key,
        chave_grouped=_format_chave(key),
        protocol=str(data.get("nfce_protocol") or ""),
        items=tuple(items),
        item_count=len(items),
        total_display=_money(order.total_q),
        payment_label=payment_label,
        customer_name=_consumer_name(data),
        customer_tax_id_display=_format_tax_id(str((data.get("fiscal") or {}).get("tax_id") or "")),
        qr_svg=_qr_svg(qr_content),
        danfe_url=str(data.get("nfce_danfe_url") or ""),
        consult_url=qr_content,
    )


class DanfeView(LoginRequiredMixin, View):
    """A nota de um pedido aberta na tela (staff). Consulta, não impressão."""

    def get(self, request, ref: str):
        if not request.user.is_staff:
            raise Http404()

        danfe = build_danfe(ref)
        if danfe is None:
            raise Http404(f"Pedido '{ref}' não encontrado.")
        return render(request, "fiscal/danfe.html", {"d": danfe})
