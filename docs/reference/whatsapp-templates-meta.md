# WhatsApp — Pacote de templates Meta

> ## ✅ Texto LIBERADO — a revisão fechou em 25/09/2026
>
> O dono revisou todas as frases de uma vez e fechou. Os corpos abaixo são a coluna
> WhatsApp daquela revisão. **Dá para submeter.**
>
> **Um template ainda não dá para submeter:** o `anuncio_novidade`, porque o destino do
> botão `Ver novidade` é decisão de quem cuida do Marketing. **Os outros 24 estão prontos.**
>
> Antes desta revisão a redação mudou duas vezes em 24 horas. Se mudar de novo, **pare de
> submeter antes de continuar**: template aprovado com texto errado não se edita, reaprova,
> e a fila da Meta leva 24-48h por rodada.

> Textos pt-BR dos templates transacionais da Nelson, **estruturados para maximizar aprovação**
> da Meta. Não é "burlar regra" — é **conformar ao formato** que a Meta exige.
> Pesquisa de regras: Meta + BSPs, jun/2026. Medição contra o código: 02/09/2026;
> voz e domínio remedidos em 25/09/2026.

**Submissão é pelo ManyChat.** O número da padaria é controlado por ele e continua sendo.
Meta Cloud API direta, WhatsApp Flows e segundo número estão **descartados**: a burocracia
da Meta (verificação, template aprovado, janela de 24h) é idêntica nos dois caminhos, então
o caminho direto não compra nada e custa uma migração.

---

## ⛔ ANTES DE SUBMETER — resolvido em 02/09

Três templates têm botão de URL e os três apontavam para lugar nenhum. O que se descobriu
ao medir contra o código, e o que ficou decidido:

**1. A base da loja é `https://www.nelsonboulangerie.com.br`.** Conferido no spec **vivo**
do `shopman-nelson` em 24/09/2026: `SHOPMAN_STOREFRONT_BASE_URL` e `SHOPMAN_DOMAIN` dizem
os dois `https://www.nelsonboulangerie.com.br`, e `.do/app.alpha-subdomains.yaml` no repo
acompanha. **Todo template novo nasce com `www.`.**

> ⚠️ O doc escreveu `menu.` até 24/09, e por duas vezes: o apex antes do corte de 01/09, o
> `menu.` depois dele. O site passou para `www.` em 17/09 e o parágrafo não acompanhou —
> ficou uma nota de rodapé dizendo `www.` por cima de um item dizendo `menu.`. Como o
> prefixo é **fixo dentro do template aprovado**, errá-lo não é edição de uma linha: é um
> ciclo de re-submissão à Meta, vezes os **oito** templates cujo botão usa o prefixo fixo
> (o nono, o `link_pagamento_enviado`, leva a URL da cobrança e não depende disto). Antes
> de submeter o primeiro botão, confira o spec vivo — não este parágrafo:
>
> ```
> doctl apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f | grep -A2 STOREFRONT_BASE_URL
> ```
>
> `alpha.*` continua aposentado. Nenhum template foi aprovado com `menu.` — quando este
> doc foi escrito não havia nenhum aprovado, e não há até hoje.

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
https://www.nelsonboulangerie.com.br/pedido/{{1}}
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
8. **Um corpo por evento, sem variantes.** `NotificationTemplate.event` é `unique=True` e o
   adapter busca um flow por evento (`_load_db_flow_ns`). Não existe "a versão com nome e a
   versão sem" da mesma mensagem: a frase escolhida tem de funcionar em **todos** os casos
   daquele evento.
9. **Nada auto-suprimível atravessa.** A Meta não aceita parâmetro vazio, então todo pedaço
   que o código apaga sozinho quando não há dado **não pode virar variável**: `{eta_note}`,
   `{courier_tracking_suffix}`, `{reserve_note}`, `{deadline_note}`, `{pix_suffix}`,
   `{reason_note}`, `{tracking_suffix}`, `{reorder_suffix}`. Eles continuam saindo inteiros
   por SMS e e-mail, que interpolam na hora. No template, ou a informação é fixa no texto,
   ou fica de fora.

