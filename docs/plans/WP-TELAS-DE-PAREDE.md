# WP — Telas de parede

> **Nome do arquivo:** `WP-TELAS-DE-PAREDE.md` segue a família `WP-<TEMA-EM-PT>` dos 20
> work packages mais recentes (`WP-ATRIBUTOS-DE-PRODUTO`, `WP-FICHA-DE-PRODUTO-E-PROMESSA`,
> `WP-PAGAMENTO-LINK-E-TEF`), e não a família `ALGO-PLAN`, que nomeia plano de domínio —
> isto é um WP de exploração com fases, não o plano de um domínio.

**Status:** exploração · nada implementado · nenhuma linha de produto muda neste PR
**Decisões do dono:** as cinco de 18/09/2026 estão tomadas e refletidas — ver §10.
**Data:** 18/09/2026
**Medições:** feitas no `HEAD` `6eac85499` (origin/main de 18/09/2026). Número aqui é
número medido; quando envelhecer, remeça — não deduza.
**Origem:** pedido do dono, 18/09/2026 — *"uma seção Telas é ótimo. Só faça isso de forma
que não se torne uma bela gambiarra. Aproveite para reorganizar alguns conceitos que
estavam meio dispersos cross-system."*

---

## 0. O resumo, para quem lê só isto

A casa tem **cinco superfícies passivas**, e as quatro que são telas de parede de
verdade nasceram **cada uma por conta própria**, em três apps diferentes e em duas
tecnologias diferentes. Cada uma resolveu bem os mesmos cinco problemas —
leitura a distância, fundo escuro, tela cheia, sem senha na parede, manter o último
quadro quando o sinal cai — e resolveu **sozinha**. Não há nada errado com nenhuma
delas isoladamente. É exatamente por isso que o risco que o dono nomeou é real: quatro
gambiarras bonitas continuam sendo quatro gambiarras.

E a mais madura das cinco é **a que ninguém lista**: o menuboard do Django, que é a
única com modelo de confiança de dispositivo, SSE travado, pintura no servidor que
falha aberta e rotação configurável por operador. Ela não é candidata a entrar na
seção; ela é a **implementação de referência** que as outras três deveriam imitar.

**As cinco decisões do dono já estão tomadas** (18/09) e incorporadas: a seção se chama
**"Telas"**; **nenhum 301** — zero resíduo, sem legado; o **letreiro ganha SSE** e sobe de
prioridade; a tabela nova é **`Screen`, em `shopman/shop/models/`**; e a confiança de
dispositivo de tela é **eterna**, o que move o peso para a revogação (§10).

As três respostas, em uma linha cada:

1. **A seção "Telas" NÃO tem domínio próprio.** A [ADR-018](../decisions/adr-018-surface-is-channel-with-commerce-policy.md)
   já decidiu que superfície de exibição é `Channel` com `commerce_policy=display`. Tela
   é **capability de rota + seção do Hub + sujeito de confiança de dispositivo**. Zero
   model novo, zero migração.
2. **As TVs dos Feeds/Canais do Catálogo entram — e são o centro da seção, não um
   apêndice.** Com uma fronteira: o **feed XML não entra**. Feed é lido por robô; tela é
   lida por gente. Hoje os dois estão sob o mesmo título "Feeds e telas", e essa é
   precisamente a colisão a desfazer.
3. **`board` sai inteiro do vocabulário de tela** e fica só como sufixo de read-model no
   backend, onde já é maioria. `painel` passa a significar *dashboard*, nunca parede.
   `tela`/`screen` — hoje vocabulário livre — passa a nomear a categoria.

**Custo em DigitalOcean: zero componente novo.** As nove superfícies Nuxt já rodam em
dois serviços (`operator-floor`, `operator-office`); toda tela é rota dentro de app que
já existe, e o menuboard segue no `web`. Este WP **não propõe** app Nuxt novo.

**E uma quarta resposta, que veio depois** (restrição do dono, 18/09): nenhuma URL da
casa cabe num controle remoto de TV. A saída **não é encurtador** — é **pareamento por
código** (§9): a TV abre um endereço único e fixo, mostra um código de 6 caracteres, e o
operador escolhe pelo Hub o que aquela tela mostra. O `doorman` já tem a peça inteira
(`TrustedDevice.SubjectType.DISPLAY` + a mecânica de código curto do `link_state`), então
**nenhuma primitiva nova** — mas **uma** tabela fina (`Screen`), e a §9.5 diz por quê.

---

## 1. O inventário medido

Cinco superfícies. Quatro são telas de parede; a quinta é fronteira e fica de fora, com
o motivo registrado.

### 1.1 Cardápio na parede — `/menuboard/<ref>/` · Django (`web`)

A que faltava na lista, e a mais madura de todas.

| | |
|---|---|
| **Quem lê** | **Cliente.** Seção, nome, preço, "esgotado" riscado. Zero informação operacional. O módulo diz: *"uma TV na parede da loja"*. |
| **Dado** | `build_menuboard(ref)` embutido no HTML no load + `GET /menuboard/<ref>/data/` a cada evento + poll de 30 s. SSE em `/menuboard/<ref>/events/`, canal `stock-catalog`. Preço **não** vem de `Product.base_price_q`: vem do canal em `display.prices_from` (o PDV). |
| **Como se chega** | URL direta na TV. Link humano no Gestor, em `/feeds` (`output_path` montado em `backstage/projections/feeds.py:37`). |
| **Se a sessão cair** | **A TV não se abala.** Ela carrega cookie `TrustedDevice` (`subject_type="display"`), gravado por `ensure_display_trust()` na primeira abertura logada. Sessão de staff caindo não derruba a parede. Sem o cookie: **403 com texto explicativo**, nunca formulário de login. |
| **É pública?** | **Não**, e foi fechada de propósito (ADR-018 §5.1). Escotilha `SHOPMAN_MENUBOARD_PUBLIC`, default `false`. O `/feed/<ref>.xml` ao lado **continua público**, de propósito. |
| **Quem configura** | `Channel` com `commerce_policy=DISPLAY` + `config.display` (`format`, `collections`, `prices_from`, `paused_skus`, `rotate_seconds`, `items_per_page`). Editado em `orders-nuxt` `/feeds` (perm `shop.manage_catalog`). Seed cria `tv-1` "TV do Café" e `tv-2` "TV do Salão". |

Envelope que ela já tem, e as outras não: rotação **paginada no servidor**, dark
hard-coded, JS externo por causa de CSP, e **falha aberta** — sem JS, o servidor já
pintou o cardápio inteiro.

### 1.2 Chamada de retirada — `/pickup` · `kds-nuxt` (:3003)

| | |
|---|---|
| **Quem lê** | **Cliente, exclusivamente.** Código do pedido grande, "pronto" em verde, relógio. Nenhum dado de cozinha. |
| **Dado** | `useKdsCustomerBoard()` → `GET /api/v1/backstage/kds/pickup/` (poll 10 s) + SSE pelo BFF. O cue de tempo real é **honesto**: verde só no `onopen`; senão, "atualiza sozinho". |
| **Como se chega** | **URL digitada. Não há link nenhum na UI** — o rail do KDS só tem "Estações". Aliases `/cliente` e `/retirada` dão 301. |
| **Se a sessão cair** | **Continua renderizando** — por exceção no shell: `app.vue:17` calcula `isCustomerBoard` e os overlays levam `&& !isCustomerBoard`. |
| **É pública?** | **Sim, de verdade**: `backstage/api/kds.py:214` → `permission_classes = []`, docstring *"Public read-only endpoint for the pickup display."* |
| **Quem configura** | **Nada.** Sem tela de admin, sem `Channel`, sem env var. É a única das quatro sem dono de configuração. |

⚠️ **O app inteiro é kiosk por causa dela**: `kds-nuxt/nuxt.config.ts` declara
`display: "fullscreen"`, `wakeLock: true`, `kiosk: true`, `idleReloadPaths: ["*"]` —
para o app da **cozinha**, cujas outras telas são tocadas o tempo todo. É o sintoma
mais claro do defeito estrutural da §4.

### 1.3 Letreiro de fornadas — `/board` · `production-nuxt` (:3005)

| | |
|---|---|
| **Quem lê** | **Equipe.** Nome do produto, quantidade em UN, horário, atraso. Agenda de fornadas, não vitrine. |
| **Dado** | `useProductionForecast()` → `GET /api/v1/backstage/production/forecast/`, poll adaptativo de 30 s. Sem SSE. |
| **Como se chega** | Item **"Letreiro"** no `OperatorRail` (`app.vue:71`). É a única das quatro com entrada visível na UI. Atalho PWA "Fornadas"; alias `/painel` → 301. |
| **Se a sessão cair** | **Mantém o último quadro no ar** em falha de rede (*"dado velho visível > tela em branco"*). Mas **401/403 reais caem no gate**: `OperatorLogin` cobre `/board`. Em estação `AUTONOMOUS`, o cookie de `TrustedDevice` resolve sem PIN. |
| **É pública?** | **Não**: `HasProductionCapability`, `can_access_board`. |
| **Quem configura** | `Terminal` marcado `AUTONOMOUS` no Admin + a conta de operador dele. |

