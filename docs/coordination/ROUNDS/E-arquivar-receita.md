# E: receitas usam is_active para arquivar

- **id:** E
- **branch:** `codex/arquivar-receita`
- **estado:** na fila #1944
- **início (UTC):** 2026-10-20 09:39

## O que entrou

- `RecipeEntry.is_archived` virou `is_active`, com default `True` e verbose name "Ativa".
- A migração `craftsman.0018` usa `RenameField` e inverte os valores existentes, preservando o sentido de receitas ativas e arquivadas.
- A lista padrão traz somente receitas ativas. O filtro "Arquivadas" traz somente as arquivadas e desarquivar devolve a receita à lista padrão.
- Serviços, busca da suíte, fila de conferência, contrato TypeScript gerado, mocks, tipos e telas da Produção usam o campo positivo.
- A tela mantém o estado "Arquivada" e padroniza o gesto como "Desarquivar", sem residual de "Restaurar" nesse fluxo.

## Provas

- Backend direcionado: 200 testes verdes; migração e limite de consultas: mais 2 testes verdes.
- Lista do inventário: 10 consultas antes e 10 depois.
- Produção: 63 testes Vitest verdes, typecheck verde e E2E Chromium desktop verde.
- Admin/Unfold: 300 testes verdes pelo `make admin`.
- `makemigrations --check --dry-run craftsman`: nenhuma mudança pendente.
- Migrações do Craftsman: nenhuma numeração duplicada.
- Varredura de código vivo em Craftsman, Backstage e Produção: zero residual `is_archived`; o nome antigo aparece só no histórico de migrações, nos planos concluídos e no teste que materializa o estado anterior à migração.
- Prévia real em 1440 × 900, temas claro e escuro, sem erro 4xx/5xx no E2E; capturas locais com nome único da frente.