> ### 📝 Para quem for reescrever as frases
>
> As sete primeiras regras são sobre o formato que a Meta exige. As duas últimas são as que
> pegam quem escreve copy boa e descobre tarde que ela não vira template — vale lê-las
> **antes** de redigir, não depois.
>
> Duas armadilhas a mais, que não são regra da Meta e sim do nosso caminho:
>
> - **Variável que pode chegar vazia quebra a frase em volta.** `customer_name` é o caso
>   vivo: o checkout da loja o exige, mas pedido anotado no PDV e ingestão do iFood não. Uma
>   frase com vírgula fixa (`Oi, {{1}}!`) não tem como se recompor sem o nome. Ou o dado é
>   garantido, ou a frase se vira sem ele.
> - **Link não vira texto, vira botão** (regra 5), e o botão tem numeração própria. Uma frase
>   que termina com "acesse o link abaixo" está pedindo um botão, não uma variável.

### Sample values do pacote

| Variável | Sample |
|---|---|
| Nome do cliente | `Ana` |
| Pedido, no corpo (final do ref) | `A17` |
| Ref do pedido, no botão | `NB-260902-A17` |
| Total | `R$ 38,00` |

> ⚠️ A ref **não** é `NB-1042`. O formato real é `{PREFIXO}-{AAMMDD}-{L##}`
> (`orderman/ids.py::generate_order_ref`), com o prefixo `NB` vindo de `order_ref_prefix`
> na config do canal. Sample com formato irreal atrapalha a revisão do botão.
>
> ⚠️ **No CORPO o pedido é chamado só pelo final** ("seu pedido A17"), decisão do dono de
> 25/09/2026: é o que o balcão fala e o que o card mostra em destaque, e é único no dia
> entre todos os canais (`generate_order_ref` sorteia de novo quando o final já foi dado).
> A variável do corpo liga ao campo `order_ref_short`; a do **botão** continua em
> `order_ref`, porque a URL precisa do ref completo.

---

## OTP — não existe neste pacote

O ManyChat **não tem a categoria Authentication** (só Marketing e Utility), então WhatsApp-OTP
é impossível por ali. **O código de verificação vai por SMS (Comtele)** — decidido, não é
pergunta aberta. Não há template de OTP a submeter.

---

## Utility — cliente

Formato: **Nome · Corpo · Variáveis · Botão**. Idioma `pt_BR`, categoria **Utility**.

> ### ✅ Estes corpos são a VOZ FECHADA de 25/09/2026
>
> O dono revisou **todas** as frases de uma vez e fechou. O que está abaixo é a coluna
> WhatsApp daquela revisão, transposta para o formato do template. A coluna SMS/e-mail
> vira `seed` + migração, em PR da sessão da voz.
>
> Por que os dois textos diferem de propósito: o SMS e o e-mail interpolam na hora e
> carregam link solto; o template aprovado não pode ter link no corpo (regra 5) nem
> variável que chegue vazia (regra 9). **Onde o SMS diz "Acompanhe por aqui: (link)", o
> template não diz nada — quem diz é o botão.**
>
> As regras que a voz aplicou, e que valem para ler qualquer corpo daqui:
>
> - **"Oi, {{1}}!" para abrir; "Oi, {{1}}." com ponto na notícia ruim** (cancelado, não
>   confirmado, prazo vencido, falha). Sem nome, o SMS/e-mail dizem "Oi!" sozinho — mas o
>   template **não tem esse recurso**, e é por isso que pedido sem nome sai por SMS.
> - **Voz feminina, é a concierge: "Obrigada".**
> - **Emoji só os da casa** — 💛✨, e 😌 nas notícias ruins. Saíram 🥐, 🥖 e 📦.
> - **O texto não repete o botão.** Sumiu todo "Toque no botão abaixo"; a ação fica escrita
>   só no botão ("Pagar pedido", "Tentar de novo", "Confirmar recebimento", "Pedir de novo",
>   "Ver saldo", "Garantir já", "Ver nota fiscal").
> - **`status_note` é a variável que nunca fica vazia.** Onde o texto precisaria de um dado
>   opcional (a hora prevista, o motivo), entra ela — e sem o dado ela traz uma frase-padrão
>   em vez de sumir. É o que permite à hora e ao motivo viajarem no template, coisa que a
>   regra 9 proibia enquanto eram sufixos auto-suprimíveis.

