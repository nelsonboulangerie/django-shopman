# WhatsApp — Pacote de templates Meta (pronto para submissão)

> Textos pt-BR dos templates transacionais da Nelson, **estruturados para maximizar aprovação**
> da Meta. Não é "burlar regra" — é **conformar ao formato** que a Meta exige.
> Pesquisa de regras: Meta + BSPs, jun/2026. Medição contra o código: 02/09/2026.

**Submissão é pelo ManyChat.** O número da padaria é controlado por ele e continua sendo.
Meta Cloud API direta, WhatsApp Flows e segundo número estão **descartados**: a burocracia
da Meta (verificação, template aprovado, janela de 24h) é idêntica nos dois caminhos, então
o caminho direto não compra nada e custa uma migração.

---

## ⛔ ANTES DE SUBMETER — resolvido em 02/09

Três templates têm botão de URL e os três apontavam para lugar nenhum. O que se descobriu
ao medir contra o código, e o que ficou decidido:

**1. A base da loja é `https://menu.nelsonboulangerie.com.br`.** É o valor de
`SHOPMAN_STOREFRONT_BASE_URL` no spec **vivo** do `shopman-alpha`. O doc escrevia o apex.

> ⚠️ `.do/app.alpha-subdomains.yaml` ainda diz `https://alpha.nelsonboulangerie.com.br`,
> morto desde o corte de domínios de 01/09. Quem aplicar aquele spec quebra todo link de
> cliente **e** o prefixo de um template já aprovado — que é um ciclo de re-submissão.

**2. `/pedido/{ref}/pagar` não existe.** O único caminho é `/pedido/{ref}`
(`storefront_links.path_order_tracking`). Acompanhar e pagar são a MESMA tela: o Pix e o
cartão vivem inline no acompanhamento (PAYMENT-TRACKING-MERGE). Não há tela de pagamento.

**3. O magic link NÃO pode ser o botão — e não é escolha, é impossibilidade.**
No caminho de flow, as variáveis do template aprovado saem dos **campos personalizados** do
assinante (`_push_custom_fields`). E `notification_manychat._safe_field_value` recusa, por
construção, gravar link de acesso pessoal como campo personalizado: o token passaria a viver
em texto claro no perfil do cliente dentro de uma ferramenta SaaS de marketing, legível por
qualquer pessoa com acesso à conta e utilizável enquanto o cliente não clicasse.

> ⚠️ Essa recusa nascera olhando só o `action_url` (campanha/estoque) e **não via** os três
> links que todo aviso de pedido carrega — `tracking_url`, `payment_url`, `reorder_url` saíam
> com o token inteiro. Era inerte apenas porque nenhum flow estava mapeado; **mapear o
> primeiro flow é que ligava o vazamento**. Corrigido em 02/09: a recusa passou a ser do
> VALOR (qualquer chave com `?t=`), com gêmea pública `<nome>_public` informada pelo emissor.
> Guardado por `test_the_order_links_do_not_leak_either`.

### Decisão: o botão leva a REF, não o link

Todos os botões de URL usam **um só prefixo fixo**, com a ref no fim:

```
https://menu.nelsonboulangerie.com.br/pedido/{{1}}
```

A variável `{{1}}` do botão mapeia para o campo personalizado **`order_ref`** — não para
`tracking_url`. Assim nenhuma URL precisa virar campo personalizado, e o token não tem por
onde vazar nem por acidente.

Quem clica sem sessão no aparelho **não bate num 404**: `/pedido/{ref}` é fechado por sessão
(`customer_orders.request_can_access_order`), e a loja responde com "Ele pode estar em outra
conta ou em outro aparelho — entre com seu telefone" e um botão **Entrar** que volta para o
mesmo pedido (`storefront-nuxt/app/presentation/orderAccess.ts`). O link é honesto e se
recupera sozinho. O preço é um toque a mais; o troco é nenhum segredo fora de casa.

Os canais que interpolam o texto na hora — SMS e e-mail — **seguem recebendo o magic link**.
Eles não gravam nada em lugar nenhum.

---

## Regras de ouro (por que cada template abaixo passa)

