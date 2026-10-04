# OBS0310-Q: Concierge, intenções no plural

- **id:** OBS0310-Q
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-intencoes
- **PR:** #1449
- **início (UTC):** 2026-10-03
- **estudo:** `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`, bloco 1 (fatia F4, fase 1). Teste de campo:
  `docs/reports/concierge-teste-campo-20261003.md`.
- **pré-requisitos:** #1442 (regras da casa) e #1443 (memória), ambos no `main` antes do PR pronto.

## O que o Jev aceita (verificado)

Fonte: cliente no código (`concierge/intent_benchmark.py`, `JevContender`) e a referência da API
(<https://docs.typesafe.ai/api.md>, lida em 03/10/2026).

- `POST /v1/systemone` com um **mapa de perguntas** numa chamada só. Três tipos: `noul` (sim/não,
  devolve a probabilidade de "sim", 0 a 1), `choice` (UMA opção entre até 255, com `probabilities`
  e `confidence`) e `score` (escala de 2 a 10 níveis).
- O cliente da casa usa `noul`, **uma pergunta por intenção**: cada intenção ganha probabilidade
  própria, independente das outras. Então **sim, é multirrótulo**, e devolve confiança por rótulo.
- Não há extração (trecho, produto, quantidade): o Jev não decompõe a mensagem em partes com campos.
- Medido no alpha (sombra gravada, 175 mensagens, conexão direta, transação somente leitura): só 10
  mensagens têm duas intenções acima de 0,5, e quase todas são a MESMA parte com duas intenções
  correlatas ("Tem a mini focaccia?" dá produto 0,70 e pedido 0,53). Contar rótulos acima do corte
  não separa "duas partes" de "uma parte ambígua".
- Por isso o porteiro usa o Jev de dois jeitos: (1) a certeza da intenção (acima de 0,8, ou acima de
  0,5 e igual à regra local; produto e pedido juntos contam como uma parte) e (2) **uma pergunta
  `noul` a mais na mesma chamada**, `multiple_parts` ("a mensagem traz duas ou mais coisas
  diferentes?"), feita só com a chave ligada. Ainda não medida ao vivo: a chave do Jev mora só no
  alpha, e a sombra antiga não fazia essa pergunta.

## O que mudou

- `concierge/intents.py` (novo): porteiro (divisão local + notas do Jev), leitura com Claude Haiku 4.5
  (uma ida, `output_config.format` com esquema JSON, lista fechada de atos com `span`, `product`,
  `qty`; teto de 4 s, sem nova tentativa), validação (ato fora da lista vira `unknown`, produto que não
  está na fala some, a regra de equipe nunca sai), execução de cada ato pelo executor que já existe
  (busca pública do catálogo e das perguntas frequentes, status do pedido, aviso de alergia, frase fixa
  de R7) e composição de UMA mensagem na ordem do cliente, com uma pergunta só. Nada de laço de
  ferramentas do modelo.
- Parte sensível no turno (reclamação, cancelamento, pessoa, encomenda especial, alergia que as fontes
  não cobrem): a resposta leva as dúvidas simples, o pedido fica suspenso ("Sobre o pedido, a equipe
  fecha com você por aqui."), a conversa vai para a equipe e o cartão leva cada parte numerada com o
  que houve com ela. Só parte de equipe: o aviso de atendimento humano da casa, como sempre.
- `service.run_turn`: atrás da chave, a triagem que escala não cala mais as outras partes;
  `mark_handoff` aceita o aviso composto (`ack_text`), conferido pelas regras da casa com o recibo de
  handoff.
- `triage.py`: com a chave ligada, o Jev recebe a pergunta `multiple_parts` na mesma chamada; a
  triagem guarda `jev_scores` (todas as notas). Nada muda com a chave desligada.
- Régua: camada `intents`, etapa `intents` e `usage.intents` (as partes e quem as decidiu).
- Copy nova no registro (`CONCIERGE_PARTS_*`), editável no Admin.
- Chave: `CONCIERGE_INTENTS_PLURAL` = `off` (padrão) | `subjects` | `all`;
  `CONCIERGE_INTENTS_SUBSCRIBERS`; `CONCIERGE_INTENTS_MODEL` (padrão `claude-haiku-4-5`). O blueprint
  do alpha (`.do/app.alpha-subdomains.yaml`) declara `subjects` com o subscriber do dono; o app vivo
  só muda quando o spec for aplicado (com `make deploy-spec-drift` antes).
- Golden set: `expected.parts` nas mensagens reais com mais de uma parte, `alpha.jev_scores` (as 12
  notas da sombra) em 164 casos, e 12 casos `teste_de_campo` (Ailo, Deeliv e o estudo v2).
- `concierge_reply_eval --plural [--reader local|model]`: antes (uma intenção) e depois (partes).

## Placar (golden set, 221 casos; 147 passam pela leitura de partes, os outros são cortesia ou mídia)

`concierge_reply_eval --plural --reader model`, duas rodadas (a variação é do modelo):

| Medida | Antes (uma intenção) | Depois, rodada 1 | Depois, rodada 2 |
|---|---:|---:|---:|
| Mensagens com várias partes, todas achadas | 0/16 | 16/16 | 15/16 |
| Todas as partes achadas, todos os casos com intenção | 30/66 | 63/66 | 61/66 |
| Partes achadas | 45/85 | 82/85 | 80/85 |
| Equipe achada | 5/13 | 11/13 | 11/13 |
| Mandadas à equipe sem precisar | 3 | 4 | 4 |
| Uma parte lida como várias | | 3/50 | 2/50 |

Sem modelo (`--reader local`, a queda segura): 12/16 várias partes, 66/85 partes, equipe 5/13.

Custo e tempo da leitura (Haiku 4.5, medido pela régua): 70% das mensagens que passam pelo porteiro
vão à leitura no golden set; US$ 0,00134 por leitura, p50 1,1 s, p95 1,8 s; por mensagem, US$ 0,00095.
O cache de prompt está marcado, mas o Haiku 4.5 só guarda prefixo a partir de 4.096 tokens e o sistema
da leitura tem cerca de 700: não há leitura de cache.

## O que ficou de fora

- Atos de pedido que mudam a sacola (fase 2): o pedido é respondido com a disponibilidade; quem
  fecha é o site, como hoje.
- "Não sei, vou verificar" com cartão e prazo (F5): a parte sem fato diz que não tem a informação e
  oferece a equipe.
- Jev ao vivo com `multiple_parts`: só no alpha, depois de ligar a chave.
