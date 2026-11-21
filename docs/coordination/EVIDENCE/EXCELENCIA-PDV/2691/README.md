# #2691: o crachá do gerente autoriza a venda no Pagamento

Prévia no PDV de verdade: Django local semeado (banco próprio `shopman_pdv_a2726`), PDV
compilado, a Caixa (Fran) com PIN e a Gerente (Joyce) com o crachá de dev dela (o que o
`setup_operators` grava). O leitor de crachá é emulado como um leitor HID: as teclas do
token, sem pausa, e Enter. Nada de produção.

Sonda: `surfaces/pos-nuxt/tests/e2e-live/cracha-autoriza-a-venda.live.spec.ts`, rodada pelo
`scripts/run_pos_e2e_live.sh cracha` (pilha :8072/:3172/:3173, host `pdva2726.localhost`).
"Antes" é a mesma sonda contra o build do `origin/main`; "depois", contra este branch.

## As capturas (`antes/` e `depois/`, em `375/` e `1366/`)

| arquivo | o passo |
|---|---|
| `01-pedir-autorizacao.png` | venda em dinheiro com 50% de desconto: o Validar vira "Pedir autorização" |
| `02-autorizar-a-venda.png` | o diálogo "Autorizar a venda", com o convite "ou passe o crachá" |
| `03-cracha-sem-resposta.png` (antes) | a Joyce passou o crachá: o diálogo segue aberto, nada aconteceu |
| `03-venda-fechada-com-o-cracha.png` (depois) | a Joyce passou o crachá: o diálogo fechou e a venda fechou |

## A auditoria (`auditoria.txt`)

- **Antes:** zero conferências em `/pos/manager-approval/check/` depois do crachá, e o
  diálogo aberto, nos dois tamanhos.
- **Depois:** uma conferência pelo crachá, 200, nenhuma pelo PIN; o diálogo fecha e a venda
  fecha. No servidor, `pos_manager_override action=sale_approval_check ... approved_by=joyce
  via=badge`, e os dois pedidos ficaram com `approved_by=joyce`.
- **Texto do diálogo:** título 13,67:1 (16 px), descrição, "Quem autoriza?" e o convite
  do crachá 6,52:1 (14 e 12 px); nada cortado, nada fora da tela, nada encoberto, tudo na
  mesma borda.
