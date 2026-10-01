# Respostas ao dono: Threads, Concierge × Jev, chá com sabor, controles de data

Turno de 02/10/2026. Base: `origin/main` em `344a6affe`. Cada resposta abre com
três linhas; o detalhe vem embaixo, com caminho e linha.

---

## 1. Threads

**Hoje não há como publicar no Threads, e o token que temos não serve para isso.**
O código é pequeno (o publicador do Instagram é o molde, quase o mesmo desenho de
duas etapas); o processo é grande: app da Meta com o caso de uso Threads,
permissões `threads_basic` e `threads_content_publish`, e revisão da Meta.
Recomendação: deixar para depois do go-live; enquanto isso, o atalho manual do
próprio app do Instagram para compartilhar no Threads.

### O que existe

- Publicador de Instagram e Facebook: um só módulo para os dois,
  `shopman/shop/adapters/marketing_delivery_meta.py` (298 linhas). O Instagram
  cria o contêiner e depois publica (`send_instagram`, linha 44); o Facebook
  publica na Página (`send_facebook`, linha 123). Os arquivos
  `marketing_delivery_instagram.py` e `marketing_delivery_facebook.py` só
  reexportam essas funções.
- A credencial é o token da Página, com os escopos `instagram_content_publish`,
  `pages_manage_posts` e `pages_read_engagement` (`config/settings.py:851`);
  o bloco de configuração é `SHOPMAN_MARKETING_META` (`config/settings.py:854`).
- As plataformas que o Marketing conhece estão em
  `shopman/shop/services/marketing_provider_capabilities.py`: instagram (117),
  facebook (207), google_business (268), whatsapp (370) e tiktok (416, marcado
  `dormant`, linha 418). **Não há Threads.** Busca por `threads.net`,
  `threads_basic`, `threads_content` ou `"threads"` em `shopman`, `config`,
  `packages` e `surfaces/marketing-nuxt/app`: 0 ocorrências.
- O registro dos publicadores liga cada plataforma por um interruptor próprio
  (`config/settings.py:898-916`).

### Opções

| Opção | O que é | Custo | Risco |
|---|---|---|---|
| A. Manual | Ao publicar no Instagram pelo app do celular, marcar "compartilhar no Threads" | Zero código | Depende de alguém lembrar; o Shopman não registra que saiu no Threads |
| B. Publicador próprio | Módulo novo no molde do `marketing_delivery_meta.py` (contêiner + publicação), entrada nova em `marketing_provider_capabilities.py`, bloco e interruptor em `config/settings.py`, testes no padrão dos existentes | Código: estimativa de 1 a 2 dias. Processo na Meta: dias a semanas, fora do nosso controle | A revisão da Meta pode recusar ou pedir vídeo de demonstração. O token do Threads é do usuário do Threads, não da Página: NÃO VERIFICADO aqui, mas a documentação pública da Meta descreve token de longa duração com validade de 60 dias e renovação, diferente do token de Página que não vence; isso exige renovação automática ou o publicador para em silêncio |
| C. Nada | Threads fora da lista | Zero | Nenhum técnico |

O que depende do dono: decidir se Threads entra (opção B) e, se entrar, criar o
app na Meta com a conta dele (credencial e revisão são dele).

---

## 2. Concierge × Jev

**O ManyChat não classifica nada; quem classifica é o nosso `triage.py` (regra local sempre, modelo opcional).**
O comparador manda para o Jev **mensagens reais de clientes, redigidas**, e por isso não rodei: o fornecedor não está aprovado, não há credencial nesta máquina e o gabarito está vazio no alpha.
Nem a linha de base da regra local roda hoje: zero mensagens conferidas (147 propostas, nenhuma rotulada).

### O que sairia da casa

Uma linha: **o texto redigido de mensagens reais de clientes do WhatsApp, uma
chamada por mensagem, junto com a descrição das 12 intenções.**

Prova:

- O gabarito é `MessageIntentSample` com status conferido, e o texto que vai é
  `sample.redacted_text()` (`shopman/storefront/concierge/intent_benchmark.py:98-117`).
  Não há conjunto sintético nem fixture versionada para o comparador.
