# OBS0310-B — Concierge: "bom dia" recebe bom dia

- **id:** OBS0310-B
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-bom-dia
- **PR:** #1415
- **início (UTC):** 2026-10-03

## A causa, medida no alpha
Leitura do banco do alpha pela conexão direta (25060, banco `shopman`, transação somente leitura).
Conversa 2, mensagem 672 "Bom dia, tudo bem?": a triagem ficou em `product_question` com fonte
`default` (ninguém reconheceu a intenção) e destino `answer`. A mensagem 673 é uma `search_storefront`
com `id` `server_search_0` e argumentos vazios: o modelo NÃO chamou a busca, foi o servidor.
A resposta 675 trouxe Chá Hibisco, Chá Tônica, Pão para Hot Dog, a FAQ do levain e a FAQ de glúten.

Dois desenhos juntos produziram isso (`concierge/agent.py`, PR "contained conversational sales"):
1. a resposta ao cliente é sempre o texto renderizado das ferramentas; o texto do modelo é descartado;
2. quando o modelo responde sem consultar, o servidor roda `search_storefront` sobre a fala inteira.
A busca não conhecia cumprimento: "bom" casou com "bom para cachorro quente" (descrição do pão de hot
dog), "tudo"/"bem"/"dia" casaram por substring nas FAQs ("todos os dias").

## O que mudou
- `concierge/small_talk.py` (novo): cumprimento, agradecimento e despedida SOZINHOS ("bom dia",
  "oi", "obrigado", "tchau", "tudo bem?") recebem uma linha na voz da casa, sem modelo e sem busca.
  O "Bom dia" devolvido é o que o cliente usou; "oi" recebe o do relógio da loja.
- Copy nova no registro (`CONCIERGE_SMALL_TALK_*`, editável em Copy Omotenashi).
- Triagem: cortesia não consulta Jev nem modelo.
- `search_storefront`: cumprimento não é termo de busca; sobrou só cortesia, não acha nada (antes,
  busca vazia viraria cardápio); as perguntas frequentes só recebem as palavras que não acharam
  produto ("tem croissant hoje?" não traz mais o levain, que cita croissant no corpo).
- "Bom dia, tem croissant hoje?" responde "Bom dia!" e o fato.

## O que ficou de fora
- "Ah ótimo", "ok", "sim" NÃO viram cortesia: "ok" depois do resumo pode ser confirmação de pedido.
  Continuam indo ao modelo, e sem fato encontrado recebem a frase fixa "Preciso consultar os dados...".
- O prompt ainda chama a concierge de "o concierge" e a copy `CONCIERGE_GREETING` também. Hoje o texto
  do modelo nunca chega ao cliente, então não muda resposta; fica para a frente de voz.
- "o pão leviano tem glúten?" vai para a equipe pela triagem (alergia é sensível, D32). A busca, se
  chamada, traz o leviano e só a FAQ de glúten.
