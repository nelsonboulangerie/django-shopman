# Runbook de consolidação — correção e estado real das guardas
> 2026-11-10 · origin/main 057fe9105 · CORRIGE a versão anterior deste arquivo

## Correção honesta (o que eu errei)

Minha varredura anterior produziu dois alarmes falsos, porque não li as guardas existentes antes de declarar o gap. Isso é exatamente o sintoma do problema real (abaixo).

1. **Colisão de migração crítica e sem guarda — ERRADO.** As duplicatas 0023–0039 (shop) e 0036/0058/0065 (backstage) são CONHECIDAS, estão allowlisted em *LEGACY_PREFIX_COLLISIONS*, e o gate *scripts/check_migrations.py* (*migration_prefix_check*, id *migrations.prefix_collisions*) já reprova colisões NOVAS. São dívida estacionada para squash pré-go-live: limpeza, não urgência.

2. **Superfície importa kernel = violação sem guarda — ENQUADRAMENTO ERRADO.** O *test_import_boundaries.py* já enforça fronteira MATIZADA: superfície pode LER models públicos do kernel (import de pacote), mas NÃO pode (a) importar *models.<submódulo>* ou *contrib.<submódulo>*, (b) importar orderman write primitives (*ids*/*commit*/*modify*), (c) dirigir lifecycle direto em views do backstage, (d) importar outra superfície. O *from shopman.orderman.models import Order* no backstage é o caminho de leitura POR DESIGN, não um buraco.

## O problema real: as guardas existem (~30), mas não têm índice

A casa já tem: migrations, silent-swallow, orchestrator-units, admin-surface-boundary, adr-governance, surface-registry, surface-versions, do-spec-drift, instance-descriptors, legal-archive, registry-drift, release-readiness, runtime-gate, seed-reentrancy, semantic-docs, constraints, workflow-budgets, operator-component-ledger, unfold-canonical e import-boundaries (11+ testes).

**O gap não é falta de guarda. É guarda sem mapa.** Nem eu, auditando, achei as guardas existentes: assumi gap onde havia allowlist. Quem entra no repo tropeça no mesmo. O conserto é o item 1 abaixo.

## O que é genuinamente aberto (revisado)

| # | Item | Natureza |
|---|---|---|
| 1 | **Mapa de guardas**: documento único enumerando cada porta invariante + a guarda que a cobre + o comando que a roda | o entregável real |
| 2 | **promise extraída pela metade**: Stockman tem *decision_from_availability* e *promise_decision_for_sku*; shop ainda tem *_stock_decision* | concluir dual-run |
| 3 | **Squash de migrations** (resolver *LEGACY_PREFIX_COLLISIONS*) | limpeza pré-go-live |
| 4 | **except Exception que nunca levanta** em handlers transacionais (já há *check_silent_swallow*; auditar cobertura) | apertar |
| 5 | *shift_opened*/*shift_closed* sem ouvinte; craftsman best-effort documentado | assumido por design |

## W0 revisado (o que eu vou entregar primeiro)

1. **Mapa de guardas** (o índice que faltava) — documento + check que confere que toda porta listada tem guarda.
2. **ADR substituibilidade** (doutrina da Q6).
3. **ADR envelope operacional** (workstation + sector derivado).
4. **Concluir o dual-run do promise_for_sku** (matar *_stock_decision* no shop).
5. **Squash de migrations** (após coordenação com as worktrees ativas).

## Precisa da palavra do dono

1. Squash de migrations: coordenar com as worktrees ativas antes de tocar.
2. Aprovar o mapa de guardas como fonte canônica (Constituição aponta para ele).
