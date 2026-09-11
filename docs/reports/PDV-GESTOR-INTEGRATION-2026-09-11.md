# Fechamento técnico PDV + Gestor — 11/09/2026

Base integrada: `47e9c657a` de `codex/orders-operational-excellence-20260910`, liberada pelo agente responsável. Worktree isolado `django-shopman-pdv-gestor-integration-20260911`, branch `codex/pdv-gestor-integration-20260911`.

## Composição

- Brief PDV `22d2e803a` aplicado como `09f8983d6`: restauração de cadastro em comanda reaberta, CPF e oferta de cadastro coerentes, remoção do bloqueio fiscal obsoleto para CPF + taxa, atalhos e aviso de pop-up do display.
- De `e3c1267a5`, somente UI/composable/testes do PDV e relatórios. O Gestor já incorporou pagamentos físicos/mistos, troco, acerto e locks. Nenhum arquivo de serviços/projeção do Gestor foi substituído pela versão antiga do PDV.
- Campos comuns já canonizados pelo PR #599: 44px, bg-background, foco 3px/50%. Avisos PDV agora usam text-warning; proposta aprovada consolidada no token claro #965411, dark #e09a4a preservado.

## Contrato definitivo de maquininha

A migration aditiva backstage0061 cria DeliveryDevice. O Gestor projeta as referências individuais `card_machine:<UUID>` e aloca exclusivamente no despacho. O PDV declara somente os tenders on_delivery; não reserva aparelho nem envia um novo campo. `dispatch.equipment` mantém compatibilidade de tipo. Devolução e acerto são independentes, com proteção de concorrência/replay na base do Gestor. Pedidos legados não ganham identidade física inventada.

## Evidência local

- PDV: 871 testes em 50 arquivos; relatório JSON `.artifacts/integrated-pos.json`.
- Pagamentos + dispositivos: 57 testes PostgreSQL, incluindo exclusividade e ciclo PDV → despacho → acerto (`integrated-payments.log`).
- Outros nove arquivos test_pos_*: 138 testes, um arquivo por invocação (`integrated-pos-backend.log`). Incluem CPF + taxa e contratos existentes.
- Guardrails do tema: 20 testes, contraste claro/escuro e fonte compartilhada. Log na worktree PDV original `.artifacts/pdv-final-theme-tests.log`.
- TypeScript do PDV passou após instalar dependências próprias do operator-kit; primeira tentativa registrou dependências locais ausentes e não é evidência de sucesso.
- Todos os dados são sintéticos, sem cobrança, emissão fiscal ou hardware real. Os resultados não substituem piloto em campo.

## Publicação e ordem

Este documento fecha a integração técnica do PDV; não declara publicados os commits nem substitui os gates de rollout do Gestor. Na liberação coordenada, preservar a ordem migration → backend com alocação exclusiva → UI compatível. Não publicar isoladamente a antiga implementação genérica de operator_orders do PDV. Não reverter migration populada nem apagar alocações em trânsito. A avaliação global de carga e o relatório final do Gestor permanecem sob a tarefa responsável.
