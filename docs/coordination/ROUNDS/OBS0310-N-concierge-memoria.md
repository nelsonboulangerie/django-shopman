# OBS0310-N: Concierge, a memória da conversa

- **id:** OBS0310-N
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-memoria
- **PR:** #1443
- **início (UTC):** 2026-10-03
- **estudo:** `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md` (PR #1438), bloco 2 (fatia F2), com a decisão
  do dono de 03/10: a memória vence pelo que acontece, não pelo relógio.

## O que mudou
- `concierge/dialogue.py` (novo): estado explícito em `Conversation.flags["dialogue"]` (sem migração,
  chave documentada em `docs/reference/data-schemas.md`): pergunta pendente com o que o "sim"/"não" faz,
  a última lista numerada, o produto em foco, o pedido em foco e a última mudança na sacola. Resolução
  determinística, sem rede: "o segundo", "essas opções", "ele", "mais 2", "quero 2 então", "não, era o
  outro", "14:30", "sim". Sem referente que ainda valha, a casa pergunta (copy nova em Copy Omotenashi).
- Vencimento pelo que acontece: resumo pendente vale enquanto o `quote_token` for o mesmo; pergunta do dia
  vence quando o dia passa; lista e foco valem até o fim do próximo dia de funcionamento
  (`business_calendar`, sexta à noite vale até segunda); pedido entregue ou cancelado fecha a memória
  dele e segue como "pedido recente" por `recent_order_days` (7, `CONCIERGE_RECENT_ORDER_DAYS`) ou até o
  próximo pedido, lido do Orderman a cada turno; `return_to_concierge` zera.
- Pedido aberto + "mais 4 croissant": a casa pergunta se é para acrescentar ao pedido (vai para a equipe,
  que é quem mexe em pedido feito) ou fazer um novo. Pedido já entregue: pergunta se é pedido novo.
- Cortesia com contexto: "obrigado, chegou!" depois de uma entrega e "ok obrigada" ao fim de um pedido
  confirmado reconhecem o evento (dados do pedido, nunca inventados). Sem evento, a cortesia de hoje.
- `agent.py`: a memória roda antes da cortesia e do glúten; a fala resolvida é o que a busca lê; o estado
  vai ao prompt como bloco à parte (`prompt.py` não foi tocado). `service.py`: grava na mesma transação da
  resposta, conferindo o `turn_fence` (turno revogado não grava).
- `concierge_reply_eval --memory` + `golden_memory.json`: placar dos 47 casos de contexto.

## Medição (saída de `concierge_reply_eval --memory`)

| esperado | casos | antes | depois |
|---|---:|---:|---:|
| resolvida pelo estado | 6 | 0 | 6 |
| "sim" que chama a equipe | 1 | 0 | 1 |
| pergunta em vez de supor | 5 | 0 | 5 |
| se basta (memória não mexe) | 35 | 35 | 35 |
| total certo | 47 | 35 | 47 |

"Sim" aplicado à pergunta errada: 0. Suposição onde cabia pergunta: 0.

Ressalva: os rótulos e o resolvedor foram escritos pela mesma frente. Sete estados são reconstituídos
(a equipe respondeu na hora; o caso imagina a Concierge respondendo a bolha anterior). O número real
sai da régua em produção.

## O que ficou de fora
- A oferta da equipe na alergia (OBS0310-I, PR #1436, já no `main`) continua em
  `flags["triage"]["answered_by"]`: o "sim" a ela é decidido pela triagem, que roda antes da memória.
  Migrar para `pending offer_team` é passo próprio, sem mudança de comportamento.
- `verifying` e `with_team` (bloco 4, "vou verificar") e várias intenções na mesma fala (bloco 1).
- O que a equipe disse no Live Chat do ManyChat continua invisível; por isso o retorno zera.
