# WP-MARKETING-OFFERS-COUPONS-RESCUE — resgate de ofertas e cupons

- **Data:** 2026-09-28
- **Estado:** pronto para execução autônoma
- **Prioridade:** P1; entrega funcional com risco explícito de grafo de migrations

## 1. Objetivo

Transformar a worktree suja `codex/marketing-v2-offers-coupons-20260928` em uma entrega limpa e revisável: criação e listagem de ofertas e cupons no cockpit de Marketing, API transacional e validada, documentação e migration linear.

O arquivo local `shopman/shop/migrations/0083_producao_concluida_no_marketing.py` colide com `0083_avisos_de_encomenda_na_voz_aprovada.py`, já presente no `main`. Ele não pode ser integrado com o número e a dependência atuais.

## 2. Dependências e ordem

- Partir do `main` estabilizado depois do WP de PRs dormentes e, preferencialmente, depois da integração de Encomendas, pois ambos podem tocar `shopman/backstage/api/urls.py`.
- O resgate dos arquivos isolados pode ocorrer em paralelo, mas a alteração de rota e o rebase final respeitam o lease do arquivo compartilhado.
- Usar o leaf real de `shop` no momento da integração. Na auditoria de 2026-09-28 ele era `0083_avisos_de_encomenda_na_voz_aprovada`; portanto a migration local deveria tornar-se a próxima migration e depender dele. Se outro merge criar novo leaf, recalcular.
- Preservar contratos e regras de preço existentes em `offerman`; não criar motor paralelo.

## 3. Ownership exclusivo

O executor deste WP detém exclusivamente:

- `docs/reference/marketing-surface-contract.md`;
- `shopman/backstage/api/marketing.py`;
- `shopman/backstage/tests/test_api_marketing_surface.py`;
- `shopman/shop/models/campaign.py`;
- `shopman/shop/services/marketing_ai.py`;
- `shopman/shop/tests/test_marketing_ai.py`;
- a nova migration de `shop`;
- todos os arquivos Marketing Nuxt tocados ou criados pela worktree, incluindo formulário, composables, página, apresentação, tipos, testes e mock backend.

`shopman/backstage/api/urls.py` possui um lease curto e exclusivo apenas na integração final. `surfaces/node_modules` é artefato local/symlink: nunca versionar, copiar ou tratar como fonte.

## 4. Escopo

- `GET` e `POST` em `/api/v1/backstage/marketing/offers/` usando a autorização existente.
- Validação server-side, transação atômica e projeção segura.
- Criação de oferta automática ou cupom com Promotion própria.
- Código de cupom normalizado, regras de tipo/valor, datas, pedido mínimo, canais, fulfillment, produtos/coleções e limite de usos de acordo com os modelos existentes.
- UI V2 para listar e criar oferta/cupom, com estados de carregamento, erro e sucesso.
- Adicionar `production_finished` às escolhas de `Campaign.trigger`, com migration correta e vocabulário/IA compatíveis.
- Preservar histórico e apresentação existentes.

## 5. Não escopo

- Editar, excluir ou desativar oferta existente.
- Analytics, disparo de campanha ou motor novo de desconto.
- Alterar precedência do pricing.
- Refactor amplo de `shopman/backstage/api/marketing.py`.
- Versionar dependências, caches, symlinks ou snapshots sem consumidor.

## 6. Etapas de execução

### Fase 0 — preservar a fonte

1. Congelar a worktree existente.
2. Inventariar diff e untracked.
3. Criar snapshot recuperável incluindo apenas os três untracked úteis de implementação e excluindo `surfaces/node_modules`.
4. Criar branch limpa do `main` estabilizado.

### Fase 1 — migration linear

1. Descartar como identidade de entrega o número `0083` local.
2. Aplicar a alteração de modelo e gerar a migration sobre o novo baseline.
3. Confirmar nome único, dependência no leaf atual e operação restrita a `AlterField Campaign.trigger`.
4. Se houver duas folhas, resolver o grafo explicitamente antes de prosseguir; não mascarar a colisão com um número arbitrário.

