"""A conferência antes do envio: correta, útil e aceitável, ou sai a alternativa segura.

A verificação de saída (``verify``) é estrutural: lastro por espaço, número sem fato, ação
sem recibo, regras da casa. Ela não sabe se a resposta **atende ao que o cliente pediu**,
nem se deixa o cliente com o próximo passo. A conferência junta três perguntas, todas antes
de a resposta sair:

- **aceitável**: a verificação de saída não segurou (voz e regras da casa);
- **correta**: tem lastro e não inventa. A resposta montada por molde sobre o fato é correta
  por construção; a redigida (por modelo) precisa da palavra de um juiz;
- **útil**: deixa o próximo passo (o leitor de cada língua é do adaptador) e, quando há juiz,
  atende ao que foi pedido.

O juiz é uma porta (``ReplyJudge``): barato, opcional e falível. **À prova de falha**: juiz
que cai é ``unavailable``, nunca "passou". Sem a palavra dele, a resposta por construção sai;
a redigida não sai, porque ninguém conferiu. Qualquer reprovação leva à alternativa segura,
que o adaptador escolhe (o texto literal das fontes, ou o "vou verificar" com dono e prazo),
nunca ao erro.

``mode="shadow"`` confere e registra sem mudar o envio: é como a conferência se mede antes
de valer (régua antes do motor, v2 8.4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

Check = Literal["acceptable", "correct", "useful"]
Status = Literal["pass", "fail", "unavailable"]
JudgeAnswer = Literal["answers", "off_target", "contradicts"]


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """A palavra do juiz: a resposta atende, fala de outra coisa, ou se contradiz."""

    answer: JudgeAnswer
    confidence: float | None = None


class ReplyJudge(Protocol):
    """Porta do juiz. Recebe só texto já redigido pelo adaptador; levanta exceção quando cai."""

    def judge(self, *, customer: str, reply: str, previous: str = "") -> JudgeVerdict: ...


@dataclass(frozen=True, slots=True)
class CheckResult:
    check: Check
    status: Status
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Conference:
    """O veredito. ``send``: a candidata sai. ``fallback``: sai a alternativa segura."""

    decision: Literal["send", "fallback"]
    checks: tuple[CheckResult, ...]
    judge: JudgeVerdict | None = None

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(f"{c.check}:{c.reason}" for c in self.checks if c.status != "pass")

    def as_record(self) -> dict:
        return {
            "decision": self.decision,
            "checks": {c.check: {"status": c.status, **({"reason": c.reason} if c.reason else {})} for c in self.checks},
            **({"judge": {"answer": self.judge.answer, "confidence": self.judge.confidence}} if self.judge else {}),
        }


def confer(
    *,
    customer: str,
    reply: str,
    held: bool,
    by_construction: bool,
    has_next_step: bool,
    judge: ReplyJudge | None = None,
    previous: str = "",
    next_step_needed: bool = True,
) -> Conference:
    """Confere a candidata. Nunca levanta: o que cai vira ``unavailable`` e decide pelo lado seguro.

    ``held``: a verificação de saída segurou. ``by_construction``: todo fato da resposta saiu de
    lastro por molde (nada redigido). ``has_next_step``: o leitor do adaptador achou o próximo
    passo. ``next_step_needed``: falso quando o cliente só agradeceu ou se despediu.
    """
    verdict: JudgeVerdict | None = None
    judge_status: Status = "unavailable"
    if judge is not None:
        try:
            verdict = judge.judge(customer=customer, reply=reply, previous=previous)
            judge_status = "pass" if verdict.answer == "answers" else "fail"
        except Exception:  # noqa: BLE001 — juiz que cai é "sem palavra", nunca "passou"
            verdict, judge_status = None, "unavailable"

    acceptable = CheckResult("acceptable", "fail" if held else "pass", "held" if held else "")
    if verdict is not None and verdict.answer == "contradicts":
        correct = CheckResult("correct", "fail", "judge_contradicts")
    elif by_construction:
        correct = CheckResult("correct", "pass")
    elif judge_status == "pass":
        correct = CheckResult("correct", "pass", "judge")
    else:
        correct = CheckResult("correct", "fail" if judge_status == "fail" else "unavailable",
                              "judge_rejected" if judge_status == "fail" else "unconferred")
    if next_step_needed and not has_next_step:
        useful = CheckResult("useful", "fail", "no_next_step")
    elif verdict is not None and verdict.answer == "off_target":
        useful = CheckResult("useful", "fail", "judge_off_target")
    else:
        useful = CheckResult("useful", "pass")

    checks = (acceptable, correct, useful)
    decision: Literal["send", "fallback"] = "send" if all(c.status == "pass" for c in checks) else "fallback"
    return Conference(decision, checks, verdict)


def conferred(conference: Conference, *, candidate: str, safe: Callable[[Conference], str],
              mode: Literal["shadow", "enforce"] = "shadow") -> str:
    """O texto que sai. Em sombra, sempre a candidata; valendo, a alternativa segura quando reprova.

    Se a alternativa segura também falhar ao ser montada, o erro sobe: a camada de cima
    trata turno que não fecha (para a equipe), e nada sai sem conferência.
    """
    if mode == "shadow" or conference.decision == "send":
        return candidate
    return safe(conference)


__all__ = ["CheckResult", "Conference", "JudgeVerdict", "ReplyJudge", "confer", "conferred"]
