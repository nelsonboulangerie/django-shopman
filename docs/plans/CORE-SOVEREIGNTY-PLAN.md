# CORE-SOVEREIGNTY-PLAN — Titularidade e Soberania do Core

> **Status:** proposta para **revisão adversarial bloqueante** (Fase 0 pendente).
> **Base:** `main @ 35d95104d`. Linhas citadas medidas nessa revisão; revalidar antes de editar.
> **Natureza:** plano de **fronteira**, não de feature. Nenhuma capacidade nova é pedida.
> **Autor:** sessão de arquitetura (DSH), a partir de leitura de `packages/*`, `shopman/shop` e ADRs.

---

## 0. Intenção

O objetivo do projeto é um conjunto de pacotes de kernel **minimalistas, flexíveis e agnósticos**, cada um respondendo de forma soberana a **uma pergunta de domínio**, e uma camada de composição capaz de montar operações comerciais densas **sem deformar nenhum tijolo**.

Este plano existe porque há uma **incoerência de titularidade** — não de capacidade. Decisões de domínio carregam dois donos: o pacote que as nomeia e o canteiro que as executa. A consequência prática não é estética: é que **toda mudança de requisito vira edição coordenada em dois lugares**, e a operação não pode parar.

**Não-objetivos** (explicitamente fora de escopo):

- distribuição/adoção externa como critério de sucesso;
- paridade de features com PIM/WMS/ERP/allauth;
- criar pacote novo "para o futuro";
- reescrita. A lógica já existe; o que muda é **quem é o dono**.

---

## 1. A Lei da Titularidade (proposta de ADR)

> **A pergunta canônica de um domínio pertence ao pacote daquele domínio. A política que compõe dois ou mais domínios pertence ao canteiro. Nenhum dos dois invade o outro.**

> **Precedente:** este critério já está em uso. `CORE-BOUNDARIES-AUDIT.md` (2026-08-18) aplica marcas equivalentes — (a) model com invariante vivendo em superfície/orquestrador, (b) alcançado por adapter de uma impl só, (c) estado de domínio em JSON alheio, (d) mesma pergunta com vários donos, (e) política transversal legítima do canteiro — e conclui "default = fica". Esta lei **consolida** esse método com ADR-005 §3, ADR-019 e ADR-022 num único ADR; **não** é doutrina nova.

Corolários operacionais:

1. **Uma pergunta, um dono, um ponto de entrada público.** Para a pergunta canônica do pacote existe exatamente um verbo público, que devolve um objeto de decisão completo (não um `bool` nem um `float` solto).
2. **Teste do vocabulário estrangeiro.** Se um model/regra precisa de campos de três domínios diferentes, ele **não** pertence a um pacote de kernel — pertence ao canteiro. (Precedente: ADR-019.)
3. **Teste do ledger.** Domínio que possui **livro imutável** (história de fatos) é pacote. Política computada sobre estados alheios é canteiro. (Precedente: ADR-022, que contrasta explicitamente com ADR-019.)
4. **O canteiro pode ser denso; não pode ser dono do verbo de um único domínio.** Ele é dono de **composição** e de **política cross-domain** — e isso não é acoplamento indevido (ADR-005 §3).
5. **Fronteira é contrato, não import.** Nenhum kernel importa outro kernel. Toda conversa passa por porto (Protocol/view), evento (signal) ou comando durável (Directive).

### Composição × Política (a distinção que autoriza o canteiro)

- **Composição** = *quem, quando, em que ordem*. Liga portas e sequencia domínios. Não contém regra de negócio própria; mudar = reordenar/reconfigurar pipeline.
  - Ex.: `on_confirmed` → `stock.hold` → `payment.capture` → `notification.send`.
- **Política** = *regra que só existe porque dois domínios se encontram*. É regra de negócio; mora em módulo nomeado, versionado e testado.
  - Ex.: "promoção vale só na web, para aniversariantes, com pedido mínimo, e zera o frete" compõe offerman × guestman × orderman.

