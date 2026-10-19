# WP-ENCOMENDAS-UNIFIED-INTEGRATION — integração única de Encomendas

- **Data:** 2026-09-28
- **Estado:** pronto para execução autônoma
- **Prioridade:** P0 de recuperação; bloqueia a evolução segura das superfícies operacionais

## 1. Objetivo

Resgatar, reconciliar e entregar como uma única solução as duas frentes locais que nasceram do mesmo baseline `79263250e` e hoje disputam arquivos centrais:

- `claude/encomendas-tela-unica`: 26 entradas locais; consolida navegação, filtros e a tela de Encomendas do PDV;
- `claude/detalhe-do-pedido-compartilhado`: 22 entradas locais; introduz contexto/contrato e detalhe de pedido compartilhado entre superfícies.

O resultado precisa ter uma única fonte de verdade para o detalhe, uma única entrada de Encomendas no PDV e um único integrador responsável pela resolução semântica dos sete arquivos sobrepostos. As worktrees de origem são evidência recuperável e ficam congeladas até merge e smoke.

## 2. Dependências e ordem

1. Executar depois das decisões do `WP-DORMANT-PR-TRIAGE-2026-09-28`, especialmente sobre os PRs `#1119` e `#1120`, que tocam `shopman/backstage/api/operations.py`; o `#1120` também toca `docs/reference/data-schemas.md`, `shopman/backstage/tests/test_order_ticket.py` e `surfaces/pos-nuxt/app/pages/index.vue`.
2. Partir de uma worktree limpa criada do `origin/main` atualizado. Não usar o checkout raiz interrompido nem rebasear diretamente uma das worktrees sujas.
3. Se Marketing for integrado antes, absorver a rota já presente em `shopman/backstage/api/urls.py`. Caso contrário, este WP mantém o lease do arquivo até o merge e o WP de Marketing rebasa depois.
4. Não depende de deploy em produção. O primeiro destino é staging.

## 3. Ownership exclusivo

Um único integrador detém, do snapshot ao merge, os arquivos abaixo:

- `shopman/backstage/api/operations.py`;
- `shopman/backstage/api/urls.py`;
- `shopman/backstage/projections/preorders.py`;
- `shopman/backstage/projections/order_queue.py`;
- `shopman/backstage/services/order_ticket.py`;
- `shopman/backstage/management/commands/export_orders_schema.py`;
- testes de preorder, contexto, ticket, edição, takeover e hand-over em `shopman/backstage/tests/`;
- `surfaces/operator-kit/app/components/OperatorOrderDetail.vue`;
- `surfaces/operator-kit/app/presentation/orderDetail.ts`;
- `surfaces/operator-kit/app/types/orderDetail.ts`;
- todos os arquivos do POS tocados pelas duas doadoras;
- os arquivos de Orders tocados pelas duas doadoras, incluindo o contrato gerado;
- `docs/reference/data-schemas.md`.

As worktrees doadoras ficam somente leitura. Nenhum outro WP edita os arquivos acima enquanto o lease estiver ativo. Em especial, `shopman/backstage/api/urls.py` só recebe alterações durante uma janela curta de integração; outros WPs declaram a rota desejada e rebaseiam depois.

## 4. Escopo

- Preservar o objetivo de uma única entrada de Encomendas no PDV.
- Unificar filtros, lista, contadores, navegação, takeover, hand-over e ações de encomenda.
- Criar ou consolidar um único detalhe de pedido no `operator-kit`, consumido coerentemente pelo PDV e pelo Gestor.
- Consolidar projeção e contrato do servidor como fonte de verdade.
- Regenerar `surfaces/orders-nuxt/app/generated/ordersContract.ts`; nunca editar o artefato gerado manualmente.
- Preservar impressão, ticket e edição existentes no `main`.
- Remover páginas redundantes apenas depois de provar navegação e redirecionamento equivalentes.
- Atualizar documentação do schema e cobertura de regressão.

## 5. Não escopo

- Novo redesign além do que as duas frentes já propõem.
- Novas regras de domínio, migrations, preço ou pagamento.
- Redesign visual de impressão do PR `#1120`.
- Marketing, checkout, endereço ou mapa.
- Manter duas implementações de detalhe atrás de uma flag sem prazo de remoção.
- Deploy direto em produção.

## 6. Etapas de execução

### Fase 0 — congelar e preservar

1. Confirmar SHA, branch e `git status --short` das duas worktrees doadoras.
2. Gerar inventário de arquivos, diff binário e lista de untracked.
3. Criar snapshot recuperável fora do branch de integração. Não incluir dependências, caches ou symlinks gerados.
4. Não limpar, arquivar nem modificar as doadoras.

### Fase 1 — baseline e caracterização

1. Criar branch limpa `codex/encomendas-integracao-<data>` do `origin/main` estabilizado.
2. Rodar os testes-alvo no baseline e registrar falhas preexistentes.
3. Mapear cada hunk das doadoras para uma destas categorias:
   - tela única;
   - contrato/detalhe compartilhado;
   - conflito semântico;
   - mudança obsoleta diante do `main`.
