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

## MKT-022 — Action resolver único e autoritativo

Implementado de forma aditiva sobre a Projection v2:

- `marketing_actions.py` passou a ser a única autoridade backend para Actions de anúncio, recuperação, regra, plataforma, notificação pessoal e alerta operacional; o resolver paralelo de recovery foi removido;
- toda Action tem ref ligada ao recurso/versão, kind, chave de presentation, prioridade, estado habilitado, reason code, href same-origin, método, payload schema, idempotência, confirmação, contagem elegível, capabilities exigidas e indicação de efeito externo;
- board e detail v2 recebem as mesmas Actions; os endpoints existentes de rules, platforms, notifications, operator alerts e delivery recovery passaram a expor o mesmo shape, preservando seus contratos v1 durante a migração;
- autorização é lida de um `User` fresco a cada resolução, portanto capability removida depois do primeiro carregamento desabilita a Action sem depender de cache do objeto da sessão; o POST continua reautorizando dentro da transação;
- permission, freeze, estado, audiência, expiry, readiness, elegibilidade de retry e reconciliação ativa são resolvidos no servidor; o browser não precisa converter status em autoridade;
- confirmação de publish/schedule/retry/reconcile/cancel/reschedule é derivada diretamente da policy transacional de MKT-020, inclusive password/TOTP, typed/summary e dual control, sem uma segunda tabela de thresholds;
- audiência zero, expirada, stale/degraded/unavailable, plataforma ausente e readiness diferente de `ready` falham fechadas com reason code explícito;
- retry aparece somente para `failed_retryable`; unknown oferece apenas lookup de reconciliação quando existe attempt ambígua e fica `reconciliation_pending` quando já há trabalho ativo;
- notificações ignoram `action_url`, `action` e `href` persistidos ao construir Actions; somente o owner recebe navegação canônica e mark-read, sem approve implícito no novo contrato;
- rules e platform writes ainda sem command/CAS completo permanecem visíveis porém `command_not_available`, evitando prometer uma mutação que o backend bloqueia;
- o emergency freeze bloqueia Actions que criam ou retomam efeitos, mas mantém reconciliação lookup-only disponível. Foi corrigido o deadlock em que o primeiro gate aceitava reconcile congelado e a emissão do challenge o recusava;
- resolução bulk busca autoridade, freeze e fatos de recovery em número constante de queries; não há consulta por card, alerta ou notificação.

Budget de omotenashi comprovado no resolver:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Traduzir status/readiness em botão possível | lógica duplicada por tela | 0; `enabled` + `reason` vêm do backend |
| Descobrir permissão faltante após tentativa | 1 POST recusado | 0 tentativas; Action já mostra `missing_capability` |
| Reabrir tela após revogação de papel | estado possivelmente cacheado | próxima Projection reavalia o usuário persistido |
| Calcular confirmação/2FA/segundo ator | consulta externa ou tentativa | 0; metadados vêm da mesma policy do command |
| Encontrar reparo de delivery parcial | navegar histórico/log | retry/reconcile contextuais no mesmo recurso |
| Distinguir retry de lookup unknown | risco de resend | dois kinds explícitos; reconcile declara zero efeito externo |
| Confiar em deep-link salvo na notificação | risco de URL/payload arbitrário | 0; resolver só emite rotas constantes same-origin |
| Carregar 75 cards | risco de N+1 | no máximo 5 queries adicionais para todas as Actions |
| Descongelar com unknown aberto | fluxo antes impossível | challenge TOTP de lookup continua disponível sem send |

Provas locais:

- 7 testes MKT-022 cobrem recovery/permission, readiness/audiência zero, revogação após load, freeze, challenge lookup-only, rules, platforms, alert, notification hostile input, endpoint v2 e orçamento de queries;
- testes focados de Actions, Projection, Security, recovery, alert e notification: 67 passaram;
- regressão ampliada Marketing/campaign/audience/notifications/alerts/E2E: 586 testes passaram em 74,05 s;
- board com 75 pendentes gerou 375 Actions com no máximo 5 queries adicionais, independentemente da cardinalidade;
- JSON Schema golden agora tipa Actions estritamente; Ruff, `git diff --check`, Django check e migration drift passaram, preservando somente o warning/log conhecido do SQLite sem schema;
- nenhuma migration, chamada de provider, destinatário, rede, deploy, produção ou escrita externa foi usada.

## MKT-023 — OpenAPI para cliente TypeScript e CI sem drift

Implementado sem cortar o consumidor v1:

- a Projection Python continua sendo a fonte de verdade; dela é montado um OpenAPI 3.1 estreito e determinístico com os dois reads v2, autenticação por session cookie e todos os schemas estritos em `components.schemas`;
- `contracts/openapi/marketing_v2.openapi.json` é o artefato OpenAPI versionado; nenhuma `$ref` privada de JSON Schema vaza para o documento;
- `marketingClient.ts` é gerado integralmente do OpenAPI: interfaces, unions literais de enum, aliases de Action/freshness, paths e um cliente GET com transporte injetável;
- o cliente força `credentials: same-origin`, usa somente paths do contrato e rejeita ID inválido antes de tocar rede;
- `app/types/campaign.ts` reexporta os tipos v2 gerados e mantém os tipos v1 apenas como adapter temporário; novos tipos v2 não têm espelho manual;
- `python manage.py export_marketing_client` regenera OpenAPI e cliente juntos; `--check` é read-only, aponta exatamente o artefato stale e retorna não-zero;
- o Runtime Gate do CI executa `export_marketing_client --check` em todo PR/merge group; além disso, a suíte Backstage compara geração in-memory e geração em diretório temporário byte a byte com os arquivos commitados;
- o teste Vitest usa o cliente real gerado, confirma os dois paths/opções e prova que Action kind permanece union fechada em vez de `string` manual;
- o cutover dos composables/telas permanece deliberadamente para MKT-032/MKT-035, depois dos contratos MKT-024–029; v1 não foi removido nem alterado silenciosamente.

Budget de omotenashi comprovado para desenvolvimento/operação do contrato:

| Trabalho/risco | Antes | Depois |
|---|---:|---:|
| Redigitar shape Python em TypeScript | dezenas de campos por mudança | 0; um comando gera tudo |
| Lembrar de regenerar antes do merge | memória do autor | 0; CI falha com comando de reparo |
| Descobrir qual arquivo divergiu | comparação manual | mensagem lista OpenAPI e/ou cliente stale |
| Conferir enum de Action no frontend | mapa manual sujeito a widening | union literal gerada e typecheckada |
| Montar path do detail em cada caller | interpolação repetida | método `getMarketingAnnouncement(id)` |
| Fazer request inválido para ID zero/fracionário | 1 round-trip + erro | 0 requests; validação local imediata |
| Lembrar credencial same-origin | opção por chamada | default imutável do cliente |
| Validar geração em outra árvore | diff manual | temp generation byte-identical automatizada |

Provas locais:

- 3 testes Django MKT-023 cobrem drift duplo, geração temporária e integridade das operações/refs/schemas;
- cadeia focada de contrato/Projection/Actions: 18 testes passaram;
- Marketing Nuxt: 7 arquivos/100 testes Vitest, ESLint e Nuxt typecheck passaram;
- `export_marketing_client --check`, parse JSON, Ruff e `git diff --check` passaram;
- gate canônico Unfold foi atualizado no registro oficial de surfaces, sem waiver: `make admin` passou com 229 testes;
- a regressão completa de Backstage passou com 2.313 testes, 22 skips e 24 subtests em 226,61 s; ela também eliminou os broad catches residuais dos commands, que agora só capturam erros contratuais conhecidos;
- nenhuma dependency, migration, chamada de rede/provider, deploy, produção ou escrita externa foi adicionada/executada.

## MKT-024 — erro, ETag, cursor e metadados API/BFF

Implementado de forma aditiva no namespace v2:

- todo read v2 responde com `X-Request-ID`, `X-Contract-Version`, `X-Resource-Version`, `X-API-Version`, `Cache-Control` privado, `Vary: Cookie` e ETag fraco calculado apenas sobre a semântica projetada, sem PII ou membership;
- `If-None-Match` retorna `304` vazio e conserva ETag/correlação/versões; relógios voláteis não invalidam cache, enquanto versão, ledger, freshness ou Actions alteradas mudam o ETag;
- request id válido do browser é preservado ponta a ponta; valor hostil/inválido nunca é refletido e recebe `req_<uuid>` seguro gerado no Django;
- o envelope de erro v2 é estrito, presentation-keyed e inclui `code`, `retryable`, `field_errors`, request id, versão corrente opcional e Actions; nenhuma exception/copy operacional atravessa a boundary;
- a base v2 intercepta a coerção do DRF/SessionAuthentication e mantém `401` anônimo diferente de `403` autenticado sem capability; `404`, `409`, `422`, `429` com `Retry-After` e `503` têm mapeamentos distintos e cobertos;
- `/marketing/v2/history/` usa snapshot `as_of`, ordem total `created_at DESC, pk DESC`, cursor opaco assinado e limite explícito 1–100; cursor adulterado ou limite fora do budget falha em `422`, em vez de truncar silenciosamente;
- a página de histórico projeta evidência/audience/ledger em bulk e reutiliza o mesmo resolver de Actions; inserções posteriores ao primeiro fetch não entram no snapshot nem deslocam itens;
- o OpenAPI agora documenta conditional request, headers, 304, erros e history; o cliente gerado aceita ETag/request id, monta cursor/limit e recusa page size impossível antes da rede;
- o export canônico passou a regenerar também o JSON Schema da Projection, eliminando o passo manual residual entre schema, OpenAPI e TypeScript;
- o BFF compartilhado encaminha somente `If-None-Match`/request id para o Django e devolve por allowlist cache, retry, ETag, request/contract/resource/API version e famílias RateLimit; um teste com evento H3 e upstream reais simulados comprova que status e `304` continuam intactos e header interno não atravessa.

