"""O ensaio dos 5 cartões do WP-14 pelo motor da Nice, de ponta a ponta, em memória (#3378).

O motor é o da Nice (as regras, os moldes, os formatadores e o perfil dela), com o leitor de verdade
(``NiceReader``: o portão do Jev e a IA da rota ``intents``, pelo freio e pelo medidor da casa). Todo
o resto é de memória, das portas falsas do pacote: o canal, a sacola, a cotação, a execução, o pedido,
a loja de registros e os livros. Nada é gravado no banco do ar, nenhuma mensagem sai e nenhum pedido
nasce: o "sim" fecha um pedido de memória.

Do Shopman vem só o que se LÊ:
- o cardápio, que o leitor busca para achar o SKU;
- o nome e o preço de cada item, pelo ``Product`` do catálogo (preço base; o modificador da casa,
  a taxa e a janela da grade não entram aqui, porque são do executor de verdade, provado nos testes
  dele).

A linha P08 ("pedido na conversa") é ligada SÓ no perfil do ensaio. O perfil do ar não é tocado.

Placar: cada cartão diz o que precisa ter acontecido no fim (o pedido, os itens, o recebimento).
Cartão que reprova por falta de movimento do motor (endereço, desistir, escolher o pagamento) reprova
de verdade. A transcrição mostra onde o motor ainda não chega.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from conversational_commerce.testing.fakes import FakeCommerceExecute

ORDER_LINE = "commerce.order_in_conversation"
CHANNEL = "whatsapp"
CART = "cart-eval"
SUBJECT = "customer-eval"


@dataclass(frozen=True)
class Cartao:
    id: str
    titulo: str
    falas: tuple[str, ...]
    pedido: bool  # o "sim" precisa ter fechado um pedido
    itens: dict[str, int] = field(default_factory=dict)  # nome (dobrado) → quantidade, no pedido ou na sacola
    recebe: str | None = None
    dia: int | None = None  # deslocamento em dias a partir de hoje
    falta: str = ""  # o que o motor ainda não tem para este cartão (vira issue)


#: As falas respondem ao que a Nice pergunta hoje, como um cliente real (#3489): o quando (o dia, retirar ou
#: entregar, o horário) e a forma de pagamento, que o canal oferece em mais de uma.
CARTOES = (
    Cartao("cartao-1-retirada", "retirada, tudo numa frase",
           ("quero 2 croissants para retirar amanhã às 16h", "pode fechar", "pix", "sim"),
           pedido=True, itens={"croissant": 2}, recebe="pickup", dia=1),
    Cartao("cartao-2-entrega", "entrega com endereço",
           # Sem "sem complemento": o mundo de memória não pergunta o complemento (só a casa pergunta, provado
           # nos testes da loja) e o falso leria a fala como outro endereço, sem número.
           ("quero 1 pain de campagne com entrega", "amanhã", "Rua das Flores, 120, Centro, Londrina, CEP 86010-000",
            "pode fechar", "às 15h", "pix", "sim"),
           pedido=True, itens={"campagne": 1}, recebe="delivery", dia=1),
    Cartao("cartao-3-mudar-no-meio", "muda a quantidade depois do resumo",
           ("quero 2 croissants", "pode fechar", "amanhã", "vou retirar", "às 16h", "pix", "na verdade 3", "sim"),
           pedido=True, itens={"croissant": 3}, recebe="pickup", dia=1),
    Cartao("cartao-4-desistir", "desiste no resumo",
           ("quero 2 croissants", "pode fechar", "amanhã", "vou retirar", "às 16h", "pix", "deixa pra lá"),
           pedido=False, itens={"croissant": 2}, recebe="pickup", dia=1),
    Cartao("cartao-5-pix", "fecha com Pix",
           ("quero 2 croissants", "pode fechar", "amanhã", "vou retirar", "às 16h", "pix", "sim"),
           pedido=True, itens={"croissant": 2}, recebe="pickup", dia=1),
)


@dataclass
class Turno:
    fala: str
    resposta: str
    movimentos: list[str]
    atos: list[dict]
    leitor: str
    ms: float
    erro: str = ""
    bloqueios: dict = field(default_factory=dict)  # movimento → por que não pôde (o perfil, a precondição)
    caminho_de_hoje: str = ""  # no ar, este turno sairia pelo caminho de hoje (e por quê)


@dataclass
class Placar:
    cartao: Cartao
    passou: bool
    erros: list[str]
    turnos: list[Turno] = field(default_factory=list)


def _fold(text: str) -> str:
    from .eval_battery import fold

    return fold(text)


def _catalog_item(sku: str):
    """O item do cardápio do ar, para a cotação de memória: nome e preço base (a moeda é a do falso)."""
    from conversational_commerce.testing.fakes.synthetic_domain import SyntheticItem
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        return None
    return SyntheticItem(ref=sku, name=product.name, unit="unit", price_minor=int(product.base_price_q or 0),
                         on_hand="99", expected="0", planned="0")


class HouseGrid(FakeCommerceExecute):
    """O executor de memória com a grade da casa, como o executor da loja (``effect_site._set_fulfillment``).

    A hora dita escolhe a janela que a cobre: sem isso, o resumo do ensaio dizia "Retirada" sem o quando, e o do
    ar diz "Retirada: quarta-feira, 25/11, a partir das 15h" (ensaio no ar, cartão 1, 24/11). E o dia sem hora
    não tem janela no recibo: o falso do pacote punha uma janela dele, que a casa não conhece, e o ensaio dizia
    "entrega amanhã, horário a confirmar".
    """

    def _apply(self, command):
        from .eval_battery import janela_da_hora

        ref = super()._apply(command)
        if command.action == "set_fulfillment":
            chosen = self.state.fulfillment[command.targets[0]]
            if command.parameters.get("time"):
                chosen["window"] = janela_da_hora(str(command.parameters["time"]))
            refs = self.applied_refs[command.command_id]
            if chosen.get("window"):
                refs["window"] = chosen["window"]
            else:
                refs.pop("window", None)
        return ref


def _world():
    """O mundo de memória: as portas falsas do pacote, com o canal da Nice e a sacola vazia."""
    from conversational_commerce.testing.fakes import FakeWorld

    from shopman.shop.conversational.commerce_read import conversation_payment_methods

    world = FakeWorld()
    world.commerce_execute = HouseGrid(world.clock, world.faults, world.state)
    world.channel.name = CHANNEL
    # As formas que a conversa do canal oferece (as do ar, sem dinheiro), não as do falso: com as do falso,
    # o "pix" virava forma não oferecida e a Nice respondia a frase do dinheiro.
    world.state.payment_methods = tuple(conversation_payment_methods(CHANNEL))
    # Os horários de retirada da grade da casa: com eles o falso exige o quando antes dos termos, como o
    # requirements do ar (#3482). Sem eles, o cartão fechava um pedido que a casa não grava.
    from shopman.shop.services.fulfillment_window import canonical_slots

    world.state.pickup_slots = tuple(str(slot.get("label") or slot["ref"]) for slot in canonical_slots())
    world.state.delivery_windows = world.state.pickup_slots  # a mesma grade da casa (fulfillment_window)
    world.state.carts = {CART: {}}
    world.state.cart_owner = {CART: SUBJECT}
    world.state.versions = {CART: 1}
    items = world.state.items

    class Catalogo(dict):
        """Os itens do cardápio do ar, lidos sob demanda (nenhuma escrita)."""

        def __missing__(self, sku):
            item = _catalog_item(sku)
            if item is None:
                raise KeyError(sku)
            self[sku] = item
            return item

        def get(self, sku, default=None):
            try:
                return self[sku]
            except KeyError:
                return default

    world.state.items = Catalogo(items)
    return world


DECIDED_AT = "2026-11-23T00:00:00.000000Z"


def _profile():
    """O perfil da Nice, com a P08 aprovada SÓ aqui (o do ar não muda)."""
    from .profile import build_profile

    profile = build_profile(environment="live")
    lines = [dataclasses.replace(line, state="approved", decided_at=line.decided_at or DECIDED_AT)
             if line.id == ORDER_LINE else line for line in profile.lines]
    return dataclasses.replace(profile, lines=tuple(lines))


def engine_for(reader: Callable, *, today: date):
    """O motor da Nice sobre o mundo de memória. ``reader(conversa, linhas)`` monta o leitor."""
    from conversational_commerce.contracts import IdentityEvidence
    from conversational_commerce.engine import Engine, Ports
    from conversational_commerce.engine.state import Subject

    from shopman.shop.models import Conversation

    from .turn_framework import NiceRules, nice_formatters, nice_templates

    world = _world()
    conversa = Conversation(channel_ref=CHANNEL)  # nunca gravada

    def linhas(_conversa):
        return [{"sku": sku, "qty": int(Decimal(qty)), "name": getattr(world.state.items.get(sku), "name", sku)}
                for sku, qty in world.state.carts.get(CART, {}).items()]

    ports = Ports.from_world(world)
    ports.model = reader(conversa, linhas)
    evidence = IdentityEvidence(kind="transport_subject", ref=SUBJECT, assurance="transported")

    def subject_of(ctx, event):
        return Subject(subject_ref=SUBJECT, identity_evidence=(evidence,), cart_ref=CART)

    engine = Engine(ports, _profile(), rules=NiceRules(), subject_of=subject_of,
                    house_templates=nice_templates(), formatters=nice_formatters())
    return engine, world


def _conferir(cartao: Cartao, world, today: date) -> list[str]:
    erros: list[str] = []
    orders = list(world.state.orders.values())
    if cartao.pedido and not orders:
        erros.append("nenhum pedido fechado")
    if not cartao.pedido and orders:
        erros.append("fechou um pedido que não devia")
    nomes = {sku: _fold(getattr(world.state.items.get(sku), "name", sku)) for sku in world.state.carts.get(CART, {})}
    sacola = {nomes[sku]: int(Decimal(qty)) for sku, qty in world.state.carts.get(CART, {}).items()}
    for produto, quantidade in cartao.itens.items():
        achado = next((q for nome, q in sacola.items() if produto in nome), None)
        if achado != quantidade:
            erros.append(f"{produto}: {achado if achado is not None else '-'}, esperado {quantidade}")
    recebimento = world.state.fulfillment.get(CART, {})
    if cartao.recebe and recebimento.get("mode") != cartao.recebe:
        erros.append(f"recebimento {recebimento.get('mode') or '-'}, esperado {cartao.recebe}")
    if cartao.dia is not None and recebimento.get("date") != (today + timedelta(days=cartao.dia)).isoformat():
        erros.append(f"dia {recebimento.get('date') or '-'}, esperado +{cartao.dia}")
    return erros


def rodar(reader_for: Callable, *, today: date, max_calls: int, max_usd: float, model: str = "",
          only: str = "", classes: frozenset[str] | None = None) -> tuple[list[Placar], dict]:
    """Os cartões pelo motor. ``classes``: as classes ligadas que o juiz considera (todas, sem ela), para
    ensaiar a config da loja ("informar" e "pedido", sem "encaminhar")."""
    from .eval_battery import leitura_do_cardapio

    with leitura_do_cardapio():
        return _rodar(reader_for, today=today, max_calls=max_calls, max_usd=max_usd, model=model, only=only,
                      classes=classes)


def _rodar(reader_for: Callable, *, today: date, max_calls: int, max_usd: float, model: str, only: str,
           classes: frozenset[str] | None) -> tuple[list[Placar], dict]:
    from conversational_commerce.ports import TrustedContext
    from conversational_commerce.testing.journeys import j4

    from shopman.shop import ai_governor

    from .turn_framework import ACTION_CLASSES, judge, nice_templates

    totais = {"chamadas": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "interrompido": "", "erros": []}
    placares: list[Placar] = []
    for cartao in CARTOES:
        if only and only not in cartao.id:
            continue
        leitores: list = []

        def reader(conversa, linhas, leitores=leitores):
            leitor = reader_for(conversa, linhas)
            leitores.append(leitor)
            return leitor

        engine, world = engine_for(reader, today=today)
        leitor = leitores[0]
        ctx = TrustedContext(tenant=engine.profile.tenant, environment="live", subject=SUBJECT)
        turnos: list[Turno] = []
        for numero, fala in enumerate(cartao.falas, 1):
            if totais["chamadas"] >= max_calls:
                totais["interrompido"] = f"teto de {max_calls} chamadas"
                break
            if max_usd and totais["usd"] >= max_usd:
                totais["interrompido"] = f"teto de US$ {max_usd:.2f}"
                break
            leitor.last_usage, leitor.last_error = None, ""
            # O relógio de memória anda entre as falas, como na conversa: a confirmação vem DEPOIS do resumo.
            if numero > 1:
                world.clock.advance(30)
            started = time.perf_counter()
            result = engine.turn(ctx, j4.message(f"{cartao.id}-{numero}", fala))
            ms = (time.perf_counter() - started) * 1000
            usage = leitor.last_usage
            tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
            if usage is not None:
                totais["chamadas"] += 1
            totais["tokens_in"] += tin
            totais["tokens_out"] += tout
            if model:
                totais["usd"] += ai_governor.estimate_usd(model, tokens_in=tin, tokens_out=tout)
            if leitor.last_error:
                totais["erros"].append(f"{cartao.id} #{numero}: {leitor.last_error}")
            understanding = result.understanding
            atos = [{"act": a.act, "fields": dict(a.fields)} for a in (understanding.acts if understanding else ())]
            if result.text:
                resposta = result.text
            elif result.reply is not None:
                achados = ", ".join(f.code for f in result.reply.verification.findings)
                resposta = f"(segurada pela verificação: {achados})"
            else:
                resposta = "(sem resposta do motor)"
            bloqueios = {c.move: list(c.blocked_by) for c in (result.decision.candidates if result.decision else ())
                         if c.blocked_by and c.move not in result.chosen_moves}
            # O mesmo juiz do turno vivo: com as classes ligadas, o turno sai pelo motor só se todo
            # molde usado tem a frase da Nice. Senão, no ar, ele sairia pelo caminho de hoje.
            veredito = judge(result, enabled=frozenset(ACTION_CLASSES) if classes is None else classes,
                             approved=frozenset(nice_templates()))
            turnos.append(Turno(fala, resposta, list(result.chosen_moves), atos,
                                understanding.reader.name if understanding else "-", ms, leitor.last_error,
                                bloqueios, "" if veredito.eligible else veredito.reason))
        erros = _conferir(cartao, world, today) if not totais["interrompido"] else ["não rodou inteiro"]
        placares.append(Placar(cartao, not erros, erros, turnos))
        if totais["interrompido"]:
            break
    return placares, totais


def relatorio(placares: list[Placar], totais: dict) -> str:
    """O placar e a transcrição por cartão, em texto puro: a fala, a resposta da Nice e o que se leu."""
    linhas = [f"cartões: {sum(p.passou for p in placares)} / {len(placares)} passaram",
              f"chamadas à IA: {totais['chamadas']} | tokens: {totais['tokens_in']} in, {totais['tokens_out']} out"
              f" | custo estimado: US$ {totais.get('usd', 0.0):.4f}"]
    if totais.get("interrompido"):
        linhas.append(f"INTERROMPIDO: {totais['interrompido']}")
    linhas.extend(f"ERRO DA IA: {erro}" for erro in totais.get("erros", [])[:10])
    for placar in placares:
        linhas.append("")
        linhas.append(f"[{'ok' if placar.passou else 'FALHOU'}] {placar.cartao.id}: {placar.cartao.titulo}")
        for turno in placar.turnos:
            atos = "; ".join(a["act"] + (f" {a['fields']}" if a["fields"] else "") for a in turno.atos)
            linhas.append(f"  Cliente: {turno.fala}")
            linhas.append("  Nice: " + turno.resposta.replace("\n", "\n        "))
            linhas.append(f"    leitura ({turno.leitor}, {turno.ms:.0f} ms): {atos or '-'}")
            linhas.append(f"    movimentos: {', '.join(turno.movimentos) or '-'}")
            if turno.caminho_de_hoje:
                linhas.append(f"    no ar: sairia pelo caminho de hoje ({turno.caminho_de_hoje})")
            for movimento, motivos in turno.bloqueios.items():
                linhas.append(f"    bloqueado: {movimento} ({', '.join(motivos)})")
            if turno.erro:
                linhas.append(f"    erro da IA: {turno.erro}")
        if not placar.passou:
            linhas.extend(f"    ✗ {erro}" for erro in placar.erros)
            if placar.cartao.falta:
                linhas.append(f"    o que falta no motor: {placar.cartao.falta}")
    return "\n".join(linhas)
