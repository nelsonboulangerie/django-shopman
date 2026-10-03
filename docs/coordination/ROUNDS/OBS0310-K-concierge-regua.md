# OBS0310-K — Concierge: a régua (custo, tempo e o golden set)

- **id:** OBS0310-K
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-regua
- **PR:** #1437
- **início (UTC):** 2026-10-03
- **estudo:** `docs/plans/CONCIERGE-ARQUITETURA-ALVO.md` (PR #1435), fatia F1. O cliente não vê nada mudar.

## O que mudou
- `concierge/metrics.py` (novo): `TurnMeter` acompanha o turno. Cronometra triagem, Jev, agente, idas
  ao modelo e ferramentas; soma tokens por (etapa, modelo) com leitura E escrita de cache (a escrita
  nunca era gravada); estima o custo pela tabela de `shop/services/ai_pricing.py` (nova
  `usage_cost`: leitura de cache a 0,1 e escrita a 1,25 do preço de entrada; Sonnet 5.5 na tabela).
- `service.run_turn` grava a régua em `ConversationMessage.usage` do PRIMEIRO bloco da resposta,
  inclusive no aviso de handoff. Sem migração: o campo `usage` já existia e nunca era escrito.
  Formato em `docs/reference/data-schemas.md` ("Régua da Concierge").
- `agent.py`: a saída diz quem respondeu (`layer`: cortesia ou agente) e as ferramentas são
  cronometradas. Nenhuma mudança de comportamento.
- `triage.py` e `handoff.py` NÃO foram tocados (frente OBS0310-I). O cliente da triagem é criado e
  medido por fora (`metrics.triage_client_for`), com a mesma regra de quando há modelo.
- `concierge/golden_set.json` (novo): 209 mensagens reais do alpha (04/09 a 03/10/2026), redigidas e
  conferidas à mão, com camada, intenção e destino esperados.
- `concierge_golden_export` (novo): rascunho redigido a partir do banco, com o rótulo da regra marcado
  `reviewed: false`. `concierge_reply_eval` (novo): placar do caminho de hoje contra o golden set;
  `--classifier rules|model|jev|jev-shadow`; `--production` resume a régua gravada.

## Como o golden set foi montado
Leitura do alpha SÓ pela conexão direta (25060, banco `shopman`), transação somente leitura
(`default_transaction_read_only=on`). 224 entradas exportadas; fora: "Testando", repetições literais
da conversa de teste do dono e uma mensagem com nomes de terceiros fora do assunto. Redação automática
(`redact_observation_text`) e, à mão: nomes próprios (seis), dois endereços, um código de cardápio, um
Pix copia e cola. A trava `test_golden_set_is_labeled_and_carries_no_personal_data` reprova telefone,
e-mail, link e número longo no arquivo.

## A primeira medição (golden set, 209 casos)
Ver o relatório da PR para a saída completa dos comandos. Resumo:

| Triagem | Destino certo | Equipe e outra mesa achadas | À equipe sem precisar | Intenção certa | Custo por mensagem | Tempo da triagem |
|---|---:|---:|---:|---:|---:|---:|
| regra local | 200/209 (96%) | 2/11 | 0 | 41/74 (55%) | US$ 0 | p50 158 ms* |
| modelo (Sonnet 5, o do alpha) | 196/209 (94%) | 10/11 | 12 | 68/74 (92%) | US$ 0,0016 | p50 2,7 s, p95 3,4 s |
| Jev (sombra gravada, 167 observados) | 164/167 (98%) | 4/6 | 1 | 40/48 (83%) | cerca de US$ 0,00002 | p50 166 ms, p95 226 ms |

\* a regra local consulta o rótulo da intenção no banco; medido daqui contra o banco do alpha.

Quem responde hoje: 133 de 209 mensagens (64%) chegam ao agente com o modelo pela regra local
(113, 54%, com a triagem por modelo, porque ela manda 12 à equipe sem precisar: "ok obrigada", "??", "Ué", "Tudo otimo" viram "falar com uma pessoa"); na arquitetura alvo seriam 47 (22%).
Todo link (17) e toda fala de contexto (47) vão hoje ao agente.

Resposta do alpha medida na hora (42 respostas, inclui 1 s de espera): sem ferramenta p50 5,6 s;
uma ferramenta p50 7,6 s; duas ou mais p50 16,4 s, máximo 43,5 s.

## O que ficou de fora
- Custo e tempo do AGENTE por resposta sobre o golden set: o agente precisa do catálogo e da sacola
  vivos, e rodá-lo aqui seria medir outro cardápio. A régua grava isso em produção a partir do deploy;
  `concierge_reply_eval --production` lê.
- Jev ao vivo: a chave mora só no alpha; a medição usa a sombra que o alpha gravou.
- Os contadores da `Conversation` seguem só com o modelo da resposta, como antes.
