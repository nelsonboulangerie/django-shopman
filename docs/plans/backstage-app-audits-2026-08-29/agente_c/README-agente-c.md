# Terceira leitura — Agente C

**Data:** 2026-08-29 · **Autor:** Agente C
**Originais intactos:** `../WP-01..09` (Agente G) e `../agente_d/WP-01..09` (Agente D) — **não foram tocados.**
**Esta versão:** `agente_c/` — `WP-00` (transversal) e `WP-01..09`.

---

## 1. Veredito

O Agente G levantou o mapa certo. O Agente D corrigiu a prescrição e acrescentou o que faltava de rigor
sobre RBAC, dependências e fronteiras de dono. Os dois entregaram trabalho bom, e a maior parte do que
escreveram sobrevive intacta aqui.

**O que faltava era um terceiro passo, e ele não é opinião: é medição.** Nenhum dos dois executou código. O
Agente D verificou as *evidências* do Agente G — se a linha citada existe e diz o que ele disse — mas ninguém
verificou as *consequências*: se o caminho descrito é alcançável, se a UI dispara aquilo, se um teste já
cobre, se o `main` já corrigiu, se o grupo que "pode fazer" existe de fato no `setup_groups`.

Esta rodada fez isso, com nove verificações independentes que abriram cada função inteira e, quando o achado
dependia de comportamento, **rodaram o código**. O resultado muda a lista de trabalho em quatro direções:

| | O que mudou |
|---|---|
| **Refutado** | ~20 itens saíram. Alguns porque o código os desmente; outros porque, implementados como escritos, **quebrariam** algo que funciona. |
| **Rebaixado** | Dois P0 do Agente D não sustentam P0 quando medidos. Um deles é um bug que **nenhum cliente do sistema alcança**. |
| **Agravado** | Quatro achados são piores do que ambos pintaram — e num deles o Agente D acertou o mecanismo e **inverteu o exemplo**. |
| **Novo** | Vinte e um achados que nenhum dos dois viu, incluindo **quatro P0**, três deles provados executando. |

E um quinto resultado, que não cabe em nenhum WP de app: **o plano de nove frentes paralelas não sobrevive a
este repositório**. Isso está no `WP-00`, e é a parte que decide se o trabalho chega ao ar.

---

## 2. O que os dois agentes acertaram

Vale dizer, porque é a maior parte:

1. **O template.** Status / Superfície / Fronteira / Evidências / Achados / Aceites / Fora de escopo / Prompt
   executor, nos nove. Mantive integralmente.
2. **As quatro invariantes** do README do Agente G — identidade operacional, servidor decide capacidade, nada
   irreversível sem contrato, UX de chão de fábrica. São a régua certa e não mudei uma vírgula.
3. **A insistência do Agente D no `setup_groups`.** É o dono único do RBAC, usa `set` (o que sai da lista sai
   do banco) e tem teste de paridade. Ele estava certo em exigir uma seção por WP. Eu levo isso adiante: como
   ele usa `set`, **as seis mudanças de permissão têm que ser um PR só** — ver §5.
4. **A recusa do Agente D em tratar decisão documentada como bug.** Correto, e apliquei o mesmo filtro às
   propostas dele.
5. **A fronteira de dono declarada por WP.** Mantida e refinada.
6. **A ordem geral** (P0 → contrato → estação → permissões → UX). Mantida, agora com matriz de colisão.

---

## 3. O que a terceira leitura mudou

### 3.1 Refutado — o que sairia pior se fosse feito

Estes não são desacordos de gosto. São itens que, implementados como escritos, quebram algo:

| WP | Proposta | O que aconteceria |
|---|---|---|
| 01 | Validar `SHOPMAN_SURFACE_URLS` inteiro contra o cookie domain (D) | **Reprovaria todo deploy correto.** A chave `loja` é o apex do storefront, deliberadamente fora da zona de operador — é o ponto inteiro do middleware de sessão. |
| 01 | "401 → sessão expirada" (G **e** D) | **Produz um `if` que nunca entra.** O backstage nunca devolve 401 (§3.4). |
| 02 | Dedupe de `fire_tab` por `client_request_id` (G) | **Quebra o disparo por curso.** A idempotência real é do ledger do KDS, por linha, sob lock. |
| 03 | Exigir motivo no cancelamento de corrida (D) | **Deixa o operador sem conseguir cancelar corrida.** A única tela que chama o endpoint nunca envia motivo e não coleta nenhum. |
| 04 | Campo `version`/`rev` novo no `KDSTicket` (G e D) | Migração e campo no core para um problema que a **identidade estável do item** resolve sozinha. O CLAUDE.md proíbe campo novo no core sem necessidade comprovada. |
| 04 | Envelope comum em todas as mutações (G e D) | Contrato para consumidor que **não existe** — a UI não lê nenhum campo de nenhuma dessas respostas. |
| 05 | ~11 permissões novas (G) | As 10 permissões por coluna **já existem**, são concedidas e têm teste de paridade. |
| 05 | Pesagem passa a usar o iniciado (G e D) | **Quebra a estabilidade da etiqueta cega**, fixada por teste ("reimpressão às 10h bate com a etiqueta das 6h"). Uma reimpressão passaria a discordar da etiqueta colada no pote. |
| 06 | Permissões finas de Compras agora (G e D) | Preparação para um usuário que **não existe**: `operate_purchase` é só do Gerente. |
| 06 | "Aprender de-para fiscal" como P0 (G e D) | É decisão documentada em `data-schemas.md`, com três testes. O risco real é outro, e tem fix de uma linha. |
| 07 | Degradar o gerador de cenários por "egress para IA" (D) | **Falso positivo** (§3.3). Degradaria o recurso para resolver um problema que ninguém decidiu que existe. |
| 09 | Migrar o template de refund para primitivas Unfold (G e D) | **Já é 100% canônico.** Custo maior que o risco. |
| 09 | "Dezenas de violações" como motivo para adiar o gate (D) | São **20, em 4 arquivos** — medido. E 17 estão em código que nunca renderiza. |

Mais os aceites inescrevíveis que o Agente D já tinha marcado e eu confirmo: `approve_purchase` e "política"
que não existem; "o número planejado bate com a audiência confirmada", que exige congelar a audiência —
decisão de produto não tomada, já que o código re-resolve na hora **de propósito**.

### 3.2 Rebaixado — os dois P0 do Agente D que não sustentam P0

Isto importa porque prioridade errada custa a ordem de execução inteira.

- **`bool("false")` no KDS.** O bug é real — medido, em JSON e em form-encoded. Mas **nenhum caminho da
  superfície produz uma string**: a UI manda boolean real. E o efeito é assimétrico: um `"false"` espúrio só
  marca item que estava desmarcado, nunca desmarca um marcado. Um bug que nenhum cliente do sistema alcança
  não é P0. → **P2**, com a ressalva de que a **mesma** falha de parsing existe na flag `force` da produção,
  que nenhum dos dois listou (§3.4).
- **SSE do KDS vazando `session_key`.** Confirmado. Mas quem lê o canal já pode ler o board inteiro **com nome
  do cliente** por REST, e o grupo Cozinha **não tem** a permissão que aceita `session_key` como entrada. É
  uma chave que o portador não consegue usar. O que legitima o achado é a regra do ADR-016, não o dano. →
  **P2**, com fix que é deleção pura.

### 3.3 O achado mais pesado do Agente D é um falso positivo

O Agente D acusou **"egress de financeiro para provedor de IA"** no gerador de cenários do B.I. Verifiquei
campo a campo, porque era a acusação mais grave dos nove WPs.

O que sai são **agregados de venda**: totais, série por dia, faturamento por canal, top 10 SKUs com nome,
pedidos por hora e por dia da semana. **Não sai nenhum pedido, nome de cliente, telefone, CPF, apuração de
caixa nem nome de operador.** A fronteira está documentada **três vezes** — docstring do módulo, docstring da
função, e o plano de fundação de dados — e o código a respeita. O recurso só roda com a chave configurada, e
sem ela o botão nem aparece.

É **decisão de negócio para o dono**, não bug — e continua valendo perguntar (§6). Mas não é achado de
auditoria, e a correção proposta teria degradado um recurso funcionando.

### 3.4 Agravado — quatro que são piores do que ambos pintaram

