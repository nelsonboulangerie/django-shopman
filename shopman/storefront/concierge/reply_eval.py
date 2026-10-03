"""Placar da Concierge contra o conjunto de mensagens reais (golden set).

Fatia 1 do estudo ``docs/plans/CONCIERGE-ARQUITETURA-ALVO.md`` (seção 6.3). Roda o
caminho de HOJE (``service.run_turn``: triagem, mídia, cortesia, agente) sobre
cada caso de ``golden_set.json`` até o ponto em que ele decide quem responde, e
compara com o rótulo conferido:

- **destino** (``answer``/``team``/``other_desk``): a mensagem foi para o lugar
  certo? É a medida de segurança;
- **intenção**: a triagem acertou uma das intenções aceitas do caso?
- **camada**: quem responde hoje (cortesia, mídia, equipe, ou o agente com o
  modelo) contra quem deveria responder na arquitetura alvo. Hoje tudo que não
  é cortesia, mídia ou equipe vai ao agente, inclusive o "sim" e o link: é o
  número que a arquitetura alvo quer derrubar;
- **custo e tempo** da triagem, medidos pela régua (``metrics.TurnMeter``), e o
  tempo das respostas do alpha gravado no caso (``alpha.reply_ms``).

Sem rede por padrão (``classifier="rules"``). Com ``model`` ou ``jev`` a triagem
chama o provedor de verdade com o texto já redigido do caso.

O agente (laço com o modelo e as ferramentas) não roda aqui: ele precisa do
catálogo e da sacola vivos. O custo e o tempo dele saem do que a régua grava em
produção (``production_summary``).
"""

from __future__ import annotations

import json
import pathlib
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.test import override_settings

GOLDEN_PATH = pathlib.Path(__file__).with_name("golden_set.json")
LAYERS = ("courtesy", "media", "context", "answer", "agent", "team", "other_desk")
LAYER_LABELS = {
    "courtesy": "cortesia",
    "media": "link ou mídia",
    "context": "depende do contexto",
    "answer": "intenção clara",
    "agent": "conversa solta",
    "team": "equipe",
    "other_desk": "outra mesa",
}
#: Quem responde no caminho de hoje (``current_layer``).
TODAY_LABELS = {
    "courtesy": "cortesia",
    "media": "mensagem de mídia",
    "agent": "agente com o modelo",
    "team": "equipe",
    "other_desk": "outra mesa",
}
#: Camadas em que a arquitetura alvo chama o modelo de linguagem (redação C4 ou agente C6).
TARGET_MODEL_LAYERS = frozenset({"answer", "agent"})
#: ``jev-shadow`` não chama ninguém: usa a intenção que o Jev deu em sombra no
#: alpha, gravada no caso (``alpha.jev``), e mede só os casos observados.
CLASSIFIERS = ("rules", "model", "jev", "jev-shadow")


def load_golden(path=None) -> list[dict]:
    data = json.loads(pathlib.Path(path or GOLDEN_PATH).read_text(encoding="utf-8"))
    return list(data["cases"])


def current_layer(case: dict, decision) -> str:
    """Quem responde este caso no caminho de hoje (a mesma ordem de ``run_turn``)."""
    from .service import CONVERSATIONAL_MESSAGE_TYPES
    from .small_talk import small_talk_kind

    if decision.escalates:
        return "other_desk" if decision.destination == "other_desk" else "team"
    if case.get("message_type", "text") not in CONVERSATIONAL_MESSAGE_TYPES:
        return "media"
    if small_talk_kind(case["text"]):
        return "courtesy"
    return "agent"


@dataclass
class CaseResult:
    case: dict
    layer: str
    intent: str
    destination: str
    source: str
    cost_usd: float | None
    triage_ms: float

    @property
    def expected(self) -> dict:
        return self.case["expected"]

    @property
    def destination_ok(self) -> bool:
        return self.destination == self.expected["destination"]

    @property
    def intent_ok(self) -> bool | None:
        wanted = self.expected.get("intent") or ""
        if not wanted:
            return None
        return self.intent in {wanted, *self.expected.get("accept", [])}