4. Registrar as rotas atuais e os deep links que não podem quebrar.

### Fase 2 — backend e contrato

1. Portar primeiro projeções, contexto, operações, exportador e testes da frente de detalhe.
2. Resolver conflitos por comportamento desejado; é proibido aceitar `ours` ou `theirs` em bloco.
3. Regenerar o contrato de Orders e confirmar diff determinístico.
4. Garantir que autorização, stale state, takeover, hand-over e ações mutáveis continuem server-driven e idempotentes.

### Fase 3 — detalhe compartilhado

1. Portar o componente, tipos e apresentação para `operator-kit`.
2. Integrar primeiro no Gestor e depois no PDV.
3. Provar que o componente compartilhado não importa regra específica de uma superfície.
4. Remover copy e apresentação duplicadas somente depois da adoção pelos dois consumidores.

### Fase 4 — tela única

1. Portar shell, lista, filtros e navegação da frente `encomendas-tela-unica`.
2. Fundir uma única vez os sete arquivos sobrepostos:
   - `shopman/backstage/api/operations.py`;
   - `shopman/backstage/projections/preorders.py`;
   - `shopman/backstage/tests/test_pos_preorders.py`;
   - `surfaces/pos-nuxt/app/composables/usePosPreorders.ts`;
   - `surfaces/pos-nuxt/app/pages/preorders/[ref].vue`;
   - `surfaces/pos-nuxt/app/types/preorders.ts`;
   - `surfaces/pos-nuxt/tests/pages/preorders.test.ts`.
3. Só então remover `panel.vue`, `today.vue`, `week.vue` e componentes obsoletos.
4. Manter redirects ou links canônicos para URLs antigas por pelo menos uma release, se houver uso externo ou bookmark operacional.

### Fase 5 — revisão e entrega

1. Atualizar schema e documentação.
2. Rodar revisão adversarial de permissões, concorrência, ação duplicada e perda de contexto ao voltar.
3. Organizar commits revisáveis: backend/contrato; detalhe compartilhado; tela única; poda/redirects; docs/testes.
4. Abrir um único PR de integração ou uma stack curta e inseparável. Não abrir dois PRs concorrentes sobre os mesmos arquivos.

## 7. Gates e testes

### Integridade

- `git diff --check` limpo;
- zero marcador de conflito;
- nenhum untracked necessário ao build;
- `manage.py makemigrations --check --dry-run` sem mudanças;
- contrato gerado reproduzível.

### Backend

Executar os testes focados de:

- `test_order_detail_context.py`;
- `test_pos_preorders.py`;
- `test_pos_preorder_counter_takeover.py`;
- `test_pos_preorder_hand_over.py`;
- `test_api_order_edit.py`;
- `test_order_ticket.py`.

Depois, executar a suíte completa de `shopman/backstage/tests` ou o gate canônico equivalente.

### Frontend

- `operator-kit`: testes;
- `pos-nuxt`: testes, lint, typecheck e build;
- `orders-nuxt`: testes, lint, typecheck e build.

### Fluxo integrado

Validar em desktop e viewport móvel:

- entrada em Encomendas;
- filtros por hoje, semana, status e pagamento;
- contador e atualização de lista;
- detalhe e retorno preservando contexto;
- edição, receber, cancelar, reagendar, takeover e hand-over;
- URL antiga redirecionando para o destino canônico;
- ausência de ação, botão, copy ou requisição duplicada.

O CI completo precisa estar verde no HEAD já atualizado. Checks anteriores ao rebase não valem como prova.

## 8. PR, merge e deploy

- O PR deve incluir matriz “fonte A / fonte B / decisão final”, lista de arquivos removidos e de rotas legadas.
- A branch deve estar atualizada antes da merge queue.
- Não reescrever nem fazer force-push nas branches doadoras.
- Após o merge, liberar somente em staging.
- Fazer smoke autenticado no PDV e Gestor e observar erros 5xx, permissões e incompatibilidade de contrato.
- Produção apenas na release seguinte, depois do smoke operacional.

## 9. Rollback

- Um revert do merge deve restaurar as telas e rotas anteriores; por isso este WP não introduz migration nem remoção de dados.
- Preservar redirects/entry points antigos por uma release permite rollback de navegação.
- Em incidente de deploy, promover a imagem anterior; não corrigir diretamente em produção.
- As worktrees doadoras só podem ser arquivadas após merge, smoke e confirmação de que todo untracked útil foi absorvido ou descartado conscientemente.

## 10. Definition of Done

- Existe uma única superfície de Encomendas no PDV.
- Existe um único componente e um único contrato de detalhe compartilhado.
- Nenhuma URL operacional conhecida quebra.
- Todas as capacidades das duas doadoras estão cobertas por teste ou têm descarte justificado no PR.
- Não há mudança perdida, conflito, dependência gerada ou worktree de integração suja.
- CI completo verde e smoke de staging registrado.
- Schema e documentação correspondem ao código.
- As worktrees antigas estão inventariadas e prontas para arquivamento recuperável.
