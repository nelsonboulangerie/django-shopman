# Marketing — plano de excelência irreprimível

**Data da auditoria:** 2026-09-08

**Escopo primário:** `surfaces/marketing-nuxt` e toda a cadeia de leitura, decisão, audiência, consentimento, dispatch, entrega, Admin, infraestrutura e observabilidade que a superfície aciona

**Baseline auditada:** branch `codex/shopman-backstage-prod-hardening`, HEAD `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`

**Natureza:** plano executável; nenhum código de produto, teste, configuração, migration ou documento preexistente foi alterado nesta auditoria

**Estado inicial do plano:** achados verificados; implementação não iniciada

> Resposta operacional: o Marketing ainda não é seguro para ser tratado como um comando de comunicação de efeito único. O caminho para excelência exige primeiro tornar consentimento, aprovação, snapshot, dispatch e resultado invariantes transacionais; depois fazer Projection + Actions e a interface exprimirem a mesma verdade; por fim provar isso sob concorrência, falha parcial, acessibilidade, carga e rollout controlado.

## 0. Contrato de execução para o futuro agente

### Instrução canônica de delegação

> **Execute `MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` por work package, em worktree isolado, sem reduzir gates; confirme o código atual, faça reproduzir → contratar → implementar verticalmente → provar → registrar e pare em todo gate humano ou de produção.**

Essa frase delega execução, não autoriza deploy, escrita em produção, envio real, alteração de credenciais, merge, push ou abertura de PR.

### Leitura e verificação obrigatórias

Antes da primeira alteração, o executor deve:

1. ler este arquivo integralmente, inclusive dependências, gates, rollback e Definition of Done;
2. localizar e ler todos os `AGENTS.md` aplicáveis ao caminho que editará;
3. ler as skills acionadas pelo trabalho; qualquer mudança no Admin exige `unfold-admin-canonical` e seus três cânones;
4. reler ADR-009, ADR-012, ADR-014, ADR-016, ADR-019, ADR-020 e ADR-021, `docs/engineering/nuxt_design_system.md`, `docs/engineering/backstage-design-system.md`, o README do `operator-kit` e os contratos de projections;
5. tratar planos e relatórios antigos apenas como hipóteses; confirmar cada achado no código e testes do HEAD da sua própria branch;
6. registrar branch, HEAD, worktree, comandos e resultados num log exclusivo da sessão;
7. comparar este baseline com o código atual. Achado que já tenha sido resolvido vira prova de regressão/fechamento, não uma mudança repetida.

### Ciclo obrigatório por fatia vertical

Para cada item do backlog:

1. **Reproduzir:** criar a menor reprodução observável, incluindo interleaving quando houver concorrência.
2. **Contratar:** fixar o comportamento em schema, máquina de estados, permissão e teste que falha pelo motivo correto.
3. **Implementar verticalmente:** model/service/handler/API/projection/Actions/UI/telemetria, sem deixar estados intermediários ambíguos.
4. **Provar:** executar testes direcionados, gates de regressão e teste de falha/rollback pertinente.
5. **Registrar:** acrescentar ao log a evidência, decisões, migration, flags, métricas e dívida deliberadamente restante.

Um teste verde não substitui contrato. Um mock do adapter não prova efeito no provedor. Uma resposta `2xx` não prova entrega. Uma fila aceita não prova publicação. O executor deve distinguir essas quatro certezas na interface e na telemetria.

### Estados de conclusão

- **Implementação técnica concluída:** código, migrations, contratos gerados, testes e runbooks da fatia passaram localmente; flags continuam seguras e nenhuma produção foi alterada.
- **Pronto para piloto:** implementação técnica concluída, revisão de segurança/privacidade/produto aprovada, dashboards e alarmes ativos no ambiente autorizado, ensaio de rollback realizado e grupo piloto definido.
- **Rollout concluído:** piloto cumpriu SLO e invariantes, expansão foi autorizada e monitorada, legado foi desligado de modo reversível e reconciliação não encontrou efeitos duplicados nem consentimento violado.
- **Plano concluído:** todos os P0/P1 e P2 aceitos como necessários estão em rollout concluído; decisões e discoveries restantes têm owner/prazo; documentação representa o sistema real; a Definition of Done da seção 22 foi assinada.

Não promover um estado por conveniência. Em especial, “implementação técnica concluída” não significa “pronto para piloto”.

### Convivência multiagente obrigatória

O executor deve assumir que há outras sessões escrevendo no repositório.

1. Antes de escrever, executar e registrar `git status --short --branch`, `git rev-parse HEAD` e `git worktree list --porcelain`.
2. Criar um worktree exclusivo e branch exclusiva com prefixo `codex/` por sessão. Não implementar no checkout compartilhado sujo.
3. Preservar absolutamente toda mudança rastreada e não rastreada de terceiros. Não mover, reformatar, apagar, adicionar ao index nem “corrigir” trabalho alheio.
4. Manter log exclusivo, por exemplo `docs/reports/execution/marketing-<WP>-<session-id>.md`, criado apenas quando a fase de execução autorizar documentação.
5. Fazer patches pequenos; imediatamente antes de cada edição, reler o arquivo e revalidar o trecho-alvo.
6. São proibidos `git reset --hard`, `git clean`, `git restore`, `git checkout --` e stash abrangente.
7. São proibidos formatter, codemod, gerador ou atualização mecânica repo-wide. Formatar apenas os arquivos efetivamente tocados.
8. Nunca usar `git add -A`; adicionar caminhos explícitos depois de revisar `git diff --check`, `git diff --stat` e `git diff -- <caminho>`.
9. Coordenar antes de tocar migrations, schemas/clients gerados, lockfiles, configs compartilhadas, CI, documentação central e `operator-kit`.
10. Fazer commits locais pequenos e coesos, um comportamento verificável por commit. Não fazer merge, push ou PR automático.
11. Entregar handoff com branch, worktree, commits, migrations, flags, comandos/testes, resultados, riscos, decisões pendentes e instruções exatas de integração/rollback.
12. Um responsável de integração deve resolver conflitos semanticamente, reler os dois lados e repetir gates; nunca escolher mecanicamente “ours/theirs”.
13. Se não houver isolamento possível, continuar somente em leitura até obter coordenação explícita.

O checkout desta auditoria já estava sujo por arquivos não rastreados de outras sessões; eles foram preservados. Isso torna as regras acima um risco atual, não uma precaução abstrata.

### Gates que nenhum executor pode reduzir

- Nenhuma escrita ou deploy em produção sem autorização humana explícita para o alvo e a janela.
- Nenhum destinatário real em teste automatizado, preview ou ensaio.
- Nenhuma troca de flow/template, credencial ou backend WhatsApp sem owner da plataforma e plano de reversão.
- Nenhuma expansão de audiência ou mudança de base legal sem aprovação de Privacidade/Jurídico e Produto.
- Nenhuma promessa de “exactly once” externo sem capacidade comprovada do provedor; timeout ambíguo deve permanecer `unknown`, não ser repetido às cegas.
- Nenhum envio assistido por IA sem revisão humana até que Produto, Marca/Jurídico e Segurança aprovem critérios mensuráveis para eventual automação.
- Nenhuma remoção de coluna/tabela/caminho legado antes de reconciliação, janela de rollback e aprovação de Operações.
- `make admin` é gate obrigatório de toda mudança no Admin/Unfold; não pode ser substituído por screenshot ou teste isolado.

## 1. Resultado operacional pretendido

O gestor deve conseguir sair de “há uma oportunidade pertinente” para “a comunicação certa foi decidida e seu resultado é conhecido” sem procurar contexto em outra tela, sem reconstruir audiência mentalmente e sem temer duplo envio. O sistema deve:

- explicar por que a campanha existe, quais fatos canônicos sustentam a mensagem e qual decisão é recomendada;
- mostrar exatamente conteúdo, variante, mídia, link, audiência elegível/excluída, timezone, janela e consequência antes da aprovação;
- preservar rascunho e contexto em navegação, erro, conflito, expiração de sessão e retomada;
- aceitar cada comando perigoso uma vez, publicar exatamente a versão aprovada e impedir que retry ou worker concorrente repita um efeito já conhecido;
- revalidar supressão e revogação imediatamente antes do envio, sem adicionar pessoas que não estavam no snapshot aprovado;
- mostrar estados por plataforma — planejado, enfileirado, enviado ao provedor, confirmado, falhou, desconhecido, cancelado, expirado — sem chamar parcial de sucesso total;
- oferecer no próprio alerta ou resultado a próxima ação autorizada, pré-preenchida e idempotente;
- manter uma trilha explicável de ator, motivo, versão, fatos, template, audiência, horário, plataforma e tentativa, sem PII em logs/projections;
- continuar funcional e honesto quando IA, SSE, ManyChat, catálogo, audience source ou um canal estiverem indisponíveis;
- manter o caso comum curto, mas tornar exceções claras e recuperáveis.

Indicadores do resultado: zero violações de opt-out; zero duplicações conhecidas; zero mutação sem ator/idempotency key; 100% dos efeitos derivados de snapshot aprovado; 100% das plataformas com resultado explícito; 100% das ações perigosas autorizadas e confirmadas; nenhum estado de UI que transforme `403`, outage ou parcial em vazio, inexistente ou sucesso.

## 2. Definição explícita de omotenashi

Aqui, **omotenashi** é o sistema antecipar trabalho e risco legítimos sem retirar agência do gestor. Não é animação, maquiagem ou uma tela “bonita”. É:

- trazer oferta, validade, disponibilidade, link, imagem aprovada, readiness, timezone, quiet hours e audiência explicada antes que o gestor precise procurar;
- recomendar uma ação primária e explicar por que outras estão bloqueadas;
- reduzir a operação comum a uma revisão consciente e uma confirmação, não a uma sequência de telas;
- impedir preventivamente horário passado, promoção que vencerá antes do dispatch, canal sem readiness, audiência zero/degradada, limite de plataforma excedido e conteúdo factual divergente;
- guardar silenciosamente um rascunho privado, mostrar quando foi salvo, restaurá-lo após sessão expirada e nunca misturá-lo à versão de outra pessoa;
- dizer “ainda não sabemos se o provedor aceitou” quando esse é o fato, preservando o comando para reconciliação segura;
- reconciliar objeto e alerta juntos; o sino não desaparece porque foi visto, mas porque a condição foi resolvida;
- exibir o mínimo de métricas operacionais necessário para decidir/reparar, sem virar BI, CRM, social inbox ou Hootsuite.

Pergunta de aceite de toda UI: **qual memória, conferência externa, redigitação, toque, espera ou incerteza previsível esta fatia removeu — e como o teste demonstra isso?**

## 3. Baseline e evidências verificadas

### 3.1 Método e limites

A auditoria inventariou o repositório real, leu o Nuxt completo e a cadeia Django/adapters/Guestman/Admin/infra relevante, confrontou ADRs e cânones, executou baseline e inspecionou o host descoberto na configuração de deploy. Planos antigos serviram somente para formular perguntas. O app vivo foi acessado anonimamente e apenas em leitura; não foram usados usuário, senha, cookie de sessão, telefone ou destinatário real.

Rótulos usados neste plano:

- **Lacuna real:** comportamento ausente ou contraditório confirmado em código/UI/teste.
- **Melhoria recomendada:** comportamento atual é válido, mas tem custo/risco comprovável que justifica evolução.
- **Discovery:** depende de observar gestores reais; não autoriza implementação definitiva.
- **Decisão de negócio:** há mais de uma política legítima; owner humano deve escolher antes do corte.
- **Hipótese:** vetor plausível cuja materialização depende de adapter/provedor/carga e exige reprodução.

### 3.2 Estado do repositório antes da escrita

```text
branch: codex/shopman-backstage-prod-hardening
HEAD:   b589e22c5c6963e79c4bf735b79eaf928b9ae6f7
status: havia .alpha-tmp/ e planos/relatórios não rastreados de terceiros
worktrees: múltiplos worktrees Codex/Claude ativos e preservados
arquivo deste plano: inexistente e, portanto, criado sem sobrescrita
```

Nenhuma dessas mudanças preexistentes pertence a esta auditoria.

### 3.3 Baseline executada

| Área | Comando/gate | Resultado verificado | Limite da evidência |
|---|---|---:|---|
| Frontend | `npm test -- --reporter=dot` em `surfaces/marketing-nuxt` | **5 arquivos, 92 testes passaram** | Muitos warnings Vue: prop obrigatória `platformLabels` ausente e `NuxtLink`/`AnnouncementPreview` não resolvidos; harness permite ruído estrutural. |
| Frontend | `npm run lint` | passou | Não cobre UX, contrato HTTP, fluxo real ou a11y. |
| Frontend | `npm run typecheck` | passou | Tipos são espelho manual e não detectam drift de payload. |
| Frontend | `npm run build` | passou | Build reportou Nuxt 4.5.0; não é smoke autenticado nem prova de deploy. |
| Dependências | `npm ls nuxt --depth=0` | **falhou `ELSPROBLEMS`**: instalado `nuxt@4.5.0`, inválido para `^4.5.2` | Há drift local/lock/install que a CI precisa tornar determinístico. |
| E2E frontend | busca por config/script Playwright e scripts `e2e` | **não existe** | Nenhum E2E de navegador, a11y ou screenshot da superfície. |
| Backend focado | `.venv/bin/pytest -q` nos 17 módulos de API Marketing, notifications, audience, campaign, schedule, handlers, delivery, ManyChat, WhatsApp, consent e integração | **433 passaram em 23,05 s** | Não há interleavings concorrentes, efeito externo real, caos, carga nem contrato gerado da superfície. |
| Admin/Unfold | `make admin` | checks canônicos passaram; **229 testes passaram em 35,47 s** | Marketing operacional está deliberadamente fora do Admin; falta decidir/aferir a superfície de configuração/auditoria. |

Os testes verdes cristalizam ao menos três políticas inadequadas: action de notificação ausente cai para aprovação, assinatura de alerta pode sobrepor consentimento global e audiência é re-resolvida no dispatch. Esses testes devem ser substituídos por contratos desejados, não apenas preservados.

### 3.4 App vivo, somente leitura

Host canônico descoberto em `.do/app.alpha-subdomains.yaml`: `https://mkt.boulangerie.com.br`.

Foram inspecionados desktop `1280×720` e mobile `390×844`, DOM acessível, foco, overflow, console, requests e as rotas `/`, `/campaigns`, `/templates`, `/platforms`, `/history` e `/announcements/1`.

| Evidência viva | Resultado |
|---|---|
| Documento e rotas anônimas | HTML `200`; o login é overlay, enquanto as páginas e seus fetches montam atrás dele. |
| API BFF `/api/v1/backstage/marketing/` | `403`, corretamente sem dados. A UI atrás do overlay converte isso em falha, vazio ou “não encontrado/expirou/foi decidido” conforme a rota. |
| SSE `/sse/notifications` anônimo | `404`, coerente com não expor/reconectar canal pessoal a anônimo. |
| Foco/login | foco permaneceu em `BODY`; overlay não apresentou `role="dialog"`, `aria-modal`, nome acessível, trap/inert. Controles do fundo permanecem alcançáveis. |
| Touch | vários botões mediram aproximadamente 20–36 px de altura; login, 42 px. O cânone pede alvo padrão mínimo de 44×44 px. |
| Layout | sem overflow horizontal do documento nos estados anônimos testados; estados autenticados e conteúdo extremo permanecem sem prova. |
| Linguagem | `lang="pt-BR"`. |
| Console | nenhum warning/error capturado na inspeção anônima. |
| Root Nuxt | `cache-control: private`, Cloudflare `BYPASS`, `x-powered-by: Nuxt`; faltaram CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, proteção de frame e COOP. |
| BFF `403` | também perdeu headers de segurança/metadados do Django. |
| API Django direta `403` | apresentou CSP, HSTS, frame `DENY`, `nosniff`, Referrer-Policy, COOP, `Vary` e versão de API. A diferença localiza o gap no envelope Nuxt/BFF. |

Nenhuma mutação viva foi feita: não houve login, approve, reject, publish, fire, send-test, rewrite, seleção de template, edição ou submit.

### 3.5 Contratos e arquitetura confrontados

- ADR-012 requer Projection + Actions backend-resolvidas; Marketing não entrega `actions`.
- ADR-014 separa dados puros de apresentação; a projection atual entrega `status_label`, `trigger_label`, `platform_label`, `schedule_label` e reach alert já redigido em português.
- ADR-016 define SSE como invalidação e refetch como verdade; o board segue a ideia, mas não torna conexão degradada observável e mantém polling de 60 s mesmo oculto.
- ADR-019/020 preservam promoção/oferta/preço/estoque/link no orquestrador: campanha anuncia, não vende. Esse corte deve permanecer.
- ADR-021 limita Marketing a métricas ligadas à ação/reparo; não deve duplicar BI.
- ADR-009 fixa WhatsApp em ManyChat; o adapter de campanha ainda admite fallback direto `whatsapp`.
- `docs/reference/projection-contracts.md` não inclui snapshot Marketing e os tipos TS são manuais, ao contrário de surfaces mais maduras.
- `docs/reference/surfaces.md`, `docs/engineering/backstage-design-system.md`, README do `operator-kit` e `surfaces/marketing-nuxt/README.md` divergem da topologia e rotas atuais.
- A exceção Nuxt para operação Marketing é legítima; Admin/Unfold deve servir somente configuração autorizada e auditoria, sem console paralelo.

### 3.6 Evidências de código de maior impacto

| Cadeia | Evidência confirmada |
|---|---|
| Consentimento | `shopman/shop/services/audience.py::_filter_opted_in` mantém qualquer recipient com reason `alerts` antes de considerar `CommunicationConsent`; um opt-out global posterior pode ser ignorado. |
| Auditabilidade de consentimento | `packages/guestman/.../consent/models.py` mantém uma linha mutável por customer/channel; `update_or_create` perde histórico de texto/base/versão/revogação. |
| Aprovação | API salva conteúdo e depois chama approve em operações separadas; service muda estado sem `select_for_update`, versão ou idempotency key. |
| Crash window | status `APPROVED`/`PUBLISHING` pode ser persistido antes de criar/enfileirar todas as directives; retry então pode retornar cedo e deixar anúncio preso. |
| Snapshot | handlers recarregam conteúdo/campanha mutáveis; público é re-resolvido no envio. Não existe snapshot imutável da aprovação. |
| Resultado | `results` JSON é read-modify-write sem lock; waves concorrentes podem sobrescrever ou contar duas vezes. `partial` e `pending_manual` acabam apresentados como publicados. |
| Delivery | WhatsApp itera uma wave sincronicamente; falha individual é absorvida, crash pode repetir destinatários e timeout externo ambíguo não tem estado próprio. |
| Preferred hour | queues usam nomes como `vip@9`/`all@9`, mas handler só seleciona `vip`, `general`, `all`; waves horárias podem resolver vazias. |
| Variante | `shopman/shop/services/campaign.py::_platform_content` faz `{**variant, "body": content["body"]}` e apaga o body específico. |
| Publicar agora | `AnnouncementCard.vue` não envia `publish_now: true`; backend pode respeitar schedule quando o CTA promete envio imediato. |
| Edição de regra | `CampaignForm.vue` reconstrói subconjunto de `audience_rules`, descartando silenciosamente match, tiers, tags, RFM, churn, aniversário, SKUs/collections e preferências existentes. |
| Preview | debounce sem abort/epoch permite resposta velha sobrescrever nova; preview não usa o mesmo artefato de dispatch e silencia falha. |
| Test send | endpoint aceita telefone arbitrário com permissão ampla, sem idempotência/throttle/allowlist; log inclui recipient em claro e retorno pode carregar detalhe do vendor. |
| RBAC | leitura, edição, aprovação, fire, teste externo e integração compartilham `shop.manage_campaigns`. |
| Actions | backend não resolve Actions; frontend infere botões/permissão/readiness e deep-links genéricos. |
| Métricas | `audience_reached` é audiência planejada, `failed_today` não está limitado ao dia e performance presume alcance público igual ao público inteiro. |
| Readiness | validação/lista de flow diverge em `is_active`; outage e lista vazia são achatadas; POST pode aceitar ref arbitrária durante outage. |
| IA | prompt incorpora instrução administrativa/contexto sem trust boundary, usa fatos possivelmente stale/base price e pode auto-despachar quando `requires_approval=false`; não há schema/claim checker/moderação/audit do modelo/prompt. |
| Imagem/link | URL livre não tem política de scheme/host/proxy; tracking externo é risco real e fetch server-side pelo provedor é hipótese de SSRF a provar. |
| Sessão | `app.vue` monta `NuxtPage` atrás do login; utilitário compartilhado local classifica `401` e `403` igualmente como expiração, embora operator-kit distinga forbidden. |
| Infra | uma instância Nuxt de 0,5 GB tem health check apenas em `/`; CI da surface roda test/typecheck, mas não lint/build/E2E/a11y/security/visual. |

## 4. Decisões arquiteturais e não objetivos

### 4.1 Decisões propostas