### `pedido_recebido` — evento `order_received`
- Corpo: `Oi, {{1}}! Recebemos seu pedido {{2}}. Estamos conferindo a disponibilidade e avisamos em seguida.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

### `pedido_recebido_fora_horario` — evento `order_received_outside_hours` 🆕
- Corpo: `Oi, {{1}}! Recebemos seu pedido {{2}} fora do nosso horário. Vamos conferir assim que abrirmos e avisamos por aqui.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

> 🆕 Template novo. Faltava por esquecimento: sem ele, o pedido que entra fora do horário
> não é avisado no WhatsApp fora da janela de 24h — que é justamente quando ele acontece.

### `pedido_confirmado` — evento `order_accepted`
- Corpo: `Seu pedido {{1}} está confirmado. O total é {{2}}. Vamos preparar com todo carinho. ✨`
- Vars: `{{1}}`=`A47` (`order_ref_short`) · `{{2}}`=`R$ 38,00` (`total`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

> ⚠️ **Sem cumprimento e sem `customer_name`** — a numeração andou, `{{1}}` é o código do
> pedido. Este texto passou por três versões em dois dias (24/09 sem agradecimento, 25/09
> com "Oi, Ana!" e "Obrigado por nos prestigiar", e a revisão final); esta é a que vale.

### `pedido_em_preparo` — evento `order_preparing`
- Corpo: `Estamos preparando seu pedido {{1}}. {{2}}.`
- Vars: `{{1}}`=`A47` (`order_ref_short`) · `{{2}}`=`Previsto para ficar pronto às 18h20. Mas avisamos assim que estiver` (`status_note`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

> ⚠️ **O ponto final é FIXO, fora da variável** — o `status_note` entra sem ponto. É o que
> impede o corpo de terminar em variável (regra 2). O ✨ que fazia esse papel saiu por
> decisão do dono em 25/09.
>
> ⚠️ **Submeta este depois de dois ou três já aprovados.** Terminar em `{{2}}.` é o corpo
> mais justo do pacote na regra 2: a Meta recusa corpo que **termine em variável**, e aqui
> só um ponto literal separa. Deve passar, mas se algum reprovar por isso vai ser este — e
> é melhor descobrir com o padrão já provado pelos outros.
>
> ℹ️ Sem hora calculável, o `status_note` diz "Avisamos assim que estiver pronto". Nunca
> chega vazio, que é o ponto dele.

### `pedido_pronto_retirada` — evento `order_ready_pickup`
- Corpo: `Seu pedido {{1}} está pronto e esperando por você no balcão. ✨`
- Vars: `{{1}}`=`A47` (`order_ref_short`)
- **Dois** botões URL: `Como chegar` (link FIXO do Google Maps da loja, sem variável) · `Ver pedido` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ A Meta aceita **até dois** botões de URL por template. O `Como chegar` é estático — não
> tem variável nenhuma, é a URL do Maps colada inteira. É o único template do pacote com
> dois botões.

### `pedido_pronto_entrega` — evento `order_ready_delivery`
- Corpo: `Seu pedido {{1}} está pronto e aguardando o entregador. Avisamos assim que sair.`
- Vars: `{{1}}`=`A47` (`order_ref_short`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

### `pedido_saiu_entrega` — evento `order_dispatched`
- Corpo: `Seu pedido {{1}} saiu para entrega. Quando receber, é só confirmar.`
- Vars: `{{1}}`=`A47` (`order_ref_short`)
- Botão URL: `Confirmar recebimento` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ O rastreio do entregador (`courier_tracking_suffix`) **fica fora**: nem toda entrega tem
> corrida com rastreio, e sufixo auto-suprimível não vira variável (regra 9). Ele continua
> saindo por SMS e e-mail.

### `pedido_entregue` — evento `order_delivered`
- Corpo: `Seu pedido {{1}} foi entregue. Esperamos que tenha gostado, {{2}}! Obrigada por nos prestigiar! 💛✨`
- Vars: `{{1}}`=`A47` (`order_ref_short`) · `{{2}}`=`Ana` (`customer_name`)
- Sem botão.

> ⚠️ **O nome está no MEIO e é `{{2}}`, não `{{1}}`.** É o único template do pacote com essa
> ordem. Ligar na ordem de costume produz "Seu pedido Ana foi entregue".

### `nota_fiscal_disponivel` — evento `fiscal_note_ready` 🆕
- Corpo: `A nota fiscal do pedido {{1}} está disponível.`
- Vars: `{{1}}`=`A47` (`order_ref_short`)
- Botão URL: `Ver nota fiscal` → `/pedido/{{1}}` (`order_ref`)

### `pedido_cancelado` — evento `order_cancelled`
- Corpo: `Oi, {{1}}. Seu pedido {{2}} foi cancelado. {{3}} Qualquer dúvida, estamos à disposição. 😌`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`) · `{{3}}`=`Motivo: item indisponível.` (`status_note`)
- Botão URL: `Ver detalhes` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ Aqui o `status_note` fica no **meio** do texto, então ele vem **com** ponto final — ao
> contrário do `pedido_em_preparo`, onde o ponto é fixo. Sem motivo informado, diz "Os
> detalhes estão no pedido.".
>
> ℹ️ "Oi, {{1}}." com **ponto**, não com exclamação: é notícia ruim.

### `pedido_nao_confirmado` — evento `order_rejected`
- Corpo: `Oi, {{1}}. Não conseguimos confirmar seu pedido {{2}} desta vez. {{3}} Se houve cobrança, devolvemos o valor. Qualquer dúvida, estamos à disposição. 😌`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`) · `{{3}}`=`Motivo: item indisponível.` (`status_note`)
- Botão URL: `Ver detalhes` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ Saiu o "Nada foi cobrado": quem pagou no checkout e teve o pedido recusado **foi**
> cobrado e recebe estorno. "Se houve cobrança, devolvemos o valor" serve aos dois casos.

### `pedido_agendado_lembrete` — evento `preorder_reminder`
- Corpo: `Oi, {{1}}! Lembrando que seu pedido {{2}} está agendado para amanhã. Vamos preparar com todo carinho. ✨`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

### `pagamento_solicitado` — evento `payment_requested`
- Corpo: `Oi, {{1}}! Seu pedido {{2}} está reservado. Falta só o pagamento.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Pagar pedido` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ O código Pix copia-e-cola **não** viaja no template (é longo e opcional). Fica no
> SMS/e-mail; aqui a pessoa chega pela tela do pedido, onde o Pix e o cartão estão inline.

### `link_pagamento_enviado` — evento `payment_link_sent`
Pedido remoto anotado no PDV (encomenda por telefone/WhatsApp): a venda fechou e o cliente paga pelo link.
- Corpo: `Oi, {{1}}! Anotamos seu pedido {{2}} no valor de {{3}}. Pague até {{4}} para garantir. Depois disso liberamos a reserva.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`) · `{{3}}`=`R$ 38,00` (`total`) · `{{4}}`=`hoje às 18h` (`payment_deadline`)
- Botão URL (dinâmico): `Pagar pedido` → a URL da cobrança inteira (`checkout_url`; é a sessão hospedada do gateway, não uma página da loja)

> ✅ **`{{4}}` nunca chega vazio — medido em 25/09/2026, não suposto.** Era a única
> dependência de dado opcional do pacote, e o caminho foi percorrido inteiro: o
> `payment_link_sent` só sai de `pos._send_payment_link`, depois do `initiate` e com a
> `checkout_url` já gravada; para `method == "link"` os dois adapters que emitem link
> (`payment_stripe` e `payment_mock` — a Efí só faz Pix) calculam
> `_payment_link.link_expires_at(...)`, que **sempre** devolve um instante
> (`max(agora + TTL_MIN, min(janela, corte))`, nunca `None`); o `services/payment.initiate`
> copia `intent.expires_at` para `order.data["payment"]["expires_at"]`, que é de onde o
> `payment_deadline` é lido; e a janela do canal (`link_timeout_minutes`) é validada `> 0`
> no `ChannelConfig`. O único jeito de faltar seria um terceiro adapter de link que não
> usasse `link_expires_at`, e não existe nenhum.

### `pagamento_confirmado` — evento `payment_confirmed`
- Corpo: `Obrigada, {{1}}! Recebemos o pagamento do seu pedido {{2}}. Vamos atualizando você por aqui.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Acompanhar pedido` → `/pedido/{{1}}` (`order_ref`)

### `pagamento_lembrete` — evento `payment_reminder`
- Corpo: `Oi, {{1}}! Seu pedido {{2}} ainda aguarda o pagamento via Pix.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Pagar pedido` → `/pedido/{{1}}` (`order_ref`)

### `pagamento_expirado` — evento `payment_expired`
- Corpo: `Oi, {{1}}. O prazo para pagar o pedido {{2}} acabou e liberamos a reserva. Nada foi cobrado.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Pedir de novo` → `https://www.nelsonboulangerie.com.br/conta/pedidos` (link **fixo**, sem variável)

### `pagamento_falhou` — evento `payment_failed`
- Corpo: `Oi, {{1}}. Não conseguimos gerar o pagamento do seu pedido {{2}}.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Tentar de novo` → `/pedido/{{1}}` (`order_ref`)

> ℹ️ O botão abre o pedido, onde ficam o Pix e o cartão. Não há tela de pagamento separada
> (PAYMENT-TRACKING-MERGE).

### `reembolso_processado` — evento `payment_refunded` 🆕
- Corpo: `Oi, {{1}}! O reembolso do pedido {{2}}, no valor de {{3}}, foi processado. Qualquer dúvida, estamos à disposição.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`) · `{{3}}`=`R$ 38,00` (`total`)
- Sem botão.

