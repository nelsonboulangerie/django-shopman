# CORE-SOVEREIGNTY-PLAN — Titularidade e Soberania

> **Status:** proposta para **revisão adversarial bloqueante** (Fase 0 pendente).
> **Base:** `main @ 35d95104d`. Linhas citadas medidas nessa revisão; revalidar antes de editar.
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

## 1. A Lei da Titularidade (proposta de ADR-035)

> **A pergunta canônica de um domínio pertence ao pacote daquele domínio. A política que compõe dois ou mais domínios pertence ao orquestrador. Nenhum dos dois invade o outro.**

> **Precedente:** este critério já está em uso. `CORE-BOUNDARIES-AUDIT.md` (2026-08-18) aplica marcas equivalentes — (a) model com invariante vivendo em superfície/orquestrador, (b) alcançado por adapter de uma impl só, (c) estado de domínio em JSON alheio, (d) mesma pergunta com vários donos, (e) política transversal legítima do orquestrador — e conclui "default = fica". Esta lei **consolida** esse método com ADR-005 §3, ADR-019 e ADR-022 num único ADR; **não** é doutrina nova.

Corolários operacionais:

1. **Uma pergunta, um dono, um ponto de entrada público.** Para a pergunta canônica do pacote existe exatamente um verbo público, que devolve um objeto de decisão completo (não um `bool` nem um `float` solto).
2. **Teste do vocabulário estrangeiro.** Se um model/regra precisa de campos de três domínios diferentes, ele **não** pertence a um pacote de kernel — pertence ao orquestrador. (Precedente: ADR-019.)
3. **Teste do ledger.** Domínio que possui **livro imutável** (história de fatos) é pacote. Política computada sobre estados alheios é orquestrador. (Precedente: ADR-022, que contrasta explicitamente com ADR-019.)
4. **O orquestrador pode ser denso; não pode ser dono do verbo de um único domínio.** Ele é dono de **composição** e de **política cross-domain** — isso não é acoplamento indevido (ADR-005 §3).
5. **Fronteira é contrato, não import.** Nenhum kernel importa outro kernel. Toda conversa passa por porto (Protocol/view), evento (signal) ou comando durável (Directive).

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
| Pacotes de domínio | **Kernel** | `packages/*` (12 pacotes pip) |
| Composição + política | **Orquestrador** | `shopman/shop` (app Django, `label="shop"`) |
| Configuração do negócio | **Instância** | `config/` + linhas no DB |
| Dados de exemplo | **Seed** | `config/management/commands/seed.py` |
| Interfaces entre pacotes | **Contratos / portas** | `protocols.py`, `Protocol` |
| Verificação de contrato | **Testes de contrato** | `tests/` |

> Os nomes "canteiro", "projeto", "gabarito" e "maquete" usados em rascunhos anteriores eram analogia, não conceito. **Estão retirados.**

### 2.2 Camadas completas (write-side e read-side)

O read-side tem estrutura própria e não pode ficar fora do mapa (ADR-012, ADR-014):

```
Kernel (decisões de domínio, ledgers)          packages/*
   ↓ portas / services
Orquestrador (composição + política)           shopman/shop
   ↓ chamadas / directives
Read-side (Projections + API)                  shop/projections, storefront/presentation+api,
                                               backstage/projections+api
   ↓ HTTP / SSE                                  (ADR-012: Projection com Actions)
Superfícies (Nuxt)  +  Admin/Unfold            surfaces/* (9 apps + operator-kit + operator-router)
Instância = config/ + DB + marca               parametriza tudo acima
```

Ordem de grandeza (main): `shopman/shop/projections` 21, `shopman/backstage/projections` 54, `shopman/backstage/api` 40, `shopman/storefront/presentation` 21, `shopman/storefront/api` 20, `shopman/shop/admin` 14, 13 arquivos de template/static.

**Projeção é mecanismo de leitura, não política.** A política pode exigir uma projeção, mas a projeção não é o lugar da decisão.
**Regras de dependência (seta única, testada):**

- **Superfícies** (Nuxt) → só falam HTTP/SSE com o read-side; nunca importam kernel nem orquestrador.
- **Read-side** → lê do orquestrador/kernel; **nunca escreve decisão**.
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
| "onde fica a tela da sacola?" | Superfície |
| "qual o horário da loja?" | Instância |


