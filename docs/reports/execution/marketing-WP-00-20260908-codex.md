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

## MKT-019 — `publish_mode=now|scheduled` ponta a ponta

Implementado:

- `AnnouncementCard` não emite mais uma edição ambígua: cada CTA carrega o enum literal `now` ou `scheduled` até o composable;
- board e detalhe usam o mesmo `buildApprovalCommand`, em vez de inferirem consequência em dois lugares pela presença de `publish_at`;
- o caminho `now` remove preventivamente qualquer timestamp residual mantido no painel de agendamento;
- o caminho `scheduled` exige um instante explícito antes de construir a request;
- base version, publish mode e consequência completa participam da fingerprint que conserva a idempotency key;
- API v2 continua fail-closed: `now` com timestamp responde `422 publish_now_has_schedule`, sem receipt/outbox parcial;
- um anúncio que já carregava horário sugerido não influencia o comando `now`: receipt registra `now`, `publish_at` fica nulo e a outbox nasce disponível imediatamente;
- copy pós-command continua honesta: “preparado para publicação” para `now`, “agendado” somente para `scheduled`.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir se “agora” respeitou horário sugerido | conferência externa/receio | 0; CTA é a autoridade |
| Limpar manualmente horário aberto no painel | risco de valor residual | 0; builder remove |
| Entender combinação inválida | comportamento inferido | erro específico antes de efeito |
| Repetir após resposta perdida | risco de trocar consequência/key | mesma fingerprint e receipt |

Provas locais:

- testes de componente provam que os CTAs emitem `now`/`scheduled` explicitamente;
- 3 testes unitários do command builder cobrem now com horário residual, scheduled com instante e scheduled sem instante;
- testes API provam que now vence horário sugerido e que now+timestamp falha sem outbox;
- Marketing Nuxt: lint, typecheck e 97 testes passaram;
- API/approval/outbox/transitions: 122 testes passaram; Ruff e `git diff --check` passaram;
- nenhuma migration; nenhum provider, rede, produção ou escrita externa foi usado.

## MKT-013 — DeliveryTarget/Attempt, uniques e identificadores protegidos

Implementado:

- `DeliveryTarget` representa um efeito lógico por snapshot/plataforma/recipient protegido; publicação pública recebe um único target sem membro;
- unique de banco em `(snapshot, platform, target_fingerprint)` fecha materialização duplicada por dois workers;
- fingerprint é HMAC-SHA-256 com chave e versão próprias, escopado por snapshot + plataforma; não é telefone, hash simples nem identidade estável entre campanhas;
- `SHOPMAN_MARKETING_TARGET_HMAC_KEY` não possui fallback em produção; ausência/valor fraco falha fechado antes de criar target;
- `fingerprint_key_version` é persistida para rotação; replay do mesmo outbox conserva targets já existentes em vez de recalcular histórico;
- target referencia somente `AudienceSnapshotMember` protegido e permite `SET_NULL` na janela de erase; não copia telefone, e-mail, nome, body ou conteúdo;
- retenções separam vínculo de identidade (90 dias após a base operacional) do registro técnico sem PII (5 anos); provider ref possui prazo próprio para MKT-014;
- `DeliveryAttempt` possui ordinal e idempotency hash únicos por target e somente outcome/error/receipt sanitizados; o lifecycle foi refinado no MKT-014;
- completion inválida é impedida por check constraint; target/version/key version têm checks positivos;
- materialização exige outbox já despachada, grafo versionado coerente e seleção explícita de membros WhatsApp;
- membro externo ao snapshot, recipient em duas waves e lote acima de 5.000 falham antes de qualquer target novo;
- o serviço usa apenas IDs internos/target keys já protegidas e nunca resolve contato nem chama adapter.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Descobrir recipient duplicado | reconciliação manual posterior | banco impede na criação |
| Relacionar telefone a tentativas para suporte comum | exposição desnecessária | fingerprint + ref opaca |
| Recuperar worker repetido | risco de recriar efeito | mesmo conjunto de target refs |
| Conferir wave sobreposta | só após resultado estranho | erro `delivery_wave_collision` imediato |
| Administrar rotação de segredo | rehash ambíguo | key version preservada por row |