> ⚠️ **Nada emite este evento hoje.** O sinal `payment_refunded` existe no `payman` e está
> ligado só aos emissores de SSE (`handlers/_sse_emitters.py`) — não há despacho de
> notificação ao cliente. O template pode ser aprovado e mapeado, mas **não vai disparar**
> até alguém ligar o evento à notificação. Ver "Templates aprovados que ainda não disparam".

### `fila_vaga_disponivel` — evento `waitlist_available`
- Corpo: `Oba! 💛✨ Acabou de sair do forno, {{1}}! Confirme o pedido {{2}} para garantir.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Confirmar pedido` → `/pedido/{{1}}` (`order_ref`)

> ⚠️ Não ligar `waitlist.enabled` antes do #392 estar no ar — ver a política de fila.

### `fila_vaga_liberada` — evento `waitlist_released`
- Corpo: `Oi, {{1}}. O prazo para confirmar o pedido {{2}} acabou e liberamos a reserva. Nada foi cobrado.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Pedir de novo` → `https://www.nelsonboulangerie.com.br/conta/pedidos` (link **fixo**, sem variável)

> ℹ️ Mesma forma do `pagamento_expirado`, de propósito: os dois dizem a mesma coisa ao
> cliente (o prazo passou, a reserva voltou, ninguém cobrou) e devem falar igual.

