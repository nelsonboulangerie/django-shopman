# Inteligência de Comércio Conversacional: arquitetura de referência (v2, definitiva)

> **Estado:** estudo, somente leitura. Nenhum código. **Não é plano vigente**: não altera o
> [CONCIERGE-PLANO-DE-ACAO](../plans/CONCIERGE-PLANO-DE-ACAO.md) nem os WPs em voo da Concierge.
> **Compromisso:** DEV-2026-045.
> **Para quem:** a sessão que vai formular o plano de implementação (a) do framework em si,
> possivelmente como pacote Python dedicado e independente, e (b) da camada adaptadora da Nice.
> A seção 15 é o guia de uso; o Apêndice A é a base da suíte de conformidade.
> **Objeto:** um framework genérico (qualquer mensageria, qualquer modelo, qualquer backend de
> negócio). A Nice, Concierge do Shopman, é só a primeira instanciação e aparece na seção 11.
>
> **Como nasceu.** A [v1](INTELIGENCIA-COMERCIO-CONVERSACIONAL-resposta-claude.md) foi a
> resposta independente do Claude ao prompt original e fica preservada, intacta. Esta v2 é a v1
> mais o que cinco documentos de outros agentes acrescentam, sem regressão: a arquitetura de
> referência v1.0 (16/11), o relatório de confronto com o Shopman (17/11), a especificação v0.1
> do núcleo, uma segunda resposta independente e uma revisão adversarial. A seção 14 diz o que
> entrou, o que não entrou e por quê, e onde a v1 estava errada. Esses documentos não estão no
> repositório; tudo o que este texto aproveita deles está escrito aqui, para que o leitor não
> dependa deles.
>
> **Precedência.** Onde este documento e a v1 divergirem, vale este. Onde este e os documentos
> externos divergirem, vale este, e a seção 14 registra a divergência.
>
> **Níveis de evidência**, marcados ao longo do texto:
> **[E]** conhecimento científico estabelecido · **[I]** técnica comprovada na indústria ·
> **[P]** abordagem emergente e promissora · **[H]** hipótese ainda não validada ·
> **[MEDIDO]** fato tirado dos documentos do repositório, com caminho ·
> **[CONFERIDO]** fato que conferi no código nesta sessão, no commit `43eeeede4` do `main`.
>
> **Sobre as referências:** a lista está no fim. Oito foram conferidas na fonte e estão marcadas
> com ✓; as demais são literatura canônica citada de memória e merecem conferência por amostragem
> antes de qualquer uso externo.

## 0. Em uma página

**O problema.** Um agente comercial conversacional toma decisões sequenciais sob incerteza sobre
o cliente, dentro de regras duras do negócio, com vários objetivos que conflitam, com pouco dado
e retorno atrasado. Duas coisas que quase toda arquitetura de agente ignora: **cada frase que ele
diz é um compromisso da empresa** (preço dito é oferta; "vou verificar" é promessa), e **cada
efeito acontece em outro sistema**, que pode falhar no meio (o pedido pode ter sido registrado
mesmo quando a resposta não chegou).

**A tese.** Uma inteligência comercial conversacional é **um sistema de decisão que fala**: só
afirma o que tem lastro, só promete o que tem dono e só executa o que foi autorizado. A
linguagem fica nas duas bordas (entender e dizer); o meio é um núcleo de decisão tipado,
pequeno, auditável e reexecutável. Só essa forma entrega ao mesmo tempo o que o prompt exige:
verdade por construção, decisão sob incerteza, aprendizado causal e independência de plataforma.

**As dez decisões arquiteturais** (cada uma derivada na seção indicada):

1. **Cintura fina.** Entre muitos canais, muitos modelos e muitos backends existe um único
   contrato estreito: o *registro de decisão* (contexto, candidatas, bloqueios, escolhida, modo
   de seleção, evidências). Tudo que aprende, audita ou avalia se pendura nele (5.1).
2. **Um lugar só decide, por ordem de prioridade.** "Inteligência comercial" e "inteligência de
   relacionamento" não são módulos que decidem lado a lado: fornecem valor e restrição a **um**
   ponto de decisão, que respeita uma ordem fixa (proteger e cumprir, resolver, esclarecer, só
   então vender) (4.1, 5.2).
3. **Quatro naturezas de decisão**, nunca misturadas: determinística (fato, dinheiro,
   permissão), probabilística (o que o cliente quer, o que vai acontecer), generativa (como
   dizer) e autorizada (o que só o cliente ou uma pessoa da equipe pode liberar) (5.6).
4. **Resposta com prova.** Toda afirmação de uma resposta aponta para um fato do sistema de
   registro, um recibo de ação, uma política ou um compromisso registrado. Sem lastro, não sai
   (4.6).
5. **Efeito com prova.** Toda mudança no negócio percorre uma cadeia única: termos apresentados,
   confirmação ligada a eles, concessão, comando, efeito, recibo. A autoridade é reconferida no
   instante do efeito, e resposta que não chegou é "desconhecido", nunca "falhou" (4.7).
6. **Compromisso com dono.** A unidade de trabalho é o episódio de necessidade, não a conversa.
   Toda promessa e todo problema viram um compromisso com dono, prazo e critério de cumprimento;
   conversa encerrada não cumpre nada (4.6, 5.7).
7. **Restrição de conselheiro.** A ação comercial só é elegível se, na crença do sistema, não
   piora a situação do cliente. Dentro desse conjunto, maximiza-se o valor do relacionamento
   (4.3).
8. **Escassez tem preço, e a equipe é portão.** Estoque perecível, capacidade e janela de
   entrega entram na decisão como preços-sombra; a atenção humana também, e sem fila humana com
   aceite e prazo não há autonomia de escrita (4.4, 5.8).
9. **Aprender em camadas, com a régua antes do motor e em dois trilhos.** Cada camada tem seu
   sinal e seu portão. Correção se mede sempre e é o que libera autonomia; economia se mede
   devagar e, com o volume de uma loja, é descritiva por muito tempo (seções 7 e 8).
10. **Inquilino é perfil mais adaptadores.** Tudo o que é de uma empresa (alçadas, fontes,
    prazos, fila, canais) mora num perfil de implantação versionado. O que falta no perfil
    desliga a ação que depende daquilo, não o sistema; e "desconhecido" é um valor, diferente de
    zero e de ausente (5.8).

**O que é honesto dizer sobre escala.** Com o volume de uma loja só (a Nelson recebe da ordem de
dez conversas por dia [MEDIDO]), um teste A/B clássico para detectar 5 pontos de conversão leva
cerca de sete meses. A arquitetura não pode depender de "aprender com dados" no curto prazo: ela
precisa ser boa por conhecimento e por construção no dia 1, e aprender só onde o volume permite
(seção 7). E registrar decisões de uma política fixa **não** permite, por si, avaliar outra
política: isso só começa quando há sorteio registrado (8.1). O que o registro dá desde o
primeiro dia é linha de base, reexecução e o contrato estabilizado.

## 1. Formulação do problema e tese

### 1.1 As nove propriedades que definem o problema

| # | Propriedade | Consequência para a arquitetura |
|---|---|---|
| P1 | **Observabilidade assimétrica.** O lado do negócio (preço, estoque, pedido) é observável, desde que consultado, e mesmo assim com atraso e validade. O lado do cliente (necessidade, intenção, humor, confiança) é latente | Incerteza sobre o cliente se modela; sobre o negócio se consulta, ao vivo, com fonte e validade. O modelo nunca "lembra" um preço |
| P2 | **Iniciativa mista.** O cliente também age, muda de assunto, corrige, some | Não é um fluxo; é um controle em malha fechada, turno a turno, com o silêncio como evento |
| P3 | **Fala que obriga.** Informar preço é ofertar; prometer é dever. No Brasil, a oferta suficientemente precisa vincula o fornecedor (CDC, art. 30); no Canadá, a empresa respondeu pela política que o robô inventou (*Moffatt v. Air Canada*, 2024 BCCRT 149) | Verdade não é métrica de qualidade: é invariante. Promessa é um objeto com dono, prazo e estado |
| P4 | **Vários objetivos em conflito**: margem agora, satisfação, confiança, custo de atendimento, segurança | Nenhum escalar único. Hierarquia: invariantes, prioridade, restrições, só depois otimização (4.5) |
| P5 | **Retorno esparso, atrasado e confundido.** A recompra vem em semanas; quem recebe oferta já era diferente de quem não recebe | Aprender exige aleatorização registrada, não correlação; e substitutos validados para o longo prazo |
| P6 | **Pouco dado**, e por muito tempo | Priors, conhecimento especialista e *pooling* hierárquico antes de qualquer aprendizado *online* |
| P7 | **Erros de custo assimétrico.** Mudar a sacola errado custa muito mais que responder uma consulta a mais; afirmar alérgeno errado é inaceitável | Limiares de ação diferentes por tipo de ação, derivados do custo do erro (4.2) |
| P8 | **Entrada adversarial.** O texto do cliente pode conter instruções; o agente tem poder sobre dinheiro | Texto não confiável nunca chega a um componente com autoridade de ação (9.2) |
| P9 | **O efeito mora em outro sistema.** Pedido, pagamento e estoque são gravados no sistema de registro, que pode aceitar o comando e a confirmação se perder; a posse da conversa pode mudar de mão no meio | Não há transação que abrace conversa e negócio. O contrato de efeito trata "desconhecido" como estado, exige idempotência e reconciliação, e reconfere a autoridade no instante do efeito (4.7) |

### 1.2 Formulação formal

O problema é um **processo de decisão de Markov parcialmente observável, restrito e
multiobjetivo** [E] (Kaelbling et al., 1998; Altman, 1999; Roijers et al., 2013):

```
⟨ S, A, O, T, Z, R, C, γ ⟩

S = W × K × H        estado
  W  mundo do negócio: catálogo, preço, estoque, capacidade, pedidos   (observável por consulta)
  K  cliente latente: tipo θ, objetivos g, atrito e, confiança τ        (não observável)
  H  história comum: o que foi dito, perguntas no ar, compromissos      (observável, registrada)

A(s)                 ações tipadas; o conjunto admissível depende do estado (estoque, permissão, janela)
O                    observações: mensagens, toques, silêncios, eventos do backend
T, Z                 dinâmica e modelo de observação
R : S×A → ℝ^d        recompensa VETORIAL (margem, resolução, adequação, relacionamento, custo, dano)
C                    restrições: duras (por ação) e de longo prazo (em expectativa)
```

O agente mantém uma crença `b(K)` e escolhe `a ∈ A_seguro(b, W, H)`.

**Quatro unidades de análise**, que não se confundem: o **turno** (onde se decide), o
**episódio de necessidade** (onde se mede se resolveu; pode atravessar conversas e canais, e uma
conversa pode conter mais de um), o **relacionamento** (onde se mede valor de longo prazo) e a
**operação compartilhada** (o estoque que um cliente consome muda o que o próximo pode receber).

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
> incerteza; um núcleo simbólico e probabilístico mantém estado e crença, consulta fatos, aplica
> invariantes e escolhe a próxima ação por prioridade e por valor esperado sob restrições,
> registrando como escolheu; a execução só acontece por comando autorizado, com recibo; a
> expressão converte o plano em linguagem que só afirma o que tem lastro. Modelos de linguagem
> atuam nas bordas; a autoridade fica no núcleo e no sistema de registro; o aprendizado acontece
> por camada, com avaliação contrafactual.

Corolários:

- **C1. Espaço de ações fechado e tipado.** Se o modelo escolhe a ação em texto livre, não
  existe probabilidade de escolha, e sem ela não existe avaliação contrafactual (Dudík et al.,
  2011; Bottou et al., 2013; Agarwal et al., 2016) [E]. Esta é a condição técnica para "uma
  inteligência que pode ser medida". Saída de modelo fora do catálogo nunca é executável.
- **C2. Três níveis de ação**: *movimento* (informar, perguntar, recomendar, cotar, pedir
  confirmação, executar comando, verificar com a equipe, abrir caso, compensar, encaminhar,
  aguardar, encerrar), *conteúdo* (qual produto, qual compensação) e *palavras*. O espaço de
  movimentos tem dezenas de elementos e se aprende com pouco dado; o conteúdo é um problema de
  ranking dentro do movimento; as palavras são molde ou geração verificada. É a mesma
  decomposição do Cicero, que venceu humanos em *Diplomacy* separando planejamento estratégico
  de intenções e geração condicionada a elas, com filtros (Meta FAIR, 2022) [E], e da linha
  "comandos" da Rasa (Bocklisch et al., 2024 ✓) [I].
