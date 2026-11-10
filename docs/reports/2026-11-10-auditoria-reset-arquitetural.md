# Auditoria adversarial do reset arquitetural do Django Shopman (versão 2, para revisão externa)

- **Base auditada:** `origin/main` em `62191553b23eafd817c56ed9659b1006cde1dbe9` (10/11/2026).
- **Método:** 24 agentes, todos somente leitura. Rodada 1: 6 inventários factuais (modelo barato), 6 frentes de julgamento, 1 red team cego, 6 revisões cruzadas. Rodada 2: 3 verificadores de fatos pendentes e 2 ataques do red team ao veredito consolidado.
- **Nada foi executado:** nenhum teste, migração, seed ou acesso a ambiente vivo. Corridas e latências são leitura de código, não medição.
- **Limitação sobre o Ultracode:** neste runtime não existe agente ou sessão separada com esse nome; "ultracode" é o modo de orquestração multiagente. O papel de red team foi cumprido por agentes dedicados do mesmo modelo, isolados das conclusões das frentes na rodada 1 e instruídos a atacar o veredito na rodada 2. Não houve conversa com outro modelo ou fornecedor. **Este documento é, portanto, a primeira leitura por um agente realmente independente.**
- **Marcas:** [F] fato atual lido no código · [H] dívida já corrigida · [I] inferência.
- **Relatórios brutos de cada agente** (19 da rodada 1, 5 da rodada 2): não foram versionados; ficaram no scratchpad da sessão que coordenou a auditoria. As citações `r1/...` e `r2/...` abaixo apontam para eles.

### O que mudou da versão 1 para esta

O dono leu a versão 1 e levantou seis objeções. Nenhum agente novo rodou; a revisão é do coordenador, sobre a mesma evidência. Mudanças:

1. O slogan "movimento, nunca reescrita" era mais absoluto que o próprio plano, que constrói tabelas novas. Reescrito (seção 1, reparo 1).
2. "Nenhum kernel é substituível" escondia o que o desenho já entrega e não dizia o que falta. Detalhado (seção 17, objeção 2).
3. "Port sem segunda implementação já morreu três vezes" omitia 8 a 11 ports de kernel vivos. Corrigido no glossário.
4. "Mil decisões só em comentário" era usado apenas como argumento contra a reescrita. É também um defeito, e virou a quarta causa (seção 2).
5. Vocabulário interno ("tag", "rajada", "catraca") definido abaixo.
6. Seção 17 (objeções do dono) e seção 18 (onde o coordenador tem menos certeza, para o revisor atacar) são novas.

### Contexto mínimo para quem não conhece o projeto

- **Django Shopman:** sistema de uma padaria (Nelson Boulangerie): loja online, PDV, cozinha, produção, compras, caixa, fiscal. Monolito Django com 13 pacotes pip-instaláveis em `packages/*` (os "kernels"), três apps Django (`shopman/shop` orquestrador, `shopman/storefront`, `shopman/backstage`) e 11 apps Nuxt em `surfaces/`.
- **Estado:** pré-produção. O ambiente vivo ("alpha") roda dado sintético mais cadastro real curado. Um dono decide; dezenas de sessões de agentes escrevem (552 PRs mergeados em 30 dias).
- **A proposta auditada:** "reset de produto e da camada de aplicação, preservando os componentes comprovadamente fortes". Hipótese: monolito modular com kernels, *capability ports* com providers alternativos (o kernel nativo, um ERP, uma planilha), módulos de aplicação por ciclo operacional, projections, integrations e surfaces.
- **"A tag":** a tag git `go-live-v1`, que ainda não existe. Ela marca a entrada em produção com cliente e dinheiro reais. Não tem data (decisão D-030: sai quando as 33 linhas da matriz de prontidão fecharem; hoje 14 estão abertas, nenhuma de código). Ela arma a ADR-015: daí em diante migrations são só aditivas e mudanças destrutivas exigem três deploys (expand-contract). Pela ADR-043 também deixa de existir ambiente de ensaio: cada release estreia em produção.
- **"Catraca"** (ratchet): um lint de CI que conta ocorrências de um padrão proibido e reprova o PR que aumenta a contagem. O repositório já usa o molde (`scripts/check_tenant_config.py`). **Catraca de nascimento** é a variante com baseline zero para código novo: o padrão antigo é tolerado onde já existe e proibido em qualquer lugar novo.
- **"Rajada de 21 dias":** o programa pré-tag tem prazo fixo e fim declarado. No dia 21 o que não entrou é descartado, não carregado. A forma existe porque o programa equivalente anterior (auditoria interna de 18/08) virou fila aberta e nada moveu em 12 semanas.
- **ADR-001:** regra da casa de que um port (Protocol + adapter trocável por settings) só nasce com duas implementações reais.
- **D-nnn:** decisões numeradas do dono em `docs/coordination/DECISIONS.md`.

---

## 1. Veredito

**APROVA COM REPAROS.** O alvo da proposta está certo: a camada de aplicação precisa ser reestruturada e a janela é agora. O método cai em dois pontos, e os reparos são obrigatórios:

1. **Mover o que está certo, construir o que falta, não reescrever o que funciona.** São três verbos, não um:
   - *Mover* services cuja lógica está correta e mora no lugar errado. Cada fatia move uma autoridade inteira e apaga a antiga no mesmo PR, sem alias nem reexport.
   - *Construir do zero* as entidades que hoje não têm tabela (documento fiscal, recebimento, corrida de entrega). Aqui não há o que mover; o molde é o do pacote de caixa (`cashman`), que nasceu com tabelas novas e apagou o antigo.
   - *Não reescrever* services com lógica correta só para "limpar". É isso que a palavra "reset" autorizaria e é isso que cai.
