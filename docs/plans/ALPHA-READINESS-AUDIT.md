# ALPHA-READINESS-AUDIT — pronto para pessoas reais no staging?

**Status:** aberto (2026-08-01). Alpha = colocar o staging na frente de
testadores reais (amigos, equipe, alguns clientes) para exercitar o produto de
ponta a ponta. NÃO é go-live (produção): para produção, ver
[GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md),
[GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) e
[GO-LIVE-SMS-WHATSAPP-STATUS](GO-LIVE-SMS-WHATSAPP-STATUS.md).

O objetivo aqui é honesto: dizer **o que já dá para testar de verdade**, **o que
está simulado/degradado no staging** (e o que isso significa para o teste), e
**o que falta fechar** para um alpha sem furos.

Staging: loja `https://shopman-staging-cdjpy.ondigitalocean.app` ·
gestor `https://gestor.boulangerie.com.br` (PIN) · admin
`https://admin.staging.nelsonboulangerie.com.br`.

---

## 1. O que já está pronto no staging (verde)

- **Pagamento fundido no acompanhamento** (PAYMENT-TRACKING-MERGE): sem rota
  `/pagamento`; Pix (QR + copia-e-cola + contador) e cartão renderizam inline no
  próprio acompanhamento. Verificado no ar.
- **Aceite otimista em 1 min** (staging): o cliente vê o QR rápido após o aceite.
- **prep_start por canal**: web espera o operador dar "Iniciar preparo" (honesto
  com o cliente remoto); iFood/PDV auto-disparam. Encomenda futura não forna antes
  do dia.
- **Pill do gestor**: pago = verde (qualquer canal/meio), esperando = ampulheta,
  marketplace pré-pago (iFood) = verde. Dinheiro = verde ao liquidar no PDV
  (tender recebido) ou COD acertado na entrega; neutro enquanto por receber.
- **Seed rico**: Cardápio 2027 (59 SKUs, coleções, bundles, receitas, fotos),
  personas (cliente novo/fiel/staff), cupons/promoções, loyalty, zonas de entrega
  + bandas de distância, slots de retirada, encomenda com produção planejada,
  happy hour, D-1 (sobras staff-only).

## 2. Roteiro de teste humano (as dimensões a exercitar)

Matriz para os testadores baterem — cada linha é um caminho que precisa "só
funcionar". Marcar ✅/❌ e anotar o pedido.

| Dimensão | Cenários a cobrir |
|---|---|
| **Pagamento** | Pix (paga / não paga → expira → cancela) · cartão (Stripe) · dinheiro (balcão/entrega) · pago iFood |
| **Fulfillment** | Retirada (slots) · entrega (endereço na zona / fora da zona / taxa por distância) |
| **Datas** | Hoje · amanhã · encomenda (data futura, dentro do lead time / além do horizonte) |
| **Descontos** | Cupom (válido / expirado / esgotado) · happy hour · loyalty (resgate) · D-1 (staff) |
| **Combinações** | Bundle · múltiplos itens · quantidades · item esgotado (estoque) · substituto |
| **Personas** | Cliente novo (OTP 1ª vez) · cliente fiel (reconhecido) · staff (D-1) |
| **Horários/dias** | Loja aberta · loja fechada (mensagem "conferimos na abertura") · vira o dia |
| **Endereço** | CEP → autofill · seleção no mapa (Google) · endereço salvo · reuso |
| **Operador (gestor)** | Aceitar/recusar · "Iniciar preparo" · avançar até pronto/entregue · KDS bump |
| **Acompanhamento** | Cada estado da cascata (recebido → pago → preparando → pronto → entregue) · SSE ao vivo |

> Pré-condição p/ testar Pix de ponta a ponta: em DEBUG/staging há "Simular
> pagamento" no acompanhamento (captura por gateway mock). Pagamento Pix REAL
> depende de sair do sandbox Efí (ver §3).

## 3. O que está simulado/degradado no staging (e o que significa)

> **Conferido no spec LIVE do DigitalOcean em 2026-08-11.** A tabela anterior
> descrevia a intenção, não o que está no ar — e um roteiro de teste com premissa
> errada produz falso furo em massa ("não recebi o SMS", "o QR não é real"), que
> queima a rodada de testadores. Os valores abaixo saem de
> `doctl apps spec get 40b86e35-...`.