1. **Categoria certa.** Status de pedido/pagamento = **Utility**. Anúncio e fornada = **Marketing**.
   Categoria errada é a causa nº 1 de reprovação — a Meta avalia a intenção antes do conteúdo.
2. **Nunca placeholder no início ou no fim** do corpo. `{{1}}` no começo/fim = reprovação
   automática. Todo corpo abaixo **começa e termina com texto literal**.
3. **Sample values em toda variável** na submissão (acelera e evita reprovação).
4. **Utility = transacional puro.** Sem desconto, oferta, upsell, "aproveite", CTA persuasivo —
   senão vira Marketing (reprova como Utility e custa mais).
5. **Links viram BOTÃO de URL**, prefixo fixo + variável no FIM. Nunca URL solta no fim do texto.
6. **Corpo majoritariamente literal.** Template que é quase só variável reprova: a Meta precisa
   ver o que a mensagem diz. Vale para o `anuncio_novidade`, o mais arriscado do pacote.
7. Sem pedir dado sensível no corpo (cartão, CPF) — reprovação automática.

### Sample values do pacote

| Variável | Sample |
|---|---|
| Nome do cliente | `Ana` |
| Ref do pedido | `NB-260902-A17` |
| Total | `R$ 38,00` |

> ⚠️ A ref **não** é `NB-1042`. O formato real é `{PREFIXO}-{AAMMDD}-{L##}`
> (`orderman/ids.py::generate_order_ref`), com o prefixo `NB` vindo de `order_ref_prefix`
> na config do canal. Sample com formato irreal atrapalha a revisão do botão.

---

## OTP — não existe neste pacote

O ManyChat **não tem a categoria Authentication** (só Marketing e Utility), então WhatsApp-OTP
é impossível por ali. **O código de verificação vai por SMS (Comtele)** — decidido, não é
pergunta aberta. Não há template de OTP a submeter.

---

## Utility — cliente

Formato: **Nome · Corpo · Variáveis · Botão**. Idioma `pt_BR`, categoria **Utility**.
Onde há botão, ele é sempre `https://menu.nelsonboulangerie.com.br/pedido/{{1}}`,
com `{{1}}` mapeado ao campo personalizado `order_ref` e sample `NB-260902-A17`.

### `pedido_recebido` — evento `order_received`
- Corpo: `Olá, {{1}}! Recebemos o seu pedido {{2}}. Vamos conferir a disponibilidade e avisamos a próxima etapa por aqui.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Acompanhar pedido`

### `pedido_confirmado` — evento `order_accepted`
- Corpo: `Olá, {{1}}! Confirmamos o seu pedido {{2}}. O total é {{3}}. Obrigado por comprar conosco.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17` · `{{3}}`=`R$ 38,00`
- Botão URL: `Acompanhar pedido`

### `pedido_nao_confirmado` — evento `order_rejected`
- Corpo: `Olá, {{1}}! Não conseguimos confirmar o seu pedido {{2}} desta vez. Nada foi cobrado. Se quiser entender o motivo, é só falar com a gente por aqui.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Ver pedido`

### `pedido_em_preparo` — evento `order_preparing`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} já está em preparo. Avisaremos assim que estiver pronto.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_pronto_retirada` — evento `order_ready_pickup`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} está pronto para retirada. Estamos te esperando.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_pronto_entrega` — evento `order_ready_delivery`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} está pronto e sairá para entrega em breve.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_saiu_entrega` — evento `order_dispatched`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} saiu para entrega e chega logo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_entregue` — evento `order_delivered`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi entregue. Obrigado pela preferência.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_cancelado` — evento `order_cancelled`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi cancelado. Se tiver qualquer dúvida, estamos à disposição.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pedido_agendado_lembrete` — evento `preorder_reminder`
- Corpo: `Olá, {{1}}! Lembrando que o seu pedido {{2}} está agendado para amanhã. Já estamos preparando tudo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pagamento_solicitado` — evento `payment_requested`
- Corpo: `Olá, {{1}}! Conferimos a disponibilidade do seu pedido {{2}} e ele está reservado. Agora falta o pagamento. Toque no botão abaixo para concluir.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Pagar pedido`

