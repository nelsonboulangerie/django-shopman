# Placar da Concierge: linha de base

A régua que os pacotes seguintes da Concierge usam para provar que nada piorou
(WP-02 de `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`). São os três placares gratuitos:
regra local, sem rede, sem custo. Medidos sobre o `main` em `d48286ec4`, com
`config.settings_test` e o conjunto `shopman/storefront/concierge/golden_set.json`
sem mudança de rótulo.

Para comparar, rode o mesmo comando com `--report <arquivo>` e confronte com a
seção correspondente.

## Os números contra os de 16/11 (seção 1.1 do plano)

| Medida | 16/11 no plano | Esta linha de base |
|---|---|---|
| Triagem: destino certo | 210/221 | 210/221 |
| Triagem: equipe e outra mesa achadas | 5/13 | 5/13 |
| Triagem: à equipe sem precisar | 3 | 3 |
| Regras da casa: exemplos da tabela | 88/88 | 88/88 |
| Memória: total certo | 47/47 | 47/47 |
| Memória: "sim" na pergunta errada | 0 | 0 |
| Plural: partes achadas | 67/85 | 67/85 |
| Plural: várias partes, todas achadas | 12/16 | 12/16 |
| Plural: equipe achada | 6/13 | 6/13 |
| Plural: equipe sem precisar | 4 | 4 |
| Plural: uma parte lida como várias | 7/50 | 7/50 |

Nenhuma diferença.

Estes três placares são determinísticos: `--repeat 2` deu o mesmo número em
todas as rodadas (por exemplo, destino certo 210/221 em cada rodada e em todas
as 2). A repetição serve ao placar com rede (`--paid`), em que o modelo pode
mudar de resposta de uma rodada para a outra.

## Rodada com modelo

Não medida: não há chave de IA no alpha e chamada paga pede a palavra do dono.
O último número com o modelo de leitura é de 03/10 (OBS0310-Q, duas rodadas):
partes 82/85 e 80/85, várias partes 16/16 e 15/16, equipe 11/13. Quando houver
autorização, o comando é:

```text
manage.py concierge_reply_eval --plural --reader model --paid --budget-usd 1 --repeat 3 --report <arquivo>
```

Sem `--paid`, ele sai com erro antes de criar qualquer cliente:

```text
CommandError: --reader model chama o provedor e custa dinheiro: rode de novo com --paid (e o teto --budget-usd, default US$ 1) para autorizar o gasto. Nenhuma chamada foi feita.
```

## Triagem com a regra local (221 casos)

- Comando: `manage.py concierge_reply_eval`
- Medido em: 16/11/2026 11:58

```text
═══ Placar da Concierge (golden set) ═══
221 mensagens reais (87 cortesia, 17 link ou mídia, 47 depende do contexto, 54 intenção clara, 3 conversa solta, 9 equipe, 4 outra mesa). Triagem por: rules.

Destino certo: 210/221 (95%) · equipe e outra mesa achadas: 5/13 · mandadas à equipe sem precisar: 3
Intenção certa: 50/85 (59%) das que têm intenção

Quem responde, hoje × arquitetura alvo:
  cortesia (87): hoje vai para cortesia 74, agente com o modelo 13
  link ou mídia (17): hoje vai para agente com o modelo 17
  depende do contexto (47): hoje vai para agente com o modelo 47
  intenção clara (54): hoje vai para agente com o modelo 51, equipe 3
  conversa solta (3): hoje vai para agente com o modelo 3
  equipe (9): hoje vai para agente com o modelo 6, equipe 3
  outra mesa (4): hoje vai para outra mesa 2, agente com o modelo 2
Chegam ao modelo de resposta: hoje 139 (63%); na arquitetura alvo 57 (26%).

Triagem: US$ 0.000000 por mensagem (US$ 0.0000 no conjunto) · tempo p50 3 ms, p95 7 ms
Resposta do alpha, medida na hora (42 casos respondidos, inclui 1 s de espera proposital):
  0 ferramenta(s): 13 casos, p50 5.6 s, máximo 7.8 s
  1 ferramenta(s): 20 casos, p50 7.6 s, máximo 12.0 s
  2 ou mais ferramenta(s): 9 casos, p50 16.4 s, máximo 43.5 s

Erros (39; os primeiros 15):
  msg-53 "quero que me avise quando estiver disponivel, pode ser?": esperado answer/product_question, saiu answer/order (rules)
  msg-77 "você não tem sentimentos! me senti ofendido…": esperado team/complaint, saiu answer/product_question (rules)
  msg-100 "sim, já tinha confirmado! vai logo que estou com pressa!": esperado answer/order, saiu answer/product_question (rules)
  msg-109 "hmm, sera que posso pagar com cartão? o [dado financeiro ou ": esperado team/sem intenção, saiu answer/ (default)
  msg-113 "o link de pagamento por [dado financeiro ou segredo omitido]": esperado team/complaint, saiu team/human (rules)
  msg-119 "#menu [código omitido]": esperado answer/product_question, saiu answer/ (default)
  msg-149 "e baguete?": esperado answer/product_question, saiu answer/ (default)
  msg-179 "oi tudo bem? porque demorou tanto pra responder?": esperado team/complaint, saiu answer/ (default)
  msg-193 "porque me ofereceu Fendu que está indisponível, criatura?": esperado team/complaint, saiu answer/ (default)
  msg-205 "Bom dia tudo bem? Vai ter croissant hoje?": esperado answer/product_question, saiu answer/ (default)
  msg-534 "Dois pães italianos pra pegar à tarde": esperado answer/order, saiu answer/ (default)
  msg-542 "Porque não sei .. eu sempre pego o de brioche e este de hamb": esperado team/complaint, saiu answer/ (default)
  msg-545 "O valor para pagar o pão de sábado": esperado answer/order_status, saiu answer/ (default)
  msg-548 "Para entregar": esperado answer/hours_delivery, saiu answer/ (default)
  msg-557 "olá, bom dia. Gostaria de saber se vcs estarão abertos no pr": esperado answer/hours_delivery, saiu answer/order (rules)

Regras da casa (tabela v1, 14 regras):
  Exemplos da tabela: 88/88 certos
  Respostas da casa gravadas no conjunto (texto do modelo, alpha 04 a 12/09): 36
    Antes: 27/36 quebram alguma regra · por regra: R1 21, R5 11, R6 3, R12 15
    Depois: 27 seguradas (equipe), 0 consertadas, 9 sem mudança · violações no que sai: 0
  Entrada: falas do conjunto com frase fixa: R7 1, R8 1
```