| Área | Estado no staging | Impacto no teste |
|---|---|---|
| **Pix** | ❗**MOCK**, não Efí sandbox (`SHOPMAN_PIX_ADAPTER = shopman.shop.adapters.payment_mock`, `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true`) | O QR **não** é de gateway nenhum. O fluxo roda inteiro, mas a captura é sempre "Simular pagamento". As credenciais Efí existem no spec e `EFI_SANDBOX=true` — só o adapter não aponta para lá. `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false` (o pagamento não se confirma sozinho) |
| **Cartão** | ❗**MOCK** (`SHOPMAN_CARD_ADAPTER = shopman.shop.adapters.payment_mock`) — pergunta de §5 **respondida** | Não é Stripe test. A chave `pk_test_…` e `STRIPE_CAPTURE_METHOD=manual` estão no spec, mas o adapter não é o da Stripe |
| **SMS / OTP** | ❗**Nada é enviado** (`DOORMAN_MESSAGE_SENDER_CLASS = shopman.doorman.senders.LogSender`) | O código de acesso só vai para o log. O login só funciona porque `SHOPMAN_EXPOSE_DEBUG_OTP=true` devolve o código na resposta. **A chave da Comtele e a rota 17 estão configuradas** — trocar o sender é uma linha de env; ⚠️ mas a Comtele estava em HTTP 500 em 10/08, então testar antes de prometer |
| **WhatsApp (Meta)** | Credenciais **presentes** no spec (`META_PAGE_ACCESS_TOKEN`, `META_PAGE_ID`, `META_IG_USER_ID`, `MANYCHAT_API_TOKEN`) — validade/escopo **não testados** | O "⏳ credencial pendente" ficou desatualizado. Mas com `LogSender` ativo nada sai por canal nenhum, então o efeito prático hoje é o mesmo |
| **NFC-e (Focus NFe)** | ⏳ pendente | Sem emissão/impressão fiscal (obrigação legal — bloqueia go-live, não o alpha) |
| **iFood** | Direto ✅ staging; homologação prod pendente | Entrada de pedido iFood testável em staging |
| **Estoque** | ⚠️ "fantasma" (autosserviço) | Por isso o aceite (disponibilidade) existe antes de cobrar — não confiar 100% no número |

## 4. Comportamentos que os testadores VÃO encontrar (esperados, não bugs)

- **Espera pelo QR**: pedido web novo fica "conferindo a disponibilidade" até o
  aceite (auto em 1 min no staging, ou o operador aceita antes no gestor). Só
  então o QR do Pix aparece. É a confirmação otimista + estoque fantasma.
- **"Iniciar preparo" é do operador**: pago não vira "Em preparo" sozinho no web;
  o operador dispara no gestor. O cliente lê "Pagamento confirmado / já vamos
  começar" nesse meio-tempo.
- **Sem tela de pagamento**: tudo acontece na página do pedido. Isso é de propósito.

## 5. Pendências e decisões abertas

- [x] **Pill de dinheiro — DECIDIDO:** verde ao liquidar no PDV (tender
      recebido) ou COD acertado na entrega; neutro enquanto por receber (COD
      pendente, web pagar-na-retirada). Lê `Order.data.payment.tenders`.
- [x] **Hydration mismatch global — NÃO REPRODUZ (11/08):** home e `/menu`
      recarregadas com o console aberto, zero warning (canal de console validado
      com um probe, para não confundir "sem warning" com "sem captura").
- [x] **Cartão no staging — RESPONDIDO (11/08):** é **mock**, não Stripe test
      (`SHOPMAN_CARD_ADAPTER = payment_mock`). O mesmo vale para o Pix.
- [ ] **Decisão de alpha: sair do mock?** Três envs resolvem, e as credenciais já
      estão no spec: `SHOPMAN_PIX_ADAPTER` → Efí (sandbox), `SHOPMAN_CARD_ADAPTER`
      → Stripe (test), `DOORMAN_MESSAGE_SENDER_CLASS` → Comtele. Cada uma torna
      uma dimensão do §2 real em vez de simulada. Custo: nenhum código.
