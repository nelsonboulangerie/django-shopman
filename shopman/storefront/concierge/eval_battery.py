"""O ensaio do leitor da Nice no ar: a bateria de 56 pedidos pela IA do perfil, sem efeito e sem escrita.

Passo 5 do pedido pelo motor (dono, 23/11/2026: a bateria roda no app do ar, pela conexão DeepSeek que
já existe, sem chave em máquina nenhuma). Cada caso é uma conversa: as falas da cliente, na ordem, e o
que a leitura precisa ter entendido no fim (os produtos e as quantidades, o dia, retirada ou entrega, e
a janela da grade da casa que cobre a hora dita).

O que roda é o leitor de verdade (``NiceReader``: o portão do Jev e a extração pela rota ``intents``,
com o freio e o medidor de gasto da casa). A sacola e o recebimento são acumulados em memória, numa
conversa que não é gravada: nenhum efeito, nenhuma mensagem, nenhuma linha nova no banco (o medidor de
gasto da casa registra as chamadas, como toda chamada paga). O produto é conferido pelo NOME do item no
catálogo do ar, não pelo SKU de um teste.

O texto da resposta não entra aqui: ele depende do motor ligado (linha P08) e da decisão da #3374.
"""

from __future__ import annotations

import calendar
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

#: O produto esperado, pelo nome no catálogo (dobrado: sem acento, minúsculo).
C, P, B, CA, PF, S = "croissant", "pain au chocolat", "baguete", "campanha", "pao frances", "sonho"


@dataclass(frozen=True)
class Caso:
    id: str
    falas: tuple[str, ...]
    sacola: dict[str, int]
    dia: object = None  # deslocamento em dias, "sabado", "dia25", ou None (não confere)
    recebe: str | None = None  # "pickup" / "delivery" / None (não confere)
    janela: str | None = None  # ref da janela da grade, ou None (não confere)
    grupo: str = ""


def _c(id, falas, sacola, **kw):
    return Caso(id=id, falas=(falas,) if isinstance(falas, str) else tuple(falas), sacola=sacola, **kw)