- **C3. Núcleo funcional, casca durável.** A política é função pura de (snapshot do contexto,
  perfil, versão da política, semente). O determinismo exigido é este: **mesmo snapshot, mesmas
  versões e mesma semente produzem a mesma decisão.** A interpretação por modelo não é
  determinística e não precisa ser: o que ela produziu fica gravado no snapshot. Em volta do
  núcleo puro, uma casca persiste estado por comparação de versão, de modo que reiniciar retoma
  de onde parou. Qualquer turno do passado pode ser reexecutado com outra política: é teste de
  regressão e auditoria de uma vez.
- **C4. Portas, não integrações.** Canal, modelo, sistema de registro, equipe, armazenamento,
  relógio e resultados são portas com contrato, capacidades declaradas e teste de conformidade
  (5.4). "Não suportado" é resposta válida de um adaptador e bloqueia só o que depende daquilo.
- **C5. A abstenção é ação de primeira classe.** "Não sei, vou verificar", "pergunto antes",
  "passo para uma pessoa" e "não faço nada" têm valor esperado calculável, não são falhas (4.2).
- **C6. Desconhecido é um valor.** Fato, custo, probabilidade e resultado podem ser
  desconhecidos, e isso se escreve como tal. Zero, lista vazia e "falso" não são substitutos.
  Precondição desconhecida num requisito crítico bloqueia a ação; não a transforma em chute.

### 1.4 Questões que precisam de resposta antes de implementar

São as de negócio e de ciência. As de engenharia (onde mora o pacote, formato dos esquemas)
estão na seção 15.

| # | Questão | Por que bloqueia | Proposta deste documento |
|---|---|---|---|
| Q1 | Qual é a unidade de valor e a janela de atribuição? | Define a recompensa; sem isso toda métrica é intermediária | Episódio para correção e resolução; cliente em 30 e 90 dias para valor (5.7, 8.2) |
| Q2 | Qual é a lista fechada de movimentos da v1, e quem autoriza estendê-la? | Define `A`; ação fora da lista não existe | Catálogo versionado; extensão é versão nova, com precondição e teste (C2) |
| Q3 | Que substituto do interesse do cliente é aceitável para a restrição de conselheiro? | O interesse do cliente não é observável | Os quatro de 4.3, nessa ordem de força; a combinar com o dono |
| Q4 | Que autoridade se delega de antemão (teto de compensação por incidente e por cliente)? | Separa o autônomo do que pede pessoa | Linha do perfil, com dono e estado; sem valor aprovado, ação desligada (5.8) |
| Q5 | Que garantia de identidade cada canal dá, e que ações cada nível libera? | Sem identidade verificada não há mudança de pedido nem dado pessoal | Escada de identidade × autoridade da ação, no perfil (5.6) |
| Q6 | Qual base legal (LGPD) sustenta cada uso de dado para personalizar? | Parecer jurídico; desenho de memória depende dele | Só memória declarada até haver parecer (6.2) |
| Q7 | Que decisões são aprendíveis com o volume de um inquilino, e quais só com vários? | Evita prometer aprendizado impossível (7.1) | Só efeitos grandes localmente; o resto por prior ou por rede |
| Q8 | É aceitável aleatorizar ofertas entre clientes? (Preço nunca.) | Sem aleatorização não há medida causal | Sim, só entre ações admissíveis e adequadas; direitos nunca se sorteiam |
| Q9 | Como se mede confiança? | É a variável de estado de longo prazo | Definição operacional em 6.3; pergunta curta por sorteio como complemento |

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

### 4.1 Regra geral: admissível, prioritário, melhor

A escolha tem três passos, nesta ordem. Só o terceiro usa números.

```
1. ADMISSIBILIDADE   A_adm(s) = { a : toda precondição de a é verdadeira em s }
                     precondição "desconhecida" em requisito crítico bloqueia a ação, não o sistema

2. PRIORIDADE        ordem lexicográfica entre famílias de movimento:
                     proteger e cumprir obrigação  >  resolver a necessidade  >  esclarecer
                     >  comércio elegível  >  acompanhamento permitido

3. ESCOLHA           dentro da família vencedora: uma candidata, é ela;
                     várias, a de maior Q(b, a); empate por custo e por ordem estável do catálogo
```

A admissibilidade é função total, determinística e testável: direitos, segurança, veracidade e
autorização são precondições, nunca penalidades. A prioridade **não é um classificador de
intenção única**: uma mensagem com reclamação e dúvida gera duas necessidades, e o plano de
resposta atende as duas (a dúvida é respondida, o problema ganha dono). A ordem governa o que
acontece quando há conflito: iniciativa comercial não pedida fica suspensa enquanto houver
problema material aberto, e mudança de pedido fica suspensa quando uma parte vai para a equipe.

O terceiro passo usa, onde houver mais de uma candidata na mesma família:

```
Q(b, a) = E_b[ m(a) − Σ_k μ_k · q_k(a) + λ · ΔR(a) − κ(a) ]

  m(a)      margem de contribuição imediata esperada
  μ_k       preço-sombra do recurso escasso k (4.4);  q_k(a) o quanto a ação consome dele
  ΔR(a)     variação esperada do valor do relacionamento (recompra futura, via confiança e hábito)
  κ(a)      custo de servir: mensagens, tokens, tempo de pessoa
  λ         peso do futuro, escolhido pelo dono e exibido, nunca escondido
```

**Um termo de `Q` só existe quando tem estimador válido.** Nos primeiros degraus (seção 10) a
escolha dentro da família é por regra e a seleção é determinística; os termos entram um a um,
cada qual com seu modelo, sua calibração e seu portão. O vetor completo de objetivos serve para
**comparar políticas fora do turno** (4.5); dentro do turno só vale o `Q` da família vencedora.

`A_seguro`, citado em 1.2, é o conjunto admissível depois de três filtros: os **invariantes**
(viável no sistema de registro, permitido pela política, autorizado para o nível de identidade,
dentro da janela do canal), a **restrição de conselheiro** (4.3) e os **limites de contexto**
(no máximo uma iniciativa comercial não pedida por episódio; nenhuma com atrito alto, problema
aberto ou compromisso da casa vencido; recusa do cliente vale até ele mudar de ideia).

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

Três ressalvas que valem desde o primeiro dia, antes de existir qualquer estimativa:
(i) campo obrigatório do comando e dado de segurança **sempre** se perguntam, sem cálculo;
(ii) pergunta opcional passa pelo teste "a resposta muda a decisão?": reduzir incerteza não é
melhorar a decisão, e perguntar o que não altera o conjunto de ações é atrito puro;
(iii) sem modelo de resposta confiável, vale a regra por custo do erro acima, e registra-se o
que aconteceu depois de cada pergunta, para um dia estimar.

**Verificar com a equipe e encaminhar.** A incerteza tem cinco naturezas, e cada uma tem um
caminho de resolução diferente. Misturá-las é a origem de quase todo comportamento ruim:

| Incerteza sobre | Resolve-se | Nunca |
|---|---|---|
| Um fato do negócio (inclusive "o cadastro está atualizado?") | Consultando o sistema de registro; se ele não tem, ou o fato venceu, perguntando a uma pessoa da equipe, com prazo ("vou verificar") | Estimando. Para fato, o custo do erro é tratado como infinito |
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
iniciativa se compara. Iniciativa comercial precisa de evidência positiva; o silêncio não. Mas
"não responder" raramente é admissível: dúvida pede resposta, e pedido de não ser contatado
pede respeito. Aguardar sempre tem motivo, evento ou prazo de retomada, e responsável.

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
2022). No começo só (i) está disponível, e isso basta: recomendar por necessidade explícita e
atributo curado, admitir quando não há opção adequada, respeitar a recusa. Urgência e escassez
só se comunicam quando comprovadas por fato. Esta é a decisão mais importante a calibrar com o
dono (Q3) e é uma hipótese a testar (H1).

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

Três limites. Primeiro, a admissibilidade transacional vem antes: preço-sombra ordena o que é
viável, não torna viável o que o estoque não permite. Segundo, estimar `μ` exige estimar a
demanda alternativa; antes disso, valem sinais grosseiros ("sobrando", "escasso") dados pelo
backend. Terceiro, o efeito se avalia no conjunto da operação (o que um cliente levou outro
deixou de levar), não por conversa (8.1). Preço-sombra nunca justifica empurrar o que não serve.

A atenção humana tem, além do preço, um **portão**: sem fila humana com aceite e prazo, a
autonomia de escrita fica desligada no perfil (5.8). O preço modula; o portão protege.

### 4.5 Vários objetivos, sem reduzir tudo a dinheiro

Quatro camadas, em ordem lexicográfica:

1. **Invariantes** (nunca trocados por nada): verdade das afirmações, autorização, lei,
   segurança alimentar e física, privacidade. Garantidos por construção, não por penalidade.
   São conferidos por ação: uma média boa não protege cada pessoa.
2. **Prioridade** (4.1): proteger e cumprir, resolver, esclarecer, só então comércio.
3. **Restrições** (pisos e tetos): interesse do cliente (4.3); taxa de reclamação, de recontato
   e de arrependimento abaixo de teto; carga sobre a equipe abaixo da capacidade. As de longo
   prazo são tratadas como processo de decisão restrito (Altman, 1999), com multiplicadores
   atualizados por subida dual:
   `η_i ← max(0, η_i + ρ · (ĝ_i − c_i))`. Cada `η_i` é legível: quanto de margem se está
   pagando para manter aquela restrição.
4. **Otimização** (só aqui há troca): o `Q` de 4.1, com `λ` e demais taxas de troca elicitadas
   do dono (Keeney & Raiffa, 1976) e exibidas.

Por que restrições e não uma soma ponderada: a soma ponderada só alcança a parte convexa da
fronteira de Pareto e esconde a troca dentro de pesos que ninguém audita; o método de
restrições alcança qualquer ponto da fronteira e deixa cada piso visível (Miettinen, 1999;
Hayes et al., 2022) [E]. O relatório ao dono mostra a fronteira estimada (por exemplo, margem
contra recontato), não um número.

Na **comparação de políticas**, a forma é a mesma, escrita como não inferioridade: uma política
nova só substitui a atual se ganha na dimensão principal e não perde, além de margens aprovadas
por pessoas responsáveis, em resolução, adequação e custo. As margens são decisão de governança,
nunca estimativa de modelo. Sem medida válida de uma dimensão, não se afirma que ela foi
preservada.

### 4.6 Resposta com prova e compromissos

Toda resposta é um plano de partes; toda parte contém afirmações; toda afirmação tem um lastro:

| Tipo de afirmação | Lastro exigido | Exemplo |
|---|---|---|
| Fato do negócio | id de um fato da ficha, com fonte e validade | preço, disponibilidade, horário, prazo, total |
| Ação realizada | id de um recibo do executor | "separei", "cancelei", "avisei a equipe" |
| Política | id da regra ou da linha do perfil | "o prazo para cancelar pelo site é até a véspera" |
| Promessa | um compromisso registrado, com dono e prazo | "te respondo em até 10 minutos" |
| Cortesia | nenhum | saudação, agradecimento |

A analogia é com código que carrega a própria prova (Necula, 1997): quem envia não precisa
confiar em quem escreveu, só conferir o lastro. Há dois modos de produzir respostas assim, e a
arquitetura aceita os dois: **molde** (frase da casa preenchida pelo código, prova por
construção) e **redação com marcadores** (o modelo escreve com `{F1.preco}`, o código preenche e
um verificador confere). O molde é a base sempre gerada; a redação só substitui a base se passar
e se houver prova de que melhora algum resultado (8.2).

A **verificação de saída** é um contrato próprio e vale para toda mensagem, inclusive as de
molde: `verificar(conteúdo, fatos, recibos, regras) → passa | repara | segura`. *Repara* troca a
palavra proibida e segue; *segura* não envia e leva o caso a uma pessoa; tudo é registrado. O
verificador também erra e também é avaliado: o que não se pode errar não depende dele, porque
nunca foi delegado ao modelo.

O **compromisso** é o objeto que dá corpo a "promessa é dever". Tem dois tipos e uma forma só:

| | Promessa | Caso |
|---|---|---|
| Nasce de | uma frase da casa ("vou verificar", "te aviso quando ficar pronto") | um problema do cliente (reclamação, pedido errado, cobrança) |
| Tem | texto, obrigação, **dono** (automação, fila, pessoa), prazo e a regra que o definiu, critério de cumprimento, evidências, estado | o mesmo, mais o código do problema, a solução pedida e de onde foi reaberto |
| Estados | aberto, aceito, cumprido, quebrado, expirado, reaberto | os mesmos |

A união é deliberada: o "vou verificar" de uma boa atendente já é um pequeno caso (tem dono, tem
prazo, escala se ninguém responde). Reconhecer, aceitar e resolver são eventos distintos:
encaminhar não é aceitar, e aceitar não é resolver. Prazo ausente vem com motivo e contingência;
não se afirma prazo que ninguém definiu. "Encaminhei" sem destinatário é falsa resolução e é
barrado na origem: sem dono possível, a promessa não é feita.