Provas locais:

- 11 testes MKT-013 cobrem replay por dois workers, unique físico, escopo/rotação HMAC, falta de chave, target público, snapshot estranho, colisão de wave, hard cap, attempts, scanner de PII/conteúdo e reverse/reapply da migration;
- ledger + audience + command/outbox/API/campaign/handlers/capabilities/notifications/maintenance: 414 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0030_marketing_delivery_ledger`; nenhum adapter, provider, rede, produção ou escrita externa foi usado.

## MKT-014 — taxonomia de outcome e `unknown` sem retry cego

Implementado:

- a tentativa agora separa `prepared` de `calling`: antes do boundary é retomável; depois dele um segundo worker nunca chama o provider;
- a transação curta de início elege explicitamente um único dono da chamada; se outro worker vencer entre prepare/begin, o perdedor recebe `in_progress` sem efeito;
- o contrato do adapter aceita somente `not_attempted`, `accepted_unconfirmed`, `confirmed`, `failed_retryable`, `failed_final` ou `unknown`, com `retryable=true` restrito aos dois estados comprovadamente repetíveis;
- exceção após o boundary sem prova de que nada foi escrito vira `unknown`; mensagens, bodies, telefones e segredos do vendor são descartados, nunca persistidos;
- `effect_happened_response_lost` do fake adversarial termina em `unknown`, sem receipt inventado, e tanto replay da mesma tentativa quanto queue manual são incapazes de reenviar;
- falha comprovada antes da escrita e `429` preservam respectivamente `not_attempted`/`failed_retryable`, inclusive `Retry-After`, permitindo somente uma nova attempt no mesmo target;
- resposta aceita é registrada como `accepted_unconfirmed`, não como entrega confirmada; receipt passa por allowlist e retenção própria;
- artifact, plataforma, content version e request hash são conferidos sob lock antes de criar attempt, evitando ledger órfão e chamada com payload incompatível;
- o token raw não é persistido: digest estável e escopado preserva replay mesmo depois da rotação da chave usada nos fingerprints;
- `calling` abandonada converge pelo reconciler para `unknown/call_completion_lost`, sem invocar provider;
- a migration transforma conservadoramente qualquer `started` legado em `calling` — nunca assume que a chamada não ocorreu — e restaura `started` ao reverter;
- nenhum adapter real foi conectado e o consumer continua desligado; esta fatia prova somente o boundary persistido com fake hermético.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Decidir se timeout pode ser reenviado | investigar logs/provider | 0 decisões inseguras; estado `unknown` bloqueia retry |
| Recuperar crash antes da rede | recriar/reconferir intenção | mesma attempt é retomada, 0 chamadas anteriores |
| Recuperar crash após possível efeito | risco de duplicar ao tentar novamente | reconciler classifica `unknown`, 0 reenvio |
| Distinguir falha repetível de rejeição final | interpretar exception/texto do vendor | taxonomy + reason code + `Retry-After` no ledger |
| Conferir se outro worker já iniciou | coordenação manual impossível | ownership atômico; perdedor faz 0 chamadas |
| Conferir payload/version antes do envio | comparação posterior | bloqueio antes de criar attempt |
| Sanear erro/receipt para suporte | revisão manual | allowlists e descarte estrutural de detail bruto |

Provas locais:

- 14 testes MKT-014 cobrem accept/replay, reject, `429`, falha antes da escrita + retry seletivo, efeito com resposta perdida, rotação de chave, exception/redaction, resposta malformada, crashes nos dois lados do boundary, corrida entre workers, mismatch de artifact, contrato da taxonomy e reverse/reapply da migration;
- contracts + ledger + attempts: 34 testes passaram;
- regressão Marketing/campaign/audience/API/E2E: 456 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0031_marketing_attempt_outcomes`; nenhum adapter/provider real, rede, produção ou escrita externa foi usado.

## MKT-015 — fan-out limitado, backpressure e recheck pré-envio

