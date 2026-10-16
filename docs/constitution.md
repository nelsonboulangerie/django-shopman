# Constituição da Suite Shopman

**Status:** Canônico
**Escopo:** toda a suite Shopman
**Origem:** consolidada em 2026-04-11; reformulada como Constituição em 2026-10-16

> Esta Constituição contém somente invariantes estáveis. As decisões detalhadas vivem nas
> ADRs; operação e implementação corrente vivem em guias e referências.

## 1. Hierarquia normativa

A arquitetura é documentada em três níveis, do mais estável ao mais mutável.

### 1.1 Constituição

Fixa linguagem, fronteiras e cláusulas pétreas. É curta e não descreve implementação,
rollout ou desenho datado. Uma cláusula só muda por ADR que declare explicitamente uma
emenda constitucional e atualize este documento no mesmo PR.

### 1.2 ADRs

Registram uma decisão, contexto, alternativas e consequências. Podem ser emendadas ou
substituídas por outra ADR. A Constituição aponta para a decisão que detalha cada cláusula,
sem copiá-la.

### 1.3 Guias e referências

Descrevem como trabalhar e o estado observável do sistema: comandos, schemas, inventários,
playbooks e exemplos. Não criam lei e precisam acompanhar Constituição e ADRs.

Em caso de conflito: **Constituição > ADR aceita mais recente > guia/referência > código
acidental**. Divergência entre código e lei é dívida explícita, não mudança silenciosa da lei.

## 2. Cláusulas pétreas

### C1. Independência dos kernels

O código de domínio de um kernel não importa outro kernel. Integrações opt-in só podem viver
em bridges nomeadas (`adapters/` ou `contrib/<outro_kernel>/`), com imports lazy e segurança
quando o outro pacote não está instalado. Porto/adapter só nasce para variação real ou retorno
síncrono necessário; anúncio sem retorno usa signal. Detalhe: [ADR-001](decisions/adr-001-protocol-adapter.md).

### C2. Dinheiro é inteiro em unidade mínima

Valores monetários são inteiros em centavos e usam sufixo `_q`; `float` não representa
dinheiro. Detalhe: [ADR-002](decisions/adr-002-centavos.md).

### C3. Identidade cross-domain usa refs textuais

Entidades preservam sua identidade técnica e expõem refs operacionais. Um kernel referencia
entidade externa por `sku`, `ref` ou `*_ref`, nunca por FK ou `pk` de outro kernel. Detalhe:
[ADR-004](decisions/adr-004-string-refs.md).

### C4. O orquestrador é o encontro dos domínios

`shopman/shop` coordena kernels, composição e política cross-domain. Essa densidade é
deliberada; não autoriza espalhar decisão entre mecanismos nem transformá-la em pacote pip.
Detalhe: [ADR-005](decisions/adr-005-orchestrator-as-coordination-center.md).

### C5. Uma decisão tem um dono

A pergunta canônica de um domínio pertence ao seu kernel; política que só existe no encontro
de domínios pertence ao orquestrador. Cada decisão tem um ponto autoritativo de entrada.
Bridges conectam donos sem transferir titularidade. Detalhe:
[ADR-037](decisions/adr-037-decision-ownership.md).

### C6. O ciclo do pedido tem vocabulário único

Os estados e transições de `Order` pertencem ao Orderman. Orquestrador, read-side e
superfícies consomem essa semântica; não inventam ciclos paralelos. Detalhe:
[ADR-006](decisions/adr-006-order-status-semantics.md).

### C7. Lifecycle é funcional e config-driven

O orquestrador despacha fases explícitas e pequenas, dirigidas pela configuração do canal.
Não há subclasses de lifecycle nem decisão específica de instância escondida em código.
Detalhe: [ADR-007](decisions/adr-007-lifecycle-dispatch-functional.md).

### C8. Superfícies são headless e não decidem

Superfícies consomem Projection com Actions. Projection transporta dado semântico já
resolvido; presentation possui copy, formatação e interação. Command ingress valida a borda e
delega. Superfície não importa kernel nem recalcula política. Detalhes:
[ADR-012](decisions/adr-012-headless-surface-contract.md) e
[ADR-014](decisions/adr-014-surface-data-presentation-cut.md).

### C9. Produção ativa expand-contract

Quando existir a tag `go-live-v1`, migrations são append-only e mudanças de contratos, nomes
ou dados persistidos seguem expansão, migração e contração explícitas. Antes da tag, vale o
regime pré-produção documentado. Detalhe:
[ADR-015](decisions/adr-015-backward-compat-policy-post-prod.md).

### C10. Read-side não é fonte do fato

Projections e B.I. leem e podem materializar derivados recomputáveis; não escrevem nos
ledgers dos kernels nem passam a possuir o fato observado. Fato novo nasce no seu dono.
Detalhe: [ADR-021](decisions/adr-021-bi-cross-suite-read-layer.md).

