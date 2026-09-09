# Execução Marketing — WP-00 — sessão 2026-09-08 Codex

## Identidade e isolamento

- Plano solicitado: `docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`, lido integralmente a partir do checkout compartilhado, onde é arquivo não rastreado de outra sessão.
- Branch exclusiva: `codex/marketing-irrepressible-excellence-20260908`.
- Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-marketing-irrepressible-20260908`.
- Baseline/HEAD: `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`.
- O checkout compartilhado e todas as mudanças rastreadas ou não rastreadas de terceiros permaneceram intocados.
- Não foram encontrados arquivos `AGENTS.md` aplicáveis no HEAD.

## Leitura obrigatória concluída

Foram lidos antes da primeira alteração:

- o plano integral, inclusive dependências, gates, rollout, rollback e Definition of Done;
- `.codex/skills/unfold-admin-canonical/SKILL.md`;
- `docs/engineering/unfold_admin_page_playbook.md`;
- `docs/engineering/unfold_canonical_policy.md`;
- `docs/reference/unfold_canonical_inventory.md`;
- ADR-009, ADR-012, ADR-014, ADR-016, ADR-019, ADR-020 e ADR-021;
- `docs/engineering/nuxt_design_system.md`;
- `docs/engineering/backstage-design-system.md`;
- `surfaces/operator-kit/README.md`;
- `docs/reference/projection-contracts.md`.

## Comparação do baseline com o código atual

O HEAD desta sessão é byte a byte o baseline auditado pelo plano. Os achados iniciais foram revalidados no código, sem inferir que o relatório antigo continuava correto:

- `shopman/shop/services/audience.py::_filter_opted_in` ainda mantém qualquer recipient com reason `alerts` antes de consultar o opt-in global;
- `CommunicationConsent` ainda é uma linha mutável única por customer+channel e `ConsentService` ainda usa `update_or_create` em grant/revoke, sem evento append-only, purpose, disclosure version ou evidence hash;
- toda a API Marketing ainda usa `shop.manage_campaigns`, incluindo aprovação, fire, teste e configuração;
- `WhatsAppTestSendView` ainda aceita recipient livre, registra recipient no log e não exige idempotency key, throttle, allowlist/sandbox verificado ou capability própria;
- a API ainda interpreta `publish_now` booleano, enquanto `AnnouncementCard.vue::publishNow` não o envia;
- `campaign._platform_content` ainda substitui o `body` da variante pelo corpo comum;
- `campaign.render` ainda converte variável desconhecida em vazio;
- o adapter ManyChat ainda retorna apenas `bool`, grava campos personalizados em chamadas separadas antes de `sendFlow`, não expõe receipt/reconcile/idempotency e converte timeout/erro ambíguo em falha comum;
- o adapter Meta direto `notification_whatsapp.py` ainda existe, em divergência com ADR-009 para o caminho WhatsApp;
- `handlers.campaign` ainda faz read-modify-write de `platform_results`, agrega waves sem lock e pode encerrar `pending_manual`/`partial` como publicado;
- `CampaignForm.vue` ainda reconstrói somente um subconjunto de `audience_rules`, descartando campos que não representa;
- a action de notificação ainda usa `approve` como default quando `action` está ausente.

Busca em `docs/`, `shopman/`, `packages/` e `surfaces/` não encontrou ata, ADR, policy versionada ou evidência assinada que feche G-H01, G-H02, G-H03 ou G-H04. O único resultado relacionado fora do plano foi uma menção genérica a throttle ManyChat, insuficiente para qualquer gate.

## Gate atingido e estado

Execução interrompida antes de MKT-001/WP-00, conforme instrução do usuário e Fase 0 do plano.

Motivos:

1. MKT-001 depende explicitamente de G-H03; a taxonomia do fake provider e o contrato de `unknown` não podem alegar capacidade externa que o owner ManyChat/Meta ainda não comprovou.
2. WP-01 não pode contratar precedence, purpose, legado, retenção, erase ou min cohort sem G-H01.
3. Persistir membership contradiz a invariante histórica da ADR-020 e exige G-H02 com threat model, encryption/access, retenção, volume e auditoria.
4. Capabilities, step-up, quotas, dual control e emergency revoke exigem G-H04 antes do enforcement; o agente não pode escolher thresholds de blast.

Nenhum código de produto, teste, migration, schema, lockfile, configuração, CI, Admin ou documento central foi alterado. Nenhum teste com rede, destinatário, provider, produção ou sandbox foi executado. Não houve deploy, push, PR, merge, escrita em produção nem envio real.

## Decisões/evidências necessárias para retomar

- **G-H01 — DPO/Jurídico + Produto:** precedence; purposes; texto/hash/versionamento do disclosure; tratamento do legado; retenção; erase/tombstone; min cohort.
- **G-H02 — DPO + Arquitetura + Dados:** threat model do cohort; cifragem/identificador; matriz de acesso; retenção/erase; volume; auditoria de acesso.
- **G-H03 — Owner ManyChat/Meta + SRE:** documentação ou ensaio autorizado em sandbox sobre idempotency token, receipt/callback, consulta/reconcile, timeout com efeito perdido, webhook/replay e rate/`Retry-After`.
- **G-H04 — Segurança + Operações:** role×capability; freshness de step-up/2FA; quotas/limites por blast; typed confirmation; dual control; emergency revoke; memberships dos grupos.

Ao retomar com essas decisões registradas, o próximo passo é MKT-001/WP-00: reproduções adversariais sem rede e contratos executáveis, antes de qualquer implementação runtime.

## Follow-up — pacote recomendado para confirmação

O proprietário pediu que o agente proponha todas as decisões e deixe para ele somente a confirmação/autorização. Foi criado `marketing-human-gates-proposal-20260908-codex.md`, ainda com status **PROPOSTA — NÃO APROVADA**.

A proposta:

- define as escolhas conservadoras de G-H01–04 necessárias para implementação técnica;
- documenta a ausência de idempotency/receipt/reconcile no contrato público ManyChat e mantém `unknown` sem retry automático;
- define defaults provisórios para G-H05–08;
- mantém G-H09/G-H10 contextuais, sem autorização permanente de release ou produção;
- fornece uma única declaração de confirmação humana.

Fontes oficiais consultadas em leitura: LGPD compilada/ANPD, OpenAPI/Help do ManyChat e OWASP/NIST para autorização transacional e step-up. Nenhuma credencial, sandbox, provider ou ambiente externo foi acionado. A execução dos WPs continua parada até a confirmação da seção 13 da proposta.

## Confirmação humana recebida

Em 2026-09-08, após receber a proposta integral e a declaração de autorização, o proprietário respondeu: “ok, pode prosseguir dessa forma.” A referência é inequívoca ao pacote `marketing-human-gates.v1`; G-H01, G-H02, G-H03 e G-H04 estão fechados para implementação exclusivamente local nos limites aprovados.

Continuam fechados: deploy, escrita em produção, credenciais ou sandbox externos, envios reais, merge, push, PR, piloto e rollout. G-H05, G-H06 e G-H08 continuam sujeitos às evidências previstas; G-H09 e G-H10 exigem autorização específica futura. A execução pode retomar em MKT-001/WP-00.

## MKT-001 — contratos executáveis e fornecedor adversarial

Implementado em 2026-09-08:

- vocabulário fechado de command, delivery e outcome externo;
- transições que proíbem retry cego de `unknown`;
- envelope de erro com `code`, `detail`, `retryable`, `field_errors`, `request_id` e `current_version`;
- `ResolvedDispatchArtifact` imutável, serialização canônica e hash SHA-256 sem destinatário;
- `Clock` injetável e relógio de teste consciente de timezone;
- fake provider hermético que distingue falha antes da chamada, rejeição, aceite e efeito ocorrido com resposta perdida;
- teste explícito que bloqueia qualquer tentativa de rede pelo fake.

Provas locais:

- `ruff check shopman/shop/services/marketing_contracts.py shopman/shop/tests/marketing_fakes.py shopman/shop/tests/test_marketing_contracts.py` — passou;
- `pytest -q shopman/shop/tests/test_marketing_contracts.py` — 9 testes passaram em 0,07 s;
- nenhum destinatário real, provider, credencial, sandbox ou rede foi usado.

Próxima dependência liberada: MKT-002, reprodução da precedência `opt-out > alert subscription`, seguida de MKT-003 para o histórico append-only de consentimento.

## MKT-002 — opt-out prevalece sobre assinatura de alerta

Reprodução antes da correção: `test_global_optout_suppresses_active_stock_alert_subscription` falhou com audiência total `1`, comprovando no código atual que o motivo `alerts` ultrapassava o opt-out global.

Correção local:

- a filtragem agora consulta, em uma única query limitada ao cohort, o estado explícito de consentimento;
- `opted_out` suprime qualquer motivo, inclusive assinatura específica;
- assinatura conhecida sem revogação continua limitada ao SKU; audiência geral ainda exige `opted_in`;
- falha da fonte é fail-closed para identidades conhecidas;
- assinatura anônima permanece possível porque não existe identidade global correlacionável.

Provas locais, com `PYTHONPATH` apontado explicitamente para os packages desta worktree:

- teste vermelho original: 1 falha pela assertiva esperada (`1 != 0`);
- `test_marketing_consent_contract.py`, `test_audience.py` e `test_audience_manual.py` — 75 passaram;
- testes Guestman filtrados por consentimento — 13 passaram.

O `PYTHONPATH` explícito é obrigatório porque o virtualenv compartilhado contém editables que apontam para o checkout original. A detecção evitou validar por engano código de terceiros; o checkout original não foi modificado.

## MKT-003 — histórico append-only e projeção atual de consentimento

Implementado de forma aditiva:

- `CommunicationConsentEvent` registra grant, revoke e import legado com finalidade, base, texto/versão/hash, locale, origem, instante, ator, IP e evidence hash;
- evento recusa update/delete por instância e queryset;
- `CommunicationConsent` passa a ser projeção reconstruível do último evento;
- opt-in novo exige disclosure textual e versão, fica `verified` e é marketable;
- opt-in legado é migrado como `legacy_unverified`, sem texto ou versão fabricados, e não entra em Marketing;
- opt-out legado continua soberano mesmo sem prova histórica completa;
- reativação depois de revoke produz um novo evento explícito;
- leituras de Marketing exigem status `opted_in` e prova `verified`.

Provas locais:

- migration test executou 0001 → 0002 e confirmou import sem prova fabricada — passou;
- reconstrução do current state após corrupção controlada da projeção — passou;
- imutabilidade por instância e bulk queryset — passou;
- suites audience/notification/consent: 90 passaram;
- suites Guestman CRM/ManyChat/merge: 120 passaram e 1 foi ignorado;
- `makemigrations --check --dry-run customer_consent` — sem drift;
- Ruff dos arquivos tocados — passou.

A checagem de migrations em banco vazio emitiu apenas o warning já existente de SQLite e logs defensivos de bootstrap; não houve falha nem acesso externo.

## MKT-004 — assinatura de disponibilidade com prova, cancelamento e recheck

Implementado:

- identidade normalizada e pseudonimizada por HMAC para unicidade de `(SKU, tipo, canal, alvo)` enquanto pendente;
- constraint parcial no banco e recuperação do vencedor de uma corrida equivalente;
- disclosure específico de disponibilidade, versão, hashes de texto/evidência e expiração automática em 30 dias;
- legado migrado como `legacy_unverified`; duplicatas legadas são encerradas de modo rastreável;
- nova confirmação encerra o registro legado e cria prova nova, sem reescrever história;
- cancelamento idempotente com ownership por cliente ou marcador da sessão anônima;
- API devolve ref/expiração e permite cancelar sem enumerar assinatura alheia;
- consultas e audiência só consideram inscrições verificadas, não revogadas, não notificadas e não expiradas;
- imediatamente antes do adapter, a linha é travada e revogação, expiração e opt-out global são rechecados;
- o lock ao redor do adapter legado é uma contenção temporária explicitamente documentada para ser substituída pelo ledger do WP-03.

Provas locais:

- unicidade de banco, dedupe de formatos telefônicos, ownership/IDOR, revoke-before-send, opt-out-before-send, evidence e expiração cobertos;
- `test_stock_alerts.py`, audience, consent contract e campaign handlers — 93 testes passaram;
- `makemigrations --check --dry-run storefront` — sem drift;
- Ruff dos arquivos tocados — passou;
- zero chamada real a backend/provider nos testes.

## MKT-005 — audiência explicável, normalizada e fail-closed

Implementado:

- telefone normalizado antes da deduplicação e do cohort hash;
- `AudienceSummary` aditivo com elegíveis, exclusões por motivo, duplicatas removidas, fontes degradadas, freshness, expiração, policy version e hash do cohort;
- hash HMAC/SHA-256 sem telefone ou customer ref na Projection/log;
- falha de fonte deixa `degraded_sources` explícito e bloqueia criação/dispatch, em vez de parecer uma audiência autoritativamente vazia;
- opt-out, ausência de consentimento e consent indisponível têm contagens distintas;
- interseção registra exclusões por `rule_mismatch` e contato inválido é contabilizado;
- Projection informa `can_approve=false` e motivo recuperável quando degradada;
- leitura de perfis/insights/loyalty foi batched, removendo N+1.

Provas locais:

- outage de favoritos retorna zero degradado, nunca zero silencioso;
- campanha automática com fonte degradada cria zero anúncio e zero directive;
- normalização/dedupe, fechamento matemático das exclusões e ausência de PII no resumo passaram;
- cohort de 100 clientes foi resolvido em exatamente 3 queries;
- suites de audiência, campanha, handlers e API Marketing — 238 testes passaram;
- Ruff dos arquivos tocados — passou.

## MKT-006 — snapshot privado e revalidação somente subtrativa

Implementado:

- `AudienceSnapshot` selado com summary, rule summary sanitizado, HMAC da regra, cohort hash, policy version, freshness e retenção de 90 dias;
- `AudienceSnapshotMember` persiste apenas FK interna de cliente ou ref segura de assinatura, target key HMAC e atributos operacionais; não existe campo telefone;
- lista explícita de `customer_refs` vira somente contagem no rule summary, enquanto o HMAC preserva integridade do input completo;
- resolução degradada ou vencida não pode ser selada;
- materialização busca o contato somente no último limite, revalida cliente, opt-out e assinatura, e apenas remove membros;
- opt-in posterior não cresce o snapshot; revoke posterior remove antes do contato;
- mudança posterior de telefone é late-bound sem mudar membership;
- assinatura anônima é ligada pela ref segura e deixa de materializar após cancelamento;
- snapshots/members não foram registrados no Admin nem expostos pela Projection/API.

Provas locais:

- cohort com opt-in tardio permaneceu com o mesmo membro;
- opt-out e revoke de assinatura subtraíram corretamente;
- teste estrutural confirmou ausência de telefone no model de membership e ausência de ref/telefone no resumo;
- suites snapshot/contratos/audience/storefront — 128 testes passaram;
- `makemigrations --check --dry-run shop` — sem drift;
- Ruff dos arquivos tocados — passou.

WP-01 está tecnicamente concluído para o escopo local; as políticas aprovadas permanecem documentadas e os ensaios humanos/externos continuam fechados pelos gates próprios.

## MKT-007 — capabilities e transição legada deny-safe

Implementado conforme o G-H04 aprovado:

- quatorze permissions separam view, edição de campanha, edição de template, preview, approve, publish, fire, retry seguro, reconcile unknown, teste, configuração, audit, PII e freeze;
- cada método da API Marketing declara suas capabilities; não há fallback implícito quando o método não foi mapeado;
- a permissão ampla `shop.manage_campaigns` mantém somente view/edit/preview durante a janela de auditoria e não autoriza approve/publish/fire/test/config;
- diferenças de autorização legada são registradas por decisão, reason code, ator técnico, método, path e capabilities, sem payload ou PII;
- aprovação no endpoint legado, que ainda também despacha, exige simultaneamente approve e publish até MKT-009 separar os comandos;
- a Action de notificação pessoal deixou de contornar o gate e aplica a mesma separação approve/publish;
- notificações de revisão são endereçadas somente a atores realmente capazes, inclusive quando `notify_users` foi configurado explicitamente;
- `Gerente` recebe somente view/edit/preview; a permissão ampla saiu da fonte de verdade do deployment;
- sete grupos capability-based nascem sem membros, preservando escolha nominal e dual control humanos;
- o destrave do Nuxt pede apenas `view_marketing`; Actions continuam revalidadas pelo backend.

Provas locais:

- default deny para leitura e efeito externo;
- fallback legado aceitou board/preview e recusou approve, fire, test-send e platform config;
- Editor não decide, Aprovador não atravessa o endpoint legado acoplado, Publisher não configura plataforma e Platform Owner não herda publish;
- matriz exata dos sete grupos e ausência de membros verificadas no banco de teste;
- suites de capabilities, API Marketing, notificações, E2E, campanha, paridade e grupos: 197 testes passaram;
- Ruff dos arquivos Python tocados e `git diff --check`: passaram;
- migration aditiva `shop.0024_marketing_capabilities`; nenhum grupo, usuário ou ambiente externo foi alterado fora do banco efêmero de teste.

## MKT-008 — test-send sandbox, unitário, idempotente e sem PII

Implementado:

- API e CLI deixaram de aceitar telefone, subscriber, backend ou audience rules livres;
- targets vêm exclusivamente de `SHOPMAN_MARKETING_TEST_TARGETS_JSON`, e só entram quando `sandbox=true` e `ownership_verified=true` ou `synthetic=true`;
- o browser recebe apenas ref, label não sensível e backend; o recipient real permanece server-side no boundary do adapter;
- payload fora da allowlist é recusado com 422 antes de resolver backend, audiência ou catálogo;
- cada tentativa exige `Idempotency-Key`, cuja forma raw não é persistida; same key+same payload reproduz o receipt sem novo efeito e payload diferente retorna 409;
- `MarketingTestReceipt` guarda hashes HMAC de key/payload/artifact, actor, target ref segura, estado, backend e retenção mínima de 180 dias, sem telefone, body ou resposta do vendor;
- receipt é marcado `sandbox=true`, `max_targets=1` e protegido por constraints de banco;
- exception após o boundary vira `unknown`, preserva receipt e nunca é repetida automaticamente;
- sandbox indisponível retorna 503 com receipt seguro; provider detail e exception message não atravessam response/log;
- quotas G-H04 de 5 testes/h por ator e 20/24h por loja retornam 429 com `Retry-After`; a reserva é serializada por lock curto no banco, sem manter lock durante o provider;
- capability é consultada novamente no banco imediatamente antes do adapter, sem confiar no cache da request;
- CLI exige target ref, ator staff capaz, idempotency key e `--send`; sem `--send`, é dry-run e não mostra recipient;
- Nuxt removeu o campo de telefone/nome, escolhe automaticamente o único aparelho verificado, gera idempotency key e mostra receipt/estado;
- o BFF compartilhado passou a preservar `Idempotency-Key` e, por allowlist, `Retry-After`, `ETag`, `X-Request-ID` e `X-API-Version`.

Budget de omotenashi comprovado:

| Trabalho do operador | Antes | Depois |
|---|---:|---:|
| Redigitar/conferir telefone ou subscriber | 1 entrada livre + conferência externa | 0 |
| Escolher alvo quando existe apenas um verificado | 1 decisão | 0, pré-selecionado |
| Navegar/abrir terminal | possível caminho alternativo | 0 |
| Criar/guardar chave de retry | manual/inexistente | 0, automática |
| Descobrir o que ocorreu após timeout | incerto | 1 receipt seguro visível |
| Targets por ação | não garantido no banco | exatamente 1 |

Provas locais:

- API/CLI cobrem payload isolado, target allowlisted, ausência de PII em response/log/model, idempotência, conflito, `unknown`, indisponibilidade, quotas, receipt/retention e ausência de chamada ao audience resolver;
- suites Marketing/API/adapter/campanha: 207 testes passaram; suíte final específica API+CLI: 19 passaram;
- Marketing Nuxt: 93 testes, lint e typecheck passaram; build Nuxt 4.5.2 passou;
- operator-kit: 172 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- somente fake adapter foi chamado; nenhuma credencial, rede, sandbox remoto, telefone ou produção foi usada.

## MKT-009 — receipt, versão monotônica, CAS e replay idempotente

Implementado de forma aditiva, preparando a transação composta do MKT-010:

- `Announcement.version` nasce em 1, é exposta na Projection/tipo TS e avança sob row lock;
- `MarketingCommandReceipt` registra ref, kind, state, resource, actor da sessão, hashes HMAC de key/payload, versões base/resultante, outcome seguro, request ID e retenção de 5 anos conforme G-H01;
- a chave raw não é persistida e receipt recusa campos de PII ou conteúdo bruto, inclusive aninhados;
- o executor trava primeiro o ator e depois o announcement, reconhece replay antes de comparar versão e mantém uma única linha por ator+key;
- mesma key+mesmo payload devolve o mesmo receipt/outcome sem executar novamente;
- mesma key+payload diferente retorna semântica 409 apontando para o receipt original;
- key nova com `base_version` stale registra um receipt `conflict`, informa `current_version` e não executa a operação;
- sucesso, mutação de domínio e avanço da versão acontecem na mesma `transaction.atomic`;
- rejeição de domínio usa savepoint: qualquer escrita parcial do callback é desfeita, mas o receipt `rejected` permanece reapresentável;
- falha inesperada desfaz tanto mutação quanto receipt, sem deixar um comando falsamente aceito;
- edição de rascunho ganhou CAS opcional compatível; conflito preserva o texto vigente e responde 409, enquanto boolean/versão inválida responde 422;
- o caminho legado de approve/reject ainda não foi conectado artificialmente a metade da transação: MKT-010 fará a composição única com artifact, snapshot, audit e outbox, conforme a dependência do plano.

Budget de omotenashi comprovado na fronteira:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Duplo toque/retry com a mesma intenção | retorno silencioso dependente do estado | 1 receipt estável, 0 segunda mutação |
| Descobrir se a tentativa original venceu | inferir pelo card/fila | receipt + state + resulting version |
| Sobrescrever edição mais nova | possível | 0 quando `base_version` é enviado |
| Diagnosticar conflito | mensagem genérica | `current_version` e campo reparável no próprio response |
| Conferir conteúdo/PII em log de comando | revisão manual | proibido estruturalmente no outcome |

Provas locais:

- 13 testes novos cobrem sucesso, replay, key conflitante, CAS stale reapresentável, rollback de rejeição, crash inesperado, PII/content scan, recurso ausente, ator inativo, timestamps e edição stale;
- contratos + commands: 22 testes passaram;
- regressão campanha/handlers/scheduler/API/capabilities: 197 testes passaram após os dois novos testes de API;
- Marketing Nuxt: typecheck e 93 testes passaram;
- Ruff, `git diff --check` e `makemigrations --check --dry-run`: passaram;
- migration aditiva `shop.0026_marketing_command_receipt`; nenhum provider, rede, produção ou banco externo foi tocado.

## MKT-010 — aprovação atômica com artifact, snapshot, audit e outbox

Implementado:

- `MarketingContentArtifact` sela o payload JSON completo da versão aprovada, valida SHA-256 sobre bytes canônicos e bloqueia save/update/delete posterior;
- `AudienceSnapshot` é criado para a mesma `resulting_version`, com membership privado e retenção de 90 dias já aprovada no G-H02;
- `MarketingAuditEvent` append-only liga command, actor da sessão, announcement, versões, artifact, snapshot, instante e fatos operacionais sem conteúdo/PII; command/audit/artifact preservam evidência por 5 anos;
- `MarketingOutbox` cria uma lane por plataforma/onda com available-at absoluto, FKs para o grafo selado e unique por command+platform+wave;
- conteúdo, platforms, audiência, decisão, artifact, snapshot, audit, receipt e outbox são gravados dentro da mesma transação do executor MKT-009;
- nenhuma chamada de provider e nenhuma `Directive` legada ocorre nessa request; consumidor/lease entra somente no MKT-012;
- falha injetada depois de artifact/snapshot/outbox e antes do audit reverte tudo, inclusive receipt e mutação do announcement;
- `publish_mode` é enum explícito `now|scheduled`: now com data, scheduled sem data/passado ou timestamp sem timezone são recusados;
- WhatsApp geral abaixo de 10 elegíveis é bloqueado antes de qualquer linha com formato de efeito; exatamente 10 sela 10 members e uma wave;
- API migra aditivamente: request que declara version/mode/key entra obrigatoriamente no comando v2 e nunca faz downgrade; cliente legado permanece temporariamente no caminho antigo até o corte previsto;
- resposta v2 inclui receipt estável, replay flag, versões e outcome seguro; key igual com conteúdo diferente retorna 409;
- Nuxt envia `base_version`, `publish_mode` e `Idempotency-Key` automaticamente e mantém a mesma key para a mesma versão+consequência, inclusive depois de resposta perdida;
- copy de sucesso diz “preparado para publicação”, não “publicado”, porque outbox ainda não prova efeito externo.

Budget de omotenashi comprovado:

| Trabalho do operador | Antes | Depois |
|---|---:|---:|
| Informar/lembrar version, mode ou idempotency key | inexistente/manual | 0; cliente deriva e conserva |
| Repetir após resposta perdida | risco de nova decisão | mesmo receipt, 0 nova mutação/outbox |
| Conferir se conteúdo e audiência pertencem à mesma aprovação | múltiplos estados inferidos | 1 grafo ligado por versão/hash/FKs |
| Esperar provider durante o clique | duração/resultado externo incerto | 0 chamadas externas na request |
| Distinguir “aceito para processar” de “publicado” | mensagem otimista | consequência honesta no próprio toast/card |
| Diagnosticar conflito depois de nova edição | comparar manualmente | receipt + `current_version`, draft vigente preservado |

Provas locais:

- 14 testes MKT-010 cobrem grafo atômico, byte/hash exato, cópia defensiva, replay, rollback total, instante agendado único, modos inválidos, min cohort, imutabilidade/hash forjado e reverse/reapply da migration;
- commands + approval + API: 106 testes passaram;
- regressão Marketing/campaign/audience/notifications/E2E: 269 testes passaram sem provider real;
- Marketing Nuxt: lint, typecheck e 94 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0027_marketing_approval_outbox`; nenhuma rede, credencial, produção ou escrita externa foi usada.