2. **Port só onde existe troca real.** Port na borda externa (pagamento, fiscal, entregador, notificação, catálogo) e onde o kernel precisa chamar para fora. Para o kernel em si: fachada fechada (toda escrita passa pelos services do kernel, garantido por lint) e suíte de contrato em Postgres. Sem Protocol na frente de estoque, pedido, caixa e pagamento enquanto não houver um segundo provider real. A fachada fechada é o primeiro passo de qualquer substituição futura, então nada aqui fecha essa porta (seção 17, objeções 2 e 3).
3. **Corte pré-tag pelo critério certo:** entra antes da tag `go-live-v1` o que muda o formato de um fato transacional ou deixa história sem carimbo. O resto espera, porque depois da tag continua barato.
4. **Execução com prazo fixo de 21 dias, amarrada à matriz de go-live**, com catracas de nascimento que impedem o defeito de nascer de novo.

O veredito provisório do coordenador era "derruba e aprova um substituto". Mudou depois do ataque do red team (seção 16): o substituto cumpre as condições que o próprio red team cego tinha fixado para converter, e "derruba" seria lido como "não mexa", que foi o desfecho da auditoria interna de 18/08.

## 2. Causa principal

Os defeitos provados são de **dado sem dono e de autoridade de escrita**, não de lógica de negócio.

- **Entidades sem tabela** [F]: documento fiscal (chaves `nfce_*` em `Order.data`, `shop/handlers/fiscal.py:497-518`; `fiscalman` tem zero models), corrida e custódia de entrega (`Order.data["courier"]` replicado em N pedidos, `shop/services/courier.py:487,929`), recebimento de compra (N `Move` com `purchase_*` em metadata, `backstage/services/purchase.py:308-352`), revisão de pedido (`Order.data["adjustment"]` ao lado do total selado, `shop/services/order_composition.py:1-40`).
- **Duas camadas de aplicação** [F]: `backstage` é rotulado superfície, mas tem 32 mil linhas de services, models de domínio e escreve direto no livro de estoque (`backstage/services/production.py:2478-2537`). O ciclo de imports atravessa os dois apps: 206 módulos, 120,9 mil linhas.
- **Fatos fracos** [F]: ator é string livre em orderman, craftsman, guestman e refs; `PaymentTransaction` e `Directive` não têm ator; o handler assíncrono roda como `"signal_dispatch"` (`orderman/dispatch.py:112`).

- **Decisões sem registro** [F]: 999 linhas de comentário em 334 arquivos carregam decisão do dono ("decisão do dono, 24/09"), contra um registro formal que vai até D-034. A decisão existe, mas só é achada por quem já está lendo aquele arquivo: ninguém vê duas decisões em conflito, e nenhuma sessão nova sabe que ela existe antes de contrariá-la. É a mesma doença das entidades sem tabela, aplicada a regra de negócio.

O que a tag muda de verdade não é "o schema congela" (tabela e coluna novas seguem livres pela ADR-015). É que **chega dado real e some o ensaio**: depois dela, mudar o formato de um fato exige backfill de nota e dinheiro reais, e todo release estreia em produção (ADR-043, `:66-70`).

Reescrever services não corrige nenhuma das quatro e destrói duas coisas. Primeiro, as decisões acima: enquanto não houver índice, o código é o único lugar onde elas estão, e reescrever é perdê-las. Segundo, a rede de testes: 1.140 `patch` por caminho de módulo, que seguem verdes sem interceptar nada quando o símbolo muda de lugar. As duas fragilidades são defeitos em si, e o plano trata a primeira (item 8: índice das decisões por arquivo e linha). O ponto é a ordem: primeiro indexar, depois mexer.

## 3. Mapa

| Camada | Estado real | Decisão |
|---|---|---|
| **Kernels** (`packages/*`) | Fortes: cashman, payman, miolo do orderman (commit idempotente), livro e promessa do stockman, `finish` do craftsman. Parciais: guestman (escreve em `Order`), doorman (depende de guestman), offerman (schema e leitura, sem comando de escrita). Não são kernel de domínio: fiscalman (biblioteca), buyman (cadastro). Bibliotecas: refs, utils, watchman | Manter. Completar fiscalman antes da tag; buyman depois |
| **Contratos de capacidade** (substitui "capability ports") | A atomicidade vem da transação que a **aplicação** abre sobre o mesmo Postgres | Fachada fechada por kernel + suíte de contrato em Postgres. Sem Protocol |
| **Ports de borda** | Pagamento (Efí, Stripe), fiscal (Focus), entregador (Machine), notificação e OTP, projeção de catálogo (iFood, Meta, Google) | Manter. São a camada de integrations |
| **Módulos de aplicação** | Hoje divididos por público (shop, storefront, backstage), não por ciclo | Pacotes Python dentro de `shop`, em camadas (seção 4). Depois da tag |
| **Projections** | Não escrevem em banco [F]. Uma exceção de desenho: o fechamento do dia usa a projection como entrada do comando (`backstage/api/operations.py:2259-2272`) | Manter; corrigir o fechamento |
| **Integrations** | Espalhadas em `adapters/`, `webhooks/`, 18 `services/ifood_*` | Agrupar por provedor é cosmético; adiar |
| **Surfaces** | 11 apps Nuxt, 232 mil linhas. Auditoria olhou só dois arquivos (seção 15) | Sem veredito firme; abrir frente própria |

## 4. Glossário