### C11. Ledger pertence ao domínio do fato

História imutável, estado atual e política computada são conceitos distintos. Um ledger mora
no kernel que possui o fato; correção é novo lançamento, nunca reescrita da história. O
Cashman é o precedente explícito. Detalhe: [ADR-022](decisions/adr-022-cashman-ledger.md).

## 3. Mapa semântico mínimo

| Parte | Pergunta ou responsabilidade |
|---|---|
| Offerman | O que é vendável e qual é seu preço de lista ou faixa de oferta? |
| Stockman | O que pode ser prometido, para quando e em qual quantidade? |
| Craftsman | O que deve ser produzido e qual foi o resultado? |
| Orderman | Qual compromisso comercial foi assumido e qual seu progresso? |
| Payman | Qual obrigação financeira existe e o que aconteceu com ela? |
| Guestman | Quem é o cliente e quais são seus contatos e vínculos comerciais? |
| Doorman | Como autenticar o sujeito e estabelecer confiança para o contexto? |
| Cashman | Quem responde pelo caixa e quais fatos alteraram a gaveta? |
| Buyman | Como comprar e receber insumos de fornecedores? |
| Fiscalman | Como classificar produtos e contratar a emissão fiscal sem o gateway definir o domínio? |
| Watchman | Como observar a saúde operacional sem tomar posse do domínio observado? |
| Utils/Refs | Quais primitivas estritamente transversais evitam duplicação sem ganhar regra de negócio? |
| Orquestrador | Como compor decisões e aplicar política que cruza domínios? |
| Query/read-side | Como expor estado e decisões já resolvidas? |
| Command ingress | Como receber intenção, validar a borda e delegar ao dono? |
| Superfícies | Como cada persona percebe e opera o sistema? |
| Instância | Quais dados, configuração e marca parametrizam a aplicação? |

O inventário físico e a topologia completa pertencem à documentação de arquitetura, não à
Constituição.

## 4. Cortes semânticos que não podem regredir

### 4.1 Preço

Offerman possui preço de lista, faixas e estrutura comercial da oferta. Ele expõe um porto
para preço contextual. Promoção e cálculo que dependam também de cliente, canal,
fulfillment ou pedido são política cross-domain e pertencem ao orquestrador. O resultado
explica os ajustes aplicados; uma superfície não recalcula preço. Decisão de titularidade:
[ADR-019](decisions/adr-019-promotion-belongs-to-the-orchestrator.md).

### 4.2 Promessa

Elegibilidade comercial não é disponibilidade operacional. Stockman é o único dono da
decisão de promessa; saldo bruto, produção planejada e política de demanda são insumos dessa
decisão. O orquestrador pode bloquear ou sequenciar o fluxo com o resultado, mas não repetir
o cálculo. Orderman só confirma compromisso sustentado pela decisão canônica.

### 4.3 Identidade e acesso

Guestman possui identidade comercial, contatos e relacionamento. Doorman possui desafios,
credenciais, autenticação, confiança e retomada de sessão. Múltiplos handles e sua
verificação atravessam um contrato explícito; nenhum service de domínio importa models ou
services do outro kernel. Bridges opt-in continuam permitidas somente nos termos da ADR-001.

## 5. Regras de modelagem

- Estado representa posição atual; evento representa mutação auditável; snapshot representa
  compromisso congelado; `data`/`metadata` são extensão, nunca contrato principal oculto.
- Defaults de uma instância não contaminam kernel ou algoritmo genérico. Código define schema
  e validação; configuração e DB caracterizam a operação.
- Integração externa adapta a linguagem do terceiro na borda; não redefine a semântica interna.
- Novo pacote de kernel exige dois ou mais consumidores reais. Novo estado ou porto exige
  necessidade demonstrada. Conveniência futura não é prova.
- Antes de mover arquivos: definir dono, contrato, transição e teste que impeça a duplicação.

## 6. Critério de conformidade

Uma mudança está em conformidade quando:

1. identifica a decisão e seu único dono;
2. preserva as setas de dependência e as exceções nomeadas;
3. não cria segunda implementação em API, projection, superfície ou orquestrador;
4. mantém fatos e ledgers no domínio correto;
5. trata política da instância como dado declarativo;
6. aplica a ADR-015 quando o regime de produção estiver ativo;
7. atualiza ADR ou guia correspondente sem duplicar lei em vários documentos.

## 7. Emendas

Uma proposta que contrarie qualquer cláusula pétrea deve:

- declarar no título e no corpo da ADR que é emenda constitucional;
- citar a cláusula afetada e justificar por que a exceção não basta;
- atualizar esta Constituição no mesmo PR;
- fornecer migração e enforcement proporcionais ao risco.

Sem esses quatro itens, a proposta é incompatível com a arquitetura, ainda que os testes de
runtime estejam verdes.
