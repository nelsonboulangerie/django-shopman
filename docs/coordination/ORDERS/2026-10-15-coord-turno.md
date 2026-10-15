# ORDEM — 2026-10-15, turno da coordenação (DeepSeek Harness)

> Arquivamento durável da ordem do turno. O canal vivo é `ORDERS/next.md`,
> reescrito a cada turno pelo coordenador. Leia também
> `docs/coordination/HANDOFF-DSH-2026-10-15.md` (estado completo, ids, decisões)
> e `docs/plans/COORDENACAO-GO-LIVE.md` (papel, regras dos agentes, D1 a D12).

## Decisões do dono neste turno (15/10, 12:0x UTC) — não reabrir

1. **N:N cliente ↔ grupo: SIM.** O cliente pode pertencer a mais de um grupo
   comercial, valendo **a melhor vantagem por tipo, sem acumular**. É mudança de
   modelo no Core (`guestman`), autorizada explicitamente nesta conversa.
2. **Disco: limpar o que já está no `main`.** Autorizado remover as worktrees cujo
   branch já está contido em `origin/main`, preservando os branches no remoto.

## Estado no fechamento deste turno

- `origin/main` = `48eb028c2`. Fila de merge andando.
- **MERGED neste turno:** #1810 (`GET /api/sessions` responde 200, paginação por
  `opened_at`) e #1814 (card de desconto por tipo no B.I., seção de Vendas). As duas
  pendências que dependiam do dono desde 14/10 **saíram**.
- **Na fila / prontas, de outras sessões:** #1812 (Core N:N cliente em vários grupos
  e vantagens tipadas), #1815 (clientes: duplicar e etiquetar em lote), #1816
  (produção: cadastro direto da ficha de execução), #1809 e #1813 (Watchman, Codex).
- **Higiene de disco:** 185 worktrees removidas, 0 falhas. Livre foi de 34 GB para
  ~140 GB (92% para 67% de uso). Nenhum branch ou commit perdido.

## Reconciliado neste turno (evita retrabalho)

O Codex entregou, na madrugada de 15/10, o núcleo das ondas 3, 4 e 5 do §7.2:
#1802 (receitas no CRUD turbo), #1803 (cadastro completo de clientes), #1804
(grupos comerciais no Gestor), #1805 (instala grupos no banco vivo), #1806 (N+1 do
Compras), #1807 (Watchman).

Consequência medida: das 5 frentes do retorno do dono, **3 já tinham o núcleo no
`main`**. Elas entregaram (ou entregam) apenas o que faltava, e isso é correto:
- `cadastro-clientes` (#1815): o núcleo veio no #1803; a frente entrega duplicar
  cadastro e etiquetar em lote.
- `cadastro-receitas` (#1816): o núcleo veio no #1802; a frente entrega a ficha de
  execução no Nuxt.
- `grupos-core` (#1812): o #1804 entregou o CRUD do grupo e o desconto por faixa
  **com um grupo por cliente** (`Customer.price_tier` é FK única). O N:N do Core
  continua faltando, e é exatamente o que o #1812 implementa. **O dono confirmou
  que o N:N é o desenho certo** (decisão 1 acima), o que encerra a ordem anterior
  de "parar e reconciliar": o plano do #1812 já reconcilia com o #1804.

**Regra para o próximo coordenador:** antes de abrir qualquer frente do §7.2, rode
`git log origin/main --oneline -20` e `gh pr list --state all --limit 30`. O Codex
trabalha o mesmo plano em paralelo. Frente que duplica PR aberto se dispensa.

## Frente irmã que morreu neste turno (registro)

Uma frente nova de N:N Core foi aberta por esta coordenação e **interrompida antes
do primeiro edit**, ao detectar o #1812 vivo e mais adiantado (5 commits, plano
próprio, desenho melhor: M2M canônica + `PriceTierAdvantage`, com `primary_price_tier`
derivado). A worktree vazia foi removida e o branch local apagado. Nada se perdeu:
o trabalho ficou com o #1812, que é quem tinha o contexto.

Lição para o próximo turno: o `git worktree list` mostrou aquela frente em
`ad256f041` (base limpa) numa leitura e já em `c88c4e61e` minutos depois. **Frente
viva se mexe enquanto você olha.** Confira o PR, não só a worktree.

## Em voo agora

| frente | PR | estado | worktree |
|---|---|---|---|
| Core N:N cliente↔grupo + vantagens tipadas | #1812 | aberto, CI rodando | `.claude/worktrees/grupos-core-20261015` |
| Clientes: duplicar + etiquetar em lote | #1815 | aberto, CI rodando | `.claude/worktrees/cadastro-clientes-20261015` |
| Produção: ficha de execução no Nuxt | #1816 | aberto, CI rodando | `.claude/worktrees/cadastro-receitas-20261015` |
| Watchman (Codex, outro agente) | #1809, #1813 | na fila | `~/.codex/worktrees/*` |

## Defeito conhecido, NÃO corrigido (precisa de decisão)

**`GET /api/sessions` faz N+1 em `Session.items`.** Página cheia de 25 = 26
consultas (1 da página, 25 de `orderman_sessionitem`). O modelo já prevê o
prefetch: `_load_items_from_lines` lê `_prefetched_objects_cache["session_items"]`,
então basta `prefetch_related("session_items")` no `get_queryset` do
`SessionViewSet` para cair a 2 consultas. Verificado em `origin/main` `48eb028c2`:
o `prefetch_related` **não** entrou, o defeito segue vivo. É follow-up de uma
linha, de comportamento observável (26 para 2 consultas), e por isso pede a
palavra do dono antes de virar PR.

## Fila (quando as de cima fecharem)

- **Onda 5b (UI de grupos):** expor o N:N e as `PriceTierAdvantage` na API, na
  projection e no `orders-nuxt`. Depende do #1812 mergear. O plano do #1812 declara
  a 5b fora do escopo dele, então **é frente nova**.
- **WP-CATALOGO-IMPORT-SERVICE** (pós-go-live): import do catálogo vira service
  público, `ProductResource` vira adaptador fino. Não bloqueia a virada.
- **Unificar o `@zxing`** quando a câmera nativa cobrir iOS/Safari. Medido: seguem
  duplicados `surfaces/production-nuxt` e `surfaces/purchase-nuxt`
  (`useZxingScanner.ts`), com o canônico `useBarcodeScanner` no `operator-kit`.

## Não concorrer

`codex/watchman-*` (Shopman Watchman, outro agente) e o Codex no §7.2. Não tocar em
`.github/`, `.do/`, `surfaces/registry.json`, `operator-router/groups.json` nem nos
docs do Watchman sem conferir antes.
