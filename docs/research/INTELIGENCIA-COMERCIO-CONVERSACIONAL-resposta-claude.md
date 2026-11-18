# Inteligência de Comércio Conversacional: arquitetura de referência

> **Estado:** estudo, somente leitura. Nenhum código. **Não é plano vigente**: não altera o
> [CONCIERGE-PLANO-DE-ACAO](../plans/CONCIERGE-PLANO-DE-ACAO.md) nem os WPs em voo da Concierge.
> **Compromisso:** DEV-2026-045.
> **O que é:** a resposta independente do Claude (Fable 5.2) ao prompt "Arquitetura de Inteligência
> Comercial Conversacional de Próxima Geração", escrita sem ler as respostas dos outros agentes,
> para ser comparada com elas.
> **Objeto:** um framework genérico (qualquer mensageria, qualquer modelo, qualquer backend de
> negócio). A Nice, Concierge do Shopman, é só a primeira instanciação e aparece na seção 11.
>
> **Níveis de evidência**, marcados ao longo do texto:
> **[E]** conhecimento científico estabelecido · **[I]** técnica comprovada na indústria ·
> **[P]** abordagem emergente e promissora · **[H]** hipótese ainda não validada (minha, salvo
> indicação) · **[MEDIDO]** fato do repositório, com caminho.
>
> **Sobre as referências:** a lista está no fim. Oito foram conferidas na fonte nesta sessão e
> estão marcadas com ✓; as demais são literatura canônica citada de memória e merecem conferência
> por amostragem antes de qualquer uso externo.

## 0. Em uma página

**O problema.** Um agente comercial conversacional toma decisões sequenciais sob incerteza sobre
o cliente, dentro de regras duras do negócio, com vários objetivos que conflitam, com pouco dado,
retorno atrasado e, detalhe que quase toda arquitetura de agente ignora, **cada frase que ele diz
é um compromisso da empresa** (preço dito é oferta; "vou verificar" é promessa).

**A tese.** Uma inteligência comercial conversacional é **um sistema de decisão que fala**, e
não um modelo de linguagem que decide. A linguagem fica nas duas bordas (entender e dizer); o
meio é um núcleo de decisão tipado, pequeno, auditável e reexecutável. Só essa forma permite as
quatro coisas que o prompt exige ao mesmo tempo: verdade por construção, decisão sob incerteza,
aprendizado causal e independência de plataforma.

**As sete decisões arquiteturais** (cada uma derivada na seção indicada):

1. **Cintura fina.** Entre muitos canais, muitos modelos e muitos backends existe um único
   contrato estreito: o *registro de decisão* (contexto, candidatas, escolhida, probabilidade da
   escolha, regras disparadas, evidências, resultado). Tudo que aprende, audita ou avalia se
   pendura nele (5.1).
2. **Um lugar só decide.** "Inteligência comercial" e "inteligência de relacionamento" não são
   módulos que decidem lado a lado: são modelos de valor e famílias de ações que alimentam **um**
   ponto de decisão. Dois decisores brigam, e ninguém consegue auditar quem ganhou (5.2).
3. **Quatro regimes de decisão**, nunca misturados: determinístico (fato, dinheiro, permissão),
   probabilístico (o que o cliente quer, o que vai acontecer), generativo (como dizer) e
   autorizado (o que só o cliente ou uma pessoa da equipe pode liberar) (5.6).
4. **Resposta com prova.** Toda afirmação de uma resposta aponta para um fato do sistema de
   registro, um recibo de ação, uma política ou é cortesia. Afirmação sem lastro não sai (4.6).
5. **Restrição de conselheiro.** A ação comercial só entra no conjunto elegível se, na crença do
   sistema, ela não piora a situação do cliente. Dentro desse conjunto, maximiza-se o valor do
   relacionamento. Vender deixa de ser o objetivo e passa a ser uma ação entre outras (4.3).
6. **Escassez tem preço único.** Estoque perecível, capacidade de produção, janela de entrega e
   atenção da equipe entram na decisão como preços-sombra da pesquisa operacional. É o que liga
   a conversa à operação (4.4).
7. **Aprender em camadas, com a régua antes do motor.** Cada camada (entender, prever, decidir,
   dizer) tem seu sinal, sua métrica e seu portão de promoção. O sistema nasce registrando
   probabilidades de escolha, mesmo quando a política ainda é fixa, porque é isso que torna o
   passado reaproveitável (seções 7 e 8).

**O que é honesto dizer sobre escala.** Com o volume de uma loja só (a Nelson recebe da ordem de
dez conversas por dia [MEDIDO]), um teste A/B clássico para detectar 5 pontos de conversão leva
cerca de sete meses. A arquitetura não pode depender de "aprender com dados" no curto prazo. Ela
precisa ser boa por conhecimento e por construção no dia 1, e aprender só onde o volume permite
(seção 7). Quem promete aprendizado por reforço nessa escala está vendendo aparência.

## 1. Formulação do problema e tese

### 1.1 As oito propriedades que definem o problema

| # | Propriedade | Consequência para a arquitetura |
|---|---|---|
| P1 | **Observabilidade assimétrica.** O lado do negócio (preço, estoque, pedido) é plenamente observável, desde que consultado. O lado do cliente (necessidade, intenção, humor, confiança) é latente | Incerteza se modela só sobre o cliente. Sobre o negócio não há crença: há consulta ao sistema de registro, ao vivo. O modelo nunca "lembra" um preço |
| P2 | **Iniciativa mista.** O cliente também age, muda de assunto, corrige, some | Não é um fluxo; é um controle em malha fechada, turno a turno, com o silêncio como evento |
| P3 | **Fala que obriga.** Informar preço é ofertar; prometer é dever. No Brasil, a oferta suficientemente precisa vincula o fornecedor (CDC, art. 30); no Canadá, a empresa respondeu pela política que o robô inventou (*Moffatt v. Air Canada*, 2024 BCCRT 149) | Verdade não é métrica de qualidade: é invariante. Promessa é um objeto com dono, prazo e estado |
| P4 | **Vários objetivos em conflito**: margem agora, satisfação, confiança, custo de atendimento, segurança | Nenhum escalar único. Hierarquia: invariantes, restrições, só depois otimização (4.5) |
| P5 | **Retorno esparso, atrasado e confundido.** A recompra vem em semanas; quem recebe oferta já era diferente de quem não recebe | Aprender exige aleatorização registrada, não correlação; e substitutos validados para o longo prazo |
| P6 | **Pouco dado**, e por muito tempo | Priors, conhecimento especialista e *pooling* hierárquico antes de qualquer aprendizado *online* |
| P7 | **Erros de custo assimétrico.** Mudar a sacola errado custa muito mais que responder uma consulta a mais; afirmar alérgeno errado é inaceitável | Limiares de ação diferentes por tipo de ação, derivados do custo do erro (4.2) |
| P8 | **Entrada adversarial.** O texto do cliente pode conter instruções; o agente tem poder sobre dinheiro | Texto não confiável nunca chega a um componente com autoridade de ação (9.2) |

### 1.2 Formulação formal

O problema é um **processo de decisão de Markov parcialmente observável, restrito e
multiobjetivo** [E] (Kaelbling et al., 1998; Altman, 1999; Roijers et al., 2013):

```
⟨ S, A, O, T, Z, R, C, γ ⟩

S = W × K × H        estado
  W  mundo do negócio: catálogo, preço, estoque, capacidade, pedidos   (observável por consulta)
  K  cliente latente: tipo θ, objetivos g, atrito e, confiança τ        (não observável)
  H  história comum: o que foi dito, perguntas no ar, compromissos      (observável, registrada)

A(s)                 ações tipadas; o conjunto viável depende do estado (estoque, permissão, janela)
O                    observações: mensagens, toques, silêncios, eventos do backend
T, Z                 dinâmica e modelo de observação
R : S×A → ℝ^d        recompensa VETORIAL (margem, satisfação, confiança, esforço, custo, segurança)
C                    restrições: duras (por estado) e de longo prazo (em expectativa)
```

O agente mantém uma crença `b(K)` e escolhe `a ∈ A_seguro(b, W, H)`.

Três observações que evitam o erro clássico de tratar a formulação como receita:

1. **O POMDP é modelo conceitual, não algoritmo.** Resolver POMDPs de diálogo exatamente é
   intratável, e a geração de sistemas estatísticos de diálogo (Williams & Young, 2007; Young et
   al., 2013) só funcionou com fatoração agressiva e espaços-resumo, em domínios minúsculos e com
   simuladores [E]. O que se aproveita é a disciplina: separar estado, crença, ação e valor.
2. **A fatoração P1 é o que torna o problema tratável.** A parte grande e exata do estado (`W`)
   não entra na crença; a parte incerta (`K`) é pequena. Quase toda alucinação comercial de um
   agente baseado em LLM é uma violação de P1: tratar `W` como algo a inferir.
3. **O horizonte longo passa por uma variável só.** O efeito de hoje sobre o futuro é mediado,
   em primeira ordem, pelo estado do relacionamento (confiança `τ`, hábito, compromissos
   cumpridos). Modelar esse estado explicitamente e dar a ele um valor permite decidir de forma
   quase míope com um termo de futuro, em vez de aprender uma política de horizonte longo por
   reforço, que o volume de dados não sustenta (4.1) [H].

### 1.3 Tese arquitetural

> **Um sistema de decisão que fala.** O entendimento converte linguagem em atos tipados com
> incerteza; um núcleo simbólico e probabilístico mantém crença, consulta fatos, aplica
> invariantes e escolhe a próxima ação por valor esperado sob restrições, registrando a
> probabilidade da escolha; a expressão converte o plano em linguagem que só afirma o que tem
> lastro. Modelos de linguagem atuam nas bordas; a autoridade fica no núcleo; o aprendizado
> acontece por camada, com avaliação contrafactual.

Corolários:

- **C1. Espaço de ações fechado e tipado.** Se o modelo escolhe a ação em texto livre, não
  existe probabilidade de escolha, e sem ela não existe avaliação contrafactual (Dudík et al.,
  2011; Bottou et al., 2013; Agarwal et al., 2016) [E]. Esta é a condição técnica para "uma
  inteligência que pode ser medida".
- **C2. Três níveis de ação**: *movimento* (perguntar, informar, recomendar, ofertar, confirmar,
  resolver, compensar, verificar, encaminhar, aguardar, encerrar), *conteúdo* (qual produto, qual
  compensação) e *palavras*. O espaço de movimentos tem dezenas de elementos e se aprende com
  pouco dado; o conteúdo é um problema de ranking dentro do movimento; as palavras são geração
  verificada. É a mesma decomposição do Cicero, que venceu humanos em *Diplomacy* separando
  planejamento estratégico de intenções e geração condicionada a elas, com filtros (Meta FAIR,
  2022) [E], e da linha "comandos" da Rasa (Bocklisch et al., 2024 ✓) [I].
- **C3. Núcleo puro e reexecutável.** A decisão é função de (evento, estado, fatos, versão da
  política). Chamadas a modelo são gravadas. Qualquer turno do passado pode ser reexecutado com
  outra política: é teste de regressão, auditoria e base de avaliação *offline* de uma vez.