- **PDV, terminal (P0).** O Agente D achou o mecanismo e **inverteu o exemplo**: o caso que ele cita não
  quebra. Quebra qualquer ref **antes** de `pdv-main` em ordem alfabética. E o efeito não é "operar no caixa
  errado" — é **o PDV parar de vender**, com o turno aberto na tela e "Abra o caixa antes de finalizar" na
  mensagem, sem saída pela UI. Um clique de gestor em Equipamentos dispara isso. **Pode já estar no ar** — é
  a primeira pergunta de §6.
- **Hub, tile de Produção (P1).** Não é "o tile some". Um usuário com **só** a permissão que o app de Produção
  exige recebe a **Central inteira vazia**, com "Nenhum app liberado, fale com o gerente" — enquanto consegue
  abrir a superfície digitando a URL. Provado. E o nav do Admin, o **outro** launcher para o mesmo destino, já
  usa o predicado certo: o Hub é o outlier.
- **Compras, custo mestre (P0).** A auto-promoção a fornecedor preferido é pior do que o Agente D disse:
  `is_preferred` **decide qual fornecedor recebe o pedido de reposição**. Uma compra de emergência às cinco da
  manhã pode eleger o fornecedor caro como o canônico, em silêncio. E a documentação ainda afirma que a tabela
  "não tem leitor" — o código andou, a documentação não.
- **Admin, ação por GET (P0).** O Agente D disse "view-only executa refund". O mecanismo está certo e o alvo
  errado: o único grupo não-superusuário com essa permissão é o **Dono**, que é quem deve. O buraco real é
  maior — ver §3.5.

### 3.5 Novo — vinte e um achados, quatro deles P0

**P0, três provados executando:**

| # | Achado | Prova |
|---|---|---|
| 1 | **Ação de estado do Admin executada por GET**, sem permissão de modelo e sem CSRF, em **três** ocorrências. Com `SameSite=Lax`, um link clicado pelo gestor logado dispara a ação. E entre os handlers de diretiva existe um de **estorno**: **o Gerente, excluído do payman de propósito, reexecuta estorno pela tela de Diretivas.** | introspecção do registro de ações |
| 2 | **Cancelar pedido responde `200 {"ok": true}` e não cancela.** A ação irmã no mesmo arquivo trava e devolve 409 — é descuido, não decisão. | `STATUS 200 / ORDER STATUS APOS CANCEL: ready` |
| 3 | **B.I.: regressão viva no `main`.** Um commit de 21/08 removeu um atributo e esqueceu um arquivo; o chip de exemplo "Quebra de caixa por operador" levanta `AttributeError` → 500 sem `detail` → **tela em branco sem mensagem**. Passou porque o único teste do caminho roda em banco vazio. | `AttributeError` em runtime |
| 4 | **Compras: nada no sistema sabe se uma NF já entrou.** Sem chave de recibo em lugar nenhum; a projection nem lista recebimentos. Reescanear é o gesto natural de quem está em dúvida. Ironia: **recusar** a nota duas vezes é idempotente; **recebê-la** duas vezes duplica o estoque. | leitura da cadeia até o `Move.objects.create` |

**P1 selecionados:**

- **O backstage nunca devolve 401.** Só `SessionAuthentication` está configurada, e o DRF rebaixa para 403. Logo
  `isUnauthenticatedError` é inalcançável, o ramo "sua sessão expirou" do Hub é código morto, e **a receita de
  erro que G e D prescrevem em vários WPs não roda**. Fix de uma linha, beneficia as sete superfícies.
- **O token de login do cliente vaza para o ManyChat.** O despacho cunha um link pessoal por destinatário e o
  adapter grava todo scalar não-denylistado no perfil do assinante — e `action_url` **não está na denylist**.
  O token de sessão do cliente passa a viver em texto claro numa ferramenta SaaS de marketing. Uma linha.
- **A onda de hora habitual é entregue a ninguém e reportada como enviada.** O handler resolve destinatários
  por um dicionário de três chaves; a chave `nome@hora` cai no default vazio; "onda vazia não é falha" faz o
  status virar `sent`. A função que resolveria existe, é citada no docstring como se estivesse em uso, e
  **não tem um único chamador**.
- **Marcar item no KDS é um toggle com a leitura fora do lock.** Dois tablets na mesma bancada — a
  configuração normal de uma cozinha — e **o item desmarca sozinho**.
