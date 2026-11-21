# WP-E3: encomenda além do plano (P1-1, P2-10)

PDV de verdade: Django local semeado (`seed --flush`, banco próprio por rodada), PDV
compilado, Caixa Fran com PIN, pela tela. Data da encomenda: daqui a dez dias (30/11/2026,
segunda); o seed planeja só a próxima semana, então a data não tem lote planejado.

## Antes (`origin/main` em 59bb2149a, banco `shopman_pdv_e3_antes`)

- `antes/{375,1366}/02-grade-sem-plano.png`: o Croissant diz "Sem saldo para 30/11" e fica inerte.
- `antes/{375,1366}/03-toque-sem-saldo.png`: o toque só repete "Croissant: Sem saldo para 30/11.".
- Medido na projeção, mesma data: 35 itens da grade bloqueados (o laudo dizia 35 de 122).

## Depois (este PR)

- `depois/375/01-grade-sem-plano.png`: o tile diz "Vira pedido à Produção" e lança no toque; a
  dica e o nome acessível levam a frase inteira.
- `depois/375/02-linha-sem-plano.png`: 30 croissants; a linha diz "Ainda sem lote planejado para
  30/11: vira pedido à Produção".
- `depois/375/03-pagamento-sem-gerente.png`: nada pede o gerente; a ressalva do item diz
  "Croissant: ainda sem lote planejado para 30/11. Vira pedido à Produção.".
- `depois/375/04-encomenda-registrada.png`: fecha em dinheiro, sem gerente.
- `depois/{375,1366}/101-plano-esgotado-bloqueado.png` e `102-toque-plano-esgotado.png`: com
  o lote de amanhã todo prometido (a J5 de 200 baguetes), a Baguette de Tradition segue "Sem
  saldo" e inerte. Acima do plano com lote livre, só o gerente libera (J5, WP-E2).
- Medido na projeção, mesma data e mesmo banco: 23 bloqueados, 12 viram pedido à Produção
  (Baguette de Tradition, Croissant, Ciabatta, Pain au Chocolat...). Dos 23: 12 chás de revenda
  (correto) e 11 itens da casa sem ficha no seed (#2925).

## O que a Produção vê (banco `shopman_pdv_e3_depois`, encomenda PDV-261120-T69)

- Reserva de 30 CRO para 30/11 como demanda sem lote;
- decisão gravada `available_qty 0, demand_qty 30, reason_code demand_over_plan`;
- aviso `order_demand_over_plan` ao público `production`: "Encomenda PDV-261120-T69: 30 Croissant
  para 30/11, e o plano da data cobre 0. Planeje mais 30 para 30/11 ou combine outra data com o
  cliente.";
- a sugestão de produção conta `committed = 30` para CRO em 30/11.

## Auditoria (`auditoria.txt`)

Por script, na J5 ao vivo: contraste (pílula 13,67; linha 6,52), letra ≥ 12 px, dentro da tela,
sem corte; borda (a pílula cabe no tile, 4 px de folga), foco (o tile recebe o foco do teclado
com anel visível) e alinhamento (o fato da linha começa na mesma coluna do nome: 74 = 74).

## Falta

A J5 a 1366 px com a data sem plano não chegou a rodar: a pausa do dono (20/11, 22h) parou a
rodada. A 375 px passou inteira (as duas jornadas da J5).