- **C4. Portas, não integrações.** Canal, modelo, sistema de registro, equipe e relógio são
  portas com contrato e teste de conformidade (5.4).
- **C5. A abstenção é ação de primeira classe.** "Não sei, vou verificar", "pergunto antes",
  "passo para uma pessoa" e "não faço nada" têm valor esperado calculável, não são falhas (4.2).

### 1.4 Questões que precisam de resposta antes de implementar

| # | Questão | Por que bloqueia |
|---|---|---|
| Q1 | Qual é a unidade de valor e a janela de atribuição (conversa, cliente em 30 dias, cliente em 90)? | Define a recompensa; sem isso toda métrica é intermediária |
| Q2 | Qual é a lista fechada de movimentos da v1, e quem autoriza estendê-la? | Define `A`; ação fora da lista não existe |
| Q3 | Que substituto do interesse do cliente é aceitável para a restrição de conselheiro? | O interesse do cliente não é observável; o substituto precisa ser combinado e auditável |
| Q4 | Que autoridade se delega de antemão (teto de compensação por incidente e por cliente)? | Separa o autônomo do que pede pessoa |
| Q5 | Que garantia de identidade cada canal dá, e que ações cada nível de garantia libera? | Sem identidade verificada não há mudança de pedido nem dado pessoal |
| Q6 | Qual base legal (LGPD) sustenta cada uso de dado para personalizar? | Parecer jurídico; desenho de memória depende dele |
| Q7 | Que decisões são aprendíveis com o volume de um inquilino, e quais só com vários? | Evita prometer aprendizado impossível (7.1) |
| Q8 | É aceitável aleatorizar ofertas entre clientes? (Preço nunca.) | Sem aleatorização não há medida causal |
| Q9 | Como se mede confiança? | É a variável de estado de longo prazo; precisa de definição operacional (6.3) |

## 2. Revisão crítica das abordagens

Formato: o que é, o que a evidência sustenta, e o veredito para esta arquitetura.

### 2.1 Decisão sob incerteza

**Teoria da decisão bayesiana e valor da informação** [E] (Raiffa & Schlaifer, 1961; Howard,
1966; Berger, 1985). Agir pela utilidade esperada sob a crença; perguntar quando o valor
esperado da resposta supera o custo de perguntar. Horvitz (1999) aplicou exatamente isso a
interfaces de iniciativa mista (agir, perguntar ou não fazer nada); Rao & Daumé III (2018)
ranquearam perguntas de esclarecimento por valor esperado de informação; Lin et al. (2024 ✓)
formalizam o diálogo em que o agente ajuda a pessoa a decidir como otimização conjunta sob
informação parcial dos dois lados. **Veredito: adotar como
espinha da decisão.** Barato, explicável, funciona com crenças grosseiras, e dá de graça a regra
"quando perguntar".

**Opção de rejeitar e aprender a delegar** [E] (Chow, 1970; Mozannar & Sontag, 2020). Abster-se
é ótimo quando a confiança cai abaixo de `1 − custo_de_abster / custo_do_erro`. **Veredito:
adotar** como forma do encaminhamento e do "vou verificar".

**POMDP completo** [E como teoria; uso restrito na prática]. **Veredito: usar como modelo
mental, não como solucionador** (1.2).

### 2.2 Aprendizado por interação

**Bandits contextuais e Thompson sampling** [E][I] (Li et al., 2010; Chapelle & Li, 2011; Russo
et al., 2018; Lattimore & Szepesvári, 2020). Fundamento maduro para escolher entre poucas ações
com retorno rápido. O Decision Service da Microsoft (Agarwal et al., 2016) mostra o que quebra
na prática: registro incorreto de probabilidades, retorno atribuído errado, laços de
realimentação. **Veredito: adotar para o nível de movimento e para variações de conteúdo, com
priors informativos e só depois da instrumentação.** Variantes necessárias: conservadora
(desempenho nunca abaixo de uma fração da política base; Wu et al., 2016; Kazerouni et al.,
2017), com restrições de recurso (Badanidiyuru et al., 2013), hierárquica (Hong et al., 2022),
não estacionária (Garivier & Moulines, 2011) e com retorno atrasado (Chapelle, 2014).

**Aprendizado por reforço profundo, online** [E como ciência; contraindicado aqui]. Exige
volume, exploração e simuladores que o comércio de uma loja não tem; os desafios de RL em
sistemas reais estão catalogados (Dulac-Arnold et al., 2021). **Veredito: não usar online. RL
*offline* restrito (Levine et al., 2020) fica como pesquisa da fase mais avançada**, para
sequências de vários turnos, e só com portões de alta confiança (Thomas et al., 2015; 2019).

**Avaliação fora da política** [E] (Dudík et al., 2011; Swaminathan & Joachims, 2015; Li et al.,
2011). Estima o valor de uma política nova com dados da antiga, se as probabilidades de escolha
foram registradas e a política antiga explorava. Com pouco dado, só avalia políticas próximas da
que gerou o registro (o tamanho efetivo da amostra desaba). **Veredito: adotar, com essa
limitação escrita**; por isso a melhoria é incremental, nunca um salto.

### 2.3 Causalidade

**Efeito incremental e *uplift*** [E][I] (Radcliffe & Surry, 2011; Künzel et al., 2019; Wager &
Athey, 2018; Gutierrez & Gérardy, 2017). A pergunta certa não é "quem compra?" e sim "em quem a
ação muda o resultado?". Ascarza (2018) mostrou em campo que mirar clientes de maior risco de
abandono pode ser inútil ou contraproducente: quem tem mais risco não é quem mais responde.
**Veredito: adotar o conceito desde o dia 1 (toda ação proativa pergunta pelo incremento) e
adiar os modelos de efeito heterogêneo**, que pedem milhares de observações aleatorizadas.

**Métodos observacionais não substituem experimento** [E]. Em 15 experimentos grandes de
publicidade, métodos observacionais sofisticados erraram o efeito medido por experimento, com
frequência por muito (Gordon et al., 2019). E medir retorno de pequenas intervenções é
estatisticamente caro mesmo com milhões de observações (Lewis & Rao, 2015). **Veredito:
aleatorizar pouco, sempre, e registrar; desconfiar de qualquer ganho que só exista em
correlação.**

**Longo prazo por substitutos** [E][P] (Prentice, 1989; Athey et al., 2019; Yang et al., 2024 ✓).
Resultados de longo prazo podem ser imputados por um índice de substitutos de curto prazo, e
políticas otimizadas no índice chegam perto das otimizadas no resultado real (Yang et al., em
dois experimentos de retenção). A condição é forte: o substituto precisa capturar o caminho
causal. **Veredito: adotar com validação periódica; um substituto nunca vira meta sem prova**
(8.3).

### 2.4 Recomendação e comportamento de compra

**Recomendação clássica** [E][I] (Koren et al., 2009; Linden et al., 2003; Gomez-Uribe & Hunt,
2015). Madura, mas calibrada para catálogos enormes e muitos usuários. Em compra recorrente de
catálogo pequeno, **a frequência pessoal é uma base muito forte**: modelos simples de frequência
empatam ou vencem redes profundas em "próxima cesta" (Hu et al., 2020; Li et al., 2023), e boa
parte do "progresso" neural não se reproduz contra bases bem ajustadas (Dacrema et al., 2019).
Na Booking.com, ganho *offline* de modelo não se correlacionou com ganho de negócio (Bernardi et
al., 2019) [I]. **Veredito: começar por frequência pessoal, coocorrência e regras de
disponibilidade; modelo mais rico só com prova em experimento.**

**Recomendação conversacional** [E][P] (Christakopoulou et al., 2016; Jannach et al., 2021). O
ganho específico da conversa é a elicitação: perguntar o que reduz mais a incerteza. **Veredito:
é o mesmo valor da informação de 2.1; não precisa de subsistema próprio.**

**Modelos de recompra e valor do cliente** [E] (Schmittlein et al., 1987; Fader et al., 2005;
Rossi et al., 2005). BG/NBD e similares estimam probabilidade de "ainda ativo" e compras futuras
só com o histórico de transações, com poucos parâmetros e *pooling* bayesiano entre clientes.
**Veredito: adotar como estimador do valor do relacionamento**; é o tipo de modelo certo para
pouco dado.

**Gestão de receita e preço-sombra** [E][I] (Gallego & van Ryzin, 1994; Talluri & van Ryzin,
2004). O valor de vender uma unidade escassa é a margem menos o custo de oportunidade daquela
unidade. **Veredito: adotar o conceito como contrato entre operação e decisão** (4.4); é raro em
sistemas de recomendação e é onde um backend de operações integrado vira vantagem.

### 2.5 Ciência do serviço e do comportamento

- **Recuperação de serviço** [E]. Justiça percebida (do resultado, do processo e do trato)
  explica a satisfação após falha (Tax et al., 1998; Smith et al., 1999; Orsingher et al.,
  2010). Compensação tem retorno decrescente e depende do tipo de falha (Gelbrich & Roschk,
  2011). O "paradoxo da recuperação" existe para satisfação, mas a meta-análise não o encontra
  para recompra (de Matos et al., 2007). **Consequência:** falhar e compensar não é estratégia;
  resolver rápido, com explicação e cortesia, é.
- **Esforço do cliente** [I] (Dixon et al., 2010). Reduzir esforço prevê lealdade melhor que
  "encantar". **Consequência:** número de mensagens até resolver e recontato são métricas de
  primeira linha.
- **Confiança** [E] (Mayer et al., 1995; Morgan & Hunt, 1994): competência, benevolência e
  integridade. **Consequência:** a arquitetura dá uma leitura operacional a cada uma
  (acerto, restrição de conselheiro, compromissos cumpridos).
- **Persuasão por modelos de linguagem** [E recente]. GPT-4 com dados pessoais do interlocutor
  foi mais persuasivo que humanos em debate em 64% dos pares desiguais (Salvi et al., 2025 ✓).
  **Consequência:** personalizar a persuasão funciona, e por isso mesmo precisa de limite
  estrutural, não de boa intenção (Susser et al., 2019; Mathur et al., 2019).
- **Otimizar engajamento não é otimizar bem-estar** [E] (Kleinberg et al., 2024; Milli et al.,
  2021), e sistemas que aprendem podem deslocar a preferência do usuário para o que é mais fácil
  de prever (Carroll et al., 2022). **Consequência:** a taxa de aceite de oferta nunca é a
  recompensa sozinha.
- **Revelar que é automação** [E, contexto específico]. Em vendas ativas por voz, revelar o robô
  antes da conversa derrubou compras em cerca de 80% (Luo et al., 2019). Não se segue que
  ocultar seja aceitável: o AI Act europeu exige a informação (art. 50) e a régua de confiança
  desta arquitetura também. Fica como hipótese a testar em comércio de relacionamento (H9).

### 2.6 Modelos de linguagem e agentes