### Fase 2 — API

1. Portar endpoint, projeções e testes.
2. Auditar permissão, lista de campos aceita, referências, datas, decimal/moeda e unicidade concorrente.
3. Preservar `transaction.atomic` e `full_clean`.
4. Provar que uma falha não deixa Promotion ou Coupon parcial.
5. Garantir que cupom tenha Promotion própria e não converta silenciosamente uma oferta automática em coupon-only.

### Fase 3 — UI

1. Portar formulário, composable, página, tipos e apresentação.
2. Impedir submit duplo.
3. Desabilitar criação até o formulário estar válido.
4. Exibir erro por campo e erro global, preservando os dados preenchidos.
5. Refazer a lista após sucesso.
6. Validar teclado, foco, copy em português e viewport estreito.

### Fase 4 — comportamento de negócio

1. Verificar a oferta automática elegível.
2. Verificar que cupom só se aplica com código.
3. Cobrir canais, fulfillment, validade, mínimo, expiração e limite.
4. Confirmar que `production_finished` não dispara campanhas por acidente e não quebra enum, seed ou opções da IA.

### Fase 5 — documentação e entrega

1. Atualizar o contrato de superfície.
2. Organizar commits por modelo/migration, API, UI e docs/testes.
3. Limpar a branch e abrir PR focado.

## 7. Gates e testes

### Integridade e migration

- `git diff --check` limpo;
- nenhum `node_modules` ou symlink versionado;
- `manage.py makemigrations --check --dry-run` sem mudanças;
- migrate em banco vazio;
- migrate a partir do leaf anterior;
- rollback e avanço da migration em banco descartável, quando reversível.

### Backend

- testes de `test_api_marketing_surface.py`;
- testes de `test_marketing_ai.py`;
- testes existentes de offers, coupons e pricing;
- depois, suítes completas de `shopman/shop/tests` e `shopman/backstage/tests` ou gates equivalentes.

Casos mínimos:

- autenticação e permissão;
- campo desconhecido;
- cupom sem código e código duplicado;
- percentual acima de 100;
- valor não positivo;
- datas inválidas ou invertidas;
- SKU, coleção ou canal inexistente;
- fulfillment inválido;
- rollback atômico;
- projeção correta de oferta e cupom.

### Frontend

- testes, lint, typecheck e build de `marketing-nuxt`;
- testes visuais e mock backend coerentes com o contrato real.

### Smoke integrado

- criar uma oferta futura e uma ativa;
- criar um cupom;
- conferir lista e estados;
- provar preço no serviço canônico e no Storefront quando aplicável;
- confirmar ausência de objeto parcial após erro.

O CI completo deve estar verde no novo HEAD.

## 8. PR, merge e deploy

- Um PR focado, com a migration destacada e screenshots desktop/mobile.
- Incluir tabela das regras de preço preservadas.
- Atualizar com o `main` antes da merge queue e conferir novamente o leaf da migration.
- Em staging, aplicar a migration no release normal e então fazer smoke de API, UI e pricing.
- O deploy não cria oferta nem cupom público automaticamente.
- Em produção, usar somente dado de teste aprovado ou validação que não publique benefício involuntário.

## 9. Rollback

- Em regressão de UI/API, reverter o PR ou retirar a entrada do menu.
- Objetos promocionais criados no smoke devem ser desativados pelos mecanismos existentes, nunca apagados às cegas.
- Como `production_finished` pode existir em linhas persistidas, um rollback de modelo/migration exige primeiro provar que não há Campaign com esse trigger ou migrá-las explicitamente.
- Em incidente de release, promover a imagem anterior e registrar os objetos criados durante o smoke.

## 10. Definition of Done

- Grafo de migrations linear, sem colisão e com `makemigrations --check` limpo.
- API, UI e regras de pricing cobertas.
- Nenhuma dependência local versionada.
- Contrato atualizado.
- PR e CI verdes no baseline atual.
- Smoke de staging registrado.
- Worktree fonte preservada até absorção integral e então pronta para arquivamento recuperável.
