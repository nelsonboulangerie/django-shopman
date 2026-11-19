"""A memória declarada: o que o cliente afirmou, com fonte, finalidade e validade (v2 6.1, 6.2).

Na primeira versão só existem a memória de trabalho (o estado de diálogo, F4) e a
declarada; nada inferido. Regras que não dependem de ninguém lembrar:

- **corrigir é registro novo que substitui** (``supersedes``); o anterior fica no
  histórico e nunca mais aparece em recuperação nem em resumo (K28);
- **vencido não se lembra**: item com ``valid_until`` passado sai da recuperação e
  dos resumos, como o corrigido;
- **derivado segue a origem**: todo resumo guarda de que itens nasceu, e a
  correção ou o vencimento de um deles o invalida; o resumo é refeito, nunca
  servido velho;
- **categoria sensível nunca é lembrada em silêncio**: só com a confirmação
  explícita do cliente (``confirmed=True``);
- **texto de memória é dado**, nunca instrução: o valor entra em situação ou em
  espaço travado, nunca em pedido a modelo (N23).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.contracts import MemoryItem


class MemoryRefused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Summary:
    """Um derivado: o texto (ou valor) resumido e os itens de que nasceu."""

    subject_ref: str
    value: Any
    sources: tuple[str, ...]


@dataclass
class MemoryStore:
    """Memória declarada em memória, que só acrescenta. O adaptador troca por um armazenamento real."""

    history: list[MemoryItem] = field(default_factory=list)
    _summaries: dict[str, Summary] = field(default_factory=dict)

    def _superseded(self) -> set[str]:
        return {item.supersedes for item in self.history if item.supersedes is not None}

    def declare(self, item: MemoryItem, *, confirmed: bool = False) -> MemoryItem:
        """Guarda o que o cliente afirmou. Só ``declared``: nada inferido entra (corte do D1)."""
        if item.evidence_state != "declared":
            raise MemoryRefused("not_declared", "na primeira versão só se guarda o que o cliente afirmou")
        if item.sensitivity == "sensitive" and not confirmed:
            raise MemoryRefused("sensitive_needs_confirmation", "categoria sensível não é lembrada em silêncio")
        if item.supersedes is not None and item.supersedes not in {m.memory_id for m in self.history}:
            raise MemoryRefused("unknown_supersedes", item.supersedes)
        if item.supersedes is not None and item.supersedes in self._superseded():
            raise MemoryRefused("already_superseded", item.supersedes)
        self.history.append(item)
        if item.supersedes is not None:
            self._invalidate({item.supersedes})
        return item

    def correct(self, memory_id: str, *, new: MemoryItem, confirmed: bool = False) -> MemoryItem:
        """A correção: o item novo substitui o anterior (mesmo sujeito e categoria)."""
        old = self.get(memory_id)
        if (new.subject_ref, new.category) != (old.subject_ref, old.category):
            raise MemoryRefused("correction_changes_referent", "a correção é do mesmo sujeito e categoria")
        return self.declare(dataclasses.replace(new, supersedes=memory_id), confirmed=confirmed)

    def get(self, memory_id: str) -> MemoryItem:
        for item in self.history:
            if item.memory_id == memory_id:
                return item
        raise KeyError(memory_id)

    def recall(self, subject_ref: str, now: str, category: str | None = None) -> tuple[MemoryItem, ...]:
        """O que vale agora: nem substituído, nem vencido."""
        gone = self._superseded()
        return tuple(item for item in self.history
                     if item.subject_ref == subject_ref and item.memory_id not in gone
                     and (category is None or item.category == category)
                     and (item.valid_until is None or item.valid_until > now))

    def value(self, subject_ref: str, category: str, now: str, default: Any = None) -> Any:
        current = self.recall(subject_ref, now, category)
        return current[-1].value if current else default

    def summary(self, subject_ref: str, now: str,
                render: Callable[[tuple[MemoryItem, ...]], Any] | None = None) -> Summary:
        """O resumo do sujeito, refeito quando alguma origem foi corrigida ou venceu (K28)."""
        current = self.recall(subject_ref, now)
        ids = tuple(item.memory_id for item in current)
        cached = self._summaries.get(subject_ref)
        if cached is not None and cached.sources == ids:
            return cached
        rendered = render(current) if render is not None else {item.category: item.value for item in current}
        fresh = Summary(subject_ref, rendered, ids)
        self._summaries[subject_ref] = fresh
        return fresh

    def _invalidate(self, memory_ids: set[str]) -> None:
        for subject, summary in list(self._summaries.items()):
            if memory_ids & set(summary.sources):
                del self._summaries[subject]

    def snapshot(self) -> Mapping[str, Summary]:
        return dict(self._summaries)
