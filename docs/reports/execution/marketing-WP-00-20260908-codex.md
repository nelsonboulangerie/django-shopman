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