| Recomendado | Rejeitado | Por quê |
|---|---|---|
| Mover (lógica certa, lugar errado) e construir (entidade sem tabela) | Reset, reescrita | O código carrega decisões não indexadas; mover preserva, e o que falta é tabela, não service novo |
| Contrato de capacidade (no processo) | Capability port para trocar kernel | Três ports criados para troca e sem segunda implementação estão mortos (`PaymentBackend`, `AccountingBackend`, `ProductionBackend`). Os 8 a 11 ports de kernel que estão vivos são inversão (kernel chamando para fora), não troca de kernel |
| Port de borda | Provider alternativo (ERP, planilha) | ERP e planilha são importação e exportação, nunca donos de pergunta canônica |
| Fachada fechada | "Aplicação depende de ports" | O defeito é escrever por fora do service do kernel |
| Processos: `sales`, `orders`, `production`, `procurement`, `closing` | Os 7 nomes como lista única | Os 7 cobrem 37% dos services e misturam processo com capacidade |
| Capacidades: `payments`, `pricing`, `promise`, `catalog`, `customers`, `fiscal`, `fulfillment`, `delivery`, `notifications` | `cash` como capacidade | Fechamento agrega quatro kernels; é processo |
| Canal: `channels/ifood` | "100% config-driven por ChannelConfig" | Há 54 a 60 ramos por literal de canal; canal é comportamento |
| Plataforma (fila, idempotência, SSE, tenant, calendário) | `shop` como guarda-chuva | 16% do `shop` é infraestrutura sem domínio |
| `app_label` e `db_table` são nomes de registro, não endereço de código | Renomear label para "arrumar" | Label é contrato de permissão recriado a cada deploy |
| Catraca de nascimento (baseline zero para o novo) | Baseline que "só diminui" | A catraca existente foi de 510 para 508 em 18 dias |

## 5. Matriz por componente

| Componente | Ação | Motivo |
|---|---|---|
| cashman | manter | Livro imutável, invariantes no banco, zero import de outro kernel |
| payman | manter + completar (depois) | Falta saldo por pedido por coluna; apagar `PaymentBackend` morto agora |
| orderman | manter miolo | Apagar `AccountingBackend`; revisão de pedido nativa e fila em pacote neutro ficam para depois |
| stockman | manter + completar | Coluna de origem em `Move` entra com o carimbo de fatos; apagar `ProductionBackend` e o proxy |
| craftsman | manter | Aceitar por escrito que a transação do `finish` é da aplicação (ADR-025) |
| guestman | corrigir | O desfazer do merge regrava o `Order.data` inteiro de um snapshot (`contrib/merge/service.py:456-463`) |
| fiscalman | **completar antes da tag** | `FiscalDocument` como registro de autoridade |
| buyman | completar depois | `Receipt` é tabela aditiva; antes, só o reparo da trava |
| `lifecycle.py`, `production_lifecycle.py` | manter | São o coordenador por ciclo que a hipótese pede |
| `Directive` (ADR-003) | manter + completar | Ator, causa e `order_ref` indexado; retenção |
| `shop/adapters/{kds,alert,pos,baskets,delivery_devices,episodes,…}` | apagar (depois) | Existem só para esconder o import shop→backstage |
| Models de domínio em `backstage` | mover só o pacote Python, depois | Zero migração; trocar label derruba o release se errar |
| `backstage/services/{production,purchase,catalog,closing}` | mover para módulos (depois) | Segunda camada de aplicação |
| `pos.py` (6.767 linhas), `payment.py`, `operations.py` | fatiar só junto de mudança funcional | Arquivos mais quentes do repositório |
| Marketing, Concierge, B.I. | carregar como estão | Já estão no `main`; Concierge fase 1 está no go-live (D-017) |
| Proto-Taskman (`backstage/models/operation.py`) | congelar | Funciona, não toca kernel |
| Histórico de migrations (335 arquivos) | **não cortar** | O reset de 08/08 deixou 7 correções em 11 dias; o banco agora é a futura produção |
| `config/synthetic_purge.py` | manter | Única classificação modelo a modelo do que sobrevive |
| Ports mortos e tabela da ADR-001 §3 | apagar, corrigir | Abstração decorativa lida como garantia |

## 6. Ciclos obrigatórios (testes de aceitação)

Defeito estrutural de cada ciclo e o que precisa continuar funcionando.

| Ciclo | Caminho | Defeito |
|---|---|---|
| Loja, Pix e cartão | checkout → commit → reserva síncrona → webhook → `on_paid` → KDS → pronto | "Pago" em três lugares; 7 entradas de `on_paid` |
| PDV | `pos.close_sale` → commit → payman + cashman na mesma transação → NFC-e | `pos.py` mistura comanda, preço, cliente, PIN e liquidação |
| iFood | webhook → `ifood_ingest` cria `Order` direto (`:187-221`) | Segundo nascimento de pedido, fora do `CommitService` |
| Encomenda paga antes | fases diferidas, `Directive` como despertador | Vínculo pedido-fornada em dois JSON espelhados |
| Produção | backstage → `craftsman.finish` → livro de estoque | Aplicação escreve `Move` direto na correção de qualidade |
| KDS | regra em `shop`, model em `backstage` | Inversão escondida por adapter |
| Entrega | `courier` → Machine → webhook | Corrida e custódia em JSON |
| Compra | `confirm_receipt` → `stock.receive` | Sem recibo; serviço mora na superfície |
| Cancelamento e devolução | `cancellation.cancel` → `_on_cancelled` | Dois desvios do portão (`lifecycle.py:1308,1333`), inativos na configuração atual |
| Caixa e dia | cashman + `DayClosing` | Quatro registros de dia sem elo; comando lê projection |

**Os 8 cenários de dinheiro e estoque que viram suíte em Postgres antes da tag:** Pix depois do cancelamento; cartão recusado libera a reserva; PDV com pagamento misto (livro e payman atômicos); PDV sem conexão reenviado; `finish` simultâneo em dois quiosques; cancelamento depois da baixa devolve estoque, cupom, pagamento e nota; recebimento com NF reescaneada; edição de encomenda com diferença a mais e a menos.