Budget de omotenashi comprovado no transporte:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Baixar novamente um card sem mudança | payload completo | `304`, zero JSON |
| Citar uma falha ao suporte | procurar logs/horário | request id visível na resposta e no erro |
| Distinguir login vencido de acesso negado | mensagem/estado ambíguo | `401` e `403` semanticamente separados |
| Decidir se deve repetir | inferência por texto/status | `retryable` + `Retry-After` estruturados |
| Navegar histórico durante novas publicações | risco de repetição/salto | snapshot `as_of` + tie-breaker por id |
| Descobrir truncamento de histórico | impossível; cap silencioso | limite declarado e excesso rejeitado |
| Lembrar headers de revalidação por chamada | repetição manual | cliente gerado + BFF allowlist canônicos |
| Regenerar três artefatos de contrato | dois comandos/passos | um export para schema/OpenAPI/TS |

Provas locais:

- 8 casos MKT-024 cobrem metadados, ETag/304, mudança de versão, cursor com timestamps idênticos, inserção concorrente, cursor adulterado, cap explícito e todos os status prometidos;
- cadeia focada Projection/Actions/cliente/HTTP: 26 testes passaram;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 491 testes passaram em 68,95 s;
- Marketing Nuxt: 7 arquivos/101 testes, ESLint e Nuxt typecheck passaram; operator-kit: 17 arquivos/174 testes passaram;
- Ruff, `export_marketing_client --check` e `git diff --check` passaram; o check preservou somente o warning conhecido de SQLite e logs defensivos de bootstrap sem schema;
- nenhuma migration, provider, destinatário, deploy, produção ou escrita externa foi usada.

## MKT-025 — ResolvedDispatchArtifact único

Implementado sobre o ledger/outbox já existente, sem provider real:

- `marketing_artifacts.py` é o único resolver puro de conteúdo por plataforma; recebe conteúdo base, overrides aprovados, plataforma, versão e hash factual, e devolve o `ResolvedDispatchArtifact` frozen usado pelo contrato de provider;
- novas aprovações persistem schema de artefato v2 com um payload já resolvido por plataforma, além das fontes aprovadas; o conteúdo que cruza o boundary externo não é renderizado novamente no worker e não depende de template/model mutável;
- approvals schema v1 continuam legíveis pela janela de compatibilidade, mas passam pelo mesmo resolver ao serem entregues; versão de model, versão interna e plataforma precisam coincidir;
- o loader recalcula e compara o hash do `MarketingContentArtifact` antes de abrir qualquer payload; alteração de bytes, platform fora da aprovação, schema/version divergente ou shape inválido falham fechados;
- `execute_approved_target` remove do chamador a montagem e o request hash: lê o artefato selado, resolve a plataforma e entrega ambos ao executor idempotente;
- o executor de baixo nível também compara o hash recebido com o hash resolvido da evidência aprovada. Assim, nem um caller legado consegue enviar um `ResolvedDispatchArtifact` apenas “parecido” ou reconstruído por lógica paralela;
- `campaign.preview` agora materializa o mesmo tipo imutável e devolve payload/hash junto do contrato compatível; plataforma e content version inválidas falham como `422` na API;
- o frontend tipa o artefato/hash retornado sem inferir seu conteúdo nem manter um segundo algoritmo.

Budget de omotenashi comprovado no caminho preview→dispatch:

| Trabalho/risco | Antes | Depois |
|---|---:|---:|
| Conferir preview contra payload do worker | comparação manual de campos | 1 igualdade de hash |
| Remontar conteúdo no worker | corpo + hashtags + link + imagem | 0; loader abre evidência selada |
| Lembrar de calcular request hash | obrigação por caller | 0 no entrypoint canônico |
| Descobrir drift de template após aprovação | só após envio | impossível; bytes resolvidos são imutáveis |
| Validar plataforma/versão/hash separadamente | até 3 conferências | uma chamada fail-closed |
| Investigar payload “quase igual” | logs/provider | bloqueado antes de criar attempt |

Provas locais:

- 3 testes MKT-025 cobrem determinismo/imutabilidade/ausência de recipient, igualdade exata preview→approval→provider→attempt e adulteração fail-closed;
- cadeia focada artifact/approval/outbox/worker/attempt/campaign/API: 205 testes passaram;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 494 testes passaram em 70,84 s;
- Marketing Nuxt: 7 arquivos/101 testes, ESLint e Nuxt typecheck passaram;
- Ruff e `git diff --check` passaram; nenhuma migration, rede, provider real, destinatário, deploy, produção ou escrita externa foi usada.

## MKT-026 — variantes preservadas e render estrito

Implementado sobre o artefato imutável do MKT-025:

- a variante agora preserva todos os campos que declara; corpo, hashtags, link e imagem comuns são herdados somente quando o campo correspondente está ausente;
- criação, edição e aprovação filtram variantes pelas plataformas realmente selecionadas e renderizam cada string no seu campo de origem, sem reprojetar o corpo comum sobre uma decisão editorial específica do canal;
- variável desconhecida ou placeholder malformado falha antes da aprovação com `code` estável e `field_errors` apontando exatamente `body` ou o caminho aninhado da variante;
- o `ResolvedDispatchArtifact` mantém `provider_fields` escalares, ordenados e imutáveis; conteúdo não pode escolher flow, token, credencial ou segredo;
- hashtags deixam de aceitar coerção silenciosa de objetos/números para texto e artefatos persistidos antes do campo aditivo continuam legíveis;
- o contrato golden versionado prova Instagram com body/hashtags próprios, Google Business herdando somente ausências e WhatsApp com template técnico permitido;
- a API de edição devolve `422` estruturado sem avançar a versão nem perder o draft quando encontra variável inválida;
- a prévia tipa os metadados técnicos devolvidos pelo mesmo artefato que será aprovado e entregue.

Budget de omotenashi comprovado no fluxo de conteúdo:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir se uma variante foi substituída pelo corpo comum | comparação manual por canal | 0; golden + resolver preservam o override |
| Descobrir variável digitada errada | após envio/aparelho externo | antes da aprovação, no campo exato |
| Repetir corpo comum em cada plataforma | até uma cópia por canal | 0; herança apenas de campos ausentes |
| Conferir flow/credencial escolhida por conteúdo | revisão de payload/log | impossível; boundary recusa o campo |
| Investigar alteração parcial após erro de edição | reabrir e comparar draft | 0; transação conserva conteúdo e versão |
| Validar três payloads manualmente | três inspeções | uma comparação contra golden versionado |

Provas locais:

- 166 testes focados de campaign/artifact/approval/API passaram;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 569 testes passaram em 74,26 s;
- Marketing Nuxt: 7 arquivos/101 testes, ESLint e Nuxt typecheck passaram;
- gate canônico Unfold: 229 testes passaram;
- Ruff, `git diff --check`, Django check e migration drift passaram; permaneceram somente o warning conhecido de SQLite e logs defensivos de bootstrap sem schema;
- nenhuma migration, chamada de rede/provider, destinatário, deploy, produção ou escrita externa foi usada.

## MKT-027 — fatos canônicos, validade e as-of

Implementado sob a política provisória de Produto aprovada no G-H05, mantendo a
discovery obrigatória de 5–8 gestores para o MKT-047:

- `marketing_facts.py` lê os donos canônicos de catálogo, cotação Offerman,
  disponibilidade, promoção e links da storefront; preço e estoque recebidos no evento
  deixam de ser aceitos como verdade editorial;
- o snapshot factual contém somente os fatos efetivamente referenciados, `as_of`, janela
  de frescor de até cinco minutos e hash determinístico da origem; o payload não contém
  cliente, audiência, telefone ou segredo;
- a prévia e a aprovação compartilham o mesmo snapshot e o mesmo hash; aprovação revalida
  as fontes sem trocar silenciosamente os bytes que o operador revisou;
- promoção inexistente, inativa, fora do canal web, dependente de cupom/segmento privado,
  incompatível com o SKU ou vencida no instante agendado bloqueia antes do outbox;
- o worker revalida o snapshot uma vez por artefato antes do claim e o entrypoint canônico
  repete a guarda imediatamente antes do adapter; drift terminal expira o target sem
  cruzar o boundary do provider, enquanto indisponibilidade transitória apenas adia;
- a Projection v2 expõe somente refs seguras, `as_of`, `fresh_until`, nomes das variáveis
  e hash; valores de conteúdo continuam fora da projection;
- um override escrito pelo operador que introduz um placeholder factual novo também é
  resolvido pelo dono canônico, em vez de herdar valor antigo do evento;
- aprovações anteriores ao MKT-027 permanecem legíveis durante a janela de compatibilidade,
  mas qualquer anúncio novo com promoção precisa ter prévia factual verificável.

Budget de omotenashi comprovado no fluxo de facts:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir preço, estoque, oferta e link fora do cockpit | até 4 consultas | 0 |
| Memorizar quando os dados foram consultados | implícito | `as_of` e frescor estruturados |
| Comparar prévia com a aprovação | campos manualmente | uma igualdade de hash |
| Descobrir que a promoção vence antes do schedule | após agendar/enviar | erro imediato em `publish_at` |
| Recuperar-se de fato alterado durante a revisão | reabrir e reconstruir | draft e versão permanecem intactos |
| Evitar mensagem factual já obsoleta | conferência humana de última hora | duas guardas pré-provider, zero chamada externa |