| ID | Decisão | Motivo | Gate |
|---|---|---|---|
| DA-01 | Manter Marketing Nuxt como cockpit operacional dedicado. Admin/Unfold fica com configuração governada e auditoria read-only/imutável, nunca um segundo cockpit. | Evita dois comandos concorrentes e respeita o corte atual/cânones. | Produto + Operações devem escolher quais poucos objetos continuam editáveis no Admin. |
| DA-02 | Criar um contrato canônico `MarketingProjection` puro e gerado para TypeScript, com `actions[]` backend-resolvidas e `version`/`etag`. | Elimina drift manual e lógica de autoridade/readiness no browser; alinha ADR-012/014. | Arquitetura de Backstage aprova schema e política de compatibilidade. |
| DA-03 | Toda decisão perigosa vira `CommandReceipt` idempotente e máquina de estados com CAS/lock, ator, motivo, base version e confirmação. | Fecha duplo toque, replay, corrida approve/edit/reject/schedule e ambiguidade de HTTP. | Segurança/Produto definem TTL e escopo das keys. |
| DA-04 | Aprovação congela `ApprovedAnnouncementSnapshot`: conteúdo/variantes/mídia/link/fatos/template renderizado/config de horário/plataformas e regra de targeting; o dispatch só lê esse snapshot. | Garante “aprovado = despachado” e auditabilidade após mudanças. | Privacidade define retenção e criptografia. |
| DA-05 | Congelar cohort elegível em armazenamento protegido separado da projection, e aplicar apenas supressões/revogações novamente no envio; nunca adicionar novo recipient após aprovação. | Concilia audiência exata com revogação tardia e evita expor listas no Announcement/API. | DPO/Jurídico decide base, retenção, acesso e apagamento. |
| DA-06 | Usar outbox/directive transacional e `DeliveryTarget`/`DeliveryAttempt` por plataforma/recipient com unique key. Resultado agregado é derivado, não JSON fonte de verdade. | Permite efeito-uma-vez interno, retry seletivo e reconciliação. | Dados/Operações aprovam volume e retenção. |
| DA-07 | Não prometer exactly-once no provedor. Se não houver idempotência/receipt, timeout vira `unknown`; retry de `unknown` exige reconciliação ou gate humano. | Sistemas externos não permitem garantia maior que sua API. | Owner ManyChat/Meta deve documentar capacidades reais. |
| DA-08 | Consentimento explícito global tem precedência sobre assinatura de SKU; assinatura é finalidade específica, revogável e comprovável. | Evita enviar contra opt-out posterior e torna propósito auditável. | Jurídico/Privacidade confirma texto e transição de legados. |
| DA-09 | Preview e dispatch consomem o mesmo `ResolvedDispatchArtifact`; preview faz redaction, nunca uma renderização paralela. | Elimina divergência de variante, limite, link, preço e horário. | Produto define nível de amostra sem expor pessoas. |
| DA-10 | IA produz sugestão estruturada e diffs, nunca fatos. Fatos vêm do orquestrador e toda publicação mantém revisão humana até gate específico. | Respeita ADR-019/020 e reduz claim/injection. | Marca/Jurídico, Segurança e Produto. |
| DA-11 | Readiness é uma capability por plataforma com `ready/degraded/blocked/unknown`, prova/freshness e Actions de reparo. | “Lista vazia” não pode significar outage nem autorizar configuração cega. | Owners dos canais. |
| DA-12 | Métricas ficam restritas a decidir/reparar: fila, atraso, parcial, falha, unknown, opt-out suprimido, retry e resolução. | Respeita ADR-021; performance comercial segue no BI. | Produto + BI. |

### 4.2 Não objetivos

- Não transformar Marketing em Hootsuite, social inbox, CRM, CDP, BI ou editor completo de flow ManyChat.
- Não mover ownership de promoção, preço, estoque, validade, disponibilidade ou link para campanha.
- Não armazenar lista de destinatários em JSON/projection/log; a proteção interna de cohort/delivery tem acesso e retenção próprios.
- Não incorporar credenciais, erro bruto do vendor ou PII no navegador, eventos, logs ou Sentry.
- Não inventar atribuição comercial, reach confirmado ou ROI sem fonte canônica.
- Não criar console Admin artesanal nem duplicar ações operacionais do Nuxt.
- Não adicionar animação como objetivo; reduced motion e clareza têm precedência.
- Não automatizar publicação de copy gerada por IA neste plano.
- Não selecionar novo provedor ou ampliar canais sem discovery/gate de negócio.

## 5. Achados classificados por severidade

Os WPs da seção 8 contêm, para cada recomendação, comportamento-alvo, local, prova, telemetria, migração, reversão e decisão. Esta tabela é o índice de risco.

### P0 — bloquear expansão e automação

| ID | Tipo | O que está errado/por que importa | Evidência/local | Destino |
|---|---|---|---|---|
| MKT-P0-01 | Lacuna real | Subscription com reason `alerts` ignora opt-out global posterior; pode violar escolha explícita. | `services/audience.py::_filter_opted_in` | WP-01 |
| MKT-P0-02 | Lacuna real | Consentimento é estado mutável, não trilha de prova; faltam finalidade/texto/versão/origem e histórico de revogação. | package Guestman consent | WP-01 |
| MKT-P0-03 | Lacuna real | Aprovação de edição não é atômica e não tem versão/lock/idempotência; versão anterior ou concorrente pode sair. | API Marketing + `services/campaign.py` | WP-02 |
| MKT-P0-04 | Lacuna real | Snapshot aprovado não existe; conteúdo, template e cohort podem mudar até o handler. | models/service/handlers | WP-02/WP-03 |
| MKT-P0-05 | Lacuna real | Crash entre status e enqueue, workers concorrentes e retry precoce deixam anúncio preso ou repetem efeito. | dispatch/handlers/schedule | WP-02/WP-03 |
| MKT-P0-06 | Lacuna real | Não há ledger por recipient/plataforma nem idempotência externa; crash/timeout/retry pode duplicar WhatsApp/publicação. | campaign handlers/adapters | WP-03 |
| MKT-P0-07 | Lacuna real | Resultados JSON concorrentes se perdem; parcial/pending manual vira publicado, dando certeza falsa. | `_record_result`, `_record_wave`, `_settle` | WP-03 |
| MKT-P0-08 | Lacuna real | `send-test` aceita telefone arbitrário, é repetível sem throttle/idempotência e registra PII; permissão também autoriza blast. | API Marketing/adapters/log | WP-04 |
| MKT-P0-09 | Lacuna real | “Publicar agora” não envia `publish_now=true`; a interface pode prometer imediato e agendar. | `AnnouncementCard.vue` + API | WP-02/WP-07 |

### P1 — necessário antes do piloto amplo

| ID | Tipo | O que está errado/por que importa | Evidência/local | Destino |
|---|---|---|---|---|
| MKT-P1-01 | Lacuna real | Wave de preferred hour usa chave que o handler não resolve e pode enviar zero silenciosamente. | `_queue_notify`/handler | WP-03 |
| MKT-P1-02 | Lacuna real | RBAC único mistura view, edição, aprovação, blast, teste externo e integração; não há separação de deveres. | `permissions.py`, API, `setup_groups` | WP-04 |
| MKT-P1-03 | Lacuna real | Projection contém copy/labels e não Actions/version; frontend infere autorização, readiness e recuperação. | projection/types/composables/pages | WP-05 |
| MKT-P1-04 | Lacuna real | CampaignForm descarta regras existentes não representadas; salvar uma edição pode ampliar/reduzir público sem mostrar. | `CampaignForm.vue` | WP-07 |
| MKT-P1-05 | Lacuna real | Variante por plataforma é sobrescrita pelo corpo comum; preview e dispatch não compartilham artefato. | `_platform_content`, preview | WP-06 |
| MKT-P1-06 | Lacuna real | Preview pode exibir resposta stale, silencia erro e não prova limite/mídia/link/template efetivo. | `AnnouncementPreview.vue`, endpoint | WP-06 |
| MKT-P1-07 | Lacuna real | Readiness aceita estados contraditórios, conflui outage/zero e pode salvar flow arbitrária quando listagem falha. | ManyChat service/API/check | WP-06 |
| MKT-P1-08 | Lacuna real | Fallback direto Meta contradiz ADR-009 e amplia caminho não governado. | campaign delivery backend | WP-06 |
| MKT-P1-09 | Lacuna real | Notificação sem `action` aprova por default; inline approve não mostra snapshot/confirmação e siblings não reconciliam. | notifications API/model/tests | WP-08 |
| MKT-P1-10 | Lacuna real | IA aceita instrução não confiável e fatos stale, não tem output schema/claim check/moderação/audit e pode autoenviar. | prompt/rewrite/campaign rule | WP-09 |
| MKT-P1-11 | Lacuna real | App monta/faz fetch atrás do login e representa forbidden/outage como vazio/404; overlay é inacessível e fundo segue interativo. | app/login/pages + inspeção viva | WP-10 |
| MKT-P1-12 | Lacuna real | Envelope Nuxt/BFF não tem headers equivalentes ao Django; permite clickjacking e reduz defesa do operador. | headers vivos + server proxy/config | WP-10 |
| MKT-P1-13 | Lacuna real | Falta cancelamento seguro, edição antes de dispatch, selective retry e reconciliação de unknown/partial. | API/domain/UI | WP-02/WP-03/WP-07 |
| MKT-P1-14 | Lacuna real | Não há frequency cap, collision key, quiet hours explícitas ou timezone de recipient; regras concorrentes podem causar fadiga. | audience/schedule/campaign | WP-01/WP-03 |
| MKT-P1-15 | Hipótese de segurança | URL livre pode rastrear recipients e talvez induzir fetch server-side inseguro pelo provedor. | template/content/adapters; requer threat test | WP-06 |
| MKT-P1-16 | Hipótese de integridade | Custom fields persistentes ManyChat podem ser sobrescritos por campanhas concorrentes antes de o flow consumi-los. | adapter ManyChat; requer sandbox/prova do vendor | WP-03/WP-06 |

### P2 — excelência, escala e redução de esforço

| ID | Tipo | O que está errado/por que importa | Evidência/local | Destino |
|---|---|---|---|---|
| MKT-P2-01 | Lacuna real | KPIs usam público planejado como alcançado, “failed today” não é diário e histórico corta sem cursor. | projection/history | WP-05/WP-11 |
| MKT-P2-02 | Melhoria recomendada | Resolução faz scans Python/N+1 e consent query global; faltam query/latency/cardinality budgets. | audience/projection | WP-11 |
| MKT-P2-03 | Lacuna real | Draft vive na memória; navegação/sessão/conflito perdem edição e escolhas. | AnnouncementCard/forms | WP-07 |
| MKT-P2-04 | Lacuna real | Agendamento local não nomeia timezone, aceita passado como imediato e helper de expiração diverge por arredondamento. | UI/service/projection | WP-07 |
| MKT-P2-05 | Lacuna real | Controles abaixo de 44 px, foco/modal/semântica incompletos e ausência de E2E/a11y/visual. | componentes + live | WP-10/WP-12 |
| MKT-P2-06 | Lacuna real | SSE degradado não é visível, polling continua em tab oculta e health `/` não prova BFF/API/channel readiness. | composables/deploy | WP-11 |
| MKT-P2-07 | Lacuna real | Logs incluem recipient/vendor detail; faltam SLO e runbook Marketing específico. | API/adapters/log/deploy/docs | WP-11 |
| MKT-P2-08 | Lacuna real | READMEs e mapas de surfaces/operator-kit estão stale; TS contract é manual. | docs/types | WP-05/WP-12 |
| MKT-P2-09 | Decisão de negócio | Admin atual desregistra modelos operacionais e a promessa “config/audit” não se materializa; voltar a editar tudo criaria dupla autoridade. | shop/admin/curated Admin | WP-12 |
| MKT-P2-10 | Discovery | Não há evidência com gestores sobre thresholds de confirmação, default de schedule, priorização de alertas e budgets de tarefa. | validar com 5–8 sessões | WP-07/WP-12 |
| MKT-P2-11 | Lacuna real | Google Fonts é dependência externa apesar do comentário “self-hosted”; cria drift de privacidade/offline/CSP. | `nuxt.config.ts`/CSS | WP-10 |
| MKT-P2-12 | Lacuna real | Instalação local Nuxt 4.5.0 não satisfaz `^4.5.2`; pipeline não torna esse drift visível cedo. | `package.json`, lock/node_modules | WP-12 |

## 6. Sequência P0/P1/P2 e dependências

```text
Gate humano de política (consentimento, cohort, RBAC, exactly-once externo)
  ├─ WP-00 contratos e reproduções
  ├─ WP-01 consentimento/supressão/snapshot de audiência
  └─ WP-04 autoridade e contenção de abuso
           ↓
WP-02 comandos + snapshot + outbox transacional
           ↓
WP-03 ledger de delivery + reconciliação + retry seletivo
           ↓
WP-05 Projection + Actions + contrato gerado
       ├─ WP-06 conteúdo/preview/readiness
       ├─ WP-07 fluxos Nuxt e preservação de contexto
       └─ WP-08 alertas acionáveis
           ↓
WP-09 IA governada   WP-10 sessão/a11y/headers   WP-11 SLO/escala/runbooks
           └───────────────┬─────────────────────┘
                           ↓
                 WP-12 Admin/docs/CI/rollout
```

Ordem de entrega:

1. **P0 contenção:** bloquear automação/rollout amplo; fixar política de consentimento; separar permissões; tornar send-test sandboxed; contratar estados/idempotência/snapshot/ledger.
2. **P0 integridade:** migrar aprovação/dispatch para snapshot + outbox + DeliveryTarget sem remover legado; testar crashes e interleavings; derivar resultados e reconciliar.
3. **P1 contrato:** publicar Projection + Actions versionada e cliente gerado; só então migrar botões, alerts, preview e workflows.
4. **P1 operação:** faithful preview, readiness, draft/conflict, cancel/retry, notification lifecycle, IA assistiva e segurança/a11y.
5. **P2 excelência/escala:** budgets, carga, métricas, runbooks, Admin mínimo, documentação e rollout progressivo.

Não antecipar “embelezamento” de UI à integridade P0: isso cristalizaria comandos inseguros em componentes novos. WP-10 pode corrigir headers/login em paralelo porque não depende do domínio, mas não deve redesenhar ações antes de WP-05.

## 7. Catálogo de work packages

| WP | Prioridade | Resultado resumido | Depende de | Gate de saída |
|---|---|---|---|---|
| WP-00 | P0 | Reproduções adversariais e contratos de estado/schema | gates iniciais | todos os P0 reproduzem e falham pelo motivo certo |
| WP-01 | P0 | Consentimento/supressão/cohort privado e explicável | WP-00 + DPO | opt-out nunca é ultrapassado; cohort não exposto |
| WP-02 | P0 | Commands, snapshot aprovado, CAS e outbox transacional | WP-00/01 | aprovado = despachado; crash recuperável |
| WP-03 | P0 | Ledger, efeito-uma-vez, chunking, resultados e retry | WP-02 | nenhuma duplicação interna; partial/unknown explícitos |
| WP-04 | P0/P1 | RBAC, confirmação, throttle e sandbox de teste | WP-00 | blast/test/config separados e auditados |
| WP-05 | P1 | Projection + Actions pura, versionada e gerada | WP-02/03/04 | browser não inventa autoridade/resultado |
| WP-06 | P1 | Artefato único de conteúdo/preview e readiness real | WP-02/05 | preview = payload despachável; variantes preservadas |
| WP-07 | P1/P2 | Fluxos omotenashi, drafts, conflitos, schedule e recovery | WP-05/06 | caso comum curto; nenhuma perda de contexto |
| WP-08 | P1 | Alertas acionáveis reconciliados | WP-02/05 | seen ≠ ack ≠ resolved; action contextual segura |
| WP-09 | P1 | IA assistiva governada e factual | WP-06 | sugestão estruturada, auditável, sempre revisada |
| WP-10 | P1/P2 | Session gate, headers, a11y e design canônico | WP-05 parcial | auth honesta; WCAG 2.2 AA; headers equivalentes |
| WP-11 | P1/P2 | Performance, observabilidade, SLO e recuperação | WP-02/03 | falha detectável/reparável sem PII |
| WP-12 | P2 | Admin/Unfold, docs, CI, piloto e convergência | todos | gates completos e produto/documentação convergentes |

## 8. Work packages completos

Cada WP abaixo responde explicitamente: o que está errado, por que importa, comportamento-alvo, onde intervir, como provar, observar, migrar, reverter e quem decide.

### WP-00 — Reproduções adversariais e contratos executáveis

**Risco.** Alterar a cadeia sem reproduções determinísticas pode trocar bugs visíveis por corridas silenciosas. A suite atual é verde, mas não exerce os interleavings críticos e alguns testes validam políticas indesejadas.

**Resultado.** Um contract pack falhando no baseline e passando somente com os WPs correspondentes: máquina de estados, schema OpenAPI/TS, relógio/timezone, concurrency harness, fake providers programáveis e fixtures sem destinatário real.

**Execução.** (1) Catalogar transições atuais e desejadas; (2) criar relógio congelável e adapter fake capaz de falhar antes da chamada, depois do efeito e antes da resposta; (3) criar barreiras para dois workers/requests simultâneos; (4) capturar golden `ResolvedDispatchArtifact`, Projection e Actions; (5) transformar testes que hoje aceitam fallback approve, alert-over-optout e re-resolução expansiva em testes do novo contrato; (6) fixar query budgets e payload cardinality.

**Contratos.** Estado do command e delivery conforme WPs 02/03; timestamps ISO-8601 com offset; errors com `code`, `detail`, `retryable`, `field_errors`, `request_id`, `current_version`; idempotency key obrigatória em mutações perigosas; JSON Schema/OpenAPI sem campos implícitos.

**Arquivos.** Novos helpers/testes sob `shopman/shop/tests/`, `shopman/backstage/tests/` e `surfaces/marketing-nuxt/tests/`; fixtures de adapter em testes, nunca em produção; `pyproject`/Vitest/CI apenas se coordenados por WP-12.

**UX.** Goldens incluem copy e ações para forbidden, conflict, expired, partial, unknown, offline e session-expired; não congelar texto de domínio dentro da Projection.

**Segurança.** Fixtures usam refs/telefones sintéticos; logs de teste falham se detectarem PII, segredo ou provider response bruto. Property tests limitam JSON/cardinalidade/URLs.

**Testes.** Unitário de schema/state; API contract; duas threads/processos com barreira; crash points; fake timeout ambíguo; timezone/DST/virada do dia; payload fuzz; contract generation drift.

**Telemetria.** Nenhuma métrica de produção ainda. O harness deve afirmar os nomes/labels permitidos e rejeitar labels de alta cardinalidade/PII.

**Migração.** Apenas testes/contratos aditivos; executar contra legado para documentar falhas esperadas. **Reversão:** remover o harness isoladamente não muda runtime, mas nenhum WP dependente pode avançar sem prova equivalente. **Decisão:** Arquitetura aprova máquina de estados; QA define seed e reprodutibilidade.

**Critérios de aceite.** Cada MKT-P0 tem reprodução; cada teste falha no baseline pela assertiva esperada; fake distingue `not_attempted`, `effect_happened_response_lost` e `rejected`; zero rede externa; comandos completos documentados no log.

### WP-01 — Consentimento, supressão, preferência e snapshot privado de audiência

**Risco.** O reason `alerts` hoje sobrepõe consentimento global; a prova de consentimento é mutável; regras podem colidir e preferências/quiet hours não são explícitas. Isso pode causar envio juridicamente indevido ou fadiga.

**Resultado.** Um `AudienceResolution` backend-only, explicável e deduplicado, que gera cohort congelado protegido na aprovação; no send revalida revogação/supressão/canal, nunca inclui pessoa nova, e devolve contagens de exclusão sem PII.

**Execução.** (1) Com Jurídico, definir precedência: global `OPTED_OUT` sempre suprime; subscription ativa concede apenas finalidade/SKU/tipo/canal especificados enquanto não revogada; ausência fail-closed; (2) tornar eventos de consentimento append-only com purpose, legal basis, text/version, locale, source, actor/customer, timestamp e evidence hash; manter current-state derivado; (3) adicionar cancel/revoke e unicidade transacional à subscription; (4) normalizar telefone antes da dedupe; (5) resolver regras em QuerySets/sets, com reasons e exclusion counts; (6) criar `AudienceSnapshot`/membership protegido, inacessível à projection/Admin comum, com retenção/erase; (7) no envio retirar opt-outs, inválidos, fatigue, collision e indisponibilidade, sem adicionar novos opt-ins; (8) definir quiet hours/timezone e frequency cap; (9) surface degradada bloqueia aprovação/fire.

**Contratos.** `AudienceSummary {eligible_count, excluded_by_reason, deduplicated_count, degraded_sources[], calculated_at, expires_at, policy_version, cohort_hash}`; nenhum recipient. Snapshot referencia command/announcement/version. Unique subscription pendente por identity normalizada+SKU+alert_type+channel. Precedência e purpose versionadas.

**Arquivos.** `shopman/shop/services/audience.py`; `shopman/storefront/models/stock_alerts.py`, services/handlers/Admin respectivos; package `packages/guestman/shopman/guestman/contrib/consent/{models,service,admin,migrations}`; novos models/migrations de snapshot no domínio aprovado; projection/API Marketing; testes de audience/consent/stock alert.

**UX.** Preview mostra “elegíveis”, “duplicados removidos”, “sem consentimento”, “quiet hours/frequência”, “dados indisponíveis” e freshness. Nunca mostra nomes/telefones. Ação primária fica disabled com reason exato quando source está degraded; settings oferecem unsubscribe claro.

**Segurança.** Membership cifrada ou identificador interno com controles de acesso, nunca log/projection/export genérico. Definir retenção mínima, purpose limitation, erase/tombstone e auditoria de acesso. Min-cohort threshold impede enumeração via count; limitar combinação/cardinalidade e rate da API.

**Testes.** Opt-in→subscription→opt-out; opt-out→nova subscription conforme política; revoke; concorrência de subscribe; dedupe de formatos de telefone; count sem membership; cohort não expande; revoke após approve suprime; source outage bloqueia; collision/frequency/quiet hours/timezone; query budget em N grande; permission/side-channel de count.

**Telemetria.** `marketing_audience_resolution_seconds`, `eligible_total`, `suppressed_total{reason}`, `source_degraded_total{source}`, `snapshot_size_bucket`, `consent_policy_version`; sem customer/phone/rule livre em label. Alerta em qualquer `sent_after_optout` derivado por auditor de consistência.

**Migração.** Expandir schema append-only; backfill current state como evento `legacy_import` com confiança explícita, sem fabricar texto/base; impedir Marketing de usar registro sem política aceita; criar snapshots só para novas aprovações; cohort legado segue bloqueado ou modo compatível explicitamente aprovado. **Reversão:** flag de resolver legado apenas para campanhas já aprovadas, mantendo supressão nova; não apagar eventos/snapshots. **Decisão:** DPO/Jurídico sobre base/texto/retenção/min cohort; Produto sobre cap/collision/quiet hours; Operações sobre legado pendente.