### `pontos_fidelidade` — evento `loyalty_earned` 🆕
- Corpo: `Parabéns, {{1}}! 💛✨ Você ganhou pontos de fidelidade com o pedido {{2}}.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`A47` (`order_ref_short`)
- Botão URL: `Ver saldo` → `/conta` (link **fixo**, sem variável)

> ⚠️ **Nada emite este evento hoje.** `loyalty_earned` só existe no `seed` e num teste; o
> `handlers/loyalty.py` não manda notificação nenhuma. Ver "Templates aprovados que ainda
> não disparam".

### `produto_chegou` — evento `stock_arrived`
- Corpo: `Oi, {{1}}! Você pediu pra avisar quando {{2}} estivesse disponível e agora está! 💛✨`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`Croissant` (`product_name`)
- Botão URL: `Garantir já` → `https://www.nelsonboulangerie.com.br/produto/{{1}}` (`product_sku`)

> ⚠️ **O prazo da reserva não viaja neste template.** O `stock_arrived` sai por dois
> caminhos — com reserva materializada e prazo (`handlers/_stock_receivers.py`) e pelo "Me
> avise" puro (`storefront/services/stock_alerts.py`), onde os dois vêm vazios. Um corpo que
> prometesse prazo ficaria falso no segundo caminho, e `whatsapp_flow_ns` é um por evento
> (regra 8). O prazo continua saindo por SMS e e-mail.
>
> ⚠️ **Categoria é o risco real deste.** Aviso de disponibilidade costuma ser lido como
> Marketing pela Meta. Submeta como Utility; se reprovar, o corpo não muda — só a categoria.

