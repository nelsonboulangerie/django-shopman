"""Prévia offline dos bytes reais ESC/POS. Não acessa banco, SEFAZ ou impressora.

Uso: python scripts/print_preview/render.py --output output/print-layouts
A fonte A é aproximada por monospace; geometria: 12x24 dots, 203 dpi, 48 colunas.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import os
import shutil
import subprocess
import sys
import types
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)] + [str(p) for p in (ROOT / "packages").iterdir() if p.is_dir()]
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
import django

django.setup()
import qrcode
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from shopman.shop.omotenashi import copy as operational_copy

operational_copy._DB_CACHE = {}

from shopman.backstage.services import receipt_escpos as after
from shopman.shop.services.danfe_xml import parse_authorized_xml
from shopman.shop.tests.danfe_fixtures import KEY, XML
from shopman.shop.views.fiscal_danfe import DanfeDocument, DanfeItem, _format_chave, document_from_xml

BASE = "eaba3d45af9e9a201ff38ca6fb03899c4a78111a"


def svg_from_escpos(data):
    """Interpreta somente os comandos emitidos pelo compositor; desconhecido falha."""
    i, y, scale_x, scale_y, bold, align, module = 0, 0, 1, 1, False, 0, 6
    content, pending, qr_data = [], bytearray(), b""

    def flush():
        nonlocal y, pending
        text = pending.decode("cp860")
        width = len(text) * 12 * scale_x
        if width > 576:
            raise ValueError(f"Linha excedeu 48 colunas: {text}")
        x = 32 + ((576 - width) / 2 if align else 0)
        if text:
            content.append(
                f'<text x="{x}" y="{y + 23 * scale_y}" font-size="{24 * scale_y}" font-weight="{700 if bold else 400}" textLength="{width}" lengthAdjust="spacingAndGlyphs" xml:space="preserve">{html.escape(text)}</text>'
            )
        y += max(30, 24 * scale_y)
        pending = bytearray()

    while i < len(data):
        byte = data[i]
        if byte == 10:
            flush()
            i += 1
        elif data[i : i + 2] == b"\x1b@":
            scale_x = scale_y = 1
            bold = False
            align = 0
            i += 2
        elif data[i : i + 2] in (b"\x1bt", b"\x1bE", b"\x1ba", b"\x1bd"):
            cmd, arg = data[i + 1], data[i + 2]
            if cmd == ord("E"):
                bold = bool(arg)
            elif cmd == ord("a"):
                align = arg
            elif cmd == ord("d"):
                y += arg * 30
            i += 3
        elif data[i : i + 2] == b"\x1d!":
            scale_x, scale_y = (data[i + 2] >> 4) + 1, (data[i + 2] & 15) + 1
            i += 3
        elif data[i : i + 2] == b"\x1dV":
            i += 3
        elif data[i : i + 3] == b"\x1d(k":
            n = int.from_bytes(data[i + 3 : i + 5], "little")
            payload = data[i + 5 : i + 5 + n]
            if payload[:2] == b"1C":
                module = payload[2]
            elif payload[:2] == b"1P":
                qr_data = payload[3:]
            elif payload[:2] == b"1Q":
                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=module, border=4)
                qr.add_data(qr_data)
                qr.make(fit=True)
                image = qr.make_image()
                w, h = image.size
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                content.append(
                    f'<image x="{32 + (576 - w) / 2}" y="{y}" width="{w}" height="{h}" href="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"/>'
                )
                y += h
            i += 5 + n
        elif data[i : i + 4] == b"\x1dv0\x00":
            w = int.from_bytes(data[i + 4 : i + 6], "little")
            h = int.from_bytes(data[i + 6 : i + 8], "little")
            raw = data[i + 8 : i + 8 + w * h]
            image = Image.frombytes("1", (w * 8, h), bytes(b ^ 255 for b in raw))
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            content.append(
                f'<image x="{32 + (576 - w * 8) / 2 if align else 32}" y="{y}" width="{w * 8}" height="{h}" href="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"/>'
            )
            y += h
            i += 8 + w * h
        elif byte < 32:
            raise ValueError(f"Comando desconhecido em {i}: {data[i : i + 10]!r}")
        else:
            pending.append(byte)
            i += 1
    if pending:
        flush()
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="{y / 8:.2f}mm" viewBox="0 0 640 {y}" style="background:white;font-family:monospace"><rect width="640" height="{y}" fill="white"/>{"".join(content)}</svg>'
    return svg, y / 8


def order(ref, *, long=False, **extra):
    items = [SimpleNamespace(name="Pão de fermentação natural", qty=Decimal("2"), unit_price_q=1800, line_total_q=3600)]
    if long:
        items += [
            SimpleNamespace(name=name, qty=Decimal("3"), unit_price_q=1200, line_total_q=3600)
            for name in [
                "Croissant de amêndoas",
                "Brioche com creme de baunilha e frutas vermelhas",
                "Baguete de tradição francesa",
                "Pão integral com sementes e castanhas",
                "Pain au chocolat",
                "Focaccia com tomates e alecrim",
                "Sanduíche de queijo e tomate",
                "Bolo de laranja",
                "Pão de queijo",
                "Tarte de maçã com amêndoas",
                "Cookie de chocolate",
            ]
        ]
    data = {
        "customer": {"name": "Ana Exemplo", "phone": "(41) 00000-0000"},
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": "14:00-14:30",
        "pos": {"sales_mode": "order"},
        "payment": {"method": "pix", "status": "pending"},
    }
    data.update(extra)
    return SimpleNamespace(
        ref=ref,
        created_at=timezone.make_aware(datetime(2026, 9, 12, 9, 5)),
        total_q=sum(item.line_total_q for item in items),
        data=data,
        items=SimpleNamespace(all=lambda: items),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output/print-layouts")
    args = parser.parse_args()
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    before = types.ModuleType("before")
    exec(
        subprocess.check_output(["git", "show", f"{BASE}:shopman/backstage/services/receipt_escpos.py"], cwd=ROOT),
        before.__dict__,
    )
    address = {
        "fulfillment_type": "delivery",
        "delivery_address": "Avenida das Araucárias, 1234, Jardim das Flores, Curitiba - PR",
        "delivery_address_structured": {
            "complement": "Apartamento 702, bloco dos Ipês",
            "delivery_instructions": "Entrada pela rua lateral; ligar ao chegar. Não deixar na portaria.",
        },
    }
    cases = [
        ("curto", "Pedido curto · retirada hoje", order("DEMO-101")),
        (
            "longo",
            "Pedido longo · endereço e observações",
            order(
                "DEMO-102",
                long=True,
                **address,
                customer={"name": "Maria Aparecida da Silva Exemplo", "phone": "(41) 00000-0000"},
                order_notes="Sem castanhas nos sanduíches. Embalar os doces separados dos salgados.",
                kitchen_note="Conferir todas as unidades e identificar as duas sacolas.",
            ),
        ),
        (
            "pago",
            "Entrega paga · não cobrar",
            order("DEMO-103", **address, payment={"method": "pix", "status": "captured"}),
        ),
        (
            "troco",
            "Entrega · cobrar e levar troco",
            order(
                "DEMO-104", **address, payment={"method": "cash", "collection": "on_delivery", "change_for_q": 10000}
            ),
        ),
        (
            "misto",
            "Entrega · pagamento misto",
            order(
                "DEMO-105",
                **address,
                payment={
                    "method": "mixed",
                    "collection": "on_delivery",
                    "change_for_q": 10000,
                    "tenders": [
                        {"method": "cash", "amount_q": 2000, "status": "pending", "collection": "on_delivery"},
                        {"method": "credit", "amount_q": 1600, "status": "pending", "collection": "on_delivery"},
                    ],
                },
            ),
        ),
        (
            "balcao",
            "Balcão imediato",
            order(
                "DEMO-106",
                pos={"sales_mode": "counter"},
                delivery_date="",
                delivery_time_slot="",
                payment={"method": "cash", "status": "captured"},
            ),
        ),
    ]
    sections = []
    metrics = []
    with override_settings(SHOPMAN_PRINT_RENDERER="raster", SHOPMAN_PRINT_LOGO_PATH=str(ROOT / "media/branding/nelson-monogram-print.png")):
        for slug, title, example in cases:
            versions = [
                before.order_ticket(example, shop_name="Nelson Boulangerie"),
                after.order_ticket(example, shop_name="Nelson Boulangerie"),
            ]
            parts = []
            heights = []
            for label, payload in zip(("antes", "depois"), versions, strict=True):
                svg, height = svg_from_escpos(payload)
                (output / f"{slug}-{label}.svg").write_text(svg)
                (output / f"{slug}-{label}.bin").write_bytes(payload)
                heights.append(height)
                parts.append(f"<figure><figcaption>{label.title()} · {height:.1f} mm</figcaption>{svg}</figure>")
            metrics.append((title, *heights))
            sections.append(
                f'<section id="{slug}"><h2>{title}</h2><div class="comparison">{"".join(parts)}</div></section>'
            )
        empty = DanfeDocument(
            order_ref="FICTICIO-152",
            emitted=True,
            is_homolog=True,
            environment_label="Homologação",
            status="autorizado",
            shop_name="Padaria Exemplo",
            shop_legal_name="Padaria Exemplo Ltda",
            shop_cnpj="00.000.000/0001-91",
            shop_address="Rua Fictícia, 100, Centro, Curitiba, PR",
            number="152",
            series="1",
            key=KEY,
            chave_grouped=_format_chave(KEY),
            protocol="141260000000152",
            total_display="R$ 50,00",
            payment_label="Pagamento misto",
            consult_url=f"http://www.fazenda.pr.gov.br/nfce/qrcode?p={KEY}|3|2",
            items=(
                DanfeItem(1, "PAO", "Pão de fermentação natural", "2", "UN", "R$ 18,00", "R$ 36,00"),
                DanfeItem(2, "CROISSANT", "Croissant de amêndoas", "1", "UN", "R$ 12,00", "R$ 12,00"),
            ),
            item_count=2,
            customer_name="Ana Exemplo",
            customer_tax_id_display="000.000.001-91",
        )
        doc = document_from_xml(empty, parse_authorized_xml(XML, KEY))
        parts = []
        for label, payload in [("antes", before.danfe_nfce(empty)), ("depois", after.danfe_nfce(doc))]:
            svg, height = svg_from_escpos(payload)
            (output / f"fiscal-{label}.svg").write_text(svg)
            (output / f"fiscal-{label}.bin").write_bytes(payload)
            parts.append(f"<figure><figcaption>{label.title()} · {height:.1f} mm</figcaption>{svg}</figure>")
        sections.append(
            f'<section id="fiscal"><h2>DANFE NFC-e · XML fictício com desconto, frete e troco</h2><p>O antes omitia valores e campos fiscais. O depois os preserva; a altura adicional contém informações necessárias.</p><div class="comparison">{"".join(parts)}</div></section>'
        )
        from django.template.loader import render_to_string

        (output / "danfe-screen.html").write_text(render_to_string("fiscal/danfe.html", {"d": doc}))
    links = (
        " · ".join(f'<a href="#{slug}">{title.split(" · ")[0]}</a>' for slug, title, _ in cases)
        + ' · <a href="#fiscal">DANFE</a>'
    )
    page = (
        """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Impressos · antes e depois</title><style>
    *{box-sizing:border-box}body{margin:0;background:#eeede9;color:#181818;font:16px/1.5 system-ui,sans-serif}header,main{max-width:1000px;margin:auto;padding:24px}h1{font-size:36px;line-height:1.15;margin:8px 0 16px}h2{font-size:23px;margin:0 0 12px}p{max-width:78ch}a{color:inherit}nav{line-height:2.1}.comparison{display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start;padding:8px 0 24px}figure{margin:0;flex:none;width:80mm;max-width:100%}figure>svg{width:100%;height:auto}figcaption{font:600 13px system-ui;margin-bottom:8px}section{padding:28px 0;border-top:1px solid #bbb}svg{display:block;box-shadow:0 2px 8px #0002}.ruler{width:80mm;border-top:2px solid black;border-left:2px solid black;border-right:2px solid black;height:8mm;font-size:12px;text-align:center}.note{padding:14px 18px;background:white;border-left:4px solid #222} @media screen and (max-width:700px){.comparison{flex-direction:column}.comparison>figure:last-child{order:-1}} @media print{@page{size:A4;margin:12mm}body{background:white;font-size:10pt}header{padding:0}main{padding:0}nav{display:none}.comparison{gap:10mm;flex-wrap:nowrap;overflow:visible}figure{width:80mm;max-width:none}section{break-before:page;border:0;padding:0}section>p{display:none}.comparison{padding:0}svg{box-shadow:none}h1{font-size:20pt}h2{font-size:13pt}.note{padding:0;border:0}}
    </style><header><p>ESTUDO DE IMPRESSÃO · DADOS FICTÍCIOS</p><h1>Informação no lugar certo.</h1><p>Ficha do pedido: preparar, conferir e encaminhar. DANFE NFC-e: reproduzir o documento autorizado.</p><div class="note">Nova composição proporcional: imagem preto e branco enviada à térmica, com Barlow Semi Condensed incorporada. Antes: fonte residente aproximada. Bobina de 80 mm; área útil de 72 mm. Imprima em A4, escala 100%, sem ajustar e sem cabeçalho/rodapé. A escala física na tela depende do monitor.</div><p class="ruler">80 mm · régua de conferência</p><nav>"""
        + links
        + """</nav><p><a href="danfe-screen.html">Abrir consulta fiscal em tela</a></p></header><main>"""
        + "".join(sections)
        + """<section><h2>Sobre o nome</h2><p><strong>Ficha do pedido</strong> é a proposta para o papel operacional. “Comanda” já tem outro significado no PDV; “romaneio” funciona melhor para lote/rota; “ordem de preparo” fica estreito para retirada e cobrança.</p><p>Sem validação em impressora física: contraste, avanço, corte, raster da marca, fonte residente, durabilidade e leitura óptica do QR ainda precisam de ensaio no balcão. Nenhum dado real, emissão, merge ou deploy foi executado.</p></section></main></html>"""
    )
    for name in ("BarlowSemiCondensed-Medium.ttf", "BarlowSemiCondensed-Bold.ttf", "NotoSans.ttf"):
        shutil.copyfile(ROOT / "shopman/backstage/assets/print" / name, output / name)
    for extension in ("svg", "png"):
        shutil.copyfile(ROOT / f"media/branding/nelson-monogram-print.{extension}", output / f"monogram.{extension}")
    (output / "typography.html").write_text("""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Estudo de tipografia</title><style>
    @font-face{font-family:Barlow;src:url('BarlowSemiCondensed-Medium.ttf');font-weight:500}
    @font-face{font-family:Barlow;src:url('BarlowSemiCondensed-Bold.ttf');font-weight:700}
    @font-face{font-family:Noto;src:url('NotoSans.ttf');font-weight:100 900}
    body{margin:32px;background:#eeede9;font:16px system-ui;color:#111}main{display:flex;gap:24px;flex-wrap:wrap}article{width:320px;background:white;padding:24px;border-radius:12px}h1{font-size:28px}h2{font:600 16px system-ui;margin:0 0 24px}.sample{font-size:22px;font-weight:500}.sample strong{font-size:28px;display:block;margin:12px 0}.barlow{font-family:Barlow}.noto{font-family:Noto}.narrow{font-family:Noto;font-variation-settings:'wdth' 75}a{color:inherit}.logo{width:160px;background:white;padding:16px}
    </style><h1>Três tratamentos tipográficos</h1><p>Mesmos textos e tamanhos. A proposta aplicada é Barlow Semi Condensed. Este estudo mostra a fonte vetorial; a galeria principal mostra os pixels enviados à térmica.</p><main>
    <article><h2>01 · Barlow Semi Condensed — proposta</h2><div class="sample barlow"><strong>ENTREGA · HOJE</strong>Ana Exemplo · 14:00 às 14:30<strong>TROCO PARA R$ 100,00</strong>2 × Pão de fermentação natural<br>Rua das Araucárias, 1234<br>0123456789 · R$ 64,00</div></article>
    <article><h2>02 · Noto Sans — versão anterior</h2><div class="sample noto"><strong>ENTREGA · HOJE</strong>Ana Exemplo · 14:00 às 14:30<strong>TROCO PARA R$ 100,00</strong>2 × Pão de fermentação natural<br>Rua das Araucárias, 1234<br>0123456789 · R$ 64,00</div></article>
    <article><h2>03 · Noto Sans Condensed — alternativa</h2><div class="sample narrow"><strong>ENTREGA · HOJE</strong>Ana Exemplo · 14:00 às 14:30<strong>TROCO PARA R$ 100,00</strong>2 × Pão de fermentação natural<br>Rua das Araucárias, 1234<br>0123456789 · R$ 64,00</div></article>
    </main><p>A Parisine Narrow permanece uma candidata, mas não está reproduzida neste estudo: não temos o arquivo licenciado incorporado ao projeto.</p><p><a href="index.html#troco">Ver os impressos</a> · <a href="monogram.svg" download>Baixar monograma SVG</a> · <a href="monogram.png" download>Baixar PNG transparente</a></p><img class="logo" src="monogram.svg" alt="Monograma Nelson preto, sem fundo"></html>""")
    page = page.replace('<nav>', '<p><a href="typography.html">Comparar as fontes e baixar o monograma</a></p><nav>')
    (output / "index.html").write_text(page)
    (output / "measurements.tsv").write_text(
        "Cenário\tAntes_mm\tDepois_mm\n" + "\n".join(f"{title}\t{old:.1f}\t{new:.1f}" for title, old, new in metrics)
    )
    print(output / "index.html")


if __name__ == "__main__":
    main()