**Critérios de aceite.** Propriedade “nenhuma revogação válida é ultrapassada” passa sob todos os reasons; uma aprovação nunca cresce; API/Projection/log não contêm membership; outage não vira zero; counts fecham matematicamente; query e latency budgets da seção 17 passam; erase/retenção e runbook testados.

### WP-02 — Command lifecycle, aprovação atômica, snapshot e outbox

**Risco.** Edit+approve em duas operações, estados sem CAS e enqueue após persistência permitem versão errada, anúncio preso, dupla decisão ou schedule cancelado que ainda dispara.

**Resultado.** Todo approve/reject/reschedule/publish-now/cancel/fire é um comando idempotente e serializável. Aprovação grava snapshot imutável, receipt, audit event e outbox na mesma transação. Workers retomam estados interrompidos com segurança.

**Execução.** (1) Definir transições e invariantes; (2) adicionar `version` monotônica e `select_for_update`/compare-and-set; (3) endpoint de decision recebe base_version, idempotency key, `publish_mode`, conteúdo completo e motivo quando exigido; (4) numa única `transaction.atomic`, validar readiness/promo/link/schedule/audience, criar snapshot, receipt, audit e outbox; (5) publicar outbox somente after commit; (6) worker claim com lease/attempt e recuperação stale; (7) cancel/reject invalida outbox não iniciada e cria tombstone; (8) dispatch revalida status/snapshot/expiry; (9) expiração é transição auditada, não bulk update opaco; (10) remover retorno precoce que encobre estado incompleto.

**Contratos.** `CommandReceipt {ref, kind, state: accepted|completed|rejected|conflict|unknown, idempotency_key, base_version, resulting_version, actor_ref, created_at, completed_at, resource_ref, outcome}`. `publish_mode` enum `now|scheduled`, nunca bool implícito. Snapshot content-addressed. Estado Announcement separa decisão de progresso de delivery.

**Arquivos.** `shopman/shop/models/campaign.py`; novos models/migrations command/snapshot/outbox/audit; `shopman/shop/services/campaign.py`, `campaign_schedule.py`; `shopman/shop/handlers/campaign.py`; management commands de schedule; `shopman/backstage/api/marketing.py`; projection e testes.

**UX.** Confirmação final diz versão, audiência, plataformas, horário/timezone e consequência. Duplo toque retorna o mesmo receipt. Conflict preserva rascunho e oferece comparar/rebase/reabrir, nunca sobrescreve. “Agora” não pode agendar; “agendar” mostra instante absoluto. Cancelar informa alvo ainda cancelável.

**Segurança.** Actor vem da sessão, não payload. Reautenticação/step-up conforme WP-04. Snapshot e receipt não incluem segredo/PII. CSRF obrigatório; payload com limites. Audit é append-only e registra reason/correlation/request ID.

**Testes.** Dois approves; approve vs edit/reject/cancel/expire; dois schedulers; crash antes/depois commit e antes/depois enqueue; idempotency replay com mesmo/diferente payload; now vs schedule; DST/past/expiry; revoked permission/session entre preview e command; stale lease recovery.

**Telemetria.** command latency/result, conflict/idempotency replay, outbox age, stuck state, lease recovery, decision-to-dispatch lag. Alertar qualquer `APPROVED` sem snapshot/outbox e `PUBLISHING` além do SLO.

**Migração.** Expandir tabelas; dual-write audit/receipt/outbox atrás de flags; backfill snapshots somente para pending/scheduled após revalidação e marca `legacy`; canary worker novo; dual-read/reconcile; cortar criação antiga; remover caminho legado só em release posterior. **Reversão:** desligar consumer novo e voltar leitura do legado para itens não migrados; receipts/snapshots permanecem; comandos novos não podem cair em caminho sem idempotência. **Decisão:** Produto define edição/cancel window; Operações define stale lease; Arquitetura aprova state machine.

**Critérios de aceite.** Conteúdo/hash despachado coincide byte a byte com snapshot aprovado; nenhuma transição sem actor/version/audit; cada idempotency key tem um outcome; crash injection converge sem comando perdido ou duplicado; cancellation vence directive não iniciada; migrations reversíveis ensaiadas.

### WP-03 — Delivery ledger, efeito-uma-vez, parcial/unknown e retry seletivo

**Risco.** O loop atual não tem alvo/tentativa persistente; falha individual é absorvida, crash repete wave, resultados concorrentes se perdem e partial/manual viram published. Garantia externa não é conhecida.

**Resultado.** Um ledger por plataforma e recipient protegido, com chave única, chunking/backpressure, tentativas e receipts. Estado agregado deriva do ledger; failed pode ser repetido seletivamente, unknown nunca às cegas.

**Execução.** (1) Modelar `DeliveryTarget` e `DeliveryAttempt`; (2) unique `(snapshot, platform, target_key)` e command key determinística; (3) popular targets da AudienceSnapshot em transação/chunks; (4) claim por lease/`skip_locked`; (5) adapter recebe immutable artifact + idempotency token se suportado; (6) gravar attempt antes e após call, provider message ID sanitizado e error taxonomy; (7) estados `planned|suppressed|queued|sending|accepted|confirmed|failed_retryable|failed_final|unknown|cancelled|expired`; (8) reconciler consulta provider quando possível; (9) retry seleciona somente estado permitido e cria nova attempt, nunca target; (10) corrigir wave horária usando selector canônico; (11) derivar agregado por plataforma e geral sem RMW JSON; (12) aplicar expiry/consent/readiness imediatamente antes do claim; (13) rate/backpressure por canal.

**Contratos.** “Efeito-uma-vez interno” significa um target lógico e no máximo um attempt simultâneo. “Confirmed” exige receipt/callback documentado. “Accepted” não significa entregue. “Unknown” é terminal temporário com Action de reconciliar; retry exige policy/gate. Agregado `completed_with_failures` nunca é `published` simples.

**Arquivos.** novos models/migrations; `handlers/campaign.py`, services campaign/schedule; adapters `_notification_templates.py`, `notification_manychat.py`, `notification_whatsapp.py`, console/email/sms e registry; webhook/reconciler se aplicável; directives/maintenance; API/projection/tests.

**UX.** Resultado por plataforma mostra contagem por estado, freshness e próximo passo. Ação “Tentar novamente 7 falhas” inclui somente retryable. Unknown oferece “Reconciliar com ManyChat” ou suporte, não “Enviar de novo”. Progresso não promete entrega. Preferência horária é visível no resumo.

**Segurança.** Target key pseudonimizada; telefone só no boundary do adapter, com acesso restrito e redaction. Provider body não persiste/loga sem allowlist. Webhook autenticado, replay-protected e idempotente. Limites evitam blast acidental.

**Testes.** Crash antes da call, depois do efeito/antes da resposta, depois da resposta/antes do commit; dois workers; duplicate directive/event; partial; callback duplicado/fora de ordem; preferred-hour; timeout; rate 429/Retry-After; circuit open; cancel/expire/revoke; payload max; load de cohort grande; property de contagem agregada.

**Telemetria.** targets/attempts por state/platform, duplicate prevented, unknown age, retry outcome, dispatch lag, chunk latency, rate-limit, circuit state, reconciliation drift. Sem target key em label. Alerta crítico se consent violation/duplicate confirmed; alto para unknown/stuck acima do budget.

**Migração.** Shadow ledger para dispatches piloto, comparando JSON legado; depois ledger source-of-truth e projeção derivada; manter JSON como snapshot compatível read-only por uma janela; backfill somente agregados históricos, nunca inventar per-recipient receipts. **Reversão:** pausar consumers, não reencaminhar unknown, voltar leitura agregada legado apenas para anúncios legacy; preservar ledger para reconciliação. **Decisão:** owner do canal prova idempotência/receipt; DPO define target retention; Operações define retry/circuit/rate.

**Critérios de aceite.** Todos os crash points convergem; unique constraint impede target duplicado; retry não toca accepted/confirmed/unknown; contagens derivadas fecham; partial/unknown são visíveis; zero telefone/provider secret em logs; carga e backpressure passam; preferred-hour envia exatamente ao cohort correto.

### WP-04 — Autoridade, confirmações, rate limiting e teste seguro

**Risco.** `shop.manage_campaigns` concede do view à troca de integração e envio para telefone arbitrário. Uma sessão comprometida ou erro humano tem blast radius amplo.

**Resultado.** Permissões capability-based, step-up e confirmação proporcional; teste só em sandbox/allowlist ownership-verified, estritamente unitário; comandos throttled, idempotentes e auditados.

**Execução.** (1) Criar permissions da matriz da seção 9 e migrar grupos; (2) backend resolve Actions/disabled reason; (3) exigir recent-auth/2FA para publish-now/fire/retry-unknown/config integration conforme decisão; (4) confirmation token curto, bound a user/snapshot/version/consequence; (5) throttle por user/IP/shop/action e quota por blast; (6) test-send apenas números sintéticos/verificados ou sandbox do provedor, payload isolado e `max_targets=1`; (7) nunca reutilizar endpoint/código que aceita audience rules; (8) redactar logs/errors; (9) auditoria de tentativa negada/limite; (10) revogar capabilities imediatamente, inclusive action já aberta.

**Contratos.** Permissions explícitas; Action `enabled/reason/confirmation`; `Idempotency-Key`; erros `403 forbidden`, `409 conflict`, `422 validation`, `429` com `Retry-After`; confirmation token one-use; test receipt marcado `sandbox=true`, sem efeito em KPIs/histórico de campanha.

**Arquivos.** `shopman/backstage/permissions.py`, API permission classes, Marketing API, notifications API, setup/bootstrap groups, models/audit, BFF header forwarding, Nuxt Actions/dialogs, adapters e testes.

**UX.** Ação não autorizada não aparece ou explica acesso conforme política; forbidden nunca vira session expired. Confirmação mostra blast, plataforma, horário, versão e irreversibilidade. Teste distingue “sandbox aceitou” de “telefone recebeu”. Campo de telefone livre é removido salvo policy formal de números verificados.

**Segurança.** CSRF/session binding, 2FA freshness, quotas, anomaly alert, no open redirect, no client-supplied actor/permission, audit imutável. Config de integration exige compare-and-set e dual control se definido.

**Testes.** Matriz role×Action; permissão revogada entre load/click; confirmation replay/expiry/wrong version; CSRF; double click; 429/Retry-After; test cannot fan-out mesmo com payload malicioso; PII/log scan; IDOR de receipt/announcement; flow change concurrency.

**Telemetria.** allowed/denied/throttled/confirmed por action e role class, blast-size buckets, test-send count, integration change audit, step-up failure. Nunca username/phone em label.

**Migração.** Criar novas perms e mapear grupos sem remover antiga; modo audit-only registra decisão; comparar por duas semanas/piloto; ativar enforcement por capability; remover perm ampla do runtime por último. **Reversão:** flag volta à perm antiga apenas para comandos não perigosos; publish/fire/test/config continuam bloqueados por deny-safe. **Decisão:** Segurança/Operações aprovam matriz, thresholds, 2FA e dual control; RH/owners aprovam membership.

**Critérios de aceite.** Tabela da seção 9 passa em API e UI; test endpoint não alcança audience resolver; 403 e 401 distintos; todos comandos perigosos têm idempotency/confirmation/audit/throttle; secrets/PII não aparecem; emergency revoke bloqueia action já carregada.

### WP-05 — Marketing Projection + Actions canônica e cliente gerado

**Risco.** Projection entrega apresentação em português e omite Actions/version; tipos manuais e lógica duplicada deixam browser prometer ações/estados divergentes.

**Resultado.** Projection pura, versionada e surface-agnostic; Actions resolvidas no backend com autoridade/readiness/consequência; schema gera o cliente TS e drift quebra CI.

**Execução.** (1) Definir schemas da seção 10; (2) remover labels/copy renderizada da projection em fase compatível; (3) expor refs/enums/facts/timestamps/counts/capabilities/freshness; (4) action resolver único para cards, detail e notifications; (5) adicionar resource version/etag e error envelope; (6) paginação cursor em history/templates/rules; (7) corrigir métricas operacionais para derivar ledger e filtro diário; (8) gerar types/client a partir de OpenAPI/schema; (9) presentation map exaustivo no Nuxt; (10) contract snapshots CI; (11) BFF preserva headers allowlisted de segurança/rate/request/version.

**Contratos.** Conforme seção 10. Unknown enum renderiza fallback seguro e telemetria, mas schema drift falha build. Actions são links/comandos relativos same-origin, payload schema allowlisted, sem copy de domínio. SSE só invalida `resource_ref/version`; refetch com ETag é canônico.

**Arquivos.** `shopman/backstage/projections/marketing.py`, `api/marketing.py`, `api/notifications.py`, schemas/URLs; `docs/reference/projection-contracts.md`; generated contract path coordenado; `app/types/campaign.ts`, presentation/composables/pages; BFF; CI/tests.

**UX.** Presentation layer escreve PT-BR, ação primária por contexto e disabled reason humano. Freshness/stale/degraded ficam visíveis. Paginação preserva filtro/scroll. Métrica não comprovada não usa “alcançadas”.

**Segurança.** Payload/action não aceita URL externa arbitrária; permissions resolvidas a cada POST; projection mínima por role; ETag não inclui PII; headers/caches privados/no-store conforme dado.

**Testes.** Golden schema, generated diff clean, enum exhaustiveness, Action parity API/UI/notification, revoked permission, ETag/304, cursor stable, metric date boundary/timezone, BFF headers, SSE invalidation no payload.

**Telemetria.** projection latency/size/query count, action enabled/disabled reason aggregates, schema/client version mismatch, stale age, refetch/SSE/poll outcome.

**Migração.** Publicar `contract_version=2` aditivo e gerar cliente; frontend suporta v1/v2 sob flag; canary v2; remover labels e espelho manual só após zero uso. **Reversão:** servir v1 por flag mantendo v2 tables/models; frontend compatível durante janela. **Decisão:** Arquitetura aprova boundary/policy de versionamento; Produto aprova nomes/copy na presentation.

**Critérios de aceite.** Nenhum label/copy operacional em Projection; nenhuma action inferida no browser; CI falha em drift; metrics reconciliam ledger; cursor não duplica/perde linhas; SSE só invalida; API/BFF carregam request/version/rate metadata segura.

### WP-06 — Conteúdo factual, preview fiel, variantes e readiness

**Risco.** Variante é apagada, preview corre e diverge do envio, links/imagens não são governados, flow outage parece vazio e um caminho WhatsApp contradiz ADR-009.

**Resultado.** Um `ResolvedDispatchArtifact` imutável por plataforma alimenta preview e adapter; fatos canônicos, limites, mídia, link e template/flow exatos são validados; readiness é verificável e reparável.

**Execução.** (1) Extrair resolver puro único; (2) preservar body/fields da variante e herdar somente campos ausentes; (3) render strict de variável desconhecida — bloquear e apontar campo, nunca vazio silencioso; (4) resolver oferta/preço/estoque/validade/link no orquestrador, com as-of/freshness e validação até o horário; (5) validar limite/encoding/hashtag/URL/media por plataforma; (6) preview recebe hash/version, cancela requests antigas e mostra erro/degraded; (7) remover sample arbitrária e usar fixture explicitamente rotulada; (8) readiness consulta somente flow ativa e distingue ready/degraded/blocked/unknown; (9) mudança de flow usa CAS/audit/confirmation; (10) remover fallback direto após gate ADR-009; (11) allowlist scheme/host, proxy de imagem quando necessário e threat test de fetch; (12) provar/evitar race de custom fields ManyChat, preferindo payload atômico/flow parametrizado.

**Contratos.** Artifact contém platform, rendered content, limits, media descriptor, canonical link ref+resolved URL, offer facts+as_of, template ref+version/hash, flow ref+version, validation warnings/errors, schedule/expiry/timezone, artifact hash. Preview devolve o mesmo hash que approve deve referenciar.

**Arquivos.** campaign/offers/promotions services/models; adapters ManyChat/WhatsApp/templates; readiness/check command; Marketing API/projection; `AnnouncementPreview.vue`, template form/card/platforms page/composables; tests/docs/runbook.

**UX.** Tabs por plataforma são fiéis; contador usa regra real; missing media/URL/variable destaca local; copy mostra “dados de HH:MM” e bloqueia validade insuficiente. Readiness apresenta causa, última checagem e Action exata; outage nunca vira “nenhum flow”.

**Segurança.** Sanitização/escaping por sink, URL policy, sem template injection, prompt/content não escolhe flow/credential, erro do vendor redigido. Preview não faz fetch arbitrário do browser e não expõe secret.

**Testes.** Golden artifact preview=dispatch; variante; Unicode/emoji/URL/hashtag/long text; unknown variable; link/promotion expiry; media absent/invalid/redirect/private IP/DNS rebinding conforme fetch real; flow inactive/outage/cache stale; ADR-009 backend selection; concorrência custom field em sandbox.

**Telemetria.** artifact validation failures por code, preview stale response discarded, readiness state/age, flow mismatch, link/media rejection, provider payload hash (não conteúdo), ADR backend selected.

**Migração.** Shadow resolver compara payload hash sem enviar; corrigir templates inválidos via relatório; ativar strict por plataforma; remover fallback só após readiness/rollback validado. **Reversão:** flag retorna renderer legado para previews/announcements legacy, nunca para nova aprovação que já exige hash novo; restaurar backend apenas por decisão incident response documentada. **Decisão:** Marca aprova limites/copy; channel owner confirma ManyChat semantics e URL fetch; Arquitetura confirma ADR-009.

**Critérios de aceite.** Snapshot preview e adapter têm mesmo artifact hash; body variant permanece; nenhuma variável desconhecida; promotion/link ainda válidos no dispatch; todos readiness states testados; SSRF/tracking controlados conforme threat model; outage bloqueia mutação cega.

### WP-07 — Fluxos Nuxt omotenashi, drafts, conflitos e scheduling

**Risco.** A edição descarta campos, draft se perde, “agora” pode agendar, erro/conflict/partial não preserva contexto e ações exigem navegação mental.

**Resultado.** Fluxos mobile-first curtos, lossless e previsíveis: formulário round-trip completo, draft restaurável e privado, timezone explícito, confirmação factual, receipts/resultados contextuais e recovery inline.

**Execução.** (1) Migrar UI para Projection + Actions; (2) gerar forms schema-driven ou preservar round-trip de todo campo desconhecido, com diff explícito; (3) draft autosave local seguro ou server-side por user/resource/version, TTL e status; (4) dirty guard e restore após 401; (5) conflict diff/rebase; (6) separar CTAs Now/Schedule com payload enum; validar futuro/expiry/timezone/DST; (7) audience preview com debounce+abort+epoch e degraded blocking; (8) fire panel não habilita count zero/falha e recebe filtros configuráveis canônicos; (9) result receipt permanece na rota e oferece retry/cancel/reconcile; (10) corrigir campanhas/template/platform/history/detail error states; (11) paginação/filtros/scroll; (12) medir budgets da seção 16 com gestores.

**Contratos.** Form state serializa losslessly; draft key user+resource+base_version; server errors field-addressable; command receipt; Actions; dates ISO offset + named shop timezone; navigation state/restoration contract.

**Arquivos.** todas as pages, AnnouncementCard/Preview/TemplateForm/CampaignForm/TopBar/FirePanel, composables, utils/session, types/presentation, novos componentes canônicos necessários e testes.

**UX.** Caso comum: alerta/card → revisar contexto e preview → confirmar em no máximo 3 ações significativas e sem troca genérica de tela. Save status visível. Back/refresh/session recovery preservam tudo. Unknown/partial mostram plataforma e action. Exclusão mostra dependências/scheduled uses e requer confirmação proporcional.

**Segurança.** Draft não persiste PII/audience membership/token; storage por usuário e TTL; rich text tratado como texto; href same-origin/allowlisted; actions reautorizadas no submit; autocomplete apropriado; clipboard não inclui segredo.

**Testes.** Round-trip de todas as audience/trigger fields, unknown-field preservation, edit concurrent, route/session reload, draft isolation, now/schedule, past/DST/expiry, zero/degraded audience, long content, double click, partial/unknown, keyboard/focus/mobile/zoom/reduced motion; budgets instrumentados.

**Telemetria.** draft restored/lost, conflict rate/outcome, validation error code, abandoned step, action-to-receipt time, navigation/touch counts amostrados sem conteúdo, session recovery success, preview-to-approve drift prevented.

**Migração.** Ligar novos forms por route/role flag; manter payload v1 adapter; importar apenas drafts compatíveis/versionados; piloto com 5–8 gestores; retirar componentes legacy após task success/erro comparados. **Reversão:** route flag volta UI anterior sem perder commands v2; drafts exportáveis ao clipboard local quando seguro. **Decisão:** Produto escolhe default schedule/confirm thresholds; usuários validam budgets/copy; Ops define delete policy.

**Critérios de aceite.** Form existente salva sem diff oculto; refresh/401 mantém rascunho; now nunca schedule; timestamps inequívocos; nenhuma action genérica obriga busca; budgets atingidos; todos estados da seção 15 têm screenshot e teste; partial não parece total.

### WP-08 — Alertas pessoais realmente acionáveis

**Risco.** Action ausente aprova por default, inline action não mostra versão/consequência e somente uma notificação é marcada; seen/read é confundido com resolução.

**Resultado.** Alerta é projeção persistente de uma condição, com owner, dedupe, severidade, lifecycle e Actions canônicas. Objeto e todas as representações do alerta reconciliam na mesma decisão.

**Execução.** (1) Remover qualquer action default; input desconhecido é inválido/disabled; (2) modelar `unseen|seen|acknowledged|resolved|expired` e eventos; (3) source condition/ref/version + dedupe/group/owner/escalation; (4) usar action resolver do WP-05; (5) inline apenas para comando curto seguro com confirmação equivalente; revisão abre a âncora exata e pré-preenchida; (6) resolver/invalidar todos siblings quando condição muda; (7) information-only sai do sino e vira estado/histórico; (8) SSE invalida e refetch reconcilia; (9) cursor e retention; (10) medir alert→action→resolution.