- **O painel público do KDS mostra telefone ou CPF inteiro** quando a comanda é numérica, porque a heurística
  "numérico é seguro" quebra acima de 8 dígitos. A função se chama `_public_comanda_code` e promete no
  docstring que protege. Medido.
- **Os relatórios de produção são inalcançáveis para toda persona não-superusuário** — e o teste de paridade
  fica verde por uma isenção cuja justificativa é factualmente falsa.
- **O guardrail de cobertura de encomendas nunca dispara no caminho real:** o filtro do guardrail e o de quem
  escreve não casam, e dá para reduzir o planejado abaixo do que já foi vendido, calado.
- **A pesagem mistura ficha congelada com rendimento vivo** — o hazard que o plano de domínio nomeia
  explicitamente. Os outros dois consumidores do snapshot fazem certo; só a pesagem erra.
- **Os dois parsers de dinheiro de Compras discordam em até 100×:** `12.50` mostra R$ 1.250,00 na tela e grava
  R$ 12,50 no banco. Zero testes, e o fix tem precedente pronto três funções abaixo.
- **Nada confere que o fornecedor escolhido é o emitente da NF**, embora o CNPJ esteja dentro da chave e o
  código já saiba extraí-lo. Fix de uma linha que fecha o núcleo do "P0 de payload" **sem draft nenhum**.
- **A série longa do B.I. soma o que não se soma:** ticket médio em janela de 1 ano mostra ~7× o valor real,
  formatado como reais. A docstring do agrupador manda somar "do jeito da métrica dela"; a página soma
  incondicionalmente.
- **A chave do 2FA do Admin está exposta**, e a tradução que "consertou" aquela tela é código morto — o que
  anula o step-up de 2FA que os dois WPs querem usar como controle.
- **Um typo num campo de dinheiro no Gestor vira 500**, porque o parser é chamado fora do `try` e a exceção é
  *irmã*, não subclasse. Ironia: 13 linhas abaixo o autor comenta que a tela "merece o 400, não um 500".

### 3.6 Verificado e limpo — o valor do negativo

Registro porque uma auditoria que só acumula achados perde credibilidade:

- **Nenhuma agregação do B.I. soma pedidos cancelados** (excluídos das vendas e das linhas, contados à parte,
  com teste).
- **Nenhuma PII de cliente nas projections do B.I.** — só contagens; e não existe export CSV.
- **Nenhum filtro de audiência que falha vira "todo mundo"** — o resolvedor parte de conjunto vazio e falha
  fechado em toda fonte, inclusive consentimento. Era a falha mais temida do Marketing, e não está lá.
- **Sem PII no SSE do caixa nem no de pedidos.**
- **O browser não consegue escolher o turno da venda**; sem parsing frouxo no intent da venda; **sem
  duplicação de venda por duplo clique** — a venda **já** é idempotente.
- **Duplo toque no finalizar da produção não credita a vitrine em dobro** — lock, marcadores, chave de
  idempotência e 409 já cobrem.
- **A contagem de insumos** — que ficou fora dos dois WPs — é o serviço **melhor construído** desta frente, e
  é a referência que o recebimento deveria seguir.

---

## 4. O `WP-00`: cinco coisas que não se resolvem app a app

Os dois auditaram por app. Cinco dos achados mais caros só ficam visíveis olhando os nove juntos. Detalhe em
[`WP-00-agente-c-transversal.md`](WP-00-agente-c-transversal.md).

**A. Idempotência — o contrato já existe e diz `"none"` em todo o dinheiro.** O Agente D propôs criar um
"manifest de actions" como infra nova. **Ele já existe e está em produção**, com campo `idempotency`,
`payload_schema` e `confirmation`; e o servidor já sabe honrar a chave, com claim e replay maduros, na venda.
Extraí as 25 ações do PDV: a venda declara `required`; **as oito mutações de dinheiro do caixa declaram
`none`** — sangria, suprimento, abertura, fechamento, estorno, acerto de conta, troco. E sete ações **nem
declaram o campo**: herdam `none` do default do dataclass. O default está invertido para dinheiro. O trabalho
não é criar; é honrar.