### `link_pagamento_enviado` — evento `payment_link_sent`
Pedido remoto anotado no PDV (encomenda por telefone/WhatsApp): a venda fechou e o cliente paga pelo link.
- Corpo: `Olá, {{1}}! Anotamos o seu pedido {{2}}, no total de {{3}}. Para garantir o pedido, é só pagar pelo botão abaixo até {{4}}. Depois disso a reserva é liberada. Qualquer coisa, é só responder esta mensagem.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17` · `{{3}}`=`R$ 38,00` · `{{4}}`=`amanhã às 9h`
- Botão URL (dinâmico): `Pagar pedido` → a URL da cobrança inteira (campo `checkout_url`; é a sessão hospedada do gateway, não uma página da loja)
- No ManyChat, cada variável é ligada ao campo personalizado de MESMO nome: `customer_name_greeting`, `order_ref`, `total`, `payment_deadline`, `checkout_url` (ver `WP-PAGAMENTO-LINK-E-TEF.md`, Frente 2).
- ⚠️ `{{4}}` é o `payment_deadline` cru ("hoje às 16h"), e a Meta não aceita variável vazia nem com quebra de linha — o template aprovado PRESSUPÕE prazo. Todo link nasce com `expires_at` (`min(agora + janela do canal, corte do atendimento)`, ver `docs/guides/payments.md`); o único caso sem prazo é um adapter que falhou ao gravá-lo, e aí o texto direto (`sendContent`) sai com a frase auto-suprimida.

### `pagamento_confirmado` — evento `payment_confirmed`
- Corpo: `Olá, {{1}}! Recebemos o pagamento do seu pedido {{2}}. Avisamos a cada passo daqui em diante.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pagamento_lembrete` — evento `payment_reminder`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} ainda aguarda o pagamento via PIX. Toque abaixo para concluir.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Concluir pagamento`

### `pagamento_expirado` — evento `payment_expired`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi cancelado porque o pagamento via PIX não foi confirmado a tempo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`

### `pagamento_falhou` — evento `payment_failed`
- Corpo: `Olá, {{1}}! Não conseguimos preparar o pagamento do seu pedido {{2}}. Abra o pedido pelo botão abaixo para tentar de novo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Abrir pedido`

### `fila_vaga_disponivel` — evento `waitlist_available`
- Corpo: `Olá, {{1}}! A fornada que você esperava saiu. Confirme o pedido {{2}} pelo botão abaixo para garantir o seu.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Confirmar pedido`

> ⚠️ Não ligar `waitlist.enabled` antes do #392 estar no ar — ver a política de fila.

### `fila_vaga_liberada` — evento `waitlist_released`
- Corpo: `Olá, {{1}}! O prazo de confirmação do pedido {{2}} passou e liberamos a sua vaga. Nada foi cobrado, e é só entrar na fila da próxima fornada.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-260902-A17`
- Botão URL: `Ver pedido`

