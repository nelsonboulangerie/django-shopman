# CORE-SOVEREIGNTY-PLAN — Titularidade e Soberania

> **Status:** Fase 0 **concluída e aceita**; plano reparado e execução autorizada.
> **Base original:** `main @ 35d95104d`. Evidências históricas continuam identificadas por
> símbolo; cada WP revalida paths e linhas contra sua própria base.
> **Rebaseline:** `main @ 1d0bc7d76`, após ADR-037, governança de 39 ADRs, mapa de camadas e
> correções A1-A2. Parecer: [CORE-SOVEREIGNTY-REVIEW.md](CORE-SOVEREIGNTY-REVIEW.md).
> **Regime de corte:** enquanto `go-live-v1` não existir, contrato único e zero
> compatibilidade runtime. A ADR-015 ativa expand-contract somente depois da tag.
> **Natureza:** plano de **fronteira**, não de feature. Nenhuma capacidade nova é pedida.
> **Autor:** sessão de arquitetura (DSH), a partir de leitura de `packages/*`, `shopman/shop` e ADRs.

---

## 0. Intenção

O objetivo é um kernel de pacotes **minimalistas, flexíveis e agnósticos**, cada um soberano na sua pergunta de domínio, e um orquestrador capaz de montar operações comerciais densas **sem deformar nenhum pacote**.

Este plano existe porque há uma **incoerência de titularidade** — não de capacidade. Decisões de domínio carregam dois donos: o pacote que as nomeia e o orquestrador que as executa. A consequência prática não é estética: **toda mudança de requisito vira edição coordenada em dois lugares**, e a operação não pode parar.

**Não-objetivos** (explicitamente fora de escopo):

- distribuição/adoção externa como critério de sucesso;
- paridade de features com PIM/WMS/ERP/allauth;
- criar pacote novo "para o futuro";
- reescrita. A lógica já existe; o que muda é **quem é o dono**.

---

## 1. A Lei da Titularidade (ADR-037, aceita)

> **A pergunta canônica de um domínio pertence ao pacote daquele domínio. A política que compõe dois ou mais domínios pertence ao orquestrador. Nenhum dos dois invade o outro.**

> **Precedente:** este critério já está em uso. `CORE-BOUNDARIES-AUDIT.md` (2026-08-18) aplica marcas equivalentes — (a) model com invariante vivendo em superfície/orquestrador, (b) alcançado por adapter de uma impl só, (c) estado de domínio em JSON alheio, (d) mesma pergunta com vários donos, (e) política transversal legítima do orquestrador — e conclui "default = fica". Esta lei **consolida** esse método com ADR-005 §3, ADR-019 e ADR-022 num único ADR; **não** é doutrina nova.

Corolários operacionais:

1. **Uma decisão, um dono, um ponto canônico de entrada.** Isso não significa um único
   verbo por pacote: um domínio pode ter várias decisões e mutações legítimas. Significa
   que a mesma decisão não pode ser recalculada por outro dono e que seu resultado preserva
   a razão da decisão.
2. **Teste do vocabulário estrangeiro.** Se um model/regra precisa de campos de três domínios diferentes, ele **não** pertence a um pacote de kernel — pertence ao orquestrador. (Precedente: ADR-019.)
3. **Teste do ledger.** Domínio que possui **livro imutável** (história de fatos) é pacote. Política computada sobre estados alheios é orquestrador. (Precedente: ADR-022, que contrasta explicitamente com ADR-019.)
4. **O orquestrador pode ser denso; não pode ser dono do verbo de um único domínio.** Ele é dono de **composição** e de **política cross-domain** — isso não é acoplamento indevido (ADR-005 §3).
5. **Fronteira é contrato, não import acidental.** Código de domínio de kernel não importa
   outro kernel. Bridges opt-in, nomeadas e lazy em `adapters/` ou `contrib/<alvo>/`
   continuam permitidas pela ADR-001; elas conectam donos sem transferir titularidade.
   A conversa usa porto, evento ou comando durável conforme a interação exigir.

### Composição × Política

- **Composição** = *quem, quando, em que ordem*. Liga portas e sequencia domínios. Não contém regra de negócio própria; mudar = reordenar/reconfigurar.
  - Ex.: `on_confirmed` → `stock.hold` → `payment.capture` → `notification.send`.
- **Política** = *regra que só existe porque dois domínios se encontram*. É regra de negócio; mora em módulo nomeado, versionado e testado.
  - Ex.: "promoção vale só na web, para aniversariantes, com pedido mínimo, e zera o frete" compõe offerman × guestman × orderman.

