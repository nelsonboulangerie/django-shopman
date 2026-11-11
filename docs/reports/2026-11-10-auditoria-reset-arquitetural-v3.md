# Auditoria do reset arquitetural do Django Shopman, versão 3

**Estado:** proposta consolidada para última reavaliação independente  
**Base factual:** `origin/main` em `7f829e02f89b8c10fc5e00b683a6a31617026fc7`  
**Fontes:** relatório v2 do PR #2258, revisão adversarial do PR #2259, código e decisões do dono  
**Esta versão não autoriza implementação nem altera decisões por si só.**

## 1. Objetivo e pergunta final

O Django Shopman ainda não está em uso comercial. Há uma janela curta para corrigir sua base
antes de dinheiro, documentos fiscais e história operacional reais tornarem mudanças profundas
mais caras.

A pergunta desta auditoria não é “reescrever ou preservar?”. É:

> Qual é a menor transformação coerente que entrega uma arquitetura simples, robusta,
> substituível e pronta para crescer, sem reescrever kernels comprovadamente fortes nem levar
> autoridades erradas para produção?

O reset pretendido é de **produto e camada de aplicação**. Não é descarte indiscriminado do
Core, troca de tecnologia ou criação de microserviços.

## 2. Estado da evidência

### Evidência forte

- O inventário da v2 leu `origin/main` em `62191553b` com 24 agentes somente leitura.
- O código comprova fatos importantes em JSON sem autoridade própria, escrita fora de services
  de kernel e lógica de aplicação dentro do Backstage.
- Existe um proto-Taskman funcional no Backstage, com templates, execuções, estados,
  evidências, supervisão, constraints e serviço transacional.
- A ADR-001 vigente declara imports diretos dos kernels pelo framework e reconhece que trocar
  um kernel exige reescrever seus pontos de uso.
- O produto tem testes extensos, mas os oito cenários críticos selecionados pela v2 ainda não
  constituem uma suíte única e executável de aceitação do reset.

### Limitações que reduzem a força do veredito da v2

- Nenhum teste, migration, seed, corrida ou medição de desempenho foi executado pela auditoria.
- As superfícies Nuxt não receberam auditoria arquitetural suficiente.
- Os 24 relatórios brutos não foram versionados; as citações `r1/` e `r2/` não são
  reproduzíveis.
- Estimativas de prazo e budgets de latência foram propostas sem baseline medido.
- Inventário, inferência e decisão do dono foram misturados em alguns trechos.

Consequência: a v2 é fonte valiosa de hipóteses e mapa de risco, mas não prova sozinha o corte
de go-live nem o plano de execução.

## 3. Decisões e premissas confirmadas

1. O alvo é um **monolito modular**, sem nova infraestrutura por padrão.
2. Kernels fortes devem ser preservados e protegidos por contratos executáveis.
3. A camada de aplicação deve ser organizada por ciclos/capacidades, não pelo público da tela.
4. Projections e surfaces são coisas diferentes: projection prepara leitura; surface apresenta
   e captura intenção.
5. Um domínio deve poder ser atendido por implementação nativa ou solução externa mediante uma
   fronteira explícita, sem comprometer a integração da suíte.
6. Provider nativo permanece em processo e pode participar da transação local; a arquitetura
   não deve cobrar rede, serialização ou broker onde eles não são necessários.
7. Storefront, PDV, iFood, produção completa, compras/recebimento, fiscal real e entrega por
   Machine pertencem à v1.
8. Marketing, B.I. e Concierge podem amadurecer depois, mas o desenho não deve exigir grande
   refatoração para recebê-los.
9. `FiscalDocument` deve existir antes da primeira NFC-e real.
10. Taskman é o nome preferido para o domínio candidato de tarefas, rotinas e pequenos projetos
    operacionais.
11. Spendman é o nome preferido para o domínio candidato da origem operacional comprovada dos
    gastos. Conta Azul permanece autoridade financeira e contábil externa.
12. `Human` e `Assetman` são nomes/fronteiras em avaliação, não packages aprovados.

## 4. Veredito consolidado

**APROVAR O RESET, CONDICIONADO A BASELINE EXECUTÁVEL E ADRS DO ALVO.**

A v3 rejeita dois extremos:

- reescrever services corretos apenas para mudar sua aparência;
- fazer somente hardening de go-live e adiar a reorganização da aplicação que motivou o reset.