### 2.3 O que é invariante entre instâncias

Confirmações explícitas:

- **Shopman é o orquestrador.** Ele usa os pacotes de domínio para fazer os domínios interagirem corretamente.
- **O código do orquestrador é um só.** Ele não muda de instância para instância.
- **Ele não é determinado pelas regras do negócio.** Quem o caracteriza é a Instância (config + DB + marca + settings).
- **Composição e política hoje NÃO são pacotes separados** — são módulos dentro do orquestrador. Criar pacote pip para elas violaria o critério "2+ consumidores reais" e a ADR-005 §3 (é no orquestrador que domínios se encontram).

**Resíduo medido:** o princípio é honrado, mas há vazamento a zerar — p.ex. `DEFAULT_EMPLOYEE_DISCOUNT_PERCENT`, `DEFAULT_TIME_WINDOW_START` e afins em `shopman/shop/modifiers.py` (política como constante de código). Nomes da instância em docstrings/comentários são prosa, não vazamento.

**Aceite (entra no WP-7):** nenhuma constante/prefijo/domínio específico de instância no código; tudo via settings, `Shop.defaults`, `RuleConfig` ou `ChannelConfig` (constituição §2.6).

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
| V3 | "Disponibilidade ilusória": sentinela `999999` e três representações de *untracked* | `shopman/shop/services/availability.py` l. 486–493; `shopman/storefront/presentation/catalog.py` (`None = untracked`); `shopman/shop/services/stock.py` (`untracked: True`) | `available_qty=None` + `is_tracked=False`; `demand_ok` não sintetiza quantidade |
| V4 | Dois caminhos de preço; um morto | `shopman/shop/services/pricing.py` `resolve` (l. 16) → `CatalogService.price` (lista) vs `shopman/shop/projections/catalog_context.py` `contextual_price` → `CatalogService.get_price` (com promoção) | Um verbo, um caminho |
| V5 | Constituição reivindica "pricing core" para offerman; ADR-019 decidiu o contrário | `docs/constitution.md` l. 193, 195, 1063 vs ADR-019 §1 | Atualizar §4.1 |
| V6 | Doorman importa guestman direto e engole a falha | `packages/doorman/.../services/verification.py` l. 553–556 + `except Exception` | Porto de identidade; sem import direto |
| V7 | Porto de identidade pobre (perde handle/primazia/verificação) | `packages/doorman/.../protocols/customer.py` `AuthCustomerInfo` (l. 9); resolução binária `target_kind` (l. 108) | Alargar o porto (CIAM) |
| V8 | Governança: ADR-019 está `Proposto` mas implementado | `docs/decisions/adr-019-*.md` `Status:` (l. 3) | Marcar Aceito |
| V9 | Drift de docs: README diz 11 pacotes (são 12) e architecture.md diz 9 apps (são 12); superfícies batem (9 + registry) | `README.md` l. 19, `docs/architecture.md`; `surfaces/registry.json` é a fonte | Atualizar no WP-1 |
| V10 | **Orquestrador sem unidade conceitual**: organização por mecanismo + 49 arquivos na raiz; decisões espalhadas | ver §5 WP-7 (inventário medido) | WP-7 |

---

## 4. Fase 0 — revisão adversarial (bloqueante)

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

Saída esperada: `docs/plans/CORE-SOVEREIGNTY-REVIEW.md` + decisão do dono.

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
- Propor **ADR-035 — Titularidade das Decisões** (a lei da §1).
- Marcar ADR-019 como **Aceito**; atualizar `docs/constitution.md` §4.1 (pricing), §4.2 (promessa) e §4.7 (filosofia do doorman).
- Corrigir drift: `README.md` (11→12 pacotes), `docs/architecture.md`.
- **Aceite:** nenhuma reivindicação da constituição contradiz ADR aceito; contagem de pacotes bate com `packages/`.