- **Agentes com ferramentas em laço** [I][P] (Yao et al., 2023; Anthropic, 2024). Flexíveis e
  rápidos de montar. Limites medidos: em tarefas de varejo com política, o melhor modelo da
  época resolvia menos da metade e, exigindo acerto em 8 de 8 repetições, menos de 25% (Yao et
  al., 2024); com usuário que também age, o desempenho cai mais (Barres et al., 2025 ✓); em
  conversas de vários turnos, queda média de 39% frente à mesma tarefa dada de uma vez (Laban et
  al., 2025 ✓). Custos e reprodutibilidade de avaliações de agentes são frágeis (Kapoor et al.,
  2024). **Veredito: o laço livre não é base aceitável para dinheiro e promessa.**
- **Arquiteturas cognitivas** [P] (Sumers et al., 2024). Úteis como vocabulário (memória de
  trabalho, episódica, semântica, procedimental); adoto a taxonomia de memória (6.1).
- **Incerteza de modelos de linguagem** [E parcial]. Confiança verbalizada é mal calibrada sem
  ajuste (Tian et al., 2023); calibração posterior funciona (Guo et al., 2017); predição
  conforme dá conjuntos com cobertura garantida sob permutabilidade (Angelopoulos & Bates,
  2023); entropia semântica detecta parte das confabulações (Kuhn et al., 2023). **Veredito:
  tratar o leitor como um sensor a calibrar contra rótulos, nunca confiar na autoavaliação
  crua.**
- **Injeção de instrução** [E] (Greshake et al., 2023; OWASP, 2025). Não há defesa confiável por
  prompt. O que funciona é arquitetura: separar fluxo de controle de dado não confiável e dar
  capacidades explícitas (Debenedetti et al., 2025 ✓, com 77% das tarefas resolvidas com
  garantia de segurança contra 84% sem defesa). **Veredito: adotar o princípio** (9.2).
- **Priors vindos de LLM** [P]. Preferências sintéticas geradas por LLM reduzem o arrependimento
  inicial de bandits contextuais (Alamdari et al., 2024 ✓). **Veredito: usar como prior fraco,
  com peso pequeno e declarado** (7.2).
- **Juiz automático** [I com ressalvas]. Vieses conhecidos (Zheng et al., 2023); precisa ser
  alinhado a critérios humanos, que por sua vez derivam ao avaliar (Shankar et al., 2024).
  **Veredito: juiz só depois de medido contra pessoa.**
- **Protocolos de comércio para agentes** [P]. ACP, AP2 e UCP (2025 e 2026) padronizam
  descoberta, sacola, checkout e mandato de pagamento entre agentes e lojistas. **Veredito:
  alinhar o vocabulário da porta de comércio a eles onde for barato**, porque o mesmo contrato
  servirá ao agente do cliente no futuro (12.1). Não conferi as especificações oficiais.

## 3. Arquiteturas alternativas

| | Arquitetura | Acerta | Falha no que este problema exige |
|---|---|---|---|
| A | **LLM com ferramentas em laço** (só prompt) | Linguagem livre, cobertura ampla, rápido de fazer | Invariantes dependem de obediência ao prompt (P3); texto do cliente chega a quem tem ferramenta (P8); sem probabilidade de escolha (C1); latência e variância altas; degrada em vários turnos |
| B | **Intenções e fluxos** (árvore clássica) | Previsível, barato, auditável | Uma intenção por mensagem; frágil à linguagem real; não decide sob incerteza; não aprende |
| C | **Leitor que emite comandos + fluxos em código** | Verdade por construção; multi-intenção; estado explícito | Reativo: responde bem, mas não tem crença, valor, oportunidade nem laço de aprendizado. É um ótimo atendente e nenhum conselheiro |
| D | **Política de diálogo de ponta a ponta** (POMDP ou RL) | Ótimo de princípio | Fome de dados, exploração insegura, opaca, depende de simulador de usuário que não é confiável |
| E | **Vários agentes LLM** (supervisor + especialistas) | Modularidade aparente | Erro composto, custo e latência multiplicados, difícil de avaliar; "especialistas" deveriam ser funções, não agentes; e viola "um lugar só decide" |
| **F** | **Proposta: núcleo de decisão tipado com LLM nas bordas** | Soma C (verdade, estado) com decisão por valor esperado, registro contrafactual e aprendizado por camada | Custo: mais desenho inicial; lista fechada de ações exige curadoria; a naturalidade da fala depende de bons moldes ou de redação verificada |

Por que F e não "A com guardrails": guardrail é verificação depois do fato, e verificador só
pega o que previu. Em F o que não pode errar não depende de verificador, porque nunca foi
delegado ao modelo. Por que F e não C: C é a metade de F que garante a verdade; falta a metade
que decide e aprende. **C é o primeiro degrau de F, não um concorrente** (seção 10).

## 4. Modelo de decisão

### 4.1 Regra geral

```
a* ∈ argmax  Q(b, a)        sujeito a   a ∈ A_seguro(b, W, H)
       a

Q(b, a) = E_b[ m(a) − Σ_k μ_k · q_k(a) + λ · ΔR(a) − κ(a) ]

  m(a)      margem de contribuição imediata esperada
  μ_k       preço-sombra do recurso escasso k (4.4);  q_k(a) o quanto a ação consome dele
  ΔR(a)     variação esperada do valor do relacionamento (recompra futura, via confiança e hábito)
  κ(a)      custo de servir: mensagens, tokens, tempo de pessoa
  λ         peso do futuro, escolhido pelo dono e exibido, nunca escondido
```

`A_seguro` é a interseção de três filtros, nesta ordem:

1. **Invariantes** (determinísticos, 4.6 e 9.1): viável no sistema de registro, permitido pela
   política, autorizado para o nível de identidade, dentro da janela do canal.
2. **Restrição de conselheiro** (4.3).
3. **Limites de contexto**: no máximo uma iniciativa comercial não pedida por conversa; nenhuma
   com atrito alto, reclamação aberta ou compromisso da casa vencido.

A regra é quase míope de propósito (1.2, observação 3). O termo `λ · ΔR` é onde o longo prazo
entra, estimado por um modelo de recompra (2.4) e por substitutos validados (8.3).

### 4.2 Perguntar, verificar, encaminhar, aguardar

**Perguntar ao cliente.** Para uma pergunta `q` com respostas possíveis `y`:

```
VOI(q) = Σ_y P(y | b) · max_a Q(b_y, a)  −  max_a Q(b, a)        pergunta se  VOI(q) > c_q
```

`c_q` inclui atrito, risco de abandono e o custo da mensagem no canal. No caso de duas
interpretações, com `p` a probabilidade da mais provável, `L` o custo de agir errado e `c` o
custo de perguntar:

```
pergunta  ⇔  (1 − p) · L > c  ⇔  p < 1 − c / L
```

Isso **deriva**, em vez de postular, uma regra que boas atendentes seguem e que a Nice chegou
empiricamente (V2, H1c): na dúvida sobre uma *mudança* (L alto), pergunta; na dúvida sobre uma
*consulta* (L é uma mensagem a mais), responde as duas leituras mais prováveis. Um limiar único
de confiança para tudo é o erro comum.

**Verificar com a equipe e encaminhar.** A incerteza tem cinco naturezas, e cada uma tem um
caminho de resolução diferente. Misturá-las é a origem de quase todo comportamento ruim:

| Incerteza sobre | Resolve-se | Nunca |
|---|---|---|
| Um fato do negócio | Consultando o sistema de registro; se ele não tem, perguntando a uma pessoa da equipe, com prazo ("vou verificar") | Estimando. Para fato, o custo do erro é tratado como infinito |
| O que o cliente quis dizer | Perguntando, se `VOI > custo`; senão, cobrindo as duas leituras | Escolhendo calado em ação que muda algo |
| O que o cliente prefere | Oferecendo com exploração registrada | Assumindo por estereótipo |
| O efeito da nossa ação | Aleatorizando e medindo | Lendo correlação |
| O próprio modelo | Calibração, conjuntos conformes, segunda opinião por regra | Confiando na autoconfiança do modelo |

Encaminhar a uma pessoa segue a regra de Chow: abaixo de `1 − c_h / L` de confiança, com `c_h`
o custo da atenção humana, que é ela mesma um recurso com preço-sombra (4.4). Daí sai uma
distinção útil: **verificação assíncrona** (a pessoa responde uma pergunta exata, a conversa
continua com o agente) custa muito menos atenção que **transferência** (a pessoa assume). A
transferência fica para o que as regras mandam (risco, reclamação, pedido explícito de pessoa).

**Aguardar e não fazer nada** são ações com valor: `Q(b, nada) = 0` é a base contra a qual toda
iniciativa se compara. Iniciativa comercial precisa de evidência positiva; o silêncio não.

### 4.3 Restrição de conselheiro

Seja `u_c(a)` a utilidade do cliente e `a_0` a melhor ação não comercial (responder o que foi
perguntado). Uma ação comercial `a` só é elegível se

```
E_b[ u_c(a) ]  ≥  E_b[ u_c(a_0) ]          e          P( arrependimento | a aceita ) ≤ ρ
```

Ou seja: maximiza-se o valor da empresa **dentro do conjunto de ações que não pioram o cliente
em expectativa**. É a formalização de "interesses legítimos do cliente" e de benevolência
(Mayer et al., 1995), e é uma restrição, não um termo da soma: um termo se compra com margem,
uma restrição não.

`u_c` não é observável. Os substitutos admissíveis, do mais forte ao mais fraco: (i) aderência à
necessidade declarada na conversa; (ii) preferência revelada por recompra do próprio cliente;
(iii) taxa de "recompra sem arrependimento" do item na população, no mesmo contexto; (iv)
ausência de cancelamento, devolução ou reclamação após aceite. O aceite da oferta **não** é
substituto de `u_c`: é justamente o que a persuasão infla (Salvi et al., 2025; Carroll et al.,
2022). Esta é a decisão mais importante a calibrar com o dono (Q3) e é uma hipótese a testar
(H1).

### 4.4 Preço-sombra: a ponte com a operação

Para cada recurso escasso `k`, o backend informa (ou o framework estima) `μ_k`, o valor de uma
unidade a mais daquele recurso:

| Recurso | Sinal de `μ` | Efeito na decisão |
|---|---|---|
| Estoque de perecível perto do fim do dia | negativo (sobra tem custo) | Sobe no ranking de sugestões, se passar pela restrição de conselheiro |
| Últimas unidades de item muito procurado | alto | Não é empurrado como complemento; é oferecido a quem pediu |
| Capacidade de produção ou janela de entrega | alto no pico | Sugere outro horário; prazo prometido vem do sistema |
| Atenção da equipe | alto no pico | Prefere verificação assíncrona à transferência |
| Orçamento de mensagens do canal | constante | Uma resposta por turno; iniciativa precisa pagar a mensagem |

É a ideia de *bid price* da gestão de receita aplicada à próxima ação. O contrato é opcional:
backend que não informa `μ` recebe zero, e o sistema continua correto, só menos esperto.

### 4.5 Vários objetivos, sem reduzir tudo a dinheiro

Três camadas, em ordem lexicográfica:

1. **Invariantes** (nunca trocados por nada): verdade das afirmações, autorização, lei,
   segurança alimentar e física, privacidade. Garantidos por construção, não por penalidade.