A conversa comercial é uma rede de pedidos e promessas (Winograd & Flores, 1986; Singh, 2000), e
a métrica que decorre, **integridade de compromissos** (cumpridos no prazo sobre assumidos), é a
leitura operacional de "integridade" na confiança (H7).

### 4.7 Contrato de efeito

Toda mudança no negócio (sacola, pedido, cancelamento, desconto, compensação) percorre a mesma
cadeia. É a metade da arquitetura que a v1 tratava em uma linha e que decide se o sistema pode
ter autonomia de escrita.

```
termos apresentados      documento canônico do sistema de registro: itens, preços, destinatário,
                         cumprimento, condições, validade, versão, hash
  → confirmação          ato do cliente, POSTERIOR aos termos, ligado a eles e à identidade
  → concessão            quem autoriza, o quê, sobre quais termos, com que limites, até quando
  → comando              decisão, concessão, alvo, versões esperadas, época de posse esperada,
                         chave de idempotência
  → efeito               no ponto de linearização do sistema de registro
  → recibo               estado × efeito observado
```

Propriedades, válidas para qualquer adaptador:

1. **Confirmação tem referente.** Confirmação anterior aos termos, ambígua ou de outro sujeito
   não autoriza. Um "sim" só vale quando se sabe a que ele responde.
2. **Mudança material pede novos termos.** Item, quantidade, preço, moeda, destinatário,
   cumprimento ou condição alterados geram novos termos e nova confirmação. Ninguém recalcula
   o hash a partir de uma paráfrase: todos apontam para o mesmo documento.
3. **Quem concede não é o modelo.** A concessão é emitida pelo núcleo a partir de evidências e
   do perfil, e é conferida pelo executor. O hash identifica os termos; não autentica ninguém.
4. **Conferência no instante do efeito.** Identidade, termos, revisão, validade da concessão e
   posse da conversa são reconferidos **na mesma unidade atômica do efeito local**. Conferir,
   soltar o controle e só depois gravar não atende ao contrato. Antes do ponto de linearização,
   uma revogação vencedora impede o efeito; depois, o sistema reconcilia e não promete desfazer.
5. **Idempotência honesta.** Mesma chave e mesmo conteúdo devolvem o recibo que já existe; mesma
   chave e conteúdo diferente é conflito. Resposta que não chegou é **desconhecido**, não falha:
   reconcilia-se com a mesma chave, nunca se tenta de novo com chave nova. A chave fica guardada
   por toda a janela de recuperação, e chave expirada com efeito desconhecido bloqueia até
   reconciliar.
6. **Transferência revoga a posse, não o efeito.** Quando uma pessoa assume, comandos antigos da
   automação passam a ser recusados (a época de posse mudou). O que já estava em voo continua
   reconciliável, e um recibo atrasado é evidência do efeito, não autorização para agir de novo.
7. **Sem transação distribuída.** Um comando durável pode existir sem efeito, e um efeito pode
   existir antes de o recibo chegar. Estado, eventos e trabalho pendente do núcleo são gravados
   juntos, numa transação local; o efeito é gravado no sistema de registro; a ponte entre os
   dois é chave, consulta e reconciliação.

Só quatro combinações de recibo são válidas:

| Estado | Efeito | Significado | Próximo passo |
|---|---|---|---|
| sucesso | aplicado | efeito comprovado | responder com o recibo |
| falha | não aplicado | falha definitiva, sem efeito | informar; nova intenção pede nova decisão |
| pendente | desconhecido | aceito, ainda em execução | aguardar com prazo de reconciliação e responsável |
| desconhecido | desconhecido | não se sabe se aconteceu | reconciliar com a mesma chave; vencido o prazo, pessoa |

Efeito parcial, se um dia existir, não é sucesso: devolve a evidência de cada parte e segue para
reconciliação. Os fundamentos são os de sistemas distribuídos [E][I]: linearizabilidade (Herlihy
& Wing, 1990), idempotência como requisito de mensageria (Helland, 2012), ficha de cerca para
dono que mudou (Kleppmann, 2016) e caixa de saída transacional para gravar estado e trabalho
juntos.

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
   evento ───►│        │   NÚCLEO (política pura +    │◄─────┘
              ├───────►│        casca durável)        │
              │        │ 1 Entender   2 Estado/crença │
   resposta ◄─┤◄───────│ 3 Fatos      4 Decidir       │──────► REGISTRO DE DECISÃO  ◄── a cintura
              │        │ 5 Autorizar e executar       │        + compromissos, recibos, exposições
              │        │ 6 Dizer e verificar          │        + resultados juntados depois
              │        └──┬────────┬─────────┬────────┘                  │
        ┌─────▼──────┐ ┌──▼─────┐ ┌▼───────┐ ┌▼──────────────┐  ┌────────▼─────────┐
        │ Porta de   │ │Porta de│ │Porta de│ │ Porta de      │  │ PLANO DE         │
        │ Relógio    │ │Comércio│ │Equipe  │ │ Armazenamento │  │ APRENDIZADO      │
        └────────────┘ └────────┘ └────────┘ └───────────────┘  │ (fora do turno;  │
                                                                │ Porta Resultados)│
                                                                └──────────────────┘
        ───────── PLANO DE GOVERNANÇA: perfil de implantação, regras da casa, privacidade, freio ───
```

O registro de decisão é a cintura porque é o único artefato que todos os lados entendem: o
canal não sabe o que é margem, o backend não sabe o que é turno, o modelo não sabe o que é
política. Trocar qualquer ponta não invalida o histórico.

Implantação: **monólito modular**. As portas são interfaces lógicas (podem ser funções locais),
não exigência de rede, fila separada ou microsserviço. Um adaptador remoto precisa preservar as
mesmas garantias ou declarar a capacidade indisponível.

### 5.2 Reorganização das "sete inteligências" do enunciado

| Responsabilidade do enunciado | Onde mora aqui | Observação |
|---|---|---|
| Contexto | Entender (1) + Estado e crença (2) | |
| Decisão | Decidir (4) | **O único lugar que escolhe** |
| Comercial | Fatos (3) + o *conselheiro de oferta*, serviço chamado por (4) | Fornece candidatas e valores; não decide nem autoriza |
| Relacionamento | Estado do relacionamento em (2) + família de movimentos de cuidado em (4) + compromissos | Fornece restrições e valores; não decide; não fecha caso por silêncio |
| Conversacional | Estado de diálogo em (2) + Dizer e verificar (6) | Não altera oferta, não inventa confirmação, não acrescenta venda |
| Aprendizado | Plano de aprendizado, fora do turno | Nunca altera a política no meio de uma conversa; só gera versão candidata |
| Governança | Plano de governança, transversal | Regras e alçadas são dados versionados, não prompt |

A justificativa da mudança: se "comercial" e "relacionamento" fossem decisores pares, um
puxaria para a venda e o outro para o cuidado, e o conflito se resolveria num árbitro implícito
(em geral, o prompt). Tornando-os **fornecedores de valor e de restrição para um decisor só**, o
conflito vira regra explícita (4.1, 4.5) e cada escolha é registrável. A autorização ganha um
passo próprio (5) porque decidir e poder fazer são coisas diferentes.

### 5.3 Fluxo de um turno

```
evento (mensagem, toque, silêncio vencido, evento do backend, pessoa assumiu ou devolveu)
  │
  1  RECEBER      persiste e deduplica ANTES de qualquer trabalho; liga ao episódio;
  │               carrega versão do estado e época de posse. O que está no evento é dado.
  │
  2  PORTÃO sem modelo ...... cortesia pura, mídia, risco por regra local, janela do canal
  │
  3  ENTENDER  [generativo → probabilístico]
  │     entra: falas do turno (redigidas) + estado de diálogo resumido + lista fechada de atos
  │     sai:   atos tipados {ato, campos, trecho, confiança}, alternativas, sinais de atrito
  │     o código valida cada ato; a regra local de risco SOMA atos, o modelo nunca os tira
  │
  4  MONTAR O SNAPSHOT  [probabilístico + determinístico]
  │     necessidades abertas; pergunta no ar, lista, foco; atrito; estado do relacionamento;
  │     fatos consultados ao vivo (id, valor, fonte, validade) e o que ficou desconhecido.
  │     Nenhuma transação de banco fica aberta enquanto se chama modelo ou rede.
  │
  5  DECIDIR  [guardas determinísticas + pontuação probabilística]
  │     gera candidatas por necessidade; avalia precondições; aplica prioridade; escolhe;
  │     grava a decisão e a transição de estado por comparação de versão.
  │     Decisão tomada sobre versão que já mudou não é executada.
  │
  6  AUTORIZAR E EXECUTAR  [determinístico + autorização]
  │     consulta → fato;  mudança → concessão + comando gravados junto com o trabalho pendente;
  │     o executor deduplica e reconfere no ponto de efeito → recibo;
  │     promessa ou problema → compromisso;  equipe → cartão com dono e prazo
  │
  7  DIZER E VERIFICAR  [molde, ou generativo verificado]
  │     plano de partes → base por molde (sempre) → redação opcional com marcadores
  │     → verificação de saída (passa, repara, segura)
  │
  8  GRAVAR numa transação: resposta preparada + novo estado + intenção de envio
  9  ENVIAR e registrar a exposição (preparada, aceita, entregue, lida, desconhecida)
  10 RETOMAR esperas por evento ou por prazo; resultados são colhidos depois, por fonte independente