Envelope próprio: `useKioskMode()` (botão de tela cheia), `useBoardPages` (rotação de
12 s), re-giro das palhetas a cada 25 s, som de flap, roll de dia à meia-noite.

### 1.4 Tela do cliente do balcão — `/display` · `pos-nuxt` (:3002)

| | |
|---|---|
| **Quem lê** | **Cliente.** Itens sendo cobrados, total, QR do Pix. *"transparência de preço em primeiro lugar"*. |
| **Dado** | **Nenhum servidor.** `BroadcastChannel` `"pos-customer-display"`, publicado pela janela de venda. O shell é taxativo: *"NUNCA abre SSE nem poll: não há leitor para o refetch"*. |
| **Como se chega** | A estação abre: `window.open("/display", …)` a partir do `PosFunctionRail`. Segundo monitor do balcão. |
| **Se a sessão cair** | **Nada acontece.** É a única **imune por arquitetura**: o shell é escolhido antes de qualquer fetch e não monta composable de operador nenhum — *"formulário de login na parede não identifica ninguém."* |
| **É pública?** | Não se aplica: não há rota de BFF nem endpoint. |
| **Quem configura** | Só o gesto do operador. `definePageMeta({ operatorActivity: false })` e exclusão deliberada de `idleReloadPaths`. |

⚠️ **A armadilha já cobrada em produção:** a comparação era `route.path === "/display"`,
e `/display/` **com barra** escapava, subindo o shell de operador — a parede pedindo
senha, vista pelo dono em 10/09. Hoje casa por `route.name`, com teste que prende
(`tests/components/PosShell.test.ts:85`). É o melhor argumento existente para a §4: a
categoria precisa ser **declarada**, não **inferida de string de rota**.

### 1.5 Fronteira, registrada e descartada — seletor de estações do KDS (`/`)

Escrito em gramática de parede (dark, leitura a distância), roda no kiosk fullscreen do
KDS — mas **alguém toca** para escolher a estação, e fica atrás do `OperatorLogin`. É
tela de operador. Registro porque o vocabulário visual engana.

Descartadas com motivo: `pos/tickets.vue` ("painel de parede" ali é **cortiça física**),
`kds/[ref].vue` (gestos de check/despacho), `production/expedite.vue` (fechamento de
fornada com partição QC), `orders/feeds.vue` (é o **configurador** das telas, não uma
tela), `/feed/<ref>.xml` (público de propósito, mas é XML para robô — ninguém olha), e
todo `admin_console/**` (interativo; **nenhum** template Django de parede além do
menuboard).

### 1.6 O que o inventário prova

**Quatro telas, quatro envelopes incompatíveis de "a sessão caiu":**

| Padrão | Telas | Como |
|---|---|---|
| Imune por **arquitetura** | `/display` | shell escolhido antes de qualquer fetch |
| Imune por **exceção no shell** | `/pickup` | `&& !isCustomerBoard` nos overlays — uma exceção esquecida põe login na parede |
| Dentro do gate, imune por **cookie de dispositivo** | `/board`, `/menuboard` | `TrustedDevice` resolve sem PIN |

E uma medição que resume tudo: **`operatorActivity: false` existe em exatamente um
lugar no repositório inteiro** — `pos-nuxt/app/pages/display.vue:18`. `/board` conta
como atividade de operador mesmo sem ninguém na frente dela.

---

## 2. O que É uma tela

### 2.1 A definição

> Uma **tela** é uma superfície que **anuncia**: ela é lida a distância, por alguém que
> não a pediu, e ninguém a toca. Ela não tem tarefa, não tem próximo passo e não tem
> erro que o leitor possa corrigir.

Cinco invariantes. Falhou um, não é tela:

1. **Ninguém toca.** Sem tarefa, sem formulário, sem destino. Se há um gesto de uso, é
   app de operador — ou totem, que o framework de omotenashi já trata como linha
   separada, justamente porque é tocado.
2. **Fica ligada indefinidamente.** Sem fim de sessão, sem trava por ociosidade, sem
   expirar. Ociosidade é o **estado normal** dela, não sinal de abandono.
3. **É lida a distância.** Tipografia de painel, contraste alto, uma hierarquia só.
4. **Falha mostrando, nunca perguntando.** Sinal caiu → último quadro no ar com aviso
   discreto. **Nunca** formulário de login, nunca tela em branco, nunca modal.
5. **Não tem sessão de pessoa — mas tem identidade de dispositivo.**

### 2.2 A hipótese do dono, confirmada em quatro pontos e corrigida no quinto

O dono propôs: *"uma tela não tem sessão, não tem trava por ociosidade, não tem gesto de
entrada, fica ligada indefinidamente e é lida a distância. Se isso for verdade, é uma
capability, não um app."*

**Confirmado:** sem trava por ociosidade, ligada indefinidamente, lida a distância, e
**é capability, não app** — a §3 responde por quê.

**Corrigido, e o código já pagou por isso:** *"não tem sessão"* está certo sobre
**pessoa** e errado sobre **credencial**. O menuboard aprendeu isto do jeito caro, e o
`menuboard_access.py` registra o motivo, que não é higiene:

> `display.prices_from` do menuboard aponta para o PDV […]. No dia em que o
> renderizador passar a ler esse ponteiro, um menuboard aberto **publica uma segunda
> tabela de preços** a quem tiver a URL. No Brasil, publicidade suficientemente precisa
> vincula o fornecedor: preço alcançável publicamente é preço a honrar.

Uma tela que anuncia preço é **publicidade**. Ela precisa de credencial — só que de
**dispositivo**, não de pessoa. E *"não tem gesto de entrada"* fica mais preciso assim:

> **O gesto de entrada acontece uma vez, na instalação, e nunca mais.** Um operador
> logado abre a tela na TV; aquela abertura autoriza aquele dispositivo
> (`ensure_display_trust`). Depois disso a parede não pede nada, para sempre, até
> alguém revogar no Admin.

Isso é omotenashi de manual: o esforço existe, acontece uma vez, e fica escondido do
leitor para sempre.

### 2.3 Por que a categoria já existia — na filosofia, não no código

`docs/omotenashi.md` já traz a linha **"Sinalização"** no Mapa de Superfícies ×
Portões — *"Informação no lugar certo, no momento certo, **legível a distância**"* — e
já lista `menuboard` no extremo **Autônomo** do Espectro de Superfícies, com a regra de
ouro: *"quanto mais automatizada a superfície, mais o omotenashi precisa estar embutido
no design. O garçom pode improvisar. O totem não pode."*

A tela de parede é o caso extremo do extremo: o totem ao menos recebe um toque e pode
reagir. A parede não recebe nada. **Todo o cuidado tem que estar embutido antes.** A
categoria não é invenção deste WP; ela está na filosofia da casa desde sempre e nunca
teve endereço no código.

---

## 3. Resposta 1 — a seção "Telas" NÃO tem domínio próprio

**Recomendação: não criar domínio, não criar model, não criar migração.**

Três razões, em ordem de força.

**(a) A decisão já foi tomada, e está implementada.** A
[ADR-018](../decisions/adr-018-surface-is-channel-with-commerce-policy.md) matou o model
`Showcase` e colapsou superfície em `Channel`, discriminada por `commerce_policy`:

> O discriminador é a **política comercial**: não *o que a superfície é*, mas *até onde a
> interação comercial vai nela*.

Criar um domínio `Telas` reabriria exatamente o que a ADR-018 fechou — e produziria a
terceira maquinaria para "o que esta superfície mostra e a que preço", que é o erro que
a ADR-011 nomeou ao recusar `FormulaPlan`.