2. **Restrições** (pisos e tetos): interesse do cliente (4.3); taxa de reclamação, de recontato
   e de arrependimento abaixo de teto; carga sobre a equipe abaixo da capacidade. As de longo
   prazo são tratadas como processo de decisão restrito (Altman, 1999), com multiplicadores
   atualizados por subida dual:
   `η_i ← max(0, η_i + ρ · (ĝ_i − c_i))`. Cada `η_i` é legível: quanto de margem se está
   pagando para manter aquela restrição.
3. **Otimização** (só aqui há troca): o `Q` de 4.1, com `λ` e demais taxas de troca elicitadas
   do dono (Keeney & Raiffa, 1976) e exibidas.

Por que restrições e não uma soma ponderada: a soma ponderada só alcança a parte convexa da
fronteira de Pareto e esconde a troca dentro de pesos que ninguém audita; o método de
restrições alcança qualquer ponto da fronteira e deixa cada piso visível (Miettinen, 1999;
Hayes et al., 2022) [E]. O relatório ao dono mostra a fronteira estimada (por exemplo, margem
contra recontato), não um número.

### 4.6 Resposta com prova e livro de compromissos

Toda resposta é um plano de partes; toda parte contém afirmações; toda afirmação tem um lastro:

| Tipo de afirmação | Lastro exigido | Exemplo |
|---|---|---|
| Fato do negócio | id de um fato da ficha, com fonte e validade | preço, disponibilidade, horário, prazo, total |
| Ação realizada | id de um recibo do executor | "separei", "cancelei", "avisei a equipe" |
| Política | id da regra | "não fazemos desconto por aqui" |
| Promessa | entrada no livro de compromissos, com dono e prazo | "te respondo em até 10 minutos" |
| Cortesia | nenhum | saudação, agradecimento |

A analogia é com código que carrega a própria prova (Necula, 1997): quem envia não precisa
confiar em quem escreveu, só conferir o lastro. Há dois modos de produzir respostas assim, e a
arquitetura aceita os dois: **molde** (frase da casa preenchida pelo código, prova por
construção) e **redação com marcadores** (o modelo escreve com `{F1.preco}`, o código preenche e
um verificador reprova o que escapar). O molde é a base sempre gerada; a redação só substitui a
base se passar e se houver prova de que melhora algum resultado (8.2).

O **livro de compromissos** registra cada promessa, oferta e orçamento feitos na conversa:
texto, prazo, lastro, estado (aberto, cumprido, quebrado, expirado). A conversa comercial é uma
rede de pedidos e promessas (Winograd & Flores, 1986; Singh, 2000), e a métrica que decorre,
**integridade de compromissos** (cumpridos no prazo sobre feitos), é a leitura operacional de
"integridade" na confiança (H7).

## 5. Arquitetura modular

### 5.1 Visão geral: a cintura fina

```
   canais (WhatsApp, web, voz, e-mail...)        modelos (qualquer provedor, regra, modelo próprio)
              │                                              │
        ┌─────▼──────┐                                ┌──────▼──────┐
        │ Porta de   │                                │ Porta de    │
        │ Canal      │                                │ Modelo      │
        └─────┬──────┘                                └──────┬──────┘
              │        ┌──────────────────────────────┐      │
   evento ───►│        │        NÚCLEO (puro)         │◄─────┘
              ├───────►│ 1 Entender   2 Estado/crença │
              │        │ 3 Fatos      4 Decidir       │──────► REGISTRO DE DECISÃO  ◄── a cintura
   resposta ◄─┤◄───────│ 5 Executar   6 Dizer         │        + livro de compromissos
              │        └───────┬──────────────┬───────┘        + resultados juntados depois
              │                │              │                          │
        ┌─────▼──────┐  ┌──────▼──────┐ ┌─────▼──────┐          ┌────────▼─────────┐
        │ Porta de   │  │ Porta de    │ │ Porta de   │          │ PLANO DE         │
        │ Relógio    │  │ Comércio    │ │ Equipe     │          │ APRENDIZADO      │
        └────────────┘  │ (sistema de │ └────────────┘          │ (fora do turno)  │
                        │  registro)  │                         └──────────────────┘
                        └─────────────┘
        ───────────────── PLANO DE GOVERNANÇA: regras da casa, autoridade, privacidade, freio ─────
```

O registro de decisão é a cintura porque é o único artefato que todos os lados entendem: o
canal não sabe o que é margem, o backend não sabe o que é turno, o modelo não sabe o que é
política. Trocar qualquer ponta não invalida o histórico.

### 5.2 Reorganização das "sete inteligências" do enunciado

| Responsabilidade do enunciado | Onde mora aqui | Observação |
|---|---|---|
| Contexto | Entender (1) + Estado e crença (2) | |
| Decisão | Decidir (4) | **O único lugar que escolhe** |
| Comercial | Fatos (3) + o *conselheiro de oferta*, serviço chamado por (4) | Fornece candidatas e valores; não decide |
| Relacionamento | Estado do relacionamento em (2) + família de movimentos de cuidado em (4) + livro de compromissos | Fornece restrições e valores; não decide |
| Conversacional | Estado de diálogo em (2) + Dizer (6) | |
| Aprendizado | Plano de aprendizado, fora do turno | Nunca altera a política no meio de uma conversa |
| Governança | Plano de governança, transversal | Regras são dados versionados, não prompt |

A justificativa da mudança: se "comercial" e "relacionamento" fossem decisores pares, um
puxaria para a venda e o outro para o cuidado, e o conflito se resolveria num árbitro implícito
(em geral, o prompt). Tornando-os **fornecedores de valor e de restrição para um decisor só**, o
conflito vira matemática explícita (4.5) e cada escolha tem uma probabilidade registrável.

### 5.3 Fluxo de um turno

```
evento (mensagem, toque, silêncio vencido, evento do backend)
  │
  0  PORTÃO sem modelo ......... cortesia pura, mídia, risco por regra local, janela do canal
  │
  1  ENTENDER  [generativo → probabilístico]
  │     entra: falas do turno (redigidas) + estado de diálogo resumido + lista fechada de atos
  │     sai:   atos tipados {ato, campos, trecho, confiança}, alternativas, sinais de atrito
  │     o código valida cada ato; a regra local de risco SOMA atos, o modelo nunca os tira
  │
  2  ATUALIZAR ESTADO  [probabilístico + determinístico]
  │     crença sobre objetivos; pergunta no ar, lista, foco; atrito; estado do relacionamento
  │
  3  LEVANTAR FATOS  [determinístico]
  │     consultas ao sistema de registro → ficha de fatos (id, valor, fonte, validade)
  │     conjunto viável: o que existe, o que a política permite, o que a identidade autoriza
  │
  4  DECIDIR  [guardas determinísticas + pontuação probabilística]
  │     gera candidatas por ato (responder, perguntar, verificar, ofertar, resolver, encaminhar...)
  │     filtra por A_seguro; pontua por Q; escolhe; REGISTRA a probabilidade da escolha
  │
  5  EXECUTAR  [determinístico + autorização]
  │     consultas → fatos; mudanças → recibos; compromissos → livro; equipe → cartão
  │     mudança vinculante exige confirmação do cliente presa a um orçamento
  │
  6  DIZER  [molde, ou generativo verificado]
  │     plano de partes → base por molde (sempre) → redação opcional com marcadores → verificador
  │
  7  GRAVAR numa transação: resposta + novo estado + registro de decisão;  8  ENVIAR
```

Propriedades de engenharia que não são opcionais [I]: idempotência por evento; turno revogável
quando chega fala nova no meio; estado gravado na mesma transação da resposta; teto de tempo por
etapa com queda para o caminho sem modelo; o sistema atende (pior, porém certo) sem nenhum
modelo disponível.

### 5.4 Portas

| Porta | Capacidades (descobertas, não presumidas) | Teste de conformidade |
|---|---|---|
| **Canal** | receber evento com identidade e instante; enviar; janela de resposta; tamanho; botões e listas; recibo de entrega; transferência a pessoa; garantia de identidade do remetente | entrega pelo menos uma vez sem duplicar efeito; janela respeitada; identidade nunca promovida sem prova |
| **Modelo** | `read` (texto → atos, com esquema), `write` (plano → texto), `score` (decisão entre opções), `embed`. Cada chamada com propósito, orçamento, classe de dado permitida e registro | resposta fora do esquema vira falha tratada; texto de cliente só para conexão aprovada |
| **Comércio** | `catalog.search/get`, `availability`, `pricing.quote` (orçamento com token e validade), `cart.mutate`, `order.place(token, confirmação)`, `order.status/cancel`, `customer.summary`, `policy.get`, `knowledge.search`, `compensation.grant` (limitado), `scarcity` (opcional) | toda mudança devolve recibo; orçamento vencido ou sacola alterada recusa o token; nenhuma escrita sem autoridade |
| **Equipe** | perguntar e receber resposta; transferir; devolver; promover resposta a conhecimento | resposta humana entra como fato com autoria e validade |
| **Relógio** | agendar e cancelar; expediente; "agora" | prazo vencido vira evento, não laço |

O framework entrega o núcleo **e** o conjunto de testes de conformidade de cada porta. Um
adaptador novo (outro canal, outro ERP) é aceito quando passa nos testes, sem tocar o núcleo.

### 5.5 Contratos de dados

Identificadores em inglês, esquemas ilustrativos (o formato de fio é irrelevante).

```jsonc
// Understanding: saída do entender
{ "acts": [ { "act": "ask_product", "slots": {"product": "pão com passas", "qty": 1},
              "span": "tem aquele pão com passas?", "confidence": 0.93 },
            { "act": "request_reserve", "slots": {"product": "ref:previous"}, "confidence": 0.81 } ],
  "alternatives": [],            // leituras concorrentes, quando houver
  "signals": { "friction": 0.08, "urgency": 0.2 },
  "reader": { "kind": "model|rules", "version": "..." , "calibrated": true } }

// Fact: unidade da ficha de fatos
{ "id": "F1", "kind": "price", "subject": "sku:RAISIN", "value": 1200,
  "source": "commerce.pricing", "as_of": "2026-11-17T10:02:11-03:00", "ttl_s": 300 }

// Decision: a cintura fina
{ "decision_id": "...", "conversation": "...", "turn": 812,
  "context": { "belief": {...}, "dialogue": {...}, "relationship": {...}, "facts": ["F1","F2"] },
  "candidates": [
    { "move": "inform", "content": {"facts": ["F1"]}, "eligible": true,  "score": 0.00 },
    { "move": "offer",  "content": {"sku": "RAISIN", "qty": 1}, "eligible": true, "score": 0.31,
      "predicted": {"p_accept": 0.42, "margin_q": 610, "shadow_q": 0, "delta_r_q": 40},
      "authority_required": "A2" },
    { "move": "offer",  "content": {"sku": "PAO-PASSAS"}, "eligible": false,
      "blocked_by": ["advisor_constraint"] } ],
  "chosen": 1, "propensity": 0.85, "explore": false,
  "policy": {"id": "moves", "version": "2026.11.3"}, "guards_fired": ["one_initiative_per_conversation:ok"] }

// Outcome: juntado depois, vindo SEMPRE do sistema de registro ou de pessoa, nunca do agente
{ "decision_id": "...", "kind": "order_placed", "value": {"margin_q": 610},
  "observed_at": "...", "source": "commerce.orders", "window": "24h" }

// Commitment
{ "id": "...", "kind": "promise|offer|quote", "text": "respondo em até 10 minutos",
  "due_at": "...", "backing": "team_card:991", "state": "open|kept|broken|expired" }
```

