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
(dinheiro, data e quantidade, por `formatters`); a padrão é neutra.

Um espaço é preenchido só quando o lastro vale **e** é de um tipo que o espaço aceita. Se não,
o espaço fica vazio e a verificação segura a mensagem. Espaço sem lastro informado é erro de
programação, nunca texto vazio que passa.

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
| `action_without_receipt` | parte de movimento que muda o negócio (`change_cart`, `commit_order`, `cancel_order`, `amend_order`, `grant_discount`) sem afirmação lastreada em recibo de **sucesso** | segura (K24) |

Efeito pendente não é efeito. A resposta a um recibo `pending` é uma parte `wait`, com o
prazo do compromisso de reconciliação, nunca a confirmação do pedido.

**Regras da casa** entram como dado: `PhraseRule(code, pattern, action, replacement?,
unless_backing?)`, por exemplo "ação afirmada no texto sem recibo de sucesso" com as palavras
da casa. Elas olham só o texto livre e não valem quando a parte tem o lastro de
`unless_backing`. O reparo não pode introduzir número. O pacote traz o mecanismo, nunca as
palavras de uma casa.

O verificador também erra e também é avaliado (v2 4.6). O que não pode errar (preço, total,
estado, efeito) não depende dele, porque nunca veio de texto livre: vem do lastro, por espaço.

## 5. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/reply/test_reply.py`:

| Prova | Escopo |
|---|---|
| K23 preço ou estado sem fato: barrado no molde, segurado na redação, segurado com fato desconhecido | `adapter` |
| K24 ação afirmada sem recibo de sucesso: segurada, pelo movimento e pela regra da casa | `adapter` |
| K27 o que se pode prometer não sai como unidade em mãos | `adapter` |
| Fato vencido não sustenta; espaço sem lastro é erro; reparo não toca o bloco travado nem cria número | núcleo |

Os três K são `adapter`: o adaptador real repete com os moldes e as regras da casa dele.
