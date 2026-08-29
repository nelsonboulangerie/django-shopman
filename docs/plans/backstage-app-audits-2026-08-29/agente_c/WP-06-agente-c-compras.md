# WP-06-agente-c — Compras

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** aba Compras + `shopman/backstage/{api,projections,services}/purchase*` + `packages/buyman`
**Objetivo:** uma nota entra uma vez só, no fornecedor que a emitiu, com o número que a tela mostrou — e o custo mestre só muda quando alguém decide mudá-lo.

## Diferenças vs. WP-06 (Agente G) e WP-06-agente-d

**Confirmado nos dois:** o recebimento não é idempotente; `confirm_receipt` lê fornecedor, linhas e chave do
payload; o custo mestre é reescrito e o fornecedor auto-promovido a preferido; a UI recalcula a reposição com
regra própria; o helper de aprovação é código morto.

**Agravado:** a promoção automática a custo preferido é **mais** grave do que o Agente D disse. `is_preferred`
decide qual fornecedor recebe o pedido de reposição e de onde sai o lead time — apesar de o docstring do
modelo e a ADR-023 ainda afirmarem que a tabela "não tem leitor". O código andou, a documentação não.

**Correção de citação:** as linhas de `api/purchase.py` citadas pelos **dois** agentes estão erradas. As
corretas são 44, 57, 74, 91, 108, 142, 193, 210.

**Refutados / descartados:**
- **"Aprender de-para fiscal do payload" como P0 (G e D).** É **decisão documentada**:
  `docs/reference/data-schemas.md:1423-1451` especifica o contrato, quem escreve, quem lê, o tratamento de
  aliases legados e a política de overwrite com aviso estruturado — e há três testes cobrindo aprendizado,
  substituição divergente e não-aprendizado sem contexto de NF. É uma decisão **correta** para o caso que ela
  resolve. O que sobra de risco real é outro achado, com fix de uma linha (P1-2).
- **`ReceiptDraft` como pré-requisito de tudo (G e D).** Não descarto a ideia; descarto a **prioridade**.
  Persistir o draft é peça grande (modelo, ciclo de vida, expiração, modo manual, deltas de conferência,
  migração), e as três consequências que os dois usaram para justificá-la se fecham mais barato: a duplicação
  (P0-1), o fornecedor errado (P1-2) e o mapa fiscal envenenado (também P1-2). O que o draft ainda resolveria
  — "confirmar linha que não veio da nota" — é hoje o gesto **legítimo** de um app cujo único usuário é o
  Gerente e que precisa aceitar entrada sem NF.
- **"Pôr as entidades de recebimento no backstage" (D).** Refutado: o `BUYMAN-PROCUREMENT-PLAN.md:72-75` já
  declara `PurchaseReceipt` append-only como **Fase 3 do buyman**. O dono existe e está escrito.
- **"Separar permissões scan/receive/cost/conversion/approve/send" agora (G e D).** `operate_purchase` é
  concedida **só ao Gerente**; `audit_stock`, só ao Dono. **Não existe hoje persona de conferente com acesso
  a Compras** — a granularidade seria preparação para um usuário que não existe. E a view de conversão tem
  vinte linhas de docstring justificando por que declarar conversão é permissão de operador de compras e não
  de gestor. Reabrir isso exige o gesto do dono, não uma auditoria. O achado de "permissão única" dos dois
  vale menos do que ambos disseram.
- **"Conversão divergente bloqueia até justificar" (G e D).** Já existe aviso de ordem de grandeza com
  tolerância igual nos dois lados, e a ADR-024 já **recusa** entrada sem fator declarado. Transformar aviso em
  bloqueio é decisão de produto — trava a entrada com o entregador esperando, que é exatamente o impasse que
  `declare_conversion` foi criada para desfazer. Vira pergunta 2.
- **Aceite "sem `approve_purchase` não envia compra acima da política" (G).** Inescrevível: nem a permissão
  nem o limite existem. O Agente D já apontou; confirmo.
- **"`_purchase_request_snapshot` roda a projection inteira" (D).** Confirmado e é desperdício, mas acontece
  uma vez por clique, num app de um usuário, num catálogo de dezenas de insumos. Nota, não achado.

