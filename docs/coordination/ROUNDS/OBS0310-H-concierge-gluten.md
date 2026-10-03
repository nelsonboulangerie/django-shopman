# OBS0310-H: Concierge responde glúten com o aviso da casa

- **id:** OBS0310-H
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-gluten
- **início (UTC):** 2026-10-03

## A decisão
Dono, 03/10/2026: pergunta sobre glúten, trigo ou doença celíaca a Concierge responde sozinha,
porque a resposta é categórica (a casa usa farinha de trigo em tudo o que assa e não tem nada sem
glúten, pela contaminação cruzada). As outras alergias continuam com a equipe (D32).
Ajuste pedido no meio da frente: nada de texto fixo novo da Concierge; a resposta vem da fonte de
conhecimento que o site já mostra.

## O que mudou
- `concierge/gluten.py` (novo): reconhece a pergunta que é SÓ de glúten e monta a resposta com o
  aviso de produção compartilhada (`Shop.food_safety_notice`, decisão do dono de 08/09) e, quando
  a fala cita um produto do cardápio pelo nome, os alérgenos declarados dele (o mesmo campo do
  cartão e da página do produto).
- Uma fonte só: `public_information.food_safety_notice()` é o que a página do produto e a
  Concierge leem. Editar o aviso no Admin muda as duas.
- Triagem: pergunta só de glúten fica `intent=allergy`, `destination=answer`,
  `answered_by=gluten_notice`, sem consultar modelo nem Jev. Sem aviso cadastrado, segue para a
  equipe como antes.
- `run_agent`: a pergunta só de glúten responde sem modelo e sem busca (nada pode ser parafraseado
  em "sem glúten"). "Bom dia, ..." abre com o mesmo bom dia.
- `handoff.py`: "tem castanha no panetone?", "leva amendoim?" passam a ser reconhecidos como
  alergia (antes caíam em pergunta de produto e o bot respondia).
- FAQ inicial de glúten (`apply_search_presence`): conferida contra o aviso (não contradiz:
  "Não temos... contêm ou podem conter glúten"); termos de busca ganham "celíaca", "doença
  celíaca" e "farinha de trigo" (antes "celíaca" no feminino não achava a resposta).
- "pão leviano" (não existe) virou "levain" nos testes e no registro da OBS0310-B.
- Documentação: `WHATSAPP-CONCIERGE-PLAN.md` (tabela e seção da triagem), D-018 em
  `DECISIONS.md`, `data-schemas.md` (`answered_by`), prompt da Concierge.

## Regras de segurança
- Nunca afirma "sem glúten"; nunca apresenta produto como seguro. Produto sem alérgeno declarado
  não aparece na resposta (lista vazia não vira "não tem").
- Glúten junto de outra alergia ("tem glúten ou castanha?", "sou celíaca e alérgica a ovo"): a
  mensagem INTEIRA vai para a equipe. Escolhi a inteira porque responder só a metade do glúten
  daria a impressão de que a outra metade foi respondida.
- "Alergia"/"intolerância" sem dizer a quê, reclamação e pedido de pessoa seguem com a equipe.

## O que ficou de fora
- No alpha a FAQ de glúten já existe como rascunho; o `apply_search_presence` não reescreve
  pergunta existente, então os termos novos só entram num banco novo ou se o gestor editar.
- Pergunta mista de glúten com disponibilidade ("tem croissant hoje e tem glúten?") recebe só a
  resposta de glúten.
