# WP-E5: receber o saldo pelo Pagamento (prévia)

Plano: `docs/plans/EXCELENCIA-PDV-PLANO.md`, WP-E5 (fecha P1-3, P1-6 cancelar encomenda,
P2-14). Regra do dono (16/11/2026): gesto de dinheiro tem uma tela só.

## Como foi capturado

- **PDV de verdade**: Django local (`:8075`, banco local `shopman_pdv_e5`, `seed --flush`),
  PDV e Cozinha em build de produção, worker de directives ligado, host próprio
  `pdve5.localhost`. Nunca produção.
- **Papéis**: Joyce (Gerente) iniciou o dispositivo com senha e vinculou o posto; Fran
  (Caixa) operou com PIN; Joyce assinou o cancelamento com o próprio PIN, escolhida da
  lista. Nunca o superusuário.
- **Tudo pela tela**: a encomenda nasce na própria jornada (Encomendas, Nova encomenda,
  cliente Ana Ferreira, hoje, retirada, a pagar na retirada) e é aberta pela lista das
  Encomendas, como quando a cliente chega.
- **Antes**: `main` em `ce9f77da2`, compilado à parte. **Depois**: o branch do PR.
- **Ajustes declarados do ambiente** (nenhum muda regra de negócio):
  - trava automática do PDV principal em 900 s (o mesmo do harness, `scripts/run_pos_e2e_live.sh`);
  - a captura do "depois" rodou depois das 18h de uma sexta: o horário de sexta da loja
    de teste foi estendido até 23h59 e o fim do expediente da equipe também (só no banco
    local `shopman_pdv_e5`), senão "Hoje" fica fechado e a encomenda do dia não nasce;
  - o produto da jornada é `PDV_LIVE_J6_PRODUCT` (Baguette de Tradition por padrão); na
    última passada foi Croissant, porque as passadas anteriores esgotaram a baguete do dia.
- **Jornada**: `surfaces/pos-nuxt/tests/e2e-live/j6-receber-e-entregar.live.spec.ts`
  (J6), 375 px (celular, toque) e 1366 px (balcão). A captura do "antes" usou a mesma
  criação de encomenda contra o `main` (só captura, sem critério).

## Antes (`antes/375`, `antes/1366`)

| Arquivo | O que mostra |
|---|---|
| `a01-detalhe-com-saldo.png` | o detalhe com "Receber R$ X e entregar" |
| `a02-dialogo-proprio.png` | o diálogo próprio de forma e troco (`PosPreorderHandOverDialog`): só Dinheiro, Débito e Crédito, campo livre de valor |
| `a03-troco-alto-sem-conferencia.png` | 9000 digitado: "Troco: R$ 8.972,80" em letra pequena, e o botão de confirmar aceso, sem conferência (P1-3) |
| `b01-cancelar-sem-o-valor.png` | cancelar a encomenda paga: o diálogo não diz quanto volta |
| `b02-gerente-sem-o-valor.png` | a Gerente assina "A venda já foi fechada.", sem o valor (P1-6) |

## Depois (`depois/375`, `depois/1366`)

| Arquivo | O que mostra |
|---|---|
| `a01-detalhe-com-saldo.png` | o mesmo gesto no detalhe |
| `a02-pagamento-com-o-saldo.png` | a MESMA tela de Pagamento da venda: "A receber" com o saldo; Dividir conta; as formas que a entrega recebe; teclado, cédulas, Exato e Limpar; à direita a encomenda (cliente, itens, desconto na própria linha, total, a receber); o aviso que trava é o primeiro conteúdo, abaixo das barras |
| `a03-troco-alto-pede-conferencia.png` | R$ 9.000,00 recebidos: a mesma conferência da venda (#2212), "Troco de R$ 8.972,80." com o botão "O troco está certo", e Receber travado |
| `a04-troco-grande.png` | nota de R$ 100,00: o troco é o número grande, "A receber" embaixo, Receber e entregar aceso |
| `a05-entregue-volta-a-lista.png` | entregue: "Recebido R$ X, com troco de R$ Y. Encomenda entregue." e o PDV de volta à lista |
| `b01-cancelar-mostra-o-valor.png` | cancelar a encomenda paga: "R$ X em dinheiro ficam a devolver no caixa." |
| `b02-gerente-ve-o-valor.png` | a Gerente assina vendo o mesmo valor (P1-6) |
| `b03-cancelada.png` | cancelada |

A Tela do cliente (segunda janela do mesmo navegador) mostrou "Total a pagar" com o saldo
enquanto o Pagamento estava aberto e voltou às boas-vindas depois da entrega: a jornada
confere as duas coisas.

## Auditoria

`auditoria.txt`, gerado pela própria jornada (`audits`, `noSideScroll`, `focusVisible`):
contraste do texto contra o fundo efetivo (mínimo 4,5:1), letra (mínimo 12 px), caixa
dentro da tela, nada cortado, nada encoberto (cada texto é rolado até o meio da área
visível antes de medir), transbordo horizontal zero, e o foco de teclado à vista.
Resultado: nenhuma linha reprovada nos dois tamanhos.

Notas da auditoria:

- O botão "Receber e entregar" desabilitado não entra na régua de contraste (controle
  inativo); habilitado, mede 4,95:1.
- No celular, com o Pagamento mais alto que a tela, a dica "tem mais abaixo" (`MoreBelow`)
  flutua sobre o pé até o operador chegar ao fim; a auditoria registra quando um texto
  está sob ela e não a conta como camada por cima.
- O próximo foco ao abrir é a primeira forma (Dinheiro), sem tirar o valor da vista. Pelo
  teclado (Tab), o foco chega ao "Receber e entregar" com anel.
- O aviso que trava ("Escolha a forma de pagamento.") é o da venda, sem botão próprio: as
  formas que o resolvem estão logo abaixo dele. O de troco alto traz o botão que resolve
  ("O troco está certo").
