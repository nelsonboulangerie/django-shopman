# ONDA4: conferência de encerramento

Ordem: `ORDERS/next-onda4.md`. Fechamento da coordenação no PR #1969.
As seis frentes e os dois PRs de suporte estão MERGED. Não há decisão ou entrega
funcional pendente desta ordem.

## Merges confirmados

Horários em UTC, conferidos por `gh pr view` com `state`, `mergedAt` e `mergeCommit`.
A [saída da conferência no GitHub](../EVIDENCE/onda4-merges.json) preserva os oito
estados, horários, links e commits consultados.

| Frente | PR | Estado | Merge em UTC | Commit de merge |
|---|---|---|---|---|
| 1. Vínculos do produto | #1960 | MERGED | 2026-10-20 23:32:08 | `c1db8e8e3e67cc86cad536d639ee40b422cf18e1` |
| 2. Preço com vigência | #1958 | MERGED | 2026-10-20 22:26:48 | `3d0a10a57fdc69a539c3a881111d97037bca4d78` |
| 3. Tabelão de insumos | #1959 | MERGED | 2026-10-20 22:36:10 | `0cdc545781440dc0e32e56d40037c1b524eae538` |
| 4. Lote de fornecedores | #1957 | MERGED | 2026-10-20 23:32:08 | `8d54b1e537a8f71706cf647412f84cead7076e5c` |
| 5. Import/export da Base | #1964 | MERGED | 2026-10-21 00:02:27 | `921d70c3275872b87a238199f9ddfd2e8beae760` |
| 6. Componentes de combo | #1961 | MERGED | 2026-10-21 00:02:27 | `53c574ff7ac4a8e2f0e22bbdaa7a97e42cc57f63` |
| Segurança das dependências | #1967 | MERGED | 2026-10-20 22:59:36 | `486423dc2abcf6539ab0e6e5c6222f0b45cc7fbb` |
| 3F. Rascunhos fora do recorte | #1968 | MERGED | 2026-10-20 23:39:58 | `2df08fa98b0b6aa82ac3506787bbe8ed24b23cc2` |

## Escopo e verificações

- Cada frente foi entregue em branch, worktree e PR próprios. Import/export e combos foram empilhados nos respectivos pais durante a preparação.
- A lista de arquivos dos oito PRs foi comparada com as exclusões da ordem. A única exceção foi `surfaces/production-nuxt/package-lock.json`, autorizada explicitamente pelo dono no #1967.
- A correção de segurança altera locks. Nenhum manifest, configuração ou allowlist temporária foi introduzido; as versões seguras permanecem.
- As provas funcionais, medições de consultas e Server-Timing, D1 a D12 e capturas estão nos ROUNDS individuais e nas evidências versionadas.
- `gh pr checks --required` omite um check obrigatório ainda não criado. A elegibilidade foi conferida contra os contextos reais da proteção de `main` e pela entrada efetiva na fila.
- O alerta opcional de auditoria nos heads anteriores ao #1967 não foi tratado como prova de falha funcional nem como impedimento obrigatório. A correção foi validada também no commit sintético da fila.

## Registros individuais

- [Frente 1: vínculos do produto](ONDA4-1-produto-vinculos.md).
- [Frente 2: preço com vigência](ONDA4-F2-preco-vigencia.md).
- [Frente 3: tabelão de insumos](ONDA4-3-tabelao-insumos.md).
- [Frente 4: lote de fornecedores](ONDA4-4-lote-fornecedores.md).
- [Frente 5: import/export da Base](ONDA4-5-import-export-base.md).
- [Frente 6: componentes de combo](ONDA4-F6-produto-combo.md).
- [Segurança das dependências](ONDA4-SEC-mcp-server-audit.md).
- [Seguimento da frente 3: rascunhos filtrados](ONDA4-3F-rascunhos-filtrados.md).

O BOARD registra a conferência das entregas sem manter reivindicações ativas de frentes concluídas. As frentes de outras coordenações permanecem intactas.

As worktrees das entregas foram conferidas limpas após os merges. Os previews foram
encerrados e somente caches gerados foram removidos. Capturas e provas versionadas
foram preservadas; nenhum branch foi apagado.
