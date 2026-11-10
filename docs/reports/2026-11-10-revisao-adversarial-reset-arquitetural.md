# Revisão adversarial da auditoria do reset arquitetural

**Alvo:** PR #2258, commit `8cefa7c7b8bfc53d6629830d6de183519d39c07c`  
**Base inspecionada:** `origin/main` em `62191553b23eafd817c56ed9659b1006cde1dbe9`  
**Data:** 2026-11-10  
**Veredito:** **APROVADO COMO INVENTÁRIO; REJEITADO COMO PLANO CANÔNICO NO ESTADO ATUAL**

## Resumo executivo

O relatório do Claude encontrou problemas reais e importantes: autoridades sem entidade
própria, escrita fora dos services dos kernels, domínio operacional dentro do Backstage,
fatos com contexto fraco e dependência excessiva de JSON. A recomendação de preservar kernels
fortes, criar entidades ausentes e instalar catracas de nascimento também é sólida.

O salto de inventário para plano, entretanto, não está maduro. A auditoria não executou testes,
não mediu desempenho, não auditou as superfícies, perdeu os relatórios brutos que sustentam
suas citações e transformou inferências do coordenador em decisões atribuídas ao dono. Mais
grave: aprova o reset da camada de aplicação, mas adia essa reorganização e o Taskman para
depois do go-live. Isso entrega a situação que o reset deveria evitar.

O PR #2258 não deve entrar como está. O relatório pode ser versionado como evidência histórica,
desde que suas limitações fiquem explícitas. D-035 e D-037 refletem decisões claras. D-036
precisa ser reescrita e D-038 precisa ser retirada até existir evidência executável e aprovação
do corte.

## Achados bloqueadores

### 1. D-038 transforma estimativa não testada em decisão de go-live

O próprio relatório declara que nenhum teste, migração, seed, corrida ou acesso ao ambiente
vivo foi executado. Mesmo assim, D-038 afirma que somente três reparos seguram a tag, aceita os
12 escritores sem lock e torna não bloqueante a suíte dos oito cenários críticos.

Isso não é uma conclusão sustentada pela evidência. Também conflita com a exigência do dono de
forçar os testes ao máximo antes de o sistema entrar em uso. Os oito cenários de dinheiro,
estoque, produção, recebimento e cancelamento devem ser pré-condição do corte arquitetural e do
go-live, não trabalho opcional “se der tempo”.

**Correção:** remover D-038 e as três linhas derivadas da matriz até que o baseline seja
executado, os cenários virem testes e o custo seja medido.

### 2. D-036 reduz um princípio arquitetural a uma possibilidade futura

O dono não descreveu substituição de capacidades como conveniência sem prazo. Ele explicou que
essa é uma motivação central: um domínio pode ser atendido pelo kernel nativo, por ERP, API ou
planilha mediante adapters, sem prejudicar a integração da suíte.

A ADR-001 vigente assume o oposto para kernels: o framework importa os cores diretamente e
declara que substituir um core exige reescrever seus pontos de uso. Usar essa ADR para rejeitar
capability providers avalia o novo alvo pela regra antiga que o reset pretende reconsiderar.

Fachadas fechadas e contract tests são pré-requisitos corretos, mas não bastam enquanto a
aplicação importar centenas de models e os tratar como contrato público. Não é necessário criar
um `Protocol` genérico para cada kernel agora; é necessário decidir e proteger a fronteira pela
qual a aplicação consome cada capacidade.

**Correção:** D-036 deve registrar substituibilidade como invariante arquitetural do alvo. Uma
nova ADR deve substituir os trechos incompatíveis da ADR-001 e distinguir três perfis:

1. provider nativo, em processo e transacional;
2. provider remoto, com idempotência, timeout, consistência e compensação explícitos;
3. fonte importada/exportada, que não assume autoridade operacional em tempo real.

Um contrato não pode prometer atomicidade idêntica nos três perfis. A semântica suportada por
cada provider deve ser declarada e testada.

### 3. O plano adia o objeto central do reset

O relatório reconhece duas camadas de aplicação e 32 mil linhas de services no Backstage, mas
manda módulos por ciclo, lint de camadas e fachada completa para depois da tag. Assim, o plano
pré-tag é predominantemente uma correção de go-live, não o “reset de produto e da camada de
aplicação” solicitado.

Há uma decisão honesta a tomar:

- fazer o reset agora e aceitar que o go-live espere seus critérios de saída; ou
- fazer apenas hardening de go-live e aceitar explicitamente a refatoração profunda posterior.

Não é maduro chamar a segunda opção de aprovação da primeira.

### 4. A evidência da auditoria não é reproduzível

Os 24 relatórios brutos não foram versionados e as citações `r1/...` e `r2/...` apontam para um
scratchpad temporário que já desapareceu. Contagens, divergências e verificações não podem ser
reexecutadas nem revisadas em sua fonte.