Os "38 cenários de pedido" não são suíte: são 38 achados de auditoria fechados num documento. O oráculo executável precisa ser construído.

## 7. Contratos e contract tests

**Kernels (sem Protocol, suíte roda contra o kernel em Postgres):**
1. Venda em dobro: N transações disputam a última unidade, exatamente uma vence.
2. Repetição idempotente concorrente: mesma chave, um efeito; mesma chave com conteúdo diferente, conflito.
3. Reversão exata: liberar reserva e reverter baixa devolvem o saldo; reverter duas vezes não faz nada.
4. Reserva vencida não conta na disponibilidade antes do sweeper.
5. Ordem de lock: carrinhos com SKUs em ordem oposta não travam um ao outro.
6. Todo efeito é consultável por referência.
7. O rollback de quem chama desfaz o efeito (a garantia que um provider remoto perderia).

**Ports de borda (contra mock; sandbox só onde for estável):**

| Port | Garantias a certificar |
|---|---|
| Pagamento | Criar de novo devolve o mesmo intent; captura dupla; estorno parcial repetido; webhook reentregue; timeout nunca vira "pago" |
| Fiscal | Reemitir a mesma referência devolve o mesmo documento; rejeição com código; consulta depois de falha de rede |
| Entregador | Status monotônico; webhook fora de ordem; cancelamento concorrente ao despacho |

**Regra para os 8 a 11 ports que os kernels já declaram** (`config/settings.py:1568-1861`, por exemplo `CUSTOMER_FENCE`, `REFUND_BACKEND`, `PRODUCTION_COMMAND_BACKEND`): cada um passa por um critério. É inversão legítima (kernel precisa chamar fora), tem duas implementações reais, ou participa de transação? Os que não passam são apagados.

## 8. Estratégia sem legado nem dupla autoridade

- **Fatias no `main`**, cada uma move uma autoridade inteira e apaga a antiga no mesmo PR. Fatia que não consegue apagar a antiga não é fatia: fica fora. É a regra que separa movimento de remendo. Branch longa é inviável: 552 PRs em 30 dias, mediana de 11 por dia.
- **Catracas de nascimento**, baseline zero para o que é novo: `save` direto de `Order.data` fora de `merge_order_data`; chave de topo nova em `Order.data`; função nova em adapter que aponta para `backstage`; model de domínio novo em `backstage`; `Move.objects.create` fora do stockman.
- **Alargar o gate que ficou vazio:** `test_backstage_views_do_not_drive_order_lifecycle_directly` (`shop/tests/test_import_boundaries.py:668`) varre só `backstage/views`, que hoje tem login e 2FA. Passa a varrer `api/` e `services/`.
- **Proibido antes da tag:** mover símbolo que algum teste intercepta por caminho. Com reexport o teste segue verde sem interceptar nada.
- **Uma exceção declarada a "sem old/new":** `FiscalDocument` entra em dois PRs (tabela como autoridade; depois remoção das chaves JSON), com prazo de uma semana entre eles.
- **Flags:** baseline dos 47 `_env_bool` e dos nomes `*_V2`, `*_LEGACY`, `*_SHADOW`, `*_PILOT`; só diminui.

## 9. Migrations, seed, dados, rollback e cutover

- **Banco:** mantém a D-029 (mesmo app, mesmo banco, purga). O cadastro curado é real e fica: `synthetic_purge.py` mantém 100 modelos e purga 94.
- **Histórico de migrations:** não cortar. As 14 importações de código vivo dentro de `RunPython` saem editando 9 arquivos, o que é permitido antes da tag. Aplicar a cadeia inteira custa 4,3 s.
- **Tabela nova de fato transacional antes da tag não precisa de backfill:** `Order`, `Move`, `Directive`, `PaymentTransaction` e `Entry` são purgados na virada.
- **Seed:** quatro autoridades dizem o que um banco novo tem (migrações de dado, `seed.py` de 10.399 linhas, descritor de instância, bootstraps do release). Convergir para o descritor é trabalho de depois da tag.
- **Label e permissão:** nada toca `Meta.permissions` nem `app_label` antes da tag. `setup_groups` roda em todo deploy e uma permissão duplicada derruba o release (`MultipleObjectsReturned` fora do `except`, `config/management/commands/setup_groups.py:46`).
- **Rollback:** por imagem anterior; dado só por restauração pontual. O ensaio de "reapontar o app para o banco restaurado" segue pendente na matriz e é pré-requisito de qualquer migração destrutiva em modelo que sobrevive.

## 10. Orçamentos

São propostas; nada foi medido nesta auditoria.

| Eixo | Orçamento |
|---|---|
| Transação | Zero chamada de rede dentro de `atomic` (hoje há duas: captura de cartão e troca cartão para Pix, `shop/services/payment.py:685-688` e `:1380-1432`) |
| Latência p95 no Django | Carrinho 150 ms; commit do checkout 400 ms; fechar venda em dinheiro 300 ms; projeção do PDV 600 ms (limite atual 2.000); fila do Gestor com 500 pedidos 500 ms |
| Consultas | Constantes em N para fila, KDS e PDV |
| Fila de directives | Tópico local até 5 s; fiscal até 60 s; toda falha terminal vira alerta |
| Infraestrutura | Os 11 componentes atuais, nenhum novo. Custo atual por volta de US$ 113/mês |
| Confiabilidade | RPO 5 min, RTO 30 min. Banco de um nó sem alta disponibilidade é risco aceito e declarado |
| Testes | Gate de PR até 20 min (um shard já estourou 30) |
| Complexidade | Arquivo novo até 1.500 linhas; nenhum arquivo acima disso cresce |

Ressalva: os limites de latência três vezes mais apertados que os atuais pedem trabalho de otimização que ninguém estimou. A fila do Gestor só passou em 500 ms com cinco processos leitores, e a segunda instância foi recusada.