Provas locais:

- 220 testes focados de facts/artifact/approval/worker/campaign/Projection/API passaram;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 570 testes passaram
  em 70,52 s, incluindo o caso legado sem placeholder factual;
- 7 casos específicos cobrem preço/estoque/link canônicos, override factual, validade da
  promoção, drift na aprovação, drift pré-send e adulteração do snapshot;
- Marketing Nuxt: 7 arquivos/101 testes, ESLint e Nuxt typecheck passaram;
- gate canônico Unfold: 229 testes passaram;
- Ruff, export de contratos `--check`, Django check, migration drift e `git diff --check`
  passaram; permaneceram somente o warning conhecido de SQLite e logs defensivos de
  bootstrap sem schema;
- nenhuma migration, rede, provider real, destinatário, deploy, produção ou escrita
  externa foi usada.

## MKT-028 — preview cancelável, ordenado e fiel por plataforma

Implementado sobre o artifact e snapshot factual dos MKT-025–027:

- a API aceita todas as plataformas e variantes em uma única chamada; todos os artifacts
  usam exatamente o mesmo snapshot factual, `as_of` e hash de origem;
- o endpoint singular anterior permanece compatível, agora como uma projeção do mesmo
  resolvedor batch, sem um segundo algoritmo;
- `AnnouncementTemplateProjection` preserva `platform_variants` para a prévia; o Nuxt não
  tenta reconstruir overrides que só o backend conhece;
- a UI cancela imediatamente a requisição anterior quando texto, oferta, plataformas ou
  variantes mudam e incrementa um epoch; mesmo que o transporte ignore o abort e entregue
  a resposta antiga, ela não pode alterar estado, loading ou erro atuais;
- enquanto a nova versão está pendente, a anterior sai da tela e um status vivo explica
  que todas as plataformas estão sendo atualizadas;
- abas com área mínima de toque de 44 px exibem o artifact exato de cada canal, incluindo
  body, hashtags, link, imagem e campos técnicos já selados pelo servidor;
- a tela identifica explicitamente produto/SKU de amostra, horário dos fatos e prefixo do
  artifact hash; a troca de canal é local e não cria nova espera;
- erro estruturado e `field_errors` permanecem no contexto, com uma Action de revalidação;
  falha não volta a parecer uma prévia vazia;
- avisos de campo vazio são restritos aos placeholders realmente usados, eliminando o
  falso alerta de disponibilidade visto na primeira inspeção visual.

Budget de omotenashi comprovado no fluxo de prévia:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir duas plataformas escolhidas | uma simulação genérica e inferência manual | uma chamada batch + abas fiéis |
| Trocar de Instagram para WhatsApp | sem variante verificável | 1 toque local, 0 request, 0 espera |
| Resposta fora de ordem durante digitação | podia substituir a mais nova | 0 respostas stale aplicadas |
| Descobrir qual produto era a amostra | nome lateral ambíguo | rótulo explícito com SKU no título |
| Conferir frescor e versão | memória/consulta externa | `as_of` + hash no mesmo card |
| Recuperar erro de variável/fonte | mensagem sumia, sem próximo passo | 1 Action inline, sem navegação/redigitação |

Provas locais:

- 4 testes de componente cobrem abort+epoch adversarial, batch/abas/variantes, erro+retry e
  identidade/as-of/hash; a resposta antiga foi resolvida propositalmente depois da nova;
- 154 testes focados de campaign/API/capabilities passaram em 23,96 s;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 573 testes passaram
  em 68,14 s;
- Marketing Nuxt: 8 arquivos/105 testes, ESLint, Nuxt typecheck e build passaram;
- fluxo real local foi exercitado por BFF→Django→SQLite seeded, sem mock do componente:
  login sintético, criação de campanha, seleção Instagram+WhatsApp, troca de aba e artifacts
  divergentes foram verificados em desktop e 390×844, sem overflow e sem escrita externa;
- a inspeção real também reproduziu o fetch protegido antes do login, dívida já destinada
  ao MKT-039, sem ampliar esta fatia fora da ordem das dependências;
- o build ainda baixou os fonts declarados por `@nuxt/fonts`; a remoção dessa dependência de
  rede está explicitamente reservada ao MKT-040. Nenhum provider, destinatário, deploy ou
  produção foi acessado.

## MKT-029 — readiness verificável e configuração de flow governada

Implementado sobre os contratos de autorização do MKT-020 e o artefato único do MKT-025:

- readiness deixou de ser um booleano inferido e passou a representar
  `ready/degraded/blocked/unknown`, com reason code allowlisted, versão, instante da
  checagem, `as_of`, validade e estado da fonte para cada plataforma;
- adapter ausente, credencial ausente, probe inexistente e probe indisponível são causas
  diferentes; uma falha do provider é redigida e vira `unknown`, nunca exception da página
  nem falso “pronto”;
- o catálogo ManyChat separa resposta fresca — inclusive uma resposta fresca realmente
  vazia — de outage, ausência de credencial e último snapshot conhecido; a cópia stale
  continua útil para diagnóstico, mas `mutation_safe=false` impede que ela autorize write;
- somente rows não marcadas inativas/arquivadas no provider entram na lista selecionável;
  um flow configurado que saiu da lista ativa bloqueia, enquanto um template inativo não
  é contado como aprovado;
- a alteração do flow é um command exclusivo do cockpit Marketing, com ator de sessão,
  capability específica, TOTP, confirmação emitida pelo servidor, chave de idempotência,
  CAS de versão, revalidação fresca em cada submit e receipt; o mesmo key reexecutado
  durante outage retorna o resultado concluído sem consultar novamente o provider;
- a transação serializa também a criação inicial, atualiza a versão monotônica e grava um
  `MarketingPlatformAuditEvent` append-only com ator, versões, refs anterior/nova e hash/
  `as_of` do catálogo; nenhum secret ou erro bruto entra no audit/receipt;
- a indisponibilidade do catálogo responde `503` + `Retry-After`; ref arbitrária, ref
  removida, versão stale e no-op têm resultados distintos e nenhum deles muda a
  configuração;
- o Admin Unfold mantém `NotificationTemplate` apenas como leitura para flow/ativação e
  aponta diretamente para Marketing → Plataformas, eliminando o segundo write path sem
  criar uma UI administrativa paralela;
- a página `/platforms` mostra causa, limitação, Action exata e horário da última
  verificação; escolhe por nome sem exibir o namespace opaco, confirma configuração atual,
  próxima configuração e versão, e pede somente o TOTP de seis dígitos;
- em conflito, a seleção permanece no modal, a versão é atualizada e só então nasce uma
  nova chave; falha ambígua conserva a chave original para replay seguro, evitando tanto
  redigitação quanto duplicação;
- o flow ativo, sua versão e o hash do catálogo agora são dados server-owned selados no
  `ResolvedDispatchArtifact` schema v3. Conteúdo/variante continua proibido de escolher
  flow. Preview, aprovação e o futuro adapter canônico recebem a mesma referência imutável;
  artefatos v2 continuam legíveis e preservam seus bytes canônicos;
- Projection v1/v2, Actions, JSON Schema, OpenAPI e cliente TypeScript foram atualizados;
  o board resolve readiness uma vez por conjunto de plataformas, sem consulta por card.

Budget de omotenashi comprovado na jornada de readiness/configuração:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Distinguir “zero flows” de outage | impossível sem consulta externa | estado e freshness no próprio painel |
| Encontrar a causa e o próximo passo | até logs/Admin/provider | 0 navegações; causa + Action no sheet |
| Copiar/digitar namespace técnico | 27+ caracteres suscetíveis a erro | 0 caracteres; uma escolha por nome |
| Confirmar o que será trocado | comparação entre telas | atual, novo e versão no mesmo modal |
| Alterar flow | Admin + provider + conferência | 1 escolha + TOTP + 1 confirmação |
| Reagir a outage | risco de colar ref antiga/arbitrária | 0 writes; 1 Action “Verificar novamente” |
| Recuperar conflito de versão | fechar, navegar e escolher novamente | 0 reseleções; modal preservado e versão recarregada |
| Conferir se preview e envio usam o mesmo flow | inspeção manual do banco/provider | flow/version/catalog hash dentro do artifact hash |
| Descobrir que um flow foi desativado | falha por destinatário | bloqueio antes da aprovação/provider |

Provas locais:

- 234 testes focados de readiness, catálogo, configuração, migration, artefato, aprovação,
  campaign, API, Actions e capabilities passaram em 32,54 s;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 652 testes passaram
  em 72,73 s;
- 107 testes Nuxt, ESLint, Nuxt typecheck e build de produção passaram;
- gate canônico Unfold: 229 testes e verificador estrutural passaram;
- `makemigrations --check --dry-run`, migration forward/reverse, Django check,
  `export_marketing_client --check`, Ruff dos arquivos alterados e `git diff --check`
  passaram; permaneceu somente o warning conhecido de SQLite local;
- o fluxo local real BFF→Django→SQLite foi inspecionado em desktop e 390×844: os quatro
  estados têm hierarquia distinta, WhatsApp degradado mostra causa/ação/horário, outage
  conserva a última lista apenas como diagnóstico, o retry é alcançável e não há overflow;