---

## Botões: para onde cada um aponta

Destino é **fixo dentro do template aprovado**, então errar custa reaprovação. A restrição
que fecha as opções vem da decisão de segurança (ver "ANTES DE SUBMETER"): **URL não vira
campo personalizado**. Sobram dois formatos:

1. **prefixo fixo + variável segura** — a variável é um identificador curto, nunca uma URL;
2. **URL estática**, sem variável nenhuma.

| Botão | Onde | Destino |
|---|---|---|
| `Acompanhar pedido` · `Ver pedido` · `Ver detalhes` · `Pagar pedido` · `Tentar de novo` · `Confirmar pedido` · `Confirmar recebimento` · `Ver nota fiscal` | a maioria | `…/pedido/{{n}}` + `order_ref` |
| `Pagar pedido` (só no `link_pagamento_enviado`) | pedido do PDV | a URL da cobrança inteira (`checkout_url`) — sessão do gateway, não página da loja |
| `Garantir já` | `produto_chegou`, `saiu_do_forno` | `…/produto/{{n}}` + **`product_sku`** |
| `Pedir de novo` | `pagamento_expirado`, `fila_vaga_liberada` | `…/conta/pedidos` — **estático** |
| `Ver saldo` | `pontos_fidelidade` | `…/conta` — **estático** |
| `Como chegar` | `pedido_pronto_retirada` | Google Maps da loja — **estático** |
| `Ver novidade` | `anuncio_novidade` | ⚠️ **ainda não decidido** — ver abaixo |

⚠️ **`product_sku`, não `sku`.** As duas chaves existem no contexto e são o mesmo valor, mas
`sku` está em `_FIELD_DENYLIST` e nunca chega ao ManyChat — `product_sku` existe justamente
para isto ("o sufixo que o template gruda no fim do link do botão", diz o comentário em
`storefront/services/stock_alerts.py`), e está em `_ALERT_FLOW_FIELDS` para os dois eventos.
Ligar o botão ao `sku` produz um botão em branco, em silêncio.

⚠️ **`Pedir de novo` é estático de propósito.** O `reorder_url` do contexto é link pessoal e
não pode virar campo personalizado. `…/conta/pedidos` (`storefront_links.path_order_history`)
resolve sem token: sem sessão, a loja pede o telefone e devolve a pessoa para lá.

### O que falta decidir: `Ver novidade`

O destino natural é o `action_url` da campanha, que é link pessoal e por isso não viaja. A
sugestão é a **home, estática** — mas o `anuncio_novidade` ficou fora da revisão de voz de
25/09, e o destino de um botão de campanha é decisão de quem cuida do Marketing, não desta
frente. Enquanto não fechar, **este é o único template do pacote que não dá para submeter.**

---

## Templates aprovados que ainda não disparam

Dois dos templates novos são de eventos que **nenhum código emite hoje**:

| Template | Evento | Estado |
|---|---|---|
| `reembolso_processado` | `payment_refunded` | o sinal existe no `payman`, mas só alimenta os emissores de SSE — não há notificação ao cliente |
| `pontos_fidelidade` | `loyalty_earned` | só existe no `seed` e num teste; `handlers/loyalty.py` não notifica |

Submeter os dois é legítimo — o template fica pronto para quando o código ligar, e a
aprovação leva 24-48h que não se quer pagar depois. Mas é bom saber que **mapear o flow deles
não faz nada** até o evento passar a ser emitido, e que um teste de ponta a ponta neles vai
dar silêncio, não falha.

---