Precedentes de indústria em que a política cross-domain é **externalizada** (a favor de modularizá-la, não de escondê-la): condition technique do SAP; Shopify Discount/Shipping Functions; Stripe Radar (risco = pagamento × cliente × pedido); Avalara/Stripe Tax (tributo = produto × endereço × cliente). Em todos, o motor é um **domínio de política** com dados + procedimento, não um `if`.

---

## 2. Camadas e vocabulário

Nomes de trabalho (conceituais; **não** exigem rename físico agora):

| Camada | Nome proposto | Onde vive hoje | Muda com que frequência |
|---|---|---|---|
| Tijolos/ferramentas | **Kernel** | `packages/*` (12 pacotes pip) | devagar — contrato, migração |
| Composição + política | **Canteiro** | `shopman/shop/` (app Django `label="shop"`) | por release — fiação |
| Planta do tenant | **Projeto** | `config/` + linhas de DB (Channel/RuleConfig/OmotenushiCopy…) | no dia — config |
| Dados de exemplo | **Maquete** | `config/management/commands/seed.py` | quando há demo/QA |
| Kit de conformidade | **Gabarito** | (a criar) testes de soberania/composição/evolução | por contrato |

> Alternativas de nome para o canteiro: **Ateliê** (artesanal), **Oficina**, **Estaleiro**. Recomendação: **Canteiro** (casa com tijolos/ferramentas/planta). Para `planta`: **Projeto** (o desenho completo); "planta" fica como sinônimo.

### O que é "Shopman", tecnicamente

Não existem dois apps Django. Existe:

- `django-shopman` — a **distribuição** (`pyproject.toml`);
- `shopman/` — o **namespace** (PEP 420);
- `shopman/shop/` — **um** app Django: `AppConfig = ShopmanConfig`, `name = "shopman.shop"`, `label = "shop"`;
- `Shop` — um **model** dentro desse app (o singleton da empresa/tenant);
- `config/` — o **projeto Django** desta instalação (settings, urls, seed).

Logo: **Shopman** = o ecossistema (kernel + canteiro + projeto + gabarito). **Shop** = o app do canteiro. São o mesmo app com nome de classe e label diferentes — origem da confusão.

---

## 3. Diagnóstico — o que viola a lei hoje (base `main`)

| # | Violação | Evidência (símbolo) | Movimento |
|---|---|---|---|
| V1 | Decisão de promessa **duplicada**; produção usa a cópia do canteiro | `shopman/shop/adapters/stock.py` `promise_decision_from_availability` (l. 974) vs `packages/stockman/.../services/availability.py` `promise_decision_for_sku` (l. 295); chamada em `shopman/shop/services/availability.py` (l. 496) | Repatriar (expor `decision_from_availability` no stockman; deletar cópia) |
| V2 | Vocabulário de negação fragmentado, sem enum | stockman `insufficient_supply` (l. 334); canteiro `insufficient_stock` (l. 505, 878, 938, 1296, 1327), `not_in_listing`, `paused` | Fechar `ReasonCode` no stockman; canteiro só compõe |
| V3 | "Disponibilidade ilusória": sentinela `999999` e três representações de *untracked* | `shopman/shop/services/availability.py` l. 486–493; `shopman/storefront/presentation/catalog.py` (`None = untracked`); `shopman/shop/services/stock.py` (`untracked: True`) | `available_qty=None` + `is_tracked=False`; `demand_ok` não sintetiza quantidade |
| V4 | Dois caminhos de preço; um morto | `shopman/shop/services/pricing.py` `resolve` (l. 16) → `CatalogService.price` (lista) vs `shopman/shop/projections/catalog_context.py` `contextual_price` → `CatalogService.get_price` (com promoção) | Um verbo, um caminho |
| V5 | Constituição reivindica "pricing core" para offerman; ADR-019 decidiu o contrário | `docs/constitution.md` l. 193, 195, 1063 vs ADR-019 §1 | Atualizar §4.1 |
| V6 | Doorman importa guestman direto e engole a falha | `packages/doorman/.../services/verification.py` l. 553–556 + `except Exception` | Porto de identidade; sem import direto |
| V7 | Porto de identidade pobre (perde handle/primazia/verificação) | `packages/doorman/.../protocols/customer.py` `AuthCustomerInfo` (l. 9); resolução binária `target_kind` (l. 108) | Alargar o porto (CIAM) |
| V8 | Governança: ADR-019 está `Proposto` mas implementado | `docs/decisions/adr-019-*.md` `Status:` (l. 3) | Marcar Aceito |
| V9 | Drift de docs: README diz 11 pacotes (são 12) e architecture.md diz 9 apps (são 12); superfícies batem (9 + registry) | `README.md` l. 19, `docs/architecture.md`; `surfaces/registry.json` é a fonte | Atualizar no WP-1 |