Precedentes de indústria em que a política cross-domain é externalizada: condition technique do SAP; Shopify Discount/Shipping Functions; Stripe Radar (risco = pagamento × cliente × pedido); Avalara/Stripe Tax (tributo = produto × endereço × cliente). Em todos, o motor é um domínio de política com **dados + procedimento**, não um `if`.

---

## 2. Camadas, nomes e invariantes

### 2.1 Glossário técnico (canônico)

| Conceito | Nome | Onde está |
|---|---|---|
| Pacotes de domínio | **Kernel** | 10 de 13 distribuições em `packages/*` |
| Capacidades compartilhadas/operacionais | **Primitivas horizontais** | `refs`, `utils`, `watchman` |
| Composição + política | **Orquestrador** | `shopman/shop` (app Django, `label="shop"`) |
| Configuração do negócio | **Instância** | `config/` + linhas no DB |
| Dados de exemplo | **Seed** | `config/management/commands/seed.py` |
| Interfaces entre pacotes | **Contratos / portas** | `protocols.py`, `Protocol` |
| Verificação de contrato | **Testes de contrato** | `tests/` |

> Os nomes "canteiro", "projeto", "gabarito" e "maquete" usados em rascunhos anteriores eram analogia, não conceito. **Estão retirados.**

### 2.2 Camadas completas e fronteira de entrega

O read-side tem estrutura própria e não pode ficar fora do mapa (ADR-012, ADR-014):

```
Kernel de domínio + capacidades horizontais    packages/*
   ↓ portas / services
Orquestrador (composição + política)           shopman/shop
   ↓ fronteira de entrega
Query/read-side (Projection + GET/SSE)         projections, presentation, endpoints de leitura
Command ingress (intents + métodos mutáveis)   POST/PUT/PATCH/DELETE que validam e delegam
   ↓ HTTP / SSE
Superfícies (Nuxt) + Admin/Unfold              produto, interna, externa e Admin
Instância = DB + config de deploy + marca      parametriza tudo acima
```

O inventário físico verificável vive em
[`docs/architecture-map.json`](../architecture-map.json): 13 distribuições pip, sendo dez
kernels de domínio, duas primitivas compartilhadas e uma capacidade operacional; onze apps
Nuxt registrados, sendo nove superfícies de produto, uma preview interna e uma superfície
externa de status. `operator-kit` é layer compartilhada e `operator-router` é infraestrutura
de deploy, não superfícies de produto.

**Projeção é mecanismo de leitura, não política.** A política pode exigir uma projeção, mas a projeção não é o lugar da decisão.
**Regras de dependência (seta única, testada):**

- **Superfícies** (Nuxt) → só falam HTTP/SSE com a fronteira de entrega; nunca importam kernel nem orquestrador.
- **Query/read-side** → lê do orquestrador/kernel e **não produz efeito novo**.
- **Command ingress** → autentica, valida transporte/permissão/idempotência/concorrência e delega; **não decide**.
- **Orquestrador** → importa vários kernels (é o único lugar onde se encontram — ADR-005 §3); nunca renderiza.
- **Kernel** → não conhece nenhum dos outros; fala por porto/signal/directive.
- **Instância** → não é camada; parametriza todas as outras (config + DB + marca).

**Onde mora o quê (teste de localização):**

| Pergunta | Camada |
|---|---|
| "onde está o saldo / o ledger?" | Kernel |
| "posso prometer?" | Kernel (decisão) + Orquestrador (gate) |
| "que desconto vale?" | Orquestrador (política) |
| "qual o JSON da sacola?" | Read-side (projeção) |
| "onde a intenção HTTP é validada?" | Command ingress |
| "onde fica a tela da sacola?" | Superfície |
| "qual o horário da loja?" | Instância |


### 2.3 O que é invariante entre instâncias

Confirmações explícitas:

- **Shopman é o orquestrador.** Ele usa os pacotes de domínio para fazer os domínios interagirem corretamente.
- **O código do orquestrador é um só.** Ele não muda de instância para instância.
- **Ele não é determinado pelas regras de uma instalação.** Quem o caracteriza é a Instância; o DB é a verdade de runtime, e config/descritor/seed servem a deploy, bootstrap e diff.
- **Composição e política hoje NÃO são pacotes separados** — são módulos dentro do orquestrador. Criar pacote pip para elas violaria o critério "2+ consumidores reais" e a ADR-005 §3 (é no orquestrador que domínios se encontram).

**Resíduo medido:** o princípio é honrado, mas há vazamento a zerar — p.ex. `DEFAULT_EMPLOYEE_DISCOUNT_PERCENT`, `DEFAULT_TIME_WINDOW_START` e afins em `shopman/shop/modifiers.py` (política como constante de código). Nomes da instância em docstrings/comentários são prosa, não vazamento.