**Contratos.** Seção 11. Alert não carrega callable arbitrário. `resolved` deriva da condição e não de read. Action usa mesma permission/base_version/idempotency do objeto. Deep-link inclui resource/anchor, nunca busca genérica.

**Arquivos.** `models/user_notification.py`, `shop/notifications.py`, service notification, API notifications/Marketing, projection/action resolver, useUserNotifications/board/topbar/pages, eventstream e testes.

**UX.** Uma primary action recomendada; alternativas só quando pertinentes. Contexto contém why/impact/deadline/freshness. Seen não remove contador de unresolved se política assim decidir. Ação resolve todos duplicados e mantém receipt; failure preserva alerta e conteúdo.

**Segurança.** Canal pessoal deriva owner da sessão; IDOR testado; payload/deep-link allowlist; permission reavaliada; alert sem action nunca aprova; PII mínima; dedupe key não inclui segredo.

**Testes.** Missing/unknown action; role matrix; action parity; sibling reconciliation; seen/ack/resolved; source already resolved; concurrent actions; expired alert; SSE disconnect/refetch; pagination/dedupe/escalation; deep-link/anchor; session revoked.

**Telemetria.** created/deduped/seen/ack/resolved/expired, time-to-ack/resolve, action chosen/outcome, stale actionable count, orphan alert, deep-link correction. Labels por type/action code, não texto/ref livre.

**Migração.** Mapear `read=true` legado para `seen`, nunca inferir resolved; backfill source condition quando determinístico e expirar o resto explicitamente; dual project; trocar endpoint; limpar default approve depois de clients v2. **Reversão:** render read-only do novo alert e bloquear mutation antiga; não voltar ao fallback approve. **Decisão:** Produto/Operações definem owner/escalation/SLA e quais informações saem do sino.

**Critérios de aceite.** Zero comando sem explicit action; lifecycle consistente; siblings fecham com o objeto; deep-link abre contexto exato; unauthorized action disabled/403; métricas ligam alert→receipt→resolution; erro não faz alerta desaparecer.

### WP-09 — IA assistiva, factual e auditável

**Risco.** Instrução/template/contexto não confiáveis entram no prompt; preço/estoque/oferta podem estar stale; não há validação estruturada, claims/moderação ou versão de modelo/prompt; regra pode autoenviar.

**Resultado.** IA sugere copy estruturada sobre fatos canônicos imutáveis, mostra diff e incerteza, nunca altera facts/target/schedule/platform e sempre requer revisão humana nesta fase.

**Execução.** (1) Delimitar dados não confiáveis no prompt; (2) usar output schema com body/hashtags e citations para fact IDs internos; (3) revalidar cada claim por allowlist/fact graph; (4) policy de conteúdo/brand e moderação; (5) limitar comprimento/URLs/idioma; (6) guardar model/provider/prompt policy version, fact hash, output hash e editor diff — sem prompt secreto/PII; (7) timeout/failure devolve edição manual intacta; (8) remover auto-dispatch de output IA; (9) proteger rate/cost; (10) criar red-team corpus PT-BR para injection, preço falso, urgência enganosa e conteúdo ofensivo.

**Contratos.** `AISuggestion {body, hashtags, used_fact_ids, warnings, policy_version, model_ref, suggestion_hash}`; `accepted` somente por humano e vira novo conteúdo versionado; nenhum campo de facts/offer/link é gravado a partir da IA.

**Arquivos.** prompt/rewrite em campaign service/API; facts/offers resolver; snapshot/audit; AnnouncementCard/Preview; settings se existentes; tests/runbook/docs.

**UX.** Botão “Sugerir texto”; compare original/sugestão, facts usados e warnings. Aceitar nunca publica. Falha preserva texto e permite continuar manual. Copy não chama sugestão de “verificada” sem claim checker completo.

**Segurança.** Prompt injection boundary, no PII/secrets, output escaped, URL generation proibida salvo canonical ref, provider retention contract, moderation, quotas, audit. Admin `ai_prompt` tem validação/authority.

**Testes.** Injection em template/event/product, facts conflitantes/stale, price/promo expiry, hallucinated claim, offensive output, invalid schema, timeout/retry, provider unavailable, long Unicode, role/rate, acceptance diff, proof no auto-send.

**Telemetria.** request/result/latency/cost bucket, invalid schema, claim rejected por code, moderation, accepted/edited/discarded, provider outage; nunca prompt/copy/customer em label/log padrão.

**Migração.** Desligar IA por default até contract; shadow/offline corpus; piloto assistivo; manter edição manual sempre. **Reversão:** feature flag remove botão e preserva drafts/snapshots; campanha nunca depende da IA para dispatch. **Decisão:** Marca/Jurídico define policy/claims; Segurança aprova provider/data; Produto decide após evidência qualquer mudança no gate humano.

**Critérios de aceite.** 100% outputs schema-valid ou rejeitados; claim fora dos facts não chega à aprovação; sugestão jamais publica; audit reproduz policy/fact/model/hash; timeout não perde conteúdo; red-team e revisão humana aprovados.

### WP-10 — Gate de sessão, segurança web, acessibilidade e design canônico

**Risco.** Páginas/fetches montam atrás do login; forbidden/outage vira vazio/404; overlay não prende foco; controles são pequenos; Nuxt/BFF perde headers e carrega Google Fonts externo.

**Resultado.** Auth gate real antes de dados/rotas, estados HTTP honestos, envelope web endurecido, componentes operator-kit consistentes e WCAG 2.2 AA em todos os estados/viewports.

**Execução.** (1) Gatear mount/navigation/data por session state; (2) login como dialog/page sem background interativo, foco inicial, trap, restore e live errors; (3) distinguir 401/403/404/409/429/5xx/offline; (4) session-expired salva draft e retoma action após reauth, com reconfirmação; (5) aplicar headers CSP/HSTS/nosniff/referrer/frame/COOP/permissions e remover `x-powered-by`; (6) BFF forwards headers allowlisted e impõe private/no-store; (7) self-host fonts/assets, sem dependência Google; (8) convergir controles com operator-kit, mínimo 44×44, focus-visible, contrast, landmarks, labels/descriptions; (9) responsive/zoom/reduced-motion/dark-light; (10) axe + keyboard + screenshots.

**Contratos.** Session state `checking|authenticated|anonymous|expired|forbidden`; nenhum fetch protegido antes de authenticated. Security header matrix por HTML/BFF/error/SSE. A11y conforme seção 15; component tokens canônicos, sem cores raw novas.

**Arquivos.** `app.vue`, OperatorLogin, UI primitives/CSS/config, utils session/API, pages/composables, server BFF/SSE, operator-kit quando contribuição reutilizável for coordenada, deploy proxy e tests.

**UX.** Login tem título/instrução/error associados; fundo inert. Loading não vira empty. Forbidden explica acesso sem sugerir login. 429 mostra espera. Reauth retorna ao draft/action. Touch e foco atendem matriz; dark/light não muda semântica.

**Segurança.** CSP sem unsafe amplo, frame ancestors none, no third-party font, cookie attributes mantidos, CSRF/origin preservados, open redirects proibidos, response headers equivalentes. Não copiar `set-cookie`/location sem validação.

**Testes.** SSR/anonymous no protected fetch, 401/403 distinction, focus trap/restore, keyboard-only, axe, 200% zoom, 320 px, reduced motion, forced colors, contrast, CSP nonces/assets, clickjacking, BFF header/cookie/cache, session expiry mid-command.

**Telemetria.** auth state/errors, session recovery, forbidden route, CSP violation endpoint sanitizado, web vitals, a11y test gate, BFF status/latency/cache. Sem URL query/username sensível.

**Migração.** Headers report-only primeiro onde necessário; self-host font antes de bloquear; auth gate por flag; component migration rota a rota. **Reversão:** relaxar apenas diretiva CSP específica com owner/expiry, nunca frame/HTTPS; UI route flag preserva command backend. **Decisão:** Segurança aprova CSP/header; Design aprova tokens; Accessibility owner valida WCAG.

**Critérios de aceite.** Nenhum request/data protected sob overlay anônimo; 401/403/404 distintos; background não focável; todos controles ≥44×44 salvo exceção documentada com área clicável; axe sem serious/critical; teclado/zoom/matrix passam; headers presentes em HTML/BFF/errors; nenhuma fonte externa.

### WP-11 — Escala, observabilidade, SLO e recuperação operacional

**Risco.** Resolução faz scans/N+1, sends são waves síncronas, health `/` prova pouco e faltam alertas/runbook de stuck/partial/unknown/consent. Logs atuais podem carregar phone/vendor body.

**Resultado.** Budgets e SLO mensuráveis, queries/chunks limitados, health/readiness por dependência, logs seguros, dashboards de decisão/reparo e runbooks ensaiados.

**Execução.** (1) Medir query plan/count/latency e trocar scans por consultas/index/materialização apropriada; (2) limitar/filter consent query por cohort; (3) cursor/batching/backpressure; (4) health liveness separado de readiness BFF→Django→DB/queue, sem chamar fornecedor caro a cada probe; (5) métricas/traces correlacionados receipt→outbox→target→attempt; (6) redaction allowlist; (7) alertas SLO da seção 17; (8) runbooks para stuck, partial, unknown, provider outage, privacy incident, bad copy/link, cancel/rollback; (9) drills; (10) capacidade da instância/workers baseada em carga, não chute.

**Contratos.** SLO e taxonomy da seção 17; request/correlation IDs; logs estruturados por refs técnicas não PII; readiness state/freshness; queue leases/retry budgets; metric labels limitadas.

**Arquivos.** audience/projection/services/handlers/adapters; logging/Sentry; directive/maintenance workers; `.do` deploy specs/alerts; health endpoints; dashboards/alerts; runbooks; load/chaos tests.

**UX.** Degraded/stale/offline mostra last-known freshness e Action pertinente; não promete sucesso. Support copy inclui receipt ref seguro copiável. Poll pausa em tab oculta e retoma/refetch ao foco; SSE backoff observável sem tempestade.

**Segurança.** Redaction tests, access-controlled dashboard, no health detail/secret público, rate on probes, retention. PII apenas no boundary estritamente necessário.

**Testes.** Query budget por cohort/cardinalidade; load sustained/burst; queue backlog; provider 429/5xx/timeout; DB deadlock; worker kill; SSE drop; cache stale; reconciliation; log scanner; health dependency outage; runbook game day.

**Telemetria.** Exatamente a seção 17; dashboard por stage/platform/state, sem dimensão customer/content. Error sampling preserva code/ref/hash, remove body/phone/token.

**Migração.** Instrumentar antes de otimizar; baseline 7–14 dias no ambiente autorizado; índices `CONCURRENTLY`/equivalente quando suportado; canary worker/chunk; alertas inicialmente non-paging até calibrar. **Reversão:** flags de batch/worker/read model; índices revertidos separadamente; nunca desligar auditoria/consent guard. **Decisão:** SRE/Ops aprova SLO/paging/capacity; Produto aprova freshness visível.

**Critérios de aceite.** Budgets/SLO mensuráveis e alertados; zero PII em scan; health detecta BFF/API/queue degradados; kill/timeout converge; runbooks executados por alguém que não implementou; capacity test sustenta pico acordado com margem.

### WP-12 — Admin/Unfold, documentação, CI e rollout disciplinado

**Risco.** A promessa de Admin config/audit não corresponde aos models registrados; docs/rotas/topologia estão stale; CI não cobre build/E2E/a11y/security/visual; dependência Nuxt instalada diverge do manifesto.

**Resultado.** Um corte único e documentado: Nuxt opera; Unfold configura apenas o autorizado e consulta auditoria. Dependências/contratos são determinísticos; CI e rollout provam toda a cadeia.

**Execução.** (1) Gate humano define ownership por objeto; (2) se houver Admin, usar somente `ModelAdmin`, fieldsets/tabs/inlines/widgets/actions/templates Unfold oficiais, audit read-only e links ao Nuxt; nenhum console custom; (3) alinhar registration/perms/list_editable com authority matrix; (4) atualizar todos os docs divergentes após implementação; (5) tornar `npm ci` determinístico e resolver Nuxt 4.5.0 vs `^4.5.2` sem atualização opportunista; (6) CI roda test/typecheck/lint/build/contracts/E2E/a11y/visual/security e backend/concurrency; (7) smoke pós-deploy read-only e sintético; (8) executar plano da seção 19; (9) remover legado só depois de reconciliação.

**Contratos.** Admin não chama command fora do mesmo service/permission/idempotency. Audit imutável. Docs têm owner/last_verified/rotas. Lockfile é fonte reproduzível e `npm ci` precisa satisfazer manifesto. Gate canônico `make admin` sempre.

**Arquivos.** `shopman/shop/admin/campaign.py`, promotion/Admin registration, curated admin/navigation/settings hub, Guestman consent Admin; operator-kit; `package*.json`, configs; workflows/deploy specs; READMEs, ADR/reference/design docs/runbooks; suites E2E/visual/security.

**UX.** Admin usa componentes Unfold canônicos e não duplica cockpit; audit oferece filtros/refs/timeline read-only. Docs descrevem rotas reais. Smoke cobre desktop/mobile e states críticos sem mutação real.

**Segurança.** Admin permissions e field locks; dados de cohort/delivery não ficam browseáveis por default; test data sintético; supply-chain/lock audit; deploy approval e separation of duties.

**Testes.** `make admin`; canonicity/widget/reachability/permission; full frontend gates; backend focused+full conforme risco; E2E local seeded; screenshot baselines; dependency consistency; deploy manifest/health/rollback smoke.

**Telemetria.** CI duration/flakes, contract drift, visual changes approved, deploy marker/canary metrics/rollback, Admin denied access/audit view. Não coletar screenshots com PII.

**Migração.** Admin e docs por último; feature flags/canary/pilot conforme seção 19; lockfile em commit isolado; screenshots versionadas com revisão. **Reversão:** unregister Admin edit paths, manter audit; rollback de imagem/config pela runbook; contracts compatíveis na janela. **Decisão:** Produto/Ops escolhe corte Admin; Design aprova visual; Release Manager autoriza cada estágio.

**Critérios de aceite.** `make admin` e todos gates CI passam; nenhum console artesanal; rotas/docs/topologia atuais; install limpo reproduz versões válidas; smoke pós-deploy seguro; piloto/rollback comprovados; audit acessível apenas a roles corretas.

## 9. Matriz de autoridade e gates de decisão

### 9.1 Capabilities propostas

Nomes finais de permission são decisão de Segurança, mas não podem voltar a uma permissão monolítica.

| Capability | Observador | Editor | Aprovador | Publisher | Platform owner | Auditor/DPO | Condição adicional |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| Ver board/history/result agregado | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | sem membership/PII |
| Ver audit de conteúdo/ator | — | próprio escopo | ✓ | ✓ | ✓ | ✓ | propósito e retention |
| Ver delivery target/PII protegido | — | — | — | suporte limitado | canal limitado | ✓ | step-up + audit de acesso |
| Criar/editar regra e draft | — | ✓ | ✓ | ✓ | — | read-only | version/CAS |
| Criar/editar template/copy | — | ✓ | ✓ | ✓ | canal limitado | read-only | strict validation |
| Preview e audience count | ✓ limitado | ✓ | ✓ | ✓ | ✓ | ✓ | min cohort + throttle |
| Aprovar/rejeitar | — | — | ✓ | ✓ | — | audit | snapshot + confirmation |
| Publicar agora/agendar/cancelar | — | — | — | ✓ | — | audit | recent-auth; blast threshold |
| Fire manual | — | — | — | ✓ | — | audit | confirmation + quota; possível dual control |
| Retry de `failed_retryable` | — | — | — | ✓ | canal | audit | seletivo/idempotente |
| Reconciliar/retry de `unknown` | — | — | — | gate humano | ✓ | audit | nunca automático |
| Enviar teste sandbox | — | ✓ restrito | ✓ | ✓ | ✓ | audit | verified/synthetic target; max 1 |
| Alterar flow/readiness/config | — | — | — | — | ✓ | audit | step-up + CAS + confirmation; dual control opcional |
| Alterar política de consent/cap | — | — | — | — | — | ✓ | Jurídico + Produto + migration |
| Exportar audit | — | — | — | — | suporte limitado | ✓ | purpose, watermark, expiry |

Defaults: deny; backend é autoridade; frontend só apresenta Actions. Publisher não herda automaticamente Platform Owner/DPO. Auditor não ganha comando operacional. Suporte vê receipt/error category antes de qualquer PII.

### 9.2 Gates humanos

| Gate | Quando bloqueia | Decisores | Evidência mínima |
|---|---|---|---|
| G-H01 Consentimento | antes de WP-01 schema/enforcement | DPO/Jurídico + Produto | precedence, purpose, texto/versionamento, legado, retenção, erase, min cohort |
| G-H02 Cohort | antes de persistir membership | DPO + Arquitetura + Dados | threat model, encryption/access, retenção, volume, auditoria |
| G-H03 Garantia externa | antes de habilitar retry automático | Owner ManyChat/Meta + SRE | docs/test sandbox de idempotency, receipt, timeout, webhook e rate |
| G-H04 RBAC/blast | antes de enforcement WP-04 | Segurança + Operações | role map, step-up, quotas, dual control, emergency revoke |
| G-H05 Produto | antes de UI definitiva | Product owner + 5–8 gestores | defaults, budgets, confirmation thresholds, cancel/edit window, alert priority |
| G-H06 Marca/IA | antes de piloto IA | Marca/Jurídico + Segurança + Produto | claims, moderation, provider data, red-team, human review |
| G-H07 Admin | antes de registrar/editável | Operações + Admin owner | ownership por objeto, no dual write, Unfold design review, `make admin` |
| G-H08 SLO/capacidade | antes do piloto | SRE/Ops + Produto | baseline, peak, pager thresholds, runbooks, on-call |
| G-H09 Release | em cada estágio da seção 19 | Release Manager + owners acima | migrations/backup, flags, smoke, dashboards, rollback ensaiado |
| G-H10 Produção | antes de qualquer write/deploy/send | proprietário do ambiente | alvo, janela, comando, blast e rollback explicitamente autorizados |

Sem resposta a um gate, o executor pode produzir teste, schema alternativo ou relatório read-only, mas não escolher silenciosamente a política.

## 10. Contratos Projection + Actions

### 10.1 Princípios

1. Projection contém fatos, refs, enums, counts, timestamps, versões, freshness e relations; não contém frase de apresentação como `status_label` ou “alcance baixo”.
2. O backend calcula Actions usando estado, autorização, readiness, version e policy atuais. O frontend nunca converte status em permissão.
3. Presentation no Nuxt mapeia enums para copy/ícone/tom. Enum desconhecido é estado seguro “não reconhecido”, desabilita mutação e gera telemetria.
4. Toda mutação recebe `base_version` e `Idempotency-Key`; comandos perigosos também recebem confirmation token.
5. SSE transmite somente invalidação: `resource_ref`, `resource_version`, `event_kind`. O Nuxt refaz GET canônico.
6. Listas usam cursor estável, limite máximo e `as_of`; não usam cortes silenciosos em 50/100.
7. Payload e ETag não contêm PII nem lista de audience.

### 10.2 Envelope proposto

```json
{
  "contract": "marketing.v2",
  "generated_at": "2026-09-08T16:00:00-03:00",
  "shop_timezone": "America/Sao_Paulo",
  "resource_version": 17,
  "freshness": {
    "state": "fresh",
    "as_of": "2026-09-08T16:00:00-03:00",
    "degraded_sources": []
  },
  "data": {},
  "actions": []
}
```

`freshness.state`: `fresh | stale | degraded | unavailable`. `degraded_sources` usa codes allowlisted (`audience`, `offers`, `manychat`, `notifications`, `delivery_ledger`), jamais texto de exception.

### 10.3 Action canônica

```json
{
  "ref": "announcement:ANN-42:approve:v17",
  "kind": "approve_announcement",
  "label": "presentation.approve_announcement",
  "priority": "primary",
  "enabled": false,
  "reason": "platform_not_ready",
  "href": "/announcements/ANN-42#readiness",
  "method": "POST",
  "payload_schema": "marketing.command.approve.v2",
  "idempotency": "required",
  "confirmation": {
    "mode": "summary",
    "token_required": true,
    "consequence_code": "publishes_now_to_eligible_audience"
  }
}
```

- `label` e `reason` são chaves/codes de apresentação, não frases renderizadas.
- `href` é same-origin e aponta para rota/âncora exata; não pode ser `/campaigns` genérico quando o problema está em uma plataforma.
- `method` é `GET` para navegação ou método HTTP real do command. Nunca codificar callable/script.
- `payload_schema` referencia schema versionado e allowlisted.
- `idempotency`: `none | supported | required`; toda ação com efeito externo é `required`.
- `confirmation.mode`: `none | simple | summary | typed`; o backend escolhe conforme blast/irreversibilidade.
- `enabled=false` não vira botão que tenta e falha; UI explica `reason` e, quando existir, mostra Action reparadora separada.

### 10.4 Projections mínimas

| Projection | Campos de verdade | Campos proibidos |
|---|---|---|
| Board | pending refs/version/reason/facts/age/expiry/audience summary/readiness/result aggregate; operational counters derivados do ledger | copy pronta, labels, “reached” sem receipt, audience members |
| Campaign rule | ref/version/name/active/trigger schema/audience schema/schedule/platform refs/template ref/requires_review/dependencies | JSON não validado, secrets, flow credentials |
| Announcement detail | ref/version/state/why/fact refs/snapshot hash/content artifact summaries/schedule/audience summary/delivery aggregates/audit refs | recipient list, mutable template masquerading snapshot, raw provider errors |
| Template | ref/version/active/body source/variables schema/platform variant schemas/AI policy ref/dependency counts | secret, unknown placeholder silently accepted |
| Platform readiness | platform/state/reason codes/as_of/template-flow ref/version/capabilities/limits/last safe test | access token, raw vendor error, zero conflated com outage |
| History | command/announcement refs, actor display policy, decided/dispatched timestamps, immutable content hash, aggregate/result/failure codes | truncated silent list, PII, commercial ROI |
| Notification | lifecycle/source ref+version/reason/deadline/owner/group/actions | default action, arbitrary href/payload, copied condition stale |