## Utility — fornecedor

Audiência diferente: quem recebe é o contato comercial do fornecedor, não um cliente
(`backstage/services/purchase.py::_supplier_dispatch_route`, modelo `SupplierContact`).

### `pedido_compra` — evento `purchase_request`
- Corpo: `Olá! Chegou um pedido de compra da {{1}}, número {{2}}: {{3}}, quantidade {{4}}. Por favor, confirme disponibilidade, prazo e valor final por aqui.`
- Vars: `{{1}}`=`Nelson Boulangerie` (`shop_name`) · `{{2}}`=`PC-260902-9C4A1F` (`purchase_ref`) · `{{3}}`=`Farinha de trigo tipo 1` (`material_name`) · `{{4}}`=`5 sc` (`purchase_qty_display`)
- Sem botão (o fornecedor responde na conversa; não há tela dele).

> ⚠️ **A ref aqui fica INTEIRA, e não é esquecimento.** A regra do código curto é do pedido
> do cliente; esta é a ref da **compra** (`purchase_ref`), e quem lê é o contato comercial do
> fornecedor, que vai procurar esse número no sistema dele. Encurtar deixaria o fornecedor
> com `9C4A1F` e sem botão — este template não tem tela para onde mandar.
>
> ⚠️ **A revisão de voz de 25/09 não passou por aqui.** Ela cobriu as mensagens ao cliente; o
> fornecedor é outra audiência e outro tom. Se a casa quiser revisar este texto também, é
> rodada própria.

---

## Marketing

Categoria e custo diferentes. **Não misture com Utility** — nem "para passar".

### `saiu_do_forno` — evento `production_ready`
- Corpo: `Olha só o que acabou de sair do forno: {{1}}! {{2}}.`
- Vars: `{{1}}`=`Croissant` (`product_name`) · `{{2}}`=`No momento temos 12 un. disponíveis` (`availability_note`)
- Botão URL: `Garantir já` → `https://www.nelsonboulangerie.com.br/produto/{{1}}` (`product_sku`)

> ℹ️ A quantidade **sempre existe** quando a fornada sai, então é variável fixa do template,
> sem frase condicional. Com zero disponível o aviso não sai.
>
> ⚠️ **O ponto final é FIXO, fora da variável**, como no `pedido_em_preparo`: o
> `availability_note` entra sem ponto. É o que impede o corpo de terminar em variável.
>
> ℹ️ **Uma redação só, em duas formas.** `availability_note` é o texto sem ponto (para este
> template) e `availability_phrase` é o mesmo texto **com** ponto (para campanha e e-mail,
> onde a frase fecha sozinha). Não são dois textos concorrentes — o segundo é literalmente
> `f"{availability_note(qty)}."` em `shop/services/availability_copy.py`. Use
> `availability_note` aqui; ligar no `availability_phrase` produz dois pontos finais.

### `anuncio_novidade` — evento `announcement_published`
- Corpo: `Oi, {{1}}! Tem novidade na Nelson Boulangerie hoje: {{2}}. Passe na loja ou peça pelo nosso site.`
- Vars: `{{1}}`=`Ana` (`customer_name`) · `{{2}}`=`o pão de campanha voltou às quartas` (`body`)
- Botão URL: `Ver novidade` → **destino a decidir** — sugestão: a home, estática (ver "Botões: para onde cada um aponta")

> ⚠️ **Submeta este por último.** No código, `announcement_published` é só um envelope: o
> corpo inteiro vem pronto do `AnnouncementTemplate` (`"{body}\n\n{cta} {action_url}"`). Um
> template aprovado **não** aceita corpo livre — a Meta precisa ler o que a mensagem diz, e
> um `{{2}}` que é a mensagem toda reprova.
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
`notification_email.SUBJECT_TEMPLATES` em 02/09/2026, e de novo em 25/09/2026 contra os
eventos realmente emitidos. O mapa antigo trazia **`order_confirmed`, que o código nunca
emitiu** — o evento é `order_accepted`.

**São 25 templates**: 22 Utility de cliente, 1 Utility de fornecedor e 2 Marketing. Quatro
nasceram na revisão de 25/09 (🆕), e dois deles são de eventos que ainda não disparam.

