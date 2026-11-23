# Resposta com prova: plano de partes, lastro, moldes e verificação

> **Estado:** vigente
> **Dono:** F6

Responde: como uma resposta é planejada em partes, com que lastro cada afirmação sai, em que
moldes, e como a saída é verificada. A fonte é o código: `conversational_commerce/reply/`.
A forma do registro (`ReplyPlan`) é do `01-contracts.md`.

Derivado de: v2 4.6 e o plano do framework, seção 3.6.

## 1. Lastro por afirmação

Toda resposta é um plano de partes; toda parte tem afirmações; toda afirmação tem um lastro,
que aponta uma chave da `Evidence`:

| Lastro | Aponta | Vale quando |
|---|---|---|
| `fact` | um fato do snapshot ou de uma porta | `Known` e dentro da validade (`Unknown` ou vencido não sustenta nada, N02) |
| `receipt` | um recibo do executor | existe; para afirmar um efeito, só `success` (seção 4) |
| `commitment` | um compromisso registrado | existe (promessa com dono e prazo) |
| `policy` | uma linha do perfil ou regra da casa | existe |
| `courtesy` | nada | saudação, agradecimento |

A `Evidence` também diz o **tipo** de cada lastro: `fact:<faceta>` (por exemplo
`fact:factual` e `fact:promisable`, as leituras da promessa do F3), `receipt:<status>` e
`commitment:<promise|case>`. Cada espaço do molde diz que tipos aceita.

## 2. Moldes (`templates.py`)

O molde é a frase da casa preenchida pelo código: prova por construção. Ele é a base sempre
gerada; redação por modelo não entra neste plano (corte). Regras do molde, conferidas quando
ele é criado:

- os espaços `{nome}` do texto são exatamente os declarados, e cada espaço aceita ao menos um
  tipo de lastro;
- **o texto fixo não tem dígito.** Preço, quantidade, horário, prazo e total só entram por
  espaço, vindos de lastro (N03);
- o valor de cada espaço é **bloco travado**: o reparo da verificação nunca o altera.

O pacote traz só moldes genéricos mínimos (`GENERIC_TEMPLATES`), para os testes e como
exemplo da forma. A voz e a língua da casa são do perfil e do adaptador. A formatação também
(dinheiro, data e quantidade, por `formatters`); a padrão é neutra (`engine/format.py`:
dinheiro, `done` para o estado do recibo, `items`, `fulfillment` e `conditions` dos termos).

Moldes de efeito com mais de um lastro: `change_cart.done` afirma o efeito pelo recibo (`{done}`,
o estado do recibo de sucesso) e mostra o carrinho pelos termos novos (`{items}`, `{total}`);
`commit_order.done` diz o pedido pelo recibo (`{order}` e `{track}`, que a casa formata como o
caminho dela para acompanhar) e o total pelo pedido lido depois do efeito (`{total}`);
`present_terms.confirm` mostra `{items}`, `{total}`, `{fulfillment}` e `{conditions}` do mesmo
fato dos termos. Com uma condição obrigatória ausente (`requirements.<carrinho>`, spec 03), a parte do
`present_terms` pergunta por ela: `present_terms.needs_<código>` (hoje, `needs_payment_method`, com as
opções do canal num espaço de LISTA lastreado no fato) ou o genérico `present_terms.needs`
(`{missing}`); os termos não se apresentam, e nenhuma pergunta de confirmação nasce. O molde da casa mantém esses espaços, como todos.

O adaptador entrega os moldes dele ao `Engine` em `house_templates`, pelo `template_id`. Cada molde
da casa troca a frase de um molde do pacote e mantém o movimento e os espaços (nome, lastro aceito
e faceta), porque é isso que a parte montada pelo movimento preenche. Um molde sem par no pacote,
ou com outro movimento ou outros espaços, reprova na criação do `Engine`. O que a casa não trocar
segue com o do pacote.

Um espaço é preenchido só quando o lastro vale **e** é de um tipo que o espaço aceita. Se não,
o espaço fica vazio e a verificação segura a mensagem. Espaço sem lastro informado é erro de
programação, nunca texto vazio que passa.

Cada parte composta registra o molde que a compôs (`RenderedPart.template_id`, e a lista em
`Composed.template_ids`). É só registro: não muda texto, lastro nem verificação. Serve ao
adaptador que decide ou mede por molde (por exemplo, ligar o motor só onde a casa tem a frase
dela).

## 3. Compor (`compose.py`)

`compose(specs, templates, evidence, rules, formatters, decision_id, record) -> Composed(plan,
verification, text)`. Cada `PartSpec(move, template_id, bindings)` diz o movimento, o molde e,
para cada espaço, o lastro (`backing`, `ref`). O molde tem de ser do mesmo movimento da
parte. O resultado é um `ReplyPlan` com:

- as partes e as afirmações;
- os blocos travados (`part<i>.<espaço>`);
- a verificação gravada;
- o texto, que é `None` quando a verificação segurou a mensagem.

## 4. Verificação de saída (`verify.py`)

