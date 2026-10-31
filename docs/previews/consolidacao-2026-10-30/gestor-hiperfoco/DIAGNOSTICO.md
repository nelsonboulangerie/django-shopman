# Gestor de pedidos, hiperfoco: diagnóstico pelo operador e pelo momento

Somente análise (31/10/2026). Não autoriza implementação. Medido no Gestor de `origin/main`
(`caf450360`) com o simulador visual (`tests/visual/mockBackend.mjs`, cenários `normal` e
`gallery`), a 390×844 (celular), 1024×768 (tablet deitado) e 1440×900 (computador). O
simulador mistura fixtures (horas como "591h", detalhe montado sobre um pedido do iFood):
nada abaixo depende desses dados; cada achado foi conferido no código citado.

## Quem, onde, quando (plano aprovado em 03/10, SUITE-UX-FUNCTION-PLAN §10.4)

| Posto | Dispositivo | A pergunta do momento |
|---|---|---|
| Passe (expedição) | tablet | O que eu faço agora, e o que vem logo depois? |
| Escritório (supervisão) | computador | Algo está parado, atrasado ou para ser perdido? |
| Dono em movimento | celular | Tem algo para ser perdido? Aceito ou recuso? |

## Achados

1. **O relógio que decide é o menor da tela.** Pedido novo do iFood a 38 s de ser
   cancelado: o número grande é "7 min" em verde (calmo) e "cancela sozinho em 0:38" sai
   em `op-micro text-muted-foreground` (`QueueView.vue:455-475`). "Aceita sozinho"
   (inofensivo) e "cancela sozinho" (venda perdida) têm o mesmo peso e a mesma cor. A
   ordenação já põe a perda primeiro (`queue.ts:151`); a forma não acompanha.
2. **"Precisa de você" traz o que não precisa de você.** Pix pendente entra na fila com
   "Iniciar preparo" travado e "O pedido só avança depois que o dinheiro entra": quem age
   é o cliente. Ocupa um dos 4 lugares de foco (`QUEUE_FOCUS = 4`).
3. **Botão principal que não se pode apertar, e o motivo atrás de um toque.** Celular,
   H58: "Bloqueado" + chip "Por que espera" + "Iniciar preparo" desativado. Contraria a L3
   (a informação da decisão no lugar da decisão, antes do gesto).
4. **Retirada com o cliente na frente.** Saída, G96: o cartão mostra o telefone, não o
   nome; "Pagamento não informado" num chip pequeno; botão "Entregar G96". O que a pessoa
   precisa, nessa ordem: quem é, se falta cobrar e quanto, quantas sacolas.
5. **Volta do entregador com conta de cabeça.** "Entregador levou R$ 26,00 de troco" +
   "Dinheiro na entrega R$ 74,00": quem confere soma R$ 100,00. O diálogo já tem a lista do
   que deve voltar (`courier_return_lines`); o cartão não.
6. **Um trabalho, duas formas.** Computador e tablet deitado abrem na fila "Precisa de
   você"; celular e tablet em pé, em três abas por etapa (`index.vue:679-690`). O dono no
   celular não vê a mesma fila, nem na mesma ordem, que o passe.
7. **Topo do computador: 14 controles antes do primeiro pedido**, vários de uso de
   escritório ocasional (ordenar, Grade/Lista, canal). E o bloco "O sistema fez" ocupa
   espaço com "Nada automático neste intervalo".
8. **"Sem estação" em "Na Cozinha"** (`queue.ts:461`): lê-se como "a cozinha não recebeu".
   É o pedido sem item de estação (pão de prateleira): não está na cozinha, alguém separa.

## O que fica (já é omotenashi)

- A ordem "mais urgente primeiro" com a perda à frente (`queue.ts:151`).
- "Troco para R$ 50,00: levar R$ 24,00" no cartão da entrega: instrução com a ação pronta.
- "Entregador voltou" como gesto único do cartão na rua.
- O aviso do iFood "Responda em 6 min · sem resposta, o iFood cancela" com Responder.
- "Seguem sozinhos: 1 na cozinha" no fim da fila.

## Perguntas ao dono

Quem opera o Gestor no pico e em qual dispositivo; quem entrega a retirada ao cliente
(PDV ou Saída do Gestor). As respostas decidem a forma de cada posto.
