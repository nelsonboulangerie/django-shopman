# #2916: o Pix misto no saldo da encomenda (prévia)

Gesto de dinheiro tem uma tela só (dono, 16/11/2026). No "Receber e entregar", Pix ao lado de
dinheiro ou cartão é o Pix da venda mista: a mesma tela de Pagamento, o mesmo degrau "Confira o
Pix" / "Recebi o Pix", e a entrega leva o Pix atestado.

## Como foi capturado

- **PDV de verdade**: Django local (`:8075`, banco local `shopman_pdv_e5`), PDV e Cozinha em build
  de produção (`:3195`/`:3196`), worker de directives ligado, host `pdve5.localhost`. Nunca produção.
  **Pagamento só no simulador local**: o Pix misto nem passa por provedor (é atestado no balcão).
- **Papéis**: Joyce (Gerente) inicia o dispositivo; Fran (Caixa) opera com PIN. A encomenda nasce
  pela tela (hoje, retirada, a pagar na retirada) e é aberta pela lista das Encomendas.
- **Jornada**: `surfaces/pos-nuxt/tests/e2e-live/j6-receber-e-entregar.live.spec.ts`, teste "Pix
  misto (#2916)", em 375 px e 1366 px. R$ 10,00 em dinheiro e o Pix completa o saldo.
- **Antes**: a mesma jornada no código do #2918 (`e6c952219`), com `PDV_LIVE_J6_SIDE=antes`: ela
  para na tela decisiva e captura.

## Antes (`antes/375`, `antes/1366`)

| Arquivo | O que mostra |
|---|---|
| `01-misto-dinheiro-e-pix.png` | dinheiro + Pix cobrindo o saldo, e a tela trava: "No saldo da encomenda, o Pix cobra o valor inteiro, sozinho." (a 375 px o aviso fica abaixo da dobra) |

## Depois (`depois/375`, `depois/1366`)

| Arquivo | O que mostra |
|---|---|
| `01-misto-dinheiro-e-pix.png` | as mesmas linhas, sem trava: "Receber e entregar" aceso |
| `02-misto-confere-o-pix.png` | o degrau da venda mista: "Confira o Pix", o valor do Pix e "Recebi o Pix" |
| `03-misto-entregue.png` | entregue: o PDV volta à lista. A rota recebeu `[{cash, 1000}, {pix, saldo − 1000, pix_confirmed: true}]` |

## Auditoria

`auditoria.txt`, gerado pela jornada: contraste (mínimo 4,5:1), letra (mínimo 12 px), dentro da
tela, nada cortado, nada encoberto. Resultado: nenhuma reprovação nos dois tamanhos.

Nota: o selo do método no diálogo de conferência sai em caixa alta ("PIX") por estilo do
componente da venda (o texto é "Pix"); é o mesmo diálogo da venda mista, sem mudança aqui.