- a inspeção usou conta e dados sintéticos, portas isoladas `3006/8011`, e encerrou ambos
  os processos; o serviço de outra worktree já presente na porta 8000 não foi tocado;
- nenhuma rede de provider, destinatário, deploy, produção ou escrita externa foi usada.

## MKT-030 — ManyChat-only e isolamento fail-closed de custom fields

Implementado conforme a decisão negativa aprovada no G-H03: a ausência de prova externa
não foi transformada em capacidade fictícia.

- Marketing por WhatsApp resolve exclusivamente ManyChat; um adapter Meta direto
  registrado não é fallback e o console só existe em development/test, sem contar como
  readiness produtivo;
- a ADR-009 recebeu emenda explícita: troca de fornecedor exige nova decisão, SMS/e-mail
  não substituem silenciosamente o consentimento de canal de uma onda Marketing e uma
  credencial não remove a trava de isolamento;
- os flows Marketing que dependem de campos persistentes do subscriber ficam
  `blocked_unverified` até o ensaio sandbox G-H03 provar atomicidade/isolamento;
- readiness, aprovação atômica e adapter aplicam o mesmo reason code
  `manychat_custom_fields_unverified`; a aprovação rejeitada preserva receipt seguro e
  cria zero artifact/outbox;
- o adapter bloqueia antes de resolver subscriber, gravar custom field ou chamar o
  provider. Duas campanhas concorrentes contra o mesmo destinatário sintético resultam
  em zero chamadas e zero PII egress;
- o único bypass não configurável é um sentinel em memória inserido pelo serviço
  server-side de `send-test`, depois das guardas já existentes de capability, sandbox,
  ownership/synthetic target, quota, idempotência e máximo de um alvo; o marcador é
  consumido e nunca serializado no payload;
- a sequência low-level de custom fields continua disponível apenas para notificações
  transacionais existentes; os três eventos Marketing conhecidos são fechados por
  allowlist e têm teste de fronteira;
- o adapter e o facade de notificações deixaram de fabricar receipt com subscriber ou
  recipient; success booleano não vira “entregue”, logs não carregam destinatário e
  exception/body/reason do vendor viram códigos allowlisted;
- o deploy check diferencia flow ausente (`SHOPMAN_W014`, com reparo no cockpit) de flow
  presente porém inseguro (`SHOPMAN_E016`, bloqueante);
- nenhuma chamada sandbox externa foi executada: isso exigiria a autorização humana
  específica que o G-H03 preservou. O sistema torna a pendência explícita e segura em vez
  de alegar que a race foi resolvida.

Budget de omotenashi comprovado na fronteira ManyChat:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Descobrir se flow configurado também é seguro | documentação/provider/logs | estado e Action no cockpit |
| Conferir se Meta direto assumiu a onda | inspeção de registry/credenciais | impossível no resolver Marketing |
| Distinguir aceitação de entrega confirmada | inferência por `mc_<subscriber>` | receipt não é fabricado; estado honesto |
| Investigar erro bruto/telefone em logs | revisão manual por ocorrência | códigos allowlisted; zero recipient padrão |
| Impedir race entre duas campanhas | vigilância/serialização manual | zero provider calls enquanto não comprovado |
| Preparar ensaio futuro seguro | montar telefone/payload/bypass | fluxo existente: target verificado, max 1, receipt |
| Descobrir a próxima ação | consultar plano/owner | reason code + ensaio G-H03 no próprio readiness |

Provas locais:

- 5 testes de fronteira cobrem bloqueio default não-retryable, duas execuções
  concorrentes com zero provider calls, sentinel sandbox não serializado, receipt não
  fabricado e redaction de exception/recipient;
- 285 testes focados de ManyChat, backend selection, readiness, aprovação, artifact,
  Projection/Actions/API e deploy checks passaram em 27,56 s;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 693 testes passaram
  em 74,59 s;
- Marketing Nuxt: 9 arquivos/107 testes, ESLint e Nuxt typecheck passaram;
- Ruff dos arquivos alterados, `git diff --check`, Django check e migration drift
  passaram; permaneceu somente o warning conhecido de SQLite local;
- nenhuma migration, rede, provider real, sandbox remoto, destinatário, deploy,
  produção ou escrita externa foi usada.

## MKT-031 — threat model e controles de URL/mídia

Implementado sobre o artifact único do MKT-025, sem introduzir fetcher/proxy ou reduzir
o gate externo G-H03:

- o threat model versionado mapeia separadamente browser do operador, artifact/adapter e
  fetch do provider; Shopman não faz DNS, `GET`, `HEAD` nem segue redirect;
- links aceitos são somente rotas canônicas `/produto/<ref>` e `/oferta/<ref>` no origin
  exato de `SHOPMAN_STOREFRONT_BASE_URL`; scheme diferente de HTTPS, suffix confusion,
  userinfo, porta, query, fragment, encoding alternativo e rota de redirect falham;
- mídia absoluta exige HTTPS e host exato em `SHOPMAN_MARKETING_MEDIA_HOSTS` ou no origin
  da storefront; não há wildcard, URL/porta na configuração nem confiança implícita;
- IPv4/IPv6 loopback, privado, link-local, reservado, hostname local/internal e endpoint
  de metadata são recusados mesmo quando alguém tenta colocá-los na allowlist;
- query de link é proibida; mídia admite somente parâmetros fechados de transformação de
  imagem. Tracking params e redirect por query são recusados;
- qualquer proxy futuro já tem contrato para negar redirect cross-origin. Como o sistema
  atual não busca a imagem, criar um proxy agora ampliaria a superfície SSRF; o provider
  continua bloqueado até seu comportamento ser ensaiado no G-H03;
- o mesmo validador atende preview, aprovação, round-trip do artifact e o handler legado
  imediatamente antes do adapter. Remover um host da allowlist interrompe efeitos novos
  fail-closed;
- a Projection v1 sanitiza rows históricas antes de gerar `<img>`/link, impedindo que um
  valor legado hostil transforme a abertura do cockpit em request do browser;
- erros carregam reason code allowlisted e o campo exato, inclusive
  `platform_content.<plataforma>.image_url`; URL rejeitada nunca entra no log;
- a API responde `422` e mantém anúncio pendente, sem artifact/outbox, quando uma edição
  de imagem tenta alcançar IP privado;
- `SHOPMAN_E017` bloqueia configuração insegura no deploy check; settings e `.env.example`
  explicam o único knob e seu default vazio.

Budget de omotenashi comprovado para URL/mídia:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Conferir scheme/host/path/query manualmente | até 4 verificações por URL | 0; uma policy server-side |
| Descobrir qual override contém a URL ruim | comparar base e variantes | field error aponta a variante exata |
| Investigar se abrir o board chamou tracking | DevTools/log externo | impossível para URL não confiável |
| Corrigir link de campanha | procurar URL válida | usar destino canônico indicado no próprio erro |
| Decidir como reparar imagem | tentativa e erro | remover ou pedir 1 hostname exato ao owner |
| Verificar host-suffix/IP/redirect | consulta técnica externa | testes adversariais e deploy check |
| Conferir drift entre preview e provider | inspeção dupla | mesma validação no artifact e pré-adapter |

Provas locais:

- 32 testes específicos cobrem links canônicos, origin exato, suffix confusion, HTTPS,
  userinfo, portas, tracking/query/fragment, rota de redirect, IPv4/IPv6 privados,
  metadata, hostname local, dot-segments, query de mídia, redirect cross-origin, ausência
  de DNS/fetch, erro da variante, Projection segura, handler pré-provider e config;
- o teste de API comprova `422`, field error, anúncio preservado e zero artifact/outbox;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 728 testes passaram
  em 74,80 s; os dois testes finais do contrato de aprovação passaram separadamente;
- Marketing Nuxt: 9 arquivos/107 testes, ESLint e Nuxt typecheck passaram;
- Ruff dos arquivos alterados, `git diff --check`, Django check e migration drift
  passaram; permaneceu somente o warning conhecido de SQLite local;
- nenhuma migration, resolução DNS, fetch de URL, rede de provider, destinatário,
  deploy, produção ou escrita externa foi usada.

## MKT-032 — CampaignForm lossless e schema completo

Implementado sobre o cliente/contrato do MKT-023, com privacidade por construção e sem
transformar compatibilidade futura em exposição de dados:

- o vocabulário de audiência tem uma allowlist canônica única no serviço; a Projection
  entrega todos os seletores públicos suportados e nunca entrega `customer_refs` nem
  campos server-side/legados ao browser;
- a API de regras recusa campos top-level, seletores desconhecidos e o seletor privado;
  durante PATCH ela substitui o schema público inteiro, mas preserva no banco os campos
  privados/legados que o navegador não pode conhecer;
- o formulário agora representa `match`, tags, faixas de preço, RFM, churn, aniversário,
  janela de horário preferido e início/fim do período, além dos critérios já existentes;
- seletores de compras por SKU/coleção e extensões recebidas são preservados byte a byte
  quando não editáveis naquela tela; filtros do evento, horários adicionais e chaves
  futuras também não são reconstruídos nem descartados;
- salvar sem tocar em audiência/agendamento devolve o objeto original, preservando
  presença de `false`, ordem, extensões e janelas; uma alteração explícita modifica apenas
  as chaves controladas;
- trocar uma campanha agendada para gatilho de evento produz `type=immediate`, evitando o
  par impossível, mas preserva extensões server-side sem significado conflitante;
- a tela informa os filtros e horários que serão preservados, eliminando a necessidade de
  conferir JSON/Admin antes de salvar.

