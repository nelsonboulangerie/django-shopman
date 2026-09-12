"""DANFE NFC-e em tela e bobina a partir do XML autorizado do provedor.

O pedido serve para localizar a nota. Dados comerciais mutáveis não substituem
XML indisponível; nessa situação a tela oferece a via do Focus e a bobina recusa.
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

        img = qrcode.make(content, image_factory=qrcode.image.svg.SvgPathImage, border=4)
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
    source_verified: bool = False
    source_problem: str = ""
    query_url: str = ""
    issued_at: str = ""
    authorized_at: str = ""
    customer_tax_id_label: str = "CPF"
    customer_address: str = ""
    totals: tuple[tuple[str, str], ...] = ()
    payments: tuple[tuple[str, str], ...] = ()
    additional_info: tuple[str, ...] = ()
    contingency: bool = False
    shop_ie: str = ""


def _format_tax_id(value: str) -> str:
    digits = "".join(ch for ch in str(value or "").upper() if ch.isascii() and ch.isalnum())
    if len(digits) == 11 and digits.isdigit():
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

    document = DanfeDocument(
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

    if not key:
        return document
    from dataclasses import replace

    from shopman.shop.services.danfe_xml import DanfeSourceError, read_authorized_xml

    if data.get("nfce_cancelled") or str(data.get("nfce_status") or "").lower() == "cancelado":
        return replace(document, source_problem="NFC-e cancelada. Impressão fiscal indisponível.", status="cancelada")
    try:
        root = read_authorized_xml(str(data.get("nfce_xml_url") or ""), key)
        return document_from_xml(document, root)
    except (DanfeSourceError, ValueError, ArithmeticError) as exc:
        logger.warning("danfe_source_unavailable order=%s reason=%s", order.ref, type(exc).__name__)
        return replace(
            document,
            source_problem=str(exc) if isinstance(exc, DanfeSourceError) else "Valores inválidos no XML fiscal.",
        )


def document_from_xml(document: DanfeDocument, root) -> DanfeDocument:
    """Todos os campos fiscais vêm do XML; pedido fornece apenas a referência interna."""
    from dataclasses import replace
    from datetime import datetime
    from decimal import Decimal

    from django.utils import timezone

    from shopman.shop.services.danfe_xml import NS, DanfeSourceError, value

    info = root.find("n:NFe/n:infNFe", NS)
    protocol = root.find("n:protNFe/n:infProt", NS)

    def money(text):
        return _money(int((Decimal(text or "0") * 100).quantize(Decimal("1"))))

    def number(text):
        return (format(Decimal(text), "f").rstrip("0").rstrip(".") or "0") if "." in text else text

    def unit_price(text):
        raw = number(text)
        places = max(2, len(raw.split(".")[1]) if "." in raw else 0)
        return "R$ " + format(Decimal(raw), f",.{places}f").translate(str.maketrans({",": ".", ".": ","}))

    def address(path):
        return ", ".join(
            value(info, f"{path}/{part}")
            for part in ("xLgr", "nro", "xCpl", "xBairro", "xMun", "UF", "CEP")
            if value(info, f"{path}/{part}")
        )

    items = tuple(
        DanfeItem(
            seq=int(item.get("nItem")),
            sku=value(item, "prod/cProd"),
            name=value(item, "prod/xProd"),
            qty=number(value(item, "prod/qCom")).replace(".", ","),
            unit=value(item, "prod/uCom"),
            unit_price_display=unit_price(value(item, "prod/vUnCom")),
            total_display=money(value(item, "prod/vProd")),
        )
        for item in info.findall("n:det", NS)
    )
    if not items:
        raise DanfeSourceError("XML fiscal sem itens.")
    forms = {
        "01": "Dinheiro",
        "02": "Cheque",
        "03": "Cartão de crédito",
        "04": "Cartão de débito",
        "05": "Crédito loja",
        "10": "Vale alimentação",
        "11": "Vale refeição",
        "15": "Boleto",
        "16": "Depósito bancário",
        "17": "PIX",
        "18": "Transferência",
        "19": "Fidelidade",
        "20": "PIX estático",
        "90": "Sem pagamento",
        "99": "Outros",
    }
    payments = tuple(
        (
            value(pay, "xPag") or forms.get(value(pay, "tPag"), f"Pagamento {value(pay, 'tPag')}"),
            money(value(pay, "vPag")),
        )
        for pay in info.findall("n:pag/n:detPag", NS)
    )
    totals = [("Valor dos produtos", money(value(info, "total/ICMSTot/vProd")))]
    for tag, label in (("vDesc", "Desconto"), ("vFrete", "Frete"), ("vSeg", "Seguro"), ("vOutro", "Outros acréscimos")):
        raw = value(info, f"total/ICMSTot/{tag}")
        if Decimal(raw or "0"):
            totals.append((label, money(raw)))
    change = value(info, "pag/vTroco")
    if Decimal(change or "0"):
        payments += (("Troco", money(change)),)
    extras = tuple(value(info, f"infAdic/{tag}") for tag in ("infAdFisco", "infCpl") if value(info, f"infAdic/{tag}"))
    if value(protocol, "xMsg"):
        extras += (value(protocol, "xMsg"),)
    tax = value(info, "total/ICMSTot/vTotTrib")
    if tax:
        extras += (f"Tributos totais incidentes (Lei Federal 12.741/2012): {money(tax)}",)
    tax_id = value(info, "dest/CPF") or value(info, "dest/CNPJ") or value(info, "dest/idEstrangeiro")
    label = "CPF" if value(info, "dest/CPF") else "CNPJ" if value(info, "dest/CNPJ") else "Id. estrangeiro"
    qr = value(root, "NFe/infNFeSupl/qrCode")
    homolog = value(info, "ide/tpAmb") == "2"
    return replace(
        document,
        source_verified=True,
        source_problem="",
        emitted=True,
        is_homolog=homolog,
        environment_label="Homologação" if homolog else "Produção",
        status="autorizado",
        shop_name=value(info, "emit/xFant"),
        shop_legal_name=value(info, "emit/xNome"),
        shop_cnpj=_format_tax_id(value(info, "emit/CNPJ") or value(info, "emit/CPF")),
        shop_ie=value(info, "emit/IE"),
        shop_address=address("emit/enderEmit"),
        number=value(info, "ide/nNF"),
        series=value(info, "ide/serie"),
        protocol=value(protocol, "nProt"),
        issued_at=timezone.localtime(datetime.fromisoformat(value(info, "ide/dhEmi"))).strftime("%d/%m/%Y %H:%M:%S"),
        authorized_at=timezone.localtime(datetime.fromisoformat(value(protocol, "dhRecbto"))).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
        items=items,
        item_count=len(items),
        total_display=money(value(info, "total/ICMSTot/vNF")),
        totals=tuple(totals),
        payments=payments,
        payment_label=", ".join(label for label, _ in payments),
        customer_name=value(info, "dest/xNome"),
        customer_tax_id_display=_format_tax_id(tax_id) or tax_id,
        customer_tax_id_label=label,
        customer_address=address("dest/enderDest"),
        query_url=value(root, "NFe/infNFeSupl/urlChave"),
        consult_url=qr,
        qr_svg=_qr_svg(qr),
        additional_info=extras,
        contingency=value(info, "ide/tpEmis") == "9",
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