### WP-2 — Stockman: soberania da promessa
- Expor no stockman `decision_from_availability(info, qty, ...)` (sem segunda query).
- Orquestrador passa a **chamar**; **deletar** `shopman/shop/adapters/stock.py::promise_decision_from_availability`.
- `reason_code` vira `enum` fechado do stockman.
- `untracked` deixa de devolver `999999`; `demand_ok` deixa de sintetizar quantidade.
- **Aceite:** teste prova que a produção chama o stockman; teste de grep proíbe a duplicata; representação única de `untracked`.

### WP-3 — Preço: um verbo, um caminho
- Um único ponto público de preço. Matar/redirecionar `shopman/shop/services/pricing.py::resolve`.
- Toda cotação devolve `Quote`/`ContextualPrice` com `conditions[]`.
- `offerman` permanece dono de lista e faixas por vitrine; política entra pelo porto `OFFERMAN["PRICING_BACKEND"]`.
- **Aceite:** não existe segundo caminho; toda cotação diz por quê.
- **Apêndice A** descreve o motor genérico de condições e o critério para virar pacote.

### WP-4 — Doorman: porto de identidade (CIAM)
- Alargar o porto: `IdentityView` com `handles: [{kind, value, verified, primary}]` + `resolve(kind, value)`.
- Resolução `identifier`-first; remover `hasattr` e o import direto de guestman; `revoke_device` usa o cookie por sujeito.
- **Aceite:** teste de contrato com resolver fake multi-handle, provando login por handle secundário e primazia explícita.

### WP-5 — Políticas cross-domain: organização explícita
- Ver WP-7 (absorvido; deixa de ser item solto).

### WP-6 — Instância, Testes de contrato, Seed
- Definir o schema da **Instância** (canais, pipelines, `RuleConfig`, políticas de preço, templates, personas RBAC, unidades, perfis fiscais) e extraí-lo de `config/settings.py` + seed + DB.
- **Testes de contrato:** três suítes — soberania (pacote sem orquestrador), composição (a Instância liga kernel sem deformar) e evolução (dados do tenant sobrevivem a upgrade de pacote).
- **Seed:** passa a materializar a Instância.
- **Aceite:** uma segunda Instância mínima (ex.: só balcão) sobe o sistema sem tocar em pacote.

### WP-7 — Unidades de composição do orquestrador

**Objetivo:** dar ao orquestrador a mesma disciplina conceitual do kernel.

**Unidade de composição (cabeçalho obrigatório):**

```
Unidade de composição
- nome / pergunta canônica
- verbo(s) público(s)           (um ponto de entrada)
- domínios tocados              (manifesto: offerman × guestman × orderman)
- portas usadas                 (contratos, nunca models de kernel alheios)
- eventos/directives emitidos
- superfície de configuração    (o que a Instância pode mudar)
- testes                       (isolado + contrato)
```

**Taxonomia — todo arquivo de `shopman/shop` tem exatamente uma categoria:**

1. **Unidade de composição** (decisão/política) → `shopman/shop/policies/`
2. **Mecanismo** (adapter, handler, projection, lifecycle, middleware) — sem decisão
3. **Contrato** (protocol, value object)
4. **Leitura** (projection/API/presentation)
5. **Configuração da instância** (`ChannelConfig`, `Shop.defaults`, derivados)
6. **Infraestrutura** (checks, telemetria, logging, migration safety, admin, views)

**Inventário medido (main):** 49 arquivos `.py` na raiz do app; `services/` 167; `adapters/` 52; `handlers/` 39; `projections/` 21; `models/` 23; `rules/` 7. God-files: `modifiers.py` 1491, `checks.py` 1366, `lifecycle.py` 1272, `config.py` 669.

**Regra de fronteira do orquestrador (diferente da do kernel):**
- Kernel: não importa kernel; fala por porto/signal/directive.
- Orquestrador: **pode** importar vários kernels (é o único lugar onde se encontram — ADR-005 §3). O que **não** pode:
  - (a) reimplementar a decisão canônica de um kernel;
  - (b) deixar de declarar os domínios tocados no manifesto;
  - (c) expor mais de um verbo para a mesma decisão.
- Um teste de fronteira verifica (a) e (c); o manifesto verifica (b).