- [ ] **OTP de verdade**: hoje o código só vai para o log e é devolvido na
      resposta (`SHOPMAN_EXPOSE_DEBUG_OTP=true`). Para testador real isso é
      aceitável se combinado, mas é o item que mais parece "quebrado" sem aviso.
- [ ] **WhatsApp Meta**: credenciais já presentes no spec; falta **testar**
      validade/escopo — ver GO-LIVE-SMS-WHATSAPP-STATUS.
- [ ] **NFC-e**: pré-requisito legal de go-live, não de alpha.
- [ ] **Pix real (sair do sandbox Efí)**: para um alpha com pagamento de verdade.
- [ ] **iFood**: homologação de produção (staging já testa direto).
- [ ] **Fotos superdimensionadas** (§7, furo #1) — decidir entre redimensionar os
      assets no `nb-catalog` ou parar de hotlinkar o `raw.githubusercontent.com`.

---

## 7. Smoke do roteiro §2 — 1ª rodada (2026-08-11, automatizada)

Primeira execução do item de gate "rodar o roteiro §2 uma vez e anotar furos".
Feita dirigindo o staging pelo navegador. **Cobre só o que é alcançável sem
autenticar** — ver "não coberto" no fim.

### ✅ Passou

- **Home e `/menu`**: renderizam, saudação por horário ("Boa noite"), barra de
  status "Aberto até 23h59" (loja 24/7 do piloto automático), navegação por
  coleções, busca no cardápio.
- **Console limpo**: zero warning no load das duas páginas — o hydration mismatch
  do §5 não reproduz mais.
- **Preço e promoção na listagem**: preço riscado + preço promocional aparecem
  (Ciabatta R$ 18,00 → R$ 15,30; Baguette R$ 16,00 → R$ 13,60).
- **Sacola**: adicionar pelo card vira stepper com quantidade, badge do header
  atualiza, `/sacola` mostra item, subtotal e total corretos.
- **Muro de entrada**: "Finalizar pedido" leva para `/entrar` guardando a sacola
  ("Sua sacola está guardada.").

### ⚠️ Furo #1 — fotos superdimensionadas (não bloqueia, mas o testador vê)

**35 de 35** imagens do cardápio chegam com mais de **3× a resolução** da caixa em
que são desenhadas. A maior tem **10,3 megapixels** (3208×3208) para um quadro de
**112px**. Só o que está visível são **1,35 MB**. `loading="lazy"` e
`decoding="async"` já estão corretos em `ProductListItem.vue:57` — o problema é a
**fonte**, não o markup.

Hospedagem: **`raw.githubusercontent.com` (10 imagens)** e `images.unsplash.com`
(25, essas já pedem `w=900`). As URLs nascem no seed
(`config/management/commands/seed.py:790-791`).

Sintoma observado: as fotos entram **aos poucos** — em capturas sucessivas da
mesma tela, cada vez mais quadros preenchidos. Num 4G de testador isso é um
cardápio que se monta na frente da pessoa.

⚠️ Risco extra: o `raw.githubusercontent.com` **não é CDN** e o GitHub limita
hotlink. Se estrangular durante o alpha, 10 produtos ficam sem foto.

### 🔑 Entrada: existe caminho sem WhatsApp — o alpha NÃO está bloqueado

O caminho **primário** de `/entrar` é o WhatsApp reverso: a pessoa manda um código
(`NB-XXXXXX`) para o WhatsApp da loja e recebe um link de volta. Isso depende da
automação ManyChat (**F3**, `ACCESS-LINK-UNIFICATION-PLAN`) estar no ar — se não
estiver, a pessoa manda o código e **nada volta**.

Mas o link **"Usar outro número"** revela um formulário de telefone que chama
`request-code` com método **`sms`** (`entrar.vue:452`), e o alerta de
`entrar.vue:510` **mostra o código na própria tela** enquanto
`SHOPMAN_EXPOSE_DEBUG_OTP=true`. Confirmado no ar: o formulário aparece.

**Conclusão:** dá para chamar testadores hoje, orientando-os a usar "Usar outro
número". Para tornar o login real basta trocar `DOORMAN_MESSAGE_SENDER_CLASS`
para a Comtele (chave e rota 17 já no spec) — ⚠️ testar antes, a Comtele estava
em HTTP 500 em 10/08.

---

## 8. Smoke — 2ª rodada, atrás do login (2026-08-11)

Feita com as personas do seed, entrando pelo fluxo de SMS + código de teste.

### ✅ Maria Santos (CLI-001, aniversariante) — passou

Pedido `WEB-260811-Q84` enviado com `expected_total_q: 2530`, **exatamente o
total exibido**, e aceito (201). O desconto de aniversário sobrevive ao commit
desde o fix da identidade do cliente. Passaram junto: contato reconhecido,
retirada × entrega, escolha de data/hora, Pix × cartão, loyalty ("Economize até
R$ 2,50"), promoção por SKU e o modal de revisão.

### 🔴 P0 — o pedido dava certo e o cliente caía num 404 (CORRIGIDO)

O checkout devolvia `next_url = /tracking/{ref}`; `finalizar.vue` faz
`navigateTo(next_url)` e o fallback `/pedido/{ref}` ao lado **nunca dispara**,
porque o campo vem sempre preenchido. `/tracking/{ref}` é o **endpoint**; a rota
de tela é `pages/pedido/[ref]`.

Reproduzido pela interface: pedido `WEB-260811-N78` criado (R$ 26,00) e o cliente
na tela "Não encontramos esta página" — no pior momento possível, logo após
comprar. Corrigido nos dois produtores, com teste que amarra o prefixo da API à
existência da página no repo do Nuxt.

### 🟠 Carlos Silva (CLI-006, funcionário) — INCOERÊNCIA ABERTA, decisão do dono

Na loja pública o Carlos **vê** "Desconto funcionário − R$ 5,20" (R$ 26,00 →
R$ 20,80). Ao enviar, o commit recalcula **sem** o desconto e a guarda recusa com
`total_changed`. Reconfirmando, o pedido fecha em R$ 26,00.

O mecanismo: `storefront/cart.py:77` **escreve `price_tier` na sessão** a cada
mexida na sacola, então a projeção aplica a regra de funcionário; o commit
substitui o bloco do cliente e o `price_tier` cai, então o total sobe.

⚠️ Isso ficou visível agora porque a regra de funcionário **voltou a carregar**
(commit `da69c714` — o parâmetro renomeado a desligava em silêncio). Antes, staff
não ganhava desconto em lugar nenhum e a incoerência não aparecia.

⚠️ O `test_persona_3_employee` afirma no docstring que "a loja nunca escreve
`customer.price_tier` na sessão" — **isso é falso no código atual**. O teste passa
porque o fixture não tem `RuleConfig` da regra de funcionário, ou seja, ele prova
"regra não configurada", não a fronteira. É cobertura falsa.

**✅ DECIDIDO (Pablo, 2026-08-11): o funcionário TEM o desconto na loja pública,
mas SÓ NA RETIRADA.**

O benefício é dele. Com entrega, o preço de funcionário viajaria para qualquer
endereço e viraria canal de preço para terceiros, sem ninguém ver — no balcão isso
não acontece porque alguém entrega o pacote na mão. Retirando, a testemunha volta.

O que mudou:
- O commit passou a preservar `ref` **e** `price_tier` (as duas decidem preço), o
  que acaba com a discordância entre a tela e a cobrança.
- O guarda mora na **regra**, não em código de superfície: `EmployeeRule.pickup_only`
  (default `True`), configurável pelo admin. Parâmetro novo entra com default, então
  `RuleConfig` antigo continua carregando — o caminho que quebra é o contrário
  (parâmetro nos dados que a classe não conhece), que foi o incidente de `da69c714`.
- A loja **avisa antes da escolha**: com o desconto ativo, a opção "Entrega" mostra
  "Sem o desconto de funcionário". Sem isso o preço "muda sozinho" e parece defeito.
  ⚠️ Limite conhecido: com a entrega já escolhida o desconto não está aplicado e o
  aviso some — ele cobre a decisão, não o arrependimento.

Não empilha: medido, o desconto de funcionário **substitui** a promoção (best-wins).
A Baguette de R$ 16,00 sai a R$ 12,80 (20% cheios), não a R$ 13,60 + 20%.

### 🟡 A confirmar — rascunho do checkout entre contas

Depois de sair da conta da Maria e entrar como Carlos, o contato apareceu como
**"Maria Santos" com o telefone do Carlos**. ⚠️ O fluxo usado foi por API (pedido e
logout), que não passa pelo `clearCheckoutDraft()` da interface — precisa de
repro só-pela-UI antes de virar bug. Se confirmar, é vazamento de nome entre
contas no mesmo aparelho.

### ✅ Pagamento, cascata e SSE — cobertos (12/08)

**Cascata completa**, pedido `WEB-260811-Q02` (retirada, Pix, funcionário):
Recebido 22:46 → Aceito 22:46 → **Pago** 22:56 → Em preparo 22:56 → Pronto 22:57
→ **Concluído** 22:58. Cobrado **R$ 12,80** — exatamente o total exibido. As ações
da tela viram "Avaliar pedido" / "Repetir pedido" no fim.

**SSE ao vivo confirmado** no pedido `WEB-260812-D14`: `EventSource` aberto em
0,5s e, aos 31s, dois eventos empurrados sem nenhum refresh —

```
order-update  {"ref":"WEB-260812-D14","status":"accepted","kind":"status_changed"}
order-update  {"ref":"WEB-260812-D14","payment_status":"authorized","kind":"payment_changed"}
```

⚠️ **Armadilha ao testar SSE aqui:** o servidor emite evento **nomeado**
(`order-update`), então `es.onmessage` NUNCA dispara — é preciso
`es.addEventListener('order-update', …)`. Numa primeira tentativa isto quase virou
um "P0: SSE não empurra" falso; o canal estava certo o tempo todo.

**Virada do dia:** o pedido seguinte nasceu como `WEB-260812-…` e a data/slot de
retirada resolveram sozinhos para o novo dia. A dimensão "vira o dia" do §2 passou
sem intervenção.

### Não coberto nesta rodada

Depois das rodadas 2 e 3 sobra pouco, e o que sobra é justamente o que exige
gente ou aparelho:

- **Cartão (Stripe)** e **Pix real** — hoje ambos em `payment_mock`; o que foi
  exercitado é a cascata, não o gateway.
- **Dinheiro na entrega** (troco) e **endereço fora de zona**.
- **Cupom, happy hour e D-1** — o loyalty e as promoções por SKU já apareceram.
- **Lado do operador**: aceitar/recusar de verdade no gestor, "Iniciar preparo",
  bump no KDS. Tudo o que se viu foi o piloto automático avançando sozinho.
- **QA físico**: impressão térmica, som do KDS, PDV no balcão.

## 6. Gate "pode chamar os testadores?"

Mínimo para um alpha honesto (staging, sem dinheiro real):
- [x] Fusão pagamento→acompanhamento no ar e verificada.
- [x] Seed rico aplicado (dados de teste para todas as dimensões).
- [x] Aceite 1 min + prep_start operador no staging.
- [~] Rodar o roteiro §2 uma vez e anotar furos — **1ª rodada feita (§7)**, mas só
      a parte pública; o que fica atrás do login ainda precisa de humano.
- [x] Decidir o pill de dinheiro (§5) — decidido, ver §5.
- [ ] **Orientar o testador a entrar por "Usar outro número"** enquanto o F3
      (ManyChat) não estiver no ar — senão ele manda o código e nada volta (§7).
- [ ] Alinhar com testadores o que é "simulado" (§3) — combinar que Pix é
      "Simular pagamento" enquanto o Efí estiver em sandbox.

Alpha com **pagamento real** adiciona: sair do sandbox Efí + Stripe test→live +
(recomendado) NFC-e, o que já encosta no go-live.

---

## Referências

- [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md) — prontidão de produção.
- [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) — credenciais externas.
- [GO-LIVE-SMS-WHATSAPP-STATUS](GO-LIVE-SMS-WHATSAPP-STATUS.md) — SMS/WhatsApp.
- [PAYMENT-TRACKING-MERGE-PLAN](PAYMENT-TRACKING-MERGE-PLAN.md) — a fusão que
  habilitou este alpha.
