# Primitivos de escolha — inventário e decisões

Medido em 18/09/2026 e revisto em 05/10/2026, varrendo os nove apps de `surfaces/` (o Storefront fica de fora:
não estende esta layer). Este arquivo é a lista de trabalho que sobrou da frente que
criou `UiCheckbox`, `UiRadioGroup`/`UiRadio` e `UiSelect`; ele encolhe, nunca cresce.

**Como ler**: *troca mecânica* é substituir o controle por um primitivo com o mesmo
comportamento. *Decisão* é onde o primitivo não responde sozinho — a tela quer outra
coisa, ou a conversão muda o que o operador vê.

## O que já foi convertido nesta frente

| Arquivo | O quê |
|---|---|
| `operator-kit/app/components/UiCheckboxGroup.vue` | wrapper fino do `UCheckboxGroup`: anatomia, teclado e formulário continuam pertencendo ao Nuxt UI/Reka |
| `operator-kit/app/components/OperatorPushSettings.vue` | categorias de aviso → `UiCheckboxGroup`, variante canônica `card` |
| `operator-kit/app/components/OperatorStationSetup.vue` | escolha do balcão → `UiRadioGroup` |
| `operator-kit/app/components/OperatorPinChange.vue` | dois botões de ícone puro ganharam nome acessível |
| `marketing-nuxt/app/components/FireCampaignPanel.vue` | 2 rádios + grupos de etiquetas, faixas, comportamento e outros públicos |
| `marketing-nuxt/app/components/CampaignForm.vue` | destinos → variante `table`; sinais do produto, etiquetas, faixas e segmentos → grupos canônicos |
| `marketing-nuxt/app/components/MarketingOfferForm.vue` | os 5 `<select multiple>` (produtos, coleções, canais, entrega e segmentos) → grupos canônicos; saiu a dependência de Ctrl/⌘ |
| `marketing-nuxt/app/components/MarketingOfferForm.vue` | listas múltiplas → variante `card`; vigência → `UiDateRangeField` + `UiTimeRangeField`, preservando o payload ISO |
| `marketing-nuxt/app/components/CampaignForm.vue` | modelos e ofertas dinâmicos → `UiSelect`/`USelectMenu` pesquisável |
| `marketing-nuxt/app/components/AnnouncementTemplateForm.vue` | formato do Instagram (rádio) + 2 checkboxes |
| `marketing-nuxt/app/components/AnnouncementCard.vue` | as duas ocorrências do horário ambíguo (rádio) |
| `marketing-nuxt/app/pages/platforms.vue` | **"Modelo aprovado": um cartão por modelo → `UiSelect` com busca** |
| `marketing-nuxt/app/pages/platforms.vue` | número verificado e produto do teste → `UiSelect` com busca |
| `purchase-nuxt/app/components/ReceiptLineSheet.vue` | `MaterialPicker` → `UiSelect` (o picker foi promovido ao kit e apagado) |
| `pos-nuxt/app/components/PosRecentSales.vue` | botão de atualizar ganhou nome acessível |
| `pos-nuxt/app/components/Ui/Switch.vue` → `operator-kit/app/components/UiSwitch.vue` | **o interruptor**: promovido ao kit, 10 consumidores migrados, a cópia do PDV apagada |
| `orders-nuxt/app/pages/feeds.vue` | coleções do feed → `UiCheckboxGroup` |
| `orders-nuxt/app/pages/[ref].vue` · `app/components/DispatchDialog.vue` | equipamentos da entrega e pedidos da mesma saída → variante `table` |

## CheckboxGroup — fronteira depois da revisão

| Caso | Decisão |
|---|---|---|
| Listas nomeadas que respondem à mesma pergunta | `UiCheckboxGroup`. É o caso de destinos, etiquetas, segmentos, canais, coleções e equipamentos. |
| Booleano isolado ou que habilita um campo dependente | `UiCheckbox`. Agrupar “comprou nos últimos + número de dias” separaria o gesto do parâmetro e pioraria a compreensão. |
| Dias da semana | `UiToggleChip`. A grade compacta e posicional é parte do uso; não é uma lista textual genérica. |
| Filtros de lista com aplicação imediata | Chrome de filtro (`UiFilterChip`/`FilterBar`). Não grava um campo de formulário. |
| Seleção de linhas em tabela, carrinho ou checklist operacional | Checkbox da linha, com “marcar todos” e estado indeterminado quando houver. O grupo não deve substituir semântica de tabela. |
| Colunas dentro de menu | `menuitemcheckbox`. Trocar pelo grupo apagaria a semântica e o teclado do menu. |
| Escolha exclusiva | `UiRadioGroup`, não CheckboxGroup, mesmo que a aparência pudesse ser parecida. |
| Horário de entrega ou retirada | Só slots devolvidos pelo servidor. Lista longa/compacta usa `UiSelect`; poucas opções que precisam comparar indisponibilidade e motivo podem permanecer em cartões exclusivos. Nunca `UiTimeField`. |

**Regra consolidada:** o chip deixou de ser a solução padrão para listas curtas. A
anatomia canônica do grupo é a base; `UiToggleChip` só permanece quando a forma compacta
tem função própria. Estado adicional (por exemplo “não publica”) entra no slot de rótulo
do grupo, sem reimplementar checkbox, fieldset ou teclado.

## Os outros apps — decisões da varredura atual

| App | O que não virou CheckboxGroup e por quê |
|---|---|
| **orders-nuxt** | Seleção do catálogo continua sendo seleção de linhas, com “marcar todos” e indeterminado. Ordenação e modo de visualização continuam `menuitemradio`. |
| **production-nuxt** | Mise-en-place é checklist operacional dentro de tabela. Os quatro estados da lista de receitas são filtros imediatos, não valores de formulário. |
| **purchase-nuxt** | “Permitir revenda” é um booleano isolado que abre o campo obrigatório de preço. Agrupá-lo separaria a condição da consequência. |
| **bi-nuxt** | Não há lista de múltipla escolha candidata. Os selects longos são escolhas exclusivas e alguns preservam grupos de opções. |
| **pos-nuxt** | Linhas para mover são seleção de itens com quantidade; opções de produto misturam mínimo/máximo, rádio, checkbox, disponibilidade e preço. A canonização desse editor é WP próprio, não troca mecânica. |
| **kds-nuxt** | Densidade é escolha exclusiva; som é switch. A semântica atual não é de grupo múltiplo. |
| **hub-nuxt** | As categorias de aviso já foram convertidas no componente compartilhado `OperatorPushSettings`. |

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
- **Skeleton não é uma `div` cinza artesanal.** A forma continua pertencendo à tela,
  mas animação, tema e semântica vêm de `UiSkeleton`/`USkeleton`.
- **Splitter não substitui grid.** Ele só entra quando há dois painéis persistentes e
  o operador ganha ao decidir a divisão. O quadro redimensionável do Gestor de Pedidos
  é candidato real; formulários de Marketing e grades que apenas quebram no mobile não são.