| Evento interno | Template Meta | Categoria |
|---|---|---|
| `order_received` | `pedido_recebido` | Utility |
| `order_received_outside_hours` | `pedido_recebido_fora_horario` | Utility 🆕 |
| `order_accepted` | `pedido_confirmado` | Utility |
| `order_rejected` | `pedido_nao_confirmado` | Utility |
| `order_preparing` | `pedido_em_preparo` | Utility |
| `order_ready_pickup` | `pedido_pronto_retirada` | Utility |
| `order_ready_delivery` | `pedido_pronto_entrega` | Utility |
| `order_dispatched` | `pedido_saiu_entrega` | Utility |
| `order_delivered` | `pedido_entregue` | Utility |
| `order_cancelled` | `pedido_cancelado` | Utility |
| `fiscal_note_ready` | `nota_fiscal_disponivel` | Utility |
| `preorder_reminder` | `pedido_agendado_lembrete` | Utility |
| `payment_requested` | `pagamento_solicitado` | Utility |
| `payment_link_sent` | `link_pagamento_enviado` | Utility |
| `payment_confirmed` | `pagamento_confirmado` | Utility |
| `payment_reminder` | `pagamento_lembrete` | Utility |
| `payment_expired` | `pagamento_expirado` | Utility |
| `payment_failed` | `pagamento_falhou` | Utility |
| `payment_refunded` | `reembolso_processado` | Utility 🆕 (não emitido ainda) |
| `waitlist_available` | `fila_vaga_disponivel` | Utility |
| `waitlist_released` | `fila_vaga_liberada` | Utility |
| `loyalty_earned` | `pontos_fidelidade` | Utility 🆕 (não emitido ainda) |
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
| Nome do cliente | `customer_name` | os de cliente, **menos** `pedido_confirmado`, `pedido_em_preparo`, `pedido_pronto_retirada`, `pedido_pronto_entrega` e `pedido_saiu_entrega` (a voz de 24-25/09 tirou o cumprimento desses cinco) |
| Pedido, no corpo | `order_ref_short` | todos os de pedido (o final do ref: `A17`) |
| Ref do pedido | `order_ref` | **todo botão de URL** — nunca no corpo |
| Total | `total` → **`order_total_display`** (rename pendente) | `pedido_confirmado`, `link_pagamento_enviado` |
| Prazo do pagamento | `payment_deadline` | `link_pagamento_enviado` |
| URL da cobrança | `checkout_url` | `link_pagamento_enviado` (botão dinâmico) |
| Frase que nunca fica vazia | `status_note` | `pedido_em_preparo`, `pedido_cancelado`, `pedido_nao_confirmado` |
| Nome do produto | `product_name` | `produto_chegou`, `saiu_do_forno` |
| Frase de disponibilidade | `availability_note` | `saiu_do_forno` |
| Nome da loja | `shop_name` | `pedido_compra` |
| Ref da compra | `purchase_ref` | `pedido_compra` |
| Material | `material_name` | `pedido_compra` |
| Quantidade | `purchase_qty_display` | `pedido_compra` |
| Corpo da campanha | `body` | `anuncio_novidade` |

⚠️ **Nunca** mapeie um botão de URL para `tracking_url` ou `payment_url`. O botão leva
`order_ref`; o prefixo já está fixo no template. Ver "ANTES DE SUBMETER".

⚠️ **Crie todos como tipo Texto**, inclusive `total`. O adapter grava por
`setCustomFieldByName` com o valor já formatado (`R$ 38,00`, `5 sc`) — campo criado como
Número recusa a gravação, e a recusa só aparece no log.

⚠️ **Valor vazio não é gravado.** `_shareable_context` descarta chave vazia, então o campo
guarda o que sobrou do envio ANTERIOR àquele assinante em vez de limpar. Na prática só
morde onde o dado é opcional: `customer_name` (o checkout da loja o exige, mas pedido
anotado no PDV e ingestão do iFood não) e `payment_deadline`. Onde o dado é obrigatório
(`order_ref`, `order_ref_short`, `total`) não há caso.

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