**B. Entrada — a casa tem dialeto de erro e não tem dialeto de entrada.** A saída é exemplar e documentada. A
entrada tem três dialetos: `bool()` cru em ~20 call sites — incluindo **a flag `force` que contorna a checagem
de insumos da produção**, que nenhum dos dois listou —, um `_as_bool` correto usado num único lugar, e dois
`_as_int` duplicados que engolem erro.

**C. Contrato gerado — os dois apps sem export são os dois com mais divergência FE↔BE.** Quatro apps têm
exportador de schema e teste de drift. **Hub e Marketing não têm** — e é exatamente onde G e D concentram os
achados de divergência. Não é coincidência: é a causa.

**D. Execução — o plano de nove frentes paralelas não sobrevive a este repositório.** Ver §5.

**E. O backstage nunca devolve 401** (§3.5). Mora aqui porque atinge as sete superfícies e é pré-requisito de
vários aceites de UX de erro.

---

## 5. Plano de execução

Duas medições feitas neste repositório, hoje, que mudam o **plano** e não o diagnóstico:

**`shopman/backstage/api/operations.py` tem 113 KB e concentra POS, Caixa, Pedidos, Produção e Operador.**
WP-02, WP-03 e WP-05 escrevem no mesmo arquivo. O CLAUDE.md abre dizendo que este repositório roda **várias
sessões ao mesmo tempo**, e a memória do projeto registra que *criss-cross derruba a fila de merge* — dois PRs
com bases diferentes chegam a `UNMERGEABLE` mostrando `CLEAN`. **O eixo de paralelização não pode ser o app.**
E **não** dividir o arquivo agora: rename em massa é hostil a merge, e faria exatamente o que se quer evitar.

**`test-backstage` tem 1.628 testes e já rodou em 20min04s.** O próprio workflow documenta o dia em que o step
tinha teto de 20 min, a suíte passou verde, o job caiu vermelho e a fila expulsou um PR inocente. Hoje há ~10
min de folga. Os nove WPs somados adicionam de 200 a 300 testes ao mesmo alvo. O modo de falha não é "teste
vermelho": é "suíte verde, check vermelho, PR inocente expulso" — o mais caro de diagnosticar, porque parece
flake.

### Ondas

| Onda | Conteúdo | Paralelizável |
|---|---|---|
| **0** | Shard do `test-backstage` · default de `Action.idempotency` · criar o parser canônico · a linha do 401 | sim, 4 branches — arquivos disjuntos |
| **1** | P0 de arquivos disjuntos: **KDS**, **Compras**, **Admin**, **B.I.**, **Hub** | sim, 5 branches |
| **2** | **Tudo que toca `operations.py`**: idempotência do caixa, terminal único, pedidos, produção, `force` estrito | **não — branch único** |
| **3** | Contratos gerados de Hub e Marketing + os achados FE↔BE que eles destravam | sim, 2 branches |
| **4** | **Permissões — PR único.** `setup_groups` usa `set`: o que sai da lista sai do banco. Seis WPs criam permissão; em seis PRs, o último a mergear revoga os cinco anteriores em silêncio no próximo deploy | **não — branch único** |
| **5** | UX de excelência | sim |

### Antes da onda 0: duas coisas para resolver

**1. Uma frente inteira está solta e não aparece em PR nenhum.** A worktree `confident-pasteur-6cf01c`, na
branch `claude/critical-fixes-notifications-67d7b2`, tem **85 arquivos não commitados** — incluindo
`backstage/api`, `backstage/admin`, `pos-nuxt`, e as **migrations 0037, 0038 e 0039** (o main está na 0035).
Seis destes nove WPs criam permissão, ou seja, migration nova, que **vai colidir** com essas. Trabalho solto
não aparece em PR, branch nem log — é uma armadilha já catalogada nesta casa. **Essa frente precisa ser
commitada, virar PR ou ser descartada antes de qualquer execução.**

**2. A pergunta 1 de §6.** Se o alpha tiver um segundo terminal, o P0 do PDV não é WP: é hotfix, hoje.

---

## 6. Perguntas ao dono — o que só você decide

Consolidadas dos nove WPs, na ordem em que mudam o trabalho:

1. **O alpha tem mais de um `Terminal` ativo?** Se tiver um com ref anterior a `pdv-main` em ordem alfabética,
   **o PDV já está quebrado em produção**. É uma consulta de um comando ao banco. *(WP-02)*
