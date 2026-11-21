# #2917: o Pix do balcão cobra só o saldo da encomenda com parte paga (prévia)

A encomenda paga e depois aumentada tem saldo. O Pix do balcão cobra exatamente esse saldo, e o
que já entrou fica como estava.

## Como foi capturado

- **PDV de verdade**: Django local (`:8075`, banco local `shopman_pdv_e5`), PDV e Cozinha em build
  de produção (`:3195`/`:3196`), worker de directives ligado, host `pdve5.localhost`. Nunca produção.
  **Pagamento só no simulador local** (`payment_mock`, `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true`, atraso
  de 25 s): o simulador faz o papel do banco e confirma pelo caminho canônico.
- **Papéis**: Joyce (Gerente) inicia o dispositivo; Fran (Caixa) opera com PIN.
- **Jornada**: `surfaces/pos-nuxt/tests/e2e-live/j6-receber-e-entregar.live.spec.ts`, teste "saldo
  parcial (#2917)", em 375 px e 1366 px. A encomenda nasce pela tela paga em dinheiro (1 Croissant,
  R$ 13,00), é editada pela tela ("Editar encomenda", mais 1 Croissant, "Salvar alterações") e o
  saldo de R$ 13,00 é cobrado em Pix no "Receber e entregar".
- **Antes**: a mesma jornada no código do #2918 (`e6c952219`), com `PDV_LIVE_J6_SIDE=antes`.

## Antes (`antes/375`, `antes/1366`)

| Arquivo | O que mostra |
|---|---|
| `01-parcial-saldo-com-o-ja-pago.png` | o Pagamento do saldo (Total R$ 26,00, Já pago R$ 13,00, A receber R$ 13,00) com o Pix apagado: o servidor recusava ("Esta encomenda já tem parte paga: o Pix do balcão ainda não cobra só o saldo."). O aviso verde é o de "Encomenda atualizada", da edição |

## Depois (`depois/375`, `depois/1366`)

| Arquivo | O que mostra |
|---|---|
| `01-parcial-saldo-com-o-ja-pago.png` | o mesmo Pagamento, com o Pix aceso |
| `02-parcial-pix-so-do-saldo.png` | o QR da venda: "Pagamento Pix · R$ 13,00", só o saldo |
| `03-parcial-pix-confirmado-entregue.png` | o banco confirma: "Pix de R$ 13,00 confirmado. Encomenda entregue." e o PDV volta à lista |

## Auditoria

`auditoria.txt`, gerado pela jornada: contraste (mínimo 4,5:1), letra (mínimo 12 px), dentro da
tela, nada cortado, nada encoberto e transbordo horizontal zero. Resultado: nenhuma reprovação nos
dois tamanhos.

Achado e corrigido no caminho: depois de editar e entregar, o "voltar" caía de novo no detalhe da
encomenda entregue (a ida e volta da edição empilhava um segundo detalhe no histórico). A edição e
a volta dela agora trocam a entrada do histórico.