`verify(partes, evidência, regras) -> pass | repair | hold`. Vale para **toda** mensagem,
inclusive a de molde e a redigida com marcadores (um `RenderedPart` montado por qualquer
caminho). *Repara* troca o trecho proibido e segue; *segura* não envia e leva o caso a uma
pessoa; tudo vira achado no `ReplyPlan`.

Regras genéricas do pacote, estruturais e sem língua nenhuma:

| Achado | Quando | Ação |
|---|---|---|
| `claim_without_backing`, `fact_not_in_evidence`, `receipt_not_in_evidence`, `commitment_not_in_evidence`, `policy_not_in_evidence` | o lastro apontado não está na evidência | segura (N01) |
| `fact_unknown`, `fact_expired` | o fato não vale | segura (N02) |
| `backing_kind_not_accepted` | o lastro existe, mas não é do tipo que o espaço aceita (o que se pode prometer não é unidade em mãos) | segura (K27) |
| `number_without_fact` | dígito no texto livre, fora de um bloco travado | segura (N03, K23) |
| `action_without_receipt` | parte de movimento que muda o negócio (`change_cart`, `set_fulfillment`, `commit_order`, `cancel_order`, `amend_order`, `grant_discount`) sem afirmação lastreada em recibo de **sucesso** | segura (K24) |

Efeito pendente não é efeito. A resposta a um recibo `pending` é uma parte `wait`, com o
prazo do compromisso de reconciliação, nunca a confirmação do pedido.

**Regras da casa** entram como dado: `PhraseRule(code, pattern, action, replacement?,
unless_backing?)`, por exemplo "ação afirmada no texto sem recibo de sucesso" com as palavras
da casa. Elas olham só o texto livre e não valem quando a parte tem o lastro de
`unless_backing`. O reparo não pode introduzir número. O pacote traz o mecanismo, nunca as
palavras de uma casa.

O verificador também erra e também é avaliado (v2 4.6). O que não pode errar (preço, total,
estado, efeito) não depende dele, porque nunca veio de texto livre: vem do lastro, por espaço.

## 4.1 Conferência antes do envio (`conference.py`)

`confer(...) -> Conference(send | fallback)` junta três perguntas antes de a resposta sair:
**aceitável** (a verificação de saída não segurou), **correta** (molde sobre lastro é correto
por construção; texto redigido precisa da palavra do juiz) e **útil** (o leitor de próximo
passo do adaptador achou o passo; um agradecimento não pede passo; o juiz não disse "fala de
outra coisa").

O juiz é a porta `ReplyJudge` (`judge(customer, reply, previous) -> JudgeVerdict(answers |
off_target | contradicts)`), opcional e falível. **À prova de falha:** juiz que cai é
`unavailable`, nunca "passou"; sem a palavra dele, a resposta por construção sai e a redigida
não. Qualquer reprovação leva à alternativa segura que o adaptador monta (o texto literal das
fontes, ou o "vou verificar" com dono e prazo), nunca ao erro. `conferred(..., mode="shadow")`
devolve sempre a candidata: é como a conferência se mede antes de valer.

## 4.2 Escada de conferência (`ladder.py`)

**Papéis separados, nunca intercambiáveis:** o conferente (`ReplyJudge`) é um decisor tipado
(escolha entre opções fechadas, com confiança) e não redige; o redator (`Drafter`) é um modelo
de linguagem e não se confere; só o redator sobe de degrau, e só quando o de baixo foi
reprovado, com teto. A configuração é por papel.

`climb(...) -> LadderResult` parte da resposta da casa já conferida. Reprovada, cada degrau
(`Drafter`, do barato ao capaz; com mais tentativas que degraus, o último se repete) reescreve
recebendo **só os fatos** da tentativa reprovada, os **passos permitidos** (o que a casa cumpre
no turno seguinte) e o **motivo** da reprovação; a reescrita é conferida de novo sem o benefício
da construção (precisa do juiz) e com `numbers_outside` (número fora dos fatos segura). Para
quando uma passa, quando as tentativas acabam (`LadderPolicy.max_attempts`, contando a da casa),
quando o custo chegaria ao teto do turno, ou quando o custo de um degrau é desconhecido (não se
sobe às cegas). Esgotou: a alternativa segura do adaptador. Degrau que cai é tentativa
reprovada. `LadderResult.rejections` é a pauta (os motivos somados); em `mode="shadow"`, `text`
é sempre a resposta da casa.

## 5. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/reply/test_reply.py`:

| Prova | Escopo |
|---|---|
| K23 preço ou estado sem fato: barrado no molde, segurado na redação, segurado com fato desconhecido | `adapter` |
| K24 ação afirmada sem recibo de sucesso: segurada, pelo movimento e pela regra da casa | `adapter` |
| K27 o que se pode prometer não sai como unidade em mãos | `adapter` |
| Conferência: juiz que cai não é "passou"; molde sai sem juiz, redigida não; sombra não muda o envio | núcleo |
| Escada: regera com o motivo e só os fatos; sobe de degrau; número fora dos fatos nunca sai; teto e custo desconhecido param; degrau que cai segue; sombra manda a da casa | núcleo |
| Fato vencido não sustenta; espaço sem lastro é erro; reparo não toca o bloco travado nem cria número | núcleo |

Os três K são `adapter`: o adaptador real repete com os moldes e as regras da casa dele.