O trabalho deve usar quatro verbos diferentes:

1. **Preservar:** kernels, invariantes e services comprovadamente corretos.
2. **Corrigir:** concorrência, idempotência, rede dentro de transação e writers que furam a
   autoridade existente.
3. **Construir:** entidades que hoje não existem como autoridade durável.
4. **Mover:** lógica correta que mora em Shop, Backstage ou Storefront para o módulo de
   aplicação correto, apagando a entrada antiga na mesma fatia.

Não se estima nem inicia a transformação completa antes de provar o baseline e aprovar as
fronteiras.

## 5. Arquitetura alvo

### 5.1 Kernels

Packages pip-instaláveis que respondem perguntas canônicas e possuem linguagem, lifecycle,
invariantes e autoridade próprias. Não importam a aplicação nem internals de kernels irmãos.

Permanecem candidatos fortes à preservação: Cashman, Payman, núcleo do Orderman, ledger e
promessa do Stockman, execução do Craftsman. “Preservar” exige contract tests; não é imunidade
a correções.

### 5.2 Contratos de capacidade e providers

A aplicação não deve depender da localização dos models nem do ORM de uma implementação. Ela
depende de operações semânticas e resultados explícitos.

Cada provider declara seu perfil:

| Perfil | Garantias possíveis | Uso esperado |
|---|---|---|
| Nativo transacional | mesma transação e rollback local | implementação padrão no monolito |
| Remoto operacional | idempotência, timeout, retry, consistência e compensação | ERP/API que assume a capacidade em tempo real |
| Importação/exportação | sincronização, reconciliação e defasagem declarada | planilha ou sistema que não participa do comando online |

Um contrato não promete a mesma atomicidade para os três perfis. A substituição só é válida
quando o provider satisfaz as garantias exigidas pelo ciclo consumidor.

Não é obrigatório criar `typing.Protocol` e registry genérico para cada kernel agora. É
obrigatório fechar a fachada de escrita, explicitar o contrato semântico e impedir que a
aplicação trate o ORM como API pública irrestrita.

### 5.3 Módulos de aplicação

Coordenam ciclos que atravessam kernels, integrations e políticas. O conjunto inicial a validar
é:

- `sales`;
- `orders`;
- `fulfillment`;
- `production`;
- `procurement`;
- `fiscal`;
- `delivery`.

Os nomes não implicam apps Django nem packages instaláveis. Podem começar como pacotes Python
dentro da aplicação, com regras de import e ownership claras.

### 5.4 Projections, integrations e surfaces

- **Projections:** modelos de leitura sem autoridade de escrita.
- **Integrations:** tradução para provedores externos, webhooks e reconciliação.
- **Surfaces:** APIs, Admin e Nuxt; apresentam estado e enviam intenções.

Surface não recalcula regra de negócio. Projection não serve de payload autoritativo para
comando.

## 6. Autoridades que precisam de decisão antes de dados reais

### Obrigatória

#### `FiscalDocument`

Registro autoritativo de emissão, rejeição, cancelamento, referências do provedor e relação com
pedido. Deve substituir as chaves fiscais em `Order.data` antes da primeira NFC-e real.

### Candidatas fortes à construção pré-go-live

#### `PurchaseReceipt`

Recebimento tem identidade, linhas, documento, divergências, ator, evidência e idempotência.
Uma chave persistente de deduplicação não substitui o fato de recebimento. Como
compras/recebimento integram a v1, a autoridade precisa ser decidida antes do corte.

#### `DeliveryRun` e custódia

Corrida, estados externos, tentativas, entregador, Machine, troco e maquininha não devem ter
como única autoridade blocos replicados em `Order.data`. A localização final pode ser Orderman,
um kernel futuro ou módulo da aplicação; a decisão precisa anteceder história real.

#### Revisão de pedido

Diferença a maior/menor, motivo, aprovação, reflexos em pagamento, estoque e fiscal não devem
ser apenas um bloco ao lado do total selado.

### Fundação transversal

Fatos relevantes precisam, quando aplicável, de:

- ator tipado;
- dispositivo e posto;
- correlação e causa;
- data operacional;
- idempotency key/fingerprint;
- referência ao fato que compensam ou substituem.

As colunas sozinhas não resolvem o problema. Writers precisam preenchê-las e testes precisam
provar propagação síncrona e assíncrona.

