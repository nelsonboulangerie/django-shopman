# Marketing — pacote recomendado de decisões dos gates humanos

**Versão:** `marketing-human-gates.v1`

**Data:** 2026-09-08

**Status:** APROVADO PARA IMPLEMENTAÇÃO LOCAL

**Escopo:** G-H01 a G-H10 do plano `MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`

**Confirmação humana:** em 2026-09-08, o proprietário confirmou o pacote por referência inequívoca à declaração da seção 13 com a resposta: “ok, pode prosseguir dessa forma.” A autorização conserva integralmente as exclusões e os gates futuros descritos neste documento.

## 1. O que a confirmação deste pacote autoriza

A confirmação humana da declaração da seção 13:

1. fecha as escolhas de política necessárias para implementar localmente G-H01, G-H02, G-H03 e G-H04;
2. autoriza testes, schemas, migrations aditivas, flags seguras e implementação local de WP-00 em diante, respeitando dependências;
3. aprova como defaults provisórios as políticas de Produto, IA, Admin e SLO abaixo;
4. não autoriza deploy, escrita em produção, uso de credencial, teste em sandbox externo, envio real, merge, push, PR, piloto ou rollout;
5. não transforma evidência futura em formalidade: discovery com gestores, red-team, sandbox ManyChat, drills, baseline de capacidade e cada gate de release continuam obrigatórios;
6. não permite que um agente declare aprovação em nome de um decisor ausente. A confirmação deve ser feita pelo proprietário/decisor responsável ou acompanhada da delegação explícita dessa autoridade.

## 2. Princípios comuns aprovados pelo pacote

- Segurança e consentimento falham fechados; indisponibilidade nunca vira audiência zero nem autorização implícita.
- Nenhum opt-out, revogação, redaction, CSRF, permission recheck ou unique guard pode ser desligado por flag.
- Nenhuma garantia externa excede a capacidade documentada do fornecedor.
- O caso comum deve ser curto, mas confirmação proporcional não será removida para bater budget de toques.
- Toda decisão perigosa mostra conteúdo, versão, plataformas, audiência, horário/timezone e consequência antes de confirmar.
- O browser nunca recebe membership, telefone, segredo, erro bruto do fornecedor ou callable arbitrário.
- IA sugere; humano edita e aprova em ações separadas; IA nunca publica.
- Nuxt é o cockpit operacional único. Admin não oferece um segundo caminho de escrita.

## 3. G-H01 — consentimento, finalidade, legado e minimização

### 3.1 Base e finalidades

Para Marketing em massa, o default aprovado é **consentimento**, não legítimo interesse. Mensagens transacionais de pedido continuam em finalidade e base próprias e jamais são reutilizadas como opt-in de Marketing.

| Purpose code | Uso permitido | O que não concede |
|---|---|---|
| `marketing_general` | novidades, produtos, campanhas e ofertas gerais no canal consentido | alertas de SKU em outro canal; transacional; profiling sensível |
| `stock_availability` | um aviso solicitado para um SKU e canal determinados | campanha geral; outro SKU; comunicação recorrente |
| `transactional_order` | mensagens necessárias ao pedido; fora do Marketing | qualquer campanha ou anúncio promocional |

O consentimento é específico por `subject + channel + purpose`. Autorizações genéricas ou inferidas por compra, favorito, tag, silêncio ou uso do site são inválidas para Marketing.

### 3.2 Precedência única

```text
hard/global do-not-contact
  > opt-out ou revogação explícita do channel+purpose
  > supressão de categoria/frequência/colisão/quiet hours
  > inválido, inalcançável ou duplicado
  > assinatura purpose-specific ativa e comprovada
  > opt-in explícito channel+purpose ativo e comprovado
  > elegibilidade da regra
```

Regras:

