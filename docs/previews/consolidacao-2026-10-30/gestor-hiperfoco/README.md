# Gestor de pedidos em hiperfoco: a fila pelo operador e pelo momento

Prévia (31/10/2026). Não autoriza implementação. Diagnóstico em `DIAGNOSTICO.md`.

Como rodar: a cópia A do `gestor-compact/run.sh` (origin/main + `apply-conn-sim.mjs`) mais
`node apply-fila.mjs <cópia>/surfaces/orders-nuxt`, `nuxt build` e o servidor na 4313 (mock
38920). Atual: http://127.0.0.1:4311/ · Proposta: http://127.0.0.1:4313/ ·
Saída: `/?columns=expedition`. Cenários: `curl 127.0.0.1:38920/__visual/scenario?set=gallery|normal`.

## O que muda, e o momento que justifica cada mudança

| Momento | Antes | Na prévia |
|---|---|---|
| Pedido novo que o sistema vai cancelar | "7 min" grande e verde; "cancela sozinho em 0:38" miúdo e cinza | "0:38" grande e vermelho, "para cancelar sozinho" embaixo; "aceita sozinho" fica calmo |
| Negociação do iFood | "responder até 07:12" | "6:58 para o iFood decidir sozinho", vermelho |
| Pix que ainda não caiu | ocupa um dos 4 lugares de "Precisa de você", com botão travado | sai da fila; conta em "Seguem sozinhos: 1 esperando o cliente pagar" |
| Bloqueio com motivo | botão desativado | só o motivo escrito; botão só quando há gesto |
| Entregador volta | "levou R$ 26,00 de troco" + "Dinheiro na entrega R$ 74,00" | "Deve voltar com o entregador: R$ 100,00 em dinheiro (74 + 26) · Maquininha" (na Fila e na Saída) |
| Dono no celular | três abas por etapa | a mesma fila "Precisa de você" do passe |
| "Na Cozinha" | "Sem estação" | "Não passa pela cozinha" |
| Supervisão | "O sistema fez · Nada automático" e nota de rodapé | o bloco só aparece quando o sistema fez algo |
| Meta | "meta 10" | "meta 10 min" |

## O que a prévia não prova

O simulador não tem pedido de retirada com pagamento pendente nem volumes declarados; o
cartão de retirada não foi exercitado. Tempo real, som e push não rodam. No produto, tirar o
Pix pendente da fila é uma regra do servidor (`order_attention.attention_kind`), não do
cartão.

## Rodada 2 (31/10): o Gestor aberto pelo posto

O dono não viu diferença significativa na rodada 1 (ajustes dentro do mesmo cartão e da
mesma tela). A rodada 2 desenha uma tela por posto, com os mesmos dados e ações
(`useOrdersBoard`): http://127.0.0.1:4313/posto?modo=caixa|passe|gerente (`posto.vue`).

- **Caixa (computador, de relance):** uma frase no topo com o que pode ser perdido
  ("I02 cancela em 0:38"), uma lista de uma linha por pedido com o prazo à esquerda e o
  gesto à direita (A aceita o primeiro novo). Sem filtro, ordenação ou painel.
- **Passe (tablet, em pé):** faixa vermelha só para o que pode ser perdido; o próximo a
  sair em destaque (código grande, nome, sacolas, endereço, troco a levar, um botão);
  "Depois" e "Entregadores" ao lado, com o que deve voltar.
- **Gerente (celular):** "Agora na loja" numa frase; "Pode ser perdido" com
  Aceitar/Recusar; "Atrasados"; "Canais".

**Decidido pelo dono (31/10):** na retirada sem pagamento registrado, a tela pergunta
"Já pagou?" antes de entregar: "Já pagou, entregar" (um toque) ou "Receber R$ X".
Lacuna: hoje o Gestor só recebe na retirada quando `can_settle_delivery_cash`; para o
pagamento não informado, o "Receber" da prévia só abre o pedido. Precisa de ação no servidor.

**Decidido pelo dono (31/10):** o prazo de perda (pedido que o sistema vai cancelar sozinho,
negociação que o iFood decide sozinho) é vermelho. Muda a regra do quadro, que reservava o
vermelho ao bloqueio com motivo: agora vermelho é **perder** (prazo de perda) ou **não poder**
(bloqueio). Atraso contra a meta continua âmbar.

## Detalhe do pedido (31/10, `apply-detalhe.mjs`)

Quem abre o detalhe, e para quê: o caixa ou o gerente com o cliente no telefone ("cadê
meu pedido?"); quem resolve um bloqueio (Pix vencido, nota recusada, iFood); quem anota um
pedido do cliente para a cozinha. Atual: http://127.0.0.1:4311/WEB-261006-F90 · proposta:
http://127.0.0.1:4313/WEB-261006-F90 (também `IFOOD-261006-W01`, gravados do Django).

| Momento | Antes | Na prévia |
|---|---|---|
| Cliente no telefone | o estado era um selo ("Aceito") | uma frase no topo: "Aceito às 15:04: o preparo ainda não começou." |
| Bloqueio | o botão do cabeçalho era o próprio bloqueio ("Pix expirado", travado) | o cabeçalho só tem botão que se aperta; o bloqueio traz o que dá para fazer ali (Cancelar pedido, Reenviar link quando há) |
| Nota da cozinha | 5 etiquetas e uma caixa de texto sempre abertas, até depois do pronto | um botão "Nota para a cozinha" que abre o editor; depois do pronto, só a leitura |
| Avisos ao cliente | "Pedido confirmado · crítico · Não enviado · Este aviso não se aplica." | uma linha: "Nenhum aviso foi enviado ao cliente: não há contato do cliente."; "crítico" só quando falhou |
| Pagamento no celular | três vezes (pílula, resumo, iFood) | duas (resumo e iFood) |

**Revisão adversarial do próprio detalhe, o que ficou:** no computador a frase da situação
vem depois do cartão dos itens (a ordem é do kit, que o PDV também usa); o pagamento do iFood
ainda aparece duas vezes no celular; a previsão de pronto ("pronto em ~4 min") não existe na
projeção do detalhe, só no cartão da fila; o detalhe é do kit (`OperatorOrderDetail`, o mesmo
da encomenda no PDV, decisão de 28/09): qualquer mudança de ordem vale para os dois apps.