**Novos:** os dois parsers de dinheiro discordam em até 100×; nada confere que o fornecedor é o emitente da
NF; o scan grava CNPJ em fornecedor **existente**; payload não-finito vira 500; a validação da chave diverge
entre tela e servidor; e a contagem de insumos — que ficou fora dos dois WPs — é o **melhor** serviço da
frente e a referência que o recebimento deveria seguir.

## Pré-requisitos

- **WP-00 Bloco B** (parser de entrada): P2-2 consome o helper de lá.
- `PurchaseReceipt` é entidade do **buyman** (Fase 3 do plano dele) — precisa da assinatura do dono do pacote.

## Achados priorizados

### P0-1 — Nada no sistema sabe se uma NF já entrou

**Mecanismo.** O operador escaneia a NF, confere as linhas, clica "Confirmar entrada". `confirm_receipt` abre
a transação e, por linha, chama `stock.receive`, que faz `Move.objects.create` **incondicional**. Não há chave
de recibo em lugar nenhum: nem no metadata do movimento (que carrega a chave de acesso, mas ninguém consulta),
nem numa tabela própria. Se a resposta se perder — 504 no proxy, aba fechada, tablet sem rede na volta — o
operador clica de novo e o estoque dobra.

E o caminho mais provável no chão nem é esse: **três horas depois, ninguém consegue responder "essa nota já
entrou?"**. A projection não expõe nenhuma lista de recebimentos; o único dado é a data da última entrada por
fornecedor. Reescanear a mesma nota é o gesto natural de quem está em dúvida, e ele duplica tudo em silêncio.

A guarda que existe é só de tela: o segundo clique é bloqueado enquanto o primeiro está em voo. Nenhuma delas
sobrevive a um retry ou a um segundo dispositivo.

**Ironia útil como prova:** `reject_receipt` **é** idempotente — usa dedupe com chave derivada de fornecedor,
motivo e linhas. **Recusar** a nota duas vezes não duplica nada; **recebê-la** duas vezes duplica o estoque.

**Fix mínimo.** `PurchaseReceipt` append-only em `packages/buyman` (dono já declarado), com constraint única
sobre a chave de acesso quando ela não é vazia; `confirm_receipt` cria o recibo **antes** do loop, na mesma
transação; violação vira 409 com a data e o operador da primeira entrada. Modo manual usa um `source_ref`
estável — hoje ele mistura `timezone.now()` e portanto é diferente a cada chamada; trocar por hash do
conteúdo.

### P0-2 — O recebimento reescreve o custo mestre sem gesto e sem trilha

**Mecanismo.** Ao confirmar, para cada linha com custo maior que zero, a atualização de custo faz três coisas
cegas:

1. sobrescreve a **conversão** do custo existente, inclusive para `None` — pode **zerar** a unidade de compra;
2. sobrescreve o **custo canônico** do par fornecedor/insumo;
3. se nenhum custo preferido existe para o insumo, **esta entrada vira o custo preferido**.

E `is_preferred` não é inerte: **decide qual fornecedor recebe o pedido de reposição** e de onde sai o lead
time.

No chão: uma compra de emergência num fornecedor caro, feita às cinco da manhã, silenciosamente reprecifica o
insumo, apaga a unidade de compra anterior e pode eleger aquele fornecedor como o canônico. Nada aparece na
tela, nada fica no histórico — a tabela não tem trilha, e o único log de custo está no caminho **manual**, não
neste.

**Fix mínimo — duas linhas e um teste:** desligar a auto-promoção (`prefer_if_missing=False`) — a promoção a
canônico volta a ser gesto explícito, e a tela **já tem** esse gesto; e não apagar conversão existente quando
a linha não declara uma. A trilha append-only (`SupplierCostObservation`) é o fix **correto**, mas é maior; as
duas linhas param a promoção e o apagamento hoje.

### P1-1 — Os dois parsers de dinheiro discordam em até 100×

Há dois parsers, com regras diferentes. O TS remove **todos** os pontos e depois troca a primeira vírgula por
ponto. O Python trata ponto como milhar **só se** houver vírgula; senão, um ponto com até duas casas vale como
decimal.

O operador digita `12.50` no campo de custo da linha — input livre, `inputmode="decimal"`:

| | resultado |
|---|---|
| A tela exibe | **R$ 1.250,00** |
| O servidor grava no movimento e no custo | **R$ 12,50** |

Com `12.5` a divergência é 10×. Nenhum dos dois lados avisa, e **nenhum teste cobre o parser de dinheiro do
TS** (há 30 testes no arquivo, zero sobre dinheiro digitado). O caminho pré-preenchido pela NF está a salvo —
o buraco é a digitação, que é exatamente o modo manual "sem NF".

Pior: um custo **impossível de parsear** vira `0` em silêncio nos dois lados, e o confirm simplesmente pula o
custo. Digitar `12,50 (com frete)` grava a entrada com custo zero e não diz nada. **Isso é falhar aberto em
dinheiro** — contra a régua explícita da casa.

**Fix mínimo — três linhas, com precedente pronto no mesmo arquivo:** a regra "a vírgula decide a notação" já
está implementada três funções abaixo, no parser de quantidade. Alinhar o TS a ela. E, no servidor, distinguir
"vazio" de "não entendi": levantar erro de campo quando o texto não é vazio e não parseia, em vez de devolver
zero.

### P1-2 — Nada confere que o fornecedor escolhido é o emitente da NF

**Este é o núcleo defensável do "P0 de payload" que G e D descreveram — e não precisa de draft nenhum para ser
fechado.**

O confirm valida a chave de acesso e valida que o fornecedor existe e está ativo — mas **nunca cruza os
dois**. Os 14 dígitos do CNPJ do emitente estão dentro da própria chave, e o código **já sabe disso**: existe
uma função que extrai exatamente esses dígitos, usada para outra coisa.

No chão: o scan preenche o fornecedor certo, mas o que volta no confirm é o do dropdown da tela, que o
operador pode ter trocado sem perceber ao navegar entre abas. O resultado é movimento com fornecedor errado,
custo no fornecedor errado, e — o pior — o de-para fiscal aprendido **no fornecedor errado**, envenenando o
scan de todas as notas futuras daquele fornecedor. O overwrite loga um aviso; o aprendizado inicial no
fornecedor errado não loga nada.

**Fix mínimo — uma linha:** no modo NF, comparar o documento do fornecedor com os dígitos do emitente na
chave, e recusar com erro de campo.

### P1-3 — O número que a tela sugere não é o número que o servidor despacha

A aba "Comprar" monta a lista com regra própria (filtro e alvo calculados no cliente). O backend calcula o
alvo com a política do Admin — lead time, período de revisão, segurança — e expõe o resultado num campo que a
UI **recebe e nunca lê**. No envio, o snapshot usa o número do **backend**.

Duas consequências: o fornecedor recebe uma quantidade diferente da que o operador aprovou; e quando o backend
chega a zero, o clique morre com *"Este insumo não tem reposição sugerida agora"* — mensagem que contradiz a
própria tela que acabou de listá-lo como urgente.

Há ainda um **terceiro** número na mesma tela: a lista de alertas usa a régua do servidor. Ou seja, alerta,
lista de compra e envio usam três réguas diferentes.

**Fix mínimo:** a lista passa a ler o campo que já chega, e filtra por ele. O custo estimado continua sendo
custo preferido vezes quantidade.

### P1-4 — `scan_invoice` escreve em cadastro mestre antes de qualquer confirmação

O scan ou **cria** um fornecedor, ou **grava CNPJ e telefone num fornecedor existente** — essa segunda metade
o Agente D não viu. Nada disso está em transação, e nada exige confirmação: basta bipar o QR. Escanear a nota
errada deixa cadastro atrás.

A adoção por nome tem guardas boas (só documento vazio, só um candidato) e é decisão documentada — mas
continua sendo escrita de dado mestre num gesto que o operador entende como "ler".

**Fix mínimo:** não criar nem adotar no scan. Devolver o emissor no draft (ele já viaja) e criar/adotar dentro
do confirm, na transação que já existe — o fornecedor nasce junto com a entrada que o justifica. Se o gesto
precisar ficar no scan, expor na projection que houve criação/adoção, para a tela poder dizer "cadastrei este
fornecedor da nota" com um desfazer.

### P2-1 — A validação da chave da NF diverge entre tela e servidor