- Um opt-out global posterior sempre vence assinatura de SKU, reason `alerts`, retry, fallback ou regra.
- Criar uma assinatura depois de um opt-out não limpa o opt-out silenciosamente. O mesmo fluxo pode oferecer uma reativação explícita e destacada; ela gera um novo evento de consentimento antes da subscription.
- Falha ou ausência de leitura é `degraded/unavailable` e bloqueia aprovação/dispatch.
- Opt-in posterior à aprovação nunca entra no cohort já aprovado. Revogação posterior sempre remove antes do claim.

### 3.3 Disclosures versionados

Versão inicial `marketing-general.pt-BR.v1`:

> Quero receber pelo WhatsApp novidades e ofertas da {shop_name}. Para esta autorização, meu telefone será usado para essa finalidade e o envio poderá ser operado pela ManyChat. Posso cancelar gratuitamente a qualquer momento em Minha conta. Política de Privacidade: {privacy_url}.

Versão inicial `stock-availability.pt-BR.v1`:

> Quero receber pelo WhatsApp um aviso quando {product_name} voltar. Este pedido vale somente para este produto e termina após o primeiro aviso, cancelamento ou 30 dias. Posso cancelar gratuitamente a qualquer momento em Minha conta. Política de Privacidade: {privacy_url}.

Requisitos:

- checkbox/controle desligado por default;
- controlador, canal de privacidade e link da política resolvidos de configuração canônica;
- registrar texto exato/hash, versão, locale, source, actor class, occurred/recorded timestamps e evidence hash;
- mudança material de finalidade, fornecedor/compartilhamento ou duração exige versão nova e novo consentimento;
- `marketing_general` deve ser reconfirmado após 24 meses sem evento afirmativo mais recente;
- alerta de estoque encerra após primeiro efeito conhecido, cancelamento ou 30 dias.

### 3.4 Legado e migração

- Opt-outs legados são importados e honrados; nunca são descartados por falta de versão de texto.
- Opt-ins sem prova de disclosure/finalidade viram `legacy_unverified`, não `opted_in` inventado, e ficam fora de campanhas novas até reconsentimento.
- Registros legados com prova verificável podem ser importados como `legacy_verified` somente por backfill idempotente que registre source, confiança e evidence hash.
- Campanhas pending/scheduled legadas não migram automaticamente: fatos, consentimento, readiness e horário devem ser revalidados.
- A migration é expand-only; o estado mutável atual continua como projection compatível até a reconstrução por eventos ser provada.

### 3.5 Retenção, erase e audience privacy

Política inicial, deliberadamente revisável pelo DPO:

- eventos de consentimento e revogação: 5 anos após o último evento, para prova e exercício regular de direitos; revisão anual de necessidade;
- IP bruto, quando realmente coletado para antiabuso: máximo 90 dias; depois remover ou reduzir a evidência a hash não reversível;
- opt-out/do-not-contact mínimo: enquanto o contato estiver ativo e por 5 anos após remoção, limitado a impedir novo contato e provar a revogação;
- command/audit sem PII: 5 anos;
- membership e delivery subject link: seção 4.4;
- pedido de erase bloqueia o envio imediatamente. PII operacional é removida; ficam somente prova mínima/tombstone quando houver fundamento documentado, legal hold ou necessidade de honrar do-not-contact;
- qualquer exceção de retenção exige reason, owner, expiry e access audit.

O prazo de 5 anos é uma escolha de gestão de risco deste sistema, não uma afirmação de que a LGPD imponha prazo geral de cinco anos.

### 3.6 Min cohort, frequência e quiet hours

- Campanha geral exige pelo menos **10 elegíveis**. Abaixo disso, não há blast; usa-se sandbox/teste ou finalidade específica.
- Alerta de SKU solicitado é fluxo próprio e pode ter uma pessoa; não usa o endpoint de campanha.
- Somente roles autorizadas veem total exato. Buckets de exclusão entre 1 e 4 aparecem como `<5` para reduzir inferência.
- Limite por recipient/channel para `marketing_general`: 1 em 24 h, 3 em 7 dias e 10 em 30 dias.
- `stock_availability`: um aviso por subscription/occurrence; não consome quota de campanha, mas respeita hard suppression e quiet hours.
- Quiet hours: 20:00–08:00 no timezone confiável do recipient; sem timezone, `America/Sao_Paulo`.
- Mensagem que expiraria antes da próxima janela permitida expira/suprime; não sai atrasada.
- Collision window para mesma promoção/SKU/purpose: 24 h.