## 11. Fundamentos agora para as capacidades futuras

**Criar agora** (única parte cuja história não se recupera depois):
- **Ator tipado** nos fatos: pessoa interna continua FK onde já é (cashman); nos demais, referência `tipo:id` (`user:<pk>`, `customer:<uuid>`, `system:<componente>`, `integration:<provedor>`, `agent:concierge`).
- **Dispositivo, posto, correlação e causa** em `OrderEvent`, `Move`, `PaymentTransaction`, `WorkOrderEvent` e `Directive`. Colunas anuláveis, sem trocar leitores.
- **Contexto gravado na `Directive`** na criação e reaberto pelo dispatcher, para o efeito assíncrono herdar quem o causou.
- **Uma função de data operacional** usada pelos escritores de fato (hoje são 248 chamadas de `timezone.localdate()` fora de teste).

**Não criar agora:** pacote `taskman`, modelos de setor ou turno de trabalho, outbox genérico, kernel de auditoria, event sourcing, identificador de loja nos fatos (a ADR-042 resolve por schema).

**Como cada uma entra:**

| Capacidade | Entrada | Mudança de kernel |
|---|---|---|
| B.I. | Lê pelos adaptadores de `backstage/bi/sources` | Nenhuma; fechar as 7 projeções que ainda leem model direto |
| Marketing | Já entrou; lê guestman e offerman, tem fila própria | Já custou um livro novo dentro do guestman (consentimento) |
| Concierge | Mesmo caminho de comandos da Loja | Nenhuma; precisa do ator `agent:concierge` |
| RH | Lê fatos com ator estável | Inviável hoje: a pessoa é nome de usuário em texto |
| Taskman | Pacote novo + módulo + superfície | Nenhuma, **se** ator, posto e data operacional estiverem estáveis. Vira kernel quando houver segundo consumidor |

## 12. Plano por horizonte

Soma do que entra antes da tag: 3 a 4 semanas em fluxo único; cerca de 2 de calendário em três frentes disjuntas. **Depois das decisões do dono (seção 16, fim), só três linhas bloqueiam a tag: o pacote de dias, o item 10 (só colunas) e o item 11. O resto corre em paralelo sem segurar o go-live.**

**Dias (0 a 5)**
1. `purchase.receipt` em `PERSISTENT_SCOPES`, com o conteúdo na impressão digital, e teste. Meio dia.
2. Catracas de nascimento e gate alargado (seção 8). 1 a 2 dias.
3. Trocar o lock de sessão do ManyChat por reserva em linha com validade (`guestman/contrib/manychat/resolver.py:55-72`). Atrás do PgBouncer o lock pode ficar órfão, e o resolvedor serve OTP e aviso da v1. 1 a 2 dias.
4. Pontos de fidelidade e pendência do fechamento passam a ler o total vigente (`shop/handlers/loyalty.py:57`, `backstage/services/closing.py:717`). 1 a 2 dias.
5. Timeout explícito na captura Stripe. 1 dia.
6. Apagar os três ports mortos; registrar os reparos numa ADR curta; abrir uma linha na matriz de go-live para cada item inegociável.

**1 semana**
7. Os 12 escritores reais de `Order.data` sem lock passam por `merge_order_data`, um por PR, `payment.py` por último. A causa comum é o despacho de fases sobre instância relida sem lock (`shop/apps.py:334`). 3 a 4 dias.
8. Índice das decisões que vivem em comentário (arquivo e linha).
9. Manifesto cenário → teste e início da suíte dos 8 cenários.

**2 a 4 semanas**
10. Carimbo de fatos (seção 11). 1,5 a 3 semanas; é o item de maior incerteza.
11. `FiscalDocument` no fiscalman como registro de autoridade antes da primeira NFC-e real. Os arquivos fiscais estão frios (zero commits em 14 dias). 1,5 a 3 semanas.
12. Vagas opcionais, só com mais de 6 linhas da matriz abertas e nenhum P1 de dinheiro em aberto: tirar a rede de dentro do lock na captura; mover o pacote Python dos models de KDS e alerta (zero migração) para desfazer o ciclo shop↔backstage; fatiar `operations.py`.

**Posterior (depois da tag, expand-contract)**
`Receipt` no buyman; corrida e custódia em tabela; saldo por pedido no payman; revisão de pedido nativa no orderman; fila e idempotência em pacote neutro; pacotes por ciclo com lint de camadas; fachada fechada completa; entidade de dia operacional; B.I. fechado nos adaptadores; convergência do seed; schema por loja (ADR-042); Taskman.

**Corte duro, não entra antes da tag:** mudança de label ou permissão; movimento de símbolo interceptado por teste; `lock_timeout` global; corte de histórico de migrations; PR estrutural acima de 300 linhas em `pos.py`, `payment.py`, `lifecycle.py` ou `operations.py`.

## 13. Dez modos de falha

| # | Modo | Sinal observável |
|---|---|---|
| 1 | O programa rouba a fila das correções do beta | PRs de correção abaixo de 35 por semana (base 51) |
| 2 | Tag sai com zero inegociável feito, porque a matriz não tem linha estrutural | Efí libera e nenhum item 7, 10 ou 11 está no `main` |
| 3 | Vira refatoração eterna, como a auditoria de 18/08 (nada moveu em 12 semanas; `shop/adapters/kds.py` foi de 150 para 389 linhas) | Dia 21 chega com fatias abertas |
| 4 | Catraca regravada para cima | `--update` com contagem maior |
| 5 | Falso verde por teste que não intercepta mais | PR move símbolo sem tocar teste |
| 6 | Deadlock ao travar os 12 escritores | `deadlock detected`; p95 de checkout e PDV |
| 7 | Tabela fiscal redesenhada no banco vivo | Segunda migração sobre tabela com menos de 14 dias |
| 8 | Release cai por permissão | Job `release` vermelho |
| 9 | Colisão em arquivo quente | PR estrutural em conflito duas vezes |
| 10 | Segundo sistema por baixo do pano: alguém cria port para kernel "já que estamos aqui" | Protocol novo sem segunda implementação |