## 7. Taskman e domínios futuros

Taskman não depende de “segundo consumidor” para ser kernel. O critério correto é possuir
pergunta canônica, linguagem, lifecycle, invariantes e autoridade próprias.

Pergunta candidata:

> Que trabalho precisa ser realizado, por quem, quando, em qual contexto e com qual evidência
> ou verificação?

Escopo inicial candidato:

- tarefas pontuais;
- templates e recorrências;
- checklists;
- atribuição e prazo;
- dependências simples;
- evidência, supervisão e apontamentos;
- ações corretivas;
- pequenos projetos operacionais como agrupamentos de trabalho.

Antes de extrair, uma descoberta adversarial deve comparar três resultados honestos:

1. extrair agora para `packages/taskman`;
2. manter temporariamente no Backstage, com limite e gatilho objetivos;
3. rejeitar o kernel e manter como módulo de aplicação.

`Human`, `Assetman` e `Spendman` seguem o mesmo rito. Nenhum nasce apenas porque será útil no
futuro.

## 8. Suíte de aceitação obrigatória

Os oito cenários selecionados pela v2 devem ser executáveis e bloqueantes antes do go-live:

1. Pix confirmado depois do cancelamento;
2. cartão recusado libera a reserva;
3. PDV com pagamento misto mantém Payman e Cashman coerentes;
4. venda offline do PDV reenviada não duplica efeitos;
5. `finish` simultâneo em dois quiosques preserva produção e estoque;
6. cancelamento depois da baixa compensa estoque, promoção, pagamento e fiscal;
7. recebimento com documento reescaneado não duplica estoque;
8. edição de encomenda trata diferenças a maior e a menor.

Também são necessários cenários de ciclo completo para Loja, PDV, iFood, produção,
compras/recebimento, fiscal, entrega e cancelamento/devolução.

O primeiro passo é mapear testes existentes e reutilizá-los. Não se cria uma segunda suíte
paralela sem saber o que já está provado.

## 9. Plano de ação

### Fase 0: corrigir a verdade canônica

- Separar decisão explícita, inferência e recomendação de engenharia.
- Tratar D-036 como contestada até sua redação refletir substituibilidade como invariante.
- Tratar D-038 como contestada até o baseline executável e a aprovação explícita do corte.
- Preservar D-035 e D-037.
- Transformar fontes temporárias da auditoria em ledger reproduzível ou rebaixar suas
  afirmações a hipótese.

**Saída:** nenhum item da matriz de go-live depende de conclusão não reproduzível.

### Fase 1: baseline executável

- Rodar kernels isolados e integração em PostgreSQL.
- Mapear testes existentes para os oito cenários e preencher lacunas.
- Produzir matriz `fato → autoridade → writers → leitores → retenção → compensação`.
- Medir p50/p95, queries, contenção e chamadas externas nos ciclos críticos.
- Auditar as superfícies para decisões de domínio duplicadas.

**Saída:** baseline verde e custo atual conhecido.

### Fase 2: ADRs do alvo

- Aprovar a taxonomia arquitetural da seção 5.
- Superar explicitamente os trechos incompatíveis da ADR-001.
- Definir contratos e perfis de provider por capacidade, sem abstração universal.
- Definir dependências permitidas dos módulos de aplicação.
- Concluir a descoberta do Taskman.
- Decidir as autoridades da seção 6.

**Saída:** fatias implementáveis sem decisão arquitetural implícita.

### Fase 3: fatos que não podem nascer errados

Ordem inicial, sujeita ao baseline:

1. contexto causal e data operacional;
2. `FiscalDocument`;
3. `PurchaseReceipt`;
4. `DeliveryRun`/custódia;
5. revisão de pedido;
6. Taskman, se aprovado.

Cada fatia exige writer único, migration, leitura canônica, concorrência, idempotência,
compensação e remoção da autoridade anterior.

**Saída:** nenhum fato essencial da v1 nasce apenas em JSON genérico ou sem contexto causal.

### Fase 4: reset da aplicação

- Criar os módulos aprovados sem mover tudo de uma vez.
- Caracterizar o comportamento antes de cada movimento.
- Mover uma autoridade completa e apagar a entrada antiga na mesma fatia.
- Fechar escrita de kernels e instalar gates de import/ownership.
- Retirar do Backstage e Storefront a lógica que não pertence a surfaces.
- Eliminar adapters cuja única função seja esconder dependência invertida.