### 10.5 Commands e erros

| Command | Campos obrigatórios | Invariantes |
|---|---|---|
| approve | base version, artifact hash, audience snapshot ref/hash, publish mode, schedule quando aplicável, idempotency, confirmation | conteúdo+approval+snapshot+outbox atômicos |
| reject | base version, reason code/text conforme policy, idempotency | não deixa directive futura ativa |
| cancel | base version, scope, reason, idempotency | só targets não iniciados; explicita irreversíveis |
| fire | campaign version, trigger context schema, audience preview ref/hash, idempotency, confirmation | teste não compartilha endpoint; no count degraded/zero |
| retry | delivery target/platform selection, current state/version, idempotency, confirmation quando unknown | accepted/confirmed nunca repetidos |
| reconcile | platform/targets unknown, version, idempotency | consulta sem efeito quando provider suporta |
| platform config | current config version, new flow ref/version, idempotency, confirmation | somente readiness verificável; audit completo |

Envelope de erro:

```json
{
  "error": {
    "code": "version_conflict",
    "detail": "presentation.version_conflict",
    "retryable": false,
    "field_errors": {},
    "request_id": "req_...",
    "current_version": 18,
    "actions": []
  }
}
```

HTTP: `401` sessão ausente/expirada; `403` autenticado sem capability; `404` recurso realmente ausente/inacessível conforme anti-enumeration documentada; `409` version/idempotency/state conflict; `422` payload/negócio; `429` throttle com `Retry-After`; `503` dependência/readiness indisponível. O BFF deve preservar status, `Retry-After`, `ETag`, `X-Request-ID` e versão por allowlist.

### 10.6 Compatibilidade e prova

- Schema canonical versionado no backend; TypeScript é gerado, não mantido à mão.
- CI gera em diretório temporário e falha em diff.
- Consumer contract cobre todos endpoints/Actions e payloads v1/v2 durante migração.
- Deprecation tem métrica por client contract, owner e data de remoção.
- Rollback mantém v1 por janela, mas comandos P0 nunca voltam a sem idempotência/consent guard.

## 11. Contrato de alertas acionáveis

### 11.1 O que merece o sino

Entra no sino apenas condição que requer decisão/reparo de uma pessoa dentro de um prazo: aprovação pendente, canal bloqueado que afeta envio próximo, partial/unknown, campanha presa, conflito que impede continuar, consent policy/dependency quebrada. Estado puramente informativo — “publicação terminou”, count normal, histórico — fica no objeto/toast/histórico e não disputa atenção.

### 11.2 Estrutura

```text
AlertCondition
  ref, type, source_ref, source_version, group_key, severity
  owner_role/owner_ref, opened_at, deadline_at, last_evaluated_at
  state: unseen | seen | acknowledged | resolved | expired
  reason_code, impact facts, recommended_action_ref
  resolution_ref, resolved_at, escalation_policy
  actions[]  (resolver canônico; não persistir callable)
```

Invariantes:

- dedupe por `group_key + active condition`, não por texto;
- `seen` prova renderização, `acknowledged` prova que alguém assumiu, `resolved` prova que a fonte deixou de exigir ação;
- um alerta só resolve quando condição/command receipt confirma; fechar a UI não resolve;
- mudança no Announcement resolve/invalida todas as notificações irmãs na mesma reconciliação;
- owner e escalation sobrevivem sessão/navegação;
- alerta desatualizado refaz projection antes de habilitar ação;
- ação inline usa exatamente a mesma permission, version, confirmação e idempotência da tela do objeto;
- failure mantém alerta e editor/contexto; receipt fica associado;
- deep-link abre `/announcements/<ref>#<problema>` ou `/platforms#<canal>`, com contexto já selecionado.

### 11.3 Primary e alternativas

| Condição | Primary | Alternativas pertinentes | Proibido |
|---|---|---|---|
| Aprovação pendente válida | revisar no card/detalhe | rejeitar com motivo; reconhecer/atribuir | approve implícito ao faltar action |
| Readiness bloqueada | abrir reparo do canal exato | cancelar/agendar depois, se autorizado | link genérico “Plataformas” sem âncora |
| Partial com failures retryable | retry somente falhas | abrir resultado/audit | replay da campanha inteira |
| Unknown | reconciliar | escalar owner/suporte | retry automático |
| Version conflict | comparar e rebase | descartar cópia local com confirmação | overwrite silencioso |
| Expirado | arquivar/recriar com fatos atuais | abrir histórico | publicar copy expirada |

### 11.4 Prova e métricas

Testar create/dedupe/assign/seen/ack/resolve/expire/escalate e concorrência de duas actions. Medir `alert_opened_total`, `alert_deduplicated_total`, time-to-ack, time-to-resolution, alert→action conversion/outcome, stale/orphan alerts e reopen rate. Produção observa condition ref e receipt ref; rollback deixa alerts novos read-only, nunca reativa fallback approve.

## 12. Privacidade, consentimento e proteção de audiência

### 12.1 Precedência proposta — gate G-H01

```text
hard legal/global suppression
  > explicit channel OPTED_OUT/revocation
  > campaign/category/frequency/quiet-hours suppression
  > invalid/unreachable/deduplication
  > purpose-specific active subscription/explicit OPTED_IN
  > campaign rule eligibility
```

Uma subscription de “avise quando este SKU voltar” não autoriza uma campanha geral e não sobrevive a um opt-out explícito posterior sem política humana expressa. Ausência, erro de leitura ou estado desconhecido é fail-closed; a UI mostra source degraded, não audiência zero.

### 12.2 Prova de consentimento

`CommunicationConsentEvent` deve ser append-only e conter, no mínimo: subject interno, channel, purpose, state transition, legal basis code, disclosure text version/hash, locale, source, occurred/recorded timestamps, actor class, evidence hash, superseded event e retention class. `CommunicationConsentCurrent` é projeção derivada e reconstruível.

Para subscription: identity normalizada, SKU, alert type, channel, purpose, disclosure version, subscribed/revoked/notified timestamps, source/evidence e unique pending constraint. Oferecer cancelamento/unsubscribe e aplicar revogação no handler direto de stock alert também, não só Marketing.

### 12.3 Snapshot sem exposição

- `AudienceSnapshot` persiste policy/rule/fact versions, count e hash.
- Membership fica em tabela/armazenamento protegido, não em JSON do Announcement, API, Admin comum ou logs.
- Chave preferencial é FK/ref interno; telefone normalizado/cifrado é resolvido o mais tarde possível. Fingerprint não reversível serve para unique/reconciliação, não para contato.
- Aprovação congela o conjunto elegível; recheck de envio só remove por revogação/supressão/invalidez/fadiga, nunca acrescenta.
- A projection expõe counts de exclusão e degraded sources. Min-cohort e rate limit reduzem membership inference.
- Acesso de suporte/DPO requer purpose, step-up e audit. Export tem watermark/expiração e não é objetivo inicial.
- Retenção/erase dependem do gate G-H02. Delete não pode destruir prova legal que precise retenção nem manter contato além dela; usar policy/tombstone documentado.

### 12.4 Frequency, collision e quiet hours

- `collision_key` por purpose/campaign/event evita regras concorrentes gerarem comunicação equivalente.
- Frequency policy por recipient/channel/category em janela móvel; emergency override é capability/audit separado.
- Quiet hours usam timezone explícito do recipient quando confiável; sem timezone, policy de loja conservadora. “Hora preferida” observada não equivale a consentimento nem quiet hours.
- Expiração anterior ao próximo horário permitido suprime/expira; não envia atrasado sem decisão.
- Preview calcula mesma policy version e mostra counts; dispatch revalida.

### 12.5 Segurança e observabilidade

Proibir phone, name, copy, audience rule livre, provider response ou membership em log/metric label/Sentry breadcrumb. Permitidos: refs técnicas, hashes, count buckets, reason codes, state, timestamps e request/receipt IDs. Scanner automatizado usa formatos sintéticos e deny patterns. Incidente `sent_after_optout > 0` é crítico, para fila, preserva evidência e aciona runbook de privacidade.

## 13. Integridade de dispatch e resultado por plataforma

### 13.1 Máquina de estado

Separar decisão do anúncio, execução por plataforma e tentativas:

```text
Announcement: draft → pending_review → approved → dispatching → settled
                  └→ rejected        └→ cancelled/expired

DeliveryTarget: planned → suppressed/cancelled/expired
                      └→ queued → sending → accepted → confirmed
                                      ├→ failed_retryable → queued (nova attempt)
                                      ├→ failed_final
                                      └→ unknown → reconciling → accepted/confirmed/failed
```

`settled` agrega `succeeded`, `completed_with_failures`, `unknown`, `cancelled` ou `expired`; jamais esconde partial. `accepted` tem semântica de provider específica e não é “cliente recebeu”. Plataforma pública sem receipt termina em `accepted/published_unconfirmed`, com copy honesta.

### 13.2 Fronteiras transacionais

1. Decision transaction: lock + validate + snapshot + cohort ref + audit + receipt + outbox.
2. Outbox publisher: claim/lease e directive idempotente depois do commit.
3. Fan-out transaction: cria targets com unique keys em chunks; repetir é no-op verificável.
4. Attempt transaction A: claim target e grava attempt/token antes da rede.
5. Network boundary: timeout tem três categorias; effect-unknown não retorna a queued automaticamente.
6. Attempt transaction B: persiste resposta sanitizada/provider ID/state; callback é idempotente e monotônico.
7. Reconciler: procura attempts/targets stale, consulta provider quando possível e cria Action humana quando não.
8. Aggregator: query/atomic counters derivados; JSON legado não é fonte.

### 13.3 Idempotência por efeito

| Efeito | Chave | Duplicação impedida por | Timeout ambíguo |
|---|---|---|---|
| Decision | actor + resource + client key + payload hash | unique receipt; payload diferente conflita | GET receipt |
| Schedule occurrence | campaign + occurrence instant + trigger/event ID | unique occurrence | reconciler |
| Platform publication | snapshot + platform | unique target + provider idempotency se houver | unknown/manual/provider lookup |
| Recipient message | snapshot + platform + recipient fingerprint | unique target + one active attempt + provider token | unknown; nunca blind retry |
| Notification alert | condition group + active lifecycle | unique active condition | refetch source |
| Stock subscription notification | subscription + occurrence | unique delivery target | mesma policy do ledger |

Evento sem event ID canônico não pode auto-disparar repetidamente; exigir source event ref ou construir collision window explicitamente aprovada.

### 13.4 Plataforma e payload

- Artifact é imutável e content-addressed; handler não recarrega Campaign/Template mutáveis.
- ManyChat deve receber payload por mensagem/target que não dependa de custom field global mutável, ou o owner deve provar atomicidade/isolamento. Até lá, classificar como risco aberto.
- ADR-009 remove fallback direto Meta do caminho normal. Adapter console é apenas ambiente não produtivo e nunca readiness válido em produção.
- Flow/template deve estar ativo, versionado e aprovado tanto no preview quanto no send.
- Payload/erro bruto do vendor fica no boundary redigido. Provider ID permitido sob retention/access definidos.
- Rate limits usam `Retry-After`, jitter, circuit breaker e quota; chunk não monopoliza worker.

### 13.5 Resultado e recovery

Projection fornece por plataforma counts e timestamps por state, última tentativa/error category, freshness e Actions. Retry falha somente nos targets explicitamente selecionados e elegíveis. Cancel declara quantos ainda foram impedidos e quantos já eram irreversíveis. Reconciler periódico detecta:

- approved sem snapshot/outbox;
- outbox/target/attempt com lease stale;
- publishing acima do SLO;
- aggregate diferente do ledger;
- accepted sem confirmação além da janela;
- unknown sem owner/action;
- envio posterior a suppression/expiry.

Runbook nunca manda “rode de novo a campanha”. Ele começa pelo receipt/snapshot/platform, reconcilia efeitos conhecidos e só então habilita ação seletiva.

## 14. Política para IA e conteúdo

### 14.1 Trust boundaries

São não confiáveis: `ai_prompt` administrativo, template, nome/descrição de produto, evento/trigger context, texto anterior e qualquer output do modelo. São fatos canônicos somente valores resolvidos/versionados pelos owners de catálogo/oferta/promoção/estoque/link e identificados por fact ID/hash/as-of.

### 14.2 Regras

1. IA só sugere `body`/`hashtags` sob JSON Schema; não sugere preço, estoque, desconto, link, audience, schedule, platform, template/flow ou consent policy.
2. Prompt separa instruções de sistema, fatos delimitados e conteúdo não confiável. Instrução dentro do conteúdo não ganha autoridade.
3. Claim checker exige que preço, quantidade, validade, urgência, disponibilidade e promoção correspondam a fact ID ainda válido.
4. Output passa por policy de Marca, linguagem, conteúdo ofensivo e limites da plataforma.
5. UI mostra fatos usados, warnings e diff; “Aceitar” apenas edita draft. Approve continua separado e confirmado.
6. Snapshot guarda provider/model ref, policy version, fact hash, suggestion/output hash e diff humano. Não guarda segredo nem PII.
7. Erro/timeout/rate deixa texto atual intacto e oferece continuar manualmente.
8. `requires_approval=false` não autoriza output IA a sair; eventual automação futura é outro projeto/gate.
9. Red-team PT-BR cobre prompt injection, preço promocional inexistente, “últimas unidades” falso, data virada, emoji/Unicode, URL maliciosa, discriminação e tom indevido.

### 14.3 Critérios mensuráveis

- zero claim factual sem fact ID válido no corpus;
- zero URL não canônica gerada;
- zero publicação pela ação de sugestão;
- 100% suggestion auditável por hashes/versions;
- invalid schema/moderação/fact mismatch são bloqueios, não warnings ignoráveis;
- taxa accepted/edited/discarded serve a discovery, não a ranking comercial.

### 14.4 Migração e rollback

Feature flag off por default; executar corpus offline/shadow, depois piloto com revisão humana. Se o provider falhar, desligar somente IA, nunca editor/preview/approve. Mudança de provider/model/prompt policy exige nova avaliação e não reaproveita aprovação de versão anterior.

## 15. Matriz de rotas, viewports, estados e detalhes visuais

### 15.1 Viewports e modos obrigatórios

| ID | Geometria/modo | O que prova |
|---|---|---|
| V-01 | 320×568 | menor mobile suportado, teclado virtual, safe area, sem overflow |
| V-02 | 375×812 | operação com uma mão, CTA no alcance, sheets/forms |
| V-03 | 390×844 | baseline viva desta auditoria e comparação visual |
| V-04 | 768×1024 portrait | tablet, grids, dialogs, teclado |
| V-05 | 1024×768 landscape | transição nav/grid, preview lado a lado |
| V-06 | 1280×800 | desktop operacional comum |
| V-07 | 1440×900 | densidade, max-width, hierarquia |
| V-08 | 200% zoom em viewport 1280 (≈640 CSS px) | WCAG reflow, sem conteúdo/ação perdida |
| V-09 | light e dark | tokens/contraste/status não dependem só de cor |
| V-10 | `prefers-reduced-motion`, forced colors e text spacing | motion, focus, bordas/semântica robustas |

Em mobile, área clicável de ações frequentes fica ≥44×44 px, CTA não fica sob browser/keyboard/safe area, ação perigosa não ocupa posição fácil de toque acidental sem confirmação. Documento não pode ter overflow horizontal a 320 px; tabelas viram cards/scroll interno rotulado sem esconder coluna de estado/ação.

### 15.2 Rotas e estados

| Rota/fluxo | Estados obrigatórios | Geometria/copy/interação | Screenshots mínimas |
|---|---|---|---|
| Gate/login global | checking, anonymous, invalid credentials, rate-limited, expired, forbidden, offline, authenticated | Sem page/fetch atrás; foco no heading/username; dialog/page nomeada; error associado; password manager; Enter; trap/restore; reauth retorna a draft/action | 320 anonymous+error; 390 keyboard; 1280 anonymous; 1280 forbidden; expired com draft |
| `/` painel | loading, empty verdadeiro, pending, stale/degraded, API failure, SSE disconnected, notification badge | Ação antes de KPI; empty só após sucesso; freshness; primary Action contextual; cards inteiros não viram armadilha de foco; números grandes localizados | 320 pending; 390 degraded; 768 empty; 1280 normal; 1440 SSE down |
| Announcement card no painel | default, editing, autosaving/saved/error, conflict, expiring, zero/degraded audience, not ready, now/scheduled, approving, receipt | Draft não salta layout; diff/facts/preview acessíveis; timezone ao lado; confirmação mostra consequence; double click disabled+receipt | 320 edit longo; 390 confirm now; 768 conflict; 1280 platform preview; partial result |
| `/announcements/:id` | loading, 401, 403, true 404, stale version, pending, decided, expired, cancelled, partial, unknown | Não confundir estados; timeline/audit; deep-link ancora problema; after decision mantém receipt/result; back preserva filtro/scroll | 320 403; 390 expired; 768 partial; 1280 pending; 1440 unknown/reconcile |
| `/campaigns` list | loading, empty, degraded, paginated, active/inactive, dependency blocked, toggle conflict | Search/filter persistem; toggle perigoso não é tiny switch direto; dependency count antes de disable/delete; action menu acessível | 320 list; 390 filters; 768 dependency dialog; 1280 dense; 1440 empty |
| Campaign create/edit | new, existing full schema, invalid fields, audience calculating/failed, draft, conflict, recurring schedule edge | Round-trip lossless; progressive disclosure; nenhum hidden field descartado; error summary+field focus; timezone/DST; SKU/collection pickers | 320 keyboard; 390 long rules; 768 validation; 1280 edit full; 1440 conflict diff |
| Fire campaign | initial, count loading/zero/degraded/large, confirmation, throttled, accepted/conflict | Disabled se zero/degraded; blast/readiness/expiry; sem body que bypassa revisão; receipt inline; no arbitrary phone | 320 zero; 390 confirmation; 768 degraded; 1280 large blast; 1440 receipt |
| `/templates` | loading, empty, degraded, list, edit, invalid placeholder/variant/media, dependency blocked, delete | Placeholder docs contextuais; cursor insertion; variante real; delete mostra dependências; unknown variable bloqueia; error preserva form | 320 edit; 390 placeholder; 768 variant; 1280 dependency; 1440 empty |
| `/platforms` | ready, degraded, blocked, unknown, outage, no configured flow, test sandbox pending/result, config conflict | Outage ≠ zero; freshness/capabilities/limits; repair Action exata; config e teste separados; secret nunca aparece | 320 blocked; 390 outage; 768 test receipt; 1280 ready; 1440 conflict |
| `/history` | loading, empty, cursor pages, filters, partial, unknown, audit unavailable | Estado/plataforma/time/ator; “aceito” ≠ “entregue”; filter URL/persist; retry contextual; sem KPI falso | 320 filters; 390 partial; 768 pagination; 1280 normal; 1440 unknown |
| Notification popover/sheet | empty, unseen, seen, acknowledged, resolved, deduped, escalated, stale action | Uma primary; owner/deadline; keyboard; action inline equivalente; deep-link exato; badge reconciliado | 320 sheet; 390 action; 768 dedupe; 1280 popover; stale action |
| 404/error global | true 404, 500, maintenance, offline, unsupported contract | Mensagem honesta, receipt/request ID quando há, retry/back pertinente; não recomendar login para forbidden | 320 offline; 390 404; 1280 500 |

### 15.3 Conteúdo extremo e critérios pixel-a-pixel

Aplicar a todas as rotas relevantes:

- body 1, 280, limite−1, limite, limite+1 e texto muito longo; palavras/URLs sem quebra; 1–10 hashtags; emojis compostos/ZWJ; acentos; RTL smoke; mídia ausente/portrait/landscape/quebrada;
- counts 0, 1, 999, 1.000, 99.999, ≥1 milhão; horários virando dia; timezone/DST; nomes de regra/template longos e iguais no prefixo;
- nenhum truncamento remove estado, diferença de plataforma, consequência ou primary Action; tooltip acessível só complementa;
- headings têm ordem; landmarks/nav/main únicos; label/description/error programáticos; status async usa live region sem spam;
- focus ring visível em ambos temas; ordem segue visual; Esc/cancel não dispara ação; dialog devolve foco ao trigger; destructive primary separado;
- skeleton mantém geometria e tem nome oculto apropriado; loading não dura indefinidamente sem estado/retry;
- cores de success/warning/error têm ícone+texto; contraste WCAG 2.2 AA; gráficos não são necessários para counts operacionais simples;
- sticky headers/footers não cobrem foco/conteúdo; modal cabe com scroll interno e CTA visível com teclado virtual;
- motion apenas reforça mudança, ≤200 ms conforme design, desativada em reduced motion; sem auto-scroll que rouba contexto.

### 15.4 Protocolo de screenshot

Screenshots nomeadas `<route>__<state>__<viewport>__<theme>.png`, capturadas com clock/data/fixtures fixos, sem PII. Para cada mudança visual: before baseline do HEAD, after, diff com threshold explícito e revisão humana; mascaramento só para timestamps/cursor inevitáveis. Além das células acima, capturar focus-visible, 200% zoom, reduced-motion (estado final), light/dark e validation error. Nenhum update indiscriminado de snapshots.

## 16. Budgets de esforço do operador

Budgets são limites do caso comum após dados carregados e cobrem toques, digitação, mudanças de tela, espera, consultas externas, recuperação e certeza. Exceções podem exceder quando isso aumenta segurança. Medir com instrumentação de tarefa e 5–8 gestores, sem conteúdo/PII.