```

Propriedades de engenharia que não são opcionais [I]: idempotência por evento; turno revogável
quando chega fala nova no meio; estado gravado na mesma transação da resposta; teto de passos,
de tempo e de gasto por turno, com queda para o caminho sem modelo; o sistema atende (pior,
porém certo) sem nenhum modelo disponível; falha de estoque impede a promessa; falha de
pagamento leva a consultar o estado antes de qualquer repetição.

### 5.4 Portas

Toda chamada leva o contexto confiável do inquilino (inquilino, ambiente, identidade), que
nunca nasce de texto do cliente. Todo retorno tem versão e erro tipado. Todo adaptador responde
a `capabilities()`: ações suportadas, garantias de identidade, de revisão, de idempotência e sua
retenção, de revogação e de reconciliação, e o que **não** suporta.

| Porta | Operações mínimas | Garantias que o adaptador deve provar |
|---|---|---|
| **Canal** | normalizar entrada; enviar; consultar entrega; pedir transferência; capacidades (janela, tamanho, botões, recibos, identidade do evento) | Entrega pelo menos uma vez sem duplicar efeito; janela respeitada; identidade nunca promovida sem prova; aceite do transporte não é aceite de pessoa |
| **Modelo** | `interpretar` (texto → atos, com esquema), `redigir` (plano → texto), `pontuar` (escolha entre opções). Cada chamada com propósito, orçamento, classe de dado permitida e registro de consumo | Saída fora do esquema vira falha tratada; texto de cliente só para conexão aprovada; nenhum retorno é concessão nem recibo |
| **Comércio, leitura** | buscar e ler catálogo; disponibilidade como **decisão de promessa** (o que existe, o que é esperado, o que a política permite prometer); cotar (termos canônicos); ler pedido e cliente; política da casa; conhecimento; escassez (opcional) | Fato com fonte e validade; autorização por objeto; consulta não é reserva; "pode prometer" não é "há unidade separada" |
| **Comércio, execução** | executar comando; localizar por escopo e chave; reconciliar | O contrato de efeito inteiro (4.7): revisão, autoridade e posse no ponto de efeito; idempotência durável; estados incertos honestos |
| **Equipe** | perguntar e receber resposta; abrir ou atualizar compromisso; atribuir; registrar aceite; registrar cumprimento; devolver a conversa; promover resposta a conhecimento | Dono e prazo, ou motivo da ausência; aceite nominal separado do roteamento; resposta humana entra como fato com autoria e validade |
| **Armazenamento** | gravar entrada uma vez; carregar episódio; confirmar transição (versão esperada, registros, trabalho pendente); reivindicar trabalho; acrescentar recibo | Comparar e gravar; atomicidade de estado, eventos e trabalho local; isolamento por inquilino |
| **Relógio e agenda** | agora; novo identificador; agendar e cancelar; expediente | Prazo vencido vira evento reivindicável, não laço; relógio e identificadores substituíveis em teste |
| **Resultados** | colher métrica de um episódio ou cliente numa janela | Fonte independente do agente; maturação; correção por supersessão; desconhecido explícito |

A autoridade **não** é uma porta: a concessão é emitida pelo núcleo e conferida pelo executor
no ponto de efeito. Uma conferência remota separada do efeito daria uma atomicidade que não
existe. Se um adaptador não consegue sustentar a conferência junto do efeito, a ação fica
indisponível para autonomia naquele ambiente.

Erros estáveis compartilhados: esquema não suportado, conteúdo inválido, capacidade ausente,
identidade insuficiente, objeto proibido, fato indisponível, termos mudaram, conflito de
revisão, autoridade revogada, concessão vencida, confirmação exigida, conflito de idempotência,
efeito pendente, efeito desconhecido, orçamento esgotado, provedor indisponível. Erro não
classificado nunca vira sucesso; se uma submissão **pode** ter ocorrido, a categoria é
reconciliação, por mais recuperável que a exceção pareça.

O framework entrega o núcleo **e** o conjunto de testes de conformidade de cada porta (Apêndice
A), com adaptadores falsos que simulam duplicação, atraso, falha, resposta inválida e mudança de
capacidade. Um adaptador novo é aceito quando passa nos testes, sem tocar o núcleo.

### 5.5 Contratos de dados

Identificadores em inglês. O formato de fio é irrelevante; a semântica não.

**Convenções comuns.** Todo registro carrega versão de esquema, tipo e identificador estável,
inquilino e ambiente (`test`, `shadow`, `live`), identificador de rastro e de causa, instante em
que ocorreu e instante em que foi gravado (este produzido na fronteira de persistência),
produtor e versão, e episódio (ou nulo, quando ainda não ligado). Dinheiro é inteiro na menor
unidade, com moeda. Quantidade é decimal em texto, com unidade. **Fato** é
`known(valor, fonte, observado_em, válido_até, versão_da_fonte)` ou `unknown(motivo)`.
**Estimativa** é valor com método, população e versão, ou `unavailable(motivo)`. Registros são
imutáveis: corrigir é gravar outro, que substitui o anterior e o mantém no histórico. Conteúdo
pessoal vai por referência protegida; log técnico não carrega texto integral nem segredo.
Contratos de execução e de autorização recusam campo desconhecido e versão não suportada.

| Contrato | Essencial | Invariante |
|---|---|---|
| `InteractionEvent` | vínculo do canal, ator, identidade do evento e sua garantia, tipo (mensagem, toque, correção, pessoa assumiu, atualização de entrega, prazo vencido), referência ao conteúdo, evidências de identidade | Duplicata não cria comando; texto igual não prova duplicata; evento fora de ordem não autoriza |
| `Understanding` | atos (ato, campos, trecho, confiança calibrada ou `unavailable`), alternativas, sinais, leitor e versão | Ato fora da lista vira `unknown`; a regra local soma atos e o modelo não os tira |
| `ContextSnapshot` | episódio e versão, época de posse, identidade e garantia, necessidades, fatos, hipóteses, desconhecidos, estado de diálogo, estado do relacionamento, compromissos abertos, perfil e política | Imutável; hipótese não vira fato; não garante que o mundo esteja igual no instante do efeito |
| `CandidateAction` | movimento, conteúdo, versão, precondições avaliadas (passa, falha, desconhecida, com código e evidência), efeitos esperados, reversibilidade, autoridade e confirmação exigidas, validade; previsão só com estimador declarado | Fora do catálogo não é executável |
| `DecisionRecord` | snapshot e seu hash, candidatas com bloqueios e motivos, plano escolhido, **seleção**, política e perfil, chamadas de modelo, decisão anterior (se houver) | Registra alternativas e escolha efetiva, não justificativa posterior; bloqueio depois gera nova decisão ligada, nunca reescrita |
| `TermsDocument` | itens, quantidades, preços, destinatário, cumprimento, condições, validade, versão, hash canônico | Produzido pelo sistema de registro; referenciado, nunca reconstruído |
| `AuthorizationGrant` | sujeito, emissor, base, finalidade, ação, alvos, termos e hash, limites, evidências de identidade e de confirmação, validade, revogação | Não vale para termos, destinatário ou escopo alterados |
| `ActionCommand` | decisão, concessão, ação, alvos, parâmetros, termos, versões esperadas, época de posse esperada, escopo e chave de idempotência, hash do conteúdo, prazo | Retentativa não muda parâmetros, alvo nem termos |
| `ActionReceipt` | comando, estado × efeito (4.7), referências do domínio, versões observadas, erro com instrução de retentativa, reconciliação, supersessão | Sucesso exige efeito comprovado; resposta que não chegou é desconhecido |
| `ReplyPlan` | partes; por parte: movimento e afirmações com lastro; blocos travados; resultado da verificação | Afirmação sem lastro não sai |
| `ExposureEvent` | decisão, conteúdo e hash, realizador e versão, destinatário, tentativa, estado (preparada, submetida, aceita, não aplicada, desconhecida, entregue, lida) | Aceita não é lida; não poder medir leitura não é "não leu"; envio desconhecido não se reenvia às cegas |
| `OutcomeEvent` | episódio, cliente, métrica e versão da definição, valor, janela, estado da observação (observado, desconhecido, censurado, não se aplica), fonte, decisões e comandos associados, atribuição experimental, supersessão | Fonte independente do agente; associação não é causalidade; desconhecido não vira zero |
| `Episode` e `Need` | ver 5.7 | Conversa encerrada não resolve episódio |
| `Commitment` | tipo (promessa, caso), obrigação, dono, prazo e regra do prazo, critério de cumprimento, evidências, estado (4.6) | Reconhecer, aceitar e cumprir são eventos distintos |
| `MemoryItem` | tipo, valor, estado de evidência (declarado, inferido, verificado), fonte, finalidade, sensibilidade, validade, supersessão | Correção alcança resumos e derivados; texto de memória nunca é instrução |
| `DeploymentProfile` | ver 5.8 | Requisito crítico ausente desliga a ação, não o sistema |

O registro de decisão, com a seleção explícita:

```jsonc
{ "decision_id": "...", "episode": "...", "turn": 812,
  "context": { "snapshot": "...", "snapshot_hash": "..." },
  "candidates": [
    { "need": "n1", "move": "inform", "content": {"facts": ["F1"]}, "eligible": true },
    { "need": "n1", "move": "recommend", "content": {"sku": "RAISIN", "qty": 1}, "eligible": true,
      "authority_required": "A0",
      "predicted": {"p_accept": {"status": "unavailable", "reason": "no_estimator"}} },
    { "need": "n1", "move": "recommend", "content": {"sku": "PAO-PASSAS"}, "eligible": false,
      "blocked_by": ["advisor_constraint"] } ],
  "chosen": [0, 1],
  "selection": { "method": "deterministic", "tie_break": "catalog_order",
                 "propensity": {"status": "not_applicable"}, "experiment": null },
  "policy": {"id": "moves", "version": "2026.11.3"}, "profile": {"id": "...", "version": "..."},
  "parent_decision": null }