Implementado:

- fan-out grava no outbox o hash protegido da seleção, total esperado, total materializado e instante de conclusão; retomar com outra seleção falha fechado;
- seleção inteira é validada contra o snapshot antes do primeiro target, impedindo que um ID estranho produza fan-out parcial;
- targets são criados em transações de chunks, com default local de 100 por chunk e no máximo 10 chunks por invocação; esses números são conservadores e não fecham o G-H08;
- progresso é derivado do próprio ledger: após kill entre chunks, repetir a mesma chamada descobre os já existentes e continua sem cursor, arquivo ou memória do operador;
- nenhum target é claimável enquanto a lane não tiver `fanout_materialized == fanout_expected` para o mesmo selection hash; kill não libera envio parcial prematuro;
- publicação pública materializa exatamente um target e replay é no-op; WhatsApp continua exigindo seleção interna explícita até o selector canônico do MKT-018;
- claims usam batch 100, lease 60 s, `skip_locked` quando suportado e limite máximo defensivo; workers concorrentes recebem lotes disjuntos;
- lease ativo cerca o boundary do MKT-014: outro worker não cria attempt nem chama provider; ao cruzar para `sending`, o lease é limpo atomicamente;
- lease stale é retomável; o token técnico deriva de target+ordinal e é reconstruído pelo novo worker para a mesma attempt `prepared`, enquanto `calling` jamais volta a chamar provider;
- imediatamente antes do claim, anúncio expirado vira `expired`, cancelado/recusado vira `cancelled`, e identidades inativas/revogadas/sem prova viram `suppressed` com reason code;
- recheck de consentimento é batched e passou a tratar opt-in `legacy_unverified` como `pending`; opt-out permanece autoritativo mesmo sem prova histórica completa;
- assinatura específica precisa continuar ativa e verificada; revogação posterior suprime antes de qualquer attempt;
- outage de consentimento não finge audiência zero nem consome target: mantém `queued`, sem lease, reason `consent_unavailable` e nova tentativa após 30 s;
- constraints de banco proíbem lease fora de `queued`, contagem materializada acima da esperada e fan-out “completo” sem hash/fechamento matemático;
- nenhum handler/adaptador real foi conectado e a flag do consumer permanece desligada; rate/capacidade finais continuam reservados ao G-H08/MKT-043.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Guardar cursor após kill de fan-out | necessário em implementação ingênua | 0; ledger deriva o próximo trabalho |
| Conferir se todos os recipients viraram targets | contagem externa | fechamento `expected/materialized` no outbox |
| Impedir envio parcial durante fan-out | coordenação manual | claim invisível até `fanout_completed_at` |
| Encontrar revogação entre aprovação e envio | inspeção de consentimento | 0; recheck batched pré-claim |
| Distinguir revogação de outage | ambos poderiam parecer zero | `suppressed/global_optout` vs `queued/consent_unavailable` |
| Coordenar workers | risco de colisão | lease de 60 s + lotes disjuntos + reclaim stale |
| Conferir prova de opt-in legado | consulta de histórico | `legacy_unverified` bloqueado automaticamente |

Provas locais:

