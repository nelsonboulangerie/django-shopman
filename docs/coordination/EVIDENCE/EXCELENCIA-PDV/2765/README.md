# #2765: a troca vinda do link do Gestor, no PDV

PDV compilado (`nuxt build`) contra Django local semeado (`seed --flush`, banco local
`shopman_pdv_2765`, nunca produção). Quem opera é a Caixa (Fran), que entra com PIN depois
de a Gerente vincular o dispositivo ao posto: nenhum superusuário.

## Promessa em risco (`375/`, `1280/`)

A encomenda de amanhã com 4 Baguette de Tradition cujo lote de amanhã foi cancelado pela
Produção (o mesmo que `test_lote_cancelado_oferece_o_que_o_lote_da_data_tem_livre` monta),
aberta pelo link do "Trocar por" do Gestor: `/preorders/<ref>?swap=TRADI`.

- `01-lista-de-alternativas.png`: o foco no bloco "Trocar 4x Baguette de Tradition", o fato
  do aviso ("Faltam 4x Baguette de Tradition. O lote de amanhã foi cancelado.") e uma
  alternativa por linha, largura inteira, com o que o lote de amanhã cobre e a diferença de
  preço da encomenda.
- `02-conferencia.png`: Sai, Entra, Total antes, Total depois, Diferença e o que acontece com
  o dinheiro (a encomenda não paga: "O novo total é R$ 50,00, a pagar na retirada.").
- `03-depois-da-troca.png`: "Trocado: 4x Fendu no lugar de 4x Baguette de Tradition.", o
  bloco some, os itens e o saldo já são os novos. Esta é também a tela de antes deste PR: o
  `main` ignorava o `swap` e abria a encomenda sem o bloco.

O "40 livres" no celular e o "36 livres" no balcão são o lote de verdade: a troca do celular
reservou 4 Fendu antes de o balcão abrir a sua encomenda.

## Jornada J12, encomenda paga (`j12-paga/`)

`surfaces/pos-nuxt/tests/e2e-live/j12-troca-vinda-do-link.live.spec.ts`, 2 passed (375 e
1280 px): a Fran monta pela tela uma encomenda de 2 Baguette de Tradition para amanhã,
recebe em dinheiro, abre o link com `swap`, troca pela primeira alternativa e, como a
encomenda paga ficou mais barata, a Gerente (Joyce) assina da lista com o próprio PIN
(`03-gerente-autoriza-a-devolucao.png`).

## Auditoria (`auditoria-j12.txt`)

- Bloco da troca: menor contraste 6,09:1 (a linha "28 livres para amanhã" em tom suave);
  título e rótulos 12,76:1. Letras de 14, 16 e 18 px, todas na escala da casa.
- Conferência: menor contraste 6,52:1 (os rótulos Sai, Entra…); valores 13,67:1.
- Nada fora da tela, cortado, encoberto ou esmagado; `overflowX` 0 em 375 e 1280 px.
- Linhas das alternativas de borda a borda do bloco (32 a 343 px em 375; 256 a 864 px em
  1280), com 62 px de altura (86 px quando o nome quebra em duas linhas no celular).
- Botões da conferência (Voltar, Trocar por Fendu) com 44 px.