### 3.7 Base normativa usada na recomendação

A LGPD exige consentimento demonstrável, específico, informado, revogável e acesso claro às informações do tratamento; a ANPD reforça revogação gratuita/facilitada e direito de eliminação sujeito às exceções legais:

- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm
- https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-cookies-e-protecao-de-dados-pessoais.pdf

## 4. G-H02 — proteção do cohort e delivery target

### 4.1 Modelo aprovado

- `AudienceSnapshot` guarda regra/policy/fact versions, counts e HMAC do cohort; não guarda telefones.
- `AudienceSnapshotMember` usa somente FK/ref interna opaca do cliente e acesso de aplicação restrito.
- `DeliveryTarget` usa unique `(snapshot, platform, target_fingerprint)`; fingerprint é HMAC-SHA-256 com secret versionado, nunca hash simples de telefone.
- Telefone é resolvido no último boundary antes do adapter e não persiste no snapshot, projection, receipt, log ou métrica.
- DB/backup devem ter criptografia at-rest; secrets de HMAC ficam no secret manager, nunca no banco ou repo.
- Rotação de HMAC mantém `key_version`; não recalcula target histórico em massa sem plano de reconciliação.

### 4.2 Classificação e proibições

- Cohort e target são dados pessoais pseudonimizados, não “anônimos”.
- É proibido segmentar ou inferir saúde, religião, origem racial/étnica, opinião política, sindicato, vida sexual, genética ou biometria.
- Tags livres que possam representar dado sensível são rejeitadas para audience rules.
- Menores conhecidos são excluídos de `marketing_general`; birthday pode ser usado somente sem inferir idade sensível e sob consentimento válido.
- Announcement JSON, Projection, SSE, Admin comum, export genérico, Sentry e logs nunca expõem membership.

### 4.3 Matriz de acesso

| Papel | Acesso |
|---|---|
| Observer/Editor/Approver | somente counts/freshness/buckets permitidos |
| Publisher | counts e states; nunca telefone/lista |
| Support | receipt, platform, state e error code; sem PII por default |
| Platform Owner | provider ref sanitizada; PII apenas em break-glass |
| Auditor/DPO | acesso purpose-bound sob step-up, com auditoria e expiração |

Break-glass exige reason, ticket/ref de incidente, TOTP, TTL de 15 minutos e evento de auditoria. Não existe browse/listagem livre no Admin.

### 4.4 Retenção e erase do cohort

- Membership e FK do target: até 90 dias após `settled/cancelled/expired`.
- `unknown` pode estender a retenção até reconciliar, com teto de 180 dias; depois disso exige legal hold explícito do DPO ou pseudonimização/erase.
- Provider ID sanitizado: máximo 180 dias após settlement, salvo incidente/legal hold.
- Após a janela, apagar membership/FK/provider ID e preservar somente counts, hashes não reversíveis, states, timestamps e audit técnico.
- Erase do titular suprime imediatamente e remove o vínculo assim que permitido; snapshots mantêm contagem/hash, nunca contato.

### 4.5 Volume e proteção operacional

- Hard cap inicial: 5.000 recipients externos por command.
- O resolver deve suportar fixture sintética de 100.000 candidates e o ledger 10.000 targets em teste de margem 2×.
- Paginação/batching é obrigatória; nenhum endpoint entrega membros.
- Counts e combinações de filtros são throttled, limitados a vocabulário fechado e auditados por code, nunca por regra livre.

## 5. G-H03 — garantia externa ManyChat/Meta

### 5.1 Capacidade documentada em 2026-09-08

A documentação pública oficial encontrada expõe `sendContent` e `sendFlow`, mas não documenta:

