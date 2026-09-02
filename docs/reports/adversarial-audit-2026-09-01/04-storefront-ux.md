# Auditoria adversarial — Storefront (cliente) · Nelson Boulangerie

Escopo: `surfaces/storefront-nuxt/` (20 páginas, 28 componentes de app, 17 composables,
11 módulos de presentation) + copy de apoio em `shopman/storefront/presentation/` e
`shopman/shop/omotenashi/`. Leitura estática — o dev server e a suíte NÃO foram executados
(regra do encargo). Os achados marcados **[verificar na tela]** dependem de confirmação
visual, mas o raciocínio está registrado por completo.

Raiz de todos os caminhos: `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agente-c-audit-fixes-0dcab9/`

Contagem: **5 P0 · 30 P1 · 47 P2** (o P1 "falha de rede vira estado vazio" conta uma vez,
mas atinge 5 páginas de `/conta`).

---

## index (home)

### P0 — A home inteira é vendida com foto de banco de imagens de OUTRA padaria
`surfaces/storefront-nuxt/app/components/HomeHeroThing.vue:35-40`
```ts
const HERO_IMAGE_URLS = {
  greeting: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?...',
  order:    'https://images.unsplash.com/photo-1517433670267-08bbd4be890f?...',
  reorder:  'https://images.unsplash.com/photo-1568254183919-78a4f43a2877?...',
  handmade: 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?...'
} as const
```
Mais três em `app/pages/index.vue:65` (fundo do CTA de WhatsApp), `:314` (card "Peça
online") e `:341` (card "Visite a loja"). São **7 fotos Unsplash** — as quatro do
carrossel do hero são a primeira coisa que qualquer visitante vê, em tela cheia
(`h-[calc(100svh-15.25rem…)]`, HomeHeroThing.vue:256).

Enquanto isso `surfaces/storefront-nuxt/public/img/products/` tem **51 .webp reais**
da casa (a memória do projeto registra a virada de 01/09: "fotos de produto moram na LOJA").

O que o cliente experimenta: a página que diz "Feito à mão, todo dia" está ilustrada
com a padaria de outra pessoa. Some a isso:
- é o LCP da home e vem de host externo — 3G lento, bloqueio corporativo ou queda do
  Unsplash deixam o hero como `bg-muted` cinza;
- `HomeHeroThing.vue:264` põe `:alt="slide.imageAlt"` = `shop.brand_name`, ou seja
  rotula a foto de terceiro com o nome da Nelson (e `aria-hidden="true"` na linha 268
  torna o alt inerte de qualquer forma — a imagem não tem descrição alguma);
- licença/uso comercial de foto de terceiro numa loja que vende.

Correção: mover as 4 fotos do hero e as 3 de seção para `public/img/` (ou para o
`Shop`/`OmotenashiCopy` server-driven, que é o padrão da casa para marca), com fotos
reais da Nelson. Enquanto não houver foto de ambiente, um hero tipográfico sobre
`bg-ink` é infinitamente menos constrangedor que a padaria de outra pessoa.

### P0 — "Loja fechada agora" é calculado pelo backend e jogado fora pela tela
`surfaces/storefront-nuxt/app/pages/index.vue:43`
```ts
const contextualNotices = computed(() => home.value?.notices.filter(notice => notice.priority !== 'global') || [])
```
O backend em `shopman/storefront/presentation/home.py:357-364` emite exatamente **um**
aviso com `priority="global"`: o `shop_status`, com título `"Loja fechada agora"`
(quando `not is_open`, linha 328) ou a copy de urgência `URGENCY_BANNER_MESSAGE`
("Estamos perto do fechamento", linhas 329-332), com as ações `Ver cardápio` e
`Falar no WhatsApp` já montadas.

O filtro acima é o único consumidor de `notices` na superfície inteira. O
`useShopSession.ts:83,137,152` guarda `homeNotices` e **nenhum componente lê**
(`grep -rn homeNotices app/` → só o composable e dois testes).

O que o cliente experimenta: chega às 22h, a loja está fechada, e a home mostra o
hero normal com "Ver cardápio". O único sinal de fechado é o `statusLabel` truncado
na barra de status do header (`ShopHeader.vue:114`) e um `UiBadge` enterrado dentro
da seção "Como funciona" (`index.vue:352`). Monta a sacola, chega no checkout e só
ali descobre. É o oposto exato do teste omotenashi.

Correção: renderizar o notice global no topo da home (acima do hero) — ou, melhor,
no shell (`app.vue`), já que ele vale em toda página. Alternativa mínima: trocar o
filtro por uma ordenação que ponha `global` primeiro.

### P1 — O banner de pedido ativo entra depois da pintura e empurra o hero
`app/pages/index.vue:69-81` busca `/api/v1/account/orders/active/` em `onMounted`,
sem placeholder. Quando responde, `index.vue:170` insere um bloco de ~64px **acima**
do hero. Layout shift medível na home, exatamente para o cliente recorrente (o que
mais importa). Correção: reservar altura, ou buscar no SSR junto do `home`.

### P1 — `?filter=ativos`: valor pt-BR em rota de API
`app/pages/index.vue:74` e `app/pages/conta/pedidos.vue:28` (`filter: orderFilter.value`,
valores `'todos' | 'ativos' | 'anteriores'`). A convenção da casa é "URL é em inglês,
ponto" — e aqui é a query de uma API pública. Não muda o texto de tela. P1 porque é
contrato BE+FE e portanto só barato de mudar agora.

### P2 — "Ver histórico" num card que pergunta "Quer repetir seu último pedido?"
`app/pages/index.vue:270` (`{{ reorderAction?.label || 'Ver histórico' }}`) com o
título de `:255`. E `handleReorder(null)` (`:85`) leva a `/conta`, não a
`/conta/pedidos`. O rótulo de fallback não diz o que acontece.

### P2 — `index.vue:262` "Seu pedido anterior volta à sacola para revisão."
Voz de sistema. Ver tabela de copy.

### P2 — Sem estado para "carregou, mas não há destaques"
`index.vue:279` esconde a seção inteira quando `featuredPreview` está vazio — some
junto o CTA "Ver cardápio completo". A home fica com hero + nada.

---

## menu

### P1 — A meta description do cardápio é linguagem de admin
`app/pages/menu.vue:297`
```ts
description: () => catalog.value?.has_items ? `${uniqueItems.value.length} itens publicados.` : 'Cardápio publicado.'
```
"itens publicados" / "Cardápio publicado" é o vocabulário do Admin. É o texto que o
Google mostra embaixo do link da loja. Proposta na tabela de copy.

### P1 — Happy hour sem prazo
`app/pages/menu.vue:420-423`: `"Happy hour ativo"` + `"X% de desconto aplicado no
cardápio."` — não diz **até quando**. O anfitrião atencioso diria a hora. Sem isso, o
desconto some sem aviso entre o momento de escolher e o de finalizar (e aí o guardião
de `total_changed` no checkout, `finalizar.vue:971`, é quem dá a notícia — no pior
momento possível).

### P1 — /menu não sabe se a loja está aberta
A página não consome `shop_status` de forma alguma. Quem chega direto por link do
WhatsApp ou pela busca do Google (o caso comum) não tem como saber se a loja está
aberta, quando abre, nem quando conseguiria retirar. O `pillbar` sticky ocupa o topo
com filtros; o status não aparece em lugar nenhum da tela.

### P2 — Empty state de filtro sem a ação que resolve
`menu.vue:488-499`: quando o filtro zera os resultados, o empty state oferece só a
`cta_href` do servidor. O botão "Limpar filtro" existe, mas lá em cima na pillbar
(`:349-359`), fora da vista de quem rolou até o vazio.

### P2 — Erro do cardápio sem saída de emergência
`menu.vue:410-414` oferece só "Tentar de novo". A home, no mesmo caso
(`index.vue:161`), oferece WhatsApp. Inconsistente, e o WhatsApp é a saída que
realmente fecha pedido.

### P2 — `sticky top-16` assume header de 4rem
`menu.vue:324`. O header tem 6.25rem expandido e 4rem colapsado
(`ShopHeader.vue:72`). Durante a transição de colapso a pillbar sobrepõe a barra de
status. Mesmo acoplamento em `app.vue:76` (`min-h-[calc(100svh-4rem)]`) e
`busca.vue:120` (`md:top-16`).

---

## produto/[sku]

### P1 — "Pausado" é jargão de operador na cara do cliente
`app/pages/produto/[sku].vue:42`
```ts
const unavailableCtaLabel = computed(() => product.value?.is_paused ? 'Pausado' : 'Indisponível')
```
e `:45` `'A loja pausou este item temporariamente.'`

"Pausar item" é o verbo do Admin. Para o cliente, "Pausado" num botão desabilitado não
significa nada e não diz **quando volta**. Também vira o `add-label` do
`CartQuantityAction` (`:283`, `:376`) — um botão cujo rótulo não é um verbo.
Mesma palavra em `app/utils/operationalCopy.ts:32` e em `SubstituteSheet.vue:39`
(este último com fallback melhor: "Temporariamente indisponível").

### P1 — Indisponível sem "quando volta" e sem porta de saída
`produto/[sku].vue:43-47`: quando `!can_add_to_cart` e o item **não** é `is_notifiable`,
a tela mostra só a razão em texto cinza (`:285`, `:367`) e um botão morto. Nenhuma
alternativa (o `crossSell` existe, mas fica embaixo, sem relação declarada com a falta).
Contraste com o `SubstituteSheet`, que faz exatamente certo no fluxo do 409.

### P1 — Erro sem WhatsApp e com vocabulário próprio
`produto/[sku].vue:151` `'Tivemos um percalço ao carregar. Tente de novo em instantes.'`
"Percalço" é charmoso mas é a terceira formulação diferente do mesmo erro em três
páginas (home: "Atualize a vitrine…", menu: "Foi uma falha nossa.", PDP: "Tivemos um
percalço"). E os botões alternam "Tentar novamente" (`index.vue:162`) / "Tentar de
novo" (`menu.vue:414`, `produto:152`, `sacola:137`, `busca:164`).

### P2 — Breadcrumb aparece só depois do fetch
`produto/[sku].vue:128` (`v-if="product"`) enquanto o skeleton já ocupa a tela em
`:140`. A barra de breadcrumb entra depois e empurra tudo — layout shift na PDP.

### P2 — `line-clamp-2` no `<h1>` do produto
`produto/[sku].vue:256`. Nome longo é cortado sem `title` nem expansão. Idem
`:259` na `short_description`.

### P2 — "% VD" sem explicação
`produto/[sku].vue:323`. É a sigla da ANVISA, mas o rodapé padrão ("% Valores Diários
com base em uma dieta de 2.000 kcal") não aparece em lugar nenhum.

### P2 — Alvo de toque de 8px nos pontinhos do carrossel
`produto/[sku].vue:216`: `class="h-2 w-2 …"`. Tem `aria-label` e `aria-current` (bom),
mas 8×8px está muito abaixo dos 44px recomendados. O swipe funciona; os pontos não.

---

## sacola

### P1 — Preço original e quantidade colidem na mesma linha
`app/pages/sacola.vue:233-236`
```html
<p class="mt-0.5 shop-meta">
  <span v-if="line.original_price_display" class="line-through">{{ line.original_price_display }}</span>
  {{ line.qty }} × {{ line.price_display }} cada
</p>
```
Com desconto ativo a linha renderiza `R$ 18,00 2 × R$ 15,00 cada` — sem separador,
sem rótulo. O cliente lê três números grudados. E "2 × R$ 15,00 **cada**" é
redundante: ou é "2 × R$ 15,00", ou é "R$ 15,00 cada".

### P1 — Contagem regressiva por segundo em `aria-live="polite"`
`sacola.vue:160`
```html
<p v-if="bannerCountdown" class="tabular-nums" aria-live="polite">Tempo restante: {{ bannerCountdown.display }}</p>
```
`nowMs` tica a cada 1s (`:42`). O leitor de tela anuncia "Tempo restante: 4:59",
"4:58", "4:57"… indefinidamente, cobrindo qualquer outra coisa na tela. A página de
acompanhamento resolve isso corretamente com `role="timer"` **sem** `aria-live` e
até documenta o porquê (`pedido/[ref]/index.vue:574-576`) — a sacola não recebeu a
mesma correção. Mesmo defeito em `pedido/[ref]/index.vue:538` (`Confirme em {{
waitlistDeadlineLeft }}` com `aria-live="polite"`).

### P1 — Empty state da sacola sem fallback de copy
`sacola.vue:178-179`
```html
<UiEmptyTitle>{{ cart.empty_title }}</UiEmptyTitle>
<UiEmptyDescription>{{ cart.empty_message }}</UiEmptyDescription>
```
Únicos dois pontos da superfície que consomem copy do servidor **sem** `||` de
fallback (compare `menu.vue:483`, `favoritos.vue:54`, `enderecos.vue:31`). O
`emptyCart()` em `useCartState.ts` também não semeia esses campos, então a sacola
vazia antes do primeiro fetch (ou com projection degradada) é um card com ícone e
dois vazios.

### P1 — Endereço fora da área: aviso sem ação
`sacola.vue:336-339`
```html
<UiAlertTitle>Endereço fora da área de entrega</UiAlertTitle>
<UiAlertDescription>Escolha a retirada na loja ou um endereço dentro da nossa área.</UiAlertDescription>
```
Nenhum botão. Nem "mudar para retirada" (que o checkout tem, `finalizar.vue:1073`),
nem "ver a área de entrega", nem "trocar endereço". Para a persona "meu único
endereço está fora da zona" isto é o beco sem saída literal, e ele está na sacola —
antes do checkout, onde a saída existe.

### P2 — "Usar 2 disponíveis" / plural por concatenação
`sacola.vue:285`: `Usar {{ line.available_qty }} disponíve{{ line.available_qty > 1 ? 'is' : 'l' }}`.
Funciona, mas o rótulo não diz o que acontece com o resto. Mesmo padrão em
`QuantityControl.vue:58`.

### P2 — O motivo do "+" desabilitado só existe em `title`
`QuantityControl.vue:58`: `:title="'Só temos N disponíveis'"`. `title` não existe em
toque. Na sacola isso é coberto pela linha de teto (`sacola.vue:296`), mas no
cardápio e na PDP o "+" simplesmente para de responder, sem explicação.

### P2 — "Sua sacola não quis carregar agora" promete o que não sabe
`sacola.vue:133,136`: "Seus itens estão guardados" é afirmado mesmo quando a falha
pode ser a própria sessão. Ver tabela de copy.

---

## finalizar (checkout)

### P0 — A barra de resumo mobile do checkout fica embaixo da bottom-nav **[verificar na tela]**
`app/pages/finalizar.vue:1851`
```html
<div v-if="checkout" class="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 p-3 shadow-lg backdrop-blur lg:hidden">
```
`app/components/AppBottomNav.vue:29`
```html
<nav class="shop-bottomnav-bar fixed inset-x-0 bottom-0 z-40 border-t bg-bottomnav pb-[env(safe-area-inset-bottom)] md:hidden">
```
Mesma borda (`bottom-0`), mesmo `z-40`, alturas equivalentes (~64px cada). A
`AppBottomNav` é renderizada incondicionalmente em `app.vue:80`, **depois** do
`<NuxtPage/>` (`app.vue:78`) — com z-index empatado, quem vem depois no DOM pinta
por cima. Abaixo de 768px as duas ocupam exatamente a mesma faixa.

Consequência: no telefone, durante o checkout, o cliente **não vê o total correndo**
e **não alcança o botão "Resumo"** (`finalizar.vue:1859`) que abre o recibo. O
`aside` com o card "Seu pedido" é `hidden … lg:block` (`:1801`), então no mobile não
há nenhuma outra superfície com o total antes do sheet de revisão.

Não é acidente de fórmula: o guardrail `tests/surfaceGuardrails.test.ts:406`
(`expect(checkout).not.toContain('sticky bottom-20')`) proíbe explicitamente no
checkout o padrão que a sacola (`sacola.vue:376`) e a PDP (`produto/[sku].vue:358`)
usam justamente para escapar da bottom-nav. O `pb-24` do `<main>` (`:1034`) reserva
96px — sobra 32px depois dos 64px da nav, insuficiente para a barra.

Correções possíveis: (a) esconder a `AppBottomNav` em `/finalizar` (o checkout já
esconde o footer por essa mesma lógica, `app.vue:50`) — é o caminho coerente com "o
fluxo focado"; (b) subir a barra para `bottom-16` e aumentar o `pb`. A opção (a) é
melhor: uma nav para sair da tela de pagamento não é o que se quer ali.

### P1 — O título da aba do checkout está em inglês
`finalizar.vue:1029`
```ts
useSeoMeta({ title: 'Checkout' })
```
A aba do navegador (e o card de compartilhamento) dizem "Checkout | Nelson
Boulangerie", enquanto o `<h1>` diz "Finalize seu pedido" (`:1049`) e o breadcrumb
diz "Finalizar pedido" (`:1041`). Todas as outras páginas usam pt-BR ("Entrar",
"Sacola", "Cardápio", "Favoritos"). Também vaza em `app/utils/operationalCopy.ts:20`.

### P1 — Erro do checkout: duas palavras e um botão, no pior momento possível
`finalizar.vue:1061-1066`
```html
<UiAlert v-else-if="error" variant="destructive">
  <UiAlertTitle>Checkout indisponível</UiAlertTitle>
  <UiAlertDescription>
    <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
  </UiAlertDescription>
</UiAlert>
```
A `AlertDescription` contém **apenas um botão** — zero explicação, zero WhatsApp,
zero "sua sacola está guardada". É a única tela da loja onde há dinheiro em jogo, e é
a que menos explica. Compare com a home (`index.vue:157-165`) e com a sacola
(`sacola.vue:132-140`), ambas mais generosas.

### P1 — No mobile, o checkout não tem nenhuma porta de ajuda
Três fatos que se somam: o footer é escondido em `/finalizar` (`app.vue:50`), o
`aside` com o alerta "Atendimento rápido"/WhatsApp é `hidden … lg:block`
(`finalizar.vue:1801,1840-1847`), e a barra fixa que sobraria está coberta pela
bottom-nav (P0 acima). Resultado: quem trava no checkout pelo telefone — o caso
majoritário — não tem link de WhatsApp, nem de Termos, nem de Privacidade.

### P1 — "R$ 0,00" como total do pedido durante o carregamento
`finalizar.vue:1611`, `:1732`, `:1809`, `:1856` — todos
`{{ cart?.grand_total_display || 'R$ 0,00' }}`. Em rede lenta ou durante um
`refresh` de cupom/fidelidade, a tela de pagamento exibe **Total do pedido: R$ 0,00**
em corpo grande. Num checkout, um zero é alarme. Correção: `—` ou um skeleton
inline; nunca um valor monetário inventado.

### P1 — "Não confirmado" como título de erro
`finalizar.vue:1102` e `:1658`. Particípio seco, sem sujeito, sem próximo passo.
O corpo traz o `serverError`, mas o título é o que se lê primeiro.

### P2 — `pickup_hint` sem fallback, `delivery_hint` com
`finalizar.vue:1183` (`{{ checkout.pickup_hint }}`) vs `:1195`
(`{{ checkout.delivery_hint || 'Taxa conforme a região' }}`). Assimetria: se a
projeção vier vazia, a opção "Retirada" fica sem subtítulo e a "Entrega" não.

### P2 — "Esta é a opção disponível para este pedido." não diz por quê
`finalizar.vue:1201-1203`. Quando só há retirada (loja sem entrega hoje, ou pedido
fora da área), a frase é factual e muda. Ver tabela de copy.

### P2 — `revealFirstError` rola para o primeiro erro do DOM, não para o primeiro erro
`finalizar.vue:781-789`: `useSonner.error(first.message)` usa a prioridade de
`firstCheckoutError`, mas o `scrollIntoView` usa
`document.querySelector('[data-slot="field-error"]')` — o primeiro do documento.
Quando os dois divergem, o toast fala de um campo e a tela rola para outro.

### P2 — "Precisa de troco?" só em entrega
`finalizar.vue:1466` (`v-if="state.payment_method === 'cash' && !isPickup"`).
Defensável (no balcão o operador resolve), mas o cliente que vai pagar R$ 47 com
uma nota de R$ 100 na retirada não tem como avisar. E `state.change_for` é texto
livre sem máscara (`:1470-1477`).

### P2 — "Pague ao receber" para dinheiro na retirada
`app/utils/checkoutFlow.ts:389`. O hint é derivado só do método, não do
`fulfillment_type`. Na retirada, "Pague no balcão" é o que a casa diria.

### Verificado — o que o checkout faz certo (ver seção final)
Rascunho em `localStorage` com validade de 6h, chave de idempotência preservada no
erro e regenerada no sucesso, guarda de duplo envio, poka-yoke de troca para
retirada, mínimo de entrega barrado cedo com CTA que resolve, transparência do
endereço que será salvo, aviso do que acontece com os pontos.

---

## pedido/[ref] (acompanhamento)

Melhor página da superfície. Achados:

### P1 — Contagem regressiva da fila em `aria-live`
`app/pages/pedido/[ref]/index.vue:538`
```html
<p v-if="waitlistDeadlineLeft" class="tabular-nums font-semibold" aria-live="polite">
  Confirme em {{ waitlistDeadlineLeft }}
</p>
```
Mesmo defeito da sacola (anúncio por segundo). Ironicamente a própria página faz
certo 40 linhas abaixo, com comentário explicando (`:574-576`).

### P2 — Breadcrumb "Pedidos" leva a `/conta`, não a `/conta/pedidos`
`pedido/[ref]/index.vue:423`: `{ label: 'Pedidos', link: '/conta' }`. Rótulo e
destino discordam, e `/conta/pedidos` existe.

### P2 — Empty state do resumo diz o que já está acontecendo
`pedido/[ref]/index.vue:737`: `"Os itens deste pedido aparecem aqui."` — mostrado
justamente quando **não** aparecem.

### P2 — Sem `<meta robots>` na página de acompanhamento
`server/routes/robots.txt.ts:14` bloqueia `/pedido/` (bom, e é o mecanismo certo),
mas um link de acompanhamento compartilhado por WhatsApp e depois republicado em
outro site pode ser indexado por descoberta lateral. `robots: 'noindex'` na página
custa uma linha e fecha o buraco (é o que `busca.vue:111`, `a.vue:115`,
`oferta/[ref].vue:76` e `conta/favoritos.vue:19` já fazem).

### Verificado
Frescor do dado com recuperação, `role="timer"` correto, offline imediato, timeline
com indicador próprio para cancelado, motivo do cancelamento + status do estorno
visíveis, avaliação sem viés (começa em 0 estrelas), estado de agradecimento no
lugar de toast, ação decorativa renderizada como rótulo e não como botão morto,
SSE + poll + reconciliação por foco.

---

## entrar

### P0 — O código de acesso do cliente é impresso na tela (bloqueador já rastreado)
`app/pages/entrar.vue:576-613` renderiza `debug_otp_code` num alerta com o código em
`font-mono text-3xl` e um botão "Usar código de teste".

Já está no radar (`SHOPMAN_EXPOSE_DEBUG_OTP`, PR #445 nasce `False`). Registro aqui
porque o encargo é adversarial e este é, de longe, o pior item da superfície de
cliente: qualquer pessoa com o número de telefone de outra entra na conta dela.
**Não pode ir ao ar.**

### P1 — A tela de entrada não linka Termos nem Privacidade
`entrar.vue:697` diz "Usamos seu telefone para autenticar a entrada. Seus dados não
são compartilhados." — uma afirmação de privacidade **sem link para a política**. O
rodapé (que tem os links) existe nessa rota, mas o texto que faz a promessa é o
lugar onde o link pertence.

### P2 — "Não consigo usar WhatsApp" abre o caminho de SMS sem dizer
`entrar.vue:515`. O rótulo descreve um problema, não a ação. "Entrar por SMS" diz o
que acontece.

### P2 — `WhatsappVerifyPanel.vue:59` põe `aria-live="polite"` na seção inteira
Qualquer mudança (geração do deep link, troca de status) re-anuncia o painel todo.

### P2 — `WhatsappVerifyPanel.vue:64` "Tente novamente ou use o SMS"
Refere um caminho que está fora do componente, atrás de outro botão, com outro nome.

### Verificado
Máquina de passos com foco movendo para o primeiro campo de cada passo
(`entrar.vue:218-222`), confirmação automática ao completar 6 dígitos com guarda de
duplo envio (`:213`, `:375`), cooldown de reenvio visível, `role="alert"` nos erros,
rate-limit tratado como recuperação calma e não como falha (`presentation/auth.ts:42`).

---

## a (access link)

Sem achados de gravidade. `robots: 'noindex'` (`a.vue:115`), token removido da barra
de endereço **antes** de qualquer outra coisa (`:65-69`, com o porquê escrito),
handoff para o navegador do sistema, fallback honesto quando o link expirou
(`:129-140`). Exemplar.

### P2 — Sem JS o `/a` fica no spinner para sempre
`a.vue:122-126` renderiza o estado de carregamento no SSR e a troca só acontece em
`onMounted`. Cenário raro; um `<noscript>` com o link para `/entrar` fecharia.

---

## busca

### P1 — Resultado de busca não é anunciado
Nenhum `aria-live` com a contagem. O `/menu` tem
(`menu.vue:392`, `menuFocusLabel`) — a busca, que é a tela onde o conteúdo muda a
cada tecla, não tem. Correção: portar o mesmo `<p class="sr-only" aria-live="polite">`.

### P2 — Empty state condicionado a `!panel.chips.length`
`busca.vue:240`. Quando o termo casa um chip mas nenhum produto, a tela mostra
"Filtre por" e mais nada — sem dizer que não houve produto.

### P2 — Empty state da busca sem CTA no overlay
`busca.vue:248-250` tem o botão do `search_empty_state`; `SearchOverlay.vue:214-222`
(a superfície que o cliente realmente usa, já que a home e o menu abrem o overlay)
**não tem**. Beco sem saída dentro do overlay.

### P2 — `bg-white` explícito num container tematizado
`busca.vue:130` e `SearchOverlay.vue:121`: `class="… rounded-full bg-white text-foreground"`.
Só não vira texto branco sobre branco no modo escuro porque a primitiva
`Ui/InputGroup/InputGroup.vue:20` já traz `dark:bg-input/30`, que ganha na cascata. É
um acidente evitado por sorte: `bg-card` resolveria sem depender da primitiva.
(O `@nuxtjs/color-mode` está sem `preference` no `nuxt.config.ts:124`, ou seja, o
padrão é `system` — o modo escuro **é** alcançável pelo telefone do cliente.)

---

## colecao/[ref]

### P2 — Breadcrumb feito à mão, diferente de todas as outras páginas
`colecao/[ref].vue:89-93` monta um `<nav>` com "Cardápio / Título", enquanto
produto, sacola, finalizar, pedido e todas as telas de conta usam `<UiBreadcrumbs>`
com "Início" na frente. O JSON-LD da própria página (`:74-78`) declara a trilha
completa com "Início" — a tela e o dado estruturado discordam.

### P2 — Meta description contada
`colecao/[ref].vue:48`: `${items.length} itens em ${title}.` quando a coleção não tem
descrição. Mesma família do problema do `/menu`.

---

## oferta/[ref]

### P2 — A mensagem de erro vira o `<h1>` da página
`oferta/[ref].vue:112`: `<h1 class="shop-title">{{ problem }}</h1>`, onde `problem`
pode ser `detail?.detail` vindo do servidor (`:65`). Um `detail` de API como título
principal do documento é frágil (comprimento, pontuação, tom).

### Verificado
`robots: 'noindex, nofollow'` com o porquê escrito (`:74-76`), conflito de sacola
resolvido perguntando em vez de sobrescrever (`:90-108`), itens que ficaram de fora
contados na tela em vez de descobertos na sacola (`:123-131`), e a decisão
deliberada de **não** exigir login (o comentário em `:4-12` é uma aula).

---

## conta/index

### P1 — Falha de rede vira "conta vazia"
`app/pages/conta/index.vue:21`
```ts
const { data: summary, pending } = await useFetch<AccountSummary>(…)
```
`error` não é desestruturado e não há estado de erro. Se `/api/v1/account/summary/`
falhar: `summary` é `null`, `activeOrders` = `[]`, `lastOrder` = `null`, `navCards`
sem contadores, `countLabel` = "0 pedidos". O cliente com 50 pedidos vê uma conta
que parece vazia, sem nenhuma indicação de que houve falha, e sem botão de tentar
de novo.

Mesmo defeito, mesma linha de código, em:
- `conta/pedidos.vue:25` → renderiza o `UiEmpty` "você ainda não fez pedidos"
- `conta/enderecos.vue:23` → renderiza "Nenhum endereço salvo"
- `conta/perfil.vue:34` → renderiza o cartão com tudo "Não informado"
- `conta/preferencias.vue:12` → renderiza dois fieldsets vazios, sem uma linha

Cinco páginas. `conta/favoritos.vue:10` é a única que faz certo (desestrutura
`error` e mostra alerta com retry, `:39-47`) — o padrão correto já existe no
diretório.

### P2 — "Sair" pode não fazer nada
`conta/index.vue:51-68`: o `try` não tem `catch`. Se o POST de logout falhar
(offline, 500), a promise rejeita, `session.reset()` e `navigateTo('/')` nunca
rodam; o `finally` fecha o diálogo. Da perspectiva do cliente: clicou em "Sair",
o diálogo fechou, e continua logado.

---

## conta/pedidos

### P1 — Erro como vazio (ver conta/index)

### P2 — Sem paginação
`conta/pedidos.vue:25` busca a lista inteira. Para a persona "50 pedidos" isso é uma
página infinita sem "carregar mais" e um payload grande no 3G.

### P2 — Skeleton único de 128px
`conta/pedidos.vue:94` (`<UiSkeleton class="h-32 rounded-lg" />`) não espelha a
lista que vai chegar. O menu (`menu.vue:398-407`) e a PDP fazem certo.

---

## conta/perfil

### P1 — Erro como vazio (ver conta/index)

### P2 — "Telefone confirmado" onde deveria haver um telefone
`conta/perfil.vue:56`: fallback de `phoneDisplayLabel`. Numa lista de rótulo:valor
("Telefone: Telefone confirmado") é confuso. `missing_value` ("Não informado") é o
fallback coerente com as outras três linhas.

### P2 — Dupla confirmação do salvamento
`conta/perfil.vue:114` (alerta persistente) + `:116` (toast). Um dos dois basta.

---

## conta/enderecos

### P1 — Erro como vazio (ver conta/index)

### P2 — "Definir padrão" pode falhar em silêncio
`conta/enderecos.vue:59-72`: `try/finally` sem `catch`. Falha = spinner some, nada
muda, nada é dito.

### P2 — Confirmação de remoção sem consequência declarada
`conta/enderecos.vue:196-198`: a descrição é só o endereço. Não diz que a ação é
definitiva nem o que acontece com pedidos que o usaram.

---

## conta/preferencias

### P1 — Erro como vazio (ver conta/index)

### Verificado
`preferencias.vue:93-101` — a explicação dos três estados da notificação (recado
transacional vs. o resto, e o que desligar uma chave cala) é o melhor parágrafo de
copy da superfície inteira. É exatamente o que "falhar gritando" quer dizer em copy.

---

## conta/seguranca

Sem achados de gravidade. Step-up por OTP antes de exportar ou excluir
(`seguranca.vue:27`), checkbox de reconhecimento explícito antes da exclusão
(`:466-469`), explicação do que sobrevive por obrigação fiscal (`:467`), passkeys com
mensagens honestas sobre por que não funcionam (`composables/usePasskey.ts:64,67`).

### P2 — `favoritos` tem `robots: noindex`, `seguranca` não
`conta/favoritos.vue:19` declara `robots: 'noindex, follow'`; nenhuma outra página de
`/conta/*` declara. O `robots.txt` cobre `/conta`, então o risco é teórico — mas a
inconsistência sugere que alguém achou que era necessário em um lugar só.

---

## privacy · terms

### P0 — Texto legal obrigatório sem aval do dono, com o aviso no próprio arquivo
`app/pages/privacy.vue:10-11`
```
// ⚠️ ESTE TEXTO PRECISA DO AVAL DO DONO antes do go-live. Ele descreve o que o
// sistema REALMENTE faz hoje — foi escrito a partir do código, não de modelo.
```
`app/pages/terms.vue:8-15` idem, listando três pontos que são decisão do dono
(política de troca/devolução de alimento e art. 49 do CDC; prazo e forma do
estorno; razão social e horário oficial).

Estas páginas cumprem exigência do art. 9º da LGPD e do Decreto 7.962/2013 e estão
linkadas do rodapé de toda tela. Publicar sem o aval é publicar um compromisso
jurídico que ninguém aprovou. É bloqueador de go-live por definição — e o próprio
código sabe disso.

### P2 — Data de atualização congelada
`privacy.vue:31` e `terms.vue:20`: `const updatedAt = '20 de agosto de 2026'`,
hardcoded. Toda edição posterior ao texto (houve pelo menos uma, registrada em
`privacy.vue:13` como "fechadas em 21/08") deixa a data mentindo.

---

## Cross-cutting

### P1 — "carrinho" e "sacola" são a mesma coisa com dois nomes
A superfície inteira diz **sacola**: bottom-nav (`AppBottomNav.vue:15`), header
(`ShopHeader.vue:30,192`), página (`sacola.vue:115` "Sua sacola"), breadcrumbs,
login ("Sua sacola está guardada"). Três strings vivas dizem **carrinho**:

- `app/composables/useCartState.ts:87` → `reason: 'Carrinho vazio.'`
  (é o `reason` do action `checkout`, renderizado em `sacola.vue:192,359,393` e
  `finalizar.vue:1640` — o cliente lê isso)
- `app/composables/useCartState.ts:323` → `'Não foi possível atualizar o carrinho.'`
  (toast em toda falha de mutação — `:324`)
- `app/composables/useReorder.ts:23` → `'Itens adicionados ao carrinho.'`
  (toast de sucesso do "Pedir de novo", disparado da home, da conta e do
  acompanhamento)

O terceiro é o pior: é a confirmação de sucesso mais frequente da loja, e usa a
palavra que a loja não usa.

### P1 — `FavoriteHeart` anuncia o SKU para leitores de tela
`app/components/FavoriteHeart.vue:41`
```ts
:aria-label="active ? `Remover ${sku} dos favoritos` : `Salvar ${sku} nos favoritos`"
```
O leitor de tela ouve "Salvar PAO-INT-500 nos favoritos". O componente recebe só
`sku` e `initial` (`:4-8`) — nunca recebeu o nome. Todos os outros componentes
fazem certo: `CartQuantityAction.vue:57`, `QuantityControl.vue:38,47,57`,
`ProductTile.vue:57`, `ProductListItem.vue:32`, `SubstituteSheet.vue:93` usam
`meta.name` / `item.name`. Correção: adicionar a prop `name` e usá-la (o chamador
`produto/[sku].vue:257` já tem `product.name` à mão).

### P1 — SKU impresso no card do produto sem foto
`app/components/ProductImageFallback.vue:25`
```html
<span class="font-mono text-xs uppercase tracking-widest opacity-80">{{ sku }}</span>
```
Usado em `ProductTile.vue:44-51`, `ProductListItem.vue:68-75` e
`produto/[sku].vue:193-200`. Qualquer produto sem `image_url` mostra o código
interno em monoespaçada no lugar da foto — no cardápio, na busca, nos favoritos e na
página do produto. São 51 fotos em `public/img/products/` para um catálogo que pode
ser maior; a diferença aparece como jargão de estoque na vitrine.

Correção: o `ProductImageFallback` já tem cor e ícone de categoria (o desenho está
certo); trocar o `{{ sku }}` pelo **nome do produto** (ou por nada). O SKU pode
ficar num `data-*` para teste.

### P1 — Barra de status do header fica `aria-hidden` com um link focável dentro
`app/components/ShopHeader.vue:110`
```html
<div class="bg-ink text-ink-foreground" :aria-hidden="scrolled ? 'true' : undefined">
```
Dentro há um `<a>` "Ligar" / "Mensagem" (`:116-135`). Ao rolar, o container vira
`aria-hidden="true"` mas o link continua na ordem de tabulação: quem navega por
teclado tab-a para um elemento que a árvore de acessibilidade declara inexistente
(violação direta de WCAG 4.1.2, e os navegadores modernos emitem warning).
Correção: `inert` no container (que já remove do foco e da AT) em vez de
`aria-hidden`, ou `:tabindex="scrolled ? -1 : undefined"` no link.

### P1 — Copiar código Pix pode falhar sem que ninguém saiba
`app/components/PaymentBlock.vue:36-40`
```ts
async function copyPix () {
  if (!props.promise.pix_copy_paste || !import.meta.client) return
  await navigator.clipboard.writeText(props.promise.pix_copy_paste)
  useSonner.success(props.copy.pix_copied)
}
```
Sem `try/catch`. `navigator.clipboard` rejeita em contexto não-seguro, em alguns
WebViews e quando a permissão é negada — e o `await` sem catch vira rejeição não
tratada: **nenhum toast, nenhum erro, nada acontece**. O cliente com o Pix aberto
toca em "Copiar" e não sabe se copiou. O texto está visível (`:97`) e é
selecionável, mas está `truncate`.

Ironia: `app/utils/operationalCopy.ts:51` já tem a frase certa para esse caso
("Não foi possível copiar automaticamente. Selecione o código PIX acima e copie
manualmente.") — e o arquivo inteiro é código morto (ver abaixo).

Correção: `try/catch` com fallback de seleção. O `WhatsappVerifyPanel.vue:47-54`
já faz certo — o mesmo padrão, dois arquivos ao lado.

### P1 — `StockNotifyButton` pede o telefone sem dizer de qual produto
`app/components/StockNotifyButton.vue:163-164`
```html
title="Avisamos quando estiver disponível"
description="Deixe seu WhatsApp e mandamos uma mensagem assim que estiver disponível."
```
O componente **recebe** `name` (`:11`) e o usa em `aria-label`/`title` (`:24-25`),
mas o sheet — a superfície onde o cliente decide entregar o telefone — não nomeia o
produto. Quem toca no sino de um card no meio do cardápio não vê qual item o aviso
cobre. Correção: `:title="\`Avisamos quando ${name} voltar\`"`.

### P1 — `SubstituteSheet` erra o gênero em pt-BR
`app/components/SubstituteSheet.vue:48`
```ts
: `O ${itemName.value} acabou agora. Veja boas alternativas.`
```
Artigo masculino colado num nome de produto de gênero desconhecido: "O Baguete
acabou agora", "O Focaccia acabou agora", "O Rosca de coco acabou agora". Correção
sem artigo: `` `${itemName} acabou agora. Veja boas alternativas.` `` — funciona nos
dois gêneros.

### P1 — Nenhum aviso de que a superfície não roda sem JS
Nada de crítico depende disso (o SSR entrega HTML), mas `/a`, `/oferta/[ref]` e o
`SearchOverlay` são inteiramente client-side. Sem `<noscript>` em lugar nenhum.

### P1 — `app/utils/operationalCopy.ts` é um dicionário de copy morto — e ruim
72 linhas, exportando 30+ strings de erro. `grep -rn "operationalCopy" app/ tests/`
fora do próprio arquivo: **zero ocorrências**. Nem importado, nem testado.

Isso importa porque é uma armadilha carregada: quem for ligá-lo vai enviar
`"Não foi possível carregar o checkout"` (`:20`, inglês), `"Volte ao carrinho"`
(`:21`, termo errado), `"Estoque, pedido mínimo, agenda, pagamento e dados do
cliente serão validados no envio."` (`:46`, fala de sistema pura), `"Sem
disponibilidade para a quantidade solicitada."` (`:30`, burocrática) e duas
referências a botões que não existem — "Use **Verificar novamente**" (`:42`) e
"Use **Atualizar status**" (`:53`).

Correção: apagar o arquivo, ou reescrever as strings antes que alguém as ligue.

### P2 — `.shop-bottom-safe` mora só no rodapé
`app/assets/css/tailwind.css:462` define `padding-bottom: calc(env(safe-area-inset-bottom) + 5.5rem)`
e ele é aplicado exclusivamente em `ShopFooter.vue:14` — com um guardrail que trava
isso (`tests/surfaceGuardrails.test.ts:543-544`). Em `/finalizar`, onde o rodapé é
escondido (`app.vue:50`), não sobra folga nenhuma para a bottom-nav. É o mecanismo
por trás do P0 da barra de checkout.

### P2 — Três formulações do mesmo erro e dois rótulos do mesmo botão
Títulos: "Não foi possível carregar a loja" (`index.vue:158`) · "Não conseguimos
abrir o cardápio agora" (`menu.vue:410`) · "Não foi possível abrir este produto"
(`produto:148`) · "Sua sacola não quis carregar agora" (`sacola:133`) · "Checkout
indisponível" (`finalizar:1062`) · "Não conseguimos buscar agora" (`busca:160`).
Botões: "Tentar novamente" (`index:162`) vs "Tentar de novo" (5 lugares) vs
"Atualizar" (`finalizar:1064`). Escolher um padrão e aplicá-lo.

### P2 — "Me avise" e "Avise-me" no mesmo componente
`StockNotifyButton.vue:121,132,148,158` dizem "Me avise"; o submit do formulário
(`:179`) diz "Avise-me". Mesma ação, mesmo componente, duas ordens de palavras.

### P2 — Não há como cancelar um aviso de estoque
`StockNotifyButton.vue:83-106`: o estado inscrito é um botão desabilitado
("Anotado" / "Avisaremos você"). Sem caminho para desinscrever, em nenhuma tela.

### P2 — "Pix" e "PIX" convivem
`checkoutFlow.ts:382` e `PaymentBlock` usam "Pix" (grafia oficial do Bacen);
`operationalCopy.ts:51` usa "PIX".

### P2 — `v-html` de SVG de rede social vindo do servidor
`ShopHeader.vue:326`. Curado pelo gerente no Admin (o comentário diz), então não é
input do cliente — mas é uma superfície de injeção que depende inteiramente da
disciplina do Admin.

### P2 — `AddressPicker` culpa o aparelho pelo que o cliente negou
`app/components/AddressPicker.vue:389`: `'Geolocalização não está disponível neste
aparelho.'` — a mesma frase para "o navegador não suporta" e para "o cliente negou
a permissão". No segundo caso a afirmação é falsa e não diz como reverter.

### P2 — Acoplamento de altura do header em três lugares
`app.vue:76` (`calc(100svh-4rem)`), `menu.vue:324` (`top-16`), `busca.vue:120`
(`md:top-16`), `HomeHeroThing.vue:256` (`calc(100svh-15.25rem-…)`). Quatro números
mágicos derivados da mesma medida, mantidos à mão.

---

## Copy rewrite table

| file:LINE | atual | proposto |
|---|---|---|
| `app/pages/menu.vue:297` | `${n} itens publicados.` / `Cardápio publicado.` | `Pães, doces e salgados feitos à mão todo dia. Peça para retirar ou receber.` |
| `app/pages/menu.vue:422` | `{{ n }}% de desconto aplicado no cardápio.` | `{{ n }}% de desconto em tudo até {{ hora }}. Aproveite.` |
| `app/pages/produto/[sku].vue:42` | `'Pausado'` | `'Indisponível hoje'` |
| `app/pages/produto/[sku].vue:45` | `A loja pausou este item temporariamente.` | `Hoje não temos este item. Ele volta ao cardápio assim que sair do forno.` |
| `app/pages/produto/[sku].vue:46` | `Este item não está disponível agora.` | `Este item acabou por hoje. Quer que a gente avise quando voltar?` |
| `app/pages/produto/[sku].vue:151` | `Tivemos um percalço ao carregar. Tente de novo em instantes.` | `Não conseguimos abrir este produto agora. Tente de novo — ou fale conosco no WhatsApp.` |
| `app/pages/index.vue:262` | `Seu pedido anterior volta à sacola para revisão.` | `A gente devolve os mesmos itens à sacola. Você confere antes de enviar.` |
| `app/pages/index.vue:270` | `'Ver histórico'` (fallback) | `'Ver meus pedidos'` |
| `app/pages/sacola.vue:133` | `Sua sacola não quis carregar agora` | `Não conseguimos abrir sua sacola` |
| `app/pages/sacola.vue:136` | `Seus itens estão guardados. Tente de novo em instantes.` | `Nada foi perdido. Tente de novo em instantes.` |
| `app/pages/sacola.vue:235` | `{{ qty }} × {{ price }} cada` | `{{ qty }} × {{ price }}` (e o preço original com rótulo: `De {{ original }}`) |
| `app/pages/sacola.vue:285` | `Usar {{ n }} disponíve{is/l}` | `Deixar {{ n }} — é o que temos hoje` |
| `app/pages/sacola.vue:338` | `Escolha a retirada na loja ou um endereço dentro da nossa área.` | `Ainda não entregamos aí. Você pode retirar na loja — ou trocar o endereço.` **+ dois botões** |
| `app/pages/finalizar.vue:1029` | `title: 'Checkout'` | `title: 'Finalizar pedido'` |
| `app/pages/finalizar.vue:1062` | `Checkout indisponível` | `Não conseguimos abrir o checkout` |
| `app/pages/finalizar.vue:1063-65` | *(só um botão "Atualizar")* | `Sua sacola está guardada. Tente de novo — se preferir fechar agora, fale conosco no WhatsApp.` + Tentar de novo + WhatsApp |
| `app/pages/finalizar.vue:1102`, `:1658` | `Não confirmado` | `Não conseguimos fechar seu pedido` |
| `app/pages/finalizar.vue:1202` | `Esta é a opção disponível para este pedido.` | `Hoje estamos só com {{ retirada/entrega }}.` |
| `app/pages/finalizar.vue:1611,1732,1809,1856` | `\|\| 'R$ 0,00'` | `\|\| '—'` |
| `app/pages/finalizar.vue:822` | `Pedido não pode ser confirmado agora.` | `Não dá para confirmar agora. Revise os itens da sacola e tente de novo.` |
| `app/pages/pedido/[ref]/index.vue:737` | `Os itens deste pedido aparecem aqui.` | `Não conseguimos carregar os itens deste pedido.` |
| `app/pages/entrar.vue:515` | `Não consigo usar WhatsApp` | `Prefiro entrar por SMS` |
| `app/composables/useCartState.ts:87` | `Carrinho vazio.` | `Sua sacola está vazia.` |
| `app/composables/useCartState.ts:323` | `Não foi possível atualizar o carrinho.` | `Não conseguimos atualizar sua sacola.` |
| `app/composables/useReorder.ts:23` | `Itens adicionados ao carrinho.` | `Pronto, tudo de volta na sua sacola.` |
| `app/components/SubstituteSheet.vue:48` | `O ${itemName} acabou agora. Veja boas alternativas.` | `${itemName} acabou agora. Veja boas alternativas.` |
| `app/components/StockNotifyButton.vue:163` | `Avisamos quando estiver disponível` | `Avisamos quando ${name} voltar` |
| `app/components/StockNotifyButton.vue:179` | `Avise-me` | `Me avise` |
| `app/components/ShopFooter.vue:31` | `Consulte os horários de atendimento.` | `Fale conosco no WhatsApp para confirmar o horário de hoje.` |
| `app/components/ShopHeader.vue:114` | `Confira nossos horários` (fallback) | `Fale conosco para confirmar o horário` |
| `app/components/AddressPicker.vue:389` | `Geolocalização não está disponível neste aparelho.` | `Não conseguimos usar sua localização. Você pode buscar pelo endereço ou CEP.` |
| `app/utils/checkoutFlow.ts:389` | `Pague ao receber` | `Pague na entrega` / `Pague no balcão` (por `fulfillment_type`) |
| `app/utils/operationalCopy.ts:20` | `Não foi possível carregar o checkout` | *(apagar o arquivo — ver P1)* |
| `app/utils/operationalCopy.ts:21` | `Volte ao carrinho, revise os itens e tente novamente.` | *(idem)* |
| `app/utils/operationalCopy.ts:46` | `Estoque, pedido mínimo, agenda, pagamento e dados do cliente serão validados no envio.` | *(idem)* |
| `app/presentation/auth.ts:30` | `Algo não deu certo` | `Não deu certo desta vez` |

---

## Verified-safe

Padrões que já estão certos e não devem ser mexidos:

**Arquitetura de estados**
- `app/error.vue` — 404 e 5xx com copy distinta, botão "Tentar de novo" que cumpre a
  promessa da frase, WhatsApp de saída, `robots: noindex, follow`, e o **esqueleto CSS
  inline** (`:98-126`) para a tela nunca abrir crua quando a folha global morre no
  deploy. Exemplar.
- `app/components/EnvironmentRibbon.vue` — a fita de ambiente. `pointer-events-none`
  no contêiner inteiro, `role="status"` sr-only fora da rotação, a frase vindo do
  servidor (sem interruptor próprio), e o comentário de geometria (`:55-80`) que
  explica o sistema de quatro números. Referência de como se documenta uma decisão.
- `app/components/SubstituteSheet.vue` — o 409 de estoque tratado como ajuda, não como
  erro: quantidade disponível, substitutos em um toque, "Me avise" quando esgotou de
  vez, "Agora não" sempre presente.
- `app/pages/oferta/[ref].vue` — conflito de sacola resolvido perguntando; itens que
  ficaram de fora contados na tela; `noindex, nofollow` com o porquê escrito.
- `app/pages/a.vue` — token removido da barra de endereço antes de qualquer coisa.

**Checkout**
- Rascunho em `localStorage` com validade de 6h, restaurado **síncrono no setup** para
  os watchers o respeitarem (`finalizar.vue:424-466`) — resolve a persona "abandona e
  volta".
- Idempotência: chave preservada no erro, regenerada só no sucesso (`:916,928`).
- Duplo envio: `submitting` + `submitDisabled` (`:292`).
- Poka-yoke de fora-de-zona com troca para retirada em um clique (`:1069-1077`).
- Mínimo de entrega barrado no passo de recebimento, com CTA que resolve, em vez de
  no commit (`:306-312`, `:1207-1237`).
- Transparência do endereço que será salvo, **antes** de salvar (`:1269-1276`).
- Sacola vazia com CTA vivo em vez de botão morto (`:1615-1627`).
- Bug do campo Nome documentado e consertado por estado, não por conteúdo
  (`:332-347` — a explicação vale mais que o conserto).

**Acessibilidade que já está certa**
- Skip link (`app.vue:69-75`), `NuxtRouteAnnouncer` (`:68`).
- `useOverlayLock` com `inert` + Esc + restauração de foco (`SearchOverlay.vue:49-52`,
  `ShopHeader.vue:88-93`).
- `role="timer"` sem `aria-live` na contagem do acompanhamento, **com o porquê
  escrito** (`pedido/[ref]/index.vue:574-576`).
- `aria-live` de contagem de resultados no cardápio (`menu.vue:392`).
- `aria-label` com nome de produto em todos os controles de quantidade e de card.
- Alvos de toque de 44px nos chips de busca (`busca.vue:178,216`) e nos ícones do
  header (`ShopHeader.vue:147,190`).
- `htmlAttrs: { lang: 'pt-BR' }` (`nuxt.config.ts:35`).

**Infra de conteúdo**
- Fontes servidas do próprio repo com `fallbacks` métricos para zero CLS, e o
  incidente do build que motivou a mudança documentado (`nuxt.config.ts:66-107`).
- `routeRules` de cache imutável para `/img/products/**` com a convenção de renomear
  em vez de sobrescrever (`nuxt.config.ts:26-30`).
- `robots.txt` domain-aware bloqueando `/conta`, `/finalizar`, `/sacola`, `/entrar`,
  `/pedido/` (`server/routes/robots.txt.ts`); sitemap alimentado pelo catálogo real.
- JSON-LD Bakery / Product / CollectionPage / BreadcrumbList com canonical
  self-consistente.
- Cartões de teste do Stripe gatilhados pela **chave do gateway**, não por flag
  (`shopman/storefront/presentation/checkout.py:306-328`) — a tupla volta vazia com
  chave live, então o bloco não existe nem no HTML.
- Copy do servidor tem fallback literal no Python
  (`copy.title("TRACKING_CANCEL_CTA", "Cancelar pedido")`,
  `shopman/storefront/presentation/order_tracking.py:1297`), com teste cruzando as
  chaves usadas contra `OMOTENASHI_DEFAULTS`
  (`shopman/shop/tests/test_omotenashi_copy_keys.py`). Botão vazio por falta de
  linha no banco **não** é um risco.
- `bg-white` no paspatur da foto (`ProductTile.vue:33`, `produto/[sku].vue:163`) e na
  moldura do QR Pix (`PaymentBlock.vue:79`) é deliberado e correto.

**Copy que já está no tom**
- `conta/preferencias.vue:93-101` — os três estados da notificação.
- `finalizar.vue:1095-1097` — "É só enviar a mensagem que já vai pronta. Sua sacola
  fica guardada."
- `finalizar.vue:1479` — "Informe o valor da nota para o entregador levar o troco
  certinho."
- `sacola.vue:296` — "Por hoje, temos N unidades deste item."
- `BrowserHandoffCard.vue:31-33,49-51` — promete o resultado, não a tecnologia, e o
  degrau manual que nunca falha.
- `pedido/[ref]/index.vue:226` — "Que bom que chegou. Bom apetite!"
- `oferta/[ref].vue:114` — "O cardápio de hoje segue no ar, e tem coisa boa saindo do
  forno."
