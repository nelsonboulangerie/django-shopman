# Primitivos de escolha — o que falta converter

Medido em 18/09/2026, varrendo os nove apps de `surfaces/` (o Storefront fica de fora:
não estende esta layer). Este arquivo é a lista de trabalho que sobrou da frente que
criou `UiCheckbox`, `UiRadioGroup`/`UiRadio` e `UiSelect`; ele encolhe, nunca cresce.

**Como ler**: *troca mecânica* é substituir o controle por um primitivo com o mesmo
comportamento. *Decisão* é onde o primitivo não responde sozinho — a tela quer outra
coisa, ou a conversão muda o que o operador vê.

## O que já foi convertido nesta frente

| Arquivo | O quê |
|---|---|
| `operator-kit/app/components/OperatorPushSettings.vue` | categorias de aviso → `UiCheckbox` (e o rótulo da lista virou "Dispositivos ativos", regra da casa) |
| `operator-kit/app/components/OperatorStationSetup.vue` | escolha do balcão → `UiRadioGroup` |
| `operator-kit/app/components/OperatorPinChange.vue` | dois botões de ícone puro ganharam nome acessível |
| `marketing-nuxt/app/components/FireCampaignPanel.vue` | 2 rádios + 3 checkboxes |
| `marketing-nuxt/app/components/AnnouncementTemplateForm.vue` | formato do Instagram (rádio) + 2 checkboxes |
| `marketing-nuxt/app/components/AnnouncementCard.vue` | as duas ocorrências do horário ambíguo (rádio) |
| `marketing-nuxt/app/pages/platforms.vue` | **"Modelo aprovado": um cartão por modelo → `UiSelect` com busca** |
| `purchase-nuxt/app/components/ReceiptLineSheet.vue` | `MaterialPicker` → `UiSelect` (o picker foi promovido ao kit e apagado) |
| `pos-nuxt/app/components/PosRecentSales.vue` | botão de atualizar ganhou nome acessível |
| `pos-nuxt/app/components/Ui/Switch.vue` → `operator-kit/app/components/UiSwitch.vue` | **o interruptor**: promovido ao kit, 10 consumidores migrados, a cópia do PDV apagada |

## Marketing — o que ficou

| Arquivo:linha | Controle | Classe |
|---|---|---|
| `app/components/CampaignForm.vue:829` | rádio do horário ambíguo (2 opções) | mecânica — **convertido em PR de seguimento** (o arquivo está sendo reescrito noutra branch) |
| `app/components/CampaignForm.vue:969` | pílula de plataforma com checkbox `sr-only` | decisão (ver abaixo) |
| `app/components/CampaignForm.vue:1017,1029,1044,1175,1186,1250,1275` | 7 checkboxes de público e de publicação | mecânica — **PR de seguimento** |
| `app/components/AnnouncementCard.vue:676` | pílula de plataforma com checkbox `sr-only` | **decisão** |
| `app/components/FireCampaignPanel.vue:299` · `app/pages/platforms.vue:526` | `UiNativeSelect` sobre o catálogo inteiro de produtos | mecânica quando a lista passa de 12 (`UiSelect` decide sozinho) |

**A pílula de plataforma é decisão, não troca.** Ela é um `<label>` com um checkbox
`sr-only` dentro, desenhada como chip e carregando o estado de prontidão da plataforma
("não publica", "não verificada"). Trocar por `UiCheckbox` apagaria o desenho de chip.
A peça certa é um irmão do `UiFilterChip` que fale `aria-pressed`/`aria-checked` — isso
é um primitivo novo (`UiToggleChip`), com três consumidores reais.

## Os outros apps