## 14. Condições de abortar ou mudar a estratégia

- P1 novo de dinheiro, nota ou estoque vindo do beta: para tudo, exceto os itens 1 e 7.
- Check obrigatório vermelho por mais de 24 h por causa de um PR do programa: reverte.
- Matriz de go-live com 3 linhas abertas ou menos: congela. O que não entrou vai para depois da tag, sem ser carregado.
- Dia 21: fim. Renovação só com a palavra do dono.
- Fatia que exija mudar a semântica de um service de kernel para fechar: aborta a fatia, não o programa.
- Fatia em conflito duas vezes: abandonada, não rebaseada.
- **Mudaria a estratégia inteira:** um segundo provider real e contratado para estoque ou pedidos (reabre a discussão de ports, com saga e reserva com validade); o dono declarar que substituir kernel por sistema externo é objetivo de produto com prazo (por exemplo, vender o Shopman a uma loja que já tem ERP); ou a frente de superfícies mostrar que os apps Nuxt recalculam decisão de domínio em escala.

## 15. Divergências entre agentes e resolução

| Divergência | Resolução |
|---|---|
| Port de estoque (frente E) contra fachada sem port (A) | Fachada, com a semântica transacional escrita e testada. Protocol com uma implementação é o que a ADR-001 veta |
| "Cerca de 70 escritas de `Order.data` sem lock" (red team cego) | Falso. Verificado no universo inteiro: 99 pontos, 16 sem lock, 12 em caminho real. O grosso é [H] |
| Acessor tipado sem model (B) contra tabelas (A, C) | Tabela para fiscal, corrida e recebimento; helper só no resíduo |
| iFood "passa pelo commit" (C) | Não passa. `Order.objects.create` direto. São dois nascimentos de pedido |
| Trava de NF duplicada some em 7 dias (C), em 24 h (A), ou é permanente (red team) | A linha só some se o comando de limpeza rodar, e ele não está agendado. A trava vale hoje por acidente. Reparo de meio dia |
| "Não há gate de fronteira" (B) | Há (`test_import_boundaries.py`, 1.220 linhas). Falta gate de camadas e de escrita, e um dos gates ficou vazio depois do cutover headless |
| Extrair Marketing quebra o ciclo de imports (B) | Não quebra: 147 para 116. O que separa os dois apps é apagar os adapters invertidos |
| Labels imutáveis (D) contra mover models (B) | Mover só o pacote Python. Trocar label custa dias por model e risco de derrubar o release |
| Corte único do histórico de migrations (D) | Rejeitado pela revisão e pelos dois ataques |
| Incidente de pool de 14/10 como prova de rede sob lock (E) | A causa foi outra e já está corrigida. O risco segue como inferência |
| Separar os signals in-tx (F, lendo a ADR-025) | A própria ADR mantém `order_changed` e `production_changed` dentro da transação. Aceitar a exceção |
| `FiscalDocument` antes da tag (ataque 1) ou depois (ataque 2) | Antes. Sem backfill agora; depois seria backfill de nota real. Com gatilho de reversão (modo 7) |
| Esforço: frentes somam 10 a 14 semanas cada; revisões, 20 a 30 no conjunto | O programa inteiro não cabe. Cabe o corte da seção 12 |
| "Schema congela na tag" (red team cego e meu provisório) | Errado. Tabela e coluna novas seguem livres. O critério é dado real e ausência de ensaio |

**Limites que nenhuma frente fechou:** as superfícies Nuxt (232 mil linhas, 61% dos toques de correção em 14 dias) não tiveram frente própria; nenhuma corrida foi reproduzida; o impacto financeiro dos 12 escritores sem lock é inferência (o Payman é a fonte autoritativa, então a perda provável é de evidência no JSON, não de dinheiro).

## 16. Objeções finais do Ultracode e resposta do coordenador

**Ataque 1, "conservador demais":**

| Objeção | Resposta |
|---|---|
| O coordenador se ancorou no parecer cego; três pilares dele caíram e o veredito os manteve | Aceita. Causa principal reescrita (seção 2), contagem de locks corrigida, movimento de models rebaixado |
| O rótulo honesto é APROVA COM REPAROS | Aceita. Rótulo mudado |
| O programa tem a forma que já morreu aqui: fila longa mais "posterior" | Aceita. Rajada de 21 dias, itens como linha da matriz, descarte do que não entrar |
| Catracas com baseline seguram e não movem | Aceita. Catracas de nascimento com baseline zero |
| "Port sem segunda implementação morreu" é falso como regra: há 8 a 11 ports de kernel vivos | Aceita em parte. Mantida a recusa a port para trocar kernel; os existentes passam um a um pelo critério da seção 7 |
| "Nenhuma frente achou lógica errada" é artefato de método; a auditoria não olhou as superfícies | Aceita como limite declarado (seção 15). Não muda o veredito, reduz a certeza sobre "o que fica" |
| Um import (`observability.py:235`) segura parte do ciclo e foi minimizado | Aceita em parte: vale no subgrafo de services (67 para 42), não no grafo real (147 para 144). Entra como vaga opcional |

**Ataque 2, "ambicioso demais":**