Budget de omotenashi comprovado na edição de regra:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Salvar só uma mudança de nome | podia alterar silenciosamente até 10 seletores | 0 diffs fora do campo alterado |
| Recriar tags/tier/RFM/match depois de abrir | até 4 grupos de redigitação/memória | 0; controles vêm preenchidos |
| Conferir período e horários adicionais | Admin/JSON externo | 0 navegações; período editável e horários listados |
| Preservar filtro de SKU/coleção não editável | impossível saber | garantia explícita no próprio formulário |
| Criar regra comum | nome + até 5 escolhas + salvar | ≤7 ações significativas, 0 mudanças de tela |
| Detectar campo novo/privado vindo do browser | write silencioso | erro dirigido, 0 writes |
| Evitar vazamento de membros da audiência | inspeção manual do payload | `customer_refs` impossível na Projection |

Provas locais:

- 17 testes do `CampaignForm` cobrem round-trip de todos os seletores, extensão futura,
  filtros do evento, schedule completo, janela adicional, edição localizada e troca de
  gatilho sem pairing inválido;
- 87 testes da API Marketing passaram, incluindo Projection sem membership, merge
  privado/legado e rejeição sem write de campos desconhecidos/privados;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 593 testes passaram
  em 72,60 s;
- Marketing Nuxt: 9 arquivos/112 testes, ESLint, Nuxt typecheck e build passaram;
- `export_marketing_client --check`, Ruff, Django check, migration drift e
  `git diff --check` passaram; permaneceu somente o warning conhecido de SQLite local;
- nenhuma migration, rede de provider, destinatário, deploy, produção ou escrita externa
  foi usada.

## MKT-033 — Rascunho privado, restaurável e reconciliável

Implementado sobre a edição lossless do MKT-032, mantendo conteúdo exclusivamente no
navegador e sem persistir membership, telefone, token ou outro dado de audiência:

- o autosave usa chave isolada por operador, tipo e recurso, schema versionado, TTL de
  sete dias e descarte defensivo de conteúdo expirado ou corrompido;
- anúncio, campanha e template salvam a edição completa após 400 ms, no `pagehide` e
  antes de qualquer comando; falha de rede ou autenticação não apaga o rascunho;
- refresh, remount, navegação e retorno de sessão restauram o conteúdo e todas as
  escolhas editáveis sem redigitação;
- `updated_at` funciona como CAS nas campanhas e templates: PATCH concorrente retorna
  `409` com a Projection atual, sem sobrescrever silenciosamente a outra sessão;
- quando base e servidor mudaram, um merge de três vias preserva automaticamente
  alterações independentes; sobreposição mostra, por campo, “Versão atual” e “Seu
  rascunho” e pede uma única escolha local;
- concluir o comando com sucesso limpa apenas a chave daquele operador/recurso;
  descartar é explícito e não afeta outros rascunhos.

Budget de omotenashi comprovado na recuperação:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Reescrever conteúdo após refresh/401 | até todo o formulário | 0 campos |
| Lembrar escolhas de plataforma/audiência/schedule | conferência e redigitação manual | 0 |
| Detectar edição concorrente | overwrite silencioso | `409` + diff no contexto |
| Resolver mudanças independentes | comparar duas versões completas | 0; merge automático |
| Resolver conflito real | copiar/colar em outra tela | 1 escolha inline por conjunto |
| Confirmar se o texto foi salvo | nenhuma certeza | status após ≤400 ms |
| Recuperar último keystroke ao sair | podia se perder | flush síncrono no `pagehide` |

Provas locais:

- 43 testes focados cobrem TTL/corrupção, isolamento operador+recurso, limpeza seletiva,
  refresh/remount, último keystroke, restauração integral de seleções, rebase sem
  conflito, diff concorrente e as duas resoluções;
- 90 testes da API Marketing passaram, incluindo CAS stale/current para campanha e
  template e garantia de zero overwrite no `409`;
- regressão ampliada Marketing/campaign/audience/notifications/E2E: 596 testes passaram
  em 76,50 s;
- Marketing Nuxt: 11 arquivos/128 testes, ESLint, Nuxt typecheck e build passaram;
- Ruff, `export_marketing_client --check`, Django check, migration drift e
  `git diff --check` passaram; permaneceu somente o warning conhecido de SQLite local;
- nenhuma migration, envio, rede de provider, destinatário, deploy, produção ou escrita
  externa foi usada.

## MKT-034 — Schedule, timezone, DST e expiração canônicos

Implementado sobre os comandos explícitos do MKT-019 e os facts/validade do MKT-027,
mantendo compatibilidade de leitura para schedules legados sem permitir que o cliente
novo volte a mandar horário ambíguo:

- `marketing_time` passou a ser o único boundary entre horário civil e instante:
  timezone IANA nomeado vem do backend, horário inexistente em gap de DST é recusado e
  horário repetido exige escolha explícita entre a primeira e a segunda ocorrência;
- o browser não infere mais seu próprio timezone. Ele envia data ISO com offset e o
  timezone nomeado da loja; API e model recusam timezone divergente, offset forjado,
  instante naive, passado ou sem próxima ocorrência;
- recorrências em gap pulam a data inexistente sem deslocar silenciosamente o horário;
  no fold disparam uma única vez, na primeira ocorrência, com teste da ocorrência
  seguinte;
- “Publicar agora” e “Agendar” continuam consequências separadas. O artefato sela modo,
  timezone e instante escolhido; receipt e cada lane da outbox apontam para o mesmo
  instante absoluto;
- o hash do artefato para “agora” permanece estável durante o gate de confirmação humana:
  a intenção imediata não contém um timestamp volátil, enquanto receipt e outbox
  registram o instante efetivo idêntico;
- quiet hours de mensagem direta aplicam a policy aprovada 20:00–08:00 no timezone da
  loja. O botão “agora” bloqueia preventivamente WhatsApp, o formulário sugere 08:00 e
  backend/reschedule recusam qualquer tentativa ou wave fora da janela; no último
  boundary, worker atrasado adia o target exatamente até a próxima abertura, antes do
  provider. Plataformas sociais não herdam indevidamente essa restrição;
- schedule no limite ou depois da expiração é recusado antes de criar artifact/outbox;
  reschedule valida todas as waves e preserva seus horários se alguma ultrapassaria a
  validade;
- o card mostra timezone, instante exato, outcome de quiet hours e expiração relativa +
  absoluta. Um prazo ainda positivo nunca aparece como “0 min”; gap, fold, passado e
  expiração são resolvidos inline sem consulta externa;
- o `CampaignForm` grava timezone em schedules novos/editados, preserva schedules legados
  intocados losslessly e explica a policy de recorrência nas duas transições de DST.

Budget de omotenashi comprovado no agendamento:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Descobrir qual timezone vale | inferência do navegador/config externa | 0 inferências; nome ao lado do campo |
| Converter horário para offset | cálculo/consulta externa | 0; conversão automática e validada |
| Resolver hora duplicada de DST | tentativa e erro | 1 escolha inline entre duas ocorrências |
| Corrigir hora inexistente de DST | falha tardia ou normalização silenciosa | erro imediato; 0 writes |
| Agendar WhatsApp durante silêncio | falha tardia + redigitação | sugestão 08:00; 1 toque, 0 redigitação |
| Conferir validade contra schedule | comparar relógios/telas | 0 navegações; bloqueio no próprio campo |
| Saber o prazo real | “0 min” ainda acionável ou relativo solto | relativo + absoluto + timezone |
| Conferir preview, receipt e worker | inspeção de três registros | igualdade do instante coberta por teste |
| Reconfirmar “agora” após step-up | podia conflitar por hash temporal | mesma intenção/hash; 0 repetição do comando |

Provas locais:

- 55 testes do cálculo temporal/schedule passaram, incluindo gap e fold de
  `America/New_York`, offset de `America/Sao_Paulo`, virada do dia e quiet-hour boundaries;
- 109 testes de aprovação/API passaram após o contrato novo; a regressão ampla de
  Marketing, scheduling, workers e projections somou 433 testes em 73,66 s;
- Marketing Nuxt: 12 arquivos/140 testes, incluindo fluxos reais dos dois formulários,
  ESLint, Nuxt typecheck e build de produção passaram;
- Ruff dos arquivos alterados, `export_marketing_client --check`, Django check,
  `makemigrations --check --dry-run` e `git diff --check` passaram; permaneceu somente o
  warning conhecido de SQLite local e não houve migration;
- o virtualenv compartilhado continuou sendo executado com `PYTHONPATH` explícito para
  todos os packages desta worktree, impedindo validação acidental do checkout original;
- nenhuma rede de provider, destinatário, deploy, produção ou escrita externa foi usada.

## MKT-035 — Resultado, partial, cancel, retry e reconcile no contexto

Implementado sobre o ledger/Aggregate do MKT-016, os comandos seletivos do MKT-017 e
as Actions/contrato gerado dos MKT-022–023, sem devolver autoridade ao browser:

- a rota `/announcements/:id` lê conteúdo compatível v1 e, em paralelo, fatos/Actions
  v2; o conteúdo mutável não foi recolocado no contrato factual e a UI deixou de inferir
  recuperação a partir de texto/status legado;
- resultado geral e por plataforma distingue `confirmed`, `accepted` ainda não
  confirmado, fila/envio, falha retryable/final, `unknown`, supressão, cancelamento e
  expiração. `completed_with_failures` é sempre “Entrega parcial” e `unknown` manda
  explicitamente não reenviar;