- O Jev recebe `{"state": {"customer_message": sample.text}, "questions": ...}`
  (`intent_benchmark.py:290-298`).
- O próprio módulo diz que o Jev manda texto de cliente para fora e só entra se
  `typesafe` estiver aprovado (`intent_benchmark.py:18-23`); a trava está em
  `JevContender.__init__` (`intent_benchmark.py:277`, chamando `_require_provider`,
  linhas 124-129).
- Lista aprovada: só `anthropic` por padrão (`config/settings.py:1413-1417`);
  credencial do Jev em `config/settings.py:1404-1406`.

### Por que não rodei (BLOQUEADO, com prova)

1. **Dado de cliente.** O conjunto é de mensagens reais; mandar ao Jev é decisão
   do dono (a regra está escrita em `config/settings.py:1408-1412`).
2. **Fornecedor não aprovado.** `typesafe` fora de
   `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED`.
3. **Sem credencial nesta máquina.** Procurei `JEV_API_KEY` e `typesafe` em
   `~/.config`, `~/.zshrc`, `~/.zprofile`, no `.env` do checkout principal e no
   ambiente da sessão: nenhuma ocorrência. Nenhum valor foi impresso.
4. **Gabarito vazio no alpha.** Contagem feita só de leitura, pela conexão
   direta (porta 25060, banco `shopman`, sessão `default_transaction_read_only=on`),
   sem ler texto de cliente:

   ```
   storefront_messageintentsample por status:  proposed | 147
   intenções ativas:                            12
   amostras conferidas com intenção:            0
   ```

   Com zero conferidas, o comando para com "Gabarito vazio"
   (`shopman/storefront/management/commands/benchmark_intent_classifiers.py:76-81`),
   para qualquer concorrente, inclusive a regra local.

### Achado de passagem

O concorrente `regex` do comparador mede a regra **velha** de 4 causas
(`classify_handoff_request`, `intent_benchmark.py:135-145`), não a regra de 12
intenções que o Concierge usa de fato (`classify_rules`,
`shopman/storefront/concierge/triage.py:175-184`). Quando o gabarito existir, a
linha de base vai subestimar a regra local. Corrigir é trocar a chamada; fica
anotado, não foi feito aqui.

### Onde a triagem acontece

- `shopman/storefront/concierge/service.py:897-916`: toda entrada passa por
  `triage_module.decide(...)` antes do modelo de resposta; o que escala sai para
  a equipe.
- `shopman/storefront/concierge/triage.py:62-76`: a tabela das 12 intenções com
  destino e urgência. O modelo só entra se `triage_with_model` estiver ligado e
  houver `AI_ASSIST_API_KEY` (`triage.py:220-225`).
- Decisão de arquitetura: `docs/decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md`
  (há outro `adr-026`, o de segurança das superfícies; não confundir).

### Para destravar (dono)

1. Conferir amostras no Admin (Clientes, Mensagens: marcar as intenções de cada
   uma). Isso já dá a linha de base local, sem nada sair da casa.
2. Se quiser medir o Jev: pôr `typesafe` em `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED`
   e a chave `JEV_API_KEY` no ambiente onde o comando roda. As duas coisas são
   dele.

---

## 3. Chá com sabor: opções de produto (desenho, não código)

**Hoje cada sabor é um SKU próprio, e o Offerman não tem variante: tem coleção (com coleção-pai), listing por canal, combo e palavra-chave.**
A mais barata é agrupar os SKUs que já existem; a mais completa é um "escolha o sabor" na vitrine que aponta para SKUs distintos, sem mexer em estoque nem nota.
Recomendação: B (escolha de sabor na ficha do produto, cada sabor continua SKU), porque estoque e NFC-e são por SKU e continuam certos.

### O que existe

- Os quatro chás são SKUs separados, mesmo preço e descrição:
  `config/management/commands/seed.py:1874-1881` (CHCAM, CHROU, CHSOP, CHBLU);
  todos na coleção `bebidas-quentes` (`seed.py:3105-3109`).