CASOS = (
    # ── Tudo numa frase, retirada ──
    _c("frase-cartao-1", "quero 2 croissants para retirar amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-cartao-1-sem-acento", "quero 2 croissants para retirar amanha as 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-busco-16h", "2 croissant pra amanha, busco 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-pegar-10h", "quero 3 pain au chocolat pra pegar amanhã às 10h", {P: 3}, dia=1, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-passo-ai", "me separa 2 baguetes pra amanhã, passo aí às 13h", {B: 2}, dia=1, recebe="pickup", janela="slot-12", grupo="uma frase"),
    _c("frase-a-tarde", "quero 1 pão de campanha para retirar amanhã à tarde", {CA: 1}, dia=1, recebe="pickup", grupo="uma frase"),
    _c("frase-vou-buscar-no-fim", "vou querer 4 croissants amanhã às 15h, vou buscar", {C: 4}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dois-produtos", "queria 2 croissants e 2 pain au chocolat pra retirar amanhã às 16h", {C: 2, P: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-sabado", "quero 2 croissants pra retirar sábado às 10h", {C: 2}, dia="sabado", recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-dia-25", "quero 2 croissants para retirar dia 25 às 16h", {C: 2}, dia="dia25", recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dd-mm", "quero 2 croissants para retirar {dm+2} às 16h", {C: 2}, dia=2, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-depois-de-amanha", "quero 2 croissants pra depois de amanhã, retiro às 9h", {C: 2}, dia=2, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-numero-por-extenso", "dois croissants pra amanhã, vou buscar às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-uma-baguete", "quero uma baguete pra amanhã, retiro 16h", {B: 1}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-telegrafica", "2 croissants amanhã 16h retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-com-saudacao", "Oi! Quero 2 croissants pra retirar amanhã às 16h, por favor", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-bom-dia-encomendar", "bom dia, queria encomendar 6 croissants pra amanhã, busco às 9h", {C: 6}, dia=1, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-so-horario", "quero 2 croissant pra amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-erro-digitacao", "quero 2 croisants pra amanhã, busco 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="digitação"),
    _c("frase-abreviada", "qro 2 croissants p amanha 16h retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="digitação"),
    _c("frase-16h30", "quero 2 croissants pra buscar amanhã às 16h30", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-16-00", "quero 2 croissants pra amanhã 16:00 retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dez-unidades", "quero 10 croissants pra retirar amanhã às 16h", {C: 10}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-meia-duzia", "quero meia dúzia de croissants pra amanhã, busco às 16h", {C: 6}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    # ── Buscar, pegar, passo aí ──
    _c("verbo-pegar", "quero 2 croissants, vou pegar amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-passo-ai", "quero 2 croissants, passo aí amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-reserva-pego", "reserva 2 croissants pra mim pra amanhã, pego às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-separa-passo-pra-pegar", "separa 2 croissants pra amanhã às 16h que eu passo pra pegar", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-de-manha", "quero 2 croissants pra amanhã de manhã, retiro às 9h", {C: 2}, dia=1, recebe="pickup", janela="slot-09", grupo="verbos"),
    _c("verbo-cartao-1-segunda-frase",
       "voce nao entendeu... quero 2 croissants para amanha e eu vou ai buscar (retirada) as 16h... entendeu?",
       {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    # ── Só o pedido, sem quando ──
    _c("so-pedido", "quero 2 croissants", {C: 2}, grupo="só o pedido"),
    _c("so-pedido-hoje", "quero 2 croissants hoje", {C: 2}, grupo="só o pedido"),
    _c("so-pedido-pra-amanha", "quero 2 croissants para amanhã", {C: 2}, grupo="só o pedido"),
    # ── Entrega ──
    _c("entrega-com", "quero 2 croissants com entrega amanhã", {C: 2}, dia=1, recebe="delivery", grupo="entrega"),
    _c("entrega-entregar", "quero 1 pão de campanha pra entregar amanhã", {CA: 1}, dia=1, recebe="delivery", grupo="entrega"),
    _c("entrega-em-casa", "me manda 2 baguetes em casa amanhã", {B: 2}, dia=1, recebe="delivery", grupo="entrega"),
    # ── Espalhado em várias falas ──
    _c("espalhado-tres", ["quero 2 croissants", "pra amanhã", "vou buscar às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-oi-primeiro", ["oi", "quero 2 croissants", "amanhã às 16h, retirada"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-dia-depois-hora", ["quero 2 croissants pra amanhã", "busco às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-telegrafico", ["2 croissants", "retirada amanhã 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-sabado", ["quero 3 baguetes", "é pra sábado", "passo aí às 10h"], {B: 3}, dia="sabado", recebe="pickup", janela="slot-09", grupo="espalhado"),
    _c("espalhado-dois-produtos", ["quero 2 croissants", "e 1 pão de campanha", "pra amanhã às 16h, vou retirar"], {C: 2, CA: 1}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-so-a-hora", ["quero 2 croissants pra retirar amanhã", "às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    # ── Correção no meio ──
    _c("corrige-na-verdade-3", ["quero 2 croissants", "na verdade 3"], {C: 3}, grupo="correção"),
    _c("corrige-sao-3-com-data", ["quero 2 croissants pra amanhã às 16h, vou buscar", "na verdade são 3"], {C: 3}, dia=1, recebe="pickup", janela="slot-15", grupo="correção"),
    _c("corrige-nao-quero-4", ["quero 2 croissants", "não, quero 4"], {C: 4}, grupo="correção"),
    _c("corrige-hora", ["quero 2 croissants pra retirar amanhã às 16h", "melhor às 10h"], {C: 2}, dia=1, recebe="pickup", janela="slot-09", grupo="correção"),
    _c("corrige-dia", ["quero 2 croissants pra retirar amanhã", "na verdade depois de amanhã"], {C: 2}, dia=2, recebe="pickup", grupo="correção"),
    _c("corrige-tira-um-produto", ["quero 2 croissants e 2 pain au chocolat", "tira o pain au chocolat"], {C: 2}, grupo="correção"),
    _c("corrige-troca-produto", ["quero 2 croissants", "troca por pain au chocolat"], {P: 2}, grupo="correção"),
    _c("corrige-tira-um", ["quero 3 croissants", "tira 1"], {C: 2}, grupo="correção"),
    _c("corrige-retira-o-croissant", ["quero 2 croissants pra amanhã às 16h, vou buscar", "retira o croissant"], {}, grupo="correção"),
    # ── Produto que não tem (na data, ou nunca) ──
    _c("sem-fora-de-venda", "quero 2 brioches pra amanhã", {}, grupo="não tem"),
    _c("sem-hoje-tem-amanha", "quero 2 sonhos pra retirar amanhã às 16h", {S: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="não tem"),
    _c("sem-fornada-na-data", "quero 2 sonhos pra retirar amanhã às 16h", {}, grupo="não tem"),
    _c("sem-no-cardapio", "quero 2 empadas pra amanhã", {}, grupo="não tem"),
)



def fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(text or "").casefold())
                   if not unicodedata.combining(ch))


def dia(spec, today: date) -> str:
    if isinstance(spec, int):
        return (today + timedelta(days=spec)).isoformat()
    if spec == "sabado":
        return (today + timedelta(days=(5 - today.weekday()) % 7 or 7)).isoformat()
    if spec == "dia25":
        if today.day < 25:
            return today.replace(day=25).isoformat()
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return date(year, month, min(25, calendar.monthrange(year, month)[1])).isoformat()
    raise ValueError(spec)


def texto(fala: str, today: date) -> str:
    """``{dm+2}`` vira a data de daqui a dois dias em dd/mm (a bateria roda em qualquer dia)."""
    for offset in range(8):
        fala = fala.replace(f"{{dm+{offset}}}", (today + timedelta(days=offset)).strftime("%d/%m"))
    return fala


def janela_da_hora(hora: str) -> str:
    """A janela da grade da casa que cobre a hora dita (a mesma regra do executor da loja)."""
    from shopman.shop.services.fulfillment_window import canonical_slots

    from .order_closing import _match_slot

    hours, minutes = (int(part) for part in hora.split(":"))
    slots = [{"ref": s["ref"], "label": s.get("label", "")} for s in canonical_slots()]
    chosen = _match_slot(slots, hours * 60 + minutes)
    return str(chosen["ref"]) if chosen else ""


@dataclass
class Fala:
    texto: str
    leitor: str
    atos: list
    ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    erro: str = ""  # o erro verdadeiro da IA, quando a fala caiu para a regra local


@dataclass
class Resultado:
    caso: Caso
    passou: bool
    erros: list[str]
    falas: list[Fala] = field(default_factory=list)
    sacola: dict[str, int] = field(default_factory=dict)
    recebimento: dict[str, str] = field(default_factory=dict)


def _nomes(skus) -> dict[str, str]:
    from shopman.offerman.models import Product

    return {p.sku: p.name for p in Product.objects.filter(sku__in=list(skus))}


def conferir(caso: Caso, sacola: dict[str, int], recebimento: dict[str, str], today: date) -> list[str]:
    """O que a leitura entendeu, contra o esperado. Lista vazia: passou."""
    erros: list[str] = []
    nomes = {sku: fold(nome) for sku, nome in _nomes(sacola).items()}
    restante = dict(sacola)
    for produto, quantidade in caso.sacola.items():
        sku = next((sku for sku in restante if produto in nomes.get(sku, fold(sku))), None)
        if sku is None:
            erros.append(f"faltou {produto} x{quantidade}")
            continue
        if restante.pop(sku) != quantidade:
            erros.append(f"{produto}: {sacola[sku]}, esperado {quantidade}")
    erros.extend(f"sobrou {nomes.get(sku, sku)} x{q}" for sku, q in restante.items())
    if caso.dia is not None and recebimento.get("date") != dia(caso.dia, today):
        erros.append(f"dia {recebimento.get('date') or '-'}, esperado {dia(caso.dia, today)}")
    if caso.recebe and recebimento.get("mode") != caso.recebe:
        erros.append(f"recebimento {recebimento.get('mode') or '-'}, esperado {caso.recebe}")
    if caso.janela:
        lida = janela_da_hora(recebimento["time"]) if recebimento.get("time") else ""
        if lida != caso.janela:
            erros.append(f"janela {lida or '-'} (hora {recebimento.get('time') or '-'}), esperado {caso.janela}")
    return erros


def rodar(reader_for: Callable, *, channel_ref: str, today: date, max_calls: int, max_usd: float = 0.0,
          model: str = "", only: str = "") -> tuple[list[Resultado], dict]:
    """A bateria pelo leitor. ``reader_for(conversa, linhas)`` monta o leitor com a sacola em memória."""
    from conversational_commerce.engine.acts import ACTS
    from conversational_commerce.ports import InterpretRequest, ModelRequest, TrustedContext

    from shopman.shop.models import Conversation

    from shopman.shop import ai_governor

    totais = {"chamadas": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "interrompido": "", "erros": []}
    resultados: list[Resultado] = []
    for caso in CASOS:
        if only and only not in caso.id:
            continue
        sacola: dict[str, int] = {}
        recebimento: dict[str, str] = {}
        conversa = Conversation(channel_ref=channel_ref)  # nunca gravada

        def linhas(_conversa, sacola=sacola):
            return [{"sku": sku, "qty": qty} for sku, qty in sacola.items()]

        reader = reader_for(conversa, linhas)
        ctx = TrustedContext(tenant="eval", environment="shadow", subject=None)
        falas: list[Fala] = []
        for numero, bruta in enumerate(caso.falas, 1):
            if totais["chamadas"] >= max_calls:
                totais["interrompido"] = f"teto de {max_calls} chamadas"
                break
            if max_usd and totais["usd"] >= max_usd:
                totais["interrompido"] = f"teto de US$ {max_usd:.2f}"
                break
            fala = texto(bruta, today)
            request = InterpretRequest(
                request=ModelRequest(purpose="interpret", data_class="redacted",
                                     budget={"max_calls": 1, "max_spend": {"amount_minor": 0, "currency": "BRL"}}),
                event_id=f"eval-{caso.id}-{numero}", content_ref=f"text:{fala}", allowed_acts=ACTS)
            started = time.perf_counter()
            reader.last_usage, reader.last_error = None, ""
            understanding, consumption = reader.interpret(ctx, request)
            ms = (time.perf_counter() - started) * 1000
            totais["chamadas"] += int(consumption.calls)
            usage = reader.last_usage
            tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
            totais["tokens_in"] += tin
            totais["tokens_out"] += tout
            if model:
                totais["usd"] += ai_governor.estimate_usd(model, tokens_in=tin, tokens_out=tout)
            if reader.last_error:
                totais["erros"].append(f"{caso.id} #{numero}: {reader.last_error}")
            atos = []
            for act in understanding.acts:
                fields = dict(act.fields)
                atos.append({"act": act.act, "fields": fields})
                if act.act == "change_quantity" and fields.get("item") and fields.get("quantity") is not None:
                    quantidade = int(str(fields["quantity"]))
                    if quantidade:
                        sacola[str(fields["item"])] = quantidade
                    else:
                        sacola.pop(str(fields["item"]), None)
                elif act.act == "choose_fulfillment":
                    recebimento.update({k: str(v) for k, v in fields.items() if k in ("date", "mode", "time")})
            falas.append(Fala(fala, understanding.reader.name, atos, ms, tin, tout, reader.last_error))
        erros = conferir(caso, sacola, recebimento, today) if not totais["interrompido"] else ["não rodou inteiro"]
        resultados.append(Resultado(caso, not erros, erros, falas, sacola, recebimento))
        if totais["interrompido"]:
            break
    return resultados, totais


def relatorio(resultados: list[Resultado], totais: dict) -> str:
    """O placar e a transcrição, em texto puro, para o console."""
    linhas = []
    passou = sum(r.passou for r in resultados)
    usd = totais.get("usd", 0.0)
    tempos = sorted(f.ms for r in resultados for f in r.falas)
    p95 = tempos[max(0, int(len(tempos) * 0.95) - 1)] if tempos else 0.0
    linhas.append(f"bateria: {passou} / {len(resultados)} passaram")
    linhas.append(f"chamadas à IA: {totais['chamadas']} | tokens: {totais['tokens_in']} in, {totais['tokens_out']} out"
                  f" | custo estimado: US$ {usd:.4f} | latência p95: {p95:.0f} ms")
    if totais.get("interrompido"):
        linhas.append(f"INTERROMPIDO: {totais['interrompido']}")
    quedas = sum(1 for r in resultados for f in r.falas if f.leitor == "concierge-local-rules")
    if quedas:
        linhas.append(f"ATENÇÃO: {quedas} falas caíram para a regra local (a IA não respondeu)")
    linhas.extend(f"ERRO DA IA: {erro}" for erro in totais.get("erros", [])[:10])
    for r in resultados:
        linhas.append("")
        linhas.append(f"[{'ok' if r.passou else 'FALHOU'}] {r.caso.id} ({r.caso.grupo})")
        for f in r.falas:
            atos = "; ".join(a["act"] + (f" {a['fields']}" if a["fields"] else "") for a in f.atos)
            linhas.append(f"  > {f.texto}")
            linhas.append(f"    {f.leitor} · {f.ms:.0f} ms · {atos}")
            if f.erro:
                linhas.append(f"    erro da IA: {f.erro}")
        if not r.passou:
            linhas.extend(f"    ✗ {erro}" for erro in r.erros)
    return "\n".join(linhas)