**Sequência:**
1. Inventário + classificação dos 49 arquivos de raiz (sem mover nada).
2. Manifestos das políticas existentes (pricing, promotion, availability, fulfillment, loyalty, tax, marketing, ifood, kds).
3. **Piloto:** extrair `promotion` (já tem `services/promotions.py` + `modifiers.py` + `adapters/pricing.py`) e provar a redução de arquivos-a-mudar.
4. Enforcement: teste de fronteira + regra "política nova nasce em `policies/`".

**Aceite:**
- 100% dos arquivos classificados; zero sem categoria.
- Cada política com manifesto e um verbo.
- Piloto `promotion` com teste isolado; teste de fronteira verde.
- `modifiers.py` deixa de crescer: nenhuma classe nova de política entra nele.
- Nenhuma constante específica de instância.

---

### WP-8 — Mapa de camadas e documentação canônica
- Declarar num único documento a hierarquia **Kernel > Orquestrador > Read-side > Superfícies** (+ Instância transversal).
- Testes de fronteira por seta: superfície não importa kernel; read-side não escreve; kernel não importa kernel.
- Reescrever `docs/architecture.md` como o mapa; corrigir contagem de pacotes e apps.
- **Aceite:** um dev localiza qualquer artefato pelo mapa; testes de fronteira verdes.

### WP-9 — Governança: Constituição, ADRs e Docs (renascimento)
- Separar **cláusulas pétreas** (constituição curta e estável) de **ADRs** (decisões datadas e revisáveis) e de guias/referência.
- Corrigir os defeitos medidos: números duplicados (`adr-026` ×2, `adr-029` ×2), status divergente (Aceito/Accepted/aceito; Proposto em ADR já implementado), supersessões não marcadas (011, 031, 032).
- Marcar como pétreas: 001 (Porto/Adapter), 002 (centavos), 004 (refs), 005 (orquestrador), 006 (status de Order), 007 (lifecycle config-driven), 015 (compat pós-prod), 021 (BI read layer), 022 (ledger), 035 (titularidade).
- Índice único de ADRs com ciclo de vida: Proposto → Aceito → Substituído; dono e data.
- Reorganizar a árvore de docs (uma fonte por tema) e aposentar o que está stale.
- **Aceite:** zero número duplicado; todo ADR com status canônico; o índice responde "qual a lei e o que a revisou".

### WP-10 — Topologia das superfícies (experiência do operador)
- Taxonomia por **trabalho/persona**, não por módulo.
- Decidir em ADR entre: app único; shell + módulos; apps separados + shell. Recomendação preliminar: **shell único + áreas**, com kiosk standalone e PWA por área.
- Fechar lacunas de operação diária: catálogo, clientes, fornecedores/estoque, fechamento.
- **Kitchensink é recurso interno de Dev**: não é superfície de operador; sai dos tiles/ingress de produção e entra no registry como `internal` (decisão do dono).
- **Aceite:** o operador entra num lugar e chega a qualquer ferramenta com um login; cada área é instalável como PWA quando fizer sentido.

### WP-11 — Fronteira Admin/Unfold × Superfícies
- Regra por **frequência + público + risco**: Admin = configuração avançada, rara, destrutiva, integração, segredo, permissão, auditoria; Superfície = CRUD do dia a dia.
- Revisar a política "nasce no Admin" — ela puxou `pos`, `terminal`, `closing` e `accounts` para o Admin.
- **Aceite:** nenhuma tarefa diária mora exclusivamente no Admin.

### WP-12 — Renascimento: reorganização do repo, ADRs e docs
- Depois de WP-1..WP-11, uma passada única de reorganização: congelar a Constituição, marcar as pétreas, arquivar planos concluídos e reconstruir o índice de docs.
- **Aceite:** repo navegável pela hierarquia declarada; nenhuma doc contradiz ADR aceito.

### Sequência de execução

**Fase 1** Lei e governança (ADR-035, Constituição, governança de ADRs, WP-8) → **Fase 2** Soberania do kernel (WP-2/3/4) → **Fase 3** Orquestrador (WP-7) → **Fase 4** Superfícies e Admin (WP-10/11) → **Fase 5** Instância e contratos (WP-6) → **Fase 6** Renascimento (WP-12).

