# ONDA4-F6: componentes de combo

- Data: 2026-10-20.
- Branch: `codex/produto-combo`.
- Estado: em execução, empilhado na frente1 (`codex/produto-vinculos`).
- Ordem: `ORDERS/next-onda4.md`, frente6.

A edição usa o mesmo detalhe, revisão e intenção do produto. A leitura terá
componentes e quantidades em lote; a escrita será atômica e reaproveitará a
validação de ciclo/profundidade de ProductComponent. O painel ganha um editor
inline no bloco Vínculos, com busca de produto e aviso do impacto no estoque.

Pendentes: implementação, provas API/componente, desempenho, capturas e CI.
