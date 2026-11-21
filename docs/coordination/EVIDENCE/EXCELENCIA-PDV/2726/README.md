# #2726: a falha dos gestos da antessala mora dentro do diálogo

Prévia no PDV de verdade: Django local semeado (banco próprio `shopman_pdv_a2726`), PDV
compilado, a Caixa (Fran) com PIN e a Gerente (Joyce) escolhida da lista, com o próprio
PIN. A falha é forçada no navegador: a ida do POST cai (`connectionreset`), o servidor não
chega a ver o pedido. Nada de produção.

Sonda: `surfaces/pos-nuxt/tests/e2e-live/j7-falha-no-dialogo-da-antessala.live.spec.ts`,
rodada pelo `scripts/run_pos_e2e_live.sh j7-falha` (pilha :8072/:3172/:3173, host
`pdva2726.localhost`). "Antes" é a mesma sonda contra o build do `origin/main`
(`4ed9145a8`); "depois", contra este branch.

## As capturas (`antes/` e `depois/`, em `375/` e `1366/`)

| arquivo | o gesto |
|---|---|
| `01-request_change-falhou.png` | "Pedido de troco": o pedido não foi enviado |
| `02-dois-pedidos-de-troco.png` | a antessala depois de repetir os dois pedidos |
| `03-serve_change-falhou.png` | "Pedidos de troco": atender falhou (o aviso na linha do pedido) |
| `04-cancel_change-falhou.png` | "Pedidos de troco": cancelar falhou (o aviso na confirmação) |
| `05-settle_account-falhou.png` | "Contas na casa": o acerto falhou (o aviso na conta) |
| `06-gaveta-sem-caminho.png` | "Abrir gaveta": sem caminho de software neste dispositivo |

**Antes:** o diálogo segue aberto e a falha é um toast que o véu cobre (a auditoria mede
`covered: true` nos quatro gestos, nos dois tamanhos). Nas capturas o toast nem aparece
por cima do diálogo.

**Depois:** o aviso aparece dentro do diálogo, como alerta (`role="alert"`), com X e com
"Tentar de novo", que repete o mesmo gesto; o foco vai para esse botão. Tocado, a
repetição confirma e o aviso some (a sonda confere: o pedido entra, o atendido e o
cancelado saem da lista, a conta acertada fecha o formulário).

## A auditoria (`auditoria.txt`)

Por script, dentro da sonda, nos dois tamanhos:

- **Contraste:** a frase do aviso 5,23:1 (14 px, peso 500), "Tentar de novo" 6,1:1. O
  botão em hover (o ponteiro do balcão fica sobre ele quando o aviso nasce) mede 4,03:1:
  é o tom de hover do botão sólido de erro da suíte inteira, registrado à parte.
- **Corte e tela:** nada cortado, tudo dentro da tela, nada encoberto.
- **Posição:** o aviso fica dentro do diálogo e na área visível dele, alinhado à borda de
  conteúdo da coluna onde mora (`columnLeft` igual aos vizinhos).
- **Foco:** segue dentro do diálogo, no "Tentar de novo". Na primeira rodada caía no
  `body` (o botão do gesto se desabilita enquanto corre); o conserto está neste PR.

Os dois `"contrast":1` da seção "antes" são o toast de sucesso "Troco de R$ 50,00
atendido." medido atrás do véu, junto do toast de erro.

## O que a tela não provou

- **Abrir gaveta:** o dispositivo da pilha não tem caminho de software para a gaveta (nem
  agente do Balcão, nem relay do servidor), e o card fica desabilitado com o motivo. As
  três falhas da gaveta (registro, relay, recusa do agente) estão provadas no vitest: na
  página (`tests/pages/sessionIndex.layout.test.ts`) e no composable
  (`tests/composables/falhaComSaida.caixa.test.ts`).
- O banner "Há N dispositivos neste balcão" é do próprio harness: cada rodada vincula um
  dispositivo novo ao mesmo posto.
