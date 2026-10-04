# OBS0310-R: intenções no plural ligadas para a coorte, sem spec

- **id:** OBS0310-R
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-intencoes-coorte
- **PR:** (preencher)
- **início (UTC):** 2026-10-03
- **pré-requisito:** #1449 (OBS0310-Q, intenções no plural) no `main`, desligado atrás de
  `CONCIERGE_INTENTS_PLURAL`, que só ligaria aplicando o spec do alpha. Aplicar o spec é proibido
  para nós (drift [FAIL] de propósito: `SHOPMAN_COURIER_ADAPTER` só no painel). O dono aprovou ligar
  primeiro só para ele.

## Como ficou ligado (sem env e sem spec)

- A Concierge em `assist` só atende a coorte fechada da connection (`allowed_subjects`, hoje o
  dono); quem está fora só é observado. `intents.enabled_for(binding)` agora pergunta exatamente
  isso: modo `assist` e `service.is_allowed(binding)`. Fora da coorte, nada muda.
- `CONCIERGE_INTENTS_PLURAL` virou interruptor, com padrão novo no código: `cohort` (sem env:
  a coorte atendida), `off` (emergência, desliga para todos), `subjects` (estreita a coorte para
  `CONCIERGE_INTENTS_SUBSCRIBERS`), `all` (também só dentro da coorte). Valor desconhecido desliga.
- O app vivo não tem a chave (o painel nunca recebeu o `subjects` do #1449): com este PR no ar,
  o dono passa a ser atendido pelas intenções no plural no primeiro deploy, sem `doctl apps update`.
- O blueprint do alpha (`.do/app.alpha-subdomains.yaml`) perdeu as duas chaves do #1449: o arquivo
  fica mais perto do vivo (que também não as tem). Nada foi aplicado.
- Não precisou de configuração no banco: a coorte já é a configuração viva da Concierge.

## Decisões da coordenação aplicadas

1. **Pergunta repetida não é reclamação** ("você não respondeu", "e a minha pergunta?").
   - `dialogue.asks_again` reconhece a cobrança e recusa quando há queixa explícita ("absurdo",
     "demorou", "descaso"... ou a regra local de reclamação).
   - A memória do #1443 ganhou `parts`: as partes da última mensagem lida em partes e o que houve
     com cada uma (`answered`, `unanswered`, `team`, `suspended`).
   - Cobrança sozinha: a Concierge pede desculpa (copy `CONCIERGE_PARTS_REPEAT_LEAD`) e responde de
     novo as partes pendentes, da memória, sem leitura com modelo. Sem partes guardadas, a última
     fala do cliente que perguntava algo; sem nada, pede para repetir (`CONCIERGE_PARTS_REPEAT_ASK`).
   - Cobrança com pergunta junto ("você não respondeu: até que horas abrem?"): a cobrança sai antes
     da leitura e o resto é lido normalmente.
   - A triagem não aceita "reclamação" do Jev ou do modelo numa cobrança sem queixa explícita (vale
     a regra local); a leitura descarta o ato `complaint` cujo trecho é cobrança.
2. **Cancelamento dentro de várias partes segue o #1445.** O #1445 continua ABERTO (sem fila) no
   fim desta frente, então ficou o ponto de ligação pronto: `intents._cancellation()` importa
   `concierge/cancellation.py` quando ele existir. Com ele: parte de cancelamento que a régua do
   site permite vira a pergunta de confirmação da Concierge (`self_cancellable` + `ask`), que fica
   como a pergunta única do fim da resposta; o "sim"/"não" é resolvido no começo do turno
   (`resolve_pending`), como no agente; fora da régua, equipe (R4). Sem o módulo, a equipe, como
   antes. Testado com um módulo de mentira com a mesma assinatura do #1445.

## Prova

- `pytest shopman/storefront/tests -k concierge` + admin + omotenashi: 720 passed, 29 skipped.
  Copy/usage/vocabulário/travessão/privacidade: 3.516 passed (com `usage_map.py` regenerado).
- As suítes que medem o agente (uma intenção) declaram `intents_plural: off` nos settings delas;
  a suíte das intenções (`test_concierge_intents.py`) cobre o padrão `cohort`, o `off`, o
  `subjects`, a pergunta repetida (memória, fala anterior, nada achado), a triagem com o Jev
  dizendo reclamação, e o ponto de ligação do cancelamento.
- Golden set (`concierge_reply_eval --plural`), antes → depois:

  | Medida | local antes | local depois | modelo antes | modelo depois |
  |---|---:|---:|---:|---:|
  | Várias partes, todas achadas | 12/16 | 12/16 | 15/16 | 15/16 |
  | Todas as partes, todos os casos | 48/66 | 48/66 | 61/66 | 62/66 |
  | Partes achadas | 67/85 | 67/85 | 80/85 | 81/85 |
  | Equipe achada | 6/13 | 6/13 | 11/13 | 11/13 |
  | Equipe sem precisar | 4 | 4 | 5 | 5 |
  | Uma parte lida como várias | 7/50 | 7/50 | 3/50 | 2/50 |

  O caso do teste de campo `campo-2` ("você não respondeu: até que horas vocês abrem? e o croissant
  tem castanha?") perdeu o ato `complaint` que a leitura com o modelo inventava; continua na lista
  "equipe sem precisar" do placar pela alergia (castanha), como `campo-1` e `campo-5`, que é
  comportamento do #1436 e não muda aqui. O placar de uma intenção (sem `--plural`) não muda:
  destino 210/221, intenção 50/85.

## O que ficou de fora

- Ligar o #1445 de fato: depende do merge dele. Quando entrar, o caminho em partes já o usa.
- Abrir para mais clientes: é abrir a coorte da Concierge (`allowed_subjects`), decisão do dono.
