# OBS0310-I: Concierge responde todas as perguntas de alergia

- **id:** OBS0310-I
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-alergenos
- **início (UTC):** 2026-10-03
- **depende de:** OBS0310-H (#1434, glúten pelo aviso da casa)

## A decisão
Dono, 03/10/2026: a Concierge responde sozinha TODAS as perguntas de alergia e alérgeno, não só
glúten, pela mesma fonte única da OBS0310-H: o aviso de produção compartilhada da casa
(`Shop.food_safety_notice`, cobre glúten e traços de leite, ovos, castanha-do-brasil, castanha de
caju, gergelim e pimenta-do-reino) mais os alérgenos declarados do produto citado. Sempre oferece
a equipe para alergia grave (uma linha, copy editável). Reação alérgica é equipe, sempre.

## O que mudou
- `concierge/gluten.py` virou `concierge/allergens.py` (sem resíduo): reconhece a pergunta de
  alergia (alergia pessoal, "tem/leva/sem <alérgeno>", "alérgenos", "traços", glúten/celíaco) e
  devolve uma de três leituras: responder, perguntar "a quê?" ou equipe.
- Resposta: linha de cada produto citado (declarados, ou "ainda não há lista de alérgenos
  cadastrada, então vale o aviso abaixo (pode conter traços)"), o aviso da casa e a oferta da
  equipe. "Bom dia, ..." abre com o mesmo bom dia. Sem modelo e sem busca.
- Copy nova em Copy Omotenashi (`copy.py`, listada no Admin do concierge, `usage_map.py`
  regenerado): `CONCIERGE_ALLERGY_TEAM_OFFER`, `CONCIERGE_ALLERGY_ASK_WHICH`,
  `CONCIERGE_ALLERGY_PRODUCT_DECLARED`, `CONCIERGE_ALLERGY_PRODUCT_UNDECLARED`.
- Triagem (`triage.py`): `answered_by` passa a ser `allergy_notice`, `allergy_ask_which` ou
  `allergy_notice_after_ask` (era `gluten_notice`). "Sim" logo depois da oferta vira equipe com
  `escalated_by=allergy_offer_accepted`. O que a Concierge não pode responder vai para a equipe
  mesmo quando a regra do `handoff.py` não viu alergia ("tem amendoim?"), com o resumo do modelo.
  `decide()` recebe `channel_ref` (o serviço passa o da conversa) para achar o produto citado.
- `handoff.py`: reação alérgica e pessoa passando mal ("teve reação", "passei mal", "tive uma
  reação alérgica", "hospital", "falta de ar") são reclamação: equipe, agora, antes da alergia.
- `run_agent`: lê a triagem DESTE turno; sem ela (chamada direta) decide pela mesma função, e o
  que não pode responder vira handoff (segunda trava).
- Documentação: D-018 em `DECISIONS.md`, `WHATSAPP-CONCIERGE-PLAN.md` (tabela e seção da
  triagem), `data-schemas.md` (`answered_by`, `escalated_by`), prompt da Concierge.

## Regras de segurança (todas testadas)
- Nunca afirma ausência; nada é listado como "pode comer" ("sou alérgico a ovo, o que posso
  comer?" recebe o aviso, sem produto).
- Produto sem alérgeno declarado não é seguro: a linha dele manda para o aviso (traços).
- "Tenho alergia" pergunta a quê; a resposta seguinte que ainda não diz vai para a equipe; a que
  diz é respondida com o produto da primeira mensagem.
- Alérgeno de que nem o aviso nem o produto citado falam (hoje soja, amendoim, peixe) e
  restrição que não é alérgeno (vegano, diabetes): equipe. Escolhi o lado seguro porque o aviso
  de hoje não cita esses alérgenos, e responder só com ele deixaria deduzir "não tem".
- Sem aviso cadastrado: equipe.

## Como verifiquei
`pytest` na worktree com os `packages/*` dela à frente do `sys.path`: concierge (engine, triagem,
cortesia), Copy Omotenashi (chaves, mapa de uso), travessão e vocabulário de tela verdes. Casos do
dono cobertos em `test_concierge_engine.py`: "tem castanha no panetone?", "tem leite no
croissant?", "sou alérgico a ovo, o que posso comer?", "tem glúten ou castanha no panetone?",
"meu filho teve reação depois do pão de ontem", "tenho alergia", mais glúten, cortesia e
disponibilidade.

## O que ficou de fora
- Nome de produto com palavra de alérgeno sem perguntar dele ("ovos de Páscoa", "pão de leite",
  "café com leite") é tratado como pedido; outras combinações raras ("tem leite?" querendo comprar
  leite) recebem a resposta de alérgeno, o que é seguro mas não é o que o cliente queria.
- Pergunta mista de alergia com disponibilidade recebe só a resposta de alergia (como na H).