| App | Checkbox | Rádio | Select longo | Observação |
|---|---|---|---|---|
| **orders-nuxt** | 12 | 0 | 2 | `app/pages/catalog.vue:550` é o **único "marcar todos" verdadeiro do repositório**, e hoje mente: `allSelected` é tudo-ou-nada, então seleção parcial desenha vazio. É o consumidor nomeado do `indeterminate`. `app/components/CatalogBindingReview.vue:70` amarra um anúncio externo ao catálogo LOCAL inteiro num `<select>` nativo — candidato direto ao `UiSelect`. |
| **production-nuxt** | 5 | 0 | 2 | `app/pages/mise-en-place.vue:378` é uma tabela de conferência com `<thead>` e sem "marcar todos" — o melhor candidato NÃO atendido do indeterminado. `app/pages/reports.vue:365` filtra por receita numa lista que cresce. O `IngredientPicker.vue` é um quarto combobox à mão: mesma promoção que o `MaterialPicker` merece, mas ele busca por API, não em lista local. |
| **purchase-nuxt** | 2 | 0 | 1 | `app/pages/index.vue:1533` escolhe insumo entre os ~56 num `<select>` nativo — a MESMA lista de que o `MaterialPicker` fugiu. Troca mecânica para `UiSelect`, e das mais valiosas. |
| **bi-nuxt** | 0 | 0 | 3 | `app/pages/explore.vue:126` tem até 41 opções em dois `optgroup` — o maior select do repositório. `UiSelect` ainda não faz grupo; ou ele ganha `group`, ou o B.I. fica para depois. **Decisão.** |
| **pos-nuxt** | 1 | 0 | 0 | `PosCustomerSearch` e `PosAddressAutocomplete` são comboboxes de BUSCA REMOTA — parentes do `UiSelect`, mas o que eles precisam é de um `UiCombobox` assíncrono. Não force o primitivo de lista local neles. |
| **kds-nuxt** · **hub-nuxt** | 0 | 0 | 0 | nada a fazer |

## O interruptor (`role="switch"`) — FEITO

Eram 10 interruptores vivos e nenhum no kit: 7 montavam o `Ui/Switch.vue` do PDV, e 3
eram o mesmo trilho+polegar reescrito à mão (Marketing e as duas telas do Gestor de
Pedidos). O WP foi feito inteiro numa branch só, que é a única forma que não cria a
duplicação que o `kitOwnership.guardrails` existe para impedir: o componente subiu
para `operator-kit/app/components/UiSwitch.vue`, os 10 consumidores passaram a montá-lo
e a cópia do PDV foi apagada.

**O que a medição achou e a promoção resolveu** — as três cópias já tinham divergido:

- **três tamanhos de trilho** (`h-6 w-11` no PDV, `h-5 w-9` no Marketing e nos feeds,
  `h-4 w-7` na matriz do catálogo). Viraram duas variantes com motivo: `md` (padrão) e
  `sm`, que existe por UMA tela — a matriz produto×superfície, com um interruptor por
  célula.
- **duas cores de trilho desligado** (`bg-input` no PDV, `bg-muted-foreground/30` nos
  outros) → uma só.
- **o alvo de toque do PDV era o próprio trilho: 24 px**, metade dos 44 px que a casa
  exige. Quem já acertava era o Marketing (alvo de 44 px em volta de um trilho menor), e
  foi a ideia dele que virou o primitivo — agora pelo token `--spacing-control`, não por
  `size-11` que cada tela precisava lembrar de escrever.
- o verde de "está no ar" do Gestor de Pedidos virou `tone="success"`, e o cinza da
  linha que está fora por outro motivo (esgotada, pausada acima) virou `tone="muted"`:
  a POSIÇÃO continua ligada e a cor não promete o que a tela não entrega.

O guardrail agora cobra os dois lados: `Switch` entrou em `KIT_OWNED_CHOICE_PRIMITIVES`
(nenhum app volta a ter um `Ui/Switch.vue`) e um teste novo recusa `role="switch"` em
qualquer arquivo de app — que é como as três cópias à mão tinham entrado, sem nome de
arquivo em comum para ninguém procurar.

## Convenções que a varredura confirmou

- **Procure antes de criar.** O select com busca já existia no Compras e quase nasceu
  uma segunda vez aqui. O que existe pronto se promove; só o que não existe se escreve.
- **Botão de ícone puro tem nome.** A varredura achou 4 botões mudos (2 no kit, 1 no
  PDV, 1 que era definição de primitivo e por isso é legítima).
  `tests/guardrails.a11y.test.ts` agora cobra isso nas nove superfícies. A exceção do
  primitivo saiu junto com a promoção do interruptor: ela era a única, e era inerte —
  a regra só cobra botão que tem `<Icon>` dentro, e o interruptor nunca teve ícone.
- **Promoção é de uma vez só.** Copiar a peça para o kit e deixar a original de pé
  produz o estado que o guardrail chama de dívida: duas implementações vivas, uma delas
  destinada a divergir em silêncio. Se a branch não puder rodar a suíte de todos os
  consumidores, ela não é a branch da promoção.