### `produto_chegou` — evento `stock_arrived`
- Corpo: `Olá, {{1}}! O {{2}} que você pediu para ser avisado chegou. Toque abaixo para ver na loja.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`Croissant`
- Sem botão de URL (ver ressalva).

> ⚠️ **Este template atende DUAS situações diferentes, e é por isso que o corpo é curto.**
> `stock_arrived` sai por dois caminhos: com **reserva materializada** e prazo
> (`handlers/_stock_receivers.py` — `reserve_note=" Sua reserva esta garantida."`,
> `deadline_note=" Confirme até as 18:30."`) e pelo **"Me avise"** puro
> (`storefront/services/stock_alerts.py`), onde os dois vêm **vazios**.
>
> Um corpo aprovado que diga "a sua reserva está garantida até {{3}}" fica **falso** no
> segundo caminho e **quebrado** quando a variável chega vazia. E não dá para ter um
> template por situação: `whatsapp_flow_ns` é **um por evento**, e o evento é o mesmo.
>
> Consequência aceita: **o prazo da reserva não viaja no WhatsApp** por este template. Ele
> continua saindo inteiro por SMS e e-mail, que interpolam o texto na hora. Recuperar o
> prazo aqui pede uma variável nova com só a hora (`18:30`, sem a frase pronta em volta) e
> um evento separado para a reserva — WP próprio, não este.
>
> ⚠️ **Categoria é o risco real deste.** Aviso de disponibilidade de produto costuma ser
> lido como Marketing pela Meta, e sem a reserva no corpo o argumento de Utility fica mais
> fraco. Submeta como Utility; se reprovar, o corpo não muda — só a categoria.
>
> ⚠️ O botão fica de fora de propósito: o destino deste aviso não é `/pedido/{ref}`, é o
> produto ou a sacola (o código entrega esse link em `action_url`). Um botão aqui exigiria
> um segundo prefixo fixo — decidir isso é WP próprio.

---

## Utility — fornecedor

Audiência diferente: quem recebe é o contato comercial do fornecedor, não um cliente
(`backstage/services/purchase.py::_supplier_dispatch_route`, modelo `SupplierContact`).

### `pedido_compra` — evento `purchase_request`
- Corpo: `Olá! Chegou um pedido de compra da {{1}}, número {{2}}: {{3}}, quantidade {{4}}. Por favor, confirme disponibilidade, prazo e valor final por aqui.`
- Vars: `{{1}}`=`Nelson Boulangerie` · `{{2}}`=`PC-260902-9C4A1F` · `{{3}}`=`Farinha de trigo tipo 1` · `{{4}}`=`5 sc`
- Sem botão (o fornecedor responde na conversa; não há tela dele).

---

## Marketing

Categoria e custo diferentes. **Não misture com Utility** — nem "para passar".

### `saiu_do_forno` — evento `production_ready`
- Corpo: `Oi, {{1}}! Acabou de sair do forno: {{2}}. Ainda quentinho, enquanto durar.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`Pão de fermentação natural`
- Sem botão de URL (mesmo motivo do `produto_chegou`: o destino é o produto).

