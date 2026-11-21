# Decisões do dono sobre a revisão das Entregas (16/11/2026)

Base: `relatorio.md` (41 itens com prova, plano em frentes F1a a F10) e `lacunas-do-critico.md` (L1 a L4).
Prévias locais: Gestor em `/preview-revisao/1` a `6` e `8` (orders-nuxt), loja em `/preview-revisao/7` (storefront-nuxt), neste PR draft.

| Prévia | Tema | Decisão |
|---|---|---|
| 1 | Sheet "Chamar entregador" | **A**: o companheiro que combina já vem marcado como "Sugestão da casa". A cotação é **só leitura** (o ✔ não é botão); quem decide é a caixa do companheiro e o botão principal. |
| 2 | Sugestões no topo de Aguardando | **A**: cartão "2 corridas sugeridas" com "Chamar juntas" por sugestão e "Chamar as 2 corridas". |
| 3 | Coluna Editando | **B** (a proposta), com a diagramação da prévia: parada em duas linhas sem truncar, troco com R$ dentro do campo, maquininha por corrida, ordem real da rota. |
| 4 | Faixa "Aguardando entregador" | **A**: dentro da Saída, abrindo a parte "A coletar". |
| 5 | "Ninguém aceitou" | **As duas ações juntas**: "Chamar de novo" (primária, sem custo a mais) e "Aumentar a oferta" (+R$ 3, +R$ 5, +R$ 8, uma vez por corrida, a casa paga a diferença). Cartão dentro de cartão é `soft`, sem borda. |
| 6 | "Entregue" na corrida com volta | **C**: o cliente recebe "entregue" pelo aviso da TaOn por parada (ER com `stop_id`, P1-7); o balcão só trata a exceção na volta ("Voltou com a sacola" → "Entregar de novo" ou "Devolver e estornar"). **B como interino** (como hoje). Acelerar a C: a homologação F6 e o P1-7 sobem na fila. |
| 7 | Tela do cliente | **B**: o botão "Acompanhar o entregador" só depois da coleta. Copy final na prévia ("Diego não pôde vir", "Está demorando mais que o normal", "Diego está a caminho. Deve chegar por volta de 12h45."): um fato útil por estado, sem prometer aviso, sem "corrida", "aceite" nem "TaOn", sem emoji. |
| 8 | Cartão da Saída | **Forma E**: o mesmo cartão para pedido solto, corrida de um pedido e corrida de vários. Corrida por **letra** (A, B, C…, nunca mais de 26 simultâneas) num quadrado colorido no canto superior direito, com "N pedidos" à esquerda dele. Códigos juntados separados por "∙", recolhidos em "+N" só quando falta espaço. Empilhamento sutil por trás para vários pedidos (uma camada por pedido a mais, até duas). Saída em duas partes: "A coletar" e "Saiu para entrega". |

Regras de copy reforçadas nesta rodada:
- Cotação sempre em duas linhas, com o ✔ na opção mais barata e essa linha em destaque (as outras esmaecidas): `Juntas: R$ 10,00 · 10 min · 5 km ✔` / `Separadas sairiam R$ 15,00`, ou `Juntas: …` / `Separadas sai mais barato: R$ 7,00 ✔`.
- "Ficar pronto", nunca "sair do forno".
- Primeira letra maiúscula em toda frase e em todo valor isolado ("Nenhuma livre").
- Ao cliente: respeito absoluto à inteligência e ao tempo dele. Um fato útil por estado; nada de "avisamos aqui quando…".
- **Hora (decidido, 16/11): "12h45" na suíte inteira** (operador e cliente). Hoje o código usa "12:45" via `toLocaleTimeString`; a troca vira frente própria, com a regra escrita em `docs/reference/suite-vocabulary.md` e uma trava que reprove o formato antigo.

Pendências que pedem a palavra do dono: os valores do "Aumentar a oferta" (propostos +3/+5/+8); a credencial para rodar a homologação da TaOn (F6).
