# Inventário anti-esquecimento do Marketing — 2026-09-15

**Escopo:** classificação por equivalência de conteúdo, e não apenas por SHA,
dos worktrees locais relacionados ao plano de excelência do Marketing.
**Base verificada:** `origin/main` em `ae52f96b7`, depois dos merges #634, #674
e #675. Nenhum worktree foi apagado e nenhum branch deste inventário foi
publicado, rebaseado ou usado para disparar CI.

## Classificação

| Branch / commit verificado | Classificação | Destino ou equivalência | Próximo passo seguro | Bloqueio preservado |
|---|---|---|---|---|
| `codex/marketing-shadow-diagnostic-20260914` / `f4c8115b7` | Publicado | PR #675, já contido em `main` | Usar `diagnose_marketing` somente como leitura; não republicar o branch | `shadow.status=GO` não fecha o período observado nem autoriza rollout |
| `codex/tiktok-delivery-shop-20260912` / `dce671568` | Publicado | PR #634, já contido em `main` pelo merge `ae52f96b7` | Manter flags e adapters externos desligados até homologação/credenciais/gate | TikTok real e TikTok Shop continuam dependentes de aprovação externa e G-H09/G-H10 |
| `codex/marketing-canary-safe-default-20260914` / `5355113a9` | Publicado | PR #674, já contido em `main` | Preservar o default desarmado | Qualquer canary real exige alvo, janela, blast e rollback autorizados |
| `codex/shopman-legal-google-oauth-20260911` / `6b3946d56` | Publicado em PR, não em `main` | O conteúdo evoluiu até o head `8d7a59b65` do PR draft #614 | Não criar PR concorrente; retomar CI completa somente quando L1/L7 e a base definitiva estiverem resolvidos | #614 permanece draft; acesso Google e gates legais/operacionais não podem ser inferidos |
| `codex/marketing-final-integration-probe-20260914` / `943f437de` | Pronto somente local como referência de composição | União revisada de #614 com PWA/main, TikTok, canary seguro e diagnóstico shadow | Conservar como base de reconciliação sem push; atualizar semanticamente quando #614 for desbloqueado | Não é candidato de release independente; múltiplos merge-bases exigem nova composição sobre a `main` vigente |
| `codex/data-retention-l7-contract-20260914` / `1203bb974` | Experimento parcialmente aproveitável | Seis commits locais; o branch inteiro reabre decisões já fechadas | Extrair por unidade somente R10, R12 e R12/OTP sobre `943f437de`; não fazer cherry-pick amplo | Jobs e descarte produtivos continuam sujeitos a dry-run, alerta operacional e gate separado |
| `codex/marketing-r10-r12-replay-20260915` / base `943f437de` | Pronto somente local, em validação | Replay seletivo de R10, R12 e R12/OTP; não contém a regressão de gates do branch L7 | Rodar os testes focados, Ruff e `diff --check`; conservar local até #614 ter base definitiva | TTLs externos, classificação de tabelas, job monitorado, PostgreSQL/restore e autorização produtiva permanecem abertos |
| `codex/marketing-final-l7-probe-20260914` / `a5ba4986b` | Experimento obsoleto | Composição integral de L7 rejeitada pela auditoria semântica | Não publicar nem usar como superset; manter apenas como evidência histórica | Reabria indevidamente gates de cancelamento e maioridade |
| `codex/marketing-controls-triage-20260911-v2` / `5c2f1ce21` | Publicado | PR #601, já contido em `main` | Nenhuma ação | — |
| `codex/marketing-controls-triage-20260911` / `d4c5086c1` + 16 arquivos modificados | Experimento obsoleto/superado | A base está em `main`; primitivos e tokens úteis já aparecem no #601 e a `main` atual contém contratos posteriores de modalidade/formato, Stories e reparo acionável | Não aplicar o diff de 2.174 linhas nem sobrescrever a UI atual; preservar o worktree para auditoria pontual | O diff foi produzido antes das mudanças posteriores e removeria comportamento atual se aplicado cegamente |
| `codex/legal-cancellation-request-20260912` / `525c9c215` | Publicado | PR #629, já contido em `main` | Não republicar | A alteração local de `.nuxtrc` para `@nuxt/test-utils=4.3.2` é alheia ao PR; preservar para o respectivo owner decidir |
| `codex/marketing-local-inventory-20260915` / base `ae52f96b7` | Pronto somente local | Correção do gate de capacidade que dependia da hora real + este inventário | Reexecutar o gate 2× completo, registrar evidência e só então abrir PR enxuto | Nenhum deploy; G-H08 ainda exige baseline real, thresholds, paging, runbooks e on-call |

## Evidência técnica nova

O gate `make marketing-capacity` foi executado fora de produção, com banco de
teste descartável e adapters externos inertes. A execução final passou nos
quatro cenários. A resolução de público cobriu 200.000 candidatos / 100.000
elegíveis com p95 de 1,5114 s, seis queries e
pico de 82,6 MiB, todos dentro dos budgets.

O cenário de workers falhou porque usava `timezone.now()` e foi executado dentro
das quiet hours: os 20.000 destinos eram corretamente adiados e o teste lia
isso como capacidade zero. A reprodução isolada confirmou 0/0 leases. Depois
de congelar somente esse teste ao meio-dia de São Paulo, ele confirmou 100/100
leases distintos, seis queries por worker e no máximo 0,0738 s por claim. Nenhum
limite, consumer, adapter ou regra de horário do runtime foi alterado.

O diagnóstico shadow teve 7/7 testes focados aprovados. Isso valida o instrumento
e seus estados de divergência; não substitui os 7–14 dias ou volume acordado de
observação exigidos para MKT-051.

## Estado máximo defensável

A implementação técnica principal continua concluída, mas o plano inteiro não.
MKT-051 permanece parcial; MKT-052, MKT-053 e MKT-054 dependem dos gates humanos,
aprovações externas, piloto observado, rollout progressivo e limpeza posterior.
Nenhum resultado deste inventário autoriza deploy, envio, ativação de jobs ou
descarte em produção.