- retry, cancel e reconcile aparecem junto do resultado somente quando a Action canônica
  existe; `enabled`, `reason`, contagem, método e href são respeitados. Href de command é
  validado contra recurso/ação same-origin antes de qualquer request;
- retry repete só `failed_retryable`; reconcile é apresentado e testado como lookup-only;
  cancel promete somente faixas ainda não iniciadas. Permissão ausente, freeze, dispatch
  iniciado, reconciliação pendente e provider não reconciliável têm explicação inline;
- cada Action abre primeiro o challenge exato do servidor. A mesma versão, payload e
  idempotency key atravessam challenge, password/TOTP e submit final; frase tipada não é
  preenchida automaticamente. Duplo controle continua obrigatório e uma única sessão é
  incapaz de contorná-lo;
- o fluxo de aprovação que conduzia ao resultado também passou a consumir o challenge
  `428` corretamente; antes, o frontend tratava a confirmação obrigatória como erro e
  nunca chegava ao receipt;
- receipt seguro (sem token, membership ou conteúdo) permanece na rota após decisão ou
  recuperação e sobrevive refresh/navegação na mesma sessão por até 24 horas, isolado
  pelo `announcement:<id>`; resposta perdida/duplo toque reutiliza a mesma key;
- painel e histórico apontam diretamente para o anúncio exato. Estados agendado,
  `settled`, cancelado e expirado deixaram de desaparecer das queries de transição v1 e
  do histórico v2, preservando o caminho para cancel/recovery durante o cutover;
- erros 401, 403, 404, 429 e indisponibilidade deixaram de compartilhar “não encontramos”
  ou vazio. Falha da leitura v2 não inventa sucesso: mantém conteúdo/receipt e oferece
  refetch do ledger;
- todos os timestamps novos de confirmação, resultado e receipt são exibidos no timezone
  nomeado da loja, preservando o contrato do MKT-034.

Budget de omotenashi comprovado para resultado e recuperação:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Reencontrar resultado após publicar | toast + retorno ao painel + busca | rota exata; 0 buscas |
| Resolver partial retryable | sem Action segura | 2 ações significativas + gate aprovado; 0 mudanças de tela |
| Tratar unknown | investigar logs/provider ou reenviar no escuro | 2 ações + TOTP; 0 reenvios e 0 consultas externas |
| Saber quem será repetido | inferir por erro/texto | contagem exata de `failed_retryable`; accepted/confirmed/unknown excluídos |
| Cancelar schedule ainda reversível | reencontrar item/interpretar estado | Action no resultado; somente lanes não iniciadas |
| Confirmar efeito do command | toast efêmero | receipt/ref/versão/horário persistem no contexto |
| Recuperar refresh da rota | receipt perdido | 0 redigitação; sessão restaura por resource ref |
| Distinguir partial/unknown de sucesso | resultado legado ambíguo | headline, ícone, plataforma e contagens explícitos |
| Corrigir falha de carregamento | 401/403/404/5xx pareciam o mesmo | causa e próxima ação locais, sem login inútil no 403 |

A frase tipada e password/TOTP adicionam digitação quando a matriz G-H04 exige; isso é a
exceção de segurança prevista na seção 16 e não foi removido para atingir o budget.

Provas locais:

- Marketing Nuxt: 17 arquivos/159 testes passaram, incluindo partial+unknown na mesma
  tela, receipt após refresh, adulteração de href, context mismatch, duplo clique,
  retry/cancel/reconcile, password/TOTP e bloqueio de dual-control numa só sessão;
- 113 testes focados de API/Actions/recovery e 14 testes de board/history/cursor passaram;
- regressão ampla de Marketing, campaign, workers, ledger, security, scheduling,
  projections e E2E: 490 testes passaram em 76,56 s;
- ESLint, Nuxt typecheck e build de produção passaram; Ruff dos arquivos Python,
  `export_marketing_client --check`, Django check, migration drift e `git diff --check`
  passaram;
- permaneceu somente o warning conhecido de SQLite local; não houve migration;
- nenhuma chamada a provider, destinatário, deploy, produção, navegador autenticado ou
  escrita externa foi usada.

## MKT-036 — Lifecycle, dedupe, owner e reconciliação de alertas pessoais

Implementado sobre o Action resolver do MKT-022, por contrato aditivo e sem antecipar a
remoção do endpoint legado que pertence ao MKT-037:

- `UserNotification` agora separa `unseen`, `seen`, `acknowledged`, `resolved` e
  `expired`; `is_read/read_at` permanece somente como dual projection temporária, e
  visualizar jamais grava resolução;
- cada alerta traz severidade, condição/ref/versão de origem, owner funcional, grupo,
  dedupe por owner, função de escalação, deadline, versão própria e retention de cinco
  anos. A política aprovada atribui revisão a Product e escalação funcional a Ops, sem
  inventar pessoa nominal ou SLA ainda não aprovados em G-H08;
- criação repetida da mesma condição/versão/owner reutiliza o registro e grava evento
  `deduped`; mudança de versão do anúncio atualiza todos os siblings in-place, preserva
  `seen/acknowledged` e corrige mensagem, deadline, group/dedupe e Action;
- eventos append-only registram criação, dedupe, seen, acknowledgement, refresh,
  escolha, sucesso/falha e fechamento. Resolução originada por command moderno contém
  FK protegida para o `MarketingCommandReceipt`, ligando alert→receipt→resolution sem
  inventar receipt para fluxo legado;
- toda mudança canônica relevante do anúncio reconcilia todas as representações, em
  lote e na mesma transação. O GET v2 também revalida a origem, portanto signal/SSE
  perdido converge no próximo fetch;
- falha de Action grava outcome e preserva o alerta ativo; aprovação/recusa, expiry,
  objeto ausente ou condição já encerrada resolvem/expiram todos os siblings e emitem
  invalidação SSE mínima para cada owner;
- o endpoint aditivo `/api/v1/backstage/notifications/v2/` é owner-scoped, exclui
  information-only do sino, oferece histórico, counts `unseen` e `unresolved`, cursor
  opaco assinado, snapshot estável e filtro por retention. O endpoint v1 segue disponível
  para a troca ordenada do cliente no MKT-037;
- Actions de lifecycle passaram a ser `mark_notification_seen` e
  `acknowledge_notification`, com versão real do alerta. Deep-link de revisão é sempre
  resolvido server-side para o anúncio exato; `action_url`, `href` ou callable armazenado
  nunca viram autoridade;
- a migration mapeia `read=true` determinístico para `seen`, nunca para `resolved`;
  fonte de anúncio é backfilled quando comprovável, duplicata antiga é expirada e todo
  registro sem origem determinística é explicitamente `expired` com evento — não some
  por inferência silenciosa.

Budget de omotenashi comprovado no contrato de alertas:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Ver um alerta sem ainda resolver | card sumia como se concluído | permanece `seen`; `unresolved=1` |
| Saber se alguém assumiu | memória/conversa externa | estado `acknowledged` + owner + timestamp |
| Fechar avisos da mesma decisão | uma baixa manual por destinatário | 1 decisão fecha todos os siblings |
| Receber duplicata da mesma condição | N cards/decisões repetidas | 1 card; 0 writes de alerta duplicado |
| Recuperar SSE perdido | card zumbi até intervenção | próximo fetch reconcilia a origem |
| Encontrar o objeto certo | busca/navegação genérica | deep-link exato `/announcements/:id#review` |
| Distinguir visto de encerrado | impossível | dois counts e cinco estados explícitos |
| Auditar ação até o resultado | cruzar logs/IDs manualmente | evento referencia o receipt moderno |
| Carregar 20 de 30 alertas | risco N+1 | ≤25 queries, budget do board |

Provas locais:

- 35 testes focados de API/migration e 127 testes do recorte notifications, Actions,
  campaign e eventstream passaram;
- regressão ampla de Marketing/campaign/notifications/E2E: 606 testes passaram em
  106,90 s, incluindo comandos, transações, segurança, workers, ledger e projections;
- teste de migration executou de 0036 para 0037 com dados legados reais e comprovou
  `read→seen`, backfill determinístico e expiry explícito do restante;
- teste de 30 alertas comprovou a página de 20 dentro do budget máximo de 25 queries;
  testes adicionais cobrem IDOR, cursor adulterado, retention, info-only fora do sino,
  evento imutável, falha preservada, refresh de versão e SSE para cada sibling;
- Marketing Nuxt: 17 arquivos/159 testes, ESLint, typecheck e build passaram;
- Ruff, `export_marketing_client --check`, Django check, migration drift e
  `git diff --check` passaram; permaneceu somente o warning conhecido de SQLite local;
- o fallback `approve` do endpoint v1 foi deliberadamente preservado neste commit: sua
  remoção segura ocorre somente após a migração do cliente, no MKT-037 seguinte;
- nenhuma chamada a provider, destinatário, deploy, produção, browser autenticado ou
  escrita externa foi usada.

## MKT-037 — Client v2 e alerta sem decisão implícita

Implementado depois do lifecycle do MKT-036 e sem reabrir o atalho legado que contornava
versão, consequência, idempotência e confirmação do command canônico:

- `POST /notifications/<id>/action/` virou tombstone fail-closed: `action` ausente,
  vazia ou nula responde `400 action_required`; valor desconhecido responde `400`; até
  `approve|reject` explícito responde `410 notification_action_moved` e só aponta a
  revisão exata. Nenhum desses caminhos decide ou publica o anúncio;