- O Frappé é o caso inverso: um SKU só com sabor na descrição ("café, chocolate
  ou frutas vermelhas", `seed.py:1883`). Ninguém sabe qual sabor saiu.
- Offerman, o que tem (`packages/offerman/shopman/offerman/models/`):
  - `Collection` com `parent` (coleção-pai, `collection.py:25`) e `rule` para
    coleção dinâmica (`collection.py:51`);
  - `Listing` por canal (`listing.py:16`);
  - combo por composição, `ProductComponent` (`product_component.py:11`): o
    produto com componentes **é** o combo;
  - palavras-chave (`product.py:63`, taggit).
  - **Não tem** variante, grupo de opção nem atributo de sabor. Busca por
    `variant`, `option_group`, `modifier_group`, `flavor` nos pacotes: nada de
    domínio.
- A linha do pedido já carrega observação para a cozinha: o iFood manda
  complementos e eles viram texto nas notas do item, que chegam ao KDS
  (`shopman/shop/services/ifood_orders.py:235-247`; teste
  `shopman/shop/tests/test_ifood_kds_session.py:79`).

### Opções

| Opção | O que muda | Toca | Estimativa | Risco |
|---|---|---|---|---|
| A. Agrupar na vitrine (a mais barata) | Uma coleção-filha "Chás" sob `bebidas-quentes`, com os 4 SKUs | Só dado (Admin ou seed). Para aparecer como bloco na loja e no PDV, a vitrine precisaria ler a coleção-filha: hoje o catálogo da loja agrupa por coleção primária (`shopman/storefront/presentation/catalog.py:257`) e não lê `parent` | Dado: minutos. Vitrine lendo subcoleção: 1 dia | Baixo. Continua sendo quatro cartões; o cliente ainda escolhe entre quatro produtos |
| B. Escolha de sabor apontando para SKUs (recomendada) | Um produto-vitrine "Chá da casa" com "escolha o sabor"; cada escolha põe na sacola o SKU do sabor | Uma chave em `Product.metadata` ou na coleção para declarar o grupo (registrar em `docs/reference/data-schemas.md`), projeção da ficha (`shopman/storefront/presentation/product_detail.py`), tela da ficha no `storefront-nuxt` e seletor no PDV | 3 a 5 dias, loja e PDV | Médio: é tela nova nas duas superfícies. Estoque, preço, NFC-e, KDS e B.I. não mudam, porque o que entra na sacola continua sendo o SKU certo |
| C. Sabor como opção na linha, um SKU só | Um SKU "Chá da casa" e o sabor vai como opção da linha (como o complemento do iFood) | `meta` da linha no Orderman, carrinho, PDV, KDS | 3 a 5 dias | Alto: estoque e NFC-e passam a ver um item só; perde-se o consumo por sabor, a falta de um sabor não pode marcar "Indisponível" só nele, e o B.I. não separa. Só serve se o sabor não tiver estoque próprio (ex.: calda do Frappé) |

Para o Frappé, que hoje é C sem estrutura (sabor só no texto), a escolha é a
mesma: separar em SKUs (A ou B) se cada sabor gasta insumo diferente, ou C se o
dono não precisa saber quanto saiu de cada um.

O que depende do dono: escolher A, B ou C; e dizer se o Frappé segue um SKU só.

---

## 4. Controles de data: inventário (sem conserto)

**Confirmado: 14 campos de data em 11 arquivos, nenhum componente compartilhado; todos são o seletor nativo do navegador (`type="date"`).**
Metade usa o `UiInput` de cada app (cópia idêntica em seis apps, não vem do `operator-kit`); a outra metade é `<input>` cru com classe copiada.
Padronizar primeiro: o trio do PDV (agendar, reagendar, Encomendas), porque é balcão, é dia de go-live e já está quase igual; esperar o #1353 entrar.

### Tabela

Linha = a linha do `type="date"` em `origin/main` `344a6affe`.

| App | Arquivo:linha | Tipo | Uso |
|---|---|---|---|
| PDV | `surfaces/pos-nuxt/app/components/PosScheduleModal.vue:124` | `UiInput` nativo, com `min` hoje e `max` | Dia da encomenda no balcão |
| PDV | `surfaces/pos-nuxt/app/components/PosPreorderRescheduleDialog.vue:119` | `UiInput` nativo, com `min`, **sem `max`** | Mudar o dia de uma encomenda |
| PDV | `surfaces/pos-nuxt/app/pages/preorders/index.vue:308` | `UiInput` nativo, ao lado das setas anterior/próximo | Navegar o calendário de Encomendas (o #1353, na fila, mexe neste arquivo: o campo fica, a linha anda) |
| Produção | `surfaces/production-nuxt/app/pages/board.vue:156` | `<input>` cru | Dia do quadro de produção |
| Produção | `surfaces/production-nuxt/app/pages/expedite.vue:526` | `<input>` cru | Dia dos lotes na expedição |
| Produção | `surfaces/production-nuxt/app/components/ProductionStageGrid.vue:628` | `<input>` cru | Dia da grade de etapas |
| Produção | `surfaces/production-nuxt/app/pages/reports.vue:347` e `:357` | `UiInput` nativo, par de/até | Filtro de relatório |
| B.I. | `surfaces/bi-nuxt/app/components/BiTopBar.vue:116` e `:124` | `<input>` cru, par de/até | Período personalizado |
| B.I. | `surfaces/bi-nuxt/app/pages/forecast.vue:75` | `<input>` cru | Dia da projeção |
| Marketing | `surfaces/marketing-nuxt/app/components/CampaignForm.vue:1048` e `:1062` | `UiInput` nativo, par início/fim | Período da campanha |
| Compras | `surfaces/purchase-nuxt/app/components/ReceiptLineSheet.vue:251` | `<input>` cru (o app não tem `UiInput`) | Validade do lote no recebimento |

As linhas que o pedido citou (`:307`, `:122`, `:117`, `:154`, `:524`, `:626`,
`:345,355`, `:114,122`, `:73`, `:1045,1059`) apontam para a abertura da tag;
o `type="date"` está duas linhas abaixo. Mesmo campo. Uma correção: o
`preorders/index.vue` é do PDV (`pos-nuxt`), não do Gestor de pedidos.

`UiInput` idêntico em `bi`, `kds`, `marketing`, `orders`, `pos` e `production`
(mesmo md5 `cea3ac67…`); o `operator-kit` não tem campo de data nem `UiInput`.

### Fora da contagem (para não esquecer)

- Data e hora: `datetime-local` no Marketing (`AnnouncementCard.vue:917`,
  `CampaignForm.vue:933`, `MarketingOfferForm.vue:256,268`,
  `GoogleBusinessPostOptions.vue:104,118`) e `time` em `CampaignForm.vue:1005`.
- Calendário próprio de intervalo no Gestor de pedidos:
  `surfaces/orders-nuxt/app/components/ChannelPeriodCalendar.vue` (feito à mão
  porque o nativo não mostra o intervalo; horas em `:75` e `:82`).
- Loja (voz própria, fora das superfícies de operador): `Ui/Datepicker.vue`
  (v-calendar) e aniversário em `pages/conta/perfil.vue:260`.

### Qual padronizar primeiro

**O trio do PDV.** Critérios:

1. Uso no balcão: é a única tela de data que o atendente usa com cliente na
   frente (agendar e reagendar encomenda).
2. Go-live: encomenda paga antes é fluxo do dia um.
3. Risco baixo: os três já usam o mesmo `UiInput` e a mesma regra (dia a partir
   de hoje). A diferença concreta é que agendar tem limite máximo e reagendar
   não (`PosScheduleModal.vue:126` × `PosPreorderRescheduleDialog.vue:120`):
   hoje dá para reagendar para além do horizonte que o agendamento aceita.
   Alinhar isso não exige primitiva nova.
4. Ordem: esperar o #1353 (na fila) entrar, porque ele mexe em
   `preorders/index.vue`.

Depois, a Produção (três `<input>` crus fazendo a mesma coisa, "escolher o dia"),
e por último B.I., Marketing e Compras, que são telas de gestor.