- idempotency key/token por envio;
- message/delivery receipt estável no response;
- consulta de status/reconcile por command;
- webhook de entrega correlacionável ao command do Shopman.

Fontes:

- Swagger oficial: https://api.manychat.com/swagger?urls.primaryName=Profile+API
- OpenAPI oficial: https://api.manychat.com/swagger/compileJson?type=Page_API
- limites oficiais: https://help.manychat.com/hc/en-us/articles/14959510331420-How-to-generate-a-token-for-the-Manychat-API-and-where-to-get-parameters

Há divergência entre a página de ajuda (25 RPS para endpoints de envio) e o Swagger (`sendFlow` 20 RPS e 100 chamadas/subscriber/hora). Endpoints de custom fields têm limite de 10 RPS. O sistema adota o menor limite relevante até sandbox provar outro.

### 5.2 Semântica aprovada

| Evidência observada | Outcome interno | Retry |
|---|---|---|
| falha de DNS/conexão comprovadamente antes de enviar bytes | `not_attempted` | automático com budget/jitter |
| `429` explícito | `failed_retryable` | respeitar `Retry-After`; sem header, circuit de 60 s |
| `4xx` explícito diferente de 429 | `failed_final` | não automático |
| `200` + status success | `accepted_unconfirmed` | nunca repetir |
| timeout/drop após possível envio; `5xx`; resposta inválida após write | `unknown` | nunca automático |
| callback/receipt futuro autenticado e correlacionado | `confirmed` ou `failed_*` | monotônico/idempotente |

Consequências:

- Não se promete exactly-once externo.
- `accepted_unconfirmed` nunca aparece como “entregue”.
- O adapter não fabrica message ID como `mc_<subscriber>`.
- `unknown` permanece até evidência; sem API de reconcile, a Action abre/escalona para o owner do canal com receipt, janela e artifact hash seguros.
- Reenvio de `unknown` é proibido nesta versão. Se o owner concluir que deve reenviar, cria-se um novo command humano explicitamente autorizado, nunca retry escondido.

### 5.3 Rate, flow e custom fields

- Cap inicial por bot: 8 targets/s, concorrência 4, com circuit breaker e jitter.
- Custom fields devem ser gravados em chamada batch única quando inevitáveis; múltiplas gravações campo a campo antes de `sendFlow` são proibidas no caminho novo.
- Até sandbox provar isolamento/atomicidade, flow que dependa de custom fields persistentes concorrentes fica `blocked_unverified` para Marketing.
- Preferir artifact totalmente renderizado por target em operação que o canal/ManyChat comprovadamente aceite; não assumir que `sendContent` de `/fb` prova WhatsApp.
- O backend direto Meta continua fora do caminho Marketing conforme ADR-009.

### 5.4 Sandbox ainda obrigatório antes do piloto

O ensaio autorizado precisa provar, com target sintético/verificado e sem cliente real:

1. resposta exata de success/error/429/5xx;
2. se há provider ref, callback ou consulta utilizável;
3. timeout antes/depois do efeito;
4. dois commands concorrentes para o mesmo subscriber;
5. isolamento de custom fields e flow version;
6. limite real por bot e comportamento de `Retry-After`;
7. redaction de request/response/log.

Sem essa prova, WhatsApp Marketing real permanece bloqueado. Esta decisão negativa é suficiente para construir fake provider, ledger e `unknown` sem alegar capacidade inexistente.

## 6. G-H04 — RBAC, blast, step-up, quotas e emergency revoke

### 6.1 Capabilities aprovadas

| Codename conceitual | Responsabilidade |
|---|---|
| `view_marketing` | board/history/result agregado |
| `edit_marketing_campaigns` | criar/editar draft e regra |
| `edit_marketing_templates` | criar/editar template/copy |
| `preview_marketing_audience` | preview e counts protegidos |
| `approve_marketing_announcements` | aprovar/rejeitar snapshot |
| `publish_marketing_announcements` | now/schedule/cancel |
| `fire_marketing_campaigns` | fire manual |
| `retry_failed_marketing` | somente `failed_retryable` |
| `reconcile_unknown_marketing` | reconciliar/escalonar `unknown`; não reenviar |
| `send_marketing_test` | sandbox/allowlist, max 1 |
| `configure_marketing_platforms` | flow/readiness/config via CAS |
| `audit_marketing` | audit/receipts sem comando |
| `access_marketing_delivery_pii` | break-glass purpose-bound |
| `freeze_marketing` | bloquear novos efeitos imediatamente |