@dataclass
class Report:
    classifier: str
    results: list[CaseResult] = field(default_factory=list)

    def render(self, *, show_misses: int = 15) -> str:
        results = self.results
        total = len(results)
        if not total:
            return "Conjunto vazio."
        by_layer = Counter(r.expected["layer"] for r in results)
        lines = [
            f"{total} mensagens reais ("
            + ", ".join(f"{by_layer[layer]} {LAYER_LABELS[layer]}" for layer in LAYERS if by_layer[layer])
            + f"). Triagem por: {self.classifier}.",
            "",
        ]
        dest_ok = sum(r.destination_ok for r in results)
        sensitive = [r for r in results if r.expected["destination"] != "answer"]
        caught = sum(r.destination_ok for r in sensitive)
        wrongly_escalated = sum(1 for r in results if r.expected["destination"] == "answer" and not r.destination_ok)
        lines.append(
            f"Destino certo: {dest_ok}/{total} ({dest_ok / total:.0%}) · equipe e outra mesa achadas: "
            f"{caught}/{len(sensitive)} · mandadas à equipe sem precisar: {wrongly_escalated}"
        )
        scored = [r for r in results if r.intent_ok is not None]
        intent_ok = sum(bool(r.intent_ok) for r in scored)
        if scored:
            lines.append(f"Intenção certa: {intent_ok}/{len(scored)} ({intent_ok / len(scored):.0%}) das que têm intenção")
        lines.append("")
        lines.append("Quem responde, hoje × arquitetura alvo:")
        matrix: dict[str, Counter] = defaultdict(Counter)
        for r in results:
            matrix[r.expected["layer"]][r.layer] += 1
        for layer in LAYERS:
            if not by_layer[layer]:
                continue
            today = ", ".join(f"{TODAY_LABELS.get(k, k)} {v}" for k, v in matrix[layer].most_common())
            lines.append(f"  {LAYER_LABELS[layer]} ({by_layer[layer]}): hoje vai para {today}")
        today_model = sum(1 for r in results if r.layer == "agent")
        target_model = sum(1 for r in results if r.expected["layer"] in TARGET_MODEL_LAYERS)
        lines.append(
            f"Chegam ao modelo de resposta: hoje {today_model} ({today_model / total:.0%}); na arquitetura alvo "
            f"{target_model} ({target_model / total:.0%})."
        )
        lines.append("")
        costs = [r.cost_usd for r in results if r.cost_usd is not None]
        latencies = [r.triage_ms for r in results]
        if self.classifier == "jev-shadow":
            cost_line = "custo não gravado na sombra (cerca de 500 tokens a US$ 0,042/M, estudo seção 2)"
        elif costs:
            cost_line = f"US$ {sum(costs) / len(costs):.6f} por mensagem (US$ {sum(costs):.4f} no conjunto)"
        else:
            cost_line = "custo desconhecido (modelo fora da tabela)"
        lines.append(
            f"Triagem: {cost_line} · tempo p50 {_q(latencies, 0.5):.0f} ms, p95 {_q(latencies, 0.95):.0f} ms"
        )
        lines.extend(_alpha_lines(results))
        misses = [r for r in results if not r.destination_ok or r.intent_ok is False]
        if misses and show_misses:
            lines.append("")
            lines.append(f"Erros ({len(misses)}; os primeiros {min(show_misses, len(misses))}):")
            for r in misses[:show_misses]:
                wanted = r.expected.get("intent") or "sem intenção"
                lines.append(
                    f"  {r.case['ref']} \"{r.case['text'][:60]}\": esperado {r.expected['destination']}/{wanted}, "
                    f"saiu {r.destination}/{r.intent} ({r.source})"
                )
        return "\n".join(lines)


def _q(values, quantile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    return statistics.quantiles(values, n=100, method="inclusive")[int(quantile * 100) - 1]


def _alpha_lines(results: list[CaseResult]) -> list[str]:
    """O tempo das respostas que o alpha deu na hora (gravado no caso), por ferramentas chamadas."""
    measured = [r.case["alpha"] for r in results if "reply_ms" in r.case.get("alpha", {})]
    if not measured:
        return []
    lines = [f"Resposta do alpha, medida na hora ({len(measured)} casos respondidos, inclui 1 s de espera proposital):"]
    groups: dict[str, list[int]] = defaultdict(list)
    for alpha in measured:
        tools = int(alpha.get("tool_calls") or 0)
        groups["0" if tools == 0 else "1" if tools == 1 else "2 ou mais"].append(int(alpha["reply_ms"]))
    for name in ("0", "1", "2 ou mais"):
        values = groups.get(name)
        if values:
            lines.append(
                f"  {name} ferramenta(s): {len(values)} casos, p50 {_q(values, 0.5) / 1000:.1f} s, "
                f"máximo {max(values) / 1000:.1f} s"
            )
    return lines


def run(cases: list[dict], *, classifier: str = "rules", model: str = "", client=None) -> Report:
    """Cada caso pela triagem de hoje, medida pela régua. Erro do provedor vale a regra (como em produção)."""
    from django.conf import settings

    from . import metrics, triage

    if classifier not in CLASSIFIERS:
        raise ValueError(f"classificador desconhecido: {classifier}")
    if classifier == "jev-shadow":
        return _run_shadow(cases)
    config = {
        **(getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}),
        "triage_classifier": "jev" if classifier == "jev" else "anthropic",
        "triage_with_model": classifier != "rules",
    }
    if model:
        config["triage_model"] = model
    report = Report(classifier=classifier if not model else f"{classifier}:{model}")
    with override_settings(SHOPMAN_CONCIERGE=config):
        for case in cases:
            meter = metrics.TurnMeter()
            context = [(line["who"], line["text"]) for line in case.get("previous", [])]
            triage_client = metrics.triage_client_for(meter, client) if classifier != "rules" else None
            if classifier != "rules" and triage_client is None:
                raise ValueError(
                    f"triagem por {classifier} indisponível neste ambiente (credencial ou aprovação do provedor)."
                )
            with meter.stage("triage"):
                decision = triage.decide(case["text"], context=context, client=triage_client)
            usage = meter.as_usage()
            report.results.append(
                CaseResult(
                    case=case,
                    layer=current_layer(case, decision),
                    intent=decision.intent if decision.source != "default" else "",
                    destination=decision.destination,
                    source=decision.source,
                    cost_usd=usage["cost_usd"],
                    triage_ms=meter.stages_ms.get("triage", 0.0),
                )
            )
    return report