**(b) Tela não tem pergunta canônica própria.** Pela constituição §8.3 ("isto é core do
domínio? plugin do domínio? conveniência de framework?"), uma tela não responde nada que
já não seja de outro: o que está à venda e a que preço é do `offerman`; o que sai do
forno e quando é do `craftsman`; de quem é o pedido que ficou pronto é do `orderman`;
quanto está sendo cobrado agora é do `payman`. **Uma tela re-apresenta respostas; ela não
tem resposta própria.** Entidade sem pergunta canônica é conveniência de framework — e
§8.3 diz que não entra.

**(c) O read model já unificou.** A projection da matriz de catálogo tem **um** eixo,
`surfaces`, e concatena canais e feeds na mesma lista. Um domínio novo repartiria o que
já está inteiro.

### O que "Telas" É, então — três peças, nenhuma delas um domínio

| Peça | Onde vive | O que faz |
|---|---|---|
| **Capability de rota** | `operator-kit`, opt-in (ADR-026) | o envelope técnico da §6 |
| **Seção do Hub** | `backstage/projections/hub.py` | o caminho de descoberta da §7 |
| **Sujeito de confiança** | `doorman`, `subject_type="display"` | a credencial de dispositivo, já genérica |

E uma linha de dado, que já existe: a tela que anuncia catálogo **já é** `Channel` com
`commerce_policy=display`. As outras três não precisam de linha nenhuma — `/pickup`,
`/board` e `/display` não anunciam oferta, logo não são canal, logo não têm o que
configurar além do dispositivo confiável.

⚠️ **Uma ressalva, e ela é do pareamento, não da categoria.** "Nenhum model novo" vale
para a **categoria**: tela não introduz conceito de negócio nenhum. Mas o pareamento que
o dono pediu (§9) exige **uma** tabela fina — `Screen` —, porque alguém tem que saber
*qual TV é esta e o que ela está mostrando agora*, e hoje ninguém sabe. É registro de
dispositivo, irmão do `Terminal` do `cashman`, não domínio. O conteúdo continua sendo
`Channel`. A §9.5 paga essa conta por extenso, em vez de escondê-la.

⚠️ **Pendência de higiene encontrada:** a ADR-018 está com **status "Proposto"** enquanto
o código dela está no ar (`Showcase` não existe mais, `commerce_policy` é coluna
indexada, `prices_from` é lido). Virar "Aceito" com a evidência é item da Fase 0.

---

## 4. O defeito estrutural — o envelope é declarado por APP, e a categoria é por ROTA

Esta é a razão técnica de a coisa ter virado quatro gambiarras, e ela é medível.

O `operator-kit` **já tem** capability de kiosk, e ela é opt-in, como a ADR-026 exige.
Só que ela é declarada **no `nuxt.config.ts` do app inteiro**
(`OperatorPwaCapabilityOptions`): `display: "fullscreen"`, `wakeLock`, `kiosk`,
`idleReloadPaths`.

**Consequência 1 — o app da cozinha inteiro virou kiosk fullscreen por causa de uma
rota.** `kds-nuxt` declara `kiosk: true` e `idleReloadPaths: ["*"]` porque `/pickup`
precisa; herdaram isso as telas de estação, que são tocadas o tempo todo.

**Consequência 2 — a Produção teve que estreitar de volta na mão.**
`idleReloadPaths: ["/board"]` existe para desfazer, por caminho, o que foi declarado por
app. O próprio comentário da capability admite a tensão: *"Kiosk exige a lista: um painel
de parede que ninguém fecha nunca trocaria de versão sem ela."*

**Consequência 3 — a única declaração que já é por rota está sozinha.**
`operatorActivity: false` é `definePageMeta` — granularidade certa — e existe em **um**
arquivo no repositório.

**Conclusão:** a casa já começou a escrever a declaração certa e parou no primeiro caso.
A tela é uma **rota**, não um app. O envelope tem que descer do `nuxt.config.ts` para o
`definePageMeta`. E isso confirma a hipótese do dono pelo caminho técnico: se fosse app,
`kds-nuxt` seria dois apps; como é rota, é capability.

---

## 5. Resposta 3 — a nomenclatura

### 5.1 O censo da colisão

Medido no `HEAD`. O dono suspeitava de três sentidos para `board`; são **cinco**.

| Palavra | Sentidos | Gravidade |
|---|---|---|
| **board** | 5 — sufixo de read-model (`KDSBoardProjection`, `ProductionBoardProjection`, `PurchaseBoardView`, `CampaignBoardProjection`, `FeedBoardProjection`); TV Solari; TV de cardápio; painel de retirada; **grade de comandas** (`PosTabBoard`) | **crítica** |
| **display** | 4 — rota do PDV; `commerce_policy`; capability de feed; `display_order` | alta |
| **painel** | 2 — aba dashboard (Marketing, Compras) **e** TV de parede, nas mesmas barras de navegação | alta |
| **"Tela do cliente"** | 2 — o monitor do PDV **e** o `/pickup` do KDS, com o mesmo nome em pt-BR | alta |
| **canal** | 4 — canal de venda; canal de exibição; canal de SSE; canal de comunicação (`ConsentChannel`) | média |
| **feed** | gênero + espécie (um menuboard **é** um Feed, e `feed` também é uma das duas espécies) | média, já admitida no código |
| **kiosk** | 3 — modo de interação; categoria de superfície; estação física que age | média |
| **tela / screen** | — | **livre** |

A linha mais afiada do censo, em `marketing-nuxt/app/components/CampaignTopBar.vue:21`:
`{ to: "/", key: "board", label: "Painel", … }` — rota `/`, chave `board`, rótulo
`Painel`, e a coisa é um **dashboard**. Três vocabulários errados no mesmo objeto
literal.

E `quadro` colide consigo mesmo: é *"quadro-negro numa TV"* no menuboard e **quadro de
vídeo** em `board.vue:25` (*"mantém o último quadro no ar"*).

### 5.2 A proposta — cada palavra com um dono

O princípio já existe na casa, no `SURFACE-OFFER-CAMPAIGN-PLAN` §10: **"política é
gênero, rota é espécie"**, e *"rotas nomeiam o artefato, nunca o acesso"*. A proposta
apenas o estende.

| Palavra | Passa a significar, e só isso | Por quê |
|---|---|---|
| **tela** (pt-BR) / **`screen`** (identificador) | **A categoria.** Superfície anunciante, lida a distância, não tocada. | Vocabulário livre hoje — a única palavra do conjunto que não precisa desalojar ninguém. |
| **`board`** | **Sufixo de read-model no backend**, e nada mais. Sai por inteiro do vocabulário de superfície. | É a maioria dos usos (6+ nomes de projection/view) e é palavra de *backend*, não de tela. Cortar aqui é o corte mais barato: **nenhum rename de backend**. |
| **painel** | **Dashboard** — a aba inicial de um app de operador. Nunca parede. | Marketing e Compras já o usam assim; só a Produção diverge, e o rail dela **já diz "Letreiro"**. A casa já convergiu; a documentação é que ficou para trás. |
| **letreiro** | **A tela de fornadas**, o Solari. | Já é o rótulo vivo no rail da Produção. O `CLAUDE.md` e o `docs/status.md` ainda dizem "kiosk Solari" — `Solari` é **estilo de renderização**, não nome de superfície. |
| **`display`** | **Política comercial** (`commerce_policy=display`) e **confiança de dispositivo** (`subject_type="display"`). Nunca rota, nunca nome de tela. | A ADR-018 já o consagrou como gênero. Rota é espécie. Nos dois lugares do Core ele é **atributo**, não coisa — ver §10.2. |
| **`Screen`** | **A coisa**: o painel físico pareado, na parede. É a tabela da §9.5. | Não colide com `display`: `display` é papel, `Screen` é objeto. *Um `Screen` é um dispositivo confiável de sujeito `display`, ligado a um `Channel` com `commerce_policy=display`.* Há camada, não colisão (§10.2). |
| **`menuboard`** | **Exceção nomeada e mantida.** A rota do cardápio na parede. | É palavra do ramo, é rota estabelecida, e o §10 manda a rota nomear o artefato. Contém "board" e sobrevive **porque é um nome próprio**, não o substantivo `board`. |
| **kiosk** | **Modo de interação**: tela cheia, sem senha, sem chrome. | Não é a categoria (isso é `screen`) e não é a estação que age (isso é `station`/`Terminal`). |
| **feed** | **Saída para robô** — o XML que Google e Meta buscam. Nunca uma TV. | Fecha a colisão gênero/espécie: o gênero passa a ser *canal de exibição*; as espécies são `menuboard` e `feed`. |

### 5.3 O de-para do que existe hoje

Este WP **não renomeia nada**. A tabela é a proposta que a Fase 2 executa.

| Hoje | Proposta | Motivo |
|---|---|---|
| rota `/board` (Produção) | `/marquee` | `board` sai do vocabulário de superfície; `letreiro` → `marquee` é o termo EN do artefato |
| rótulo "Painel" → Solari (docs, `CLAUDE.md`) | "Letreiro" | `painel` = dashboard; o rail já diz Letreiro |
| rota `/display` (PDV) | `/customer` | `display` deixa de ser rota |
| `useKdsCustomerBoard` | `useCustomerPickupScreen` | `board` sai; `screen` entra |
| `PosTabBoard` / `presentation/tabBoard.ts` | `PosTabGrid` / `tabGrid.ts` | é grade de comandas, não board nem tela |
| `aria-label="Tela do cliente"` no KDS (`[ref].vue:357`) | "Chamada de retirada" | "Tela do cliente" fica sendo **uma** coisa: o monitor do PDV |
| título `<h2>Feeds e telas</h2>` em `/feeds` | dois blocos: **"Telas"** e **"Feeds"** | é a colisão D7 na tela; ver §8 |
| `"kiosk Solari"` em `CLAUDE.md:189`, `docs/status.md:25` | "letreiro de fornadas" | `Solari` é estilo, não superfície |
| docstring de `views/menuboard.py:2`: *"a superfície DISPLAY **pública**"* | "superfície interna" | **está errada hoje** — o parágrafo seguinte já diz "interna" |
| docstring de `menuboard_access.py`: *"No dia em que o renderizador passar a ler esse ponteiro"* | prosa de fato consumado | **está errada hoje** — `prices_from` já é lido (`test_board_shows_the_price_of_the_channel_it_points_at` passa) |

⛔ **Zero resíduo, decidido.** A versão anterior ressalvava que `/board` e `/display`
tocam bookmark de TV na parede e recomendava 301. **O dono revogou** (§10, decisão 2):
*"o sistema é novo e não devemos legado a nada ainda"*. A rota antiga some — sem alias,
sem redirect, sem passo de compatibilidade.

### 5.4 A regra de URL que não estava escrita

O censo achou uma regra viva e **não documentada**: URL de operador é em inglês; URL do
storefront é em português (`/sacola`, `/conta/*`, `/entrar`, `/finalizar`). Isso está
escrito em **um** lugar: um comentário inline em `pos-nuxt/app/pages/display.vue:7`. O
`CLAUDE.md` diz "URL é em inglês. Ponto." sem a ressalva. Promover essa regra ao
`CLAUDE.md` é item da Fase 0 — barato, e evita que a próxima varredura "corrija" o
storefront.

---

## 6. Resposta à voz, e o envelope técnico

### 6.1 A voz segue o leitor, não o app onde o código mora — confirmado

A hipótese do dono está certa, e o código já a obedece sem ter a regra escrita:
`/pickup` mora no app da **cozinha** e fala com o cliente (*"aqui é chrome neutro, copy
acolhedor"*, *"Nunca mente pro cliente"*); o letreiro mora na Produção e fala com a
equipe (UN, atraso, SKU fora).

> **A regra:** a voz de uma tela é a do **leitor**, nunca a do app que a hospeda. Tela
> lida por cliente segue a voz da loja; tela lida por equipe segue a voz de operador. O
> diretório é acidente de hospedagem.

Consequência concreta e verificável: a trava de vocabulário
(`test_vocabulario_de_tela.py`) isenta o storefront *"por concessão explícita do dono —
é superfície de cliente final, com voz própria"*. Pela regra acima, **`/pickup` e o
menuboard pertencem à mesma isenção** — são voz de cliente hospedada em app de operador.
Hoje a isenção é por **diretório**, e portanto não os alcança. A Fase 2 troca o critério
de diretório por **leitor declarado**.

### 6.2 Onde o envelope mora — duas metades, e só uma é do kit

A hipótese do dono era `operator-kit`. Está certa para **metade**, e a outra metade já
existe em outro lugar — melhor implementada do que qualquer coisa que o kit teria.

**Metade A — autorização. Já existe, já é genérica, e é do Django.**

`TrustedDevice(subject_type, subject_id)` do `doorman` é totalmente genérico
(`active_for`, `revoke_all_for`, checagem do par tipo+id, cookie HttpOnly, `label`,
`ip_address`, `last_used_at`, revogável por dispositivo no Admin). O menuboard já o usa
com `subject_type="display"` e `subject_id=<ref do quadro>`, com testes que provam o
isolamento (`test_trust_of_another_board_does_not_open_this_one`,
`test_revoking_the_device_closes_the_board`).

**Não se constrói nada aqui. Generaliza-se o uso** de "menuboard" para "qualquer tela",
com `subject_id` = ref da tela. E a alternativa já foi descartada com motivo registrado —
token assinado na URL, recusado por não ter revogação, não ter auditoria e pôr
credencial no histórico do navegador.

**Metade B — apresentação. Essa sim é do `operator-kit`, e é opt-in por rota.**

```ts
definePageMeta({ screen: { reader: "customer" | "team", idle: "never" } })
```

O que a capability passa a garantir, em um lugar só: sem gate de operador, sem trava por
ociosidade (generalizando `operatorActivity: false`), tela cheia + wake lock **da rota**
e não do app, recarga ociosa para pegar versão nova, dark da rota, e a regra de falha —
último quadro no ar, nunca pergunta.

**Como isso respeita a ADR-026, que é o ponto que o dono mandou ler antes de propor:**

- É **capability declarada explicitamente por consumidor**, nunca ativação implícita —
  a §1 e a §4 da ADR exigem isso literalmente, e o modelo já existe em
  `OperatorPwaCapabilityOptions`.
- **Não enfraquece ninguém.** Hoje `kds-nuxt` é kiosk fullscreen por app; descer para a
  rota **aperta**, não afrouxa: as telas de estação do KDS deixam de herdar envelope de
  parede.
- **O CSP não entra neste WP.** A adoção do envelope de segurança HTML por outros
  consumers segue o `SEC-SURF-001`, com inventário de dependências e aprovação humana.
  Este WP toca sessão/ociosidade/kiosk, não CSP.
- **Metade A fica fora do kit**, e é bom que fique: é política de autorização, tem que
  valer igual para o menuboard do Django, que não consome o kit.

### 6.3 O menuboard NÃO migra para Nuxt — e essa é a recomendação, não uma omissão

Tentador unificar as quatro telas numa tecnologia. **Recusado, por três razões:**

1. **Ele falha aberta, e a versão Nuxt não faria isso.** O servidor pinta o cardápio
   inteiro no HTML; sem JS, a TV mostra o cardápio. Uma tela na parede que depende de
   JS para mostrar qualquer coisa é pior que a que tem hoje.
2. **Não há app de destino legítimo.** Ele é voz de cliente; o app de cliente é o
   `storefront-nuxt`, e a **ADR-026 §6** o mantém deliberadamente fora do `operator-kit`
   (*"exige perfil e threat model próprios"*). Metê-lo num app de operador seria repetir
   o erro que a §6.1 acabou de nomear.
3. **Custa componente ou custa coerência**, e nenhum dos dois se paga.

> **O envelope é um CONTRATO com duas implementações conformes** — a do Django e a do
> `operator-kit` —, não uma biblioteca única. O contrato é o que a trava verifica; a
> tecnologia é detalhe de cada parede.

### 6.4 SSE, pela ADR-016

A ADR-016 é "SSE-first, com poll calmo de reserva", e o inventário mostra três estágios:
o menuboard está **em dia** (SSE `stock-catalog` + poll de 30 s); o `/pickup` está **em
dia** (SSE + poll de 10 s, com cue honesto); o letreiro **não tem SSE** — poll adaptativo
de 30 s, e é candidato explícito na própria ADR-016 (*"produção/fornadas"*); a tela do
cliente do PDV **não deve ter** — `BroadcastChannel` é a fonte certa, e o shell já
explica por quê.

⚠️ **O menuboard tem a lição que as outras precisam copiar:** o SSE passa pela **mesma
trava da página** (`_gated_eventstream`). O comentário chama isso de *"o vazamento mais
sério das quatro rotas"* — sem a trava, qualquer visitante assinaria o ritmo operacional
da loja: o que está esgotando, quando a fornada entra. Toda tela nova que ganhar SSE
herda esse requisito.

---

## 7. Resposta 2 — as TVs dos Feeds/Canais do Catálogo, e o caminho de descoberta

### 7.1 Entram, e são o centro

**Sim.** E não como apêndice: o menuboard é a **implementação de referência** da
categoria — a única com confiança de dispositivo, SSE travado, falha aberta e
configuração por operador. A seção "Telas" se organiza **em volta dele**.

Isso responde a pergunta do dono — *"me parece que seria um excelente lugar poder
acioná-las por aqui, não?"* — com um sim qualificado: o lugar de **abrir** uma tela é a
seção Telas; o lugar de **configurá-la** continua sendo `/feeds` no Gestor, onde a
permissão `shop.manage_catalog` já mora. Abrir e configurar são gestos diferentes, de
pessoas diferentes, em momentos diferentes.

### 7.2 A fronteira — o feed XML NÃO entra

| | Tela | Feed |
|---|---|---|
| Quem lê | gente, a distância | robô, agendado |
| Rota | `/menuboard/<ref>/` | `/feed/<ref>.xml` |
| Acesso | interno, dispositivo confiável | **público de propósito** |
| No `Channel` | `capability="display"` | `capability="feed"` |

O discriminador **já existe no código**: `backstage/projections/feeds.py:24-26` mapeia
`format` vazio → `capability="display"`, e `google_merchant`/`meta_catalog` →
`capability="feed"`. A seção Telas lista `capability="display"`. Uma linha de filtro,
nenhum campo novo.

⚠️ **E é a correção do defeito D7 que está vivo na tela hoje:** em `/feeds`, sob o
título **"Canais"**, o bloco **"Feeds e telas"** põe uma TV da loja e o catálogo do
Google lado a lado como irmãos, e logo abaixo **"Canais de venda"** mostra uma terceira
coisa. Uma palavra, três sentidos, uma tela. A §5.3 separa em dois blocos.

### 7.3 A seção no Hub

**Como o Hub funciona hoje:** registry declarativo em Python
(`backstage/projections/hub.py`, `_REGISTRY` de `_AppSpec`), oito entradas, filtradas
**no servidor** por predicado de permissão — tile que o operador não pode abrir nunca
chega ao navegador. `label` e `icon` têm cruzamento obrigatório com
`operator-kit/app-identity.json`, com CI que prende (`test_hub_projection_identity.py`).
URL vem de `SHOPMAN_SURFACE_URLS`, **sem env var nova**, e URL vazia ⇒ sem tile
(*"nunca apontar para link morto"*).

**Não há nenhuma noção de seção, grupo ou cabeçalho.** `HubTileProjection` é plana;
`app.vue` renderiza uma grade única; a ordem é a posição na tupla. A seção "Telas" exige
um campo novo nas duas pontas do contrato (Python + TS) e um agrupamento no render.

**Recomendação — a seção é de tiles de tela, não de apps:**

1. Campo `section` em `HubTileProjection` (`"apps"` | `"screens"`), default `"apps"`, e
   render agrupado. É a menor mudança que o Hub admite, e a que o próprio docstring dele
   já antecipa (*"caminho claro p/ configurável no Admin depois"*).
2. As telas entram como tiles com `kind: "launch"` e URL **absoluta da rota da tela** —
   `/menuboard/<ref>/` (uma por `Channel` display ativo), `/pickup`, `/marquee`,
   e **não** `/customer`, que não se abre por link (ela nasce de `window.open` da
   estação de venda; um link no Hub abriria uma tela morta, sem `BroadcastChannel`).
3. Permissão: o predicado do tile tem que ser **a mesma pergunta que a tela faz na
   porta dela** — o registry já registra que errar isso quebra nos dois sentidos. Para o
   menuboard é `shop.manage_catalog`; para o letreiro, `can_operate_production`.
4. ⚠️ **Tile no Hub é para o operador que vai INSTALAR a tela**, não para a parede. A
   parede não navega — ela recebe uma URL uma vez. O Hub é o lugar onde o operador
   descobre que a tela existe e a coloca no ar.

⚠️ **Correção registrada, porque o erro é sutil e a casa já pagou por ele.** A primeira
versão desta seção dizia que *abrir o tile logado provisiona o dispositivo*. **Está
errado, e o erro é perigoso:** se o operador abre o tile no laptop dele, quem recebe o
cookie de confiança é **o laptop**, não a TV. É a mesma classe de confusão do buraco de
estação de 20/08 — identidade trocada, cookie válido na zona inteira. O gesto de
instalação **não pode** ser "abrir o link logado" quando o operador e a tela são
dispositivos diferentes. A §9 é a correção.

---

## 8. Custo, e o que este WP não faz

### Componente novo na DigitalOcean: nenhum

Medido no `.do/app.alpha-subdomains.yaml`: as nove superfícies Nuxt **não são nove
componentes**. O ingress por hostname aponta para **dois** serviços Nuxt —
`operator-floor` e `operator-office` — mais `web` (Django) e `storefront-nuxt`.

Toda tela deste WP é **rota dentro de app que já existe**, e o menuboard segue no `web`.
**Nenhuma fase abaixo adiciona componente, worker, job ou banco.** A regra dura do dono
de 17/09 (custo medido ~US$ 115–130/mês) é respeitada por construção, e este WP **não
conclui** que um app Nuxt novo seja necessário — conclui o contrário, na §6.3.

### O que este WP NÃO faz

Não implementa. Não renomeia. Não decide domínio nem custo. Não toca CSP (isso é
`SEC-SURF-001`). Não migra o menuboard. Não cria model, migração nem env var.

---

## 9. A TV não tem teclado — pareamento por código

> **Restrição do dono, 18/09/2026:** *"qualquer domínio/host nosso será muito comprido
> para digitar no controle remoto de uma TV."*

Isso não é conveniência: é o que decide se a seção Telas é usável ou decorativa. Um
controle remoto digita com teclado na tela, uma letra por vez, navegando com setas.

### 9.1 O tamanho do problema, medido

| URL | Caracteres |
|---|---|
| `https://api.boulangerie.com.br/menuboard/tv-1/` | **46** |
| `api.boulangerie.com.br/menuboard/tv-1/` | 38 |
| `kds.boulangerie.com.br/pickup` | 29 |
| `boulangerie.com.br/tv` | **21** |

`boulangerie.com.br` **já é domínio da casa** — é a zona de todos os subdomínios de
operador, e hoje o apex nu só faz 301 para `www.nelsonboulangerie.com.br`. O piso
prático é 21 caracteres. Nenhum encurtador próprio desce muito disso sem **domínio
novo**, que é decisão de DNS do dono.

### 9.2 Encurtador × pareamento — o veredito

**Pareamento vence. O encurtador é recusado.** As quatro razões do time, avaliadas uma a
uma, com a primeira **corrigida** porque a versão original enfraquece o argumento:

**1. "O encurtador ainda exige digitar; o pareamento exige digitar uma vez na vida."**
→ **Refutado como está, e a versão correta é mais forte.** O encurtador também se digita
uma vez, se a URL for estável. A diferença real não é *quantas vezes*, é **o que a
string identifica**. Uma URL encurtada ainda codifica **qual conteúdo**: `nb.link/x7k2`
é o cardápio, `nb.link/p9m3` é a retirada — uma string por tela, e outra sempre que o
conteúdo mudar. A URL pareada codifica **nada**: é `boulangerie.com.br/tv`, **a mesma
string em toda TV da casa, para sempre**. O ganho não é "digitar menos"; é **haver um
só endereço no mundo**, que cabe num post-it na parede do escritório.

**2. "O encurtador não resolve trocar o que a TV mostra."** → **Confirmado, e é o
argumento decisivo.** Com encurtador, mudar o cardápio de uma TV é subir numa escada com
o controle remoto. Com pareamento, é um toque no Hub.

**3. "Salto a mais na rede, dono a mais, jeito a mais de quebrar — e quebra em silêncio
numa parede que ninguém está olhando."** → **Confirmado, e agrava:** encurtador de
terceiro é dependência externa nova; encurtador próprio é rota nova **mais** um domínio
curto novo (DNS = decisão do dono). E ele é um **redirect**: a URL final continua longa,
então não remove nada — só embrulha.

**4. "Pareamento abre porta para um painel de controle das telas."** → **Confirmado**, e
é o que impede a seção de ser gaveta de links (§7.3). Qual TV mostra o quê, qual está
viva, qual parou de buscar.

**Os dois não são exclusivos, e a recomendação usa os dois:** o pareamento é o
mecanismo; a URL curta no apex é o complemento barato que torna a digitação única
trivial. O que se recusa é o **encurtador** — a indireção com dono próprio.

### 9.3 O que o Core já tem — "desconfie da implementação, confie no Core"

A busca no `doorman` encontrou a peça **inteira**, e ela já conhece telas:

`TrustedDevice.SubjectType` tem **`DISPLAY`** como valor de primeira classe, com a
docstring dizendo o que é: *"um quadro de menu na parede é um navegador autorizado a ler
um quadro, e a forma é a mesma."* Junto vêm, já prontos: hash HMAC-SHA256 do token em
repouso, cookie HttpOnly **com nome por `subject_id`** (porque *"um computador pode tocar
duas TVs"* — o nome único fazia dois quadros se derrubarem), `label`/`ip_address`/
`last_used_at` para auditoria, revogação por dispositivo no Admin, e limpeza agendada.

E existe **um** fluxo de código-curto-na-tela no produto: `doorman/services/link_state.py`
— `new_code()`, `store_state()`, `pop_state()` (uso único), com alfabeto
**deliberadamente legível por humano**: `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, sem `0/O` e
sem `1/I`, *"porque o código pode ser lido por humano"*. É a mesma direção do
pareamento: a superfície A exibe um código, um humano o carrega, a parte B resgata uma
vez.

E o molde de UI/API de provisionamento também existe: `backstage/station_trust.py`
(`provision`/`revoke`, idempotente, sob `select_for_update`, com `PROVISION_PERM`) mais
`OperatorStationSetup.vue` + `useStationProvision.ts` no `operator-kit`.

> **Conclusão: nada de primitiva nova.** O pareamento é `TrustedDevice` **inalterado**,
> composto com a mecânica de código curto que já existe, na forma de provisionamento que
> já existe.

⚠️ **Três coisas que a documentação afirma e o código não tem** — achadas nesta busca, e
que enganariam quem fosse implementar: **`BridgeToken` não existe** (citado no
`CLAUDE.md:129`, `README.md`, `docs/README.md:75`); **`MagicLink` não existe** (a coisa
real é `AccessLink`); e **`manage.py menuboard_token` não existe** — citado como vivo no
`config/settings.py:1771` e na ADR-018:206, e pior: ele descreve **token assinado na
URL**, que é exatamente o desenho que o `menuboard_access.py` **descartou** por não ter
revogação, não ter auditoria e pôr credencial no histórico do navegador. Quem ler o
settings hoje implementa o desenho recusado. Vai para a Fase 0.

### 9.4 O desenho

**O gesto, do começo ao fim:**

1. Alguém digita `boulangerie.com.br/tv` na TV. **Uma vez na vida do aparelho.**
2. A tela não pede nada. Ela mostra, em fonte de parede, **um código de 6 caracteres** e
   uma frase: *"Digite este código na Central de Apps para escolher o que esta tela
   mostra."*
3. No Hub, seção Telas, o operador digita o código, dá um **nome** à tela ("TV do Café")
   e escolhe **o que ela mostra**.
4. A TV — que já está buscando — recebe o cookie de confiança e **troca para o
   conteúdo**. Ninguém subiu na escada.
5. Dali em diante, trocar o conteúdo é um toque no Hub. A TV nunca mais é tocada.

**Onde mora o código, e quanto vale:** em cache, com a chave do `link_state`, **nunca em
URL**. TTL de **minutos**, não os 1800 s do `link_state` (aquilo é orçamento de ida e
volta no WhatsApp; isto é alguém atravessando a sala). O código **se renova sozinho**
enquanto a tela não pareada estiver no ar — ela está exibindo, então pode rotacionar.

**O que ele autoriza — e esta é a parte que precisa estar certa:** o código **não é
credencial**. Sozinho ele não abre nada. Quem tem autoridade é a **sessão do operador**
no Hub, com a mesma permissão da porta da tela (§7.3). O código prova apenas **presença
física** — que você está vendo aquela TV. É o inverso do OTP: no OTP o código prova que
você *recebeu* a mensagem; aqui ele prova que você *enxerga* a parede.

⚠️ **Mas ele carrega autoridade suficiente para merecer trava**, e é aqui que ele difere
do `link_state` de hoje: adivinhar um código válido permitiria **vincular o navegador de
um atacante como se fosse uma tela**. O `link_state` não tem limite de tentativa nem de
taxa, porque o código dele não autoriza nada. Este precisa: **use `Gates.rate_limit` e a
contagem de tentativas que o `doorman` já tem** (`ACCESS_CODE_MAX_ATTEMPTS = 5`,
5 por 15 min, cooldown de 60 s). Não inventar contador novo. E **hash em repouso** se
virar linha de tabela em vez de chave de cache — todos os irmãos do `doorman` guardam só
digest, e destoar aqui seria a única coisa fora do lugar.

**O que a TV mostra enquanto não está pareada** — o primeiro estado que alguém vê, e que
**hoje não existe**:

> fundo escuro da casa · o código, enorme · *"Tela nova"* · uma linha dizendo o que
> fazer · o relógio.

Nada de erro, nada de logotipo de sistema, nada de "aguardando configuração". É um
estado **legítimo e calmo**, não uma falha — e é a primeira coisa que o dono vai ver
quando ligar uma TV. Ele vale desenho.

**Rede caindo:** invariante 4 da §2.1, sem exceção — último quadro no ar, aviso
discreto, **nunca** pergunta. O pareamento não muda isso, porque o cookie já está no
aparelho: a TV volta sozinha quando a rede volta.

**Pareamento revogado** (no Admin, por dispositivo, como já é hoje): na busca seguinte a
TV recebe 403 e **volta ao estado não pareado** — mostrando um código novo. Revogar
**não escurece a parede**; devolve a tela ao estado "esperando que me digam o que
mostrar". É o comportamento certo, e cai de graça do desenho.

**A TV que dormiria em 30 dias — resolvido por decisão.** ⚠️ O gap é real e medido:
`DEVICE_TRUST_TTL_DAYS = 30` e `check()` **não renova**, então uma TV pareada cairia em
30 dias e alguém subiria na escada. A versão anterior deste WP propunha janela
deslizante. **O dono decidiu melhor** (§10, decisão 7): *"Device Trust pode ser eterno."*
Para o sujeito `display`, a confiança **não expira** — TTL por sujeito, não global
(`customer` e `station` seguem em 30 dias). O que a eternidade cobra em troca — revogação
encontrável na seção Telas, e rastro — está na §10.3, e **não é opcional**.

### 9.5 O preço honesto: uma tabela nova

O §3 diz que Telas não tem domínio próprio, e isso continua verdadeiro. Mas o pareamento
**tem um custo estrutural**, e escondê-lo seria o oposto do que este WP existe para
fazer.

Hoje `subject_id` do `TrustedDevice` é o **ref do conteúdo** (o `Channel` do quadro). Se
o conteúdo mudar, muda o `subject_id`, muda o nome do cookie, e a TV precisa ser pareada
de novo — o que mata a promessa inteira. Logo, para o dono poder trocar o conteúdo pelo
Hub, o `subject_id` tem que ser a **identidade da própria tela**, e "o que ela mostra"
precisa de um lugar.

> **Uma tabela, em `shop`, fina:** `Screen(ref, label, location_ref, shows, is_active,
> metadata, paired_at, last_seen_at)`.

Por que isso não contradiz a §3, e por que não é domínio novo:

- **O conteúdo continua sendo `Channel`.** `shows` aponta para o canal de exibição; a
  ADR-018 fica intacta. Nenhum segundo mecanismo de "o que esta superfície mostra".
- **Ela responde uma pergunta que hoje ninguém responde:** *qual TV é esta, onde ela
  está, e o que ela está mostrando agora.* Pela constituição §8.3, isso é **registro de
  dispositivo**, não conceito de negócio — a mesma natureza do `Terminal` do `cashman`
  (*"o dispositivo onde a gaveta está"*), que já tem exatamente esta forma:
  `ref`/`label`/`channel_ref`/`location_ref`/`is_active`/`metadata`. **O precedente
  existe e a forma se copia dele**, inclusive o `channel_ref` — "dispositivo físico
  aponta para um `Channel`" já é padrão aceito da casa.
- **Não vai no Core.** `Terminal` mora no `cashman` porque lá é o domínio da gaveta;
  `Screen` mora no `shop` porque lá é quem orquestra `Channel` e serve o menuboard.
  Reaproveitar o `Terminal` seria fazer "terminal" significar duas coisas — exatamente o
  D7 que este WP existe para fechar.

**É a única tabela nova do WP inteiro**, e ela só aparece porque o dono pediu pareamento.
Sem pareamento, ela não existe.

### 9.6 Custo em DigitalOcean: zero componente novo

Rota `/tv` no Django (`web`, já existe) · código em cache (o `cache` já é componente do
app) · seção no Hub (`operator-office`, já existe) · aviso de pareamento por SSE
(`django_eventstream` já roda no `web`, e a tela não pareada já estaria buscando de
qualquer forma). **Nada de worker, job, banco ou serviço novo.** O único item que toca
infraestrutura é a regra de ingress do apex curto — §10, item 1.

### 9.7 O QR, com o alcance certo

Correção que o time registrou, e que o WP herda: **QR não serve para configurar uma TV** —
TV não tem câmera. Citar "QR para configurar o quiosque" sem essa ressalva é errado.

Mas há um uso legítimo, e ele é o **inverso**, com a câmera do lado que a tem: **a TV
exibe o QR ao lado do código, e quem escaneia é o celular do operador**, já logado, que
abre a tela de pareamento com o código preenchido. Mesmo mecanismo, mesma trava, zero
digitação. E quando a tela é instalada num **tablet** (que tem câmera e teclado), o
problema do controle remoto nem existe.

→ **Recomendação: Fase 3, opcional.** O código digitado é o caminho obrigatório, porque
é o único que funciona em toda parede; o QR é atalho, e atalho não pode ser o único
caminho.

---

## 10. As decisões do dono — tomadas em 18/09/2026

Estavam publicadas aqui como recomendação. **Ele decidiu as cinco.** Ficam registradas
como decisão, com a consequência de cada uma no plano.

**1. A seção se chama "Telas".** Sem qualificador — não "Telas de parede", não "Telas e
painéis". A palavra sozinha. ✅ **Decidido.** Consequência: é o rótulo da seção no Hub
(§7.3) e o nome da categoria em toda a casa (§5.2). O título deste WP mantém "de parede"
por ser nome de arquivo, não rótulo de tela.

**2. ⛔ NENHUM 301. A recomendação anterior está REVOGADA.**
> *"o sistema é novo e não devemos legado a nada ainda!!!"* — o dono, 18/09/2026

A versão anterior recomendava 301 em `/board` e `/display` citando o precedente de kiosk
do PR #68. **Não vale aqui, e o argumento de bookmark está descartado.** A regra
pré-go-live do `CLAUDE.md` é zerar o nome antigo — variáveis, strings, comentários,
docstrings —, e ela vale inteira. As rotas antigas **somem**; nenhum alias, nenhum
redirect, nenhum passo de compatibilidade. Uma TV com bookmark velho se resolve digitando
o endereço novo uma vez, e depois do pareamento (§9) ela nem tem mais bookmark de
conteúdo: tem `/tv`. ✅ **Decidido.**

**Confirmação de 24/09/2026, sobre a consequência do item 12b.** A decisão alcançava três
aliases 301 que já existiam antes deste WP, e isso foi levado de volta a ele porque não
estava no pedido original. Resposta: *"SIM — os três aliases de quiosque morrem junto com o
endereço único (pré-go-live não há legado)."* ✅ **Decidido, com a ordem que a própria frase
dele impõe** — *junto com*, não antes: ver 12b.

**3. O endereço único: `boulangerie.com.br/tv`.** Regra de ingress, não domínio novo —
o apex nu hoje só faz 301 para `www.nelsonboulangerie.com.br`. 21 caracteres contra 46 da
URL de menuboard de hoje. **Encurtador de URL recusado** (§9.2). A execução do ponteiro é
dele; o pareamento não fica bloqueado nisso — funciona em qualquer host fixo, e a URL
curta é conforto.

**4. `SHOPMAN_MENUBOARD_PUBLIC` continua `false`**, com teste que prenda o default
fechado (Fase 0). A razão é jurídica, não higiene (§2.2). ✅ **Decidido.**

**5. O letreiro ganha SSE — ele quer.** Deixou de ser "melhoria pós-go-live" e virou
requisito. ✅ **Decidido.** A §11 reposiciona, e a §10.1 diz o que isso passa a exigir.

**6. A tabela nova está aprovada, e chama-se `Screen`, em `shopman/shop/models/`.**
✅ **Decidido.** A §9.5 já justificava a tabela; a §10.2 responde as duas perguntas dele
— *onde* ela mora e *`Screen` ou `Display`* — e fecha o de-para inteiro, porque ele foi
explícito sobre a hora:
> *"Sei que precisamos arrumar essa zona que ficou de nomenclaturas... A hora é agora."*

**7. Confiança de dispositivo para tela é ETERNA.**
> *"Device Trust pode ser eterno."* — o dono, 18/09/2026

✅ **Decidido**, e resolve o `DEVICE_TRUST_TTL_DAYS = 30` sem janela deslizante que a §9.4
achou. A §10.3 escreve o que isso cobra em troca, porque confiança que não morre sozinha
muda o desenho da revogação.

---

### 10.1 O que o SSE do letreiro passa a exigir, agora que não é opcional

Hoje o letreiro é o único dos quatro sem push: poll adaptativo de 30 s
(`useProductionForecast`). A ADR-016 já o nomeia candidato. Virando requisito, ele cobra
quatro coisas, e a terceira é a que costuma ser esquecida:

1. **Canal nomeado + permissão explícita** no `ShopmanChannelManager`, autorizada *up
   front* na view (Http404 para não-autorizado, para o `EventSource` falhar de vez e cair
   no fallback) — ADR-016 §3.
2. **Rota BFF de uma linha** no `production-nuxt`, sobre o `proxyEventStream` que o
   `operator-kit` já fornece. Transporte existente; nada novo.
3. ⚠️ **A trava do canal, no modelo do `_gated_eventstream` do menuboard.** O comentário
   de lá chama a falta dela de *"o vazamento mais sério das quatro rotas"*: sem trava,
   quem chamar assina o ritmo operacional da loja. O letreiro publica **o que sai do
   forno e a que horas** — é a mesma classe de informação. A trava não é opcional porque
   a tela é de parede.
4. **O poll continua**, em cadência calma (ADR-016 §2). SSE é camada de push sobre o
   fetch canônico, nunca a fonte da verdade — no evento, refaz o fetch.

**De quem depende:** de ninguém fora da casa. É trabalho de backend (canal + permissão) e
de superfície (BFF + `EventSource`), ambos com molde pronto. **Sobe da Fase 4 para a
Fase 3**, junto do pareamento, porque os dois tocam a mesma tela não-pareada: ela precisa
saber que foi pareada sem recarregar, e o transporte é o mesmo.

---

### 10.2 `Screen` ou `Display`, e onde ela mora — as duas perguntas dele

#### `Screen` é o nome. E a razão não é que "display está ocupado".

A razão é melhor: **os dois nomes descrevem coisas de naturezas diferentes, e mantê-los
separados torna o sistema mais legível, não menos.**

`display` já é **papel/atributo** em dois lugares do Core, e em nenhum deles é uma coisa:

| Onde | O que é | Natureza |
|---|---|---|
| `Channel.CommercePolicy.DISPLAY` (`shop/models/channel.py:37`) | *"somente exibição"* — até onde a interação comercial vai naquele canal | **política** |
| `TrustedDevice.SubjectType.DISPLAY` (`doorman/.../device_trust.py:70`) | de quê aquele navegador é confiável | **tipo de sujeito** |

`Screen` nomeia a **coisa**: o painel físico, pareado, pendurado na parede, que mostra
alguma coisa. A composição fica legível numa frase:

> Um **`Screen`** é um dispositivo confiável de sujeito **`display`**, ligado a um
> **`Channel`** com `commerce_policy=display`.

**Não há colisão — há camada.** Cada palavra responde uma pergunta diferente: *o que é
isto* (`Screen`), *de que ele é confiável* (`display`), *até onde aquele canal vai*
(`display`). Renomear `display` para `screen` nos dois lugares do Core seria o erro
oposto: apagaria a distinção entre política e coisa, e exigiria migração em pacote Core
para piorar a semântica.

✅ Verificado: **`class Screen` não existe** em lugar nenhum do repositório. O nome está
livre.

#### Ela mora em `shopman/shop/models/`. E o `doorman` foi descartado com razão de código.

A pergunta era legítima: se o pareamento é identidade, por que não no `doorman`?
**Porque o `doorman` deliberadamente não conhece ninguém**, e isso está escrito no
próprio model:

> `subject_id = models.CharField(...)` — *"Sujeito tipado (**sem FK** — mesmo padrão de
> desacoplamento de sempre)"*, e o sujeito é textual *"porque cliente é identificado por
> UUID, display por `ref` de canal"*.

O `TrustedDevice` guarda `ref` de `cashman.Terminal` e `ref` de `shop.Channel` **sem
importar nenhum dos dois**. É o mesmo desacoplamento que faz `Terminal` morar no
`cashman`, e não no `doorman`, mesmo sendo o sujeito `station`.

`Screen` aponta para um `Channel` (o que ela mostra) **e** é sujeito de confiança de
dispositivo. Pôr isso no `doorman` obrigaria um pacote de autenticação a conhecer o
catálogo — quebrando a regra de dependência da casa (cores não se importam entre si).
**Só o `shop` pode costurar os dois**, porque é o orquestrador e já é dono do `Channel` e
do menuboard.

**Precedente de forma**, copiado de propósito — `cashman.Terminal`, *"o dispositivo onde
a gaveta está"*: `ref`, `label`, `channel_ref`, `location_ref`, `is_active`, `metadata`.
"Dispositivo físico aponta para um `Channel` por ref" **já é padrão aceito**; `Screen`
não inventa nada, só o aplica na parede.

#### O de-para fechado — cada palavra com um dono

A §5.2 e a §5.3 já traziam o grosso. Isto fecha o que faltava, no Core:

| Hoje | Passa a ser | Natureza da mudança |
|---|---|---|
| `SubjectType.DISPLAY = "display", _("quadro")` | `_("tela")` — **o valor gravado `"display"` NÃO muda** | rótulo pt-BR |
| docstrings de `device_trust.py` que dizem *"um quadro de menu na parede"*, *"cliente, quadro ou estação"* | "tela" | prosa |
| `help_text` do `subject_id`: *"ou ref do canal de exibição"* | *"ou ref da tela"* — ⚠️ **muda de fato** com o pareamento (§9.5): o sujeito passa a ser a tela, não o conteúdo | semântica |
| `Channel.CommercePolicy.DISPLAY` | **inalterado** | — |
| `board` como palavra de superfície | sai; fica só como sufixo de read-model no backend | §5.2 |

⚠️ **Sobre a migração do rótulo.** Trocar o label de um `TextChoices` gera `AlterField`.
Dois cuidados que a casa já pagou para aprender:

- **Regerar, não editar.** A migração `0004_trusted_device_station.py:28` carrega o par
  `("display", "quadro")`. **Não se edita** — gera-se uma nova. Editar uma migração
  aplicada e renumerar não basta quando o que muda são `choices`: a última `AlterField`
  apaga o que a outra registrou.
- **Precedente existe:** `0003_rotulos_em_portugues.py` é exatamente esta classe de
  mudança — só rótulo, nenhuma coluna, nenhum dado. A nova migração se parece com ela.

---

### 10.3 O que a confiança eterna cobra em troca

A decisão resolve o gap de 30 dias da forma mais simples possível: **para o sujeito
`display`, a confiança não expira.** Sem janela deslizante, sem renovação no `check`,
sem TV que escurece sozinha num domingo.

Mas ela **transfere o peso inteiro para a revogação**, e isso é a parte do desenho que
passa a ser obrigatória:

> Se a confiança não morre sozinha, **revogar é o único caminho** — e o que é único
> caminho tem que existir, ser encontrável e deixar rastro.

Três exigências, e nenhuma é opcional:

1. **A revogação tem que existir e ser encontrável na seção Telas** — não só no Admin,
   enterrada numa lista de dispositivos confiáveis. A pessoa que precisa despareá-la é a
   que está olhando a lista de telas: *"esta TV foi trocada"*, *"esta sumiu"*. A seção
   Telas é o lugar natural, e o §7.3 já a desenha como painel de controle, não gaveta de
   links. `TrustedDevice.revoke()` e `revoke_all_for(type, id)` já existem — falta a
   porta.
2. **Tem que deixar rastro.** `label`, `ip_address`, `last_used_at` já existem no model e
   hoje quase ninguém os lê. Com confiança eterna eles viram a **única** forma de
   responder "esta tela ainda é a que eu pendurei?". A seção Telas mostra, por tela:
   quando foi pareada, quando foi vista pela última vez, e de onde. **Tela que parou de
   buscar é o sinal de que algo aconteceu com o aparelho** — e é exatamente o que a §7.3
   pedia para a seção não ser decorativa.
3. **O risco a nomear, porque confiança eterna o cria:** uma TV **roubada ou trocada**
   continua válida para sempre se ninguém souber onde despareá-la. Esse é o preço da
   decisão, e ele é aceitável **desde que** 1 e 2 existam. Se a seção Telas sair sem a
   revogação visível, a eternidade vira dívida silenciosa — o oposto do que este WP
   existe para evitar.

⚠️ **Escopo da eternidade:** vale **só** para `subject_type="display"`. `customer` e
`station` mantêm os 30 dias — são pessoas e balcões, não paredes, e o argumento ("ninguém
está lá para reautorizar") não se aplica a eles. A implementação é TTL por sujeito, não
`DEVICE_TRUST_TTL_DAYS = 0` global.

---

## 11. Fases, e o que é pré-requisito de quê

As cinco decisões do dono (§10) estão tomadas. **Nenhuma fase espera palavra dele.**

### Fase 0 — a verdade escrita (nenhum código de produto)

Barata, sem risco, e pré-requisito de todas as outras porque é onde a nomenclatura vira
regra citável.

1. Corrigir as **duas prosas erradas** medidas na §5.3 (docstring "pública" do
   `views/menuboard.py`; "no dia em que o renderizador passar a ler" do
   `menuboard_access.py` — ele já lê).
2. ADR-018 de **"Proposto" → "Aceito"**, com a evidência do código no ar.
3. Promover ao `CLAUDE.md` a **regra de URL por superfície** (§5.4) e a **regra de voz
   pelo leitor** (§6.1).
4. Entrada de **tela** no `docs/reference/glossary.md`, com o de-para da §5.3 e da §10.2.
5. Corrigir `"kiosk Solari"` → `"letreiro de fornadas"` no `CLAUDE.md` e no
   `docs/status.md`.
6. Teste que prende `SHOPMAN_MENUBOARD_PUBLIC=false` como default.
7. ⚠️ **Apagar as três referências a coisas que não existem** (§9.3), porque elas
   induzem a implementar o desenho errado: `BridgeToken` (`CLAUDE.md:129`, `README.md`,
   `docs/README.md:75`), `MagicLink` (o real é `AccessLink`), e `manage.py
   menuboard_token` (`config/settings.py:1771`, ADR-018:206) — este último descreve
   **token assinado na URL**, que o `menuboard_access.py` descartou por não ter
   revogação nem auditoria.

### Fase 1 — o envelope (depende de: Fase 0)

8. Capability `screen` por rota no `operator-kit` (§6.2, metade B), **opt-in**, com
   `definePageMeta`. Generaliza `operatorActivity: false`.
9. Adotar nas quatro telas, **uma por PR**. `/pickup` primeiro: é a que hoje depende de
   exceção no shell, que é o padrão mais frágil dos três (§1.6).
10. Descer `kiosk`/`wakeLock` de `kds-nuxt` e `production-nuxt` do app para a rota.
    ⚠️ **Aperta, não afrouxa** — as telas de estação do KDS param de herdar envelope de
    parede.
11. Trava de varredura do envelope, no modelo do `test_vocabulario_de_tela.py`
    (varre STRING/AST, tem auto-teste de que a varredura leu algo): toda rota declarada
    `screen` tem que passar nos cinco invariantes da §2.1.

### Fase 2 — a nomenclatura (depende de: Fase 0)

⛔ **Zero resíduo, sem exceção.** A rota antiga some; nenhum 301, nenhum alias, nenhum
passo de compatibilidade (§10, decisão 2).

12. De-para da §5.3 — inclusive `/board` → `/marquee` e `/display` → `/customer`, que na
    versão anterior deste WP tinham ressalva de bookmark e **não têm mais**.
12b. ✅ **Os três aliases 301 de kiosk do PR #68 saem** — `/cliente` e `/retirada` →
    `/pickup`, `/painel` → `/board`. Era consequência da decisão 2 e não do pedido original,
    então foi confirmado com o dono em 24/09: *"os três aliases de quiosque morrem junto com
    o endereço único"*.
    ⚠️ **"Junto com" é condição de ordem, e ela não é decorativa.** Estes três são diferentes
    dos renomes do item 12: eles são, para pelo menos uma tela, **o único caminho que
    existe** — o inventário da §4 registra que ao `/pickup` "não há link nenhum na UI" e
    chega-se por URL digitada. Tirá-los num deploy anterior ao do endereço novo deixa uma TV
    na parede sem caminho nenhum, e ninguém está olhando aquela tela para perceber. O custo
    que o dono aceitou é *digitar o endereço novo uma vez*; não é *a parede apagada até
    alguém notar*.
    **Então:** a remoção destes três vai no MESMO deploy que entrega o endereço novo
    alcançável. Se o endereço único (§10, decisão 3) ainda depender do ponteiro de DNS, o
    "endereço novo" desta condição é a rota renomeada do item 12, que já está no ar no mesmo
    push — e aí a condição está satisfeita sem esperar o DNS.
13. De-para do Core da §10.2: `SubjectType.DISPLAY` com rótulo `_("tela")` (**valor
    `"display"` inalterado**), docstrings e `help_text` do `device_trust.py`.
    ⚠️ **Migração nova, nunca editar a `0004`** — o precedente de forma é a
    `0003_rotulos_em_portugues.py`.
14. Trocar o critério de isenção da trava de vocabulário: de **diretório** para **leitor
    declarado** (§6.1) — é o que traz `/pickup` e o menuboard para a isenção de voz de
    cliente, onde eles sempre pertenceram.
15. Separar `"Feeds e telas"` em dois blocos em `/feeds` (§7.2).

### Fase 3 — pareamento, SSE e a seção Telas (depende de: Fases 1 e 2)

Depende das duas porque um tile que abre uma tela sem envelope e com nome errado publica
o defeito em vez de escondê-lo. **O SSE do letreiro subiu da Fase 4 para cá** (§10,
decisão 5): ele e o pareamento tocam a mesma tela não-pareada, que precisa saber que foi
pareada **sem recarregar**, e o transporte é o mesmo.

16. Tabela **`Screen`** em `shopman/shop/models/`, na forma do `Terminal` do `cashman`
    (§9.5, §10.2).
17. Rota `/tv`: **estado não pareado** (o código enorme, §9.4) e, pareada, o conteúdo.
    O estado não pareado é o primeiro que alguém vê e **não existe hoje** — vale desenho,
    não improviso.
18. Pareamento: código curto na mecânica do `link_state`, TTL de minutos, **com
    `Gates.rate_limit` e contagem de tentativas** (§9.4 — o `link_state` não tem, e este
    código precisa). Resgate no Hub sob a mesma permissão da porta da tela.
19. Generalizar `subject_type="display"` de "menuboard" para qualquer tela (§6.2,
    metade A), com `subject_id` = ref da **tela**, não do conteúdo.
20. ⚠️ **TTL eterno para o sujeito `display`** (§10, decisão 7) — TTL **por sujeito**,
    não `DEVICE_TRUST_TTL_DAYS = 0` global: `customer` e `station` seguem em 30 dias.
    Substitui a renovação deslizante que a versão anterior deste WP propunha.
21. ⚠️ **A revogação visível na seção Telas, e o rastro** (§10.3) — é o que paga a
    eternidade. Por tela: quando foi pareada, quando foi vista pela última vez, de onde,
    e o botão de desparear. **Sem isto, a Fase 3 não fecha**: confiança eterna sem
    revogação encontrável é dívida silenciosa.
22. Campo `section` no `HubTileProjection`, nas duas pontas do contrato, com o
    cruzamento de identidade que a CI já exige. Seção **"Telas"** (§10, decisão 1)
    listando `Screen` — qual TV mostra o quê, qual está viva, qual parou de buscar.
23. **Letreiro ganha SSE** pela ADR-016 (§10.1): canal nomeado + permissão *up front*,
    rota BFF sobre `proxyEventStream`, ⚠️ **trava do canal** no modelo do
    `_gated_eventstream`, e poll calmo mantido como rede.

### Fase 4 — depois do go-live

24. QR ao lado do código, escaneado pelo **celular do operador** (§9.7). Atalho, nunca o
    único caminho.

---

## 12. Referências

- [ADR-018 — Superfície e canal: uma entidade, com política comercial](../decisions/adr-018-surface-is-channel-with-commerce-policy.md) — §5.1 (menuboard é interno), §9
- [ADR-016 — Tempo real por SSE](../decisions/adr-016-sse-first-realtime.md)
- [ADR-026 — Envelope de segurança das surfaces de operador](../decisions/adr-026-operator-surface-security-envelope.md) — §1, §4, §6
- [Omotenashi — Espectro de Superfícies e Mapa × Portões](../omotenashi.md) — a linha "Sinalização"
- [Omotenashi Copy](../reference/omotenashi-copy.md) — D7 (colisão de vocabulário)
- [`surfaces/operator-kit/README.md`](../../surfaces/operator-kit/README.md) — como um app consome
- [`SURFACE-OFFER-CAMPAIGN-PLAN.md`](SURFACE-OFFER-CAMPAIGN-PLAN.md) — §10 ("rotas nomeiam o artefato"), decisões 8 e 10 do dono
- [`CATALOG-FEEDS-GOOGLE-META.md`](CATALOG-FEEDS-GOOGLE-META.md) — o feed público
- `shopman/shop/menuboard_access.py` — a razão jurídica da trava
- `shopman/backstage/tests/test_vocabulario_de_tela.py` — o modelo de trava de vocabulário