| Tarefa | Toques/cliques | Digitação | Mudanças de tela | Espera percebida | Consulta externa | Recuperação | Certeza ao concluir |
|---|---:|---:|---:|---:|---:|---|---|
| Aprovar anúncio pronto | ≤3 ações significativas incluindo confirmação | 0 | 0; inline/detail contextual | preview ≤1 s cache/fresh; command ack ≤1 s | 0 | receipt no mesmo contexto; retry seguro | versão, cohort, horário e plataformas resumidos; state por canal |
| Ajustar texto e aprovar | ≤5 + edição | só o texto; facts/links pré-preenchidos | 0 | autosave ≤500 ms local/≤1 s servidor | 0 | refresh/401/conflict preservam draft | diff + artifact hash/preview final |
| Agendar | ≤4 | 0 quando default pertinente; no máximo data/hora | 0 | validação imediata | 0 | erro foca campo e mantém tudo | instante com data, timezone, expiry e quiet-hour outcome |
| Criar regra comum | ≤7 | nome; filtros por controles | ≤1 | audience count ≤2 s | 0 | draft/round-trip/conflict | trigger, exclusões, dedupe e próximos occurrences |
| Disparar regra manual | ≤4 após escolher regra | 0 | 0 | count ≤2 s; ack ≤1 s | 0 | receipt; double touch idem | blast/readiness/schedule e result tracking |
| Resolver partial retryable | ≤3 | 0 | 0 | ack ≤1 s | 0 | retry só targets falhos | counts before/after e remaining unknown |
| Tratar unknown | ≤3 para reconciliar/escalar | 0 | ≤1 para audit detalhado | feedback ≤1 s; provider conforme SLO | no máximo Action de console oficial quando indispensável | nunca reenvio cego | linguagem explícita de incerteza/owner |
| Corrigir readiness | ≤4 no app para config conhecida | ref selecionada, não redigitada | ≤1 âncora exata | check ≤3 s ou async receipt | 0 salvo autenticação oficial do provider | config CAS/rollback | last check, flow version, safe-test result |
| Retomar após sessão | login + 1 reconfirmação | credencial via password manager | 0 | retorno ≤1 s após auth | 0 | draft/action restaurado | mostra que version/readiness foram revalidados |

Definições:

- **Toque significativo:** decisão/entrada; scroll e foco não mascaram fluxo ruim e devem ser observados separadamente.
- **Espera:** acima de 400 ms recebe feedback; acima do budget oferece cancel/background receipt; nunca spinner eterno.
- **Recuperação:** volta ao ponto com conteúdo e selections intactos; não apenas “tente novamente”.
- **Certeza:** o final distingue accepted/confirmed/partial/unknown e mostra próximo passo. Toast isolado não atende.

Se discovery mostrar budget incompatível com segurança, Produto documenta exceção e motivo. Não remover confirmação de blast para bater meta de toques.

## 17. Observabilidade e SLO

### 17.1 SLO iniciais propostos — calibrar em G-H08

| Jornada/serviço | SLI | Objetivo inicial | Alerta |
|---|---|---:|---|
| Board projection | p95 server latency, payload/query budget | ≤500 ms, ≤300 KB, query budget fixado por teste | burn rate 5m/1h |
| Navegação | LCP p75 / INP p75 / CLS p75 | ≤2,5 s / ≤200 ms / ≤0,1 no mobile piloto | regressão por deploy |
| Audience preview | p95 até cohort máximo acordado | ≤2 s; timeout vira degraded, nunca zero | >2 s ou errors >1% |
| Command acceptance | p95 POST→receipt persisted | ≤1 s | errors/conflicts por code |
| Immediate dispatch | p95 receipt→primeiro target queued | ≤10 s | outbox age/stuck |
| Scheduled dispatch | p95 lag após instante permitido | ≤30 s | occurrence lag/stale lease |
| Result freshness | ledger change→projection | ≤10 s com SSE/poll | stale >30 s |
| Efeito duplicado confirmado | taxa | **0** | crítico imediato |
| Envio pós-opt-out/expiry | taxa | **0** | crítico imediato, freeze |
| Unknown | proporção e idade | <0,1%; nenhum >15 min sem owner | high/paging conforme canal |
| Partial sem Action | count | **0** | high |
| Readiness | freshness do check | <5 min antes de blast; policy por canal | block action se stale |
| Draft recovery | taxa de restauração após 401/refresh | ≥99,9% para draft confirmado salvo | product alert |

Disponibilidade geral não pode esconder segurança: mesmo dentro do error budget, consent violation/duplicate confirmado é incidente.

### 17.2 Métricas

- `marketing_command_total{kind,outcome}` e `marketing_command_seconds{kind}`;
- `marketing_outbox_age_seconds`, `marketing_stuck_total{stage}`;
- `marketing_delivery_target_total{platform,state}` e `marketing_delivery_attempt_total{platform,outcome}`;
- `marketing_duplicate_prevented_total{effect}`, `marketing_unknown_age_seconds{platform}`;
- `marketing_suppressed_total{reason,platform}`, `marketing_consent_violation_total`;
- `marketing_audience_resolution_seconds{source_state}`, `marketing_audience_size_bucket`;
- `marketing_projection_seconds{projection}`, `projection_bytes`, `projection_queries`;
- `marketing_readiness{platform,state}`, `readiness_age_seconds`;
- `marketing_alert_total{type,lifecycle}`, time-to-ack/resolve;
- `marketing_sse_connection{state}`, invalidations, refetch outcomes, poll fallback;
- `marketing_ai_total{outcome}`, claim/moderation failures;
- frontend Web Vitals, session recovery, conflict and action outcome.

Labels proibidas: recipient/customer/phone, announcement/campaign ref individual em métricas, body/prompt, URL, raw error/provider response. Refs ficam em trace/log access-controlled com retenção.

### 17.3 Logs, traces e audit

Um correlation trace liga request→command receipt→snapshot→outbox→target aggregate→attempt, com IDs técnicos. Log usa allowlist; exception é classificada/sanitizada. Audit append-only registra ator/capability/reason/version/hash e não é substituído por log. Sentry remove PII, query, cookie, auth header, request body e provider body por teste automatizado.

### 17.4 Alertas operacionais

- crítico: consent violation, confirmed duplicate, credential leak signal, blast fora de policy;
- alto: unknown envelhecido, approved sem snapshot/outbox, publishing/lease stale, reconciliation mismatch, partial sem Action, readiness falsa;
- médio: error budget burn, audience/readiness source degraded, notification orphan, SSE reconnect storm, dependency version drift;
- baixo/ticket: docs/contract freshness, visual/a11y regression não deployada.

Cada alerta aponta para runbook e filtro por receipt/platform/stage, nunca para dashboard genérico.

### 17.5 Health e runbooks

Separar `/health/live` (processo) de `/health/ready` (BFF→Django/session endpoint sintético seguro, DB/queue essenciais). Provider readiness é cacheada/telemetrizada e não precisa derrubar liveness. Runbooks obrigatórios:

1. `marketing-stuck-command.md`;
2. `marketing-partial-retry.md`;
3. `marketing-unknown-provider-effect.md`;
4. `marketing-channel-readiness-outage.md`;
5. `marketing-consent-or-privacy-incident.md`;
6. `marketing-bad-content-or-link.md`;
7. `marketing-cancel-and-reconcile.md`;
8. `marketing-rollout-rollback.md`.

Cada um contém sintomas, queries read-only, freeze/circuit, decisões proibidas, comunicação, recuperação idempotente e fechamento/reconciliação.

## 18. Estratégia completa de testes

### 18.1 Pirâmide e suites

| Camada | Cobertura obrigatória | Gate |
|---|---|---|
| Unitário | validators/schema, state transitions, consent precedence, dedupe, schedule/timezone/expiry, artifact renderer, aggregation, presentation enum | rápido em todo commit |
| Model/migration | constraints, reversibilidade, legacy backfill, retention, indexes, state invariants | migration CI em DB real equivalente |
| API/contract | auth/RBAC, CSRF, idempotency, version conflict, Actions, errors/headers/cursor, OpenAPI→TS | snapshots + generated diff clean |
| Integração | decision transaction→outbox→handler→fake provider→ledger→projection/alert | DB/queue reais de teste |
| Concorrência | approve/edit/reject/cancel, scheduler/expiry, duplicate event/directive, target claim, callback/retry | barreiras determinísticas, repetir ≥100 quando pertinente |
| E2E navegador | login/session, board→approve/schedule, rule/template, partial/retry, readiness, alerts/deep-link | Playwright local seeded, sem rede/prod |
| A11y | axe, keyboard, focus trap/restore, screen reader semantics, zoom/reflow, forced colors/reduced motion | zero serious/critical; checklist manual |
| Visual | matriz seção 15, content extremes, light/dark, screenshots/diffs | revisão humana de diff |
| Segurança | permission matrix/IDOR/CSRF/XSS/template injection/SSRF/open redirect/cache/headers/rate/PII/secret/webhook replay | scanner + testes adversariais |
| Carga | audience counts, fan-out, history cursor, API/BFF, worker chunks, DB locks | peak acordado + margem 2× sem violar SLO |
| Caos | kill/timeout nos crash points, provider 429/5xx/slow, DB deadlock, queue/SSE down, cache stale, IA off | convergência e Action/runbook corretos |

### 18.2 Matriz adversarial mínima

| Cenário | Oráculo |
|---|---|
| Dois taps com mesma key/payload | um receipt/efeito; segunda resposta referencia o mesmo |
| Mesma key, payload diferente | `409 idempotency_conflict`; nenhum efeito novo |
| Edit e approve em versões diferentes | uma vence; outra recebe conflict e draft preservado |
| Approve e reject simultâneos | uma transição auditada; nenhuma publicação da decisão perdedora |
| Crash antes do commit | nenhum snapshot/outbox/efeito |
| Crash após commit antes de enqueue | reconciler publica outbox uma vez |
| Crash após vendor effect antes da resposta | `unknown`; sem retry cego; reconcile/owner |
| Dois workers no mesmo target | unique/lease; no máximo um attempt ativo |
| Callback duplicado/atrasado | transição idempotente/monotônica; state não regride |
| Partial de uma plataforma | geral `completed_with_failures`; retry só failed targets |
| Preferred hour `vip@9` | selector entrega exatamente cohort da wave, não zero silencioso |
| Opt-out após approve | target suprimido no send; cohort não cresce com opt-in tardio |
| Duas regras colidem | collision/frequency policy impede spam e explica count |
| Source audience/offers down | degraded bloqueia ação; não vira empty/zero |
| Promo expira antes do horário | schedule bloqueado ou anúncio expira conforme policy |
| Timezone/DST/virada do dia | preview/receipt/worker escolhem o mesmo instante permitido |
| Permissão revogada após load | POST `403`; nenhuma mutation; draft preservado |
| Sessão expira na confirmação | reauth, refetch/version/readiness, reconfirma; no auto-resubmit |
| Preview requests fora de ordem | somente resposta do input/version atual renderiza |
| Variável/variant | unknown bloqueia; variant artifact=adapter payload |
| ManyChat flow inactive/outage | readiness bloqueado/unknown; config arbitrária rejeitada |
| Imagem URL host privado/redirect | rejeitada sem fetch inseguro |
| IA injection/claim falso | output bloqueado, texto anterior intacto |
| SSE cai | indicador degraded, backoff, polling/focus refetch; sem storm |
| History durante writes | cursor estável, sem duplicação/perda |

### 18.3 Volume e query budgets

Fixtures: 0/1/100/10k/100k candidates conforme capacidade acordada; overlaps altos; consent/suppression mistos; 1/5/todos canais; history 10k; callbacks burst. Medir query count, scanned rows, memory, transaction/lock time, queue depth e p95. Proibir uma query global de todos marketable customers quando cohort é pequeno e N+1 de loyalty/profile.

### 18.4 Fidelidade e qualidade do harness

- Vue warnings tornam teste falho; stubs declarados e props completas.
- E2E fala com BFF/Django/DB seeded e fake adapter, não mock de composable.
- Fake adapter registra artifact hash/idempotency e simula effect-lost-response.
- Clock/timezone congelados; nenhum `sleep` frágil.
- Testes de propriedade para aggregation/consent/state.
- Não acessar internet, app vivo, telefone ou provider real em CI.
- Sandbox provider é suite manual autorizada, separada, com target verificado e receipt; não é gate de todo commit.

### 18.5 Gates mínimos por WP

Todo WP roda suite direcionada + `npm test`, lint, typecheck, build, backend Marketing focused. WPs Admin rodam `make admin`. Mudança shared roda consumers do operator-kit. Antes de piloto: suite backend completa pertinente, E2E, a11y, visual, security, load e chaos. Registrar contagens, duração, warnings e flakes; “passou” sem comando/commit/ambiente não é evidência.

## 19. Rollout, feature flags, migrations, piloto e rollback

### 19.1 Flags mínimas

| Flag | Default | Controla | Failsafe |
|---|---|---|---|
| `marketing_commands_v2_write` | off | receipts/CAS/snapshot/outbox como comando | off bloqueia comandos v2 não compatíveis; não cai em inseguro |
| `marketing_audience_policy_v2` | off/audit | precedence/snapshot/suppression | opt-out guard novo permanece on mesmo em rollback |
| `marketing_delivery_ledger_shadow` | on após deploy schema | dual-write/shadow ledger | pausa consumer, preserva dados |
| `marketing_delivery_ledger_source` | off | read/aggregate/dispatch pelo ledger | legacy somente para itens legacy conhecidos |
| `marketing_projection_v2` | off por cohort | schema/Actions/client v2 | frontend aceita v1 na janela |
| `marketing_ai_assist_v2` | off | sugestão IA | editor manual continua |
| `marketing_auth_gate_v2` | off→on cedo | mount/fetch protegido | fallback page segura, não fundo montado |
| `marketing_admin_config_v2` | off | poucos edits Admin aprovados | unregister edit, audit permanece |

Flags não podem desligar consent hard suppression, redaction, CSRF, permission recheck ou duplicate unique constraint.

### 19.2 Fases

| Fase | Ação | Entrada | Saída/abort |
|---|---|---|---|
| 0 Freeze/decisão | congelar expansão/auto-send; fechar G-H01–04 | plano aceito | policies assinadas; abort mantém read-only/legado contido |
| 1 Expand schema | migrations aditivas command/snapshot/audience/ledger/audit | backup/estimate/rehearsal | schema ok, app legado compatível; rollback migration ensaiado |
| 2 Shadow | dual-write/resolver/artifact/ledger sem mudar efeito | observabilidade ativa | reconciliação por 7–14 dias ou volume acordado; mismatch zero/explicado |
| 3 Internal canary | usuários internos sintéticos, canal sandbox | security/QA gates | nenhum P0, SLO/carga/chaos passam |
| 4 Pilot | 5–8 gestores/loja/campanhas e canais explicitamente limitados | owners/on-call/runbooks | task success, zero consent/duplicate, partial/unknown dentro SLO |
| 5 Progressive | 5%→25%→50%→100% por command/cohort | go/no-go por estágio | burn rate saudável e reconciliação limpa; abort congela próximo estágio |
| 6 Cutover | ledger/projection v2 source; UI v2 default | compat clients conhecidos | legado sem writes; rollback window aberta |
| 7 Contract/legacy cleanup | remover v1/JSON paths/perm ampla em release posterior | zero uso medido + backup | docs finalizadas; rollback por restore compatível documentado |

Nenhuma fase implica deploy automático. Cada avanço exige autorização G-H09/G-H10.

### 19.3 Migration discipline

- Expand/contract; migrations pequenas, com estimate de lock/rows e rehearsal em cópia/synthetic scale.
- Constraints `NOT VALID`/validação posterior ou equivalente quando DB permitir; índices online/concurrent conforme ambiente.
- Backfill resumível, idempotente, throttled, com cursor/checkpoint e métricas; nunca inventar recipient receipt histórico.
- Itens legacy recebem version/policy explícitas. Pending/scheduled só migram depois de revalidar facts/consent/readiness; conflito bloqueia e cria Action.
- Generated schemas/lockfile/migration number requerem coordenação multiagente e commits isolados.
- Contract drop apenas em release separada após métricas de uso zero e backup/restore testado.

### 19.4 Piloto e go/no-go

Piloto usa campanhas sintéticas/sandbox primeiro; qualquer envio real exige autorização específica, cohort limitado e mensagem aprovada. Instrumentar task success, budgets, conflict/recovery, partial/unknown, SLO e feedback do gestor. Go se: zero P0, zero consent violation/duplicate, 100% receipts reconciliados, SLO dentro budget, runbook drill passa e gates humanos assinam. No-go/freeze se: unknown sem owner, mismatch snapshot/payload/cohort, PII em telemetry, rollback não ensaiado, readiness stale ou permissão indevida.

### 19.5 Rollback

1. Parar expansão e novos commands perigosos por circuit/flag; não repetir unknown.
2. Preservar receipts/snapshots/ledger/audit e capturar deploy marker.
3. Pausar consumers novos; deixar reconciler read-only identificar efeitos.
4. Reverter UI/projection compatível por flag/imagem; manter consent/redaction/idempotency guards.
5. Para schema, preferir forward fix; migration reversa só após prova de que não perde evidência.
6. Reconciliar cada command in-flight por state/plataforma e criar Actions/owners.
7. Comunicar incident owner, escopo, efeitos conhecidos/desconhecidos e decisão antes de reabrir.

Rollback termina quando o sistema está estável **e** efeitos são reconciliados; “versão anterior no ar” não basta.

## 20. Manifesto arquivo por arquivo

Este manifesto é uma lista de intervenção, não autorização para alterar todos os arquivos. O executor confirma o HEAD, reduz cada patch ao mínimo e coordena paths compartilhados. “Validar” pode terminar em nenhuma mudança quando o contrato já estiver correto.

### 20.1 Todo o Marketing Nuxt

| Arquivo | Intervenção/prova esperada | WP |
|---|---|---|
| `surfaces/marketing-nuxt/.gitignore` | Validar cobertura apenas de outputs/cache locais; não esconder goldens/contracts exigidos. | 12 |
| `surfaces/marketing-nuxt/README.md` | Corrigir rotas reais, auth/BFF/SSE, comandos/gates e execução local; remover `/rules` e `/posts/:id` stale. | 12 |
| `surfaces/marketing-nuxt/app/app.vue` | Gatear mount/fetch por session; landmarks/nav; notification lifecycle; nenhum fundo protegido sob login. | 05, 08, 10 |
| `surfaces/marketing-nuxt/app/assets/css/tailwind.css` | Tokens operator-kit, touch/focus/contrast/reflow/reduced motion e font self-hosted; remover cor raw divergente. | 10 |
| `surfaces/marketing-nuxt/app/components/AnnouncementCard.vue` | Draft/version/artifact hash, Actions, publish mode enum, confirmação, expiry/readiness/audience, receipt/partial/recovery. | 02, 05–07 |
| `surfaces/marketing-nuxt/app/components/AnnouncementPreview.vue` | Resolver único, abort+epoch, variants/limits/media/link/facts/failure/freshness; preview hash. | 06, 07 |
| `surfaces/marketing-nuxt/app/components/AnnouncementTemplateForm.vue` | Placeholder strict/cursor, source de imagem canônica, URL policy, variants e AI policy validada; mutation error. | 06, 09 |
| `surfaces/marketing-nuxt/app/components/CampaignForm.vue` | Round-trip integral de rules/trigger/platform/notify/schedule, schema, draft/conflict, timezone; eliminar truncamento silencioso. | 01, 07 |
| `surfaces/marketing-nuxt/app/components/CampaignTopBar.vue` | Notification Actions/lifecycle, badge reconciliado, session/keyboard/mobile. | 08, 10 |
| `surfaces/marketing-nuxt/app/components/FireCampaignPanel.vue` | Audience preview obrigatório, zero/degraded bloqueado, filters canônicos, confirmation/idempotency/receipt; sem body bypass. | 01, 02, 04, 07 |
| `surfaces/marketing-nuxt/app/components/OperatorLogin.vue` | Dialog/page semântica, focus trap/restore, inert, 401/403/429/offline e retomada de draft/action. | 10 |

#### Primitivos UI

Cada arquivo abaixo deve ser comparado com o primitive equivalente no `operator-kit`/design canon; consolidar upstream apenas se reutilizável por mais de uma surface e coordenado. O gate comum é alvo ≥44×44, ref forwarding, keyboard/focus-visible, ARIA correta, dark/light, reduced motion, sem token raw e testes sem warnings.