- o client Marketing trocou para `/notifications/v2/`, cujo owner continua derivado da
  sessão. Href, método, kind e `resource_ref` de cada Action são comparados com o source
  canônico antes de qualquer request ou navegação; URL absoluta, recurso estranho,
  método trocado e source malformado falham fechados;
- abrir o sino marca os alertas unseen carregados por uma única mutação owner-scoped,
  limitada a 100 IDs e sem confiar em `user_id` do browser. A transação faz lock/bulk
  update/bulk event e emite uma única invalidação SSE; IDs de outro owner permanecem
  intocados;
- `seen` altera somente o contador de novos. O badge e a headline continuam mostrando
  `unresolved` até a condição do Announcement resolver; `acknowledged` assume a
  responsabilidade sem fabricar resolução;
- o sino mostra owner, lifecycle, deadline relativo + absoluto, timezone IANA, versão
  da origem e escalação. Há uma primary Action “Revisar anúncio”; decisão permanece no
  card, onde os gates modernos mostram versão/consequência. Falha de leitura ou mutação
  preserva o alerta e oferece retry no mesmo contexto;
- a Action abre `/announcements/<id>#review`; a página ganhou uma região DOM explícita
  `#review`, verificada no navegador depois que a primeira tentativa por fallthrough do
  componente mostrou que URL correta, sozinha, não garantia uma âncora real;
- o SSE continua carregando somente invalidação mínima. A caixa refaz seu fetch
  canônico e incrementa uma revisão local compartilhada; o board refaz sua própria
  projection sem abrir uma segunda conexão. Poll de 60 s, retorno à aba, retorno da rede
  e reconnect cobrem push perdido;
- information-only continua fora do sino; cursor, retention, dedupe, sibling
  reconciliation e ligação alert→receipt→resolution permanecem server-owned pelo
  contrato do MKT-036. O v1 de leitura fica durante a janela dual; sua mutação antiga
  permanece bloqueada e rollback algum restaura approve implícito.

Budget de omotenashi comprovado para alerta→revisão:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Action ausente | 1 command de aprovação implícita | 0 commands; erro explícito |
| Encontrar o anúncio do alerta | ação inline sem contexto ou busca genérica | sino + “Revisar anúncio”; 2 gestos, 0 buscas |
| Chegar ao problema exato | rota do objeto sem âncora garantida | `#review` existente e visível |
| Marcar uma página de alertas como vista | até N requests/gestos | 1 request para até 100 itens |
| Distinguir “vi” de “foi resolvido” | contador sumia cedo | `unseen=0`, `unresolved=1` após abrir |
| Saber prazo, fuso, owner e escalação | memória ou consulta externa | 0 navegações; tudo no card do alerta |
| Recuperar push perdido | F5/intervenção | refetch no reconnect/online/visible e ≤60 s por poll |
| Falha ao assumir/atualizar | risco de sumir ou repetir no escuro | alerta e mensagem de retry permanecem juntos |
| Usar em tela estreita | risco de painel recortado | 390×844 sem overflow; largura medida dentro do viewport |

Provas locais:

- 41 testes focados da API de notificações passaram, cobrindo missing/unknown action,
  zero efeito legado, IDOR, batch owner-scoped, lifecycle, dedupe, siblings, cursor,
  retention, expiry, Action/capability e receipt;
- regressão ampla Marketing/campaign/notifications/E2E: **623 testes passaram em
  106,51 s**;
- Marketing Nuxt: **20 arquivos/172 testes**, incluindo Action adulterada, batch único,
  SSE→refetch, falha preservada, capability desabilitada, ausência de approve/reject no
  sino e âncora DOM explícita; ESLint, Nuxt typecheck e build de produção passaram;
- gate canônico Unfold: verificador estrutural e **229 testes** passaram; Ruff,
  `export_marketing_client --check`, Django check, migration drift e `git diff --check`
  também passaram. Permaneceu somente o warning conhecido de SQLite local;
- fluxo BFF→Django→SQLite foi inspecionado com conta/anúncio/alerta sintéticos em portas
  isoladas `3006/8011`: desktop e 390×844, badge `unresolved`, seen sem resolução,
  fuso/escalação, deep-link exato, região `#review` visível, Escape e console sem erros;
  os três registros e ambos os processos temporários foram removidos/encerrados;
- nenhuma decisão de anúncio, provider, destinatário, deploy, produção, push remoto ou
  escrita externa foi executada.

## MKT-038 — IA estruturada, factual, auditável e sempre assistiva

Implementado depois do artefato e dos fatos canônicos dos MKT-025–027, sob a policy
provisória aprovada no G-H06 e sem habilitar piloto ou provedor externo:

- a IA ficou atrás de dois gates independentes, ambos `false` por default:
  `SHOPMAN_MARKETING_AI_ASSIST_V2` e
  `SHOPMAN_MARKETING_AI_PROVIDER_POLICY_APPROVED`. Credencial isolada não expõe o botão
  nem autoriza request;
- nascimento de anúncio voltou a ser 100% determinístico. A geração automática foi
  removida do campaign service e uma regra com `requires_approval=false` nunca chama IA
  nem despacha output gerado;
- a sugestão usa contrato estrito `body/hashtags/used_fact_ids/warnings`, tamanho e
  cardinalidade limitados, timeout fixo e budget de 900 tokens. Campos extras, schema
  inválido, Unicode oculto, idioma claramente não PT-BR, URL, número, preço/promoção,
  urgência/escassez, claim dietético/saúde, atributo de produto, evento ou disponibilidade
  sem suporte e conteúdo ofensivo são rejeitados antes de chegar à revisão;
- prompt, voz, instrução de template, texto atual e até valores de produto passam como
  dados não confiáveis sob uma boundary fixa. Injection, telefone, e-mail, CPF, segredo e
  credencial são barrados antes do provider; somente facts canônicos allowlisted e ainda
  frescos entram no pedido;
- o ledger append-only registra actor/request, provider/model/policy, versão, fact/prompt/
  output/field hashes, IDs de fatos, warnings e buckets de latência/custo. Não persiste
  prompt, copy, cliente, membership, telefone ou erro bruto do provider;
- aceitar/descartar é telemetria humana e nunca grava o Announcement. Só “Usar no
  rascunho” altera o estado local; aprovação continua sendo command separado e registra
  se o resultado foi aprovado intacto ou editado, com os campos do diff e hashes;
- timeout/falha preserva corpo e hashtags. Revalidar na aprovação impede reutilizar
  sugestão depois de mudança de versão ou fact hash; desligar a flag remove o botão sem
  afetar edição manual, snapshot ou dispatch;
- o Admin valida a instrução antes de salvar e a copy deixou claro que IA é uma sugestão
  separada na revisão, nunca geração automática;
- a inspeção BFF→Django encontrou um defeito que o mock de componente não revelava: os
  POSTs novos não declaravam `credentials: same-origin` e recebiam 403 apesar das leituras
  autenticadas. Ambos os POSTs foram corrigidos e ganharam asserção de regressão.

Budget de omotenashi comprovado para a assistência de copy:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Pedir uma alternativa | redigir fora do contexto ou geração implícita | 1 gesto, 0 navegações |
| Comparar antes/depois | memória ou troca de tela | original, sugestão, facts e warnings lado a lado |
| Conferir base factual | consulta a catálogo/evento | 0 consultas externas; facts nomeados no card |
| Aceitar sem publicar | risco de confundir geração com envio | 1 gesto muda só o draft; 0 commands |
| Desfazer | redigitar o texto anterior | 1 gesto, 0 redigitação |
| Continuar após timeout/falha | risco de perder edição | 0 caracteres perdidos; edição manual permanece |
| Saber o que a IA pode decidir | inferência/uncertainty | policy visível; target, oferta, link, schedule e plataforma fora do contrato |
| Auditar edição humana | comparar copy em logs | hashes + `approved_edited|unedited` + campos do diff |

Provas locais:

- 314 testes focados de IA/copy/approval/campaign passaram; o corpus offline contém 200
  casos adversariais PT-BR, injection, dados pessoais, URL, Unicode, números, fatos/eventos
  conflitantes, idioma, urgência e ofensa, com zero escape crítico;
- regressão ampla de Marketing/campaign/notifications/workers/deploy: **932 testes
  passaram em 121,55 s**; os únicos 3 warnings são os esperados de override de banco nos
  testes de deploy;
- Marketing Nuxt: **20 arquivos/175 testes**, ESLint, typecheck e build de produção
  passaram;
- gate Unfold: verificador estrutural e **229 testes** passaram; Ruff, contrato TS,
  Django check, migration drift e `git diff --check` passaram. Permaneceu somente o
  warning conhecido de SQLite local;
- fluxo visual local com conta/produto/template/campanha/anúncio sintéticos comprovou:
  botão condicional, original intacto após pedir, comparação com dois facts/warning/policy,
  uso sem publicação e undo em um gesto. O provider foi um stub estritamente local em
  `127.0.0.1`; tentativas com facts vencidos e ID inexistente falharam fechadas. Os três
  processos foram encerrados e o banco SQLite exclusivo desse QA foi removido da worktree
  para a Lixeira, de forma recuperável;
- foi criada a migration `0038` para o ledger e para a semântica review-only do template;
  nenhuma rede externa, destinatário, deploy, produção, push remoto ou escrita externa
  foi usada.

Limite do gate: a implementação técnica local do MKT-038 está concluída. O piloto de IA
continua bloqueado pelo G-H06 até Segurança/Privacidade comprovar retenção, no-training e
transferência do provider e Marca/Jurídico/Produto aprovar a revisão humana. Nenhuma flag
de ambiente real foi ou será habilitada por esta entrega.