### 5.6 Os quatro regimes de decisão

| Decisão | Regime | Quem decide | Como se prova | Aprende? |
|---|---|---|---|---|
| Preço, estoque, horário, total, prazo | Determinístico | Sistema de registro | Por construção | Não |
| Viabilidade, elegibilidade, política, janela | Determinístico | Regras versionadas | Exemplos que são testes | Não; pessoas revisam |
| O que o cliente quis dizer | Probabilístico (modelo gerador usado como sensor) | Leitor + validação em código | Conjunto rotulado, calibração, repetição | Supervisionado, por correções e revisão |
| Atrito, propensão, valor do relacionamento | Probabilístico | Modelos estatísticos | Regras de pontuação próprias | Sim |
| Qual movimento | Decisão sob incerteza, dentro de guardas | Política | Avaliação contrafactual e experimento | Bandit com priors |
| Qual conteúdo (produto, substituto) | Ranking probabilístico sob restrição | Conselheiro de oferta | Offline e experimento | Sim |
| Como dizer | Molde, ou generativo verificado | Casa, ou modelo + verificador | Resposta com prova | Teste de variação de frase |
| Fechar pedido, pagar | **Autorização do cliente** | Cliente, por confirmação explícita presa ao orçamento | Token | Não |
| Compensar acima do teto, exceção de política, caso sensível | **Autorização humana** | Equipe | Trilha de auditoria | Tetos revistos por pessoas |
| Promover política ou modelo | **Autorização humana com portão estatístico** | Dono | Limite inferior de confiança positivo e guardas dentro do teto | Não |

Níveis de autoridade de ação, usados nas guardas: **A0** informar fato público · **A1** leitura
personalizada (pede identidade verificada) · **A2** mudança reversível (sacola) · **A3**
compromisso vinculante (pedido, pagamento; pede confirmação presa a orçamento) · **A4** exceção
(compensação, desconto; dentro de teto pré-autorizado ou com pessoa) · **A5** proibido.

## 6. Dados, memória e personalização

### 6.1 Cinco memórias, cinco donos

| Memória | Conteúdo | Regra |
|---|---|---|
| **De trabalho** | Estado de diálogo pequeno e tipado: pergunta no ar, última lista mostrada, item em foco, recibo da última mudança, o que está sendo verificado | Vence por evento (a pergunta foi respondida, a equipe assumiu), não só por relógio. O modelo recebe o estado; nunca o reconstrói |
| **Episódica** | Linha do tempo do relacionamento em eventos: pedidos, falhas, reclamações, compromissos e seus desfechos | Eventos, não transcrições. A transcrição tem retenção curta e propósito de auditoria |
| **Semântica do cliente** | Preferências como **crenças com origem e confiança** ("costuma pedir às sextas", origem: 6 pedidos) | Visível e corrigível pelo cliente; categoria sensível (saúde, alergia) nunca é lembrada em silêncio |
| **Institucional** | Regras da casa, perguntas frequentes promovidas de respostas da equipe, moldes de frase | Versionada, revisada por pessoa antes de valer |
| **Sistema de registro** | Catálogo, preço, estoque, pedidos, endereço | **Não é memória**: é consultado ao vivo, sempre |

A separação responde a um achado da Nice que generaliza: das mensagens que dependem de
contexto, a maior parte não se resolve mandando mais histórico ao modelo, e sim consultando o
que o sistema já sabe do cliente ou guardando um estado explícito [MEDIDO, V2 seção 1.1].
"Memória igual a transcrição" é o padrão por omissão dos agentes LLM e é o padrão errado.

### 6.2 Personalização em três degraus

1. **Contextual** (sem identidade): hora, canal, o que foi dito nesta conversa. Sempre
   disponível, sem custo de privacidade.
2. **Histórica** (identidade verificada): frequência pessoal, último pedido, endereço. É onde
   está quase todo o ganho em compra recorrente (2.4).
3. **Inferida** (modelos): propensão, valor, sensibilidade. Só com base legal clara e só depois
   que os dois primeiros degraus estiverem medidos.

Limites estruturais: preço nunca é personalizado pelo agente; atributos sensíveis não entram em
modelo; toda inferência usada numa decisão fica no registro (direito de revisão de decisão
automatizada, LGPD, art. 20).

### 6.3 Estado do relacionamento

Vetor pequeno por cliente, atualizado por eventos: recência e frequência (modelo de recompra),
valor esperado, **confiança operacional** e atrito recente. Definição proposta de confiança
operacional [H]: uma evidência acumulada do tipo Beta, em que compromisso cumprido, pedido sem
falha e problema resolvido na primeira conversa somam do lado positivo; compromisso quebrado,
erro de pedido e recontato pelo mesmo problema somam do negativo, com esquecimento exponencial.
Ela não é "a confiança do cliente" (que só ele sabe): é a parte dela que o sistema tem como
observar e pela qual responde.

### 6.4 Estratégia de dados

- **Evento como fonte**: registro de decisão, livro de compromissos e resultados são
  acrescentados, nunca editados. Tudo o mais é projeção.
- **Junção de resultado por chave do sistema de registro** (pedido, cliente), com janelas
  declaradas (24 horas, 7, 30 e 90 dias).
- **Minimização na borda**: o texto é redigido antes de ir a qualquer modelo externo; o executor
  trabalha no texto original, que não sai.
- **Retenção por classe**: transcrição curta; eventos e decisões em forma pseudonimizada por
  mais tempo; agregados sem prazo.

## 7. Partida com poucos dados

### 7.1 A conta que governa tudo

Para detectar um aumento de conversão de 20% para 25% (5 pontos) com poder de 80% e
significância de 5% bilateral:

```
n por braço = (1,96 + 0,84)² · [0,20·0,80 + 0,25·0,75] / 0,05²  ≈  1.090      (total ≈ 2.180)
```

Com cerca de 10 conversas por dia (84 conversas em 8 dias de observação [MEDIDO, V2 seção 1]),
são **uns 7 meses para um único teste**. Para 10 pontos (20% para 30%), cerca de 290 por braço,
uns 2 meses. Conclusões:

- Numa loja só, experimento clássico detecta apenas efeitos grandes. Decisões finas não são
  aprendíveis localmente; têm de vir de conhecimento, de priors ou de vários inquilinos (Q7).
- O critério certo em escala pequena não é significância, é **lucro esperado da decisão**:
  testar numa fração e aplicar o vencedor ao resto, com tamanho de teste que cresce com a raiz
  da população alcançável e é muito menor que o do teste de hipótese (Feit & Berman, 2019) [E].
- Bandits minimizam arrependimento sem exigir conclusão estatística: servem para escolher,
  não para provar.

### 7.2 A pilha de priors

Do mais confiável ao menos, cada um com peso declarado em pseudo-observações, para que se saiba
quando o dado passa a mandar:

| Camada | O que fornece | Peso típico |
|---|---|---|
| 1. **Regras e política do negócio** | O conjunto seguro e a política base `π₀` (o que uma boa atendente faria) | Duro: não é prior, é restrição |
| 2. **Histórico de transações de todos os canais** | Frequência pessoal, coocorrência, modelo de recompra. O canal de conversa é novo; a base de clientes não é | Forte: é dado real |
| 3. **Conhecimento especialista elicitado** | "De cada 4 que perguntam se tem, 1 reserva": `Beta(2, 6)` | Médio: 5 a 20 pseudo-observações |
| 4. **Estrutura hierárquica** | Cliente novo herda do segmento; produto novo, da categoria; loja nova, do conjunto de lojas (Hong et al., 2022; Rossi et al., 2005) | Aprendido |
| 5. **Modelo de linguagem como prior** | Leitura sem treino; preferências sintéticas para iniciar o bandit (Alamdari et al., 2024) | Fraco: 1 a 3 pseudo-observações; o modelo erra a distribuição real |

Exemplo do mecanismo: a taxa de aceite do movimento "oferecer para separar" começa em
`Beta(2, 6)` (média 25%, peso de 8 conversas). Depois de 40 ofertas com 16 aceites, a posterior
é `Beta(18, 30)` (média 37,5%), e o dado já pesa cinco vezes o prior.

### 7.3 Exploração segura

- Só se explora **dentro** de `A_seguro` e só entre candidatas que a política base aceitaria.
- Variante conservadora: o desempenho acumulado não pode cair abaixo de `(1 − α)` do da política
  base (Wu et al., 2016).
- Piso de exploração `ε` pequeno e registrado, para que os pesos de importância tenham teto e a
  avaliação contrafactual seja possível.
- Nunca se explora em: preço, afirmação de fato, segurança, compensação acima do teto.
- Thompson sampling com probabilidade de escolha estimada por amostragem e gravada.

### 7.4 O que se aprende desde o primeiro dia sem experimento