## Memória da conversa (47 casos)

- Comando: `manage.py concierge_reply_eval --memory`
- Medido em: 16/11/2026 11:59

```text
═══ Placar da memória da Concierge (golden set) ═══
Memória da conversa: 47 mensagens que dependem do contexto (rótulos em golden_memory.json).

  esperado                           casos   antes  depois
  resolvida pelo estado                  6       0       6
  'sim' que chama a equipe               1       0       1
  pergunta em vez de supor               5       0       5
  se basta (memória não mexe)           35      35      35
  total certo                           47      35      47

Precisam de memória (12): resolvidas certo ou com pergunta curta, antes 0, depois 12.
Com referente no estado (7): resolvidas sem pergunta, antes 0, depois 7.
'Sim' aplicado à pergunta errada: 0. Suposição onde cabia pergunta: 0.
```

## Intenções no plural com a divisão local (147 casos)

- Comando: `manage.py concierge_reply_eval --plural --reader local`
- Medido em: 16/11/2026 12:01

```text
═══ Intenções no plural (golden set) ═══
147 casos (16 com mais de uma parte). Leitura: local. Porteiro: regra local e, nos casos observados, as notas do Jev gravadas em sombra.

                                    antes (uma intenção)    depois (partes)
  Todas as partes achadas, várias   0/16                    12/16
  Todas as partes achadas, todos    30/66                   48/66
  Partes achadas                    45/85                   67/85
  Equipe achada                     5/13                    6/13
  Equipe sem precisar               3                       4
  Uma parte lida como várias                                7/50

Quem decidiu as partes: gate 43, local 104 · motivo do porteiro: jev_unsure 63, jev_certain 24, local_multiple 21, rules_single 19, rules_unsure 17, jev_two_intents 3
Por mensagem (todas): US$ 0.000000 de modelo · porteiro + leitura p50 0 ms, p95 1 ms
Equipe perdida: msg-77 "você não tem sentimentos! me senti ofendido…" (product_question + unknown); msg-109 "hmm, sera que posso pagar com cartão? o [dado fina" (unknown + unknown); msg-179 "oi tudo bem? porque demorou tanto pra responder?" (greet + unknown); msg-193 "porque me ofereceu Fendu que está indisponível, cr" (unknown); msg-596 "[link omitido]" (unknown); msg-646 "Olá boa tarde, tudo bem ? Me chamo [nome] e tenho " (greet + order); campo-11 "Quero falar com uma pessoa, mas antes: vocês abrem" (order + hours_delivery)
Equipe sem precisar: msg-696 "Cancela" (cancel_order); campo-1 "então quero 2 croissants. até que horas vocês fica" (order + hours_delivery + product_question + allergy); campo-2 "você não respondeu: até que horas vocês abrem? e o" (hours_delivery + product_question + allergy); campo-5 "o pão de queijo tem lactose? meu filho tem alergia" (allergy)

Partes perdidas (18; as primeiras 15):
  msg-53 "quero que me avise quando estiver disponivel, pode ser?": esperado product_question, saiu order (gate)
  msg-59 "seguimos. é para entrega, ok. qual a taxa?": esperado order|hours_delivery + hours_delivery, saiu unknown + hours_delivery + product_question (local)
  msg-77 "você não tem sentimentos! me senti ofendido…": esperado complaint, saiu product_question + unknown (local)
  msg-113 "o link de pagamento por [dado financeiro ou segredo omitido], ok. avis": esperado complaint|human + complaint|human|order_status, saiu unknown + human + unknown + unknown + unknown (local)
  msg-119 "#menu [código omitido]": esperado product_question, saiu unknown (local)
  msg-179 "oi tudo bem? porque demorou tanto pra responder?": esperado complaint, saiu greet + unknown (local)
  msg-193 "porque me ofereceu Fendu que está indisponível, criatura?": esperado complaint, saiu unknown (local)
  msg-205 "Bom dia tudo bem? Vai ter croissant hoje?": esperado product_question, saiu greet + unknown (local)
  msg-545 "O valor para pagar o pão de sábado": esperado order_status|order, saiu unknown (local)
  msg-557 "olá, bom dia. Gostaria de saber se vcs estarão abertos no próximo domi": esperado hours_delivery, saiu greet + order (local)
  msg-596 "[link omitido]": esperado job, saiu unknown (local)
  msg-608 "Por favor , preciso que entreguem em casa, tudo bem?": esperado hours_delivery|order, saiu unknown (local)
  msg-610 "Amanhã vai ter pão de forma?": esperado product_question, saiu unknown (local)
  msg-646 "Olá boa tarde, tudo bem ? Me chamo [nome] e tenho uma empresa que forn": esperado supplier_offer, saiu greet + order (local)
  msg-665 "Ainda é possível fazer pedidos?": esperado order|hours_delivery, saiu unknown (local)
```
