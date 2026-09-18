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
| `operator-kit/app/components/OperatorPushSettings.vue` | categorias de aviso → `UiCheckbox` (e "Aparelhos ativos" virou "Dispositivos ativos", regra da casa) |
| `operator-kit/app/components/OperatorStationSetup.vue` | escolha do balcão → `UiRadioGroup` |
| `operator-kit/app/components/OperatorPinChange.vue` | dois botões de ícone puro ganharam nome acessível |
| `marketing-nuxt/app/components/FireCampaignPanel.vue` | 2 rádios + 3 checkboxes |
| `marketing-nuxt/app/components/AnnouncementTemplateForm.vue` | formato do Instagram (rádio) + 2 checkboxes |
| `marketing-nuxt/app/components/AnnouncementCard.vue` | as duas ocorrências do horário ambíguo (rádio) |
| `marketing-nuxt/app/pages/platforms.vue` | **"Modelo aprovado": um cartão por modelo → `UiSelect` com busca** |
| `purchase-nuxt/app/components/ReceiptLineSheet.vue` | `MaterialPicker` → `UiSelect` (o picker foi promovido ao kit e apagado) |
| `pos-nuxt/app/components/PosRecentSales.vue` | botão de atualizar ganhou nome acessível |

## Marketing — o que ficou

| Arquivo:linha | Controle | Classe |
|---|---|---|
| `app/components/CampaignForm.vue:829` | rádio do horário ambíguo (2 opções) | mecânica — **convertido em PR de seguimento** (o arquivo está sendo reescrito noutra branch) |
| `app/components/CampaignForm.vue:969` | pílula de plataforma com checkbox `sr-only` | decisão (ver abaixo) |
| `app/components/CampaignForm.vue:1017,1029,1044,1175,1186,1250,1275` | 7 checkboxes de público e de publicação | mecânica — **PR de seguimento** |
| `app/components/AnnouncementCard.vue:676` | pílula de plataforma com checkbox `sr-only` | **decisão** |
| `app/pages/campaigns.vue:547` | liga/desliga da campanha (`role="switch"` à mão) | **decisão** — ver "O interruptor" |
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

## O interruptor (`role="switch"`) — por que ele NÃO nasceu aqui

Há 10 interruptores vivos, e nenhum no kit: 7 montam o `Ui/Switch.vue` do PDV (com 3
suítes de teste presas ao contrato `role="switch"`), e 3 são cópias do mesmo
trilho+botão escritas à mão (`marketing-nuxt/app/pages/campaigns.vue:547`,
`orders-nuxt/app/pages/catalog.vue:754`, `orders-nuxt/app/pages/feeds.vue:144`).

Promover é o certo — mas promover pela METADE (copiar para o kit e deixar a do PDV de
pé) cria exatamente a duplicação que o `kitOwnership.guardrails` existe para impedir.
O WP é um só: subir o `Ui/Switch.vue` do PDV para o kit, migrar os 10 consumidores e
apagar a cópia, numa branch que possa rodar a suíte do PDV inteira.

## Convenções que a varredura confirmou

- **Procure antes de criar.** O select com busca já existia no Compras e quase nasceu
  uma segunda vez aqui. O que existe pronto se promove; só o que não existe se escreve.
- **Botão de ícone puro tem nome.** A varredura achou 4 botões mudos (2 no kit, 1 no
  PDV, 1 que era definição de primitivo e por isso é legítima).
  `tests/guardrails.a11y.test.ts` agora cobra isso nas nove superfícies.
