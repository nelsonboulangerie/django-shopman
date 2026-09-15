# Execução — fechamento automatizável de PROD-016

- Sessão: `codex-production-prod016-print-proof-20260914`
- Data: 14 de setembro de 2026, `America/Sao_Paulo`
- Worktree exclusivo: `/private/tmp/shopman-prod016.GZeTTJ`
- Branch: `codex/production-prod016-print-proof-20260914`
- SHA-base: `2aff555a538126d88e1e263864b751607012f50c` (`origin/main`)
- Commit técnico: `6003633065e8835e49d8d20c30a20624fc151022`
- Escopo: checklist local honesto e prova PostgreSQL do claim de impressão
- Estado: implementação técnica local; sem push, PR, merge, deploy ou hardware real

## Critério normativo confirmado

O WP-P1.4 exige que um checklist mantido no navegador seja chaveado por
**estação + data + hash/revisão da projeção**, avise e reconcilie quando o plano
mudar e se apresente claramente como auxílio local, não como auditoria. O mesmo
WP exige que impressão exponha preview, destino/status, confirmação, erro,
retry e reimpressão auditada, reutilizando o agente térmico quando aplicável.

PROD-016 não autoriza transformar o checklist em fato compartilhado nem
substituir o gate humano de papel real. Responsabilidade compartilhada continua
pertencendo a eventos server-side com ator/estação/hora; `localStorage` não é
sincronizado nem promovido a ledger.

## Baseline reproduzido

- `useMiseEnPlace` usava `preparacao:<data>`: duas estações e duas revisões da
  mesma data compartilhavam marcações antigas.
- A tela mostrava a contagem de itens separados, mas não declarava que o estado
  era local e não auditável.
- `PrintJob` já persistia `requested_station_ref`, `source_revision`, documento
  congelado, `document_sha256`, payload e `payload_sha256`; o Admin Unfold já os
  mantinha somente leitura.
- O serviço já usava `SELECT FOR UPDATE SKIP LOCKED`, mas não havia uma prova
  PostgreSQL específica no runtime gate para dois relays disputando o mesmo job.

## Implementação

1. O checklist usa namespace versionado por estação (ou dispositivo ainda não
   provisionado), data e digest SHA-256 da projeção.
2. Um ponteiro de revisão por estação/data detecta mudança do plano, remove a
   lista anterior, carrega somente a nova revisão e mostra aviso contextual.
3. A tela declara: “Checklist local desta estação · não é registro de
   auditoria”. Nenhuma escrita servidor-side foi criada.
4. A regressão HTTP prova que o job persistido conserva exatamente a revisão
   assinada apresentada ao operador e que o hash corresponde ao documento
   canônico congelado.
5. A nova prova PostgreSQL lança dois relays da mesma estação em conexões
   independentes e exige exatamente um claimant, um `PrintAttempt` leased e um
   único job em estado leased. O arquivo foi incluído no executor obrigatório
   de runtime; em SQLite ele pula explicitamente em vez de simular locks.

## Evidências

| Gate | Resultado |
|---|---|
| Produção Nuxt completa | 37 arquivos, 284 testes aprovados |
| Produção Nuxt typecheck + ESLint | aprovados |
| Build de Produção Nuxt | aprovado |
| Backend impressão + costura do runtime | 26 testes aprovados em SQLite |
| Concorrência específica de impressão | 1 teste aprovado em PostgreSQL local real |
| Unfold canônico | `make admin`: gate de templates + 270 testes aprovados |
| Ruff + `git diff --check` | aprovados |

O `npm ci` isolado encontrou `ENOSPC`. Para não alterar dependências nem lock,
os testes usaram `node_modules` de outra worktree cujo `package-lock.json` tinha
o mesmo SHA-256 (`5d334d119cc60b3554783d64174195e47c13897b80b2f7634e1d47f4580e431f`).
O Operator Kit usou a mesma técnica após igualdade do próprio lock
(`6787705b7c76d85f7aae4ffa8b6716c2e5dc4008b55e814eacb84e45304e5cb3`).

## Limites humanos preservados

- A impressão em adesivo 60×40 mm ainda precisa ser observada no hardware real.
- Aceite do spooler continua significando “enviado à fila”, não papel emitido.
- O checklist continua auxílio individual; caso o negócio exija
  responsabilidade compartilhada, D5 deve definir o processo e o fato factual.
- Nenhum dado de produção, impressora ou estação real foi alterado.

## Handoff

Integrar o commit técnico deste slice sobre a `origin/main` correspondente, repetir a
suíte de Produção, o runtime PostgreSQL e `make admin`. Não restaurar a chave
legada por data nem tratar o checklist local como auditoria.