**Correção:** versionar um ledger mínimo de evidências com comando, ref, universo, resultado e
responsável. Afirmações sem fonte reproduzível devem ser marcadas como hipótese, não fato.

### 5. O critério proposto para Taskman está errado

O relatório diz que Taskman “vira kernel quando houver segundo consumidor”. Número de
consumidores não define domínio. Um kernel se justifica por pergunta canônica, linguagem,
lifecycle, invariantes e autoridade próprias.

Já existe um proto-domínio com templates, execuções, evidências, supervisão, idempotência,
estados e constraints. Congelá-lo sem descoberta preserva a posição errada no Backstage e
encarece justamente a história operacional que será útil a Human, Assetman e avaliações.

**Correção:** executar a descoberta adversarial do Taskman antes do plano final. Se aprovado,
extrair antes de acumular dados reais. Se adiado, definir o limite que o proto-domínio não pode
ultrapassar e o gatilho objetivo de extração.

### 6. Entidades da v1 são adiadas apesar de sua história ser irrecuperável

O plano posterga `Receipt` e corrida/custódia estruturadas, embora Compras/recebimento e entrega
por Machine estejam no escopo confirmado da v1. Guardar apenas uma chave idempotente não cria
o fato de recebimento, suas linhas, documento, divergências, responsável e evidências. Da mesma
forma, JSON de corrida em pedidos não constitui autoridade durável de entrega e custódia.

**Correção:** antes de dados reais, decidir e modelar as autoridades mínimas de
`FiscalDocument`, `PurchaseReceipt` e `DeliveryRun/Custody`. A decisão pode manter alguma delas
fora de um kernel, mas não pode deixá-las como JSON sem dono por conveniência de prazo.

### 7. A remoção de “três ports mortos” não está suficientemente discriminada

Os nomes agrupam situações diferentes:

- `PaymentBackend` descreve a borda de gateways e convive com adapters Efí, Stripe e mock;
- `AccountingBackend` é precisamente a fronteira necessária para Conta Azul, embora a
  implementação produtiva ainda não exista;
- `ProductionBackend` possui contrato, implementação Craftsman e testes, ainda que também
  carregue um proxy de compatibilidade questionável.

Pode haver classes mortas ou documentação divergente, mas apagar os três em bloco por contagem
de implementações arrisca remover uma fronteira válida junto com abstração decorativa.

**Correção:** auditar cada método e caminho real. Remover apenas símbolos comprovadamente sem
chamador; corrigir a documentação; preservar ou redesenhar as capacidades reais.

## Achados importantes, não bloqueadores isoladamente

- A exceção de duas PRs para `FiscalDocument`, com uma semana de dupla representação, conflita
  com o princípio pré-go-live de zero autoridade duplicada. O cutover deve nomear escritor e
  leitor canônicos em cada fase, preferencialmente numa fatia atômica.
- Os orçamentos de latência são desejos, não budgets. Sem baseline p50/p95, volume, hardware e
  número de queries, não servem como critério de aceitação.
- “Arquivo novo até 1.500 linhas” é permissivo demais para orientar desenho. Complexidade deve
  ser controlada por responsabilidade, acoplamento e contratos, não apenas LOC.
- Um limite arbitrário de 21 dias pode impedir deriva, mas não pode converter trabalho
  estrutural necessário em dívida automática. O timebox deve limitar investigação e tamanho de
  fatias; os critérios de saída decidem o go-live.
- “Fatia em conflito duas vezes é abandonada” confunde conflito de integração com erro de
  produto. Conflito exige replanejamento; não justifica manter autoridade duplicada.
- A ausência de auditoria das superfícies impede um veredito sobre “reset de produto”. É
  necessário provar que as superfícies apresentam e encaminham intenções, sem recalcular
  decisões de domínio.

## O que deve ser preservado do relatório

1. Preservar cashman, payman, o miolo do orderman, o ledger/promessa do stockman e a execução
   do craftsman, condicionados a contract tests.
2. Criar entidades onde hoje existem fatos importantes em JSON.
3. Impedir escritas diretas fora da autoridade do kernel.
4. Não trocar `app_label`, permissões ou histórico de migrations por estética.
5. Criar catracas de nascimento com baseline zero para novas violações.
6. Manter `FiscalDocument` antes da primeira NFC-e real.
7. Separar projections de surfaces e corrigir qualquer comando alimentado por projection.
8. Tratar canais externos e provedores remotos como integrações com idempotência e recuperação.

## Plano de ação corrigido

O plano abaixo não estima a implementação inteira antes de medir o baseline. Ele fecha primeiro
as decisões que alteram a arquitetura e só então compromete prazo e paralelismo.

### Fase 0: corrigir a verdade canônica

**Saída:** nenhuma inferência apresentada como decisão do dono.

1. Manter o PR #2258 fora da fila até revisão.
2. Preservar D-035 (Concierge pode ficar para depois) e D-037 (`FiscalDocument` antes da
   primeira NFC-e real).