## MKT-011 — reject/cancel/reschedule/expire transacionais e auditados

Implementado:

- `reject`, `cancel` e `reschedule` usam o mesmo executor idempotente/CAS do MKT-009 e produzem receipt + audit na transação da mudança;
- rejeitar um draft registra ator/motivo e versão; rejeitar um agendamento também cancela todas as lanes ainda pendentes;
- cancelar marca o anúncio `cancelled`, limpa o horário e grava em cada lane o tombstone `cancelled_by_command`/`cancelled_at`;
- qualquer lane `claimed`, `dispatched` ou em outro estado não pendente bloqueia a promessa de cancelamento/reagendamento com `dispatch_already_started`;
- reagendamento aceita somente anúncio aprovado ainda agendado, move todas as lanes por um único delta e preserva atraso relativo de waves;
- duas decisões com a mesma base version têm um vencedor; a segunda recebe receipt `version_conflict` e não sobrescreve a primeira;
- expiração deixou de ser `QuerySet.update` opaco: cada item recebe lock, version, command receipt, audit e transição atômica;
- o ator de expiração é explicitamente `system:marketing-expiry`, com FK humana nula; nenhuma conta/pessoa fictícia é criada;
- receipts/audit agora têm `actor_ref`; comandos humanos continuam ligados à sessão por FK e ref `user:<pk>`;
- a migration preenche `actor_ref` dos receipts/audits já existentes e mantém unique próprio para comandos de sistema;
- endpoints v2 de reject/cancel/reschedule exigem base version e idempotency key, rejeitam campos desconhecidos e devolvem o mesmo envelope seguro;
- Nuxt passou a gerar e reaproveitar automaticamente idempotency key também na recusa; o motivo continua opcional conforme G-H04;
- o reject legado permanece somente para consumidores ainda não migrados (notificação pessoal), cuja retirada ordenada está em MKT-036/037.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Cancelar lanes individualmente/conferir fila | não existia | 1 comando atômico |
| Reagendar plataformas/waves separadamente | N ajustes ou caminho inexistente | 1 horário; offsets preservados |
| Saber se “cancelar” ainda vale | inferência externa | resposta imediata `dispatch_already_started` |
| Lembrar version/key ao recusar | manual/inexistente | 0; Nuxt deriva e conserva |
| Explicar por que um item sumiu por prazo | bulk state sem autoria/evento | receipt + audit + reason code |
| Recuperar duplo toque/resposta perdida | risco de segunda transição | mesmo receipt, 0 segunda mudança |