**Saída:** ciclos v1 atravessam módulos explícitos; surfaces não são segunda camada de domínio.

### Fase 5: ensaio e go-live

- Replay de migrations e ensaio de restauração/rollback.
- Seed e purga sintética reproduzíveis.
- Suíte crítica e contract tests verdes.
- Budgets medidos atendidos ou risco aceito explicitamente.
- Nenhuma autoridade dupla, writer desconhecido ou entidade essencial somente em JSON.

**Saída:** decisão de go-live baseada em evidência, não em um prazo arbitrário.

## 10. Orçamento de complexidade

O orçamento final só nasce depois do baseline. Até lá, valem limites estruturais:

- nenhuma infraestrutura nova sem problema medido;
- provider nativo em processo por padrão;
- nenhuma chamada remota dentro de transação de banco;
- nenhuma abstração genérica sem caso real;
- uma autoridade de escrita por fato;
- nenhuma nova decisão de domínio em surface;
- nenhuma chave top-level nova em JSON para esconder entidade durável;
- cada fatia com rollback e teste de concorrência proporcionais ao risco;
- desempenho comparado ao baseline por ciclo, não por números inventados.

Timebox limita investigação e tamanho da fatia. Não transforma trabalho estrutural necessário
em dívida automática no “dia 21”.

## 11. Riscos que podem derrubar o plano

1. O baseline revelar lógica divergente nas surfaces.
2. A fronteira de capability provider exigir saga onde o ciclo depende de atomicidade local.
3. As entidades candidatas não terem pergunta ou lifecycle próprios e duplicarem kernels.
4. A reorganização competir com correções P1 de dinheiro, estoque ou fiscal.
5. Movimentos quebrarem testes que interceptam símbolos por caminho em vez de comportamento.
6. Fatias manterem escrita antiga “temporariamente” e criarem dupla autoridade.
7. Estimativas serem assumidas antes do mapa de writers e consumidores.

Um P1 real interrompe a fatia afetada. Não cancela automaticamente todo o programa nem legitima
levar autoridade errada ao go-live.

## 12. Instruções para a última reavaliação do Claude

Atue rigorosamente como **coordenador**. Delegue verificações factuais delimitadas a agentes
baratos e apropriados; reserve modelos fortes para síntese arquitetural e red team. Não escreva
código, não altere documentos canônicos e não crie novas decisões. Trabalhe sobre o `main`
atual e cite evidência reproduzível por arquivo/linha ou comando.

Responda obrigatoriamente às perguntas abaixo:

1. A arquitetura alvo preserva corretamente os kernels fortes sem preservar acoplamentos da
   aplicação?
2. A formulação de capability providers permite substituição real sem impor custo ao provider
   nativo?
3. Quais trechos da ADR-001 precisam ser mantidos, superados ou reescritos?
4. D-036 deve ser reescrita? Proponha texto exato.
5. D-038 tem evidência suficiente para continuar `DECIDIDA`? Se não, proponha estado e texto.
6. Quais entidades da seção 6 precisam obrigatoriamente existir antes do primeiro dado real?
7. Taskman deve ser extraído agora, adiado com gatilho ou rejeitado? Aplique os critérios de
   domínio, não contagem de consumidores.
8. Os módulos de aplicação propostos são suficientes e não sobrepostos? Proponha correções de
   nomes e fronteiras.
9. Os oito cenários são os gates mínimos corretos? Identifique cobertura já existente e lacunas.
10. Qual é a menor auditoria das surfaces necessária antes de aprovar o reset de produto?
11. A ordem das fases evita dupla autoridade e refatoração estrutural profunda pós-go-live?
12. Quais estimativas podem ser feitas agora e quais dependem obrigatoriamente do baseline?

Para cada objeção, classifique:

- **BLOQUEANTE**;
- **CORREÇÃO OBRIGATÓRIA**;
- **MELHORIA**;
- **SEM FUNDAMENTO**.

Finalize com um único veredito:

- **APROVAR V3**;
- **APROVAR V3 COM CORREÇÕES**, acompanhado de patch textual exato;
- **REJEITAR V3**, acompanhado de alternativa completa e menor.

Não reabra decisões confirmadas sem evidência nova. Não use quantidade de agentes como prova.
Convergência entre agentes do mesmo modelo não substitui teste, medição ou fonte reproduzível.