Nomes técnicos finais podem se ajustar à convenção Django, mas nenhuma capability pode voltar a `manage_campaigns` monolítica.

### 6.2 Personas e separação

| Persona | Grants iniciais |
|---|---|
| Observer | view |
| Editor | view, edit campaigns/templates, preview, test sandbox |
| Approver | view, preview, approve/reject |
| Publisher | view, preview, approve, publish/fire/cancel, retry failed |
| Platform Owner | view, platform config/test, reconcile/escalate unknown |
| Auditor/DPO | view, audit; PII somente break-glass |
| Security/Ops | view, freeze; sem edição de copy por herança |

- Publisher não herda Platform Owner nem Auditor/DPO.
- Auditor não recebe command operacional.
- O mesmo usuário pode possuir mais de um grupo inicialmente, mas nunca pode satisfazer sozinho um dual control.
- `Gerente` deixa de receber efeitos perigosos por herança. Na migration, recebe somente view/edit/preview em modo audit; grupos perigosos nascem vazios.
- Antes de enforcement/piloto, o proprietário atribui pessoas nominais aos grupos. Superuser não é caminho operacional normal.

### 6.3 Confirmação proporcional

| Blast/ação | Confirmação |
|---|---|
| 10–49 recipients, scheduled | resumo explícito |
| qualquer `publish now`/fire; ou 50–499 | recent-auth ≤15 min + digitar `PUBLICAR <count>` |
| 500–1.999 | TOTP + typed confirmation + segundo ator com capability de Approver/Publisher |
| 2.000–5.000 | dual control + TOTP + somente scheduled com antecedência mínima de 15 min + aviso ao on-call |
| acima de 5.000 | bloqueado; nova decisão G-H04/G-H08 |
| config de platform/flow | TOTP + CAS + summary; em produção, segundo Platform Owner |
| reconcile de unknown | TOTP; consulta/escalation sem efeito |
| retry de unknown | proibido por G-H03 v1 |

Cancel/reject exige reason. Cancelar declara targets ainda evitados e efeitos já irreversíveis.

### 6.4 Step-up e tokens

- Senha recente pode fazer step-up até 499 recipients; TOTP é obrigatório a partir de 500, platform config e break-glass.
- Sessão originada apenas por PIN/crachá pode editar/preview, mas não causar efeito externo antes de password/TOTP step-up.
- Step-up vale 15 minutos e é invalidado por logout, troca de usuário, troca de senha, remoção de capability, risk event ou freeze.
- Confirmation token é server-generated, one-use, TTL 5 min e vinculado a actor, action, resource, base version, artifact hash, audience hash/count, platforms, schedule e consequence.
- Idempotency receipt permanece consultável por no mínimo 180 dias. Mesma key+payload retorna o receipt; mesma key+payload diferente responde 409.

As recomendações seguem autorização transacional server-side, token único e curto, reautenticação para ação sensível e default deny:

- https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- https://pages.nist.gov/800-63-3/sp800-63b.html

### 6.5 Quotas e throttle iniciais

- login existente: manter 5/min por username e 30/min por IP;
- audience preview: 30/min por user e 120/min por shop;
- command perigoso: 10/min por user, 30/min por shop;
- fire: 3/h por user e 10/dia por shop;
- test-send: 5/h por user, 20/dia por shop, max 1 target, allowlist/sandbox verificado;
- targets externos totais: 5.000/dia por shop até G-H08 recalibrar;
- 429 sempre traz `Retry-After` e preserva draft/contexto.

### 6.6 Emergency freeze