O servidor confere o dígito verificador módulo-11. A tela só procura 44 dígitos e chama isso de válido — e o
gate de confirmação usa a validação **fraca**. Com um dígito trocado, a tela libera "Confirmar", o servidor
recusa, e a linha só volta a ser digitável depois do erro.

**Fix:** portar o cálculo para o TS (é determinístico, ~8 linhas, e não é regra de negócio — é aritmética do
documento) ou, mais barato, só liberar a confirmação depois de o scan ter respondido com sucesso para aquela
chave.

### P2-2 — Payload não-finito vira 500

Três valores chegam ao 500 (verificado executando os parsers): quantidade `"NaN"`, custo `"Infinity"` e
quantidade `"Infinity"` — este último passa do gate de positividade e estoura só no banco. A mesma classe
existe no parser da contagem.

E há uma **terceira** convenção decimal na frente: o parser genérico só troca vírgula por ponto, então o fator
de conversão `"1.250"` (mil duzentos e cinquenta, escrito à brasileira) vira `1,25` em silêncio — num número
que multiplica estoque e dinheiro.

**Fix:** recusar não-finitos nos parsers, e envolver as views de escrita para que erro inesperado devolva o
dialeto canônico em vez da página de erro do DRF.

### P2-3 — `approved` é estado inalcançável com endpoint vivo

A view e o serviço funcionam; o helper do frontend existe e **não é chamado de lugar nenhum**; o envio vai
direto de revisão para enviado sem consultar o estado. Recalibrado de P1 para P2: a rota exige a mesma
permissão do resto (não é escalada) e o efeito é só um carimbo. É dívida de coerência, não de risco.

**Fix — escolher um:** apagar view, rota, helper, o valor do enum, o tipo TS e o badge; **ou** dar call site
ao helper e fazer o envio recusar o que não foi aprovado. **Não** criar `approve_purchase` com limite de
gasto agora — é feature nova (pergunta 3).

### P2-4 — O contrato tem campos que ninguém lê

O campo de quantidade sugerida chega ao TS e **não é lido por nada** — é justamente o que fecharia o P1-3. A
cobertura em dias é calculada só no cliente e é o eixo de ordenação e filtro, sem contraparte no servidor. E a
projection não expõe **nada** sobre recebimentos realizados, que é a raiz do P0-1 pelo lado da tela.

## A contagem de insumos é a referência que falta

Nenhum dos dois WPs menciona a aba de contagem — e ela é o **melhor** serviço desta frente:

- idempotente por construção (converge ao contado; um segundo envio dá delta zero e não lança nada);
- recusa SKU duplicado;
- exige motivo para divergência;
- **reconfere a divergência no momento de aplicar**, não no de carregar;
- escreve sempre pelo caminho canônico do estoque.

É exatamente o padrão que o P0-1 e o P0-2 deveriam seguir. Vale lê-la antes de escrever o recibo.

⚠️ Nota de fronteira: ela importa um privado de `services/purchase.py`. Quem mexer nesse arquivo precisa saber.

## RBAC / `setup_groups`

**Nenhuma permissão nova.** A matriz atual é coerente com o que as views exigem, e não há persona a separar
hoje. Se a pergunta 1 revelar um conferente que não é o Gerente, aí sim — e nesse caso vai no **PR único de
permissões da onda 4**.

## Testes

1. Confirmar a **mesma chave de NF** duas vezes: a segunda devolve 409 nomeando data e operador da primeira, e
   **nenhum** movimento novo é criado.
2. Modo manual: dois confirms com o mesmo conteúdo produzem um recibo só.
3. Confirmar entrada **não** promove o fornecedor a preferido quando não havia preferido.
4. Confirmar entrada com linha sem conversão **não** apaga a conversão já cadastrada.
5. `12.50` digitado produz o **mesmo** valor na tela e no banco. Idem `12,50`, `1.250,00`, `12.5`.
6. Custo impossível de parsear devolve 400 com `field`, em vez de gravar zero.
7. Fornecedor diferente do emitente da chave devolve 400 com `field: supplierRef`; e o de-para fiscal **não**
   é aprendido.