2. **Quem cancela um pedido já pronto?** Hoje o sistema não deixa ninguém, mas a tela oferece o botão e mente.
   Ou a transição passa a existir com permissão elevada — e aí é preciso decidir o que acontece com o estorno e
   com o iFood —, ou o botão some depois de pronto. **Decide o WP-03 inteiro.**
3. **O Gerente pode reexecutar uma diretiva de estorno?** O `setup_groups` diz por escrito que dinheiro é do
   Dono, e a tela de Diretivas dá ao Gerente o botão. Ou a tela ganha permissão, ou a regra tem uma exceção que
   ainda não está escrita. *(WP-09)*
4. **Agregados de venda podem sair para a API da Anthropic?** É o que acontece hoje no gerador de cenários.
   Nenhum dado de cliente, caixa ou operador; documentado em três lugares; desliga sozinho sem a chave. **Não
   é bug — é decisão sua.** *(WP-07)*
5. **O balcão usa o telefone do cliente como referência de comanda?** Se sim, o número aparece inteiro na TV do
   salão hoje (medido), e aquele achado vira P0. *(WP-04)*
6. **O disparo de campanha está ligado no alpha?** Muda a gravidade de metade do WP-08, e não dá para
   descobrir lendo código.
7. **Os relatórios de produção são do Gerente ou do Dono?** A tela existe, está gateada, e ninguém tem a
   permissão. **Bloqueia um fix de uma linha.** *(WP-05)*
8. **Os `packages/*/admin.py` mortos: migrar ou apagar?** 17 das 20 violações do gate estão em código que nunca
   renderiza. Apagar respeita "zero resíduos" e faz a fase 2 passar quase de graça — mas remove o fallback
   "roda sem Unfold" que os pacotes anunciam. *(WP-09)*
9. **Uma bancada pode dar "Finalizar" no ticket de outra?** Decide se aquilo é UX barata (identidade visual) ou
   RBAC caro (vínculo operador→estação). *(WP-04)*
10. **O custo de uma nota nova deve virar canônico sozinho?** Hoje vira. Proponho que não — mas quem decide
    preço de insumo é você. *(WP-06)*

Mais: fundo de troco negativo recusa ou aceita com aviso (WP-02); teto de plausibilidade do fechamento de
fornada (WP-05); forçar fechamento exige PIN ou só motivo escrito (WP-05); divergência de conversão trava a
entrada (WP-06); a quebra de caixa se atribui à gaveta ou à pessoa (WP-07); o alerta de faturamento chega ao
balconista (WP-07); o link pessoal pode ir em campanha (WP-08); o host da Central vira setting do Django
(WP-01); o e2e do Hub entra no CI ou é apagado (WP-01).

---

## 7. Método

Nove verificações independentes, uma por app, cada uma instruída a **não confiar** em nenhum dos dois agentes
anteriores. Cada evidência citada foi aberta e lida — a função inteira, não a linha —, com a linha **atual**
registrada quando havia mudado de lugar. Toda afirmação de comportamento foi rastreada até o ponto de decisão
real, incluindo decorators, `permission_classes` e middleware. Cada relatório procurou: testes que já cobrem o
caso, comentários e ADRs que documentam a decisão, e `git log` no arquivo para ver se o `main` já corrigiu.

Onde o achado dependia de comportamento e não de leitura, os agentes **rodaram o código** — pytest contra a
stack real, introspecção do registro de admin do Django, chamadas diretas às funções de parsing. As frases
"medido", "provado" e "verificado em runtime" ao longo dos WPs significam isso, e não uma leitura confiante.

Em paralelo, verifiquei eu mesmo a camada transversal: o `setup_groups` inteiro, o dataclass de ação e as 25
ações do PDV extraídas mecanicamente, o handler de erro canônico, a configuração de autenticação do DRF, os
exportadores de schema, a estrutura de `operations.py`, o workflow de CI e a contagem da suíte — mais o estado
de PRs abertos e de worktrees sujas, que é o que fundamenta §5.

**Onde não consegui confirmar, os WPs dizem isso** em vez de afirmar. Cada relatório de verificação continua
em `scratchpad/verify/` com a tabela evidência-a-evidência, para quem quiser conferir a conferência.