Provas locais:

- 10 testes MKT-011 cobrem reject pendente/agendado, tombstone, cancel replay, claimed/dispatched, reschedule com offset, disputa CAS, expiry idempotente, crash rollback e reverse/reapply da migration;
- transitions + approval + commands + API + campanha/notificações/capabilities: 262 testes passaram;
- Marketing Nuxt: lint, typecheck e 94 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0028_marketing_transactional_transitions`; nenhum provider, rede, produção ou escrita externa foi usado.

## MKT-012 — outbox claim/lease/reconciler e crash recovery

Implementado:

- consumidor dedicado faz claim somente de rows commitadas e vencidas, em batch limitado, com `select_for_update(skip_locked)` quando o banco suporta;
- o budget inicial autorizado pelo pacote, sem declarar G-H08 fechado, está codificado: batch 100, lease 60 s, máximo de 5 tentativas e backoff limitado;
- estado `claimed` exige owner + prazo de lease no banco; qualquer outro estado proíbe lease residual;
- a `Directive` durável e a transição para `dispatched` são gravadas na mesma transação, com `dispatch_ref` único e timestamp obrigatório;
- o callback já existente da fila roda somente depois desse commit; queda anterior não cria fila, queda posterior deixa uma única fila retomável;
- payload da fila carrega refs/hash/version do artifact e snapshot aprovados, sem conteúdo, membership, telefone ou idempotency key;
- antes do handoff, o consumer revalida status, prazo, command concluído, versões/refs do grafo, platform aprovada e hash byte a byte do artifact;
- dedupe encontrado com topic/payload divergente falha fechado como `directive_identity_mismatch`; nunca é aceito por coincidência de chave;
- reconciler liga fila durável já existente, recupera lease stale ainda segura, encerra budget esgotado e apenas alerta — sem blind retry — se um dispatch já conhecido perdeu a fila;
- anúncio agendado v2 não cai também no scheduler legado; o primeiro handoff válido move `approved` para `publishing` e limpa `publish_at`;
- `process_marketing_outbox` suporta ciclo único/watch e isola falha por row; o maintenance worker o chama silenciosamente como fallback;
- `SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED` nasce `False` e é repinado `False` nos testes; `--force` é impossível fora de development/test;
- logs estruturados expõem somente counts e idade da outbox: claimed/dispatched/requeued/failed, lease recovery/failure, linked e oldest due age.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Resgatar aprovação perdida após crash | inspeção/reenfileiramento manual | 0 ação; próximo ciclo converge |
| Descobrir worker morto | anúncio preso/estado implícito | lease 60 s + contador de recovery |
| Conferir se duas filas representam a mesma intenção | comparação manual impossível | `dispatch_ref` e dedupe por outbox |
| Evitar duplo caminho no agendamento | scheduler legado + novo indefinidos | v2 excluído do legado por grafo |
| Ativar caminho novo inadvertidamente | risco por simples deploy | flag segura off; force bloqueado em produção |
| Diagnosticar backlog | consulta ad hoc a rows | 1 log com counts e idade, zero PII |

Provas locais:

- 14 testes MKT-012 cobrem workers concorrentes sequenciais, batch, lease/reclaim/exhaustion, handoff/replay, crash antes/depois do commit, revalidação, reconciliação, mismatch, scheduler legado, flag/force e reverse/reapply da migration;
- Marketing command/outbox/API/campaign/handlers/capabilities/notifications/maintenance: 359 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0029_marketing_outbox_recovery`; nenhum provider, rede, produção ou escrita externa foi usado.
