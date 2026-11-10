# Mapa de Guardas — índice das portas invariantes

> Status: canônico. (Ponteiro a partir da Constituição: pendente, frente F1.) O *check_guard_map.py* confere que este mapa é completo e que cada guarda existe.

Leia assim: cada linha é uma *porta invariante* (o que nunca pode quebrar), a *guarda* que a cobre e o *comando* que a roda. Porta sem guarda explícita está na seção 9.

## 1. Fronteira dos kernels (C1)

| Porta | Guarda | Comando |
|---|---|---|
| Kernel não importa host/orquestrador/superfície | test_import_boundaries.py::test_kernel_packages_do_not_import_host_layers | make test-framework |
| Kernel não importa outro kernel fora de bridge | test_import_boundaries.py::test_domain_kernels_do_not_import_each_other_outside_bridges | make test-framework |
| Kernel não alcança outro app via apps.get_model | test_import_boundaries.py::test_kernels_do_not_reach_other_apps_through_the_registry | make test-framework |

## 2. Orquestrador (C4, C5)

| Porta | Guarda | Comando |
|---|---|---|
| Inventário físico e unidades semânticas do orquestrador | check_orchestrator_units.py | make orchestrator-governance |
| Preço de lista com autoridade única no Offerman | test_offerman_is_the_only_list_tier_price_owner | make test-framework |

## 3. Superfícies headless (C8) e Admin/Unfold

| Porta | Guarda | Comando |
|---|---|---|
| Superfície não importa outra superfície | test_surfaces_do_not_import_each_other | make test-framework |
| Shop só toca superfície via adapters | test_shop_imports_surfaces_only_through_adapters | make test-framework |
| Framework não importa internals de kernel (models.x/contrib.x) | test_framework_does_not_import_protected_kernel_internals | make test-framework |
| Superfície não importa orderman write primitives | test_surfaces_do_not_import_orderman_write_primitives | make test-framework |
| View do backstage não dirige lifecycle diretamente | test_backstage_views_do_not_drive_order_lifecycle_directly | make test-framework |
| Admin/Unfold × superfícies de operador | check_admin_surface_boundary.py | make admin |
| Templates Admin usam Unfold canônico | check_unfold_canonical.py | make unfold |

## 4. Migrações e evolução (C9, ADR-015)

| Porta | Guarda | Comando |
|---|---|---|
| Nada sem migration + schema limpo do zero + grafo + numeração não-ambígua | check_migrations.py | make test-migrations |
| Backward-compat pós-produção (expand-contract) | check_adr015.py | make canonical-docs |
| Seed --flush re-entrante | check_seed_reentrancy.py | make test-migrations |

## 5. Documentação e governança canônica

| Porta | Guarda | Comando |
|---|---|---|
| ADR: número, status e índice únicos | check_adr_governance.py | make adr-governance |
| Links vivos, teto histórico, índice de planos | check_docs_governance.py | make docs-governance |
| Docs canônicas de go-live acompanham código e tag ADR-015 | check_canonical_docs.py | make canonical-docs |
| Mapa semântico dos pacotes + referências da Constituição | check_semantic_docs.py | make canonical-docs |
| Versão legal arquivada é imutável | check_legal_archive.py | make docs-governance |
| Docs/rotas/probes do Marketing não derivam | check_marketing_docs.py | make marketing-docs |

## 6. Superfícies Nuxt (registry, versão, operador, copy)