| Arquivo | Responsabilidade específica | WP |
|---|---|---|
| `app/components/Ui/Alert/Alert.vue` | Semântica por severity/status e live behavior sem anunciar conteúdo repetido. | 10 |
| `app/components/Ui/Alert/Description.vue` | Associação com title/action e wrapping de texto/URL. | 10 |
| `app/components/Ui/Alert/Title.vue` | Hierarquia/nome acessível sem heading saltado. | 10 |
| `app/components/Ui/Badge.vue` | Estado não depende só de cor; counts grandes. | 10 |
| `app/components/Ui/Button.vue` | 44×44, loading/disabled reason, double-submit guard e foco. | 04, 10 |
| `app/components/Ui/Card/Action.vue` | Ordem/área da action; sem card clicável aninhando controles. | 10 |
| `app/components/Ui/Card/Card.vue` | Landmark/group e responsive bounds. | 10 |
| `app/components/Ui/Card/Content.vue` | Wrapping, density e skeleton geometry. | 10 |
| `app/components/Ui/Card/Description.vue` | Contraste/tamanho legível, associação. | 10 |
| `app/components/Ui/Card/Footer.vue` | CTA mobile/safe area e reflow. | 10 |
| `app/components/Ui/Card/Header.vue` | Hierarquia e truncamento seguro. | 10 |
| `app/components/Ui/Card/Title.vue` | Heading level configurável/canônico. | 10 |
| `app/components/Ui/Dialog/Dialog.vue` | Estado controlled e lifecycle. | 10 |
| `app/components/Ui/Dialog/Trigger.vue` | Trigger/ref/expanded/controls. | 10 |
| `app/components/Ui/Dialog/Portal.vue` | Portal SSR/hydration. | 10 |
| `app/components/Ui/Dialog/Overlay.vue` | Inert/pointer/contrast/reduced motion. | 10 |
| `app/components/Ui/Dialog/Content.vue` | role/modal/name/description/trap/scroll/viewport. | 04, 10 |
| `app/components/Ui/Dialog/Header.vue` | Estrutura visual/semântica. | 10 |
| `app/components/Ui/Dialog/Title.vue` | ID e accessible name. | 10 |
| `app/components/Ui/Dialog/Description.vue` | ID e consequência associada. | 04, 10 |
| `app/components/Ui/Dialog/Footer.vue` | Ordem safe/destructive e mobile keyboard. | 04, 10 |
| `app/components/Ui/Dialog/Close.vue` | Nome, target e foco restaurado; não confirma. | 10 |
| `app/components/Ui/FilterChip.vue` | Pressed state, 44×44 e label/count. | 10 |
| `app/components/Ui/IconButton.vue` | Accessible name/tooltip, 44×44, disabled reason. | 10 |
| `app/components/Ui/Input.vue` | label/help/error/autocomplete/required e touch. | 10 |
| `app/components/Ui/Popover/Popover.vue` | Estado/foco/escape/outside click. | 10 |
| `app/components/Ui/Popover/Trigger.vue` | expanded/controls/ref. | 10 |
| `app/components/Ui/Popover/Anchor.vue` | Posicionamento em zoom/viewport. | 10 |
| `app/components/Ui/Popover/Portal.vue` | SSR/z-index sem escapar modal. | 10 |
| `app/components/Ui/Popover/Content.vue` | role, focus, collision/overflow mobile. | 08, 10 |
| `app/components/Ui/Popover/Arrow.vue` | Decorativo, contraste; esconder de AT. | 10 |
| `app/components/Ui/Popover/Close.vue` | Nome/target/focus. | 10 |
| `app/components/Ui/Popover/X.vue` | Ícone decorativo, não control duplicado. | 10 |
| `app/components/Ui/SearchInput.vue` | label, clear action 44×44, debounce/cancel, no hidden submit. | 07, 10 |
| `app/components/Ui/Separator.vue` | Decorative vs semantic role correto. | 10 |
| `app/components/Ui/Sheet/Sheet.vue` | Estado/lifecycle mobile. | 10 |
| `app/components/Ui/Sheet/Trigger.vue` | expanded/controls/ref. | 10 |
| `app/components/Ui/Sheet/Portal.vue` | SSR/z-index. | 10 |
| `app/components/Ui/Sheet/Overlay.vue` | inert/pointer/reduced motion. | 10 |
| `app/components/Ui/Sheet/Content.vue` | dialog semantics, trap, safe area, keyboard/scroll. | 08, 10 |
| `app/components/Ui/Sheet/Header.vue` | Hierarquia. | 10 |
| `app/components/Ui/Sheet/Title.vue` | Accessible name. | 10 |
| `app/components/Ui/Sheet/Description.vue` | Associated description. | 10 |
| `app/components/Ui/Sheet/Footer.vue` | Sticky CTA sem ocluir conteúdo/foco. | 10 |
| `app/components/Ui/Sheet/Close.vue` | Nome/44×44/focus restore. | 10 |
| `app/components/Ui/Sheet/X.vue` | Decorativo. | 10 |
| `app/components/Ui/Sonner.vue` | Live region, dedupe, mobile viewport; toast não é receipt. | 07, 10 |
| `app/components/Ui/Textarea.vue` | Label/error/count, resize/mobile, texto extremo. | 06, 10 |
| `app/components/Ui/Toolbar.vue` | Role/roving focus só se semanticamente toolbar; responsive wrap. | 10 |
| `app/components/Ui/Tooltip/Tooltip.vue` | Estado e touch alternative. | 10 |
| `app/components/Ui/Tooltip/Trigger.vue` | Accessible name não depende do tooltip. | 10 |
| `app/components/Ui/Tooltip/Portal.vue` | SSR/z-index. | 10 |
| `app/components/Ui/Tooltip/Content.vue` | role/id, hover+focus, viewport collision. | 10 |
| `app/components/Ui/Tooltip/Arrow.vue` | Decorativo/contraste. | 10 |
| `app/components/Ui/Tooltip/Provider.vue` | Delay/reduced motion e consistência. | 10 |

Os paths da tabela de primitivos são relativos a `surfaces/marketing-nuxt/`; todos foram enumerados.

#### Composables, páginas, contratos e runtime

| Arquivo | Intervenção/prova esperada | WP |
|---|---|---|
| `app/composables/useAnnouncementTemplates.ts` | Client gerado, cursor, errors/degraded, version/idempotency e mutation receipts. | 05–07 |
| `app/composables/useAudienceCount.ts` | Abort/epoch, min cohort/throttle, exclusion/degraded/freshness e cache key versionada. | 01, 05, 07 |
| `app/composables/useCampaignBoard.ts` | Projection v2, ETag, SSE invalidate/refetch, visibilidade/poll/backoff e degraded state. | 05, 11 |
| `app/composables/useCampaignHistory.ts` | Cursor/filter, aggregate honesto, retry/reconcile Actions. | 03, 05, 07 |
| `app/composables/useCampaigns.ts` | Commands/receipts/version; remover toast que atribui zero a “sem consentimento” sem evidência. | 02, 05, 07 |
| `app/composables/usePlatforms.ts` | Readiness state/freshness/error; config CAS/action/receipt. | 04–06 |
| `app/composables/useUserNotifications.ts` | Lifecycle/cursor/Action/refetch, SSE cleanup/backoff e sibling reconciliation. | 05, 08, 11 |
| `app/composables/useWhatsAppTemplate.ts` | Zero vs outage, active flow, safe test/config, throttle/idempotency. | 04, 06 |
| `app/pages/index.vue` | Action-first board; empty/degraded honest; KPIs operacionais depois da decisão; route matrix. | 05, 07, 10 |
| `app/pages/announcements/[id].vue` | Distinguir auth/not-found/state, manter receipt/result, timeline/partial/recovery/deep-link. | 02, 03, 05, 07 |
| `app/pages/campaigns.vue` | List/cursor/dependency, safe activate/delete, form/fire workflow e round-trip. | 04, 05, 07 |
| `app/pages/templates.vue` | Mutations/versions/errors/dependencies/variants e delete confirmation. | 04–07 |
| `app/pages/platforms.vue` | Readiness/action/config/test sandbox e estados zero/outage/unknown. | 04–07 |
| `app/pages/history.vue` | Cursor/filters, estados por plataforma, receipt/audit/retry/reconcile. | 03, 05, 07 |
| `app/presentation/campaign.ts` | Mapeamento exaustivo enum→copy/icon/tone; fallback seguro e sem lógica de autorização. | 05 |
| `app/types/campaign.ts` | Substituir espelho manual por re-export/client gerado; tipos de state/action/error exatos. | 05 |
| `app/utils/api.ts` | Base URL consistente, error/header/idempotency/request ID/ETag; não hardcode divergente. | 04, 05, 10 |
| `app/utils/operatorSession.ts` | Remover duplicação ou alinhar shared: 401 expired, 403 forbidden, preservação de draft. | 07, 10 |
| `server/api/v1/[...path].ts` | Proxy allowlist de status/headers/cookie/location, CSRF/origin, cache/security, timeout/body limits. | 04, 05, 10, 11 |
| `server/routes/sse/notifications.ts` | Manter canal pessoal server-derived/404 anon; headers, abort/cleanup/backoff tests. | 08, 10, 11 |
| `nuxt.config.ts` | Security headers/runtime base, self-host font, operator-kit, source maps/telemetry seguros. | 10, 12 |
| `package.json` | Scripts E2E/a11y/contracts; dependências coerentes, sem upgrade fora de escopo. | 12 |
| `package-lock.json` | Regenerar em commit isolado para satisfazer manifesto; provar `npm ci`; coordenação obrigatória. | 12 |
| `eslint.config.mjs` | Fail em warnings relevantes/contratos sem enfraquecer base compartilhada. | 12 |
| `tsconfig.json` | Incluir client gerado/tests sem relaxar strictness. | 05, 12 |
| `vitest.config.ts` | Harness Vue sem warnings, cobertura e setup canônico; não mascarar componentes. | 00, 12 |
| `public/favicon.ico` | Validar branding/contraste apenas; nenhuma mudança se correto. | 10 |
| `public/robots.txt` | Confirmar política para surface operacional; não confiar em robots como controle de acesso. | 10 |

#### Testes frontend existentes e novos

| Arquivo | Mudança de contrato | WP |
|---|---|---|
| `tests/campaign.test.ts` | Projection/actions/presentation/error/date/metric v2; remover expectativas do contrato stale. | 00, 05 |
| `tests/components/AnnouncementCard.test.ts` | now flag enum, atomic content, conflict/draft/confirm/result; fornecer props/stubs reais e zero warnings. | 00, 02, 07 |
| `tests/components/CampaignForm.test.ts` | Round-trip completo, schedule edge, unknown fields, validation; zero warnings. | 00, 07 |
| `tests/components/FireCampaignPanel.test.ts` | zero/degraded block, blast confirm/idempotency/receipt e filtros canônicos. | 00, 04, 07 |
| `tests/templatePickerReachable.test.ts` | Readiness/keyboard/variant; evitar teste meramente textual. | 06, 10 |
| `tests/e2e/**` (novo) | Rotas/jornadas seeded da seção 15; auth/session/partial/conflict. | 07, 10, 12 |
| `tests/a11y/**` (novo) | axe/keyboard/focus/zoom/modes. | 10, 12 |
| `tests/visual/**` (novo) | Screenshots/diffs nomeados e content extremes. | 10, 12 |
| `tests/contracts/**` (novo) | Schema/generated drift/Actions/API error. | 00, 05 |

### 20.2 Backend API, projections, domínio e workers

| Arquivo/caminho | Intervenção/prova esperada | WP |
|---|---|---|
| `shopman/backstage/api/marketing.py` | Separar query/commands, schema strict, RBAC, version/idempotency/confirmation/throttle, atomic service, cursor/error envelope; test sandbox isolado. | 02, 04–06 |
| `shopman/backstage/projections/marketing.py` | Projection pura v2 + Actions/freshness; ledger metrics; sem copy/PII/cortes silenciosos; expiry correto. | 03, 05 |
| `shopman/backstage/api/notifications.py` | Sem fallback approve; lifecycle/action resolver/receipts/perms/cursor/reconciliation. | 04, 05, 08 |
| `shopman/backstage/api/permissions.py` | Permission classes por capability e 401/403 corretos. | 04 |
| `shopman/backstage/api/urls.py` | Rotas v2/commands/receipts/reconcile sem quebrar compatibilidade; names claros. | 02–05 |
| `shopman/backstage/api/projections.py` | Validar convenções/version/error/actions compartilhadas; não duplicar serializer Marketing. | 05 |
| `shopman/backstage/permissions.py` | Predicados canônicos e role matrix; deny default. | 04 |
| `shopman/shop/eventstream.py` | Invalidation-only, permission/revocation/canal pessoal e nenhum payload sensível. | 05, 08, 11 |
| `shopman/shop/models/campaign.py` | Validadores/schema ou relações tipadas; version/state; snapshot/command/outbox/ledger/audit conforme ownership final. | 01–03 |
| `shopman/shop/models/promotion.py` | Manter ownership; refs/facts/version/validity usados pelo artifact, sem duplicar preço. | 06 |
| `shopman/shop/models/user_notification.py` | Lifecycle/source/group/owner/resolution; events imutáveis. | 08 |
| `shopman/shop/services/campaign.py` | State machine transacional, snapshot/artifact, strict render, sem mutable reload/RMW, AI boundary. | 02, 03, 06, 09 |
| `shopman/shop/services/campaign_schedule.py` | Occurrence unique, timezone/expiry/quiet hour, lock/lease/cancel/recovery. | 01–03 |
| `shopman/shop/services/campaign_identity.py` | Chaves determinísticas de command/occurrence/target, collision policy e compatibilidade. | 02, 03 |
| `shopman/shop/services/audience.py` | Consent precedence, explainability/dedupe/query budget, snapshot e recheck subtract-only. | 01, 11 |
| `shopman/shop/services/notification.py` | Delivery boundary/consent comum, receipt/error/redaction; não criar segundo ledger. | 01, 03, 08 |
| `shopman/shop/services/offers.py` | Facts canônicos/as-of/link/promotion validity para artifact; campanha não vende. | 06 |
| `shopman/shop/services/promotions.py` | Resolver policy/version, click-time authority e schedule validity. | 06 |
| `shopman/shop/services/manychat_flows.py` | Active flow/readiness/freshness/outage/cache/CAS; no config cega. | 04, 06 |
| `shopman/shop/services/whatsapp_verify.py` | Readiness/verification sanitizada; alinhar ManyChat-only. | 06 |
| `shopman/shop/handlers/campaign.py` | Claims/ledger/chunks/leases/recheck/unknown/retry/aggregate; corrigir preferred-hour e no mutable content. | 02, 03 |
| `shopman/shop/handlers/notification.py` | Integrar delivery target/consent/idempotência quando aplicável; evitar caminhos paralelos. | 01, 03 |
| `shopman/shop/handlers/stock_alerts.py` | Recheck global opt-out, claim transacional e ledger; subscription idempotente. | 01, 03 |
| `shopman/shop/management/commands/arm_scheduled_campaigns.py` | Idempotent occurrence/catch-up horizon/locks/metrics/dry-run. | 02, 03, 11 |
| `shopman/shop/management/commands/maintenance_worker.py` | Reconciler/outbox/expiry commands ordenados, budgets, health e graceful shutdown. | 02, 03, 11 |
| `shopman/shop/management/commands/setup_groups.py` | Mapear capabilities novas em grupos sem perm ampla residual. | 04 |
| `shopman/shop/management/commands/send_test_announcement.py` | Manter explicitamente não audience/prod; synthetic/sandbox safeguards, audit e nome/copy claros. | 04 |
| models/migrations novos de `CommandReceipt`, `ApprovedAnnouncementSnapshot`, `AudienceSnapshot`, `DeliveryTarget`, `DeliveryAttempt`, `AuditEvent`, `Outbox` | Expand/contract, constraints/indexes/retention; nomes/apps finais escolhidos por Arquitetura para evitar duplicar infraestrutura existente. | 01–03 |

### 20.3 Adapters e canais

| Arquivo | Intervenção/prova esperada | WP |
|---|---|---|
| `shopman/shop/adapters/_notification_templates.py` | Template/flow version/active/strict schema; erro sanitizado. | 03, 06 |
| `shopman/shop/adapters/notification_manychat.py` | Immutable payload/idempotency/timeout taxonomy/provider ID/redaction; provar ou remover race de custom fields. | 03, 06 |
| `shopman/shop/adapters/notification_whatsapp.py` | Remover do caminho campanha conforme ADR-009 após gate; manter só ownership permitido/testado ou eliminar em projeto coordenado. | 06 |
| `shopman/shop/adapters/notification_console.py` | Nunca readiness prod; ambiente/test marker explícito. | 03, 04 |
| `shopman/shop/adapters/notification_email.py` | Contract target/attempt/error/receipt consistente se plataforma Marketing habilitada. | 03, 06 |
| `shopman/shop/adapters/notification_sms.py` | Mesmo contrato, rate/PII/receipt; não ativar canal novo implicitamente. | 03, 06 |
| `shopman/shop/adapters/audience_sources.py` | Source freshness/degraded/explainability e query budgets; no silent zero. | 01, 11 |
| `shopman/shop/management/commands/manychat_flows.py` | Read-only/default dry run, active/readiness e sem segredo/output bruto. | 04, 06 |
| `shopman/shop/tests/test_manychat_flow_picker.py`, `test_manychat_flow_variables.py`, `test_whatsapp_flow_coverage.py`, `test_notification_whatsapp.py`, `test_notification_sms_comtele.py` | Recontratar backend único, active flow, payload atomics, redaction, timeout/unknown e sandbox. | 00, 03, 06 |

### 20.4 Guestman, consentimento e subscriptions

| Arquivo/caminho | Intervenção/prova esperada | WP |
|---|---|---|
| `packages/guestman/shopman/guestman/contrib/consent/models.py` | Evento append-only + current projection, purpose/text/version/evidence/retention. | 01 |
| `packages/guestman/shopman/guestman/contrib/consent/service.py` | API batch por cohort, precedence/revoke/history/fail-closed, sem scan global. | 01, 11 |
| `packages/guestman/shopman/guestman/contrib/consent/admin.py` | Unfold canônico, current + timeline read-only, access audit; sem audience browsing. | 01, 12 |
| `packages/guestman/.../consent/migrations/` | Expand/backfill `legacy_import` honesto/reversível; coordenação de migration. | 01, 19 |
| `shopman/storefront/models/stock_alerts.py` | Unicidade pending, normalized identity, purpose/evidence/revoke/expiry. | 01 |
| `shopman/storefront/services/stock_alerts.py` | Subscribe/revoke transacional, consent proof e no race. | 01 |
| `shopman/storefront/admin/stock_alerts.py` | Audit/filters/PII permission e Unfold; no send action insegura. | 01, 12 |
| `shopman/shop/handlers/stock_alerts.py` | Recheck suppression + delivery ledger/idempotency. | 01, 03 |
| `shopman/shop/tests/test_notification_consent.py`, `test_audience.py`, `test_audience_manual.py`, `shopman/storefront/tests/test_stock_alerts.py` | Trocar override-alert por opt-out precedence, history/subscription race/cohort subtract-only/query budget. | 00, 01 |

### 20.5 Admin/Unfold

| Arquivo | Intervenção/prova esperada | WP |
|---|---|---|
| `shopman/shop/admin/campaign.py` | Após G-H07, audit read-only e apenas config aprovada com forms/fieldsets/tabs/inlines/widgets Unfold; remover raw JSON/list_editable perigoso. | 04, 12 |
| `shopman/shop/admin/promotion.py` | Manter promoção no owner; mostrar refs/validade/dependências Marketing sem redefinir oferta. | 06, 12 |
| `shopman/shop/admin/__init__.py` | Registration explícita coerente com curated Admin; não esconder audit prometido nem registrar cockpit duplicado. | 12 |
| `shopman/backstage/admin/navigation.py` | Link/corte de config/audit canônico conforme permission, se aprovado. | 12 |
| `shopman/backstage/admin_console/settings_hub.py` | Somente links/config ownership, sem form Marketing artesanal. | 12 |
| `shopman/backstage/templates/admin_console/settings_hub/index.html` | Usar componentes/helpers Unfold e link exato; nenhuma operação duplicada. | 12 |
| `shopman/backstage/tests/test_admin_display_canonicity.py`, `test_admin_widget_canonicity.py`, `test_admin_navigation.py`, `test_admin_reachability.py`, `test_admin_smoke.py`, `test_admin_field_locks.py` | Cobrir registro, permissão, read-only audit, widgets oficiais e ausência de dual write. | 12 |

Regra: antes de qualquer edição, reler `unfold-admin-canonical`, `docs/engineering/unfold_admin_page_playbook.md`, política canônica e inventário. Gate final obrigatório: `make admin`.

### 20.6 Operator-kit

| Arquivo | Intervenção/prova esperada | WP |
|---|---|---|
| `surfaces/operator-kit/app/composables/useOperatorSession.ts` | Fonte única 401/403/recovery para Marketing; contribuir apenas comportamento genérico. | 10 |
| `surfaces/operator-kit/app/composables/useOperatorLock.ts` e `components/OperatorLock.vue` | Gate/focus/session semantics reutilizáveis; não acoplar Marketing. | 10 |
| `surfaces/operator-kit/app/composables/useConnectivity.ts`, `components/OfflineBanner.vue` | Offline/stale/focus refetch comum. | 10, 11 |
| `surfaces/operator-kit/app/utils/httpError.ts`, `retryBackoff.ts`, `ssePath.ts` | Error taxonomy, Retry-After/backoff/jitter/baseURL canônicos. | 05, 10, 11 |
| `surfaces/operator-kit/server/utils/djangoProxy.ts`, `eventStream.ts`, `apiVersion.ts`, `djangoBaseUrl.ts` | Header/cache/CSRF/SSE/version allowlists compartilhadas. | 05, 10, 11 |
| `surfaces/operator-kit/app/plugins/errorReporter.client.ts`, `utils/clientErrorReport.ts` | Redaction/PII/request ID/CSP-safe telemetry. | 10, 11 |
| `surfaces/operator-kit/app/assets/css/operator-theme.css` | Tokens/target/focus/contrast/reduced-motion comuns; sem override Marketing-specific. | 10 |
| `surfaces/operator-kit/README.md` | Atualizar surfaces/capabilities/roadmap/testes reais após implementação. | 12 |
| testes correspondentes em `surfaces/operator-kit/tests/**` | Provar consumers, session/errors/proxy/SSE/redaction/tokens e evitar regressão em outras surfaces. | 10–12 |

Mudança no kit exige executar testes de todos os consumers impactados; se a necessidade for exclusiva de Marketing, manter local para não criar abstração prematura.

### 20.7 Deploy, segurança, observabilidade e documentação

| Arquivo/caminho | Intervenção/prova esperada | WP |
|---|---|---|
| `.do/app.alpha-subdomains.yaml` | Health live/ready, capacity/env/alerts/rollout; não incluir segredo; mudança autorizada separadamente. | 10–12, 19 |
| `.github/workflows/surfaces-gate.yml` ou workflow real equivalente | Adicionar lint/build/contracts/E2E/a11y/visual/security com install determinístico. | 12 |
| `.github/workflows/deploy-images.yml` | Incluir dependency/operator-kit impact correto e smoke pós-deploy; sem deploy automático desta execução. | 12, 19 |
| configs de logging/Sentry/deploy/worker existentes | Correlation/redaction/metrics/health/graceful shutdown/capacity. Confirmar paths no HEAD antes da edição. | 11 |
| `docs/decisions/adr-009-whatsapp-via-manychat.md` | Implementação converge; alterar ADR só por nova decisão formal, não para justificar drift. | 06, 12 |
| ADR-012/014/016/019/020/021 | Referenciar contracts realizados; não reescrever arquitetura silenciosamente. | 05, 06, 12 |
| `docs/reference/projection-contracts.md` | Adicionar Marketing v2, versioning/Actions/error/SSE invariants e generation source. | 05, 12 |
| `docs/reference/surfaces.md` | Atualizar topologia/hosts/surfaces operator atuais. | 12 |
| `docs/engineering/nuxt_design_system.md` | Registrar apenas padrões realmente compartilhados aprovados. | 10, 12 |
| `docs/engineering/backstage-design-system.md` | Atualizar inventário de surfaces e corte Admin/Nuxt. | 12 |
| `docs/guides/deploy-digitalocean.md`, `docs/guides/deploy.md` | Health/canary/flags/smoke/rollback da surface. | 11, 12, 19 |
| `docs/runbooks/ativar-whatsapp-transacional.md` | Alinhar readiness/ManyChat, sem misturar transacional/Marketing. | 06, 11 |
| `docs/runbooks/rollback-de-deploy.md` | Incorporar preservação/reconciliação de commands in-flight. | 11, 19 |
| `docs/runbooks/marketing-*.md` novos | Oito runbooks da seção 17, revisados por operador não autor. | 11 |
| planos/relatórios Marketing antigos | Não editar para “fazer bater”; manter como histórico e linkar supersession apenas se policy documental exigir. | 12 |