- Freeze é estado persistido/consultado em cada POST perigoso e imediatamente antes de claim/network call; não depende de deploy.
- Ativação exige `freeze_marketing`, reason e audit; pode ser imediata por um ator.
- Desativação exige segundo ator Security/Ops, TOTP e reconciliação dos commands in-flight.
- Freeze cancela/suprime apenas trabalho ainda reversível; `accepted/unknown` é preservado e reconciliado, nunca reenviado.
- Revogação de permission invalida confirmation token já aberto e é reavaliada no submit.

## 7. G-H05 — Produto, omotenashi e discovery

### 7.1 Defaults provisórios

- Default seguro é revisar e **agendar no próximo horário permitido**; `Publicar agora` é uma Action separada, nunca default.
- Sempre mostrar data, hora, `America/Sao_Paulo` ou timezone do recipient, quiet-hours outcome e expiry.
- Draft pode ser editado até approval. Depois do snapshot, conteúdo é imutável; correção cria nova versão/command.
- Cancel alcança somente outbox/targets ainda não iniciados; a tela mostra quantos foram evitados e quantos são irreversíveis.
- Alertas no sino: privacy/duplicate/unknown/partial/stuck/readiness que bloqueia envio próximo/aprovação pendente. Informativo fica no objeto/histórico.
- Primary Action sempre aponta para o problema e chega pré-preenchida.

### 7.2 Critério do estudo com 5–8 gestores

Executar em ambiente local/staging seeded, sem destinatário real, as nove tarefas da seção 16 do plano. Aprovação final exige:

- pelo menos 80% dos participantes concluindo cada caso comum sem ajuda;
- mediana dentro do budget de toques/telas/digitação/espera;
- zero perda de draft, zero ação perigosa acidental e zero interpretação de `accepted/partial/unknown` como entrega total;
- 100% localizando versão, audiência, horário, plataformas e próxima ação no encerramento;
- exceção de budget documentada por tarefa, com motivo de segurança e aprovação de Produto.

Até isso ocorrer, UI nova é provisional/flagged; não é chamada definitiva nem pronta para piloto.

## 8. G-H06 — Marca e IA

- `marketing_ai_assist_v2` default off.
- IA recebe somente facts canônicos allowlisted, sem customer, membership, phone, prompt secreto ou credencial.
- Output permitido: `body`, `hashtags`, `used_fact_ids`, warnings e hashes/version refs.
- IA não escolhe preço, estoque, desconto, validade, URL, audience, schedule, platform, template ou flow.
- Claim factual sem fact ID vigente bloqueia a sugestão.
- Proibidos falsa escassez, urgência enganosa, preço/promoção não vigente, conteúdo discriminatório/ofensivo e URL gerada.
- `Aceitar sugestão` só altera draft e mostra diff; approval é ação humana posterior. `requires_approval=false` nunca bypassa IA.
- Timeout/erro mantém o texto anterior intacto.
- Provider só pode entrar em piloto após contrato de retenção/no-training/transferência aprovado por Segurança/Privacidade.
- Red-team PT-BR mínimo: 100 casos cobrindo injection, facts conflitantes, virada de data, Unicode, URL, discriminação e false urgency; zero critical escape.

## 9. G-H07 — ownership do Admin

Decisão recomendada:

- Nuxt Marketing é o único cockpit e o único caminho para commands.
- Campaign, template, platform config, approval, fire, cancel, retry e reconcile não são editáveis no Admin.
- Admin pode oferecer somente audit read-only de consent events/current state, command receipts, snapshots, delivery aggregates e audit events, com PII protegida/oculta.
- Configuração de voz da marca que já pertence ao Shop global permanece no owner global; não se cria cópia Marketing.
- Links do Admin apontam à rota/âncora exata no Nuxt.
- Nenhum `list_editable`, raw JSON perigoso, action de envio ou browse de cohort.
- Toda UI Admin usa Unfold canônico e passa `make admin`; sem console custom ou dual write.

Esta escolha fecha o ownership sem exigir nova superfície editável no Admin.