def production_summary(*, days: int = 7) -> str:
    """O que a régua gravou nas respostas reais (``ConversationMessage.usage``), por camada."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.shop.models import ConversationMessage

    rows = list(
        ConversationMessage.objects.filter(
            kind=ConversationMessage.Kind.REPLY,
            created_at__gte=timezone.now() - timedelta(days=days),
            usage__version__gte=1,
        ).values_list("usage", flat=True)
    )
    if not rows:
        return f"Nenhuma resposta com a régua gravada nos últimos {days} dias."
    lines = [f"{len(rows)} respostas com a régua nos últimos {days} dias:"]
    by_layer: dict[str, list[dict]] = defaultdict(list)
    for usage in rows:
        by_layer[usage.get("layer") or "?"].append(usage)
    for layer, items in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        costs = [u["cost_usd"] for u in items if u.get("cost_usd") is not None]
        total = [u["latency_ms"]["total"] for u in items if "total" in (u.get("latency_ms") or {})]
        model_ms = [u["latency_ms"].get("model", 0) for u in items]
        tools_ms = [u["latency_ms"].get("tools", 0) for u in items]
        cache_write = sum(int(u.get("cache_creation_input_tokens") or 0) for u in items)
        lines.append(
            f"  {LAYER_LABELS.get(layer, layer)} ({len(items)}): custo médio "
            + (f"US$ {sum(costs) / len(costs):.4f}" if costs else "desconhecido")
            + f", ponta a ponta p50 {_q(total, 0.5) / 1000:.1f} s / p95 {_q(total, 0.95) / 1000:.1f} s, "
            f"modelo p50 {_q(model_ms, 0.5) / 1000:.1f} s, ferramentas p50 {_q(tools_ms, 0.5) / 1000:.1f} s, "
            f"escrita de cache {cache_write} tokens"
        )
    return "\n".join(lines)


def _run_shadow(cases: list[dict]) -> Report:
    """A decisão que a triagem com Jev teria tomado, pela sombra gravada no alpha.

    Mesma precedência de ``triage.decide``: a regra sensível (e a encomenda
    especial) vence; senão vale a intenção do Jev; senão a regra. Só entram os
    casos com sombra (observação passiva, a partir de 26/09/2026).
    """
    from . import triage
    from .small_talk import small_talk_kind

    report = Report(classifier="jev-shadow")
    for case in cases:
        alpha = case.get("alpha") or {}
        if "jev_latency_ms" not in alpha:
            continue
        rules_intent, rules_source = triage.classify_rules(case["text"])
        jev = "" if small_talk_kind(case["text"]) else str(alpha.get("jev") or "")
        if rules_intent in triage.SENSITIVE or rules_intent == "special_order":
            intent, source = rules_intent, "rules"
        elif jev in triage.ROUTES:
            intent, source = jev, "jev"
        else:
            intent, source = rules_intent, rules_source
        destination = triage.ROUTES[intent][0]
        decision = triage.Triage(intent, "", destination, "", source)
        report.results.append(
            CaseResult(
                case=case,
                layer=current_layer(case, decision),
                intent=intent if source != "default" else "",
                destination=destination,
                source=source,
                cost_usd=None,
                triage_ms=float(alpha["jev_latency_ms"]),
            )
        )
    return report