### `anuncio_novidade` — evento `announcement_published`
- Corpo: `Oi, {{1}}! Tem novidade na Nelson Boulangerie hoje: {{2}}. Passe na loja ou peça pelo nosso site.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`o pão de campanha voltou às quartas`

> ⚠️ **Submeta este por último.** No código, `announcement_published` é só um envelope: o
> corpo inteiro vem pronto do `AnnouncementTemplate` (`"{body}\n\n{cta} {action_url}"`). Um
> template aprovado **não** aceita corpo livre — a Meta precisa ler o que a mensagem diz, e
> um `{{1}}` que é a mensagem toda reprova.
>
> O corpo acima é a adaptação: moldura fixa + uma variável curta. Isso **restringe** o que
> uma campanha pode dizer pelo WhatsApp — o `{{2}}` passa a ser uma frase, não um texto. Se
> a casa quiser campanhas de formato livre no WhatsApp, o caminho é um template por formato,
> e isso é WP próprio.

---

## Não precisam de template

- **`access_link`** — a janela de 24h está aberta **por construção**: a pessoa acabou de
  escrever, e é isso que dispara o fluxo. Não é envio iniciado pela loja, então é mensagem
  livre. Ver o commit `0c29318a9`. **Não crie template para este.**
- **`stock_alert`** e **`purchase_receipt_rejected`** — avisos **internos**, vão para
  `compras`, não para o cliente.
- **OTP** — vai por SMS (Comtele). Ver acima.

---

## Mapa evento interno → template

⚠️ Conferido chave a chave contra `notification_manychat.MESSAGE_TEMPLATES` e
`notification_email.SUBJECT_TEMPLATES` em 02/09/2026. O mapa antigo trazia
**`order_confirmed`, que o código nunca emitiu** — o evento é `order_accepted`.

| Evento interno | Template Meta | Categoria |
|---|---|---|
| `order_received` | `pedido_recebido` | Utility |
| `order_accepted` | `pedido_confirmado` | Utility |
| `order_rejected` | `pedido_nao_confirmado` | Utility |
| `order_preparing` | `pedido_em_preparo` | Utility |
| `order_ready_pickup` | `pedido_pronto_retirada` | Utility |
| `order_ready_delivery` | `pedido_pronto_entrega` | Utility |
| `order_dispatched` | `pedido_saiu_entrega` | Utility |
| `order_delivered` | `pedido_entregue` | Utility |
| `order_cancelled` | `pedido_cancelado` | Utility |
| `preorder_reminder` | `pedido_agendado_lembrete` | Utility |
| `payment_requested` | `pagamento_solicitado` | Utility |
| `payment_link_sent` | `link_pagamento_enviado` | Utility |
| `payment_confirmed` | `pagamento_confirmado` | Utility |
| `payment_reminder` | `pagamento_lembrete` | Utility |
| `payment_expired` | `pagamento_expirado` | Utility |
| `payment_failed` | `pagamento_falhou` | Utility |
| `waitlist_available` | `fila_vaga_disponivel` | Utility |
| `waitlist_released` | `fila_vaga_liberada` | Utility |
| `stock_arrived` | `produto_chegou` | Utility |
| `purchase_request` | `pedido_compra` | Utility (fornecedor) |
| `production_ready` | `saiu_do_forno` | Marketing |
| `announcement_published` | `anuncio_novidade` | Marketing |
| `access_link` | — (janela aberta, mensagem livre) | — |
| `stock_alert` | — (interno) | — |
| `purchase_receipt_rejected` | — (interno) | — |

---

## Como ligar no código

**Use o Admin, não o `settings.py`.** `NotificationTemplate.whatsapp_flow_ns` tem precedência
sobre `MANYCHAT_FLOW_MAP` (`notification_manychat.send`), e o mapa em `config/settings.py` é
hardcoded — mexer nele custa deploy. O Admin é por evento e vale na hora.

Para cada template aprovado, o ManyChat devolve um **flow namespace** no formato
`contentAAAAMMDDHHMMSS_NNNNNN`. Grave-o em `NotificationTemplate.whatsapp_flow_ns` do evento
correspondente.

**Sem flow mapeado**, o adapter cai em `sendContent` (texto livre) e a Meta só entrega dentro
da janela de 24h — fora dela, `HTTP 400 code 3011`.

ℹ️ Preencher o `whatsapp_flow_ns` do `announcement_published` também destrava a prontidão de
campanha: `delivery_readiness._has_approved_template` considera o WhatsApp pronto justamente
por esse campo estar não-vazio.

### Campos personalizados no ManyChat

As variáveis do template aprovado saem dos **campos personalizados do assinante**, gravados
por `_push_custom_fields` antes do envio. **O campo precisa existir no ManyChat com o mesmo
nome**, senão a variável sai em branco e nada falha.

| `{{n}}` | Campo personalizado | Onde |
|---|---|---|
| Nome do cliente | `customer_name` | todos os de cliente |
| Ref do pedido | `order_ref` | todos os de pedido **e todo botão de URL** |
| Total | `total` | `pedido_confirmado` |
| Nome do produto | `product_name` | `produto_chegou`, `saiu_do_forno` |
| Nome da loja | `shop_name` | `pedido_compra` |
| Ref da compra | `purchase_ref` | `pedido_compra` |
| Material | `material_name` | `pedido_compra` |
| Quantidade | `purchase_qty_display` | `pedido_compra` |
| Corpo da campanha | `body` | `anuncio_novidade` |

⚠️ **Nunca** mapeie um botão de URL para `tracking_url` ou `payment_url`. O botão leva
`order_ref`; o prefixo já está fixo no template. Ver "ANTES DE SUBMETER".

### Critério de aceite

Template **aprovado** e **mapeado**. Só depois disso faz sentido inverter a ordem de
preferência de canal para WhatsApp primeiro (decisão de 02/09: WhatsApp primário, SMS
fallback). Inverter antes troca "SMS que chega em 76%" por "WhatsApp que não chega".

## Se algum reprovar
- Veja o motivo no painel (Meta/ManyChat). 90% é **categoria** ou **placeholder no início/fim**.
- Reenvie corrigindo só o apontado — mudar só variável de um corpo já aprovado costuma reaprovar na hora.
- Nunca mova status de pedido para Marketing "pra passar" — passa, mas cobra caro e quebra a janela grátis.

## Referências
- [WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN](../plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md)
- Meta: [template fundamentals](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview)
- ManyChat: [usar Message Templates](https://help.manychat.com/hc/en-us/articles/14281326740124-How-to-use-WhatsApp-Messages-Templates-in-Manychat)