### 20.8 Testes backend e infraestrutura

| Arquivo/suite | Intervenção/prova esperada | WP |
|---|---|---|
| `shopman/backstage/tests/test_api_marketing_surface.py` | API v2/RBAC/schema/actions/errors/idempotency/cursor/test sandbox. | 00, 02, 04, 05 |
| `shopman/backstage/tests/test_api_notifications.py` | Sem default action; lifecycle/reconcile/parity/concurrency. | 00, 08 |
| `shopman/shop/tests/test_campaign.py` | State/snapshot/artifact/strict render/AI boundary. | 00, 02, 06, 09 |
| `shopman/shop/tests/test_campaign_handlers.py` | Ledger/crash/leases/waves/recheck/aggregate/retry. | 00, 03 |
| `shopman/shop/tests/test_campaign_delivery_backend.py` | ManyChat-only/readiness/provider contract/unknown. | 00, 03, 06 |
| `shopman/shop/tests/test_campaign_schedule.py`, `test_campaign_scheduling.py` | Occurrence locks/idempotency/cancel/catch-up/timezone/expiry. | 00, 02, 03 |
| `shopman/shop/tests/integration/test_campaign_e2e.py` | Vertical decision→outbox→fake provider→ledger→projection/alert. | 00–08 |
| `shopman/shop/tests/test_offers.py`, `test_promotion_channel_scope.py` | Canonical facts/link/validity/channel; campanha não vende. | 06 |
| `shopman/shop/tests/test_nuxt_deploy_config.py` | Manifest/lock/install/runtime/base/headers/health consistency. | 10, 12 |
| `shopman/shop/tests/test_deploy_checks.py` | Readiness/worker/config/flow warnings como gates proporcionais. | 06, 11, 12 |
| `shopman/shop/tests/test_maintenance_worker.py` | Reconciler/outbox/expiry ordering/failure isolation/graceful shutdown. | 02, 03, 11 |
| novas suites `test_campaign_concurrency.py`, `test_campaign_idempotency.py`, `test_marketing_security.py`, `test_marketing_load.py`, `test_marketing_chaos.py` | Interleavings/abuso/volume/fault injection da seção 18. Nomes finais seguem convenção do repo. | 00–04, 11 |

## 21. Backlog priorizado com IDs

Cada item é pequeno o bastante para um commit coeso; “Done” inclui teste, telemetria e nota no log. Dependências são IDs ou gates.

### P0

| ID | Entrega atômica | Depende de | Gate/aceite específico |
|---|---|---|---|
| MKT-001 | Congelar máquina de estados/erros/clock e fake provider adversarial | G-H03, WP-00 | crash modes distinguíveis; sem rede |
| MKT-002 | Teste vermelho: alert subscription não ultrapassa opt-out | MKT-001, G-H01 | property passa para todos reasons |
| MKT-003 | Consent event append-only + current projection/migration | MKT-002, G-H01 | legacy marcado, history reconstruível |
| MKT-004 | Subscription unique/revoke/evidence e handler com recheck | MKT-003 | corrida subscribe e revoke-before-send passam |
| MKT-005 | Resolver audience explainable/dedup/normalized/fail-closed | MKT-003 | counts fecham, outage degraded |
| MKT-006 | AudienceSnapshot/member protection subtract-only | MKT-005, G-H02 | no exposure; opt-in tardio não entra |
| MKT-007 | Capability permissions e modo audit de enforcement | G-H04 | matrix diffs coletados, deny default |
| MKT-008 | Isolar send-test sandbox max-1 + redact + throttle/idempotency | MKT-007 | payload não alcança audience; PII scan zero |
| MKT-009 | CommandReceipt/version/CAS/idempotency schema | MKT-001 | same key same outcome; different payload 409 |
| MKT-010 | Approve content+snapshot+audit+outbox numa transação | MKT-006, MKT-009 | artifact hash byte-identical |
| MKT-011 | Reject/cancel/reschedule/expire transacionais e auditados | MKT-010 | concorrência tem um vencedor; directive cancelada |
| MKT-012 | Outbox claim/lease/reconciler e crash recovery | MKT-010 | after-commit crash converge |
| MKT-013 | DeliveryTarget/Attempt schema, uniques e protected identifiers | MKT-006, MKT-012 | dois workers não duplicam target |
| MKT-014 | Adapter outcome taxonomy + unknown sem blind retry | MKT-013, G-H03 | effect-lost-response fica unknown |
| MKT-015 | Fan-out chunk/backpressure e consent/expiry pre-send recheck | MKT-013 | load+kill passa; revogado suprimido |
| MKT-016 | Agregador ledger e platform/general states honestos | MKT-013–015 | partial/manual/unknown nunca published total |
| MKT-017 | Selective retry/reconcile commands e Actions backend | MKT-014–016 | accepted/confirmed/unknown não reexecutados indevidamente |
| MKT-018 | Corrigir preferred-hour pelo selector canônico | MKT-005, MKT-015 | `vip@9`/`all@9` entregam cohort correto |
| MKT-019 | Corrigir command `publish_mode=now|scheduled` ponta a ponta | MKT-009–010 | CTA now jamais agenda |

### P1

| ID | Entrega atômica | Depende de | Gate/aceite específico |
|---|---|---|---|
| MKT-020 | Enforce RBAC/step-up/confirmation/quotas | MKT-007–009, G-H04 | revocation mid-flow bloqueia efeito |
| MKT-021 | Marketing Projection v2 pura/versionada | MKT-016 | sem labels/copy/PII; schema golden |
| MKT-022 | Action resolver único para anúncio/regra/plataforma/alert | MKT-017, MKT-020–021 | UI não infere permission/state |
| MKT-023 | OpenAPI→TS client e CI drift | MKT-021–022 | geração temporária sem diff |
| MKT-024 | Error/header/ETag/cursor contract no API+BFF | MKT-021 | 401/403/409/422/429/503 distintos |
| MKT-025 | ResolvedDispatchArtifact único | MKT-010, MKT-021 | preview/adapter hash iguais |
| MKT-026 | Preservar variants e strict unknown variables | MKT-025 | golden multicanal passa |
| MKT-027 | Facts canônicos/link/promo validity/as-of | MKT-025, G-H05 | schedule inválido bloqueado |
| MKT-028 | Preview request cancellation/epoch e fidelity UI | MKT-025–027 | stale response nunca aparece |
| MKT-029 | Readiness states/active flow/CAS/audit/outage | MKT-020, MKT-025 | outage não aceita ref arbitrária |
| MKT-030 | Convergir ManyChat-only e provar custom-field isolation | MKT-014, MKT-029, G-H03 | ADR-009; race resolvida ou bloqueio explícito |
| MKT-031 | URL/media threat model e controls | MKT-025, G-H03 | private/redirect/tracking tests passam |
| MKT-032 | CampaignForm lossless/schema completo | MKT-023 | save sem diff oculto |
| MKT-033 | Draft autosave/isolation/restore/conflict diff | MKT-009, MKT-032 | refresh/401 não perde conteúdo |
| MKT-034 | Schedule/timezone/DST/expiry UI canônica | MKT-019, MKT-027 | preview/receipt/worker mesmo instante |
| MKT-035 | Result/partial/cancel/retry/reconcile flows | MKT-017, MKT-022–023 | recovery inline, receipt preservado |
| MKT-036 | Notification lifecycle/dedupe/owner/reconcile | MKT-022 | seen≠resolved; siblings fecham juntos |
| MKT-037 | Remover default approve e migrar notification client | MKT-036 | missing action inválida, test legado removido |
| MKT-038 | IA structured/fact checker/moderation/audit, sempre revisão | MKT-025–027, G-H06 | red-team/zero auto-send |
| MKT-039 | Auth mount gate e 401/403/session recovery | MKT-023–024, MKT-033 | nenhum fetch protected anônimo |
| MKT-040 | Security headers/BFF/cache/self-host fonts | MKT-024 | matriz HTML/BFF/error/SSE passa |
| MKT-041 | A11y/operator-kit/touch/focus/reflow components | MKT-022–023 | axe/keyboard/44px/zoom passam |
| MKT-042 | Marketing telemetry/redaction/reconciler alerts | MKT-012–017 | SLO dashboards, zero PII |
| MKT-043 | Audience/query/worker load optimization | MKT-005, MKT-015, MKT-042 | budgets peak×2 passam |
| MKT-044 | Health live/ready e oito runbooks/drills | MKT-042 | operador não autor executa drill |

### P2

| ID | Entrega atômica | Depende de | Gate/aceite específico |
|---|---|---|---|
| MKT-045 | Cursor/filtros/history e métricas corrigidas | MKT-016, MKT-021 | sem corte/alcance falso |
| MKT-046 | Visual/state matrix completa e screenshot baseline | MKT-032–041 | todas células seção 15 revisadas |
| MKT-047 | Discovery de 5–8 gestores e budgets | MKT-035, MKT-046, G-H05 | task metrics + decisão documentada |
| MKT-048 | Admin ownership decision e implementação Unfold mínima | G-H07, MKT-020–023 | no dual write; `make admin` |
| MKT-049 | CI completo e dependência Nuxt determinística | MKT-023, MKT-040–046 | install/test/lint/type/build/E2E/a11y/visual/security |
| MKT-050 | Atualizar READMEs/surfaces/design/contracts/deploy docs | MKT-048–049 | docs verificadas contra rotas/HEAD |
| MKT-051 | Shadow reconciliation e internal canary | MKT-001–050, G-H08/09 | zero unexplained mismatch/P0 |
| MKT-052 | Piloto limitado e avaliação go/no-go | MKT-051, todos gates | SLO/budgets/zero invariants quebrados |
| MKT-053 | Rollout progressivo com gates 5→25→50→100% | MKT-052, G-H09/10 | burn/reconcile limpos em cada estágio |
| MKT-054 | Cutover/contract cleanup legado em release separada | MKT-053 | uso zero, backup/rollback, docs finais |

### Backlog de discovery/decisão, não implementação implícita

| ID | Pergunta | Owner | Saída exigida |
|---|---|---|---|
| MKT-D01 | Subscription específica pode ser recriada depois de opt-out global, e com qual disclosure? | DPO/Jurídico + Produto | tabela de precedência/versioned policy |
| MKT-D02 | Qual retenção/acesso/erase para cohort e delivery target? | DPO + Dados | policy e threat model aprovados |
| MKT-D03 | ManyChat oferece idempotency/receipt/reconcile e custom fields atômicos? | Platform owner | evidência sandbox/docs e adapter contract |
| MKT-D04 | Quais blast thresholds exigem typed confirmation, 2FA ou dual control? | Segurança + Ops | matriz por count/canal/horário |
| MKT-D05 | Quais objetos são configuráveis no Admin e quais exclusivos do Nuxt? | Produto + Ops | ownership map sem dual write |
| MKT-D06 | Qual default de schedule/cancel/edit e quais quiet hours/timezones? | Produto + Jurídico/Ops | policy/test cases |
| MKT-D07 | Quais alertas merecem sino/owner/escalation/SLA? | Produto + Ops | catálogo de condition/action |
| MKT-D08 | Os budgets da seção 16 são atingíveis e úteis? | UX research + gestores | relatório de tarefas e ajustes aprovados |
| MKT-D09 | Quais SLO/peak/cohort limits e paging thresholds refletem operação? | SRE/Ops + Produto | capacidade/SLO/error budgets |
| MKT-D10 | IA pode avançar além de sugestão revisada? | Marca/Jurídico + Segurança + Produto | decisão futura separada; default “não” |

## 22. Definition of Done rigorosa

O plano só pode ser marcado “plano concluído” quando **todos** os itens aplicáveis abaixo estiverem evidenciados por commit/comando/artefato/owner. Marcar “não aplicável” exige justificativa e aprovador; não é forma de reduzir gate.

### 22.1 Domínio e contratos

- [ ] Conteúdo, variants, mídia, link, facts, template/flow version, audience policy e schedule aprovados estão num snapshot imutável content-addressed.
- [ ] Artifact despachado coincide byte a byte/hash a hash com o preview aprovado, por plataforma.
- [ ] Campaign continua anunciando; preço/estoque/promoção/link permanecem canônicos no orquestrador/click.
- [ ] Commands têm actor, reason quando exigido, version/CAS, idempotency, confirmation, receipt e audit.
- [ ] Approve/edit/reject/cancel/reschedule/expire concorrentes têm exatamente uma transição válida e outcome explícito para perdedores.
- [ ] Outbox é transacional e todo estado stale é detectado/reconciliado.
- [ ] Projection v2 é pura, versionada, paginada, sem labels/copy/PII/membership e com freshness.
- [ ] Actions são resolvidas pelo backend e carregam permission/readiness/priority/reason/href/method/schema/idempotency/confirmation.
- [ ] TypeScript é gerado do contrato; CI falha em drift.
- [ ] SSE somente invalida e refetch/ETag é a verdade.

### 22.2 Consentimento, privacidade e audiência

- [ ] DPO/Jurídico aprovou e versionou precedence, purposes, disclosure, legado, retenção, erase e min cohort.
- [ ] Opt-out/revogação nunca é ultrapassado por `alerts`, regra, retry, stock alert ou fallback.
- [ ] Consentimento tem trilha append-only e current-state reconstruível; legado não recebe prova inventada.
- [ ] Subscription é unique/idempotente, revogável, purpose-specific e auditável.
- [ ] Audience total é backend-resolvido, deduplicado e explicável; source failure é degraded, não zero.
- [ ] Cohort aprovado nunca cresce; recheck só suprime.
- [ ] Membership/telefone não aparece em Announcement JSON, Projection, browser, Admin comum, log, métrica ou Sentry.
- [ ] Access/retention/erase de snapshot/targets foi testado e auditado.
- [ ] Frequency, collision, quiet hours, timezone e expiry usam policy única no preview e send.
- [ ] `sent_after_optout` e `sent_after_expiry` são zero e disparam incidente crítico se diferentes.

### 22.3 Dispatch, plataformas e recuperação

- [ ] Cada publicação/recipient tem DeliveryTarget unique e attempts persistentes; dois workers/duas directives não duplicam alvo.
- [ ] Provider semantics de accepted/confirmed/idempotency/receipt/timeout estão documentadas e testadas.
- [ ] Timeout ambíguo vira `unknown`; não há blind retry.
- [ ] Retry seleciona somente failed_retryable; accepted/confirmed não repetem; unknown exige reconcile/gate.
- [ ] Partial/pending manual/unknown nunca aparecem como sucesso total.
- [ ] Preferred-hour waves entregam cohort correto; schedule/expiry/cancel são revalidados no claim.
- [ ] Chunk/backpressure/rate/circuit respeitam capacity e não monopolizam worker.
- [ ] Readiness distingue ready/degraded/blocked/unknown, exige active flow e tem freshness/Action.
- [ ] ADR-009 está cumprida ou nova decisão formal aprovada; não existe fallback escondido.
- [ ] Errors/secrets/provider bodies estão redigidos; webhooks são autenticados, replay-safe e idempotentes.
- [ ] Reconciler encontra approved/outbox/target/attempt/aggregate inconsistentes e produz resolução segura.

### 22.4 Segurança e autoridade

- [ ] Matriz role×capability passa no backend e UI; permissão ampla antiga não autoriza publish/fire/test/config.
- [ ] Publisher, Platform Owner e Auditor/DPO são separáveis; deny é default.
- [ ] Permissão/session revogada entre load e submit impede efeito.
- [ ] Send-test é sandbox/verified, max 1, sem audience resolver, throttled/idempotente e não contamina KPIs.
- [ ] Ações perigosas têm confirmação proporcional/step-up/dual control conforme G-H04.
- [ ] CSRF, IDOR, XSS, template injection, SSRF/URL, open redirect, cache, header, rate e abuse suites passam.
- [ ] HTML/BFF/errors/SSE têm matriz de headers/caches aprovada; frame protection/CSP/HSTS/nosniff/referrer/COOP presentes.
- [ ] Nenhuma fonte/asset de terceiro não aprovada; nenhum secret/PII em telemetry.
- [ ] Emergency freeze/revoke foi ensaiado e não depende de deploy.

### 22.5 UX, omotenashi e acessibilidade

- [ ] Gate de auth impede mount/fetch protegido; 401/403/404/409/422/429/5xx/offline são distintos.
- [ ] Login/modal têm nome/descrição/focus trap/inert/restore; background nunca é interativo.
- [ ] Form de campanha faz round-trip integral sem descartar field oculto/desconhecido.
- [ ] Draft sobrevive refresh/navegação/401 e conflict oferece diff/rebase sem overwrite.
- [ ] “Publicar agora” nunca agenda; schedule mostra data, timezone, quiet-hours e expiry inequívocos.
- [ ] Preview real representa variants, limites, Unicode, mídia, link, flow/template e mesmo artifact do send.
- [ ] Zero/degraded audience/readiness bloqueia ação com reason/repair; empty só após fetch bem-sucedido.
- [ ] Resultado por plataforma e receipt permanecem no contexto com cancel/retry/reconcile pertinentes.
- [ ] Alertas têm primary Action, owner/dedupe/lifecycle e resolvem com a condição; seen ≠ ack ≠ resolved.
- [ ] Budgets de toques/digitação/telas/espera/consultas/recovery/certeza foram medidos com gestores e atendidos ou têm exceção aprovada.
- [ ] Toda célula da matriz de rotas/viewports/states/content extremes tem teste/screenshot revisado.
- [ ] WCAG 2.2 AA: axe sem serious/critical, keyboard/focus/zoom/reflow/contrast/forced colors/reduced motion aprovados.
- [ ] Alvos de toque são ≥44×44 ou têm hit area equivalente documentada e testada.
- [ ] Light/dark, 320 px e 200% zoom não perdem conteúdo, estado nem ação.

### 22.6 IA e conteúdo

- [ ] IA está off por default até gates; sempre sugere, nunca publica.
- [ ] Output é estruturado; prompt/content/context não confiáveis estão delimitados.
- [ ] Facts/claims/URLs são validados contra owner canônico vigente; nenhum fact vem da IA.
- [ ] Moderação/Marca/limites/red-team PT-BR passam.
- [ ] Accept preserva diff e exige approve posterior; timeout mantém draft.
- [ ] Model/provider/policy/fact/output hashes são auditáveis sem guardar PII/segredo.

### 22.7 Testes, performance e operações

- [ ] Baseline nova registra contagens sem warnings Vue e sem flakes conhecidos não triados.
- [ ] Unit/model/API/integration/concurrency/E2E/a11y/visual/security/load/chaos passam nos ambientes definidos.
- [ ] Crash before/after commit/network effect e dois workers convergem sem loss/duplication.
- [ ] Query/cardinality/memory/lock/queue budgets passam em peak acordado ×2.
- [ ] SLOs têm dashboards, burn alerts, owners e error budgets; consent/duplicate são invariantes fora do budget.
- [ ] Health live/ready detecta processo, BFF/API/DB/queue corretamente sem expor detalhes.
- [ ] Oito runbooks existem e foram executados por operador que não implementou.
- [ ] PII/secret log scanner passa em success/error/timeout/webhook.
- [ ] CI executa `npm ci`, unit, lint, typecheck, build, contracts, E2E, a11y, visual e security; backend focused/full proporcional; Admin usa `make admin`.
- [ ] Nuxt instalado satisfaz manifesto/lock em checkout limpo.

### 22.8 Admin, documentação, rollout e governança

- [ ] G-H07 definiu ownership; Nuxt é cockpit e Admin não oferece dual write.
- [ ] Qualquer Admin novo usa Unfold canônico, audit read-only e permissões/field locks; nenhum console artesanal.
- [ ] `make admin` passa com contagem/commit registrados.
- [ ] ADRs, projection contracts, surface map, design docs, operator-kit README, Marketing README, deploy guides e runbooks correspondem ao produto real.
- [ ] Migrations expand/contract/backfill foram ensaiadas, observadas e têm rollback/forward-fix seguro.
- [ ] Flags têm owner/default/failsafe/expiry; nenhuma desliga consent, redaction, CSRF, permission ou unique guard.
- [ ] Shadow reconciliation ficou zero ou todos mismatches estão explicados/aprovados.
- [ ] Canary/piloto atenderam SLO, budgets e invariantes; go/no-go assinado.
- [ ] Rollout 5→25→50→100% teve gate/observação por estágio, sem deploy automático.
- [ ] Contract/legacy cleanup ocorreu em release posterior com uso zero, backup e rollback testados.
- [ ] Não houve escrita/deploy/send em produção sem autorização explícita registrada.
- [ ] Handoff final lista branch, worktree, commits, migrations, flags, comandos/resultados, dashboards, decisões e rollback.
- [ ] Responsável de integração resolveu conflitos semanticamente e repetiu gates.

### 22.9 Critério final

Somente então alterar o cabeçalho de estado para **plano concluído**. Se qualquer P0 estiver aberto, o Marketing não está pronto para expansão nem automação. Se P0 estiver fechado mas houver gate humano/piloto pendente, o máximo é **implementação técnica concluída**. Se gates e ensaios estiverem completos mas rollout ainda não, o máximo é **pronto para piloto**. `Rollout concluído` exige produção autorizada, observada e reconciliada; nenhum agente pode inferi-lo a partir de testes locais.
