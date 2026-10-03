# OBS0310-M: Concierge, regras da casa (fatia F3 da arquitetura v2)

- **id:** OBS0310-M
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-regras
- **base:** começou sobre `claude/obs0310-concierge-regua` (PR #1437, golden set e `concierge_reply_eval`);
  a #1437 e a #1438 entraram no `main` durante a frente, e o `main` foi trazido para o branch.
- **estudo:** `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md` (PR #1438), seção 7 e fatia F3.
- **PR:** #1442
- **início (UTC):** 2026-10-03

## O que mudou
- `concierge/house_rules.py` (novo): as 14 regras da v2 numa tabela declarativa. Cada regra tem id,
  quando se aplica, o que exige ou proíbe, o efeito quando é quebrada (por origem: resposta montada
  pela casa ou texto do modelo), quem executa, e exemplos que são testes.
- Toda resposta passa pela tabela antes de ser gravada para envio, inclusive a montada pelo sistema:
  `service.run_turn` revisa o turno inteiro (onde a conversa ainda pode ir para a equipe) e
  `service._prepare_reply` é a última trava (conserto e medida). Efeitos: `REPAIR` troca a palavra e
  segue; `HOLD` segura a resposta, entrega a conversa à equipe e manda o aviso de handoff (que é verdade,
  porque o handoff foi criado); `RECORD` só mede. O envelope de cada resposta grava o que a tabela fez
  (`envelope["house_rules"]`, em `data-schemas.md`).
- R6 (promessa só com recibo): "vou avisar a equipe", "separei", "pedido confirmado", "vou verificar" e
  "confirme com a loja" só saem com o recibo do turno (equipe avisada, handoff, sacola, pedido, aviso de
  disponibilidade). Os recibos vêm do que os executores fizeram (`receipts_for`).
- R4 ganhou o que o dono decidiu em 03/10: Pix ou link de pagamento que não funcionou, desistência pela
  taxa de entrega e "avise seus superiores" vão para a equipe (`handoff.py`); cancelamento de pedido vai
  para a equipe com `escalated_by = cancel_order` (`triage.py`).
- R7 (nunca negociar) e R8 (diz que é a assistente da casa) viraram frase fixa, sem modelo nem busca
  (`agent.run_agent`, copy `CONCIERGE_PRICE_NEGOTIATION` e `CONCIERGE_IDENTITY`, editáveis no Admin).
- A copy da casa que a própria tabela reprovou foi corrigida na fonte: `CONCIERGE_TURN_LIMIT` prometia
  "a equipe segue com você" sem chamar ninguém; `CONCIERGE_UNAVAILABLE` prometia que a equipe continuava
  o atendimento (agora diz que a equipe foi avisada, o que o alerta garante) e falava "nosso concierge";
  `CONCIERGE_GREETING` estava no masculino. As respostas de ferramenta (`tools.render_result`) usavam
  travessão em toda linha de produto, sacola e pedido; viraram dois-pontos.
- `concierge_reply_eval` imprime a seção "Regras da casa": exemplos da tabela, as respostas "Casa"
  gravadas no golden set (antes e depois) e as falas que ganham frase fixa.

## Coordenação
- Cortesia (#1415) e alergia (#1434 no `main`, #1436 aberta) foram reaproveitadas: R9 é o
  `small_talk.py`, a entrada de R3 é a triagem e o executor de alergia. `house_rules.py` não importa
  `gluten.py` (que a #1436 apaga); a saída de R3 só proíbe afirmar ausência e "pode comer".
- Conflito esperado com a #1436 em `agent.py` (bloco vizinho ao do glúten), `copy.py`, `usage.py` e
  `admin/concierge.py` (linhas vizinhas). Resolver mantendo as duas.
- Teste de campo (PR #1441): "confirme com a loja" sem acionar ninguém entrou em R6. "Toda parte da
  mensagem recebe resposta" depende da decomposição em partes (F4) e fica para ela; o aviso de handoff
  sempre sai quando a tabela segura uma resposta (teste), mas o prazo do retorno é a F5.

## Como verificar
```
make test-framework   # ou, no worktree, com PYTHONPATH apontando para packages/* do worktree
.venv/bin/python manage.py concierge_reply_eval
```

## Medição (golden set, 209 casos, triagem pela regra local)

| | Destino certo | Equipe e outra mesa achadas | À equipe sem precisar |
|---|---:|---:|---:|
| Antes (base #1437) | 200/209 (96%) | 2/11 | 0 |
| Depois | 202/209 (97%) | 4/11 | 0 |

Regras da casa: exemplos da tabela 88/88; das 36 respostas "Casa" gravadas no conjunto (texto do
modelo, alpha 04 a 12/09), 27 quebram alguma regra (R1 21, R5 11, R6 3, R12 15); com a tabela, as 27
seriam seguradas (equipe) e nenhuma violação sairia. Os recibos da época não estão nos casos, então
toda promessa conta como sem recibo comprovável.

## Fora desta fatia
- Memória (F2), decomposição em partes e "toda parte respondida" (F4), "vou verificar" com prazo (F5),
  redação com marcadores (F6). R1 e R5 hoje são cumpridas por construção (nenhum texto do modelo chega
  ao cliente); o verificador delas reprova texto `MODEL` e é a trava para a F6.
- O prompt não passou a citar a tabela: o texto do modelo é descartado hoje, e a citação entra com a F6.
