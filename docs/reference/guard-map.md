# Mapa de Guardas — índice das portas invariantes

> Status: canônico. A [Constituição](../constitution.md) aponta para cá. O *check_guard_map.py* confere que este mapa é completo, que cada guarda existe e que este documento cita todas elas.

Leia assim: cada linha é uma *porta invariante* (o que nunca pode quebrar), a *guarda* que a cobre e o *comando* que a roda. Porta sem guarda explícita está na seção 9.

As guardas das cláusulas pétreas (C2, C3, C5, C6, C7, C10, C11 e ADR-025) são AST, sem Django, e reprovam fechado contra uma baseline única, `scripts/constitution-baseline.json`: cada entrada diz se é **violação** (com a frente que conserta) ou **exceção** decidida (com o motivo). Achado novo reprova; entrada que deixou de acontecer também, até ser apagada no PR que consertou. `python scripts/check_<guarda>.py --strict` mostra o estado bruto, sem baseline. Todas rodam juntas em `make constitution-guards`, no job Quality do CI.

## 1. Fronteira e identidade dos kernels (C1, C3)

| Porta | Guarda | Comando |
|---|---|---|
| Kernel não importa host/orquestrador/superfície | test_import_boundaries.py::test_kernel_packages_do_not_import_host_layers | make test-framework |
| Kernel não importa outro kernel fora de bridge | test_import_boundaries.py::test_domain_kernels_do_not_import_each_other_outside_bridges | make test-framework |
| Kernel não alcança outro app via apps.get_model | test_import_boundaries.py::test_kernels_do_not_reach_other_apps_through_the_registry | make test-framework |
| Kernel referencia outro kernel por ref, nunca FK (alvo string ou importado) (C3) | check_cross_kernel_refs.py | make constitution-guards |

## 2. Orquestrador, decisão, ciclo e fato (C2, C4, C5, C6, C7, C11, ADR-025)

| Porta | Guarda | Comando |
|---|---|---|
| Inventário físico e unidades semânticas do orquestrador | check_orchestrator_units.py | make orchestrator-governance |
| Preço de lista com autoridade única no Offerman | test_offerman_is_the_only_list_tier_price_owner | make test-framework |
| Decisão canônica definida só no kernel dono; duplicação conhecida não volta; política de oferta (`stock_only`/`planned_ok`/`demand_ok`) só se compara no Stockman (C5) | check_decision_authority.py | make constitution-guards |
| Estado/transição de Order só no Orderman (C6) | check_order_lifecycle_owner.py | make constitution-guards |
| Lifecycle sem classe nem herança (C7) | check_lifecycle_functional.py | make constitution-guards |
| Dinheiro em campo de modelo é inteiro `_q` (C2) | check_money_integer.py | make constitution-guards |
| Ledger escrito só pelo dono; dentro do dono, sem reescrita (C11) | check_ledger_immutability.py | make constitution-guards |
| Anúncio por signal sai por on_commit; escrita acoplada declarada (ADR-025) | check_signal_on_commit.py | make constitution-guards |

## 3. Superfícies headless (C8), read-side (C10) e Admin/Unfold

| Porta | Guarda | Comando |
|---|---|---|
| Superfície não importa outra superfície | test_surfaces_do_not_import_each_other | make test-framework |
| Shop só toca superfície via adapters | test_shop_imports_surfaces_only_through_adapters | make test-framework |
| Framework não importa internals de kernel (models.x/contrib.x) | test_framework_does_not_import_protected_kernel_internals | make test-framework |
| Superfície não importa orderman write primitives | test_surfaces_do_not_import_orderman_write_primitives | make test-framework |
| View do backstage não dirige lifecycle diretamente | test_backstage_views_do_not_drive_order_lifecycle_directly | make test-framework |
| Projection/presentation não grava, direta ou transitivamente (C10) | test_read_side_does_not_write + test_read_side_never_writes | make test-framework |
| B.I. e backstage/presentation não escrevem em modelo de kernel (C10) | check_read_side_immutability.py | make constitution-guards |
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
| Este mapa é completo e cita toda guarda que existe | check_guard_map.py | make constitution-guards |

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
| Vocabulário/copy/UX nos apps Nuxt (noEmDash, jargon, copyNeverTruncates, identifiers, a11y…) | surfaces/operator-kit/tests/guardrails.*.test.ts (~30, entre eles guardrails.vocabulary.test.ts) | make test-operator-ux |
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
| Chamada a modelo de IA só pela porta, que freia e mede (ID3A, D-039) | check_ai_port.py | make ai-port |

## 9. ÁREAS NÃO COBERTAS (sem guarda explícita): o ponto de decisão

Estas portas têm lei (Constituição/ADR), mas ainda não têm check dedicado. É aqui que a decisão de travar ou assumir precisa ser tomada.

| Porta | Evidência de que está aberta | Risco se morder |
|---|---|---|
| Duplicação de autoridade de decisão (geral) | a promessa de estoque já tem autoridade única (`promise_for_sku`/`decision_from_availability` no Stockman; `_stock_decision` apagado, caracterização em `shopman/shop/tests/test_promise_for_sku_characterization.py`), travada por check_decision_authority.py, que também reprova comparar a política de oferta fora do Stockman ("pode pedir" em selo, substituto, anúncio, post social e falta na prateleira pergunta a `decision_from_availability`, caracterização em `shopman/shop/tests/test_pode_pedir_pergunta_a_promessa.py`); fora a promessa e o preço de lista, a guarda só conhece o que está registrado em `CANONICAL`/`FORBIDDEN`, e duplicação nova com outro nome passa | outra decisão duplicada diverge em produção |

O que as guardas da seção 2 ainda não enxergam, por limite do AST e não por decisão: escrita de ledger por related manager (`order.events.create`) ou por `instancia.save()` (C11; valem as travas de runtime dos próprios modelos); FK de modelo do orquestrador para kernel (C3 vale entre kernels; o orquestrador é o encontro, C4); `send` de signal sem `sender=` (ADR-025).

> O check_guard_map.py imprime esta seção 9. Cada linha é uma decisão do dono: travar agora (virar guarda) ou assumir convenção (e registrar o porquê).