Missão completa do agente externo em [CORE-SOVEREIGNTY-MISSION.md](CORE-SOVEREIGNTY-MISSION.md).

## 6. Cercas (não fazer)

- Não criar pacote de kernel novo sem **2+ consumidores reais** (ADR-001).
- Não transformar composição/política em pacotes pip: elas vivem no orquestrador (ADR-005 §3).
- Não colocar verbo de domínio de um único domínio no orquestrador.
- Não importar model de um kernel dentro de outro kernel.
- Não mexer em migração de kernel antes da lei (WP-1) e sem expand-contract (ADR-015).
- Não renomear app/pacote por estética enquanto houver decisão dividida.
- Não reescrever lógica: os movimentos são de **titularidade**.

---

## 7. Critérios de aceite globais

1. **Soberania:** cada pacote alvo passa a suíte com o orquestrador desinstalado.
2. **Um dono por decisão:** não existe segunda implementação da mesma decisão.
3. **Contrato explícito:** toda decisão devolve objeto com razão/condições; nada de `bool`/`float`/sentinela.
4. **Fronteira:** nenhum import kernel→kernel fora de porto; nenhum import orquestrador→model de kernel fora de adaptador.
5. **Localidade:** mudar uma política toca um módulo.
6. **Reversível:** cada movimento tem dual-run e caminho de volta.

---

## 8. Perguntas abertas

- P1: um `priceman` passa a valer a pena a partir de quantos tipos de condição? Qual o gatilho?
- P2: o `Quote` nasce em `utils` (contrato transversal) ou no pacote que o emite?
- P3: `IdentityView` é contrato no doorman ou no guestman? Quem declara o porto?
- P4: a Instância é arquivo versionado, dados no DB, ou ambos com precedência definida?
- P5: qual o teto de tamanho do orquestrador antes de virar god-module — e como medir?
- P6: unidades de composição viram pacotes pip algum dia? (preliminar: não; ADR-005/019/022)
- P7: o read-side ganha a mesma taxonomia? (frente separada; ADR-012/014 já governa)
**Recomendações (para o dono decidir):**

- **P1 — motor de condições virar pacote?** Recomendação: **não agora**. Definir o contrato `Quote { base, conditions[], total }` já; extrair para pacote só quando (a) o motor não tiver vocabulário de outro domínio, (b) houver 2+ consumidores reais, (c) o ruleset não couber mais em código.
- **P4 — a Instância é arquivo ou DB?** Recomendação: **DB é a verdade de runtime**; um descritor versionado (YAML/JSON) serve para bootstrap e diff (`instance-apply` / `instance-dump`). Nunca duas verdades.
- **P6 — unidades de composição viram pacotes?** Recomendação: **não**. Elas vivem no orquestrador (ADR-005 §3). Pacote só para domínio com invariante/ledger próprio (ADR-022).


---

## 9. Protocolo do executor

1. **Worktree próprio antes do primeiro edit** (regra do `CLAUDE.md`). Este plano vive em `plan/core-sovereignty`.
2. Ler `docs/constitution.md`, ADR-001, ADR-005, ADR-019, ADR-021, ADR-022, `CORE-BOUNDARIES-AUDIT.md` e este plano.
3. **Fase 0 primeiro**, com parecer em arquivo; aguardar aceite do dono.
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

Contrato genérico: `quote(request, procedure) -> Quote { base, conditions[], total }`, com condições aplicadas nomeadas (auditoria e explicação na tela).

O `django-salesman` é o ancestral direto do `modifiers.py`: `SALESMAN_BASKET_MODIFIERS` é uma lista **ordenada** de `BasketModifier`, cada um com `identifier` e `add_extra_row`. Dele, aproveitar **ordem + identificador + linha visível**; não aproveitar o "tudo num arquivo de modifiers", que é justamente a origem do god-file.

**Critério para virar pacote de kernel** (e não antes): (a) pergunta canônica própria; (b) nenhum vocabulário estrangeiro no motor; (c) 2+ consumidores/implementações reais; (d) o ruleset do deployment deixou de caber em código fixo. Hoje nenhum dos quatro vale — por isso o preço fica no orquestrador, com o contrato `Quote/conditions[]` definido **desde já**.