---

## 4. Fase 0 — Revisão adversarial (bloqueante)

O agente externo **não edita código** antes de responder a esta fase. Ele deve tentar **derrubar** o plano, com evidência, e devolver: (a) o que derruba, (b) o que repara, (c) o que aceita.

Ataques obrigatórios:

1. **A Lei generaliza?** ADR-019 decidiu promoção; isso autoriza a lei como está escrita? Ache um contraexemplo em `packages/`.
2. **Steelman do `priceman`.** A condition technique justifica pacote de kernel hoje? Sob quais condições?
3. **O canteiro vira deus?** A lei "política cross-domain → canteiro" tem limite de tamanho/complexidade? Qual?
4. **O teste de soberania é tautológico?** Um teste que passa sem o canteiro prova o quê, exatamente?
5. **Os três movimentos são behavior-preserving?** Qual o plano de *dual-run* e de reversão?
6. **O Projeto recria um pacote de instância pela porta dos fundos?** Onde está a fronteira entre "config" e "código"?
7. **O que quebra se o go-live ocorrer no meio?** ADR-015 (expand-contract) muda o sequenciamento?
8. **Cada WP tem aceite falseável?** Aponte o WP cujo aceite é decorativo.

Saída esperada da Fase 0: `docs/plans/CORE-SOVEREIGNTY-REVIEW.md` (parecer) + decisão do dono sobre seguir/ajustar.

---

## 5. Work Packages

### WP-1 — Consolidar a lei e a verdade documental
- Propor **ADR-035 — Titularidade das Decisões** (a lei da §1).
- Marcar ADR-019 como **Aceito**; atualizar `docs/constitution.md` §4.1 (pricing), §4.2 (promessa) e §4.7 (filosofia do doorman) para não contradizer ADR aceito.
- Corrigir drift: `README.md` (11→12 pacotes), `docs/status.md` (superfícies), `docs/architecture.md` (marcar/atualizar).
- **Aceite:** nenhuma reivindicação da constituição contradiz ADR aceito; `grep` de contagem de pacotes bate com `packages/`.

### WP-2 — Stockman: soberania da promessa
- Expor no stockman uma função de decisão a partir de snapshot já carregado (sem segunda query): `decision_from_availability(info, qty, ...)` ou equivalente.
- Canteiro passa a **chamar** o stockman; **deletar** `shopman/shop/adapters/stock.py::promise_decision_from_availability`.
- `reason_code` vira `enum` fechado do stockman; canteiro pode **compor** contexto, não inventar literal.
- `untracked` deixa de devolver `999999`; `demand_ok` deixa de sintetizar quantidade.
- **Aceite:** teste prova que a produção chama o stockman; teste de grep proíbe a duplicata; o payload de `untracked` tem uma única representação.

### WP-3 — Preço: um verbo, um caminho
- Um único ponto público de preço. Matar/redirecionar `shopman/shop/services/pricing.py::resolve` (sem consumidor real).
- Toda cotação devolve `Quote`/`ContextualPrice` com `conditions[]` (por quê do preço).
- `offerman` permanece dono de **lista e faixas por vitrine**; a política contextual entra pelo porto que ele já declara (`OFFERMAN["PRICING_BACKEND"]`).
- **Aceite:** não existe segundo caminho; nenhuma superfície lê preço por API divergente.
- **Apêndice A** descreve o motor genérico de condições e o critério para um dia virar pacote.