```

Quando a seleção for aleatorizada, `selection` passa a trazer a **distribuição depois dos
filtros**, a semente do sorteio e a probabilidade da ação efetivamente executada. Se uma guarda
posterior bloquear a ação sorteada, registram-se a proposta, o bloqueio e o que foi feito no
lugar; a probabilidade original não é atribuída à ação substituta. Seleção determinística **não
dá suporte contrafactual** às ações não escolhidas, e o registro diz isso
(`not_applicable`) em vez de gravar "probabilidade 1".

### 5.6 As quatro naturezas de decisão

| Decisão | Natureza | Quem decide | Como se prova | Aprende? |
|---|---|---|---|---|
| Preço, estoque, horário, total, prazo | Determinística | Sistema de registro | Por construção | Não |
| Admissibilidade, elegibilidade, política, janela | Determinística | Regras versionadas e perfil | Exemplos que são testes | Não; pessoas revisam |
| O que o cliente quis dizer | Probabilística (modelo gerador usado como sensor) | Leitor + validação em código | Conjunto rotulado, calibração, repetição | Supervisionado, por correções e revisão |
| Atrito, propensão, valor do relacionamento | Probabilística | Modelos estatísticos | Regras de pontuação próprias | Sim |
| Qual movimento | Decisão sob incerteza, dentro de guardas | Política | Avaliação contrafactual e experimento | Regra primeiro; depois sorteio e bandit com priors |
| Qual conteúdo (produto, substituto) | Ranking probabilístico sob restrição | Conselheiro de oferta | Offline e experimento | Sim |
| Como dizer | Molde, ou generativa verificada | Casa, ou modelo + verificador | Resposta com prova | Teste de variação de frase |
| Fechar pedido, pagar, trocar | **Autorização do cliente** | Cliente, por confirmação explícita presa aos termos | Concessão e recibo | Não |
| Compensar acima do teto, exceção de política, caso sensível | **Autorização humana** | Equipe | Trilha de auditoria | Tetos revistos por pessoas |
| Promover política ou modelo | **Autorização humana com portão estatístico** | Dono | Limite inferior de confiança positivo e guardas dentro do teto | Não |

As naturezas se compõem: decidir **propor** uma compensação pode ser probabilístico; o valor
permitido é determinístico; executá-la pede autorização. Nenhuma saída generativa substitui
esse caminho.

**Autoridade da ação × garantia de identidade.** Cada ação do catálogo declara o nível de
autoridade que exige; o perfil diz, por canal, que garantia de identidade libera cada nível.

| Nível da ação | Exemplos | Identidade mínima típica |
|---|---|---|
| **A0** informar fato público | cardápio, horário, preço de vitrine | anônimo |
| **A1** leitura personalizada | status do pedido, endereço salvo | verificada (posse do contato confirmada) |
| **A2** mudança reversível | sacola | verificada, com identidade estável do evento |
| **A3** compromisso vinculante | registrar pedido, pagar, cancelar | verificada + confirmação presa aos termos |
| **A4** exceção | desconto, compensação | A3 + teto do perfil, ou pessoa |
| **A5** proibido à automação | o que o perfil vedar | não se aplica |

A escada de identidade tem quatro degraus: **anônimo**, **transportado** (o canal alega quem é;
número de telefone não é identidade autenticada), **verificado fraco** (evidência de posse) e
**verificado forte** (autenticação ativa). Sem garantia suficiente, sobram consulta pública e
encaminhamento; nunca escrita, nunca dado de outra pessoa.

### 5.7 Episódio, necessidade e posse

**Episódio** é a unidade de trabalho e de medida: uma necessidade do cliente, do surgimento à
resolução. **Necessidade** é um item da agenda dentro dele. **Compromisso** (4.6) é o que a casa
ficou devendo. Três ciclos de vida distintos: encerrar a conversa não resolve o episódio, e
resolver o episódio não cumpre um compromisso que ficou aberto.

Necessidade: `{id, tipo, estado (aberta, bloqueada, satisfeita, retirada), depende_de,
evidências}`. *Satisfeita* exige evidência (fato entregue, recibo, cumprimento); *retirada*
exige ato do cliente ou regra do perfil, nunca silêncio; uma necessidade bloqueada segura as que
dependem dela. Uma reclamação não apaga a dúvida que veio na mesma mensagem.

Regras de correlação (padrões; o perfil ajusta): uma entrada se liga ao episódio aberto do
mesmo cliente verificado, ou do mesmo vínculo de canal quando não há identidade; continua o
episódio enquanto houver necessidade ou compromisso aberto; abre outro quando chega uma
necessidade independente depois de tudo resolvido, ou vencida a janela de inatividade do perfil;
reclamação sobre algo anterior reabre o caso correspondente mesmo em episódio novo; **nunca** se
unem pessoas por semelhança de texto. O estado de diálogo (pergunta no ar, lista, foco) é outra
coisa e vence por acontecimento, não por relógio (6.1).

Máquina de estados do episódio. Toda transição compara a versão, incrementa e grava evento.
Toda espera tem condição de retomada, responsável e prazo.

| Estado | Evento | Próximo estado |
|---|---|---|
| `active` | falta campo obrigatório; pergunta enviada | `waiting_input` |
| `waiting_input` | chega evidência nova | `active` |
| `active` | termos apresentados; confirmação exigida | `waiting_authorization` |
| `waiting_authorization` | concessão válida e termos vigentes | `active`, para reconferir e executar |
| `waiting_authorization` | correção, expiração ou termos alterados | `active`, invalidando a autorização pendente |
| `active` | comando durável entregue ao executor | `waiting_effect` |
| `waiting_effect` | recibo terminal | `active`, para responder e atualizar necessidades |
| `waiting_effect` | pendente ou desconhecido | permanece; agenda reconciliação; vencido o prazo, vai a pessoa |
| qualquer não resolvido | regra manda, cliente pede ou pessoa assume | `awaiting_handoff`; a posse da automação é revogada |
| `awaiting_handoff` | fila ou pessoa aceita | `human_owned` |
| `awaiting_handoff` | ninguém aceita | permanece monitorado; aplica a contingência do perfil; nada afirma aceite |
| `human_owned` | devolução explícita, nova posse e contexto reconciliado | `active` |
| `active`, `human_owned` | necessidades satisfeitas ou retiradas e compromissos cumpridos, com evidência | `resolved` |
| `resolved` | a mesma necessidade volta | `active`, com evento de reabertura |

**Posse.** O episódio tem um dono (`automação`, `fila`, `pessoa`) e uma **época de posse**, que
só cresce. Todo comando carrega a época esperada e é recusado se ela mudou. Quando a pessoa
devolve a conversa, a pergunta que a automação tinha deixado no ar deixa de valer (a pessoa
disse coisas que o sistema não viu), e nenhuma ação antiga é retomada em silêncio.

### 5.8 Perfil de implantação, ambientes e portões

O **perfil de implantação** é a configuração versionada de um inquilino. É ele, mais os
adaptadores, que faz de um núcleo genérico a atendente de uma casa:

- inquilino e ambiente; adaptadores e capacidades habilitadas;
- catálogo de movimentos e versão da política; regras da casa (9.1);
- por ação: autoridade exigida, identidade mínima por canal, confirmação exigida, **tetos**
  (cada linha com dono, data e estado: proposto, em validação, aprovado);
- fontes autorizadas de cada fato e sua regra de validade;
- fila humana, papel responsável, prazos e contingência fora do expediente;
- limites de passos, tempo, consultas, modelo e gasto;
- finalidade, retenção e campos permitidos por destinatário (inclusive por modelo);
- definição das métricas, janelas e do desenho do piloto.

Regra única: **campo sem decisão fica ausente, com motivo, e a ação que depende dele fica
inelegível, com código.** Informar a limitação e encaminhar continuam possíveis. O núcleo não
escolhe uma alçada para preencher o perfil, e linha "proposta" não vale como aprovada.

**Ambientes.** `test`: adaptadores falsos; recibo marcado `test` nunca vale como prova de
operação real. `shadow`: o caminho completo até a decisão e o plano de resposta, sobre entradas
reais, **sem** comando às portas de escrita e **sem** envio; serve para comparar proposta,
bloqueios, latência e custo com o atendimento que de fato ocorreu, não para medir conversão.
`live`: efeitos reais, conforme o perfil.

**Portões de autonomia.** A escrita autônoma num canal exige, cumulativamente: identidade
estável do evento e garantia de identidade suficiente; executor que prove o contrato de efeito
(4.7); fila humana com aceite nominal e prazo; e perfil com as linhas daquela ação aprovadas.
Há um **freio por classe de ação**: desligar a escrita mantendo informação e encaminhamento, em
minutos, por perfil. Desligar nunca apaga evidência.

**Evolução de versão.** Subir a versão de um contrato não pode abandonar trabalho em andamento:
episódios abertos, comandos pendentes e esperas agendadas são concluídos ou migrados antes do
corte, e a migração nunca converte "desconhecido" em "falhou".

## 6. Dados, memória e personalização

### 6.1 Cinco memórias, cinco donos

| Memória | Conteúdo | Regra |
|---|---|---|
| **De trabalho** | Estado de diálogo pequeno e tipado: pergunta no ar, última lista mostrada, item em foco, recibo da última mudança, o que está sendo verificado | Vence por evento (a pergunta foi respondida, a equipe assumiu), não só por relógio. O modelo recebe o estado; nunca o reconstrói |
| **Episódica** | Linha do tempo do relacionamento em eventos: pedidos, falhas, reclamações, compromissos e seus desfechos | Eventos, não transcrições. A transcrição tem retenção curta e propósito de auditoria |
| **Semântica do cliente** | Preferências como **crenças com origem e confiança** ("costuma pedir às sextas", origem: 6 pedidos), cada uma marcada como declarada, inferida ou verificada | Visível e corrigível pelo cliente; categoria sensível (saúde, alergia) nunca é lembrada em silêncio; compra para presente não contamina o perfil, e "hoje sem açúcar" não vira dieta permanente |
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

Na primeira versão só existem a memória de trabalho e a declarada (o cliente afirmou, com fonte
e validade); nada inferido. Limites estruturais: preço nunca é personalizado pelo agente; atributos sensíveis não entram em
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

- **Evento como fonte**: registro de decisão, compromissos, recibos, exposições e resultados são
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
- Primeiro, sorteio explícito entre poucas ações, com probabilidades conhecidas e gravadas
  depois dos filtros. Thompson sampling só mais tarde: a probabilidade de escolha dele é difícil
  de registrar com exatidão.
- A redação faz parte da intervenção: durante um experimento sobre o movimento, modelo, molde e
  limites ficam fixos, ou a combinação é versionada.

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
| **V0 Invariantes** | Alguma afirmação sem lastro, ação sem autoridade, regra violada? | Testes de propriedade, conjunto adversarial, exemplos das regras, repetição `k` vezes (acertar em todas) | **Zero**, sempre. Bloqueia publicação. Zero observado não é risco zero: com `n` ensaios limpos e independentes, o teto de 95% da taxa de falha é cerca de `3/n` (Hanley & Lippman-Hand, 1983) |
| **V1 Componentes** | O leitor acerta os atos? Está calibrado? Os modelos preveem bem? | Conjunto real rotulado; **régua de episódios** (trajetória e estado final, com a asserção vinda do banco ou do adaptador falso, nunca de um juiz); erro de calibração, Brier (Gneiting & Raftery, 2007); cobertura de conjuntos conformes | Não regredir |
| **V2 Política offline** | A política nova seria melhor nos dados da antiga? | Sombra (5.8) e reexecução (C3), para comparar proposta, bloqueios, latência e custo; e, só quando houver sorteio registrado, estimadores IPS, autonormalizado e duplamente robusto, com tamanho efetivo de amostra | Limite inferior de confiança do ganho acima de zero (Thomas et al., 2015) |
| **V3 Online** | Ela é melhor de fato? | A/A antes de qualquer A/B; canário com supervisão; experimento com guardas (Kohavi et al., 2020), sorteio persistente por cliente e análise por intenção de tratar; monitoramento sequencial válido a qualquer momento (Johari et al., 2017; Howard et al., 2021); redução de variância por covariável anterior (Deng et al., 2013) | Guardas dentro do teto; ganho no critério combinado |
| **V4 Longitudinal** | O sistema inteiro gera valor incremental? | **Grupo de controle permanente** (5% a 10% dos clientes recebem a política base, sem iniciativa comercial), comparado em 90 dias e mais | Revisão trimestral pelo dono |

Sobre simulação com usuário sintético [P]: útil para teste de fumaça e para o conjunto
adversarial; **não** é evidência de valor, porque o simulador é ele mesmo um modelo com os
mesmos vieses.

Sobre interferência [E]: com estoque finito, aleatorizar por cliente viola a hipótese de não
interferência (vender a última unidade ao tratado tira do controle). Decisões que consomem
recurso escasso se testam por **alternância no tempo** (Bojinov et al., 2023) ou se avaliam pelo
valor líquido do preço-sombra. Não se alterna a cada hora: o estoque consumido só volta no dia
seguinte, a confiança dura semanas, e uma loja só oferece poucos blocos comparáveis. Agrupar
por dia não cria amostra grande por decreto. Questões de relacionamento pedem desenho por
cliente; questões de capacidade, desenho por operação; não se misturam os dois estimandos.

### 8.2 Estrutura de métricas

| Dimensão | Métrica principal | Contramétrica obrigatória (anda junto) |
|---|---|---|
| Receita incremental | Margem de contribuição por cliente **elegível** (não por quem terminou a conversa) contra o controle permanente | Taxa de arrependimento: cancelamento, devolução ou reclamação em pedidos influenciados |
| Qualidade da recomendação | Recompra do item recomendado sem arrependimento | Aceite sozinho não conta |
| Resolução | Resolvido sem recontato em 72 horas | Tempo e mensagens até resolver |
| Satisfação e confiança | Integridade de compromissos; recontato; avaliação pedida por sorteio | Pesquisa só a quem o agente escolhe é proibida |
| Relacionamento | Recompra em 30 e 90 dias; valor esperado pelo modelo de recompra | |
| Eficiência | Custo por conversa resolvida (modelo, canal, pessoa) | Taxa de transferência evitável **e** de transferência perdida |
| Segurança e conformidade | Violações de invariante (zero); casos de equipe perdidos (zero) | |
| Decisão | Calibração; arrependimento estimado; fração de turnos em exploração | |
| Exposição | Aceitas, entregues e lidas, por decisão elegível | Ausência de recibo não é "não leu" |
| Equidade | Acesso à solução e desempenho por grupos pertinentes e legalmente tratáveis | Não inferir atributo sensível para medir |

O critério de promoção é: nenhuma guarda violada, **depois** ganho na métrica principal. Não
há índice único. Toda métrica declara numerador, denominador, fonte, janela e maturação antes da
coleta. Estratos se definem por características anteriores à ação; o que a ação muda (número de
turnos, aceite da oferta) é resultado, nunca controle.

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

### 8.5 Dois trilhos, e o que cada um libera

**Trilho de correção.** Alta frequência, auditável por verificador determinístico e por amostra
humana. É o que **libera autonomia**. Mede-se desde o primeiro dia: invariantes, componentes,
régua de episódios, integridade de compromissos.

**Trilho de economia.** Baixa frequência, matura devagar e, com o volume de uma loja, é
descritivo por muito tempo. Libera **mudança de política comercial**, nunca autonomia.

Regras do segundo trilho: denominador, janela e maturação escritos antes da coleta; só coortes
com janela concluída; desfecho sem resposta é censurado (nem resolvido, nem fracasso); custo
ausente é desconhecido, não zero; atribuição ao tratamento, exposição efetiva e execução são
três registros separados; resultado inconclusivo não prova equivalência; várias hipóteses pedem
correção de multiplicidade; e quem recebe o controle recebe atendimento legítimo, porque não se
sorteia o cumprimento de um direito.

A consequência, dita sem rodeio: **no primeiro ano, o critério de progresso é correção
auditável, não significância estatística.**

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
- **Freio e medidor**: interruptor geral e por classe de ação (5.8), teto de gasto por propósito, registro de toda chamada
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
Guarda-se o que foi usado, o que foi bloqueado e o que foi observado. A cadeia de raciocínio do
modelo não é prova e não é guardada como tal; a justificativa da decisão e o texto ao cliente
são registros separados.

## 10. Roteiro evolutivo

Cada degrau tem critério de saída mensurável e critério de recuo; não se sobe sem cumprir o
primeiro, e nenhum degrau entrega menos que o anterior.

| Degrau | Entrega | Critério de saída | Recua se |
|---|---|---|---|
| **D0 Contratos** | Esquemas e validadores, catálogo de movimentos, perfil de teste, vetores de termos e concessões, o Apêndice A como testes nomeados | Toda ação tem precondição e teste; toda jornada de referência tem estado final verificável | Fonte crítica inexistente ou política contraditória |
| **D1 Núcleo com adaptadores falsos** | Política por regra e prioridade, casca durável, contrato de efeito, resposta com prova por molde, compromissos, registro de decisão; as seis jornadas de referência de ponta a ponta | A suíte de conformidade passa sem Django, sem SDK de modelo, sem rede | Um teste só passa com conhecimento de um adaptador real |
| **D2 Primeiro adaptador, leitura e sombra** | Portas sobre o sistema real; decisão em sombra sobre conversas reais; junção de resultados | Provas de concorrência no mecanismo real; linhas de base das métricas de 8.2 | O adaptador precisou mudar o núcleo |
| **D3 Atendente verdadeira, assistida** | Informar, esclarecer, verificar com a equipe, encaminhar; leitor calibrado; perguntar por custo do erro | Trilho de correção aprovado em amostra humana; integridade de compromissos medida; fila humana operando | Afirmação sem lastro em produção; fila sem capacidade |
| **D4 Escrita limitada** | Comandos autorizados conforme o perfil | Integridade sob falha e concorrência; nenhum efeito duplicado; A/A limpo | Efeito duplicado ou estado ambíguo mal tratado |
| **D5 Conselheira** | Movimentos comerciais sob a restrição de conselheiro, por regra e prior: substituto na indisponibilidade, complemento, "o de sempre", encomenda antecipada; recuperação com compensação em teto; preço-sombra; controle permanente | Ganho de margem contra o controle sem piora de arrependimento nem de recontato | Poder insuficiente ou troca inaceitável |
| **D6 Política que aprende** | Sorteio explícito entre ações admissíveis; depois bandit com priors; avaliação contrafactual; portões | Primeira promoção de política aprovada offline e confirmada online | Retorno atrasado demais, deriva, perda de explicabilidade |
| **D7 Rede e pesquisa** | Segundo adaptador como prova de portabilidade; priors hierárquicos entre inquilinos; RL *offline* restrito; conversa entre o agente do cliente e o da loja | Núcleo intacto com adaptador novo; arrependimento de partida menor que sem a rede (H5) | Regra de uma empresa disfarçada de universal |

D0 a D3 valem para qualquer volume. D4 exige os portões de 5.8. D5 exige confiança do dono na
restrição de conselheiro. D6 exige volume ou paciência (7.1). D7 exige mais de um inquilino.

**As seis jornadas de referência** (todas com adaptadores falsos e domínio sintético, sem
presumir nada de uma loja real):

| # | Jornada | O que exercita |
|---|---|---|
| J1 | Pergunta de produto respondida com fato | Fatos com fonte, resposta com prova, desconhecido que não vira frase |
| J2 | Pedido ambíguo esclarecido | Pergunta no ar, referente do "sim", limiar por custo do erro |
| J3 | Fato que o sistema não tem: verificar com a equipe e devolver | Compromisso com dono e prazo, espera com retomada, escalonamento |
| J4 | Necessidade → cotação → termos → confirmação → pedido → recibo | O contrato de efeito inteiro |
| J5 | Reclamação e dúvida na mesma mensagem | Agenda de necessidades, prioridade, caso com dono, nenhuma oferta |
| J6 | Recomendação por necessidade explícita | Primeiro movimento comercial, restrição de conselheiro, recusa respeitada |

Ordem sugerida de construção: J1 e J2 (o esqueleto), J4 (o contrato mais difícil, cedo), J3 e
J5 (compromissos e posse), J6 por último.

## 11. Proposta de implementação experimental: Nice no Shopman

Esta seção é a única que depende do Shopman. É o mapa do **adaptador**, não a definição do
núcleo: nenhuma classe citada aqui vira tipo público do framework.

### 11.1 O que a Nice já tem, visto pela arquitetura

| Peça da arquitetura | Na Nice hoje | Distância |
|---|---|---|
| Porta de Canal | `concierge/contracts.py`, `transport.py`: registro de conexões, `ChannelCapabilities`, `IdentityAssurance`, `InboundEvent`, janela com prova [MEDIDO] | **Pronta**; é a porta mais madura |
| Porta de Modelo | `shopman/shop/ai.py`: conexão e rota por propósito, texto de cliente só para conexão aprovada; freio e medidor em andamento (WP-01) [MEDIDO] | Quase pronta |
| Porta de Comércio, leitura | Executores em `concierge/tools.py` sobre os services; disponibilidade como decisão de promessa (`PromiseDecision` em `packages/stockman/.../protocols/sku.py`, com esperado e planejado separados do factual) [CONFERIDO] | Existe, sem contrato explícito; preservar factual × esperado × planejado em vez de reduzir a "disponível" |
| Porta de Comércio, execução | `place_order` com orçamento, confirmação posterior, token, revisão esperada e `run_idempotent_mutation` (`shop/services/remote_mutations.py`) [CONFERIDO] | Forte, com uma janela aberta (11.2, A1) |
| Porta de Equipe | Transferência (`handoff.py`); `OperatorAlert` com `acknowledged_by`, `resolved_by`, `respond_by` [CONFERIDO]; "vou verificar" planejado (WP-05 a WP-07, WP-15) | Primitivas prontas; falta compor obrigação, aceite nominal, cumprimento e reabertura |
| Entender | `concierge/intents.py`: atos no plural, validação em código, regra local que soma [MEDIDO] | Pronto; **falta confiança calibrada** por ato |
| Estado | `concierge/dialogue.py`, em `Conversation.flags["dialogue"]`, gravado com o `turn_fence` [MEDIDO] | Estado de diálogo e época de posse prontos; **sem episódio, sem crença, sem estado do relacionamento** |
| Regras da casa e verificação de saída | `concierge/house_rules.py`: 14 regras, exemplos que são testes, efeitos `REPAIR`, `HOLD`, `RECORD` aplicados a toda resposta [CONFERIDO] | Pronto; é o contrato "passa, repara, segura" já implementado |
| Dizer | Frase da casa por molde (decisão do dono: o modelo não reescreve salvo necessidade provada) [MEDIDO] | Pronto, prova por construção |
| Exposição | `OutboundAttempt`, registro só de acréscimo das tentativas de envio (`shop/models/concierge.py`) [CONFERIDO] | Base pronta; falta ligar à decisão |
| Régua | `golden_set.json` (221 casos), `golden_memory.json` (47), `concierge_reply_eval`, `metrics.py` [MEDIDO] | Correção de mensagem existe; **não há régua de episódio, de política nem de resultado** |
| **Decidir** | Não existe como peça: o destino sai de regras encadeadas no executor | **A lacuna central** |
| **Registro de decisão** | Não existe; há `ConversationMessage.usage` (custo e tempo) | **A lacuna que impede aprender** |
| **Compromissos** | Só o embrião (`verifying` planejado, regra R6) | A generalizar |
| **Junção com resultado** | Não existe: nenhuma ligação conversa → pedido → recompra | A construir sobre o Orderman |

Leitura: a Nice chegou, por medição e por rodadas adversariais, a quase toda a **metade C** da
arquitetura (seção 3): verdade por construção, atos, estado, regras, régua. O que este estudo
acrescenta é a **metade que decide e aprende**, o **contrato de efeito** escrito e o recorte que
torna o conjunto independente do Shopman. As decisões vigentes do dono são compatíveis com a
arquitetura e viram linhas do perfil: a língua é do modelo e o dinheiro é do código (ADR-026); a
frase é da casa; "nunca afirmar algo falso"; "vou verificar" como caminho nobre; texto redigido
antes de sair.

### 11.2 Dois defeitos locais, conferidos no código

Os documentos externos apontaram dois achados. Conferi os dois no `main` de hoje; procedem.

**A1. A posse da conversa não é reconferida no instante do efeito.** Em `tools.py`,
`place_order.commit_local` abre uma transação, trava conversa e sacola e chama
`_assert_authority` (linhas 1348 a 1353). A transação fecha na linha 1392, e
`checkout_service.process` roda **depois**, na 1395, recebendo ator e conversa mas não a época
de posse. O invólucro idempotente usa `local_atomic=False`. Se uma pessoa assumir a conversa
nesse intervalo, o pedido pode ser registrado com a autoridade antiga. O desconto tem a mesma
classe de problema: `discount.py` não menciona `turn_fence` nem `_assert_authority`, e `_grant`
abre sua transação sem reconferir a posse [CONFERIDO].

É risco por leitura de código; a corrida não foi reproduzida. E está **latente**: hoje a escrita
da Concierge está fechada no ar (`CONCIERGE_READ_ONLY=true`) e `place_order` só é alcançável
pelo laço do agente, que o plano de ação vigente retira (corte C3) [MEDIDO]. Vira requisito
duro dos WPs de pedido na conversa (WP-11 a WP-14) e do adaptador: a propriedade 4 do contrato
de efeito (4.7) e os testes K11 e K12 do Apêndice A, rodados no Postgres real, com barreira
exatamente entre a validação e a gravação, provando que **nenhum efeito local** nasce.

**A2. Preço de modelo ausente vira custo zero no placar.** `intent_benchmark.prices_for` faz
`Price(price_in or 0.0, price_out or 0.0)` e devolve a lista de modelos sem preço; quem chama,
em `intent_pilot.py` (linha 194), guarda a lista em `_unpriced` e a descarta [CONFERIDO]. O
medidor de produção (`metrics.py`) já distingue ausente de zero. Consequência: um modelo sem
preço cadastrado parece gratuito na comparação. É correção pequena e independente do framework
(invariante N21, teste K34), e deve entrar antes de qualquer uso de custo para escolher modelo.

### 11.3 Alçadas que já existem e não podem sumir

A Nice já concede desconto com teto configurável, cancela dentro da janela de autoatendimento e
trata acréscimo a pedido feito [MEDIDO]. O framework não rebaixa nem amplia isso em silêncio:
cada uma vira linha do perfil da Nice, com dono e estado, e a decisão de herdar, restringir ou
desligar é do dono (15.5). O teto que o código traz como padrão não é, por estar no código,
política aprovada para a Nice.

### 11.4 Recorte do framework dentro do repositório

Proposta de forma, para o plano decidir: o núcleo como pacote Python puro, sem Django e sem
dependência de outro pacote, na mesma disciplina dos pacotes de `packages/`, com um teste que
falha se algo de infraestrutura for importado; os adaptadores (canal ManyChat, porta de IA,
portas de comércio sobre Orderman, Offerman, Stockman, Guestman, Craftsman e Payman, porta de
equipe sobre os alertas do Gestor) no orquestrador, como hoje. Nascer dentro do monorepo é mais
barato enquanto a suíte de conformidade e o primeiro adaptador evoluem juntos; extrair para
repositório próprio fica natural quando existir o segundo adaptador.

A regra do repositório "Protocol só com duas implementações reais" (ADR-001) pede cuidado: a
porta de canal e a de modelo já têm mais de uma; a de comércio teria uma só, e a segunda
implementação honesta é o **backend falso de referência** da suíte de conformidade, que é também
o que prova a independência de plataforma.

Não se cria um segundo livro de pedidos: `Session`, `Order`, pagamento e estoque continuam
sendo a verdade do negócio; o framework guarda referência e evidência.

### 11.5 Experimentos, em ordem, respeitando o modo somente leitura atual

| # | Experimento | Cliente vê? | O que prova | Custo |
|---|---|---|---|---|
| **X0** | **Corrigir A2** e escrever os testes de barreira de **A1** | Não | Invariantes N07, N10 e N21 no mecanismo real | Sem modelo |
| **X1** | **Decisão em sombra.** Em cada turno, gravar snapshot, candidatas, bloqueios, plano e seleção; juntar com pedidos do cliente em 24 horas e 7 dias | Não | Linhas de base reais (conversa → pedido, recontato, transferência) e se o contrato da cintura basta | Sem modelo |
| **X2** | **Calibração do leitor** nos 221 + 47 casos: diagrama de confiabilidade, conjunto conforme, e a regra de 4.2 avaliada offline contra o limiar fixo | Não | H3 em versão offline; se a confiança do leitor serve para decidir | Chamada paga: pede a palavra do dono |
| **X3** | **Compromissos** sobre o "vou verificar" (WP-05): toda promessa com dono, prazo e desfecho | Indiretamente | Integridade de compromissos como métrica; base de H7 | Sem modelo |
| **X4** | **Primeiro movimento aprendível: oferecer para separar** quando o cliente pergunta disponibilidade com quantidade ("teria 2 pães rústicos pra hoje?"). A/A primeiro; depois sorteio registrado entre "só responde" e "responde e oferece" | Sim | O mecanismo inteiro de D5 e D6 num caso de risco baixo. Com o volume atual só detecta efeito grande (7.1): serve para validar a máquina, não para concluir | Sem modelo |
| **X5** | **Substituto na indisponibilidade**: sugerir um substituto ranqueado por aderência, disponibilidade e margem líquida do preço-sombra (a regra "para o cliente é só Indisponível" continua valendo) | Sim | H4; a ponte com Stockman e Craftsman | Sem modelo |
| **X6** | **Controle permanente** de 10% quando houver iniciativa comercial ligada | Não | O valor incremental do conjunto | |

X1 é o primeiro passo recomendado no lado da Nice: não muda nada para o cliente, não gasta
modelo, e é a instrumentação da qual todo o resto depende.

### 11.6 O que a Nice não deve herdar deste estudo sem prova

Redação por modelo (o dono já decidiu; a arquitetura a mantém opcional); modelos de efeito
heterogêneo; qualquer RL; memória de preferência inferida; preço personalizado; contato
proativo. Nenhum deles se justifica com o volume atual, e cada um tem condição de reativação
escrita em 15.6.

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
4. **Resposta com prova e compromisso com dono**: a fala tratada como ato jurídico e
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
| H10 | O horizonte longo é bem aproximado pelo termo de relacionamento (decisão quase míope) | Valor em 90 dias: míope com termo contra RL offline | Só em D7 |
| H11 | Estado com proveniência reduz erro mais que trocar por um modelo maior | Erros de fato por episódio, a custo total igual | Ablação: com e sem proveniência, contra modelo maior |
| H12 | Política separada da linguagem torna barata a troca de modelo | Régua de episódios e canário com outro modelo, mesma política | Repetição da suíte |

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
- **A avaliação contrafactual com pouco dado só enxerga políticas vizinhas**, e só existe
  depois que há sorteio registrado; saltos de política não são avaliáveis offline.
- **A união de promessa e caso num só contrato** (4.6) é decisão minha, não consenso: a
  especificação externa mantém o caso separado. Se a fila humana de algum inquilino exigir um
  ciclo de vida muito diferente, a união terá de ser revista.
- **O contrato de efeito está especificado, não provado**: nenhuma das propriedades de 4.7 foi
  exercitada por teste nesta sessão. A1 foi lido no código, não reproduzido.
- **As regras de correlação de episódio são padrões razoáveis, não medidos.** Errar a fronteira
  do episódio contamina toda métrica de resolução.
- **Não medi nada novo no banco**: os números da Nice vêm dos documentos do repositório. As
  especificações dos protocolos de comércio para agentes não foram lidas na fonte. A situação
  regulatória brasileira de IA precisa de conferência na data.
- **Não conferi as referências próprias dos documentos externos.** Quatro delas não entraram na
  minha lista por isso (14.2).

## 14. Confronto com os documentos de outros agentes

Lidos por inteiro: a arquitetura de referência v1.0 (16/11), o relatório de confronto com o
Shopman (17/11), a especificação v0.1 do núcleo, uma segunda resposta independente e uma
revisão adversarial. Convergem com a v1 no centro: compreender, decidir, autorizar, executar e
avaliar separados; política fora da geração de texto; POMDP como linguagem e não como motor;
catálogo fechado de ações; avaliação causal honesta; nada de reduzir tudo a dinheiro; roteiro
por evidência. A convergência de três agentes independentes é ela mesma um sinal de que o
problema tem um centro de gravidade.

### 14.1 O que entrou, e onde está

| O que os externos tinham e a v1 não | Onde entrou |
|---|---|
| Cadeia de efeito completa: termos canônicos, concessão, comando, recibo com estado × efeito, idempotência, ponto de linearização, reconciliação | 4.7, P9, 5.4, 5.5 |
| Posse com época (ficha de cerca) reconferida no efeito; transferência revoga posse, não efeito | 4.7, 5.7 |
| Episódio como unidade de análise; agenda de necessidades; caso com dono, prazo e critério de resolução | 1.2, 5.7, 4.6 |
| Fato com três valores (conhecido, desconhecido, ausente); precondição desconhecida bloqueia; custo desconhecido não é zero | C6, 5.5, N21 |
| Exposição separada da decisão (preparada, aceita, entregue, lida, desconhecida) | 5.5, 8.2 |
| Resultado com janela, maturação, censura e supersessão | 5.5, 8.5 |
| Perfil de implantação versionado; requisito ausente desliga a ação, não o sistema | 5.8 |
| Ambientes `test`, `shadow`, `live`, com semântica de sombra | 5.8 |
| Escada de identidade e matriz ação × garantia | 5.6 |
| Máquina de estados do episódio, com espera sempre retomável | 5.7 |
| Algoritmo normativo do turno: persistir antes, comparar versão, gravar estado e trabalho juntos, não segurar transação durante modelo | 5.3 |
| Ordem de prioridade entre famílias de movimento | 4.1, 4.5 |
| Verificação de saída como contrato (passa, repara, segura) | 4.6 |
| Capacidade humana como portão; freio por classe de ação | 4.4, 5.8 |
| Dois trilhos de avaliação; régua de episódios; A/A antes de A/B; intenção de tratar; regra de três | 8.1, 8.5 |
| Desenho de experimento: sorteio persistente por cliente, probabilidade depois dos filtros, ação efetivamente executada, realizador fixo | 5.5, 7.3, 8.5 |
| Invariantes e testes de conformidade numerados | Apêndice A |
| Achados locais A1 e A2, e as alçadas que a Nice já tem | 11.2, 11.3 |
| Governança dos documentos e decisões antes do primeiro código | seção 15 |

### 14.2 O que não entrou, e por quê

| Proposta externa | Decisão aqui | Motivo |
|---|---|---|
| Nove portas, com `AuthorityPort` própria | Oito portas; a autoridade é do núcleo (emite) e do executor (confere no efeito) | A própria especificação admite que uma conferência remota separada do efeito dá atomicidade falsa |
| `CaseRecord` como contrato à parte | Unido à promessa em `Commitment`, com dois tipos | O "vou verificar" tem a mesma forma de um caso; um contrato só dá uma métrica só (integridade de compromissos) |
| Primeira entrega com uma jornada só (cotação e pedido) e sem ação de recomendar | Seis jornadas de referência, todas com adaptadores falsos, e `recommend` no catálogo | A revisão adversarial já apontava o encolhimento silencioso de quatro jornadas para uma; sem recomendar não há como exprimir a primeira jornada comercial |
| Política só determinística, formalização "deliberadamente mínima" | Mantida a camada de valor (`Q`, valor da informação, conselheiro, preço-sombra), mas **em degraus**: regra primeiro, números só com estimador | Sem ela não há o que aprender nem o que medir depois; com ela desde o início seria complexidade sem dado |
| Vetor de objetivos usado só offline | Adotado em parte: no turno vale só o `Q` da família vencedora; o vetor compara políticas | Concilia as duas posições |
| Dividir a documentação em `docs/nice/` com oito arquivos | Não feito aqui; recomendado para a fase de especificação (15.8) | Este é um documento de referência; a divisão serve quando contrato, estado e portas forem editados por mãos diferentes |
| Referências próprias dos externos (τ-Rec, AgentRecBench, bandits conservadores não lineares, aquisição ativa de atributos) | Não entraram na lista | Não as conferi; ficam citadas aqui como pistas, não como fonte |
| Nome `docs/nice/` e `nicecore` para o núcleo | Não adotado | O núcleo não pode levar o nome da primeira instanciação |

### 14.3 Onde a v1 estava errada ou incompleta

1. **"Registrar probabilidade 1 desde já torna o passado reaproveitável."** Meia verdade.
   Registro de política determinística dá linha de base, reexecução e contrato estável; **não**
   dá suporte para avaliar ações que não foram escolhidas. Corrigido em 0, 5.5 e 8.1: a seleção
   grava `not_applicable`, e a avaliação contrafactual só começa com sorteio.
2. **Efeito tratado em uma linha.** "Mudança devolve recibo" não basta: faltavam termos
   canônicos, concessão, idempotência, estado desconhecido, ponto de linearização. É a maior
   lacuna da v1, e os documentos externos a cobrem bem (4.7).
3. **Sem unidade de análise.** A v1 decidia por turno e media por conversa; o episódio resolve
   a Q1 que ela deixava aberta.
4. **Thompson sampling cedo demais.** Com probabilidade de escolha estimada por amostragem, o
   registro fica frágil. Primeiro, sorteio explícito com probabilidades conhecidas (7.3).
5. **Exposição ausente.** Decidir e enviar não provam que o cliente viu; sem isso, o efeito
   medido mistura política com entrega.
6. **Exemplo de política que contradizia a Nice.** A v1 usava "não fazemos desconto por aqui"
   como exemplo; a Nice tem desconto com teto. Trocado, e a regra virou seção (11.3).
7. **Sombra sem definição.** A v1 propunha "registro em sombra" sem dizer o que a sombra pode e
   não pode fazer (5.8).

### 14.4 O que os externos não cobrem e este documento cobre

Para quem for planejar, é onde **não** procurar resposta naqueles documentos: o modelo de valor
da decisão e a derivação do limiar de pergunta pelo custo do erro (4.1, 4.2); a restrição de
conselheiro (4.3); o preço-sombra como contrato com a operação (4.4); resposta com prova e
promessa como compromisso (4.6); a pilha de priors com peso declarado e a conta de poder
aplicada ao volume real (seção 7); controle permanente, substitutos de longo prazo e separação
de poderes (seção 8); e as lacunas que a revisão adversarial achou na especificação e que aqui
já vêm resolvidas: agendamento de prazos (porta de relógio), matriz válida de estado × efeito,
prazo de reconciliação, transições de necessidade, regras de correlação de episódio, semântica
de sombra, critério de determinismo, e os testes de lastro, de injeção por conteúdo recuperado e
de reordenação (K23, K26, K03).

### 14.5 Concordância de nomes

| Aqui | Nos documentos externos |
|---|---|
| movimento, catálogo de movimentos | ação semântica, catálogo de ações |
| registro de decisão (`DecisionRecord`) | `DecisionRecord` |
| concessão | `AuthorizationGrant` (grant) |
| época de posse | `owner_epoch`, fence |
| compromisso, tipo caso | `CaseRecord` |
| compromisso, tipo promessa | sem equivalente |
| resposta com prova, verificação de saída | realização fundamentada, `verify_outbound` |
| ordem de prioridade | regime hierárquico |
| naturezas de decisão | natureza de cada decisão |
| porta de relógio e agenda | `Clock/IdPort` (sem agendamento) |
| porta de equipe | `CasePort` e parte de `ChannelPort` |
| perfil de implantação | `DeploymentProfile` |
| degraus D0 a D7 | fatias F1 a F8 e etapas 0 a 7 |
| testes K01 a K40 | T01 a T29, mais T30 a T32 propostos |

## 15. Guia para a sessão que vai planejar a implementação

### 15.1 O que este documento é

É **referência**, não especificação. Duas partes são normativas para o plano: as propriedades
do contrato de efeito (4.7) e os invariantes do Apêndice A. O resto orienta. O plano deve
produzir a especificação (esquemas, assinaturas, vetores de teste) e é ela que passará a valer
para o código; divergência entre a especificação e este documento se anota, não se esconde.

### 15.2 Dois produtos, dois planos

| | Framework | Adaptador da Nice |
|---|---|---|
| O que é | Núcleo, contratos, portas, adaptadores falsos, suíte de conformidade | Implementação das portas sobre o Shopman, mais o perfil da Nice |
| Depende de | Nada de Django, de Shopman, de SDK de modelo ou de canal | Do framework e dos services canônicos do Shopman |
| Pronto quando | A suíte passa sem rede, com as seis jornadas | A suíte comum passa **e** as provas de concorrência e reconciliação rodam no mecanismo real |
| Não pode | Levar regra, nome ou valor de uma empresa | Mudar o núcleo para caber |

A regra de corte, emprestada da segunda resposta independente: **o que não puder ser dito sem
"padaria", "Shopman", "WhatsApp" ou "Django" pertence ao adaptador ou ao perfil.** Desconto,
alérgenos, prazos, voz da casa e vocabulário são perfil e fontes; o núcleo governa como
consultar, decidir e comprovar.

### 15.3 Forma sugerida do pacote

Módulos por responsabilidade, sem agentes: `contracts` (tipos, validadores, vetores),
`catalog` (movimentos e precondições), `policy` (admissibilidade, prioridade, escolha; pura),
`workflow` (casca durável, máquina de estados, esperas), `authority` (concessão), `reply`
(plano, moldes, verificação de saída), `ledger` (decisão, compromisso, exposição, resultado),
`evaluation` (réguas, portões), `ports` (interfaces e capacidades), `testing` (adaptadores
falsos e suíte de conformidade, distribuídos junto para qualquer adaptador usar).

### 15.4 Decisões de engenharia a fechar antes do primeiro código

Nenhuma precisa do dono.

1. Onde o pacote nasce (recomendo: dentro do monorepo, com teste de importação; 11.4) e que
   nome leva (não o da Nice).
2. Como os contratos são definidos (esquema independente de linguagem mais tipos Python
   gerados, ou o inverso) e o formato canônico dos termos, com vetores de teste.
3. Armazenamento de referência da suíte (em memória basta para o núcleo; o adaptador prova no
   banco real).
4. Catálogo de movimentos da primeira versão e a precondição de cada um.
5. Padrões do perfil de teste: janela de episódio, retenção de chave de idempotência, prazos.
6. Base de código para mapear o adaptador: `origin/main`, nunca o checkout principal, que
   costuma estar muito atrás.
7. Como a especificação se divide em arquivos e quem é dono de cada um (15.8).

### 15.5 Decisões do dono

Cada uma é uma linha do perfil, com estado. Enquanto estiver "proposta", a ação fica desligada.

| Decisão | Enquanto não houver resposta |
|---|---|
| A Nice herda desconto com teto, cancelamento em autoatendimento e acréscimo, em quais canais? | Comportamento atual preservado; nada novo ligado |
| Lista de movimentos comerciais da primeira versão | Só informar, esclarecer, verificar, encaminhar |
| Substituto do interesse do cliente (Q3) | Só recomendação por necessidade explícita |
| Teto de compensação por incidente e por cliente (Q4) | Compensação só com pessoa |
| Aceita sortear ofertas entre clientes? (Q8) | Nenhum experimento de oferta |
| Fila humana: quem aceita, em quanto tempo, e fora do expediente | Sem escrita autônoma |
| Unidade e janela do primeiro desfecho (Q1) | Só telemetria; nenhuma alegação de eficácia |
| Base legal e retenção para memória além do episódio (Q6) | Só memória declarada |

### 15.6 O que não construir agora, e quando reabrir

| Não agora | Reabre quando |
|---|---|
| Redação por modelo | Houver conversas reais em que a frase da casa saiu dura ou confusa, e teste que mostre ganho |
| Bandit, efeito heterogêneo, RL | Houver sorteio registrado, volume para a conta de 7.1 e portão aprovado |
| Preferência inferida, perfil de longo prazo | Houver base legal, tela em que o cliente veja e corrija, e ganho medido sobre a memória declarada |
| Preço personalizado | Houver política explícita, análise de equidade e teste próprio |
| Contato proativo | Houver permissão registrada por finalidade e canal, e medida de efeito incremental |
| Vários agentes, microsserviços, segundo livro de pedidos | Houver requisito demonstrado de escala ou isolamento |
| Nota única de "qualidade da conversa" | Nunca: mistura o que não se soma |

### 15.7 Convivência com os WPs em voo da Concierge

O plano de ação vigente da Concierge (16 WPs) segue. O framework não o bloqueia nem o refaz:
os WPs entregam comportamento que o adaptador depois embrulha. Três pontos de contato: (i) A1
vira requisito dos WPs de pedido na conversa; (ii) A2 é correção pequena e avulsa; (iii) a
refatoração da Nice para dentro do framework só começa depois de D1, para não mover a Concierge
enquanto as portas ainda mudam. Toda sessão confere `gh pr list` e `git worktree list` antes de
tocar em arquivo da Concierge.

### 15.8 Governança dos documentos

- **Um fato, um dono.** Contrato mora num lugar; os outros documentos apontam, não redefinem.
- **Estado por artefato** (rascunho, em revisão, vigente) e um índice com a ordem de leitura.
- **Decisão de arquitetura vira ADR** no padrão do repositório; decisão do dono vira linha do
  perfil, com dono e data.
- **Vetor de teste mora com o código**, não em anexo de documento.
- **Matriz teste × invariante** mantida junto da suíte (o Apêndice A já a traz).
- **Evidência de código presa a commit.** Linha de arquivo sem commit envelhece em dias.

## Apêndice A. Invariantes e testes de conformidade

Base da suíte que acompanha o framework. Origem: **ext** = documentos externos (I01 a I18, T01
a T32), **v1** = desta linha de trabalho. São especificações de caso, não resultados: nada aqui
foi executado.

### A.1 Invariantes

| ID | Regra | Origem |
|---|---|---|
| | **Verdade e fala** | |
| N01 | Afirmação sem lastro (fato, recibo, política, compromisso) não sai | v1 |
| N02 | Fato ausente ou vencido não vira afirmação; poder prometer não é ter unidade separada | ext |
| N03 | Preço, total, prazo e estado nunca vêm de texto de modelo | v1, ext |
| N04 | Toda promessa cria compromisso com dono e prazo; sem dono possível, não se promete | v1 |
| | **Autoridade e efeito** | |
| N05 | Nenhum efeito nasce de texto ou de saída de modelo; só de comando do catálogo, validado | ext |
| N06 | Confirmação corresponde aos termos canônicos exatos e à identidade autorizada, e é posterior a eles | ext |
| N07 | Mudança material, concessão vencida ou revogada, ou posse inválida bloqueia o efeito antes do ponto de linearização | ext |
| N08 | Mesma chave e mesmo conteúdo devolvem o recibo existente; mesma chave e conteúdo diferente é conflito | ext |
| N09 | Resposta que não chegou não é falha sem efeito; não se repete com chave nova; chave expirada com efeito desconhecido bloqueia até reconciliar | ext |
| N10 | Transferência revoga a posse da automação; efeito em voo continua reconciliável | ext |
| N11 | Inquilino, ambiente, identidade e autorização de objeto são conferidos em leitura e em escrita | ext |
| | **Estado e registro** | |
| N12 | Entrada duplicada não cria comando; texto igual não prova duplicata; evento fora de ordem não autoriza | ext |
| N13 | Estado, eventos e trabalho local são gravados juntos; quem consome aceita repetição | ext |
| N14 | Snapshot e decisão são imutáveis; correção é registro novo | ext |
| N15 | Conversa encerrada, silêncio, sentimento ou transferência não comprovam resolução | ext |
| N16 | Aceite do canal, entrega, leitura e efeito comercial são observações distintas | ext |
| | **Decisão e aprendizado** | |
| N17 | Toda decisão registra candidatas, bloqueios e método de seleção; se sorteada, a distribuição depois dos filtros e a probabilidade da ação executada | v1, ext |
| N18 | Só se explora dentro do conjunto admissível, e nunca em preço, fato, segurança ou autoridade | v1 |
| N19 | Iniciativa comercial só passa com a restrição de conselheiro e os limites de contexto satisfeitos | v1 |
| N20 | Quem aprende não escreve o resultado pelo qual é avaliado; resultado vem de fonte independente | v1, ext |
| N21 | Desconhecido não vira zero (custo, resultado, probabilidade); resultado imaturo é censurado, não fracasso | ext |
| N22 | Nenhuma política ou modelo se promove sem portão e autorização humana | v1 |
| | **Segurança e independência** | |
| N23 | Texto não confiável (cliente, catálogo, memória, resposta da equipe) é dado: não altera perfil, ferramenta, identidade nem autoridade; o leitor não tem ferramentas | v1, ext |
| N24 | Trocar modelo, canal ou sistema não muda contratos nem autorizações; diferenças são capacidades declaradas | ext |
| N25 | O que vai a um modelo externo sai redigido; registros, memória e chamadas respeitam finalidade e retenção | ext, v1 |
| N26 | O núcleo não importa infraestrutura (ORM, SDK de modelo, cliente de canal) | ext |

### A.2 Testes

| ID | Dado e quando | Resultado obrigatório | Invariantes | Origem |
|---|---|---|---|---|
| K01 | Mesma entrada, identidade estável, chega duas vezes | Uma entrada lógica; nenhum comando duplicado | N12 | T01 |
| K02 | Duas mensagens iguais com identidades diferentes | As duas preservadas | N12 | T02 |
| K03 | A confirmação chega antes dos termos (ordem de chegada trocada) | Não autoriza; mesmos efeitos finais que na ordem certa | N06, N12 | T06, T32 |
| K04 | Fonte crítica falha ou está vencida | Fato desconhecido; ação dependente bloqueada; pergunta, molde ou pessoa | N02 | T03 |
| K05 | O modelo devolve ação fora do catálogo | Nenhuma execução; erro tipado; queda registrada | N05 | T04 |
| K06 | Confirmação vem de outro cliente, inquilino ou ambiente | Concessão recusada; nenhum dado revelado | N06, N11 | T05 |
| K07 | Preço, destinatário ou item muda depois da confirmação | Comando recusado; novos termos e nova confirmação | N07 | T07 |
| K08 | Mesma chave e conteúdo repetidos depois de resposta perdida | Um efeito, um recibo | N08, N09 | T08 |
| K09 | Mesma chave com conteúdo diferente | Conflito estável; recibo não é sobrescrito | N08 | T09 |
| K10 | Queda depois do efeito no sistema de registro e antes do recibo local | A reconciliação recupera o pedido original | N09, N13 | T10 |
| K11 | A revogação vence imediatamente antes do ponto de efeito | Nenhum efeito local do comando antigo | N07, N10 | T11 |
| K12 | A transferência ocorre depois da submissão externa | Efeito reconciliado; nenhuma promessa de desfazer | N10 | T12 |
| K13 | Dois trabalhadores usam a mesma versão do episódio | Um vence; o outro recarrega e não repete decisão nem efeito | N13 | T13 |
| K14 | O trabalhador morre no meio da execução | Reconcilia antes de repetir; não troca a chave | N09 | T14 |
| K15 | A concessão vence entre a decisão e a execução | Recusada no ponto de efeito | N07 | T27 |
| K16 | Chave expirada com efeito anterior desconhecido | Bloqueia até reconciliação ou pessoa | N09 | T28 |
| K17 | O canal devolve "desconhecido" ao enviar | Não marca entregue nem reenvia às cegas | N16 | T15 |
| K18 | O canal confirma entrega e não suporta leitura | Entregue; "lida" segue não observada | N16 | T16 |
| K19 | Reclamação e dúvida na mesma entrada | Duas necessidades; a dúvida é respondida; o caso tem dono e prazo; nenhuma oferta | N15, N19 | T17 |
| K20 | A fila não aceita a transferência | Compromisso monitorado, com contingência; nada afirma aceite | N04, N15 | T18 |
| K21 | O cliente encerra a conversa com compromisso aberto | A interação encerra; compromisso e episódio seguem | N15 | T19 |
| K22 | Promessa com prazo vence sem resposta da equipe | Evento de prazo; escala conforme o perfil; cliente avisado uma vez | N04 | v1 |
| K23 | A redação traz preço ou estado sem fato correspondente | Reprovada; sai a base por molde; caso registrado | N01, N03 | T30 |
| K24 | A resposta afirma uma ação ("separei") sem recibo | Reprovada | N01 | v1 |
| K25 | Instrução embutida na mensagem do cliente | Tratada como dado; nenhuma mudança de autoridade | N23 | T26 |
| K26 | Instrução embutida em descrição de catálogo ou em resposta da equipe | Idem; não vaza para outra chamada de modelo sem enquadramento de dado | N23 | T31 |
| K27 | A política permite prometer sem estoque físico | Não comunica unidade física separada | N02 | T22 |
| K28 | Memória corrigida ou vencida | O referente inválido não reaparece em resumo nem em recuperação | 6.1 | T23 |
| K29 | "Sim" depois de a equipe devolver a conversa | Não é lido contra a pergunta antiga | N06 | v1 |
| K30 | Duas leituras possíveis: numa mudança; numa consulta | Na mudança, pergunta; na consulta, cobre as duas | 4.2 | v1 |
| K31 | Problema aberto ou atrito alto | Nenhuma iniciativa comercial no plano | N19 | v1 |
| K32 | Decisão sorteada; depois, uma guarda bloqueia a ação | Distribuição e probabilidade gravadas; o bloqueio gera nova decisão ligada | N14, N17 | v1, ext |
| K33 | A janela do resultado ainda não terminou | Censurado, não zero | N21 | T20 |
| K34 | Modelo sem preço cadastrado | Custo desconhecido; comparação econômica vetada | N21 | T21 |
| K35 | Fonte externa corrige um resultado anterior | Novo registro que substitui; histórico preservado | N14 | T29 |
| K36 | Ambiente de sombra | Nenhuma escrita em porta de comércio; nenhuma exposição | 5.8 | ext |
| K37 | Troca-se o canal ou o modelo falso | Os mesmos testes de política e autorização passam | N24 | T24 |
| K38 | O núcleo roda sem Django, sem SDK, sem rede | Importa e passa a suíte | N26 | T25 |
| K39 | Requisito crítico ausente no perfil | Ação inelegível, com código; informar e encaminhar seguem | 5.8 | ext |
| K40 | Reexecução de um turno gravado, com a mesma política e a mesma semente | A mesma decisão | C3 | v1 |

Cada teste, ao virar código, declara o que prova no núcleo e o que depende do adaptador real.
Os de concorrência (K11 a K14) só valem para um adaptador quando rodados no mecanismo real
dele, não em simulação.

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

**Sistemas distribuídos e eventos raros**
- Hanley, J. A., Lippman-Hand, A. (1983). If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA*, 249(13).
- Helland, P. (2012). Idempotence is not a medical condition. *ACM Queue*, 10(4).
- Herlihy, M., Wing, J. (1990). Linearizability: a correctness condition for concurrent objects. *ACM TOPLAS*, 12(3).
- Kleppmann, M. (2016). How to do distributed locking. Texto do autor, sobre fichas de cerca.

**Direito e normas**
- Brasil. Lei 8.078/1990 (CDC), art. 30. Lei 13.709/2018 (LGPD), art. 20.
- *Moffatt v. Air Canada*, 2024 BCCRT 149.
- União Europeia. Regulamento (UE) 2024/1689 (AI Act), arts. 5º e 50.
- NIST (2023). *AI Risk Management Framework 1.0*.

**Do repositório** (fonte dos fatos marcados [MEDIDO])
- `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`, `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`,
  `docs/decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md`,
  `docs/guides/concierge-supervised-improvement.md`, `shopman/storefront/concierge/`.
- Conferidos no código nesta sessão, no commit `43eeeede4`: `shopman/storefront/concierge/tools.py`
  (`place_order`), `discount.py`, `intent_benchmark.py`, `intent_pilot.py`, `house_rules.py`;
  `shopman/shop/services/remote_mutations.py`; `shopman/shop/models/concierge.py`;
  `shopman/backstage/models/alerts.py`; `packages/stockman/shopman/stockman/protocols/sku.py`.

**Documentos de outros agentes** (lidos por inteiro; fora do repositório)
- *Arquitetura de Inteligência Comercial Conversacional*, v1.0, 16/11/2026.
- *Arquitetura agnóstica de inteligência comercial: confronto com Shopman / Nice*, 17/11/2026.
- *Especificação implementável v0.1: núcleo agnóstico de inteligência comercial*, 17/11/2026.
- *Resposta independente ao prompt original*, 17/11/2026.
- *Revisão adversarial, Nice / Shopman*, 17/11/2026.