| Porta | Guarda | Comando |
|---|---|---|
| Todo lugar enumera superfície conforme registry.json | check_surface_registry.py | make test-surface-registry |
| Mesma versão de pacote compartilhado nas superfícies | check_surface_versions.py | make test-surface-versions |
| Ledger/teto de componentes dos apps de operador | check_operator_component_ledger.py | make test-operator-components |
| Sem cópia de layout/token canônico | check_operator_layout_guardrails.py | make test-operator-ux |
| Sem listener global/colisão de atalho | check_operator_shortcuts.py | make test-operator-ux |
| Tema compartilhado casado com baselines | check_theme_baseline_contract.py | make theme-baselines |
| Vocabulário de tela (dispositivo/aparelho) no Django | test_vocabulario_de_tela.py + test_vocabulario_abertura_fechamento.py + test_vocabulario_etapa_da_receita.py | make test-backstage |
| Vocabulário/copy/UX nos apps Nuxt (noEmDash, jargon, copyNeverTruncates, identifiers, a11y…) | surfaces/operator-kit/tests/guardrails.*.test.ts (~30) | make test-operator-ux |
| Audit de dependências npm | check_npm_audit_gate.mjs | CI surfaces-gate |

## 7. Qualidade de código

| Porta | Guarda | Comando |
|---|---|---|
| Sem engolir exceção em silêncio | check_silent_swallow.py | make test-silent-swallow |
| constraints.txt cobre tudo que a imagem instala | check_constraints.py | make test-constraints |
| Teto de job cabe a espera declarada | check_workflow_budgets.py | make test-workflow-budgets |
| Menu do catálogo monta acima do mínimo | check_menu_smoke.py | make test-framework |

## 8. Deploy, runtime e prontidão

| Porta | Guarda | Comando |
|---|---|---|
| Spec versionado confere com app vivo | check_do_spec_drift.py | make deploy-spec-drift |
| Publicado confere com o que o main pede | check_registry_drift.py | make deploy-drift |
| Contrato de produção hermético | check_production_contract.py | make production-contract |
| PostgreSQL+Redis reais configurados | check_runtime_gate.py | make test-runtime-preflight |
| Prontidão de release/piloto/go-live | check_release_readiness.py | make release-readiness / production-readiness |
| Descritores de instância (schema, ownership) | check_instance_descriptors.py | make test-instance-descriptors |
| Configuração de loja não cresce por env/settings (ADR-042) | check_tenant_config.py | make test-instance-contracts |

## 9. ÁREAS NÃO COBERTAS (sem guarda explícita) — o ponto de decisão

Estas portas têm lei (Constituição/ADR) mas ainda não têm check dedicado. É aqui que a decisão de travar ou assumir precisa ser tomada.

| Porta | Evidência de que está aberta | Risco se morder |
|---|---|---|
| Duplicação de autoridade de decisão (geral) | a promessa de estoque já tem autoridade única (`promise_for_sku`/`decision_from_availability` no Stockman; `_stock_decision` apagado, caracterização em `shopman/shop/tests/test_promise_for_sku_characterization.py`); fora a promessa, só há guarda para o preço de lista | outra decisão duplicada diverge em produção |
| Cadeia de custo write-only (ADR-023/024) | COST_BACKEND em settings, mas nenhum leitor em runtime (grep no repo: só offerman+settings+docs) | margem/custo de receita mentem no BI |
| ADR-025 (signal on_commit) | Status Proposto; P1 do Payman diagnosticado mas sem gate que reprove signal.send fora de on_commit | efeito fantasma sob rollback |
| C2 (dinheiro em _q) | sem lint que impeça float em campo monetário | arredondamento de dinheiro |
| C3 (identidade por ref, nunca FK/pk de outro kernel) | convenção; sem check por tipo | acoplamento cross-kernel por pk |
| C6 (ciclo de Order só no Orderman) | convenção + ADR-006; sem check de transição fora do dono | segundo ciclo paralelo |
| C7 (lifecycle funcional, sem subclasse) | convenção; sem check que reprove classe de lifecycle | decisão de instância escondida |
| C10 (read-side não é fonte do fato) | convenção; sem check que reprove escrita em projection | projection vira autoridade |
| C11 (ledger imutável no dono do fato) | precedente Cashman não virou check genérico | reescrita de história |

> O check_guard_map.py imprime esta seção 9. Cada linha é uma decisão do dono: travar agora (virar guarda) ou assumir convenção (e registrar o porquê).