- 17 testes MKT-015 cobrem chunks limitados sem cursor, kill/recovery, validação integral, conflito de seleção, target público, opt-out, consent legado, outage, subscription revoke, expiry, fencing, reclaim stale com reconstrução de token, backpressure, budget de queries, constraints e reverse/reapply;
- claim de 100 recipients: no máximo 10 queries, sem N+1;
- focused consent/snapshot/stock-alert/ledger/attempt/worker: 145 testes passaram;
- regressão Marketing/campaign/audience/API/E2E: 473 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0032_marketing_delivery_leases`; nenhum adapter/provider real, rede, produção ou escrita externa foi usado.

## MKT-016 — agregado honesto por plataforma e geral

Implementado:

- `Announcement.delivery_state` separa decisão editorial da verdade de execução: `not_started`, `fanout_pending`, `delivering`, `succeeded`, `completed_with_failures`, `unknown`, `cancelled`, `expired` ou `legacy_untracked`;
- execução nova encerrada usa o status neutro `settled`; nenhum agregado parcial, desconhecido ou apenas aceito recebe `published`;
- contagens por plataforma e gerais são uma query agregada sobre `DeliveryTarget`; `platform_results` legado não é lido, reescrito nem usado como oráculo;
- o resumo inclui todos os estados com zero explícito, total de targets, expected/materialized do fan-out, lanes completas e fechamento matemático verificável;
- `accepted` aparece como `accepted_unconfirmed`, separado de `confirmed`; nenhuma aceitação de provider é apresentada como entrega;
- `unknown` tem precedência mesmo quando outras lanes ainda estão ativas, evitando que incerteza acionável desapareça sob um progresso genérico;
- `failed_retryable` mantém o agregado aberto; success+final failure encerra como `completed_with_failures`; grupos integralmente cancelados e expirados permanecem distintos;
- plataforma concluída com sucesso e outra com falha produzem geral `completed_with_failures`, nunca sucesso total;
- fan-out incompleto domina como `fanout_pending`; lane vazia concluída sem target não é sucesso fabricado;
- histórico `published/failed` sem ledger migra para `legacy_untracked`, preservando o fato histórico sem inventar target, receipt ou confirmação;
- refresh é idempotente, troca `settled_at` quando um `unknown` é reconciliado e reabre o agregado se selective retry voltar a existir;
- mutações de fan-out, claim, queue e attempt agendam refresh robusto somente após commit; falha dessa projection não desfaz nem reclassifica o efeito persistido;
- guards legados tratam `settled`, `failed` e `cancelled` como estados não reaprováveis/rejeitáveis, fechando reenvio acidental pelo caminho antigo;
- constraints recusam delivery state terminal sem settled-at e valores inventados em target/outbox;
- a Projection/UI atual ainda não foi trocada: MKT-021 consumirá este contrato; o JSON legado permanece somente para compatibilidade read-only até o cutover.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Somar resultados de platforms/waves | N cards/JSON concorrente | 1 resumo geral matematicamente fechado |
| Descobrir se “aceito” significa entregue | interpretação externa | 0; accepted-unconfirmed e confirmed separados |
| Encontrar falha escondida por sucessos | inspeção por plataforma | geral `completed_with_failures` imediato |
| Encontrar efeito incerto | procurar logs/provider | `unknown` tem precedência e freshness própria |
| Conferir se fan-out terminou | comparar jobs/targets | expected/materialized/lanes complete no resumo |
| Interpretar histórico sem receipt | certeza falsa `published` | `legacy_untracked` explícito e idempotente |
| Esperar resumo de 100 targets | risco de N+1 | exatamente 3 queries |

Provas locais:

- 13 casos MKT-016 cobrem fan-out incompleto, accepted não confirmado, partial, unknown contra JSON otimista, retryable, duas plataformas, cancel/expire, legado/replay, callback pós-commit, 100 targets, constraints e reverse/reapply;
- aggregate + ledger + attempts + worker: 55 testes passaram;
- campanha + agregado + cadeia Marketing focada: 144 testes passaram;
- regressão Marketing/campaign/audience/API/E2E: 486 testes passaram;
- Ruff, `git diff --check` e migration drift passaram;
- migration reversível `shop.0033_marketing_delivery_aggregate`; nenhum adapter/provider real, rede, produção ou escrita externa foi usado.

## MKT-017 — retry seletivo, reconciliação lookup-only e Actions backend

Implementado:

- retry é um command CAS/idempotente próprio e seleciona sob lock somente `failed_retryable`; o operador escolhe no máximo plataformas, nunca recipients ou target refs;
- accepted, confirmed, unknown, falha final e estados ativos não são tocados pelo retry; a nova tentativa continua pertencendo ao mesmo `DeliveryTarget` e só nasce quando o worker claimar a fila;
- a seleção efetiva é registrada por contagem, plataformas e hash opaco no receipt/audit, sem membership, contato ou conteúdo;
- replay da mesma key devolve o mesmo receipt e não altera target/version/horário pela segunda vez; seleção sem falha segura produz receipt recusado `nothing_retryable`;
- `unknown` cria `DeliveryReconciliation` durável vinculada à attempt incerta; o endpoint não chama provider e o worker conhece apenas o protocolo `lookup`, que estruturalmente não expõe `send`;
- o lookup usa o token determinístico da attempt e pode concluir como accepted, confirmed, failed final, still unknown ou, quando o provedor prova ausência de efeito, failed retryable;
- resultados só avançam monotonicamente: target já resolvido nunca regride; `unknown` não vira retryable por timeout, exception ou suposição;
- outage/retorno malformado de lookup conserva target unknown, descarta erro bruto, reagenda após 30 s e permite que o worker continue;
- claims de reconciliação usam batch limitado, lease, `skip_locked` quando disponível e reclaim stale; replay de job concluído não consulta novamente;
- unique constraints impedem dois jobs ativos para o mesmo target e dois jobs do mesmo command/target; checks impedem lease e completion incoerentes;
- Actions backend resolve URL same-origin, método, capability, elegibilidade, disabled reason, necessidade de confirmação e se há efeito externo; o browser não precisa inventar autorização nem confundir lookup com resend;
- endpoints separados exigem `retry_failed_marketing` e `reconcile_unknown_marketing`; leitura das Actions exige somente `view_marketing` e mostra razões machine-safe;
- migration `shop.0034_marketing_delivery_recovery` é aditiva e reversível; nenhum reconciler/provider real foi ligado e nenhum envio foi habilitado.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Identificar manualmente quais falhas podem repetir | inspeção de logs/recipients | 0; backend conta e seleciona apenas retryable |
| Marcar recipients um a um | potencialmente N seleções | 0; escopo opcional por plataforma |
| Conferir se success/unknown entrou no retry | auditoria posterior | 0; filtro de estado + máquina + teste adversarial |
| Decidir se `unknown` deve reenviar | investigação perigosa | 0; única Action possível é lookup-only |
| Retomar reconciliação após crash | lembrar job/target | 0; intenção durável + lease stale |
| Descobrir permissão e próximo passo | tentativa/erro ou lógica no browser | 1 fetch de Actions com enabled/reason/count |
| Repetir clique após resposta perdida | receio de duplicação | mesmo receipt, 0 segunda mutação/lookup |
| Sanear erro do vendor | conferência manual | detalhe bruto é descartado estruturalmente |

Provas locais:

- 13 casos MKT-017 cobrem retry seletivo/replay/rejeição, criação lookup-only, cinco outcomes monotônicos, outage/redaction, reclaim de lease, Actions/capabilities, API e reverse/reapply da migration;
- cadeia command/approval/transitions/outbox/ledger/attempt/worker/aggregate/recovery/API/RBAC: 210 testes passaram;
- regressão Marketing/campaign/audience/notifications/maintenance/E2E: 567 testes passaram;
- Ruff, `git diff --check`, Django check e migration drift passaram (mantido apenas o warning conhecido de SQLite e bootstrap sem schema no check local);
- nenhuma chamada real, destinatário, rede, deploy, produção ou escrita externa foi usada.

## MKT-018 — selector canônico e estável para preferred-hour

Implementado:

- o plano de waves aprovado passa a ser a autoridade da partição; o selector não recalcula se a hora ainda está no futuro quando a lane finalmente executa;
- `all@H`, `vip@H` e `general@H` selecionam por hora preferida e grupo; membro cuja hora não possui lane aprovada cai na base correspondente em vez de desaparecer;
- o grafo aceita exclusivamente `all` ou o par completo `vip`/`general`, sempre com lane-base para cada subdivisão horária; mistura, chave inválida, lane ausente ou snapshot divergente falha fechado;
- cada membro do snapshot pertence exatamente a uma lane; os testes fecham união e disjunção e a unique constraint continua cercando qualquer sobreposição;
- fan-out WhatsApp sem seleção manual usa o selector canônico sobre `AudienceSnapshotMember`, sem resolver telefone e sem adicionar opt-in tardio ao cohort aprovado;
- a seleção explícita interna continua disponível para testes/recovery, mas a operação comum não exige que worker ou operador transporte IDs/cursor;
- directives novas — tanto no caminho legado quanto na outbox v2 — carregam `wave_keys` e `waves_expected`; o handler usa esse plano completo para manter a partição estável;
- o reconciler de outbox também compara `wave`, plano completo e total esperado antes de religar uma directive preexistente, impedindo dedupe com payload de outra partição;
- directives legadas sem plano preservam o comportamento compatível para lanes-base; chave desconhecida nova não vira envio silencioso de zero pessoas;
- nenhuma migration foi necessária: a chave já persistida passou a ser interpretada por um contrato único, PII-free e testável.

Budget de omotenashi comprovado:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir se a wave horária enviou zero | inspeção posterior | 0; chave aprovada seleciona deterministicamente |
| Guardar/repassar IDs de membros por worker | até N IDs/cursor | 0; selector deriva do snapshot + lanes |
| Descobrir duplicação entre base e `@H` | reconciliação posterior | 0; partições disjuntas + unique física |
| Recalcular mentalmente VIP × hora | combinação implícita | regra única: grupo, depois hora se lane existe |
| Lidar com hora sem lane | recipient podia sumir | fallback automático para base |
| Diagnosticar plano corrompido | zero silencioso | erro técnico antes de qualquer target/send |
| Conferir opt-ins posteriores | risco de expansão | impossível; selector consulta só o snapshot selado |

Provas locais:

- 7 testes MKT-018 cobrem `all@9`, `vip@9`/`general@9`, fallback à base, fechamento/disjunção, grafo inválido, handler no instante H e propagação do plano em directives;
- audience + handlers + worker + outbox + approval: 111 testes passaram;
- regressão Marketing/campaign/audience/notifications/maintenance/E2E: 574 testes passaram;
- Ruff e `git diff --check` passaram; não há mudança de model/migration;
- nenhum provider real, destinatário externo, rede, deploy, produção ou escrita externa foi usado.

## MKT-020 — autorização transacional, quotas e emergency freeze

Implementado conforme o G-H04 aprovado:

- todo command com efeito calcula no servidor o contexto exato — actor, action, resource, base version, artifact/cohort hash, contagem, plataformas, horário e consequência — antes de emitir confirmação;
- o bearer de confirmação é aleatório, one-use, expira em 5 minutos e somente seu HMAC é persistido; qualquer alteração de contexto, versão, pessoa, sessão, senha, capability ou geração de segurança o invalida;
- `publish now` e retry seguro exigem recent-auth por senha e a frase exata `PUBLICAR <count>`; a partir de 500 destinos exigem TOTP e segundo ator distinto; 2.000–5.000 só agenda com ao menos 15 minutos; acima de 5.000 falha fechado;
- o segundo controle guarda também fingerprint de senha/permissões e é revalidado no submit final; a mesma pessoa nunca satisfaz os dois papéis;
- step-up dura 15 minutos, fica na sessão e é ligado ao auth hash, permission fingerprint e geração do freeze; logout/troca de usuário, senha, RBAC ou risk/freeze tornam a evidência inútil;
- mudanças de permissions/grupos incrementam uma geração persistida após commit; o command ainda consulta usuário ativo e capabilities novamente dentro da mesma transação que consumirá token e produzirá efeito;
- publish, cancel, reschedule, retry e reconcile receberam o mesmo callback de autorização junto ao boundary transacional; challenge não deixa receipt/outbox parcial e replay idempotente não cria segundo efeito;
- reject/cancel exigem motivo de até 200 caracteres; a auditoria preserva o motivo e cancel declara separadamente lanes evitadas e targets já irreversíveis;
- quotas de API seguem 30/min user + 120/min shop para audience, 10/min user + 30/min shop para commands e 3/h user + 10/dia shop para fire; a reserva durável limita 5.000 targets externos/dia e `429` sempre traz `Retry-After`;
- send-test permanece isolado, allowlisted, max-1 e com suas quotas 5/h por user e 20/dia por shop; o freeze é rechecado imediatamente antes do adapter e deixa receipt `denied`, sem chamada;
- emergency freeze é um estado persistido com reason, actor, CAS version e audit; ativá-lo é uma ação imediata de um Security/Ops e invalida todas as confirmações/step-ups abertas;
- na ativação, outboxes/targets/directives que ainda não cruzaram boundary são terminalmente cancelados/suprimidos; `accepted`, `unknown` e calls possivelmente iniciadas são preservados, nunca reenviados;
- workers consultam o freeze antes de claim/handoff e novamente no último limite antes da chamada externa; uma attempt preparada que encontra freeze volta a estado recuperável sem tocar o provider;
- desativar exige TOTP, segundo Security/Ops distinto, versão CAS correta e zero `calling`, `unknown` ou reconciliação pendente; trabalho reversível criado durante a janela também é suprimido antes da retomada;
- writes legados de platform config e fire manual, que ainda não possuem CAS/snapshot/receipt completos, retornam `409` deny-safe e zero mutação até MKT-029 e o command canônico correspondente;
- eventos de segurança, confirmações consumidas e reservas de quota são protegidos contra update/delete arbitrário e retidos sem body, telefone, username, token raw ou resposta de fornecedor;
- o sweep amplo também removeu imports diretos de Storefront do core por adapters e eliminou catches silenciosos nas etapas Marketing anteriores, restaurando os gates arquiteturais globais.

Budget de omotenashi comprovado no contrato backend:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Montar blast/plataforma/horário para confirmar | conferências externas e memória | 0; challenge devolve o resumo autoritativo no contexto |
| Repetir campos do command após step-up | payload inteiro | somente token e, quando exigida, 1 frase pronta para copiar |
| Descobrir qual step-up/segundo ator é necessário | tentativa e erro | `mode`, `step_up`, `dual_control` e frase resolvidos pelo servidor |
| Conferir validade da ação já aberta | risco silencioso após revogação | submit revalida tudo; 0 efeitos com capability removida |
| Coordenar double click/resposta perdida | investigação de receipt | mesma key devolve o mesmo receipt; token não produz segundo efeito |
| Congelar canais em incidente | deploy/worker a worker | 1 POST + motivo; estado global e contagens auditadas |
| Separar evitado de irreversível | inspeção de fila/provider | contagens explícitas no cancel/freeze; accepted/unknown preservados |
| Calcular limites e espera | regra mental | bloqueio server-side + `Retry-After` |
| Reabrir após incidente | checklist fora do produto | CAS + reconciliação + TOTP + segundo ator obrigatórios |

Provas locais:

- 13 testes MKT-020 cobrem challenge sem efeito parcial, password/TOTP, typed phrase, replay, expiração/context binding, revogação após load, quota/`Retry-After`, segundo ator e sua rotação de senha, thresholds, freeze seletivo, unfreeze dual e reverse/reapply da migration;
- testes de boundary provam freeze depois de `begin_call` e antes de `provider.send`, além do send-test sem chamada;
- cadeia focada de segurança/recovery/attempt/transitions/test-send/API/RBAC: 140 testes passaram;
- regressão ampliada Marketing/campaign/notification e gates arquiteturais: 2.709 testes passaram, 16 ignorados, 26 deselecionados e 10 subtests; somente 3 warnings esperados de override de `DATABASES` nos testes de deploy;
- Ruff de todos os Python tocados, `git diff --check`, Django check e migration drift passaram; o check preserva apenas o warning conhecido de SQLite e os logs de bootstrap sem schema no banco efêmero;
- migration única, aditiva e reversível `shop.0035_marketing_security_authorization`; nenhum provider, destinatário, credencial, sandbox, rede, deploy, produção ou escrita externa foi usado.

## MKT-021 — Marketing Projection v2 pura e versionada

Implementado de forma aditiva e sem trocar o consumidor atual:

- o envelope canônico `marketing.v2` expõe timezone da loja, instante da leitura, resource version, freshness, dados e o slot de `actions`; a resolução das Actions permanece vazia e explicitamente reservada para MKT-022;
- board e detalhe usam o mesmo read model imutável de fatos, refs técnicas, enums, contagens, hashes, timestamps e versões;
- foram removidos do contrato v2 labels, frases de apresentação, nomes de ator, motivo livre de recusa, conteúdo mutável, resultado JSON legado, erro bruto de provider e qualquer membership/target/contact;
- trigger context é allowlisted: somente a ref técnica do SKU pode sair; JSON arbitrário, nome, telefone e e-mail não atravessam a Projection;
- metadados antigos de audiência são saneados: policy/ref/hash seguem formatos técnicos, reason desconhecido vira somente a contagem `unclassified` e nunca carrega a chave potencialmente sensível;
- audience freshness distingue `fresh`, `stale`, `degraded` e `unavailable`; histórico sem ledger fica `delivery_ledger` indisponível, sem inventar receipt ou sucesso;
- readiness existe como verdade `unknown` até MKT-029 conectar provas atuais do canal; a Projection não infere disponibilidade pela ausência de erro;
- estado efetivo expirado é derivado pelo relógio sem escrita no caminho de leitura e sem permitir que card vencido continue parecendo revisável;
- métricas de “publicado/alcançado” saíram do v2; o painel conta somente targets `accepted` não confirmados, `confirmed`, `failed_final` e `unknown` diretamente do ledger, com janela diária no timezone da loja;
- o aggregate do ledger ganhou leitura bulk: qualquer quantidade de anúncios custa duas queries de ledger, eliminando N+1 por card;
- o board não tem o corte silencioso de 50 itens; todos os pendentes válidos e todos os resultados da janela de 24 horas são projetados, deixando cursor/history para MKT-024;
- a versão do board é content-addressed e ignora apenas campos que avançam com o relógio, portanto não muda a cada segundo sem mudança operacional; no detalhe, `resource_version` continua sendo o CAS version do anúncio;
- `/api/v1/backstage/marketing/v2/` e `/api/v1/backstage/marketing/v2/announcements/<id>/` usam a capability de leitura existente; `/marketing/` v1 permanece intacto durante a janela de compatibilidade;
- o JSON Schema estrito e versionado foi cristalizado em `contracts/projections/marketing_v2.schema.json`; propriedades extras falham no contrato e timestamps possuem formato `date-time`.

Budget de omotenashi comprovado no read path:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Traduzir status em certeza de entrega | inferência por labels/JSON legado | estados e contagens fechadas do ledger |
| Distinguir aceito de confirmado | “alcançado” somava audiência estimada | counters separados e nenhum `reached` |
| Conferir histórico para achar falha parcial | card/resultados divergentes | agregado geral + por plataforma no mesmo fetch |
| Descobrir se zero é real ou outage | ausência ambígua | freshness + source code allowlisted |
| Abrir logs/provider para validar legado | necessário para certeza | `legacy_untracked`/`unavailable` explícito |
| Esperar painel crescer com N anúncios | N+1 de agregado | 6 queries totais para board; 2 são ledger bulk |
| Perder pendente por corte oculto | limite silencioso de 50 | 75 itens cobertos sem corte; implementação sem limite |
| Revalidar contrato BE↔FE manualmente | espelho informal | schema golden executável e drift falha teste |

Provas locais:

- 8 testes MKT-021 cobrem schema golden, ausência de copy/PII/membership, saneamento de JSON legado, métricas honestas, orçamento constante, ausência de corte, resource version estável, expiração read-only e endpoints compatíveis;
- projection + aggregate: 21 testes passaram;
- regressão Marketing/campaign/audience/API/E2E: 513 testes passaram em 69,42 s;
- board com 75 pendentes executou exatamente 6 queries, independentemente da cardinalidade;
- Ruff, `git diff --check`, JSON parse, Django check e migration drift passaram; permaneceram apenas o warning conhecido de SQLite e logs defensivos de bootstrap sem schema no check local;
- nenhuma migration, provider, destinatário, rede, deploy, produção ou escrita externa foi usada.