## 10. G-H08 — SLO, capacidade e on-call

### 10.1 Objetivos iniciais

Adotar os SLOs da seção 17 do plano, com estes budgets executáveis:

| Caminho | Budget inicial |
|---|---|
| Board Projection | p95 ≤500 ms, ≤300 KB, ≤25 queries |
| Audience preview 100k candidates | p95 ≤2 s, ≤30 queries, sem query global fora do cohort |
| Command acceptance | p95 ≤1 s; transaction DB p95 ≤500 ms |
| Immediate dispatch | primeiro target queued p95 ≤10 s |
| Scheduled dispatch | lag p95 ≤30 s |
| Ledger→Projection | ≤10 s; stale visível após 30 s |
| Worker | chunk inicial 100, concorrência 4, lease 60 s; recalibrar por teste |
| ManyChat | cap 8 targets/s/bot até sandbox |
| Duplicado confirmado / pós-opt-out / pós-expiry | 0, fora de error budget |

Carga pré-piloto: 100k candidates, 10k targets, history 10k, callback burst e dois workers; sustentar 2× o hard cap por teste sem liberar 2× em runtime.

### 10.2 Owners iniciais por função

- Ops: command/outbox/partial/stuck e runbooks.
- SRE: DB/queue/latency/capacity/alerts.
- Platform Owner: ManyChat/readiness/unknown.
- DPO/Security: consent violation, PII e freeze.
- Product: freshness/copy/budgets do operador.

Pessoas nominais, rota de paging e backup devem ser registradas antes do piloto. O pacote aprova a função, não inventa nomes.

Baseline de 7–14 dias em ambiente autorizado, dashboards, alertas e execução dos oito runbooks por operador não autor continuam condições de fechamento de G-H08 antes do piloto.

## 11. G-H09 — release por estágio

Não existe autorização permanente de rollout. Cada fase 1–7 precisa de um registro separado contendo:

- commit/image e ambiente exatos;
- migrations/estimate/backup/rehearsal;
- flags, default, owner, expiry e failsafe;
- testes, smoke read-only/sintético, dashboards e alertas;
- commands in-flight e resultado da reconciliação;
- janela, on-call e rollback ensaiado;
- critério go/no-go e assinatura do Release Manager + owners aplicáveis.

Progressão continua 5%→25%→50%→100%, nunca automática. Qualquer P0, mismatch, PII, unknown sem owner, readiness stale ou rollback não ensaiado congela o próximo estágio.

## 12. G-H10 — produção

Este pacote **não** autoriza produção. Cada write/deploy/send requer confirmação explícita e contextual no formato:

```text
AUTORIZO G-H10
ambiente/alvo: <exato>
janela: <início/fim/timezone>
commit/imagem: <sha/digest>
comando/ação: <exato>
audience/blast/canal: <exato>
flags/migrations: <exato>
on-call: <nome/contato operacional>
rollback: <runbook + comando/flag>
```

Autorização genérica, antiga, sem alvo ou sem janela é inválida. Preview, teste automatizado e smoke nunca usam destinatário real.

## 13. Declaração única para confirmação humana

Para aprovar este pacote sem reescrever suas decisões, responder exatamente ou de forma semanticamente equivalente:

> **CONFIRMO o pacote `marketing-human-gates.v1` como proprietário/decisor responsável e autorizo sua implementação exclusivamente local, em worktree/branch isolados e flags seguras, sem deploy, escrita em produção, credenciais externas, sandbox externo ou envios reais. Reconheço que G-H05/G-H06/G-H08 ainda exigem evidência humana/técnica antes de piloto e que G-H09/G-H10 exigirão autorizações futuras específicas.**

Após a confirmação:

- G-H01–04 ficam aprovados para implementação técnica conservadora;
- G-H07 fica aprovado quanto ao ownership Admin/Nuxt;
- G-H05/06/08 ficam com policy aprovada e evidência de saída ainda pendente;
- G-H09/10 permanecem necessariamente fechados até cada autorização contextual futura.