3. Reescrever D-036 como invariante de substituibilidade, sem prescrever ainda `Protocol` para
   todos os kernels.
4. Retirar D-038 e as linhas da matriz derivadas dela.
5. Versionar o ledger de evidências ou rebaixar para hipótese tudo que dependia dos relatórios
   brutos perdidos.

### Fase 1: baseline executável e mapa de autoridades

**Saída:** sabemos o que funciona, quem escreve cada fato e quanto custa hoje.

1. Executar suites dos kernels isoladamente e a suíte de integração em PostgreSQL.
2. Transformar os oito cenários críticos do relatório em testes bloqueantes.
3. Adicionar cenários completos para Loja, PDV, iFood, produção, compra/recebimento, fiscal,
   entrega e cancelamento/devolução.
4. Produzir matriz `fato → autoridade → escritor → leitores → retenção → reversão`.
5. Medir p50/p95, queries e contenção nos caminhos críticos antes de definir budgets.
6. Auditar as nove superfícies de produto para identificar decisão de domínio duplicada no
   cliente.

### Fase 2: decisões arquiteturais antes de mover código

**Saída:** ADRs do alvo e fatias com critérios inequívocos.

1. Aprovar a taxonomia: kernels, módulos de aplicação, projections, integrations e surfaces.
2. Substituir a parte incompatível da ADR-001 por contratos de capacidade e perfis de provider.
3. Definir módulos por ciclo e suas dependências permitidas.
4. Executar a descoberta adversarial de Taskman.
5. Decidir as autoridades de documento fiscal, recebimento, corrida/custódia, revisão de pedido
   e dia operacional.
6. Fixar regra de cutover: uma autoridade de escrita por fato; sem alias permanente ou segunda
   fonte de verdade.

### Fase 3: construir os fatos que não podem nascer errados

**Saída:** dados reais começam com identidade, contexto e autoridade corretos.

Ordem sugerida, ajustada pelo baseline:

1. contexto causal comum: ator tipado, dispositivo, posto, correlação, causa e data
   operacional;
2. `FiscalDocument`;
3. `PurchaseReceipt` com linhas, divergências, documento, ator e idempotência;
4. `DeliveryRun/Custody` para Machine e operação própria;
5. Taskman, se a descoberta aprovar a extração;
6. Spendman apenas após descoberta própria; Conta Azul permanece provider financeiro externo.

Cada fatia precisa de migration, writer único, leitura canônica, teste de concorrência,
idempotência, reversão/compensação e remoção da autoridade anterior.

### Fase 4: reset da camada de aplicação

**Saída:** Backstage e Storefront voltam a ser interfaces; o orquestrador deixa de ser um
arquivo ou pasta onisciente.

1. Criar módulos verticais pelos ciclos confirmados: `sales`, `orders`, `fulfillment`,
   `production`, `procurement`, `fiscal` e `delivery`.
2. Mover uma autoridade completa por fatia, com testes de caracterização antes do movimento.
3. Fazer toda escrita de kernel atravessar sua fachada pública.
4. Fazer leitura operacional atravessar projections ou contratos de leitura explícitos.
5. Eliminar adapters cuja única função seja esconder dependência invertida entre Shop e
   Backstage.
6. Instalar gates de import, escrita e criação de models no lugar errado.

Arquivos grandes não são fatiados por estética. São fatiados quando uma fatia vertical permite
remover uma responsabilidade completa e sua antiga entrada.

### Fase 5: ensaio e go-live

**Saída:** decisão de go-live baseada em prova, não em calendário.

1. Replay completo de migrations em banco novo e ensaio de upgrade/restauração.
2. Seed e purga sintética reproduzíveis.
3. Oito cenários críticos e ciclos v1 verdes em PostgreSQL.
4. Contract tests verdes para kernels e integrações externas.
5. Budgets medidos atendidos ou risco explicitamente aceito pelo dono.
6. Nenhuma autoridade dupla, writer desconhecido ou fato v1 essencial apenas em JSON.
7. Plano de rollback por fatia e cutover ensaiado.

## Critério para estimar prazo e complexidade

Não estimar o reset completo antes das fases 1 e 2. Ao final delas, cada fatia recebe:

- número de autoridades e writers afetados;
- migrations e volume de dados;
- integrações externas;
- cenários de concorrência e compensação;
- superfícies consumidoras;
- arquivos quentes e risco de conflito;
- custo de rollback;
- p95 e queries atuais/alvo.

O menor custo de infraestrutura continua sendo requisito. Provider nativo permanece chamada em
processo e pode participar da transação local. Nenhum broker, microserviço ou banco adicional
nasce sem problema medido que o exija.

## Decisão recomendada sobre o PR #2258

**REQUEST CHANGES.** Preservar o relatório, corrigir suas marcas de evidência e limitar as
decisões canônicas ao que foi realmente decidido. O plano de execução e a matriz de go-live
devem ser substituídos somente depois do baseline executável e das ADRs do alvo.