8. A lista da aba "Comprar" mostra exatamente a quantidade que o envio despacha.
9. `"NaN"` e `"Infinity"` em quantidade e custo devolvem 400, nunca 500.
10. Chave com dígito verificador errado é bloqueada **antes** do confirm.
11. Scan não cria nem adota fornecedor; o confirm cria.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Observação |
|---|---|---|
| `shopman/backstage/services/purchase.py` | MÉDIO | arquivo central deste WP; `purchase_count.py` importa um privado dele |
| `shopman/backstage/api/purchase.py` | BAIXO | linhas reais: 44, 57, 74, 91, 108, 142, 193, 210 |
| `shopman/backstage/projections/purchase.py` | BAIXO | — |
| `packages/buyman/**` (modelo + migration) | MÉDIO | **dono do pacote precisa assinar**; migration nova → conferir colisão de numeração |
| `surfaces/*/presentation/purchase.ts`, `usePurchaseDesk.ts` | BAIXO | — |
| `shopman/shop/checks.py` | MÉDIO | só se entrar setting nova — WP-01 toca o mesmo dict |

⚠️ **Migration nova no buyman:** antes de abrir PR, conferir numeração duplicada
(`ls packages/buyman/**/migrations | sed 's/_.*//' | sort | uniq -d`). E ver o WP-00 Bloco D3 — há migrations
0037-0039 não commitadas numa worktree paralela.

## Fora de escopo

`ReceiptDraft` persistido (fase posterior). Permissões finas de Compras (não há persona). Bloqueio por
conversão divergente (decisão de produto). Validação fiscal no import de catálogo. Otimização do snapshot de
pedido.

## Perguntas para o dono do produto

1. **Existe, ou vai existir, um conferente de recebimento que não é o Gerente?** Hoje `operate_purchase` é só
   dele. A resposta decide se as permissões finas que G e D pediram têm destinatário — ou se são preparação
   para um usuário que não existe.
2. **Divergência de conversão deve travar a entrada?** Hoje avisa. Travar significa o entregador esperando na
   porta — que é o impasse que a declaração de conversão foi criada para desfazer.
3. **O custo de uma nota nova deve virar canônico sozinho?** Hoje vira, quando não há preferido. Proponho que
   não — que a promoção seja gesto explícito, que a tela já tem. Mas quem decide preço de insumo é você.

## Prompt para agente executor

~~~text
Execute WP-06-agente-c (Compras).

⚠️ PurchaseReceipt e entidade do packages/buyman (Fase 3 do BUYMAN-PROCUREMENT-PLAN),
nao do backstage. Precisa da assinatura do dono do pacote. Migration nova: confira
numeracao duplicada ANTES do PR.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-06-agente-c-compras.md
- docs/plans/BUYMAN-PROCUREMENT-PLAN.md:72-75 (o dono ja declarado)
- docs/reference/data-schemas.md:1423-1451 (o de-para fiscal e DECISAO, nao bug)
- shopman/backstage/services/purchase_count.py — LEIA PRIMEIRO. E a referencia de
  idempotencia que o recebimento deveria seguir.
- shopman/backstage/services/purchase.py:112-200 (confirm_receipt), :254-263
  (reject_receipt — o padrao CERTO), :685-702, :856-871, :1064-1106, :1178-1182
- surfaces/*/app/presentation/purchase.ts:38-47 e :457-465 (o parser CERTO, 3 funcoes abaixo)
- surfaces/*/app/composables/usePurchaseDesk.ts:562-575

Fases:
1. P1-2: uma linha — fornecedor tem que ser o emitente. Fecha o nucleo do "P0 de payload"
   sem draft nenhum. Teste 7.
2. P1-1: alinhar o parser TS ao Python (copie a regra de parseQtyInput) e fazer o servidor
   recusar custo impossivel em vez de gravar zero. Testes 5 e 6.
3. P0-2: prefer_if_missing=False + nao apagar conversao existente. Testes 3 e 4.
4. P0-1: PurchaseReceipt no buyman + constraint + 409. Testes 1 e 2.
5. P1-3: a lista le suggestedQty do servidor. Teste 8.
6. P2-2 (nao-finitos), P2-1 (digito verificador), P1-4 (scan nao cadastra), P2-3.

NAO construa ReceiptDraft. NAO crie permissao nova de Compras. NAO transforme o aviso de
conversao em bloqueio. NAO trate o aprendizado de de-para como bug — e decisao documentada.
~~~