### WP-4 — Doorman: porto de identidade (CIAM)
- Alargar o porto: `IdentityView` com `handles: [{kind, value, verified, primary}]` + `resolve(kind, value)`.
- Resolução `identifier`-first; remover `hasattr` e o import direto de guestman (l. 553–556); `revoke_device` passa a usar o nome de cookie por sujeito.
- **Aceite:** teste de contrato com resolver fake multi-handle (whatsapp/email/instagram), provando login por handle secundário e primazia explícita.

### WP-5 — Políticas cross-domain: organização explícita
- Criar no canteiro um espaço nomeado (`shopman/shop/policies/`) com **um módulo por política**, cada um com um verbo público e um **manifesto de domínios tocados**.
- Políticas candidatas: `pricing`, `promotion`, `availability`, `fulfillment`, `loyalty`, `tax`.
- Regra: política depende de **portos/views**, nunca de models de kernel alheios.
- **Aceite:** cada política tem teste isolado e manifesto; nenhum import de model estrangeiro fora do adaptador.

### WP-6 — Projeto, Gabarito, Maquete
- Definir o schema do **Projeto** (canais, pipelines, `RuleConfig`, políticas de preço, templates, personas RBAC, unidades, perfis fiscais) e extraí-lo do amontoado `config/settings.py` + seed + DB.
- **Gabarito:** três suítes — *soberania* (pacote sem canteiro), *composição* (Projeto liga kernel sem deformar) e *evolução* (dados do tenant sobrevivem a upgrade de pacote).
- **Maquete:** `seed` passa a materializar o Projeto.
- **Aceite:** um segundo Projeto mínimo (ex.: só balcão) sobe o sistema sem tocar em pacote.

---

## 6. Cercas (não fazer)

- Não criar pacote de kernel novo sem **2+ consumidores reais** (ADR-001).
- Não colocar verbo de domínio de um único domínio no canteiro.
- Não importar model de um kernel dentro de outro kernel.
- Não mexer em migração de kernel antes da lei (WP-1) e sem plano expand-contract (ADR-015).
- Não renomear app/pacote por estética enquanto houver decisão dividida.
- Não reescrever lógica: os movimentos são de **titularidade**.

---

## 7. Critérios de aceite globais (o "Gabarito" mínimo)

1. **Soberania:** cada pacote alvo passa a suíte com o canteiro desinstalado.
2. **Um dono por decisão:** não existe segunda implementação de uma mesma decisão (teste de grep + teste de contrato).
3. **Contrato explícito:** toda decisão devolve objeto com razão/condições; nada de `bool`/`float`/sentinela.
4. **Fronteira:** nenhum import kernel→kernel fora de porto; nenhum import canteiro→model de kernel fora de adaptador.
5. **Reversível:** cada movimento tem dual-run e caminho de volta.

---

## 8. Perguntas abertas (para a Fase 0)

- P1: um `priceman` passa a valer a pena a partir de quantos tipos de condição? Qual o gatilho?
- P2: o `Quote` deve nascer em `utils` (contrato transversal) ou no pacote que o emite?
- P3: `IdentityView` é contrato no doorman ou no guestman? Quem declara o porto?
- P4: o Projeto é arquivo versionado, dados no DB, ou ambos com precedência definida?
- P5: qual o teto de tamanho do canteiro antes de virar god-module — e como medir?

---

## 9. Protocolo do executor

1. **Worktree próprio antes do primeiro edit** (regra do `CLAUDE.md`). Este plano vive em `plan/core-sovereignty`.
2. Ler `docs/constitution.md`, ADR-001, ADR-005, ADR-019, ADR-021, ADR-022, CORE-BOUNDARIES-AUDIT.md e este plano.
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

**Critério para virar pacote de kernel** (e não antes): (a) pergunta canônica própria; (b) nenhum vocabulário estrangeiro no motor; (c) 2+ consumidores/implementações reais; (d) o ruleset do deployment deixou de caber em código fixo. Hoje nenhum dos quatro vale — por isso o preço fica no canteiro, com o contrato `Quote/conditions[]` definido **desde já**, para não fechar a porta.