## MKT-039 — Gate real de sessão, 401/403 e retomada segura

Implementado depois de Projection/Actions e drafts (MKT-023, MKT-024 e MKT-033),
sem antecipar headers ou a revisão completa de acessibilidade dos MKT-040/041:

- a antessala `/operator/session/` passou a receber uma capability allowlisted e
  responde apenas `authorized: true|false` para a identidade atual; não lista
  permissões, não concede acesso e recusa nomes fora da allowlist;
- a API v1 de Marketing mantém `401` para sessão ausente/expirada e `403` para
  identidade autenticada sem capability. O frontend deixou de tratar os dois como
  se novo login resolvesse ambos;
- o shell usa a máquina `checking|authenticated|anonymous|expired|forbidden` do
  operator-kit. O `NuxtPage` permanece como outlet do router, mas o componente de
  rota, seus composables, timers e SSE só são instanciados em `authenticated`;
- erro da antessala mostra indisponibilidade e retry com o cockpit fechado; não vira
  painel vazio, 404 ou pedido de senha. Forbidden explica que reentrar não amplia
  acesso e oferece retorno à Central;
- todos os reads protegidos do Marketing sinalizam 401 para o gate. Um 403 só levanta
  a trava quando o reason code canônico é `station_locked`; capability negada não é
  reinterpretada como expiração;
- login deixou de recarregar a página inteira: primeiro reconcilia a sessão ainda com
  o gate fechado e só depois libera a rota. Requests de identificação/cadeado declaram
  credenciais same-origin explicitamente;
- decisão interrompida preserva anúncio, ação, corpo editado, versão e chave
  idempotente em estado global do app. Token/challenge antigo é sempre descartado;
  após reautenticar, um gesto explícito pede nova conferência do servidor e exige nova
  confirmação. A intenção é ligada ao operador original e é apagada se outra pessoa
  entrar, impedindo transferência silenciosa de decisão;
- um 401 vindo de poll/read enquanto o diálogo estava aberto também converte o
  challenge em intenção retomável antes de desmontar a página. Rascunhos continuam
  isolados por operador pelo contrato do MKT-033;
- nenhuma migration foi necessária e nenhum endpoint protegido ficou disponível à
  antessala.

Budget de omotenashi comprovado para sessão e recuperação:

| Trabalho/risco do operador | Antes | Depois |
|---|---:|---:|
| Abrir Marketing sem sessão | até 4 reads protegidos montavam atrás do overlay | 0 reads protegidos; somente antessala |
| Saber se é login ou falta de acesso | tentativa, vazio/403 ou novo login inútil | 1 estado explícito; 401 e 403 distintos |
| Recuperar após login | reload completo e reconstrução mental da rota | 0 reloads; mesma rota retorna automaticamente |
| Redigitar draft após expiração | risco de perda/reabertura manual | 0 caracteres e 0 navegações perdidos |
| Retomar approve/reject interrompido | reconstruir texto/ação/chave | 1 gesto “Retomar e reconfirmar”, 0 redigitação |
| Conferir se a ação saiu antes da expiração | consulta externa ou medo de duplicar | receipt/idempotência preservados; UI afirma “não foi enviada” |
| Evitar token stale | conferência manual impossível | challenge descartado estruturalmente e reemitido |
| Troca de operador | risco de herdar intenção anterior | 0 decisões transferidas; owner mismatch bloqueia e apaga |
| Outage da sessão | login/empty enganoso | cockpit fechado + 1 botão de retry |

Provas locais:

- reproduções contratuais falharam primeiro por ausência de `authorized` e por 403
  anônimo; depois, 122 testes focados de sessão/login/API Marketing passaram;
- regressão ampla de Marketing/campaign/notifications/workers/deploy e sessão:
  **938 testes passaram em 123,33 s**; os únicos 3 warnings são os esperados de
  override de banco nos testes de deploy;
- Marketing Nuxt: **23 arquivos/187 testes** passaram; operator-kit: **18 arquivos/179
  testes** passaram. ESLint, typecheck e build de produção passaram;
- Ruff, contrato TS, Django check, migration drift e `git diff --check` passaram;
  permaneceu somente o warning conhecido de SQLite local;
- teste vivo local em `127.0.0.1` comprovou que anônimo fez somente a consulta de
  sessão e zero requests a board/rules/options/notifications; esses quatro reads só
  começaram depois do login autorizado. Uma identidade autenticada sem
  `shop.view_marketing` recebeu o estado forbidden e também fez zero reads protegidos;
- a repetição após trocar o outlet pelo slot do `NuxtPage` manteve zero fetch protegido
  e eliminou o warning de outlet condicional do Nuxt;
- os dois processos locais foram encerrados. O SQLite exclusivo do QA, com apenas
  identidades sintéticas, foi movido de forma recuperável para
  `/Users/pablovalentini/.Trash/django-shopman-marketing-mkt039-qa-20260909.sqlite3`;
- nenhuma chamada a provider, destinatário, rede externa, deploy, produção, push,
  merge, PR ou escrita externa foi realizada.

A implementação técnica local do MKT-039 está concluída. Os gates de piloto/release
permanecem inalterados; MKT-040 (headers/BFF/cache/fonts) é a próxima dependência da
ordem aprovada.

## MKT-040 — Headers, BFF sem cache compartilhado e fontes incorporadas

Implementado depois do contrato BFF/Actions do MKT-024 e do gate de sessão do
MKT-039, sem tocar proxy/deploy real:

- uma única matriz reutilizável no operator-kit aplica CSP com nonce por request,
  HSTS, `nosniff`, `DENY`/`frame-ancestors 'none'`, referrer, COOP/CORP,
  permissions policy e DNS-prefetch off; `x-powered-by` é removido;
- o render hook do Marketing injeta o mesmo nonce em todos os `script`/`style` do
  HTML SSR. `script-src` não contém `unsafe-inline`; o único `unsafe-inline` ficou
  confinado a `style-src-attr`, necessário para estilos de estado do Vue;
- HTML e respostas privadas usam `private, no-store`; o BFF sobrescreve qualquer
  cache-control permissivo do upstream. SSE só usa `no-cache, no-transform` quando o
  stream foi aceito; recusas e falhas permanecem privadas/no-store;
- JS/CSS com hash e os webfonts com hash recebem `public, max-age=31536000,
  immutable`, sem transformar endpoints privados em cacheáveis;
- o proxy continua repassando apenas metadados operacionais allowlisted. Cookies do
  Django só atravessam após validação de sintaxe, atributos e prefixos seguros;
  redirects só atravessam como caminho absoluto same-origin, sem `//`, backslash ou
  bytes de controle. CSRF, origin/referer e atributos válidos continuam preservados;
- `@nuxt/fonts` e o provider Google foram removidos do manifest/lock. Instrument
  Sans e Fira Code, nos subsets `latin`/`latin-ext`, estão incorporadas no app com
  nomes content-addressed e licença OFL versionada;
- nenhum header foi relaxado por ambiente e nenhuma exceção CSP oculta foi criada.

Matriz viva comprovada no build de produção local:

| Superfície | Status exercitado | Cache | Matriz/CSP |
|---|---:|---|---|
| HTML `/` | 200 | `private, no-store` | completa, nonce único |
| erro HTML inexistente | 404 | `private, no-store` | completa, nonce único |
| BFF Marketing anônimo | 401 | `private, no-store` | completa |
| antessala BFF anônima | 403 | `private, no-store` | completa |
| SSE pessoal anônimo | 404 | `private, no-store` | completa |
| JS/font local com hash | 200 | `public, max-age=31536000, immutable` | proteção estática estrita |

Budget de omotenashi/segurança comprovado:

| Trabalho/risco | Antes | Depois |
|---|---:|---:|
| Headers web ausentes no HTML Nuxt | 7 classes essenciais ausentes | 0; 10 headers defensivos explícitos |
| Resposta privada que podia herdar cache upstream | 1 decisão implícita por resposta | 0; BFF sempre `private, no-store` |
| Redirect/cookie upstream aceito sem conferência | 2 superfícies abertas | 0; duas validações fail-closed |
| Dependência de catálogo/download Google no build | 1 módulo/provider + 2 famílias descobertas | 0 endpoints externos |
| Recursos DOM observados fora da origem local | não contratado | 0 de 18 |
| Violações CSP no carregamento do cockpit | não contratado | 0 |
| Conferência manual de nonce entre header e HTML | necessária | 0; geração/injeção compartilham o mesmo contexto |

Provas locais:

- operator-kit: **19 arquivos/185 testes**; Marketing Nuxt: **24 arquivos/189
  testes**, incluindo cookies, redirects, cache, headers, nonce e presença física de
  cada fonte;
- ESLint, typecheck, build de produção e `git diff --check` passaram;
- busca no artefato `.output` encontrou zero `fonts.googleapis`, `fonts.gstatic`,
  `https://fonts`, `@nuxt/fonts` ou `/_fonts/`;
- navegador real hidratou o login, confirmou `document.fonts` pronto para Instrument
  Sans, observou somente recursos same-origin e registrou zero violação CSP;
- nenhum deploy, provider, destinatário, ambiente real, push, merge, PR ou escrita
  externa foi realizado. O Django/Nuxt usados na prova foram apenas processos locais.

A implementação técnica local do MKT-040 está concluída. A aprovação final da matriz
por Segurança permanece requisito humano de piloto/release; MKT-041 (acessibilidade,
touch, foco e reflow) pode seguir localmente sem reduzi-la.