| Objeção | Resposta |
|---|---|
| "Escritor único em 1 semana" ataca os 99 pontos; o risco está em 12 | Aceita. Item 7 |
| Corte de migrations: ganho cosmético, risco no banco que vira produção | Aceita. Removido |
| `lock_timeout` antes de tirar a rede do lock troca espera por exceção no webhook de Pix | Aceita. Fora do pré-tag |
| Os 38 cenários não são suíte | Aceita. Construir 8 |
| Mover símbolos antes da tag desmonta a rede de testes no pior momento | Aceita. Corte duro |
| Tabela nova de nota na véspera do go-live é risco; `FiscalDocument` deve ficar para depois | **Recusada.** Antes da tag o custo de backfill é zero e os arquivos estão frios; depois, é backfill de nota fiscal real com 117 leitores, em produção sem ensaio. Mantido antes, com gatilho de reversão |
| Faltam aborto, teto e dono por item | Aceita. Seções 13 e 14. Dono por item depende do dono do projeto |
| O veredito não responde 5 das 9 autoridades duplicadas (progresso físico em 5 portadores, vínculo pedido-fornada, mapa de próximo passo do operador) | Aceita como lacuna: ficam diagnosticadas e sem fatia antes da tag |

**Decisões do dono, todas respondidas em 10/11/2026:**

1. *O programa entra na matriz de go-live como linhas que bloqueiam a tag?* O dono delegou ao coordenador com um critério: **menor tempo possível até o go-live**. Decisão do coordenador: bloqueiam a tag só três linhas, as que não se recuperam depois dela.
   - **Pacote de dias** (itens 1 a 6 da seção 12, até 5 dias): trava de NF duplicada, catracas de nascimento, lock do ManyChat, total vigente em fidelidade e fechamento, timeout da Stripe, ports mortos.
   - **`FiscalDocument`** (item 11): depois da tag seria backfill de nota real.
   - **Carimbo de fatos, só as colunas** (item 10, fase expand): história sem ator não se reconstrói.

   Não bloqueiam e correm em paralelo, entrando se der tempo: os 12 escritores sem lock (item 7), o índice de decisões (8), a suíte dos 8 cenários (9) e as vagas opcionais (12). Se a matriz fechar antes, eles passam para depois da tag sem cerimônia. Motivo de não bloquearem: nenhum perde dado por esperar, e todos seguem permitidos pela ADR-015. Risco aceito: os 12 escritores entram em produção como estão; a perda provável é de evidência em JSON, não de dinheiro, e isso é inferência (seção 18, ponto 2).
   Efeito no prazo: as 14 linhas abertas da matriz são todas externas ou do dono. As três linhas novas somam cerca de 2 semanas de calendário em frentes paralelas, então só atrasam a tag se a matriz externa fechar antes disso.
2. *`FiscalDocument` antes da primeira NFC-e real?* **Sim, antes.** Confirma a recusa do coordenador à objeção do red team (seção 16).
3. *Concierge no go-live ou depois?* **Pode ser depois.** Isso substitui a D-017 nesse ponto e precisa ser registrado em `docs/coordination/DECISIONS.md` e na matriz (linha 72), o que esta auditoria não fez por ser somente leitura. Consequências para este relatório: o código do Concierge (13,6 mil linhas em `shopman/storefront/concierge`) fica no `main` como está, desligado; o tipo de ator `agent:concierge` continua reservado no carimbo; a troca do lock do ManyChat **continua** no pacote de dias, porque o mesmo resolvedor serve OTP e avisos da v1.
4. *Substituir kernel por sistema externo é objetivo com prazo?* **Sem prazo.** É propriedade desejável, não objetivo datado. Vale o reparo 2 como escrito, e a condição de mudança de estratégia da seção 14 não está acionada.

## 17. Objeções do dono à versão 1 e resposta do coordenador

**1. "Mil decisões minhas só existirem como comentário e código não é, em si, um sintoma?"**
É. A versão 1 usava o número só como argumento contra reescrever e não o nomeava como defeito. Agora é a quarta causa (seção 2). As duas leituras valem juntas: é defeito, e enquanto não for tratado torna a reescrita mais cara. O reparo é o item 8 do plano (índice por arquivo e linha), e ele vem antes de qualquer movimento. O que a auditoria **não** fez: ler as 999 linhas para dizer quantas conflitam entre si ou com o registro formal.

**2. "Nenhum kernel ser substituível por ERP ou planilha é uma surpresa. Fiz desde o início pensando nisso."**
O desenho entrega metade da propriedade, e a metade que falta é do lado da aplicação, não dos kernels.

- *O que existe* [F]: nenhum kernel importa a aplicação (gate em `shop/tests/test_import_boundaries.py:432-466`); cada um tem settings de teste próprios; os kernels declaram 8 a 11 pontos de extensão para fora (`config/settings.py:1568-1861`). Um kernel pode ser instalado sozinho em outro projeto.
- *O que falta, lado 1, acoplamento* [F]: a aplicação importa **models** de kernel direto em 163 arquivos (orderman), 115 (offerman), 54 (craftsman), 44 (guestman), 33 (cashman), 32 (stockman), 28 (buyman), e o contrato público declarado inclui os models (`shop/tests/test_no_deep_kernel_imports.py:3-15`). São 741 linhas de import direto contra 84 chamadas por adapter. Em alguns pontos a aplicação escreve linhas do kernel por fora dos services dele. Trocar o kernel hoje é trocar o ORM debaixo de centenas de leitores.
- *O que falta, lado 2, semântica* [I]: um ERP de estoque não tem reserva com validade, promessa nem saldo planejado; um CRM não tem as cercas de privacidade; um provedor de identidade não tem PIN nem confiança de estação. A troca perde comportamento que a loja usa todo dia.
- *O que falta, lado 3, transação* [F]: a garantia contra venda em dobro e a atomicidade entre pedido, pagamento e caixa vêm de uma transação que a aplicação abre sobre o mesmo Postgres. Um provider remoto não participa dela. Substituir exigiria saga com compensação e reserva com validade, o que é outro desenho.
- *Também não é verdade que os kernels são independentes entre si* [F]: há imports de produção kernel a kernel não declarados nos `pyproject.toml` (guestman → orderman 7, offerman → craftsman/stockman 9, buyman → stockman 3, entre outros).

