# Contrato da superfície Marketing

- **Proprietário:** Produto/Marketing (operação), Platform/SRE (entrega) e DPO
  (consentimento/auditoria)
- **Última verificação:** 2026-10-04
- **Verificado contra:** rotas, projeções, permissões e specs de deploy do `HEAD`
- **Gate de deriva:** `make marketing-docs`

Este é o mapa factual do Marketing. Identificadores de código e protocolo permanecem
estáveis em inglês; a apresentação ao operador é pt-BR. Histórico de plano ou relatório
não substitui este contrato.

## Responsabilidade e canais

O `marketing-nuxt` é o único cockpit operacional. Django decide estado, público,
consentimento, autorização, horário, oferta, artefato e ações possíveis. Admin/Unfold
mostra somente auditoria agregada para `shop.audit_marketing`, sem escrita concorrente
e sem navegação por membro, contato, outbox, destino ou tentativa.

| Plataforma | Consequência atual | Cardinalidade | Não significa |
|---|---|---:|---|
| Instagram | Story público por padrão; Feed só por escolha explícita | 1 por anúncio | mensagem direta ou fallback de Story para Feed |
| Facebook | postagem pública na página | 1 por anúncio | mensagem por pessoa |
| Google Meu Negócio | post público no perfil: Atualização, Evento ou Oferta | 1 por anúncio | mensagem por pessoa |
| WhatsApp | mensagem direta | até 1 por pessoa elegível | postagem pública |

Mensagem direta no Instagram está fora do contrato. Se for aprovada no futuro, exige
fluxo de entrega, capability, consentimento, prontidão, limites e comprovante próprios.

**Vocabulário da operação:** mensagem é uma mensagem direta e possui destinatário;
publicação é uma postagem pública e não possui destinatário individual; entrega é o
termo genérico que pode se referir às duas anteriores. Identificadores técnicos podem
permanecer em inglês, mas esses termos não podem ser trocados na UI.

O gate `MKT-CAP-01` foi aprovado em 2026-09-11: a evolução adotará a identidade
`{platform, delivery_kind, format}`, um catálogo server-owned de capacidades e schemas
fechados por destino. Durante a transição, cada plataforma continua resumida a uma
única modalidade de entrega e nenhum novo efeito externo será habilitado. A auditoria
e a decisão completas estão em
[`marketing-platform-capability-audit-20260911.md`](../reports/execution/marketing-platform-capability-audit-20260911.md).

Para novas entregas, as três dimensões são obrigatórias desde o schema 4 e são
persistidas no artefato, outbox e destino. A resposta de `/marketing/options/`
projeta `delivery_capabilities` com modalidade, formatos, default, campos aceitos e
exigência de mídia; o composer de campanha consome essa projeção na etapa Destinos e
na revisão das composições. Ele não consome `provider_capabilities`, que é inventário
teórico e pode conter formatos planejados ou bloqueados. Linhas e artefatos anteriores
continuam legíveis pela compatibilidade histórica, mas não podem originar uma nova
identidade incompleta.

O formato público faz parte do artefato imutável (`publication_format`). A prévia,
aprovação e chamada do provider leem o mesmo valor. No Instagram, `story` é o default
de produto para FOMO e exige imagem pública; `feed` é secundário e precisa estar
explicitamente escolhido. Artefato histórico sem formato continua legível, mas o
adapter real o recusa antes da rede — nunca adivinha um efeito novo. A prévia de Story
mostra a imagem 9:16 e avisa que o texto do rascunho não é sobreposto automaticamente.

`/marketing/preview/` tem dois modos. Sem `announcement`, é a prévia do formulário de
campanha/modelo: ainda não existe anúncio, e um produto real da loja serve de exemplo
(`sample: true`, "Exemplo com: …"). Com `announcement: <id>` (tela de revisão), a prévia
sai do conteúdo GRAVADO do anúncio mais as edições do card (`body`, `hashtags`,
`platforms`, `google_business`), montada como a aprovação monta — nunca com produto de exemplo. Se o
anúncio não tem link, a prévia não mostra link, porque o post não terá
(`campaign.preview_announcement`).

### Post do Google Meu Negócio

