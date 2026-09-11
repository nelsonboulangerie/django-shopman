# Brief e integração com main — 11/09/2026

## Evidência anterior e implementação

Brief externo e auditoria lidos integralmente; hashes, classificação e sequência
em `../../../ORDERS-CONTROLS-TRIAGE-2026-09-11.md`. Worktree próprio, nenhuma
mudança de terceiros transportada. `git fetch origin main` fixou
`0acb727ff8845595cff101ad23c77336681dcc9f`; não usado FETCH_HEAD mutável para rebase.

Backup `codex/orders-pre-brief-20260911` → `daf58b9c2`; 96 commits reaplicados,
resultado `aa412f87c`. Os hashes nos relatórios históricos permanecem resolvíveis.
Correção de integração `8669dce40` conserva código de erro seguro de notificação
do main e testa `outcome_unknown=True`; organiza imports da telemetria.

Resoluções revisadas:

- BFF: mesma allowlist operacional contém headers de receipt/idempotência e os
  headers upstream; preservados filtros de cookies, redirects, cache e segurança.
- Login: cópia local removida conforme main; consumer Orders usa
  `reload-on-success=false` + limpa station/refaz leitura. Não destrói draft nem
  compartilha estado entre pessoas; jornada integrada confirmou ambos.
- Inbox: lifecycle do stream e coalescimento mantidos sem segunda fonte de dados.
- Teste de período: mantida data fixa do main, já corrigida upstream.
- Telemetria: Marketing Web Vitals/redaction e observabilidade Orders convivem.
- ManyChat: nenhum subscriber id inventado como receipt; detalhes de erro
  permanecem redigidos; exceção/aceite incerto conserva unknown sem retry cego.
- Selects: preservado UiNativeSelect upstream, inclusive `bg-none` e comentário
  na barra invertida. Rail já44 px no main; não recriada correção equivalente.

## Testes efetivamente executados

| Rodada | Resultado | Log |
| --- | --- | --- |
| Orders Vitest | 303 passed, 4,62s | orders-unit.txt |
| Kit Vitest final | 255 passed, 3,34s | kit-final.txt |
| Orders typecheck | exit0 | orders-typecheck.txt |
| Orders build | exit0 | orders-build.txt |
| PostgreSQL conflitos: unknown/observabilidade/período | 58 passed,25,11s | backend-conflicts.txt |
| Seleção compartilhada inicial | arquivo inexistente, zero testes | backend-shared.txt |
| Seleção válida antes da correção | 59 passed,1 failed: código de erro divergente | backend-shared-valid.txt |
| Compartilhada final +unknown +ClientError/WebVitals | 85 passed,48,01s | backend-shared-final.txt |
| Browser Chromium → Nitro → Django → PostgreSQL/Redis | 29 passed,2min | integration.txt |
| Ruff dos quatro Python resolvidos | imports/re não usado detectados; corrigidos; final verde | ruff*.txt |

As famílias PostgreSQL se sobrepõem. Não houve skips nessas rodadas. Node22 e
ambientes Python/npm existentes foram reutilizados; não é instalação limpa.
Python prioriza worktree/packages no sys.path e usa somente venv original para
leitura. Warning NO_COLOR/FORCE_COLOR no browser preservado. Não reexecutada a
suíte ampla8.718 deste diário nem a cadeia completa dos outros consumidores.

Build/units usam árvore aa412 mais limpeza de whitespace do BFF. O servidor8014
das jornadas foi iniciado nessa árvore;8669 muda somente código seguro do erro de
exceção e imports, cobertos na rodada PostgreSQL final. Não se atribui ao browser
um ensaio desse ramo de exceção. Screenshots de avanço e motivo inspecionados;
não são matriz visual/contraste light-dark completa.

## Resultado e esforço

As29 jornadas revalidaram: um POST em resposta perdida +consulta do mesmo receipt;
SSE preservando nota/preço/feed; disputa exige escolha; mesma pessoa retoma texto,
outra pessoa não herda; confirmação de descarte/reload mantida; preço/curadoria/
publicação adotam receipt; leitura falha conserva contexto; ação já confirmada
não regride quando o GET seguinte falha. Alvos44/48 e ícones também verificados.
Não se acrescentou gesto nem removeu confirmação ou permissão para integrar main.
Não há observação humana nem ganho de30% comprovado.

Desempenho não remedido nesta rodada: último browser500 p951951ms contra1500;
backend500/10 clientes, quatro processos, p95898,565ms contra500. Continuam
**reprovados**, sem exclusão ou relaxamento aprovado. G06 ainda exige aparelho,
rede, carga/coorte e assinatura dos critérios; esta integração não encerra T.

## Migração e rollback

Parados somente os dois servidores próprios, conferindo PID e cwd, antes de
reabrir servidor sobre código novo. Aplicadas migrações upstream no banco
`orders_lab` em127.0.0.1:55439, com Redis próprio56389/0. Log migrate.txt.
Seed apenas sintético e sem workers/adaptadores externos; não exportados cookies.
O ajuste Orders não acrescenta DDL, mas o main integrado contém migrações de
Marketing/consentimento/notificações. Backup de branch preserva código histórico,
**não** autoriza rollback de schema nem desfazer dados.

Rollback de capacidade mantém backend seguro, receipts e fences de unknown;
worker antigo continua inseguro. A versão anterior permanece para comparação,
não para reativação automática. Produção, reconciliação, comunicação, despacho,
fiscal e dinheiro reais não executados.

## Gates e sequência restante

T aberto, piloto preparado/não iniciado, rollout não autorizado. G01–G08 continuam
conforme PILOT-PROTOCOL. Novo gate de hierarquia de opacidades apresentado ao dono,
sem resposta presumida. A/B/C preparados por classificação, ainda dependentes do
encerramento da branch operacional conforme §3 do brief. Nenhum PR/push/merge ou
deploy foi executado nesta rodada.