Conclusão do coordenador: "pip-instalável e sem conhecer a aplicação" está entregue; "trocável neste sistema" não está, e não há segundo provider contratado (o Bling aparece na documentação só como fonte de comparação, "não como escritor"). O único candidato honesto a dado externo é o cadastro de compras, e a forma certa ali é importação. Limite desta resposta: a frente A não leu `guestman/contrib/{loyalty,consent,insights}`, `doorman/services` nem `craftsman/contrib/formula`.

**3. "Sem ports para kernels, por quê exatamente?"**
Quatro razões, em ordem de peso:

1. *A garantia mora na transação compartilhada.* Um port que admite provider remoto não pode prometer "o rollback de quem chama desfaz o efeito". Declarar o port sem essa garantia é prometer troca que quebraria dinheiro e estoque.
2. *A regra é da própria casa.* A ADR-001 exige duas implementações reais. Os três ports criados para troca sem segunda implementação estão mortos, e a tabela da ADR lista classes que não existem mais na árvore.
3. *O defeito provado é outro.* A aplicação fura os services e escreve linhas e JSON do kernel. Um Protocol na frente não impede isso; um lint de escrita (fachada fechada) impede, e custa dias em vez de reescrever 741 pontos de import.
4. *Port com uma implementação vira CRUD genérico* ou se fatia por método, e passa a ser lido como garantia que não existe.

O que **não** está sendo dito: que port é ruim, ou que a troca nunca virá. A fachada fechada mais a suíte de contrato são exatamente o pré-requisito de um port futuro: quando houver segundo provider real, a suíte já diz o que ele precisa cumprir. O red team apontou, e o coordenador aceitou, que "port destrói atomicidade" confunde port com provider remoto; por isso os 8 a 11 ports de kernel que já existem não são apagados em bloco, passam um a um pelo critério da seção 7.

**4. "Meu receio de movimento em vez de reescrita é gerar lixo e mais lixo, gambiarras."**
O receio é legítimo e a versão 1 não o respondia. Três pontos:

- *O que a auditoria achou não é lixo espalhado.* A gambiarra está concentrada: entidades em JSON, 9 adapters que existem só para esconder o import shop→backstage, 54 a 60 ramos por literal de canal, três arquivos gigantes. A lógica de dinheiro e estoque nos kernels fortes foi lida e não mostrou erro.
- *Onde o lixo é a estrutura, a resposta já é construir do zero:* `FiscalDocument`, `Receipt`, corrida de entrega. Isso é reescrita localizada, com tabela nova e remoção do antigo, e está no plano.
- *O que impede o movimento de virar remendo* são regras, não intenção: a fatia apaga o antigo no mesmo PR; alias e reexport são proibidos; catraca de nascimento com baseline zero; fatia em conflito duas vezes é abandonada; fim no dia 21.

O risco que permanece e o coordenador não esconde: o plano pré-tag **não** toca `pos.py` (6.767 linhas), `payment.py` nem `operations.py` além dos 12 escritores sem lock. Quem espera sair da tag com esses arquivos limpos vai se frustrar. E o precedente joga contra: a auditoria de 18/08 propôs movimento e nada moveu em 12 semanas. Se o revisor externo concluir que só uma reescrita delimitada de um desses arquivos resolve, o argumento a derrubar é o da rede de testes (1.140 interceptações por caminho) e o das decisões não indexadas.

**5. "O que significa rajada de 21 dias com catracas?"** e **6. "Antes da tag: qual tag?"**
Definidos no contexto do início. Em uma linha: tag é a `go-live-v1`, o marco de entrada em produção; rajada é um programa com dia de término, em que o que não entrou é descartado; catraca é um lint que reprova o PR que reintroduz o padrão proibido.

## 18. Onde o coordenador tem menos certeza (alvos para o revisor externo)

1. **A recusa a reescrever foi decidida sem olhar as superfícies.** Os 11 apps Nuxt (232 mil linhas) concentram 61% dos toques de correção em 14 dias e não tiveram frente própria. "Nenhuma frente achou lógica errada" pode ser artefato de onde se olhou.
2. **Nada foi executado.** Os 12 escritores sem lock, a rede sob lock na captura de cartão e o lock órfão do ManyChat são leitura de código. Nenhuma corrida foi reproduzida.
3. **`FiscalDocument` antes da tag** foi mantido contra uma objeção do red team. O argumento é custo de backfill zero agora; o contra-argumento é tabela fiscal nova na véspera da primeira nota real.
4. **Estimativas.** As frentes somavam 10 a 14 semanas cada e as revisões 20 a 30 no conjunto. O corte de 3 a 4 semanas em fluxo único é inferência do coordenador, e o carimbo de fatos tem faixa de 1,5 a 3 semanas.
5. **A janela não tem comprimento conhecido.** Depende de credenciais, contador, hardware e QA física. "21 dias" pode ser maior que a janela ou muito menor.
6. **Substituibilidade.** A resposta à objeção 2 se apoia em contagem de imports e em inferência sobre o que um ERP oferece. Ninguém desenhou o port de estoque para medir o custo real; a frente E propôs um ("port semântico" que declara se entra na transação de quem chama) e foi vencida por argumento, não por experimento.
7. **Mesmo modelo dos dois lados.** Frentes, revisões e red team rodaram no mesmo modelo. Convergência entre eles vale menos do que parece.
8. **Cinco autoridades duplicadas ficaram sem fatia** (progresso físico do pedido em 5 portadores, vínculo pedido-fornada em dois JSON, mapa de próximo passo do operador). Estão diagnosticadas e não entram no plano pré-tag.