Três formatos (`publication_format`): `standard` (Atualização), `event` (Evento: título,
início e fim em hora local da loja) e `offer` (Oferta). `ALERT` fica de fora. O botão é
escolha explícita (`call_to_action`), no modelo e na revisão do anúncio, com o rótulo que o
Google mostra em pt-BR: **Nenhum** (padrão), Ligar agora (`call`, sem URL: usa o telefone
do perfil), Saiba mais (`learn_more`), Pedir on-line (`order`), Comprar (`shop`), Reservar
(`book`), Inscrever-se (`sign_up`). **Link nunca vira botão sozinho**; sem botão, o link não
aparece no post. Pedir on-line e Comprar só levam a `/produto/` ou `/oferta/`. "Como chegar"
não existe na API. A Oferta não tem botão escolhível (o Google mostra "Ver oferta") e nasce
da `Promotion` da campanha: título e validade são selados pelo servidor a partir dos fatos,
o link de resgate é a página da oferta e o operador só escreve as condições. Chaves e donos
em [data-schemas.md](data-schemas.md#google_business--post-do-google-meu-negócio).

Travas na prévia e na aprovação, com a mensagem no campo (`field_errors`), a partir dos
limites da documentação oficial do Google conferidos em 2026-09-25: texto + hashtags até
1.500 caracteres (`google_summary_too_long`), sem telefone no texto
(`google_summary_has_phone` — o Google remove post com contato que não consegue
verificar; o botão "Ligar agora" é o caminho), foto JPEG ou PNG, de 10 KB a 5 MB e com ao
menos 250 × 250 px (`google_media_*`). Formato, peso e dimensão da foto são lidos do
arquivo (`marketing_media_probe`): `GET` com `Range` de 256 KB, só em host da lista de
mídia, sem seguir redirecionamento, com cache de 10 min por URL — é a única leitura de
mídia que o servidor faz. A prévia mostra a foto no recorte do cartão e desaconselha
texto dentro da imagem (o Google corta as laterais conforme a tela). As mesmas travas
puras voltam no adapter antes da rede.

O editor de modelo mostra os três formatos com seus próprios campos; não existe um
“tipo de publicação” genérico aplicado a destinos não-Google. Evento exige título,
início e fim antes de salvar. Oferta recebe apenas condições editoriais no modelo; a
promoção escolhida na campanha sela título, validade e link. Atualização e Evento
oferecem somente os CTAs aceitos pelo contrato e desabilitam os que precisam de link
quando o texto não usa `{{link}}`.

A intenção editorial continua simples: um texto comum serve todos os destinos. O
operador abre uma composição somente quando precisa adaptar o texto ou formato daquela
plataforma. A tela lista exclusivamente `delivery_capabilities`, sela o formato
escolhido em `platform_variants` e mantém a adaptação visível como “Adaptada”. Para
WhatsApp, template, variáveis e botões aprovados continuam pertencendo à conexão; o
editor não inventa controles genéricos para eles. Se a allow-list não carregar, o
formulário falha fechado e não salva opções presumidas pelo navegador.

Depois do aceite, a passada de entrega (`process_marketing_delivery --with-reconciliation`,
no `maintenance-worker`) consulta `localPosts.get` dos posts do Google aceitos nas últimas
48 h: `LIVE`/`RECURRING`/`SCHEDULED` → `confirmed`, `REJECTED` → `failed_final`
(`google_post_rejected`), `PROCESSING` fica `accepted` para o ciclo seguinte (a foto
aparece ~1–2 min depois do texto). A consulta só lê. Apagar um post é outra ação
pública: não existe no cockpit, e quando existir será comando explícito, com
confirmação, nunca automático.

## Rotas Nuxt

### A casa é a fila de decisões

Decisão do dono (2026-10-03, SUITE-UX §9): `/` é a **fila de decisões**, ordenada
por prazo, sem corte. Antes eram cinco portas (Hoje cortado em quatro, sino, push, a
volta do disparo e a linha do histórico) e nenhuma tela. A fila lê
`GET /marketing/decisions/` (`shopman/backstage/projections/marketing_decisions.py`,
capability `shop.view_marketing`, `Cache-Control: private, no-store`) e só traz
decisões que existem no sistema, cada uma com o lugar exato onde ela já é tomada:

| Tipo (`kind`) | Quando entra | Prazo (`deadline_at`) | "Revisar" abre |
|---|---|---|---|
| `review` | anúncio `pending_review` dentro do prazo | `expires_at` do anúncio | `/announcements/:id#review` |
| `retry_failed` | destino `failed_retryable` (só volta por gesto do operador) | `expires_at` do anúncio: depois dele o worker encerra o destino como vencido | `/announcements/:id#result` |
| `reconcile_unknown` | destino `unknown` cuja última tentativa já teve consulta e nenhuma está em andamento | nenhum | `/announcements/:id#result` |

Cada item leva o alcance nas duas grandezas, separadas (`reach.posts` e
`reach.people`, nunca somadas) e, quando é falha, o motivo por plataforma
(`failures[].reason_code`, o código mais frequente do ledger); a frase em pt-BR mora
em `app/presentation/decisions.ts`. A projeção não leva texto do anúncio, rótulo nem
PII. A fila também traz `automatic_checks` (o resultado incerto que o sistema
consulta sozinho, ver abaixo), `scheduled` (aprovados com `publish_at` futuro, que
alimentam `/scheduled`), `scheduled_today_count` e `active_campaign_count`, que viram
a linha "+N agendados hoje · M campanhas ligadas". A fila não decide nada: a revisão
do anúncio revalida as Actions do operador.

O sino deixou de ter lista própria: é um link para `/` que diz quantas decisões
esperam. Ele mora na barra de 56px do celular; do tablet para cima o selo de Decisões
no rail faz o papel dele. A caixa pessoal (SSE `/sse/notifications` e poll de 60 s, que
só invalidam; a fila refaz o fetch) tem um dono só, o `MarketingInboxLive`, montado
uma vez no shell em qualquer largura, que também registra os avisos como vistos quando
a fila está na tela. O push continua abrindo `/announcements/:id#review`, que é o
"Revisar" do cartão daquele anúncio.

Seções de operação: **Decisões** (`/`), **Agendados** (`/scheduled`), **Enviados**
(`/history`) e **Ajustes** (`/campaigns`). Ajustes entra por um item só e tem as
próprias seções numa segunda linha, na linha de recortes do cabeçalho de cada tela de
Ajustes, cada uma com rota própria: Campanhas (`/campaigns`), Modelos (`/templates`),
Ofertas e cupons (`/offers`) e Plataformas (`/platforms`). Desde o V4-MKT o Marketing
veste a camada visual da suíte (`data-suite="v3"`): do tablet para cima as seções moram
no rail da suíte (Decisões, Agendados e Enviados em cima, Ajustes no pé); no celular, na
barra do polegar do kit. Cada tela abre com o cabeçalho de uma linha do kit
(`MarketingPageHeader` sobre `OperatorPageHeader`), com o "ao vivo" discreto nas telas
de fila; no celular a barra de 56px leva o sino e o menu do operador (tema, giro e
Bloquear).

O workspace V2 (`/v2`, com o panorama em `area=today`) e a prévia estática
`/marketing-v2-preview/` saíram na V6-MKT: pré-go-live é zero legado e sem
redirecionamento. As capacidades que moravam nele vivem nas rotas de Ajustes acima.
`/offers` cria oferta e cupom e leva "Criar campanha com esta oferta" para
`/campaigns?new=1&offer=<ref>`.

### A revisão e o selo (V6-MKT)

A revisão do anúncio (`/announcements/:id`) ocupa a tela inteira (`fullscreen` na
página: a barra do polegar some) e segue a v4: foto grande com "Tirar outra" (upload
re-encodado pelo servidor em `marketing/announcements/<id>/photo/`, e a aprovação só
aceita uma foto que veio dessa revisão), contador de caracteres contra o limite da
plataforma, uma linha por plataforma com interruptor, "Quando" (agora ou agendar) e um
pé fixo com Recusar e Continuar. O selo confirma com a **digital do dispositivo**
(WebAuthn, `security/device/*`), que vale só para a confirmação para a qual foi pedida
e dispensa a frase digitada e a senha; "Usar o meu código" mantém a frase e a senha ou
o autenticador como alternativa. Acima do limiar de dupla confirmação, "Pedir a
confirmação de outra pessoa" manda push a quem tem a capacidade de aprovar
(`security/second-control/request/`); o aviso abre `/second-control/:ref`, onde a
segunda pessoa confirma com a digital ou o autenticador dela. Quem pediu nunca
confirma o próprio pedido.

Os fluxos densos de campanha, disparo manual, modelo e configuração de plataforma
abrem em um workspace modal. No desktop ele usa a largura disponível para etapas,
composições e prévias; no mobile ocupa a tela. Fechar devolve o operador à lista da
própria rota e restaura o foco no acionador (em Plataformas, a linha da plataforma).

O inventário de destinos combina, sem fundir, a allow-list selecionável das
opções, o catálogo de capacidades por formato e a prontidão viva das conexões. Uma
plataforma desconectada ou bloqueada permanece visível com o motivo real; somente a
allow-list do servidor decide se ela entra no composer. Na fixture hermética, Google
faz parte da matriz normal e expõe Atualização, Evento e Oferta.

Na lista de campanhas, editar e ligar/desligar exigem a Action `edit_campaign` exata
para o recurso e a versão visíveis. A Action decide se o controle existe e está
habilitado; o navegador não deduz permissão. O PATCH continua same-origin no recurso
canônico e sempre leva `base_updated_at`. Action ausente/desatualizada ou relógio de
leitura ausente falham fechado, sem chamada de rede; `409` recarrega a projeção e não
aplica estado otimista. Enquanto um PATCH está em voo, outro gesto de liga/desliga é
bloqueado para não duplicar a intenção.

“Preparar disparo” obedece separadamente à Action `fire_campaign`: recurso, versão,
href, método, idempotência e exigência de token precisam coincidir. O primeiro POST
apenas sela a intenção; o challenge `none` é consumido automaticamente porque a
consequência é criar um anúncio para revisão. O receipt viaja para a tela desse anúncio
e nenhuma plataforma recebe conteúdo no `fire`.

<!-- marketing-ui-routes:start -->
- `/`
- `/announcements/:id`
- `/campaigns`
- `/history`
- `/offers`
- `/platforms`
- `/scheduled`
- `/second-control/:ref`
- `/templates`
<!-- marketing-ui-routes:end -->

Rotas de infraestrutura: `/api/v1/**` é o BFF same-origin, `/sse/notifications`
transporta apenas invalidação pessoal, `/health/live` prova o processo/BFF e
`/health/ready` inclui a prontidão do Django. As duas rotas vêm da layer
`operator-kit` (`server/routes/health/`), iguais nos oito apps de operador. O alias legado
`/campaign/announcements/:id` redireciona para `/announcements/:id`.

## Rotas Django

A lista abaixo é comparada por máquina com `shopman/backstage/api/urls.py`. `:id` e
`:ref` representam parâmetros de rota, não texto literal.

<!-- marketing-api-routes:start -->
- `/api/v1/backstage/marketing/`
- `/api/v1/backstage/marketing/announcements/:id/`
- `/api/v1/backstage/marketing/announcements/:id/approve/`
- `/api/v1/backstage/marketing/announcements/:id/cancel/`
- `/api/v1/backstage/marketing/announcements/:id/delivery-actions/`
- `/api/v1/backstage/marketing/announcements/:id/photo/`
- `/api/v1/backstage/marketing/announcements/:id/reconcile-deliveries/`
- `/api/v1/backstage/marketing/announcements/:id/reject/`
- `/api/v1/backstage/marketing/announcements/:id/reschedule/`
- `/api/v1/backstage/marketing/announcements/:id/retry-deliveries/`
- `/api/v1/backstage/marketing/announcements/:id/rewrite/`
- `/api/v1/backstage/marketing/announcements/:id/suggestions/:ref/disposition/`
- `/api/v1/backstage/marketing/audience/count/`
- `/api/v1/backstage/marketing/decisions/`
- `/api/v1/backstage/marketing/history/`
- `/api/v1/backstage/marketing/options/`
- `/api/v1/backstage/marketing/offers/`
- `/api/v1/backstage/marketing/platforms/`
- `/api/v1/backstage/marketing/preview/`
- `/api/v1/backstage/marketing/rules/`
- `/api/v1/backstage/marketing/rules/:id/`
- `/api/v1/backstage/marketing/rules/:id/fire/`
- `/api/v1/backstage/marketing/security/device/`
- `/api/v1/backstage/marketing/security/device/options/`
- `/api/v1/backstage/marketing/security/device/register/`
- `/api/v1/backstage/marketing/security/device/register/options/`
- `/api/v1/backstage/marketing/security/dual-control/`
- `/api/v1/backstage/marketing/security/freeze/`
- `/api/v1/backstage/marketing/security/second-control/:ref/`
- `/api/v1/backstage/marketing/security/second-control/request/`
- `/api/v1/backstage/marketing/security/step-up/`
- `/api/v1/backstage/marketing/security/unfreeze/`
- `/api/v1/backstage/marketing/telemetry/vital/`
- `/api/v1/backstage/marketing/templates/`
- `/api/v1/backstage/marketing/templates/:id/`
- `/api/v1/backstage/marketing/v2/`
- `/api/v1/backstage/marketing/v2/announcements/:id/`
- `/api/v1/backstage/marketing/v2/history/`
- `/api/v1/backstage/marketing/whatsapp-template/`
- `/api/v1/backstage/marketing/whatsapp-template/test/`
<!-- marketing-api-routes:end -->

### Ofertas e cupons

`GET /marketing/offers/` exige `shop.view_marketing` e devolve a lista junto das
opções server-owned de produtos, coleções, canais, fulfillment, segmentos e fuso da
loja. `POST /marketing/offers/` exige `shop.edit_marketing_campaigns`, aceita somente
os campos documentados pela própria tela e cria a regra inteira em uma transação.
Erro de validação não deixa `Promotion` nem `Coupon` parcial.

Cupom sempre recebe uma `Promotion` própria. Essa separação preserva o motor canônico:
uma promoção que possui cupom é excluída das promoções automáticas e só é resolvida
quando a sessão carrega o código. A API não muda precedência nem empilhamento.

| Regra preservada | Comportamento |
|---|---|
| percentual | 1 a 100; compete por item e o maior desconto vence |
| valor fixo | inteiro positivo em centavos; aplica uma vez no pedido |
| entrega grátis | `0` cobre todo o frete; valor positivo limita a renúncia |
| pedido mínimo | inteiro não negativo em centavos |
| produtos e coleções | listas vazias abrangem o catálogo; referências precisam existir |
| canais e fulfillment | listas vazias abrangem todos; valores são validados no servidor |
| cupom | código normalizado em maiúsculas, único e necessário para ativar sua promoção |
| limite de usos | `0` é ilimitado; contagem continua no mecanismo atômico existente |

O cockpit permite somente criar e listar. Editar, desativar ou excluir uma regra já
criada permanece fora desta superfície.

## Projeção e comandos

As leituras v2 são o limite gerado e versionado:

- fonte: `shopman/backstage/projections/marketing_v2.py`;
- JSON Schema: `contracts/projections/marketing_v2.schema.json`;
- OpenAPI 3.1: `contracts/openapi/marketing_v2.openapi.json`;
- cliente: `surfaces/marketing-nuxt/app/generated/marketingClient.ts`;
- verificação: `python manage.py export_marketing_client --check`.

Projection não carrega rótulo final, copy de UX, PII nem membership. A apresentação
pt-BR mora no Nuxt. Cada ação vem resolvida pelo backend com método, disponibilidade,
motivo, versão, esquema, idempotência e confirmação. O cliente não deduz autorização
nem transição a partir do status.

Comandos sensíveis usam CAS, idempotência, confirmação contextual e comprovante.
A cerimônia mede a consequência, e a consequência é medida em **pessoas que recebem
mensagem** — nunca em plataformas, que é outra grandeza:

- **`fire`** não pede cerimônia nenhuma (modo `none` — cria rascunho em revisão e não
  entrega);
- **postagem pública** pede sempre só o resumo + um toque, qualquer que seja o número de
  plataformas: ela se apaga, não custa por pessoa e alcance não é fatura;
- **mensagem direta** pede a **frase digitada (`ENVIAR <pessoas>`) SEMPRE**, de uma
  pessoa em diante: o atrito segue o que não tem desfazer, e mensagem enviada não se
  apaga. O que escala com o limiar da loja é o resto —
  `max(piso, min(percentual × base de clientes, teto de gasto ÷ custo por mensagem))`:
  abaixo dele, só a frase; dele até `× múltiplo`, frase + senha; daí em diante, frase +
  TOTP + duplo controle;
- **disparo misto** é decidido pela parte de mensagem, porque é a irreversível — e a
  frase continua sendo `ENVIAR <pessoas>` mesmo com o botão dizendo "Disparar agora": o
  que se digita é o número que não volta, nunca a soma de pessoas com murais;
- os cinco ajustes (percentual, teto de gasto, custo por mensagem, piso e múltiplo) vivem
  em `Shop.defaults["marketing"]`, editáveis em Loja → Integrações → "Cerimônia do
  disparo", que mostra a base viva e a conta ao lado dos campos. Base de clientes = o
  cadastro ativo (`Customer.is_active=True`); o histórico do Yooga vive no B.I. e não
  cria cadastro.

Agendar não é mais barato que entregar agora, e a obrigação de agendar acima de 2.000
conta mensagens. A quota diária de 5.000 destinos externos e o teto de 5.000 por comando
continuam somando mensagens + postagens, porque ali a pergunta é volume, não risco. Ver
[ADR-031](../decisions/adr-031-marketing-ceremony-proportional-to-consequence.md) e
[ADR-032](../decisions/adr-032-marketing-ceremony-threshold-is-proportional.md) e
[ADR-033](../decisions/adr-033-marketing-typed-phrase-follows-the-irreversible.md).

**O selo** (V4-MKT, prévia `marketing-decisoes4.html`): a caixa de confirmação da
aprovação é a mesma de antes (mesmo desafio, mesma frase, mesma senha/TOTP, mesmo
duplo controle) com o desenho da v4. No celular ela sobe do pé como folha; o carimbo
marca o que faz algo sair; os destinos vêm um por linha, cada um na sua grandeza
(`sealRows`: "1 postagem" por mural, "N pessoas" na mensagem direta, nunca somados), e
a frase de consequência separa o que volta do que não volta (`sealConsequence`:
"Mensagem enviada não volta. Postagem pode ser apagada depois, na plataforma."). A
confirmação pela digital do dispositivo e o pedido à segunda pessoa por push (ROUNDS
UX-M1) são função nova e não estão no cockpit.

O desafio de confirmação diz por que pediu: `ceremony_reason` vale `direct_message`
quando a frase veio da mensagem e `""` quando não houve frase; `direct_message_count`,
`public_post_count` e `ceremony_threshold` completam a explicação.
Outbox, público selado, artefato imutável, destinos e tentativas formam o grafo durável.
`accepted_unconfirmed`, `confirmed`, falha final, falha repetível e `unknown` são estados
distintos. `unknown` nunca recebe repetição cega.

**O incerto é conferido sozinho** (decisão do dono, 2026-10-03, SUITE-UX §5.1). A
cada passada com `--with-reconciliation`, `request_automatic_reconciliations`
(`marketing_delivery_recovery.py`) cria a consulta de cada tentativa `unknown` que
ainda não teve nenhuma, com recibo de sistema (`actor` nulo, `actor_ref`
`system:marketing-reconciliation`, auditoria `automatic_reconcile_unknown`), só para
plataformas com provedor registrado no ciclo. A guarda é a mesma do comando do
operador: a consulta usa `lookup`, que não tem `send`, e o resultado nunca volta
para a fila de envio. Cada tentativa recebe **uma** consulta automática: se a
plataforma responder "não sei" de novo, o destino entra na fila de decisões como
`reconcile_unknown`, e consultar de novo é gesto do operador (o comando
`reconcile-deliveries/`, com `shop.reconcile_unknown_marketing`). A fila mostra o que
o sistema fez em `automatic_checks`: "O sistema está consultando sem reenviar ·
automático" ou "O sistema consultou sem reenviar: publicado às 09:58 · automático".

Dialeto de erro: comandos respondem `{code, detail, field_errors}`, o CRUD de
campanhas/modelos `{detail, field, fields}` e o 401 leva `code`; `detail` está sempre
presente. Ver [Superset do Marketing em `errors.md`](errors.md#superset-do-marketing-deliberado).

## Capacidades

| Capacidade | Autoriza |
|---|---|
| `shop.view_marketing` | leitura agregada |
| `shop.edit_marketing_campaigns` | criar/editar campanhas; editar anúncio antes de aprovar (`PATCH announcements/:id/`) |
| `shop.edit_marketing_templates` | criar/editar modelos |
| `shop.preview_marketing_audience` | contar e pré-visualizar público |
| `shop.approve_marketing_announcements` | aprovar, rejeitar e usar assistência de texto |
| `shop.publish_marketing_announcements` | publicar, agendar, cancelar e reagendar |
| `shop.fire_marketing_campaigns` | disparar campanha para revisão |
| `shop.retry_failed_marketing` | repetir somente falhas seguras |
| `shop.reconcile_unknown_marketing` | consultar resultado incerto sem reenviar |
| `shop.send_marketing_test` | um alvo de teste cadastrado e verificado |
| `shop.configure_marketing_platforms` | configurar plataformas |
| `shop.audit_marketing` | auditoria agregada no Admin |
| `shop.access_marketing_delivery_pii` | acesso excepcional a PII protegida |
| `shop.freeze_marketing` | congelar/descongelar efeitos externos |

`shop.manage_campaigns` é legado e só mantém leitura/edição/prévia durante a transição;
não concede aprovação, publicação, disparo, teste ou configuração.

## Flags e configuração segura

| Configuração | Owner | Padrão/failsafe | Expira ou é reavaliada |
|---|---|---|---|
| `SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED` | Platform/SRE | `false`; sem handoff | MKT-054 |
| `SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` | Platform/SRE | `false`; sem tentativa | MKT-054 |
| `SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED` | Release Manager | `false`; comando unitário não cruza a fronteira | desligar após o canário |
| `SHOPMAN_MARKETING_DELIVERY_ADAPTERS` | Platform Owner | vazio; canal indisponível | por adapter/canário |
| `SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED` | Platform Owner | `false`; adapter durável do WhatsApp nem é registrado — campanha aprovada fica na fila | por etapa, junto do modo: `canary` → `open` |
| `SHOPMAN_MARKETING_WHATSAPP_MODE` | Platform Owner | `blocked`; nenhum evento de Marketing sai por WhatsApp. `canary`/`open` sem cache compartilhado continuam bloqueados | por etapa: `canary` → `open` |
| `SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS` | Platform Owner | vazio; `canary` sem lista fica bloqueado | esvaziar ao fim do ensaio |
| `SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS` | Platform Owner | `120`; inválido volta ao padrão | revisar com a latência observada no ensaio |
| `SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado. No alpha: `true` só no spec vivo desde 2026-09-25 (ensaio publicado) | desligar se o token da Página for anulado |
| `SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter experimental nem é registrado | somente após OAuth, revisão e gate TikTok |
| `SHOPMAN_MARKETING_TARGET_HMAC_KEY` e versão | Segurança | vazio bloqueia materialização segura | rotação versionada |
| `SHOPMAN_MARKETING_TEST_TARGETS_JSON` | Platform Owner | `{}`; nenhum alvo de teste | remover alvo ao fim do teste |
| `SHOPMAN_MARKETING_MEDIA_HOSTS` | Segurança/Marca | vazio; mídia externa bloqueada | revisão por host |
| `SHOPMAN_MARKETING_MEDIA_PROBE_ENABLED` | Platform Owner | `true`; a foto do Google é lida antes de aprovar. `false` só onde não há rede (testes, simulador) | — |
| `SHOPMAN_MARKETING_AI_ASSIST_V2` | Produto | `false`; assistência invisível | MKT-054 |
| `SHOPMAN_MARKETING_AI_PROVIDER_POLICY_APPROVED` | Jurídico/Segurança | `false`; chave não basta | por política do fornecedor |

`SHOPMAN_MARKETING_SIMULATION_ENABLED`, o bypass local de horário e os fluxos
sintéticos pertencem exclusivamente a `config.settings_marketing_demo`. A simulação
recusa ambiente não local e qualquer flag que permita saída externa. Nenhuma flag
desliga consentimento, permissão, CSRF, redaction, unicidade ou revalidação pré-envio.

WhatsApp de Marketing (campanha e "Me avise") abre por modo, não por credencial. Cada
mensagem com flow reserva o contato no cache compartilhado durante a janela de
assentamento, antes de gravar qualquer campo; outra mensagem com flow para a mesma
pessoa volta depois (`subscriber_busy`, retentável, nunca `unknown`). Em `canary`, quem
está fora da lista é suprimido no claim (`whatsapp_canary_recipient_excluded`) e o
adapter recusa na última porta; a prontidão aparece como `degraded` com
`canary_recipients` (contagem, nunca refs). Decisão e limites em
[ADR-009](../decisions/adr-009-whatsapp-via-manychat.md).

Campanha de WhatsApp aprovada chega ao ManyChat pelo ledger durável só quando
`SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED` registra o adapter
`marketing_delivery_whatsapp` — com a flag desligada a prontidão diz
`platform_switched_off` e os destinos ficam na fila, sem envio. O adapter confere o modo na última
porta, relê consentimento, exige o flow selado na aprovação e monta as variáveis do
flow só do artefato aprovado (corpo, link, foto e fatos selados; do destino, só
telefone e primeiro nome). Aceite do ManyChat é `accepted_unconfirmed`; resposta
ambígua depois de possível escrita é `unknown`; recusa antes de chamar é falha final
com código; contato ocupado volta pela fila. A etapa que leva o destino ao provedor
roda no `maintenance-worker`, sem componente próprio — ver
[Entrega sem componente próprio](#entrega-sem-componente-próprio).

Cada mensagem com flow de Marketing grava o conjunto completo de campos declarado para o
evento (`MARKETING_FLOW_FIELDS`), com vazio para o que não tiver — nunca herda preço,
nome ou link da mensagem anterior.

Campanha geral por WhatsApp exige um **mínimo de pessoas elegíveis configurável no
Admin** (Configuração → A loja → Integrações → "Campanhas de WhatsApp"), gravado em
`Shop.defaults["marketing"]["whatsapp_minimum_audience"]`. Aumentar o número impede que
uma campanha "geral" vire mensagem mirada em uma pessoa. **Padrão 1** (chave ausente),
por decisão do dono em 2026-09-17: no início da operação um mínimo alto seguraria
campanhas boas antes de a casa sentir o impacto. O Admin aceita inteiro a partir de 1 e
recusa zero, negativo e texto com mensagem em português; quem mudou e quando fica no
histórico da página (`LogEntry`). A aprovação lê o valor na hora e, abaixo dele, recusa
com `audience_below_minimum`, `minimum_count` igual ao número configurado e o número na
mensagem. No modo `canary` o mínimo não se aplica, porque só a lista de canário
controlada pela operação recebe — a aprovação registra `canary=true` com o
`minimum_count` que não valeu, e o cockpit diz "Ensaio: o mínimo de N não vale; só a
lista de canário recebe". Em `blocked` e `open` o mínimo vale.

Instagram/Facebook usam `META_PAGE_ACCESS_TOKEN`; Instagram também exige
`META_IG_USER_ID`, conta Instagram Business ligada à página, e Facebook,
`META_PAGE_ID`. Google exige token OAuth com escopo
`business.manage`, `GOOGLE_BUSINESS_ACCOUNT_ID` e `GOOGLE_BUSINESS_LOCATION_ID`.
O token Google configurado nesta etapa é estático: serve ao canário, mas ativação
contínua exige decidir e validar seu ciclo de renovação. Credencial presente não liga
publicação: a flag da plataforma e os consumidores duráveis — ou o canário unitário
explicitamente armado — permanecem gates independentes. Em `DEBUG`, adapter externo
também exige o opt-in geral de saída externa.

O `META_PAGE_ACCESS_TOKEN` do alpha é token de **Página** derivado do usuário de
sistema `shopman-api` do Business Manager (app "App Nelson"), com expiração **Nunca** e
os escopos `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`,
`instagram_basic` e `instagram_content_publish`. Token de Página derivado de token de
usuário pessoal vence junto com ele (o Graph API Explorer usa o token pessoal por
padrão): confira no Access Token Debugger que o usuário é `shopman-api` e "Expira:
Nunca" antes de colar no painel. Ensaio de 2026-09-25: anúncio 34 (campanha "Ensaio
Facebook", só Facebook, revisão ligada) publicou foto + legenda na Página
`764222643620409`, recibo `accepted` no ledger e post conferido na Página. O adapter
chama a Graph API `v21.0` (`META_API_VERSION`), que expira em 2027-01-21.

O app OAuth do Google é do tipo **Interno** no Google Cloud: o Google não pede página
inicial pública nem verificação do app, então o Storefront não tem página própria para
ele.

TikTok ainda não integra o catálogo selecionável. O adapter Direct Post de foto é
somente uma fronteira testável e inerte: token estático serve no máximo a canário
controlado; operação contínua exige armazenamento OAuth com renovação, consulta de
`creator_info`, aprovação de `video.publish` e auditoria Direct Post. A simples
presença da flag ou da credencial não autoriza adicionar TikTok a uma campanha.

### Plataforma desligada × integração não registrada

Os adapters de Instagram, Facebook, Google e WhatsApp existem no código; a flag de
cada plataforma (tabela acima) decide se ele é registrado em
`SHOPMAN_MARKETING_DELIVERY_ADAPTERS` neste ambiente. `Shop.integrations`, quando
define `marketing_delivery`, responde antes das settings, como em `get_adapter`.
O estado de cada plataforma sai de `marketing_delivery_runtime.delivery_lanes()`,
sem chamar adapter nem provedor:

| Estado | Quando | Prontidão | Worker | Log |
|---|---|---|---|---|
| `registered` | há integração registrada | segue para simulação/credencial/probe | pede o adapter | — |
| `switched_off` | nada registrado e a flag da plataforma desligada | `blocked`, `platform_switched_off`, "desligada neste ambiente"; a ação cita a flag | não pede o adapter; destinos seguem `queued`, sem reserva | nenhum |
| `unconfigured` | nada registrado com a flag ligada | `blocked`, `publication_adapter_missing` / `whatsapp_durable_provider_missing`, "erro de configuração" | pede o adapter | WARNING do `get_adapter` a cada ciclo |

Desligada é escolha de quem opera; o aviso do `get_adapter` fica para a integração
que deveria existir e não existe. A aprovação não recusa plataforma desligada: o que
for aprovado para ela é materializado e fica `queued`. No cockpit, o resultado da
plataforma diz "aguardando a plataforma ligar", e não só "na fila"; o
`diagnose_marketing` mostra o bloco `lanes` (estado, flag e destinos na fila) e
aponta `observe:platform_switched_off_holds_queued`. Ao ligar, cada destino ainda
passa pelas conferências de prazo e consentimento antes do envio.

## Entrega sem componente próprio

A etapa final da entrega — destino `queued` → adapter → provedor
(`process_marketing_delivery`) — **não tem componente próprio** no App Platform. Ela roda
dentro do `maintenance-worker` que já existe (`python manage.py maintenance_worker`, ciclo
de 300 s), uma passada por ciclo, logo **depois** de `process_marketing_outbox`. A ordem é
proposital: a outbox publica a Directive, o dispatch por signal materializa e enfileira os
destinos no commit, e a passada de entrega os encontra no mesmo ciclo. Decisão do dono
(2026-09-17): um worker a mais custaria mais do que a entrega que ele faz.

| Opção da passada | Valor | Por quê |
|---|---|---|
| `worker_id` | `maintenance_worker:marketing-delivery` | estável: o `lease_owner` diz qual componente segura o destino |
| `limit` | `20` destinos (e 20 consultas) por passada | uma mensagem de WhatsApp com flow custa ~20 chamadas ao ManyChat; o lote cabe no ciclo |
| `lease_seconds` | `300` | cobre a passada inteira; se o processo cair, o destino volta a ser elegível em até 5 min |
| `--with-reconciliation` | ligado | pede sozinho **uma** consulta somente-leitura por tentativa `unknown` (decisão do dono, 2026-10-03) e executa as consultas pendentes, do sistema ou do operador; `unknown` nunca é reenviado |
| `--watch` / `--with-outbox` | desligados | passada única; a outbox já roda como tarefa própria do ciclo |

`SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` continua sendo o portão: desligada, a passada
volta calada (sem aviso a cada ciclo) e nenhum destino é reservado. Exceção na entrega é
logada e **não** derruba o ciclo das demais tarefas. Ligar a consequência é ligar as flags;
não há worker para criar, escalar ou pagar. O comando avulso continua servindo ao
simulador local (`make marketing-simulator`) e a ensaio explícito.

**Latência esperada (aprovação → chamada ao provedor).** Uma campanha aprovada entra na
próxima passada, não sai no mesmo segundo. No pior caso, a aprovação chega logo depois da
outbox do ciclo corrente e espera o ciclo seguinte: **até ~300 s + a duração das tarefas
que vêm antes da outbox no ciclo + a própria passada**, na prática **até ~7 minutos** para
o último dos primeiros 20 destinos. Cada 20 destinos a mais somam um ciclo (≈300 s): 100 pessoas
elegíveis levam até ~30 minutos para esgotar a fila. Se a Directive não for processada no
commit e ficar para o `directive-worker`, soma-se mais um ciclo. Horário comercial,
contato ocupado (`subscriber_busy`) e freeze adiam por conta própria. **"Enviar agora"
significa "na próxima passada" e pode levar alguns minutos** — não é defeito.

## Operação, diagnóstico e gates

- `make marketing-diagnose`: leitura agregada sem PII ou chamada de provider;
- `make marketing-drills`: oito incidentes sintéticos e testes dos runbooks;
- `make marketing-capacity`: 200 mil candidatos e 20 mil destinos, sem provider;
- `make marketing-simulator`: outbox → ledger → comprovante local, sem rede;
- `python manage.py run_marketing_publication_canary --announcement-id ID
  --platform instagram`: preflight somente leitura a partir do número já visível na
  URL; imprime a consequência e o comando exato, sem publicar;
- `make admin`: garante o corte Nuxt operacional/Admin audit-only;
- job `Marketing — cadeia completa`: instalação, unit/component, lint, tipos, build,
  E2E, acessibilidade, visual, segurança e auditoria de dependências.

Runbooks: [`docs/runbooks/README.md`](../runbooks/README.md). Simulador:
[`docs/operations/marketing-local-simulator.md`](../operations/marketing-local-simulator.md).
Canário público:
[`docs/operations/marketing-publication-canary.md`](../operations/marketing-publication-canary.md).
Capacidade: [`docs/engineering/marketing-capacity-gate.md`](../engineering/marketing-capacity-gate.md).

## Deploy e estado de rollout

O host é `mkt.<domínio>`, com `NUXT_DJANGO_BASE_URL`/`NUXT_PUBLIC_DJANGO_BASE_URL`
apontando para `api.<domínio>` e `NUXT_PUBLIC_OPERATOR_HUB_URL` para `central.<domínio>`.
Os dois blueprints versionados usam `/health/live` no `health_check` e no
`liveness_health_check`: o probe da plataforma não consulta o Django. `/health/ready`
fica para smoke e diagnóstico. Desde a
[ADR-030](../decisions/adr-030-operator-nuxt-dois-servicos.md) o Marketing roda no
service de grupo `operator-office` (com B.I. e Compras): o ingress de `mkt.` aponta
para ele e o roteador do contêiner entrega ao Nitro do Marketing. A sonda da
plataforma recebe o `/health/live` agregado do grupo (200 só com os três Nitro de
pé); no host `mkt.`, `/health/live` e `/health/ready` continuam sendo os do próprio
Marketing. O envelope CSP/nonce continua gerado pelo Nitro do Marketing; o roteador
não reescreve cabeçalho. Eles são referência; nunca devem sobrescrever o spec vivo sem preservar
segredos e obter autorização explícita.

Em 2026-09-11, o cockpit e o pipeline-base de `#601` estão em produção e o teste
WhatsApp unitário para contato verificado foi recebido pelo proprietário. Os adapters
de postagem pública e a escolha Story/Feed estão em branch isolada, desligados por
default e ainda sem deploy. Publicar Story, Feed, página do Facebook ou atualização do
Google continua sendo gate humano: requer peça válida, conferência da prévia, conta
correta, credenciais/escopos, autorização explícita e canário público observável. Teste
local não substitui esse gate.