Sinais densos e gratuitos que o desenho por atos captura: a **correção** do cliente ("não, era
o outro") é rótulo de erro de leitura; a **pergunta repetida** é rótulo de resposta que não
serviu; a **resposta da equipe** a uma verificação é rótulo de fato faltante; o **motivo da
transferência** é rótulo de lacuna de cobertura. Cada um alimenta uma camada específica, com
revisão humana antes de virar conhecimento.

## 8. Avaliação, experimentação e melhoria contínua

### 8.1 Cinco níveis de prova

| Nível | Pergunta | Instrumento | Portão |
|---|---|---|---|
| **V0 Invariantes** | Alguma afirmação sem lastro, ação sem autoridade, regra violada? | Testes de propriedade, conjunto adversarial, exemplos das regras, repetição `k` vezes (acertar em todas) | **Zero**, sempre. Bloqueia publicação |
| **V1 Componentes** | O leitor acerta os atos? Está calibrado? Os modelos preveem bem? | Conjunto real rotulado; erro de calibração, Brier (Gneiting & Raftery, 2007); cobertura de conjuntos conformes | Não regredir |
| **V2 Política offline** | A política nova seria melhor nos dados da antiga? | Reexecução (C3); estimadores IPS, autonormalizado e duplamente robusto, com tamanho efetivo de amostra | Limite inferior de confiança do ganho acima de zero (Thomas et al., 2015) |
| **V3 Online** | Ela é melhor de fato? | Experimento com guardas (Kohavi et al., 2020); monitoramento sequencial válido a qualquer momento (Johari et al., 2017; Howard et al., 2021); redução de variância por covariável anterior (Deng et al., 2013) | Guardas dentro do teto; ganho no critério combinado |
| **V4 Longitudinal** | O sistema inteiro gera valor incremental? | **Grupo de controle permanente** (5% a 10% dos clientes recebem a política base, sem iniciativa comercial), comparado em 90 dias e mais | Revisão trimestral pelo dono |

Sobre simulação com usuário sintético [P]: útil para teste de fumaça e para o conjunto
adversarial; **não** é evidência de valor, porque o simulador é ele mesmo um modelo com os
mesmos vieses.

Sobre interferência [E]: com estoque finito, aleatorizar por cliente viola a hipótese de não
interferência (vender a última unidade ao tratado tira do controle). Decisões que consomem
recurso escasso se testam por **alternância no tempo** (Bojinov et al., 2023) ou se avaliam pelo
valor líquido do preço-sombra.

### 8.2 Estrutura de métricas

| Dimensão | Métrica principal | Contramétrica obrigatória (anda junto) |
|---|---|---|
| Receita incremental | Margem de contribuição por cliente contra o controle permanente | Taxa de arrependimento: cancelamento, devolução ou reclamação em pedidos influenciados |
| Qualidade da recomendação | Recompra do item recomendado sem arrependimento | Aceite sozinho não conta |
| Resolução | Resolvido sem recontato em 72 horas | Tempo e mensagens até resolver |
| Satisfação e confiança | Integridade de compromissos; recontato; avaliação pedida por sorteio | Pesquisa só a quem o agente escolhe é proibida |
| Relacionamento | Recompra em 30 e 90 dias; valor esperado pelo modelo de recompra | |
| Eficiência | Custo por conversa resolvida (modelo, canal, pessoa) | Taxa de transferência evitável **e** de transferência perdida |
| Segurança e conformidade | Violações de invariante (zero); casos de equipe perdidos (zero) | |
| Decisão | Calibração; arrependimento estimado; fração de turnos em exploração | |

O critério de promoção é: nenhuma guarda violada, **depois** ganho na métrica principal. Não
há índice único.

### 8.3 Contra a ilusão da métrica intermediária

- **Substituto precisa de prova de substituição**: o efeito do tratamento no substituto tem de
  prever o efeito no resultado final (Prentice, 1989; Athey et al., 2019). Reavaliar a cada
  trimestre contra o controle permanente.
- **Separação de poderes**: o componente que aprende não escreve o resultado pelo qual é
  recompensado. Resultados vêm do sistema de registro (pedido, reembolso) e de pessoas, nunca
  da classificação do próprio agente. É a defesa estrutural contra adulteração de recompensa
  (Everitt et al., 2021; Skalse et al., 2022) e contra as variantes da lei de Goodhart (Manheim
  & Garrabrant, 2018).
- **Auditoria humana por sorteio uniforme**, com rubrica fixa; e, se houver juiz automático,
  concordância com pessoas medida antes e de tempos em tempos.
- **Abster-se demais também é falha medida**: "não sei" e transferência sem necessidade têm
  métrica própria, porque um agente pode aprender a fugir.

### 8.4 Ciclo de melhoria

Observar → rotular por amostragem → diagnosticar por camada (leu errado? faltou fato? decidiu
mal? disse mal?) → propor mudança numa camada só → V0 e V1 → V2 → V3 em fração pequena →
promover com autorização → acompanhar deriva. Deriva monitorada em três pontos: distribuição dos
atos (o que os clientes pedem mudou), calibração do leitor (o modelo mudou) e taxa-base dos
resultados (o negócio mudou).

## 9. Governança, segurança, privacidade e supervisão

### 9.1 Regras da casa como constituição

Tabela declarativa, versionada, em que cada regra tem identificador, gatilho, efeito e
**exemplos que são testes** (frases que precisam disparar e frases que não podem). Atuam antes
(decidem destino e elegibilidade) e depois (reprovam a resposta). Regra de segurança não é
editável em painel: muda por revisão e teste. O que é editável é a frase.

### 9.2 Segurança por arquitetura

- **Texto não confiável não encontra autoridade.** O leitor recebe o texto do cliente, não tem
  ferramenta nenhuma e só pode devolver atos de uma lista fechada, validados em código. Quem
  executa não lê o texto. Quem redige (se houver) recebe plano e fatos, não o texto do cliente.
  É o princípio de separar controle de dado (Debenedetti et al., 2025).
- **Capacidades, não confiança**: cada mudança exige um nível de autoridade (5.6) derivado de
  identidade verificada, confirmação e política. "O dono autorizou", dito pelo cliente, não é
  capacidade.
- **Conteúdo do próprio negócio também é dado**: descrição de produto e resposta da equipe
  passam pelas regras de forma antes de sair.
- **Freio e medidor**: interruptor geral, teto de gasto por propósito, registro de toda chamada
  a modelo.

### 9.3 Privacidade

Minimização e redação na borda; propósito por chamada; classes de dado (público, pessoal,
sensível) com destinos permitidos; inventário público de quem recebe o quê; direitos do titular
atendidos por projeção sobre os eventos (acesso, correção, eliminação); explicação de decisão
automatizada a partir do registro de decisão. Marcos: LGPD (Lei 13.709/2018), CDC, AI Act
europeu (transparência de interação com IA, art. 50; vedação de técnicas manipulativas, art.
5º), NIST AI RMF como estrutura de gestão de risco. A situação do marco brasileiro de IA deve
ser conferida na data da implementação.

### 9.4 Supervisão humana

- **Antes**: o que exige pessoa está na tabela de autoridade.
- **Durante**: a equipe está sempre a uma frase de distância; o agente se identifica como
  assistente quando perguntado e nunca nega ser automação.
- **Depois**: auditoria amostral, revisão de toda violação de invariante, relatório de
  fronteira ao dono.
- **Sobre o aprendizado**: nenhuma política se promove sozinha; o portão estatístico informa, a
  pessoa autoriza.

### 9.5 Rastreabilidade

Cada resposta enviada permite reconstituir: o que foi entendido (e com que confiança), que fatos
foram consultados (com fonte e instante), que candidatas existiam, por que as outras caíram, com
que probabilidade a escolhida foi tomada, sob qual versão de regra e de política, e o que
aconteceu depois.

## 10. Roteiro evolutivo

Cada degrau tem critério de saída mensurável; não se sobe sem cumpri-lo.

| Degrau | Capacidade | Critério de saída |
|---|---|---|
| **D0 Atendente verdadeira e instrumentada** | Atos tipados, estado explícito, regras, resposta com prova por molde, "vou verificar", livro de compromissos, **registro de decisão desde já** (política fixa, probabilidade 1) | V0 em zero; integridade de compromissos medida; linha de base de todas as métricas de 8.2 |
| **D1 Incerteza de primeira classe** | Leitor calibrado; perguntar por valor da informação; limiares por custo do erro; crença sobre objetivos | Menos mudanças erradas **e** menos perguntas desnecessárias que o limiar fixo (H3) |
| **D2 Conselheira** | Movimentos comerciais sob a restrição de conselheiro, por regra e prior: substituto na indisponibilidade, complemento, "o de sempre", encomenda antecipada; recuperação de serviço com compensação em teto; preço-sombra; controle permanente começa | Ganho de margem contra o controle sem piora de arrependimento nem de recontato |
| **D3 Política que aprende** | Bandit sobre movimentos e conteúdo, exploração segura, avaliação contrafactual, portões | Primeira promoção de política aprovada por V2 e confirmada em V3 |
| **D4 Rede** | Priors hierárquicos entre inquilinos; iniciativa proativa por efeito incremental; substitutos de longo prazo validados | Arrependimento de partida de um inquilino novo menor que sem a rede (H5) |
| **D5 Pesquisa** | RL *offline* restrito para sequências; elicitação ativa de preferência; conversa entre o agente do cliente e o da loja pelos protocolos de comércio para agentes | Publicável, ou descartado com prova |

D0 e D1 valem para qualquer volume. D2 exige confiança do dono na restrição de conselheiro. D3
exige volume ou paciência (7.1). D4 exige mais de um inquilino.

## 11. Proposta de implementação experimental: Nice no Shopman

Esta seção é a única que depende do Shopman. Fatos do repositório marcados [MEDIDO].

### 11.1 O que a Nice já tem, visto pela arquitetura

| Peça da arquitetura | Na Nice hoje [MEDIDO] | Distância |
|---|---|---|
| Porta de Canal | `concierge/contracts.py`, `transport.py`: registro de conexões, `ChannelCapabilities`, `IdentityAssurance`, janela com prova | **Pronta**; é a porta mais madura |
| Porta de Modelo | `shopman/shop/ai.py`: conexão e rota por propósito, texto de cliente só para conexão aprovada; freio e medidor em andamento (WP-01) | Quase pronta |
| Porta de Comércio | Executores em `concierge/tools.py` sobre os services do Shopman; `quote_token` prende a confirmação ao orçamento (ADR-026) | Existe, sem contrato explícito nem teste de conformidade |
| Porta de Equipe | Transferência (`handoff.py`); "vou verificar" planejado (WP-05 a WP-07, WP-15) | Parcial |
| Entender | `concierge/intents.py`: atos no plural, validação em código, regra local que soma | Pronto; **falta confiança calibrada** por ato |
| Estado | `concierge/dialogue.py`, em `Conversation.flags["dialogue"]`, gravado com o `turn_fence` | Estado de diálogo pronto; **sem crença, sem estado do relacionamento** |
| Regras da casa | `concierge/house_rules.py`: 14 regras, 88 exemplos que são testes | Pronto |
| Dizer | Frase da casa por molde (decisão do dono: o modelo não reescreve salvo necessidade provada) | Pronto, prova por construção |
| Régua | `golden_set.json` (221 casos), `golden_memory.json` (47), `concierge_reply_eval`, `metrics.py` | V0 e V1 existem; **V2 a V4 não** |
| **Decidir** | Não existe como peça: o destino sai de regras encadeadas no executor | **A lacuna central** |
| **Registro de decisão** | Não existe; há `ConversationMessage.usage` (custo e tempo) | **A lacuna que impede aprender** |
| **Livro de compromissos** | Só o embrião (`verifying`, R6) | A generalizar |
| **Junção com resultado** | Não existe: nenhuma ligação conversa → pedido → recompra | A construir sobre o Orderman |

Leitura: a Nice chegou, por medição e por rodadas adversariais, a quase toda a **metade C** da
arquitetura (seção 3): verdade por construção, atos, estado, regras, régua. O que este estudo
acrescenta é a **metade que decide e aprende**, e o recorte que torna o conjunto independente do
Shopman. As decisões vigentes do dono são compatíveis com a arquitetura e viram parâmetros
dela: a língua é do modelo e o dinheiro é do código (ADR-026); a frase é da casa; "nunca afirmar
algo falso"; "vou verificar" como caminho nobre; texto redigido antes de sair.

### 11.2 Recorte do framework dentro do repositório

Proposta de forma, para decisão posterior (nada disto é pedido agora): o núcleo como pacote
puro, sem Django e sem dependência de outro pacote, na mesma disciplina dos pacotes de
`packages/`; os adaptadores (canal ManyChat, porta de IA, porta de comércio sobre Orderman,
Offerman, Stockman, Guestman e Craftsman) no orquestrador, como hoje. A regra do repositório
"Protocol só com duas implementações reais" (ADR-001) pede cuidado: a porta de canal e a de
modelo já têm mais de uma; a de comércio teria uma só, e a segunda implementação honesta é um
**backend falso de referência** usado pelos testes de conformidade, que é também o que prova a
independência de plataforma.

### 11.3 Experimentos, em ordem, respeitando o modo somente leitura atual

| # | Experimento | Cliente vê? | O que prova | Custo |
|---|---|---|---|---|
| **X1** | **Registro de decisão em sombra.** Em cada turno, gravar candidatas, escolhida (probabilidade 1), regras disparadas e fatos; juntar com pedidos do cliente em 24 horas e 7 dias | Não | Linhas de base reais: conversa → pedido, recontato, transferência; e se o contrato da cintura é suficiente | Sem modelo |
| **X2** | **Calibração do leitor** nos 221 + 47 casos: diagrama de confiabilidade, conjunto conforme, e a regra de 4.2 avaliada offline contra o limiar fixo | Não | H3 em versão offline; se a confiança do leitor serve para decidir | Chamada paga: pede a palavra do dono |
| **X3** | **Livro de compromissos** sobre o "vou verificar" (WP-05): toda promessa com prazo e desfecho | Indiretamente | Integridade de compromissos como métrica; base de H7 | Sem modelo |
| **X4** | **Primeiro movimento aprendível: oferecer para separar** quando o cliente pergunta disponibilidade com quantidade ("teria 2 pães rústicos pra hoje?"). Sorteio registrado entre "só responde" e "responde e oferece" | Sim | O mecanismo inteiro de D2 e D3 num caso de risco baixo. Com o volume atual só detecta efeito grande (7.1): serve para validar a máquina, não para concluir | Sem modelo |
| **X5** | **Substituto na indisponibilidade**: quando o item pedido está indisponível, sugerir um substituto ranqueado por aderência, disponibilidade e margem líquida do preço-sombra (a regra "para o cliente é só Indisponível" continua valendo) | Sim | H4; a ponte com Stockman e Craftsman | Sem modelo |
| **X6** | **Controle permanente** de 10% quando houver iniciativa comercial ligada | Não | V4 | |

X1 é o primeiro passo recomendado: não muda nada para o cliente, não gasta modelo, e é a
instrumentação da qual todo o resto depende.

### 11.4 O que a Nice não deve herdar deste estudo sem prova

Redação por modelo (o dono já decidiu; a arquitetura a mantém opcional); modelos de efeito
heterogêneo; qualquer RL; memória de preferência inferida. Nenhum deles se justifica com o
volume atual.

## 12. Inovação, hipóteses de pesquisa e vantagens defensáveis

### 12.1 O que é novo de fato (e o que não é)

Não são novos: bandits, valor da informação, comandos tipados, recuperação de serviço. O que,
até onde sei, não aparece junto em nenhum sistema descrito publicamente [H]:

1. **Registro contrafactual numa arquitetura de agente conversacional.** A indústria de agentes
   LLM avalia por tarefa cumprida e por juiz; a de recomendação avalia por contrafactual. Juntar
   as duas (espaço de movimentos fechado, probabilidade registrada) é o que torna o agente
   mensurável em resultado, não em aparência.
2. **Restrição de conselheiro como filtro de elegibilidade**, e não como peso.
3. **Preço-sombra da operação dentro da próxima melhor ação** de uma conversa.
4. **Resposta com prova e livro de compromissos**: a fala tratada como ato jurídico e
   operacional, com integridade mensurável.
5. **Taxonomia das cinco incertezas com caminhos de resolução distintos**, e a derivação do
   limiar de pergunta pelo custo do erro.
6. **O mesmo contrato para humanos e para agentes**: a porta de comércio que serve a conversa
   com o cliente serve, amanhã, a conversa com o agente do cliente.

### 12.2 Hipóteses testáveis

| # | Hipótese | Medida | Desenho |
|---|---|---|---|
| H1 | Políticas sob restrição de conselheiro têm recompra em 90 dias maior, sem margem menor, que políticas que maximizam aceite | Recompra, margem, arrependimento | Experimento entre inquilinos ou por alternância |
| H2 | Resposta com prova leva violações de fato a zero mensurável, com perda pequena de naturalidade | Violações em V0; avaliação humana cega | Molde contra redação verificada |
| H3 | Perguntar por valor da informação reduz mudanças erradas e perguntas desnecessárias frente a limiar fixo | As duas taxas | Offline no conjunto rotulado; depois online |
| H4 | Recomendação com preço-sombra reduz sobra de perecível e frustração por ruptura, sem piorar satisfação | Sobra, pedidos frustrados, recontato | Alternância no tempo |
| H5 | Priors hierárquicos entre inquilinos reduzem o arrependimento de partida | Arrependimento acumulado nas primeiras N decisões | Inquilino novo com e sem prior |
| H6 | Prior de LLM supera o não informativo e perde para o especialista | Idem | Simulação com dados reais retidos |
| H7 | Integridade de compromissos é substituto válido de retenção | Critério de Prentice | Longitudinal contra o controle |
| H8 | Verificação assíncrona mantém satisfação com custo humano menor que transferência | Recontato, tempo de pessoa | Alternância |
| H9 | Em comércio de relacionamento, identificar-se como assistente, com pessoa a uma frase, não reduz conversão de forma relevante | Conversão, transferência | Variação de abertura |
| H10 | O horizonte longo é bem aproximado pelo termo de relacionamento (decisão quase míope) | Valor em 90 dias: míope com termo contra RL offline | Só em D5 |

### 12.3 Vantagens defensáveis

- **O conjunto de dados causal próprio**: decisões com probabilidade registrada e resultado
  juntado não se compram nem se reconstituem depois. Cresce com o uso.
- **Efeito de rede no aprendizado** entre inquilinos, por priors, sem compartilhar dado bruto.
- **Integração vertical com a operação**: assistentes genéricos de canal não leem estoque vivo,
  capacidade nem custo; o preço-sombra é inacessível a eles.
- **Confiança por construção** como atributo de marca: poder dizer, com prova, que o assistente
  nunca afirma o que não está no sistema.
- **O kit de avaliação e conformidade** como produto: é o que permite a um terceiro confiar num
  adaptador novo.

## 13. Limitações e o que eu não sei

- **A restrição de conselheiro depende de um substituto do interesse do cliente** que pode
  estar errado. Se o substituto for fraco, ela vira enfeite. É o ponto conceitualmente mais
  frágil do documento.
- **Lista fechada de movimentos tem custo de cobertura**: o que não está na lista vira
  "desconhecido" e vai para pergunta ou equipe. Isso é proposital, mas pode frustrar em
  domínios muito abertos.
- **O termo de relacionamento é uma aproximação** do horizonte longo (H10 pode ser falsa).
- **Calibração de leitores LLM deriva** a cada troca de modelo; o custo de recalibrar é
  recorrente.
- **A avaliação contrafactual com pouco dado só enxerga políticas vizinhas**; saltos de política
  não são avaliáveis offline.
- **Não medi nada novo nesta sessão**: os números da Nice vêm dos documentos do repositório, não
  de consultas minhas ao banco. As especificações dos protocolos de comércio para agentes não
  foram lidas na fonte. A situação regulatória brasileira de IA precisa de conferência na data.
- **Não li as respostas dos outros agentes**, por desenho.

## Referências

✓ = conferida na fonte nesta sessão. As demais, citadas de memória.

**Decisão, POMDP e diálogo**
- Altman, E. (1999). *Constrained Markov Decision Processes*. Chapman & Hall.
- Berger, J. O. (1985). *Statistical Decision Theory and Bayesian Analysis*. Springer.
- Chow, C. K. (1970). On optimum recognition error and reject tradeoff. *IEEE Trans. Information Theory*, 16(1).
- Horvitz, E. (1999). Principles of mixed-initiative user interfaces. *CHI '99*.
- Howard, R. A. (1966). Information value theory. *IEEE Trans. Systems Science and Cybernetics*, 2(1).
- Kaelbling, L. P., Littman, M. L., Cassandra, A. R. (1998). Planning and acting in partially observable stochastic domains. *Artificial Intelligence*, 101.
- Keeney, R. L., Raiffa, H. (1976). *Decisions with Multiple Objectives*. Wiley.
- Mozannar, H., Sontag, D. (2020). Consistent estimators for learning to defer to an expert. *ICML*.
- Raiffa, H., Schlaifer, R. (1961). *Applied Statistical Decision Theory*. Harvard.
- Rao, S., Daumé III, H. (2018). Learning to ask good questions: ranking clarification questions using neural expected value of perfect information. *ACL*.
- Williams, J. D., Young, S. (2007). Partially observable Markov decision processes for spoken dialog systems. *Computer Speech & Language*, 21(2).
- Young, S., Gašić, M., Thomson, B., Williams, J. D. (2013). POMDP-based statistical spoken dialog systems: a review. *Proc. IEEE*, 101(5).
- Winograd, T., Flores, F. (1986). *Understanding Computers and Cognition*. Ablex.
- Singh, M. P. (2000). A social semantics for agent communication languages. In *Issues in Agent Communication*, LNCS 1916.

**Bandits, reforço e avaliação fora da política**
- Agarwal, A. et al. (2016). Making contextual decisions with low technical debt. arXiv:1606.03966.
- ✓ Alamdari, P. A., Cao, Y., Wilson, K. H. (2024). Jump starting bandits with LLM-generated prior knowledge. *EMNLP*. arXiv:2406.19317.
- Badanidiyuru, A., Kleinberg, R., Slivkins, A. (2013). Bandits with knapsacks. *FOCS*.
- Bottou, L. et al. (2013). Counterfactual reasoning and learning systems. *JMLR*, 14.
- Chapelle, O. (2014). Modeling delayed feedback in display advertising. *KDD*.
- Chapelle, O., Li, L. (2011). An empirical evaluation of Thompson sampling. *NIPS*.
- Dudík, M., Langford, J., Li, L. (2011). Doubly robust policy evaluation and learning. *ICML*.
- Dulac-Arnold, G. et al. (2021). Challenges of real-world reinforcement learning. *Machine Learning*, 110.
- Garivier, A., Moulines, E. (2011). On upper-confidence bound policies for switching bandit problems. *ALT*.
- Hong, J., Kveton, B., Zaheer, M., Ghavamzadeh, M. (2022). Hierarchical Bayesian bandits. *AISTATS*.
- Kazerouni, A. et al. (2017). Conservative contextual linear bandits. *NeurIPS*.
- Lattimore, T., Szepesvári, C. (2020). *Bandit Algorithms*. Cambridge.
- Levine, S., Kumar, A., Tucker, G., Fu, J. (2020). Offline reinforcement learning: tutorial, review, and perspectives. arXiv:2005.01643.
- Li, L., Chu, W., Langford, J., Schapire, R. (2010). A contextual-bandit approach to personalized news article recommendation. *WWW*.
- Li, L., Chu, W., Langford, J., Wang, X. (2011). Unbiased offline evaluation of contextual-bandit-based news article recommendation algorithms. *WSDM*.
- Russo, D. et al. (2018). A tutorial on Thompson sampling. *Foundations and Trends in ML*, 11(1).
- Swaminathan, A., Joachims, T. (2015). Batch learning from logged bandit feedback through counterfactual risk minimization. *JMLR*, 16.
- Thomas, P., Theocharous, G., Ghavamzadeh, M. (2015). High confidence policy improvement. *ICML*.
- Thomas, P. et al. (2019). Preventing undesirable behavior of intelligent machines. *Science*, 366.
- Wu, Y., Shariff, R., Lattimore, T., Szepesvári, C. (2016). Conservative bandits. *ICML*.

**Causalidade e experimentação**
- Ascarza, E. (2018). Retention futility: targeting high-risk customers might be ineffective. *Journal of Marketing Research*, 55(1).
- Athey, S., Chetty, R., Imbens, G., Kang, H. (2019). The surrogate index. NBER WP 26463.
- Bojinov, I., Simchi-Levi, D., Zhao, J. (2023). Design and analysis of switchback experiments. *Management Science*, 69(7).
- Deng, A., Xu, Y., Kohavi, R., Walker, T. (2013). Improving the sensitivity of online controlled experiments by utilizing pre-experiment data. *WSDM*.
- Feit, E. M., Berman, R. (2019). Test & Roll: profit-maximizing A/B tests. *Marketing Science*, 38(6).
- Gordon, B. R., Zettelmeyer, F., Bhargava, N., Chapsky, D. (2019). A comparison of approaches to advertising measurement. *Marketing Science*, 38(2).
- Gutierrez, P., Gérardy, J.-Y. (2017). Causal inference and uplift modelling: a review of the literature. *PMLR*, 67.
- Howard, S. R., Ramdas, A., McAuliffe, J., Sekhon, J. (2021). Time-uniform, nonparametric, nonasymptotic confidence sequences. *Annals of Statistics*, 49(2).
- Johari, R., Koomen, P., Pekelis, L., Walsh, D. (2017). Peeking at A/B tests. *KDD*.
- Kohavi, R., Tang, D., Xu, Y. (2020). *Trustworthy Online Controlled Experiments*. Cambridge.
- Künzel, S., Sekhon, J., Bickel, P., Yu, B. (2019). Metalearners for estimating heterogeneous treatment effects using machine learning. *PNAS*, 116(10).
- Lewis, R. A., Rao, J. M. (2015). The unfavorable economics of measuring the returns to advertising. *Quarterly Journal of Economics*, 130(4).
- Prentice, R. L. (1989). Surrogate endpoints in clinical trials. *Statistics in Medicine*, 8(4).
- Radcliffe, N. J., Surry, P. D. (2011). Real-world uplift modelling with significance-based uplift trees. Stochastic Solutions.
- Wager, S., Athey, S. (2018). Estimation and inference of heterogeneous treatment effects using random forests. *JASA*, 113.
- ✓ Yang, J., Eckles, D., Dhillon, P., Aral, S. (2024). Targeting for long-term outcomes. *Management Science*, 70(6). arXiv:2010.15835.

**Recomendação, preferência e operações**
- Bernardi, L., Mavridis, T., Estevez, P. (2019). 150 successful machine learning models: 6 lessons learned at Booking.com. *KDD*.
- Christakopoulou, K., Radlinski, F., Hofmann, K. (2016). Towards conversational recommender systems. *KDD*.
- Dacrema, M. F., Cremonesi, P., Jannach, D. (2019). Are we really making much progress? *RecSys*.
- Fader, P., Hardie, B., Lee, K. L. (2005). "Counting your customers" the easy way: an alternative to the Pareto/NBD model. *Marketing Science*, 24(2).
- Gallego, G., van Ryzin, G. (1994). Optimal dynamic pricing of inventories with stochastic demand over finite horizons. *Management Science*, 40(8).
- Gomez-Uribe, C., Hunt, N. (2015). The Netflix recommender system. *ACM TMIS*, 6(4).
- Hu, H. et al. (2020). Modeling personalized item frequency information for next-basket recommendation. *SIGIR*.
- Jannach, D., Manzoor, A., Cai, W., Chen, L. (2021). A survey on conversational recommender systems. *ACM Computing Surveys*, 54(5).
- Koren, Y., Bell, R., Volinsky, C. (2009). Matrix factorization techniques for recommender systems. *IEEE Computer*, 42(8).
- Li, M., Jullien, S., Ariannezhad, M., de Rijke, M. (2023). A next basket recommendation reality check. *ACM TOIS*, 41(4).
- Linden, G., Smith, B., York, J. (2003). Amazon.com recommendations: item-to-item collaborative filtering. *IEEE Internet Computing*, 7(1).
- Rossi, P., Allenby, G., McCulloch, R. (2005). *Bayesian Statistics and Marketing*. Wiley.
- Schmittlein, D., Morrison, D., Colombo, R. (1987). Counting your customers: who are they and what will they do next? *Management Science*, 33(1).
- Talluri, K., van Ryzin, G. (2004). *The Theory and Practice of Revenue Management*. Springer.

**Multiobjetivo**
- Hayes, C. F. et al. (2022). A practical guide to multi-objective reinforcement learning and planning. *JAAMAS*, 36.
- Miettinen, K. (1999). *Nonlinear Multiobjective Optimization*. Kluwer.
- Roijers, D., Vamplew, P., Whiteson, S., Dazeley, R. (2013). A survey of multi-objective sequential decision-making. *JAIR*, 48.

**Serviço, confiança e comportamento**
- Carroll, M. et al. (2022). Estimating and penalizing induced preference shifts in recommender systems. *ICML*.
- de Matos, C. A., Henrique, J. L., Rossi, C. A. V. (2007). Service recovery paradox: a meta-analysis. *Journal of Service Research*, 10(1).
- Dixon, M., Freeman, K., Toman, N. (2010). Stop trying to delight your customers. *Harvard Business Review*.
- Gelbrich, K., Roschk, H. (2011). A meta-analysis of organizational complaint handling and customer responses. *Journal of Service Research*, 14(1).
- Kleinberg, J., Mullainathan, S., Raghavan, M. (2024). The challenge of understanding what users want: inconsistent preferences and engagement optimization. *Management Science*, 70.
- Luo, X., Tong, S., Fang, Z., Qu, Z. (2019). Machines vs. humans: the impact of artificial intelligence chatbot disclosure on customer purchases. *Marketing Science*, 38(6).
- Mathur, A. et al. (2019). Dark patterns at scale. *CSCW*.
- Mayer, R., Davis, J., Schoorman, F. D. (1995). An integrative model of organizational trust. *Academy of Management Review*, 20(3).
- Milli, S., Belli, L., Hardt, M. (2021). From optimizing engagement to measuring value. *FAccT*.
- Morgan, R., Hunt, S. (1994). The commitment-trust theory of relationship marketing. *Journal of Marketing*, 58(3).
- Orsingher, C., Valentini, S., de Angelis, M. (2010). A meta-analysis of satisfaction with complaint handling in services. *JAMS*, 38.
- ✓ Salvi, F., Horta Ribeiro, M., Gallotti, R., West, R. (2025). On the conversational persuasiveness of GPT-4. *Nature Human Behaviour*, 9(8).
- Smith, A., Bolton, R., Wagner, J. (1999). A model of customer satisfaction with service encounters involving failure and recovery. *Journal of Marketing Research*, 36(3).
- Susser, D., Roessler, B., Nissenbaum, H. (2019). Online manipulation: hidden influences in a digital world. *Georgetown Law Technology Review*, 4.
- Tax, S., Brown, S., Chandrashekaran, M. (1998). Customer evaluations of service complaint experiences. *Journal of Marketing*, 62(2).

**Modelos de linguagem, agentes, incerteza e segurança**
- Angelopoulos, A., Bates, S. (2023). Conformal prediction: a gentle introduction. *Foundations and Trends in ML*, 16(4).
- Anthropic (2024). Building effective agents.
- ✓ Barres, V., Dong, H., Ray, S., Si, X., Narasimhan, K. (2025). τ²-Bench: evaluating conversational agents in a dual-control environment. arXiv:2506.07982.
- ✓ Bocklisch, T., Werkmeister, T., Varshneya, D., Nichol, A. (2024). Task-oriented dialogue with in-context learning. arXiv:2402.12234.
- ✓ Debenedetti, E. et al. (2025). Defeating prompt injections by design. arXiv:2503.18813.
- Everitt, T., Hutter, M., Kumar, R., Krakovna, V. (2021). Reward tampering problems and solutions in reinforcement learning. *Synthese*, 198.
- Gneiting, T., Raftery, A. (2007). Strictly proper scoring rules, prediction, and estimation. *JASA*, 102.
- Greshake, K. et al. (2023). Not what you've signed up for: compromising real-world LLM-integrated applications with indirect prompt injection. *AISec*.
- Guo, C., Pleiss, G., Sun, Y., Weinberger, K. (2017). On calibration of modern neural networks. *ICML*.
- Kapoor, S. et al. (2024). AI agents that matter. arXiv:2407.01502.
- Kuhn, L., Gal, Y., Farquhar, S. (2023). Semantic uncertainty. *ICLR*.
- ✓ Laban, P., Hayashi, H., Zhou, Y., Neville, J. (2025). LLMs get lost in multi-turn conversation. arXiv:2505.06120.
- ✓ Lin, J., Tomlin, N., Andreas, J., Eisner, J. (2024). Decision-oriented dialogue for human-AI collaboration. *TACL*. arXiv:2305.20076.
- Manheim, D., Garrabrant, S. (2018). Categorizing variants of Goodhart's law. arXiv:1803.04585.
- Meta Fundamental AI Research Diplomacy Team (2022). Human-level play in the game of Diplomacy by combining language models with strategic reasoning. *Science*, 378.
- Necula, G. (1997). Proof-carrying code. *POPL*.
- OWASP (2025). Top 10 for LLM Applications, LLM01: Prompt Injection.
- Shankar, S. et al. (2024). Who validates the validators? *UIST*.
- Skalse, J. et al. (2022). Defining and characterizing reward hacking. *NeurIPS*.
- Sumers, T., Yao, S., Narasimhan, K., Griffiths, T. (2024). Cognitive architectures for language agents. *TMLR*.
- Tian, K. et al. (2023). Just ask for calibration. *EMNLP*.
- Yao, S. et al. (2023). ReAct: synergizing reasoning and acting in language models. *ICLR*.
- Yao, S., Shinn, N., Razavi, P., Narasimhan, K. (2024). τ-bench: a benchmark for tool-agent-user interaction in real-world domains. arXiv:2406.12045.
- Zheng, L. et al. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. *NeurIPS*.

**Direito e normas**
- Brasil. Lei 8.078/1990 (CDC), art. 30. Lei 13.709/2018 (LGPD), art. 20.
- *Moffatt v. Air Canada*, 2024 BCCRT 149.
- União Europeia. Regulamento (UE) 2024/1689 (AI Act), arts. 5º e 50.
- NIST (2023). *AI Risk Management Framework 1.0*.

**Do repositório** (fonte dos fatos marcados [MEDIDO])
- `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`, `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`,
  `docs/decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md`,
  `docs/guides/concierge-supervised-improvement.md`, `shopman/storefront/concierge/`.