**Aceite (entra no WP-7):** nenhuma constante/prefijo/domínio específico de instância no código; tudo via settings, `Shop.defaults`, `RuleConfig` ou `ChannelConfig`, conforme a
[Constituição §5](../constitution.md#5-regras-de-modelagem).

### 2.4 O que é "Shopman", tecnicamente

Não existem dois apps Django:

- `django-shopman` — a **distribuição** (`pyproject.toml`);
- `shopman/` — o **namespace** (PEP 420);
- `shopman/shop/` — **um** app: `AppConfig = ShopmanConfig`, `name = "shopman.shop"`, `label = "shop"`;
- `Shop` — o **model** singleton da empresa/tenant;
- `config/` — o **projeto Django** da instalação.

Logo: **Shopman** = ecossistema (kernel + orquestrador + read-side + superfícies + instância). **Shop** = o app do orquestrador. São o mesmo app com classe e label diferentes — origem da confusão.

---

## 3. Diagnóstico — o que viola a lei hoje (base `main`)

| # | Violação | Evidência (símbolo) | Movimento |
|---|---|---|---|
| V1 | Decisão de promessa **duplicada**; produção usa a cópia do orquestrador | `shopman/shop/adapters/stock.py` `promise_decision_from_availability` (l. 974) vs `packages/stockman/.../services/availability.py` `promise_decision_for_sku` (l. 295); chamada em `shopman/shop/services/availability.py` (l. 496) | Repatriar (expor `decision_from_availability` no stockman; deletar cópia) |
| V2 | Vocabulário de negação fragmentado, sem enum | stockman `insufficient_supply` (l. 334); orquestrador `insufficient_stock` (l. 505, 878, 938, 1296, 1327), `not_in_listing`, `paused` | Fechar `ReasonCode` no stockman; orquestrador só compõe |
| V3 | "Disponibilidade ilusória": sentinela `999999` e três representações de *untracked* | `shopman/shop/services/availability.py` l. 486–493; `shopman/storefront/presentation/catalog.py` (`None = untracked`); `shopman/shop/services/stock.py` (`untracked: True`) | Separar `available_qty` factual de `orderable_ceiling` político, ambos opcionais, mais `is_tracked`; `demand_ok` não falsifica o fato observado |
| V4 | Dois caminhos de preço; um morto | `shopman/shop/services/pricing.py` `resolve` (l. 16) → `CatalogService.price` (lista) vs `shopman/shop/projections/catalog_context.py` `contextual_price` → `CatalogService.get_price` (com promoção) | Um verbo, um caminho |
| V5 | Constituição reivindica "pricing core" para offerman; ADR-019 decidiu o contrário | [Constituição v1 §4.1 (histórica)](../_archive/constitution-v1.md#41-offerman), antigas linhas 193, 195 e 1063, vs ADR-019 §1 | Atualizar §4.1 |
| V6 | Doorman importa guestman direto e engole a falha | `packages/doorman/.../services/verification.py` l. 553–556 + `except Exception` | Porto de identidade; sem import direto |
| V7 | Porto de identidade pobre (perde handle/primazia/verificação) | `packages/doorman/.../protocols/customer.py` `AuthCustomerInfo` (l. 9); resolução binária `target_kind` (l. 108) | Alargar o porto (CIAM) |
| V8 | Governança: ADR-019 está `Proposto` mas implementado | `docs/decisions/adr-019-*.md` `Status:` (l. 3) | Marcar Aceito |
| V9 | Drift topológico e contagens sem semântica | baseline original em `README.md` e `docs/architecture.md`; fontes atuais em `packages/*` e `surfaces/registry.json` | Derivar o inventário e distinguir kernel, capacidade horizontal, superfície de produto, preview interna e status externo |
| V10 | **Orquestrador sem unidade conceitual**: organização por mecanismo + 49 arquivos na raiz; decisões espalhadas | ver §5 WP-7 (inventário medido) | WP-7 |

---

## 4. Fase 0 — revisão adversarial (concluída)

O parecer foi entregue em
[CORE-SOVEREIGNTY-REVIEW.md](CORE-SOVEREIGNTY-REVIEW.md) e aceito pelo dono em
2026-10-16. Os dez ataques abaixo permanecem como registro do protocolo bloqueante;
nenhum código de produção foi alterado antes do aceite.

O agente externo **não edita código** antes de responder a esta fase. Deve tentar **derrubar** o plano, com evidência, e devolver: (a) o que derruba, (b) o que repara, (c) o que aceita.

Ataques obrigatórios:

1. **A Lei generaliza?** ADR-019 decidiu promoção; isso autoriza a lei como está escrita? Ache um contraexemplo em `packages/`.
2. **Steelman do `priceman`.** A condition technique justifica pacote de kernel hoje? Sob quais condições?
3. **O orquestrador vira god-module?** A lei "política cross-domain → orquestrador" tem teto? Como medir?
4. **O teste de soberania é tautológico?** O que exatamente ele prova?
5. **V1/V3/V4 são behavior-preserving?** Descreva o dual-run e o rollback de cada um.
6. **A Instância recria um pacote de instância pela porta dos fundos?** Onde é a fronteira config × código?
7. **O que quebra se o go-live (ADR-015, expand-contract) acontecer no meio?**
8. **Qual WP tem aceite decorativo (não falseável)?** Corrija o aceite.
9. **A taxonomia do WP-7 têm categorias mutuamente exclusivas?** Ache um arquivo que caiba em duas.
10. **O manifesto de política é verificável por máquina ou vira documentação que apodrece?**

Saída entregue: `docs/plans/CORE-SOVEREIGNTY-REVIEW.md`, com decisão do dono registrada
no próprio parecer.

### 4.1 Autoauditoria do WP-7 (ataque de mim mesmo)

| Ataque | Gravidade | Mitigação no plano |
|---|---|---|
| A classificação vira burocracia sem mudar comportamento | alta | Cada manifesto é pareado com um bug real que ele pega; o piloto `promotion` prova o ganho ou o WP é abortado |
| `policies/` colide com `rules/` e `services/` e cria um terceiro endereço | alta | Definir a diferença: `rules/` = regra config-driven avaliada; `services/` = mecanismo; `policies/` = decisão. Proibir novo módulo de política em `services/` |
| Refactor big-bang de 167 services | alta | WP-7 **não move nada**: inventário + manifestos primeiro; extração só no toque; um piloto |
| Teste de fronteira ingênuo (o orquestrador importa kernels por design) | média | Regra própria (a)(b)(c) da §5 WP-7, não a regra do kernel |
| Escopo invade o read-side | média | Read-side fica fora do WP-7; frente separada, já governada por ADR-012/014 |
| Vazamento de instância continua | média | Critério "nenhuma constante de instância" no aceite do WP-7 |
| "É mais simples?" fica só retórico | alta | Critério objetivo: o piloto deve reduzir o número de arquivos que precisam mudar para alterar a promoção |
| Micromódulos demais | média | Teto: uma política por **decisão**, não por arquivo; duas políticas com o mesmo dono são uma |

---

## 5. Work Packages

### WP-1 — Consolidar a lei e a verdade documental
- Publicar **ADR-037 — Titularidade das Decisões** (a lei da §1), preservando as
  bridges opt-in da ADR-001.
- Marcar ADR-019 como **Aceito**; atualizar a Constituição vigente em
  [§4.1 (preço)](../constitution.md#41-preço),
  [§4.2 (promessa)](../constitution.md#42-promessa) e
  [§4.3 (identidade e acesso)](../constitution.md#43-identidade-e-acesso) (filosofia do doorman).
- Corrigir drift com contagem derivada e qualificada, sem tratar toda distribuição pip como
  kernel de domínio.
- **Aceite:** nenhuma reivindicação da Constituição contradiz ADR aceita; mapa e fontes
  físicas concordam.
- **Estado:** executado em `main` pelos PRs #1843, #1844 e #1845. Isso não antecipa os WPs
  funcionais seguintes.

### WP-2 — Stockman: soberania da promessa
- Expor no stockman `decision_from_availability(info, qty, ...)` (sem segunda query).
- Orquestrador passa a **chamar**; **deletar** `shopman/shop/adapters/stock.py::promise_decision_from_availability`.
- `reason_code` vira `enum` fechado do stockman.
- `untracked` deixa de devolver `999999`. O contrato separa `available_qty` (fato
  observado, opcional) de `orderable_ceiling` (limite de política, opcional), com
  `is_tracked`, decisão e razão explícitas. `demand_ok` não transforma uma autorização
  sem teto em quantidade factual.
- Caracterizar em teste e, se útil, comparar temporariamente somente a função pura. O
  corte pré-go-live é direto para o contrato único: sem serializer legado, alias,
  dual-read/write ou segunda árvore runtime. Comparação descartável nunca duplica hold,
  ledger ou outro efeito.
- **Aceite:** teste prova que a produção chama o Stockman; busca proíbe a duplicata e
  `999999`; matriz de contrato distingue saldo factual, teto e estoque não rastreado;
  zero vocabulário/formato legado permanece no runtime.
- **Estado:** núcleo mergeado no PR #1846. O PR #1848 canonicaliza `reason_code`; depois
  dele, uma correção própria remove o dual-read/write de `Order.data.hold_ids`. WP-3 só
  começa após ambos, e só então o WP-2 está fechado sob a regra pré-go-live.

### WP-3 — Preço: um dono por decisão, um caminho canônico
- Eliminar o segundo cálculo morto em `shopman/shop/services/pricing.py::resolve`. Preço
  de lista/faixa, preço contextual e total final da cesta continuam decisões distintas,
  cada uma com seu entrypoint autoritativo; elas não viram um motor duplicado.
- Cotação contextual preserva `ContextualPrice.adjustments[]` como contrato de efeitos
  aplicados. Condições/regras de elegibilidade são insumo de decisão, não um rename de
  `adjustments`.
- `offerman` permanece dono de lista e faixas por vitrine. Promoção, cupom, segmento e
  janela são política contextual do orquestrador, aplicada pelo porto
  `OFFERMAN["PRICING_BACKEND"]`.
- O wrapper antigo tinha zero callers e era equivalente ao caminho de lista/faixa de
  `CatalogService.price`, não a `CatalogService.get_price(...).final_line_total_q`.
  O corte removeu somente essa duplicata; o caminho contextual e
  `ContextualPrice.adjustments[]` foram preservados sem perda semântica.
- **Aceite:** não existe segunda implementação da mesma decisão; toda cotação contextual
  preserva ajustes e explica o total.
- **Apêndice A** descreve o motor genérico de condições e o critério para virar pacote.
- **Estado:** implementado no PR #1851. O conteúdo da correção de repricing do PR
  #1852 já está em `main`, no merge commit `75eca4000`; o objeto do PR foi fechado
  por dessincronização do GitHub e não representa pendência técnica. O follow-up B3/B4
  está publicado no PR #1856 e
  tornou explícita a cadeia causal: a repricing correta expôs uma corrida entre revisão
  e commit; por isso o kernel, autoridade da transição Session→Order, passa a exigir um
  `CommitSeal` tipado (revisão + total + autoridade auditável) e valida ambos sob o lock.
  O status determinístico do concierge pertence ao mesmo conserto: ele representa o
  resultado concorrente sem iniciar uma segunda tentativa de pedido.
  Em `packages/orderman/shopman/orderman/tests/test_services.py`, os testes
  `test_commit_refuses_a_revision_changed_after_repricing`,
  `test_every_authority_obeys_revision_and_total_fences` e
  `test_commit_seals_commitment_evidence_in_snapshot` cobrem revisão stale, total stale,
  todas as autoridades e preservação do selo no snapshot. Bundle futuro que não puder
  compartilhar a mesma revisão e total deve ser separado antes do commit; nunca relaxa
  o selo da sessão.

### WP-4 — Doorman: porto de identidade (CIAM)
- Alargar o porto: `IdentityView` com `handles: [{kind, value, verified, primary}]` + `resolve(kind, value)`.
- Resolução `identifier`-first; remover `hasattr` e o import direto de guestman; `revoke_device` usa o cookie por sujeito.
- A bridge fica no orquestrador ou numa bridge opt-in da ADR-001; services de domínio não
  importam internals do kernel irmão. Handles são minimizados por finalidade e redigidos
  em logs.
- **Aceite:** teste de contrato com resolver fake multi-handle, provando login por handle
  secundário, primazia explícita, conflito fail-closed e revogação vinculada ao sujeito.
- **Estado:** implementado no PR #1853. O dono aprovou o expand-contract mínimo
  `OTP_EMAIL`; `EMAIL_LINK` permanece exclusivo de links e não é usado como
  substituto semântico.

### WP-5 — Políticas cross-domain: organização explícita
- Ver WP-7 (absorvido; deixa de ser item solto).

### WP-6 — Instância, Testes de contrato, Seed
- Definir o schema da **Instância** (canais, pipelines, `RuleConfig`, políticas de preço, templates, personas RBAC, unidades, perfis fiscais) e extraí-lo de `config/settings.py` + seed + DB.
- O **DB é a única verdade de runtime**. Descritor versionado, declarativo e sem secrets
  serve apenas a bootstrap/diff; apply é transacional e idempotente, dump exclui segredo e
  estado operacional, e drift é reportado em vez de corrigido silenciosamente.
- **Testes de contrato:** três suítes — soberania (pacote sem orquestrador), composição (a Instância liga kernel sem deformar) e evolução (dados do tenant sobrevivem a upgrade de pacote).
- **Seed:** passa a materializar a Instância.
- **Aceite:** uma segunda Instância mínima (ex.: só balcão) sobe o sistema sem tocar em
  pacote; precedência, conflito, rollback e exclusão de secrets têm testes.

### WP-7 — Unidades de composição do orquestrador

**Objetivo:** dar ao orquestrador a mesma disciplina conceitual do kernel.

**Manifesto verificável, antes do piloto:** cada unidade tem registro versionado, parseável
sem importar Django e validado por schema. Campos mínimos:

```
id; question; owner; responsibility; public_entrypoint; source;
touchpoints; domains; ports; events; directives; config_surface; tests
```

O gate resolve símbolos e testes, compara imports AST com domínios/portos declarados,
rejeita perguntas ou entrypoints duplicados, módulo de política sem manifesto, source órfão
e manifesto órfão. Cada tipo de falha tem fixture negativa.

**Taxonomia em dois eixos independentes:**

1. **Responsabilidade semântica:** `decisão | composição | leitura | contrato |
   configuração | infraestrutura`. Exatamente uma por unidade; `mixed` só pode aparecer
   como dívida explícita a decompor, nunca como classificação final conveniente.
2. **Mecanismo/touchpoint:** `service | adapter | handler | projection | API | admin |
   model | lifecycle | middleware | outro`. Um arquivo pode ter mais de um touchpoint.

O inventário começa pelo estado real de `shopman/shop` e registra contagens derivadas na
base do WP. Números medidos no plano original são baseline histórica, não verdade manual
permanente.

**Regra de fronteira do orquestrador (diferente da do kernel):**
- Kernel: não importa kernel; fala por porto/signal/directive.
- Orquestrador: **pode** importar vários kernels (é o único lugar onde se encontram — ADR-005 §3). O que **não** pode:
  - (a) reimplementar a decisão canônica de um kernel;
  - (b) deixar de declarar os domínios tocados no manifesto;
  - (c) expor mais de um entrypoint autoritativo para a mesma decisão.
- O gate de fronteira verifica os três itens e o manifesto é entrada verificável, não
  comentário livre.

**Sequência:**
1. Inventário sem mover código, classificado nos dois eixos.
2. Schema, manifestos verificáveis e fixtures negativas do gate.
3. Congelar cenários do piloto `promotion`, a lista atual de arquivos tocados e a métrica
   composta (soma, mediana e união dos arquivos por cenário).
4. **Piloto:** extrair a decisão pura de promoção; adapters continuam adaptando e services
   continuam orquestrando. Não mover models, migrations, Admin nem políticas fora do
   cenário congelado.
5. Enforcement: teste de fronteira + regra "política nova nasce em `policies/`".

**Critério de aborto do piloto:** abortar e reverter a extração se a métrica não melhorar,
se a redução vier apenas de façade que ainda encaminha para a dispersão anterior, se surgir
dependência circular, se o teste isolado precisar de DB/Django, ou se o manifesto não
conseguir descrever imports e entrypoint sem exceção ad hoc. Abortar o piloto aborta o WP;
o inventário e a evidência permanecem, mas não legitimam uma reorganização cosmética.

**Aceite:**
- 100% das unidades classificadas nos dois eixos; zero órfão e zero `mixed` não justificado.
- Cada política com manifesto verificável e um entrypoint canônico por decisão.
- Piloto `promotion` com teste isolado e redução material na métrica congelada; teste de
  fronteira e fixtures negativas verdes.
- `modifiers.py` deixa de crescer: nenhuma classe nova de política entra nele.
- Nenhuma constante específica de instância.

---

### WP-8 — Mapa de camadas e documentação canônica
- Declarar num único documento a hierarquia **Kernel/capacidades horizontais >
  Orquestrador > Query/read-side + Command ingress > Superfícies** (+ Instância
  transversal). API é fronteira de entrega, não superfície de produto.
- Testes de fronteira por seta: superfície não importa kernel; GET/SSE não produz efeito
  novo; command ingress delega; código de domínio de kernel não importa kernel.
- Reescrever `docs/architecture.md` e manter inventário verificável em
  `docs/architecture-map.json`.
- **Aceite:** 100% dos diretórios/apps registrados; nenhum diretório desconhecido; cada
  seta com check positivo e negativo; contagens derivadas das fontes; links/owners
  resolvem; exercícios fixos de localização encontram o dono por regra.
- **Estado:** executado em `main` pelo PR #1845; dívidas históricas ficaram em baseline
  ratchetada e não autorizam regressão.

### WP-9 — Governança: Constituição, ADRs e Docs (renascimento)
- Separar **cláusulas pétreas** (constituição curta e estável) de **ADRs** (decisões datadas e revisáveis) e de guias/referência.
- Corrigir os defeitos medidos: manter os ADRs mais antigos como 026/029 e renumerar
  somente os mais novos para 038/039; normalizar status; registrar 011 emendado por 022 e
  a cadeia real 031 → 032 → 033, sem emenda circular.
- Marcar como pétreas: 001 (Porto/Adapter), 002 (centavos), 004 (refs), 005 (orquestrador), 006 (status de Order), 007 (lifecycle config-driven), 012/014 (headless), 015 (compat pós-prod), 021 (BI read layer), 022 (ledger), 037 (titularidade).
- Índice único de ADRs com ciclo de vida: Proposto → Aceito → Substituído; dono e data.
- **Aceite:** zero número duplicado; todo ADR com status canônico; o índice responde "qual a lei e o que a revisou".
- **Estado:** executado em `main` pelos PRs #1843 e #1844.

### WP-10 — Topologia das superfícies (experiência do operador)
- Taxonomia por **trabalho/persona**, não por módulo.
- Decidir em ADR entre app único, shell + módulos ou apps separados + launcher. A baseline
  atual é federada por persona, com Central como launcher e `operator-kit` como layer;
  qualquer mudança precisa de evidência, não de preferência por monólito.
- Fechar lacunas de operação diária: catálogo, clientes, fornecedores/estoque, fechamento.
- **Kitchensink é recurso interno de Dev**: não é superfície de operador; sai dos tiles/ingress de produção e entra no registry como `internal` (decisão do dono).
- **Aceite:** registry separa público, papel, shell e deployment; toda persona alcança sua
  ferramenta com sessão coerente; instalação PWA segue o uso real; nenhum app é unido ou
  renomeado sem ADR e prova de benefício.

### WP-11 — Fronteira Admin/Unfold × Superfícies
- Regra por **frequência + público + risco**: Admin = configuração avançada, rara, destrutiva, integração, segredo, permissão, auditoria; Superfície = CRUD do dia a dia.
- Revisar a política "nasce no Admin" — ela puxou `pos`, `terminal`, `closing` e `accounts` para o Admin.
- **Aceite:** nenhuma tarefa diária mora exclusivamente no Admin.

### WP-12 — Renascimento: reorganização do repo, ADRs e docs
- Depois de WP-1..WP-11, uma passada única de reorganização: congelar a Constituição, marcar as pétreas, arquivar planos concluídos e reconstruir o índice de docs.
- **Aceite:** zero link vivo quebrado; baseline histórica de links não cresce; zero plano
  ativo arquivado; índice completo; zero contradição detectada pelo gate. Não há
  reorganização em massa por estética.

### Sequência de execução

**Fase 1** Lei e governança (ADR-037, Constituição, governança de ADRs, WP-8) →
**Fase 2** Soberania do kernel (WP-2/3/4, PRs separados) → **Fase 3** Orquestrador
(WP-7) → **Fase 4** Superfícies e Admin (**WP-11 antes de WP-10**) → **Fase 5**
Instância e contratos (WP-6) → **Fase 6** Renascimento (WP-12).

Missão completa do agente externo em [CORE-SOVEREIGNTY-MISSION.md](CORE-SOVEREIGNTY-MISSION.md).

## 6. Cercas (não fazer)

- Não criar pacote de kernel novo sem **2+ consumidores reais** (ADR-001).
- Não transformar composição/política em pacotes pip: elas vivem no orquestrador (ADR-005 §3).
- Não colocar verbo de domínio de um único domínio no orquestrador.
- Não importar model de um kernel dentro de outro kernel.
- Não mexer em migração de kernel antes da lei (WP-1). Antes de `go-live-v1`, não criar
  compatibilidade runtime; depois da tag, toda evolução persistida segue a ADR-015.
- Não renomear app/pacote por estética enquanto houver decisão dividida.
- Não reescrever lógica: os movimentos são de **titularidade**.

---

## 7. Critérios de aceite globais

1. **Soberania:** cada pacote alvo constrói e instala seu wheel em ambiente limpo, sem
   `django-shopman` nem kernels irmãos, e passa sua suíte/contrato público.
2. **Um dono por decisão:** não existe segunda implementação da mesma decisão.
3. **Contrato explícito:** toda decisão devolve objeto com razão e efeitos aplicados; nada
   de `bool`/`float`/sentinela. Preço contextual preserva `adjustments[]`.
4. **Fronteira:** código de domínio kernel→kernel é proibido; bridges da ADR-001 são lazy,
   opt-in e nomeadas; command/query ingress não decide.
5. **Localidade:** o cenário congelado de mudança toca uma unidade de política + testes e
   melhora a métrica de acoplamento, não só a aparência do caminho.
6. **Regime de corte:** antes de `go-live-v1`, comparação só de cálculo puro e
   descartável, seguida de corte único sem legado. Depois da tag, evolução de contrato
   segue expand-contract e caminho de volta conforme ADR-015.

---

## 8. Decisões encerradas e perguntas abertas

**Encerradas pelo aceite da Fase 0:** não há `priceman` agora; DB é a verdade de runtime e
o descritor serve a bootstrap/diff; unidades de composição não viram pacote pip; API é
fronteira de entrega; preço contextual preserva `adjustments[]`; disponibilidade separa
fato (`available_qty`) de política (`orderable_ceiling`).

- P2: o `Quote` nasce em `utils` (contrato transversal) ou no pacote que o emite?
- P5: qual o teto de tamanho do orquestrador antes de virar god-module — e como medir?
- P7: o read-side ganha a mesma taxonomia? (frente separada; ADR-012/014 já governa)
**Decisões registradas:**

- **P1 — motor de condições virar pacote?** Decisão: **não agora**. Extração só quando
  (a) o motor não tiver vocabulário de outro domínio, (b) houver 2+ consumidores reais
  independentes e (c) o ruleset não couber mais em código. O contrato vigente continua
  `ContextualPrice.adjustments[]`.
- **P3 — quem declara o porto de identidade?** **Doorman**, porque é o consumidor da
  decisão de autenticação e deve declarar o contrato mínimo que necessita. Guestman
  implementa esse porto na bridge opt-in `shopman/guestman/adapters/auth.py`; nenhum dos
  dois kernels importa internals do outro.
- **P4 — a Instância é arquivo ou DB?** **DB é a verdade de runtime**; um descritor versionado (YAML/JSON) serve para bootstrap e diff (`instance-apply` / `instance-dump`). Nunca duas verdades.
- **P6 — unidades de composição viram pacotes?** **Não**. Elas vivem no orquestrador (ADR-005 §3). Pacote só para domínio com invariante/ledger próprio (ADR-022).


---

## 9. Protocolo do executor

1. **Worktree próprio antes do primeiro edit** (regra do `CLAUDE.md`). Este plano vive em `plan/core-sovereignty`.
2. Ler `docs/constitution.md`, ADR-001, ADR-005, ADR-019, ADR-021, ADR-022, `CORE-BOUNDARIES-AUDIT.md` e este plano.
3. **Fase 0 primeiro**, com parecer em arquivo; concluída e aceita em 2026-10-16.
4. Um WP por PR; aceite do WP no corpo do PR; `make test` + `make admin` conforme o escopo.
5. Não commitar no checkout principal; `git add` só de arquivo nomeado.
6. Publicar (esteira do AGENTS.md): commit + push + PR (draft enquanto a Fase 0 não foi aceita). Frente não termina dormente.

---

## Apêndice A — Motor genérico de condições (direção, não hoje)

O que falta tem nome de indústria: **condition technique** (SAP). Em vez de `if` de promoção espalhado, separam-se **dados** de **procedimento**:

- **Condition type** — categoria + cálculo (percentual, valor, escala), sinal, arredondamento.
- **Condition record** — o valor vigente para uma chave (SKU/cliente/canal/data).
- **Access sequence** — a ordem de busca do registro.
- **Pricing procedure** — a sequência ordenada de steps, com requisitos, subtotais e exclusões.
- **Scales** — faixas por quantidade/valor; **exclusion groups** — regras de não-cumulatividade.

Direção conceitual do motor: `quote(request, procedure) -> resultado` com regras de
elegibilidade separadas dos efeitos aplicados. Na API vigente, esses efeitos continuam
nomeados em `ContextualPrice.adjustments[]`; este apêndice não autoriza rename de contrato.

O `django-salesman` é o ancestral direto do `modifiers.py`: `SALESMAN_BASKET_MODIFIERS` é uma lista **ordenada** de `BasketModifier`, cada um com `identifier` e `add_extra_row`. Dele, aproveitar **ordem + identificador + linha visível**; não aproveitar o "tudo num arquivo de modifiers", que é justamente a origem do god-file.

**Critério para virar pacote de kernel** (e não antes): (a) pergunta canônica própria; (b) nenhum vocabulário estrangeiro no motor; (c) 2+ consumidores/implementações reais; (d) o ruleset do deployment deixou de caber em código fixo. Hoje nenhum dos quatro vale — por isso a política de preço fica no orquestrador, sem pacote novo e sem substituir `ContextualPrice.adjustments[]`.
