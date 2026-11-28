# #2775: endereço do pedido de entrega sem etiqueta (loja, /conta/enderecos, 375 px)

- `enderecos-375-antes.png`: a página do `origin/main` com o dado de hoje. Os três
  endereços gravados por pedido de entrega dizem "Entrega", e só a linha de baixo
  distingue um do outro.
- `enderecos-375-depois.png`: a página deste branch com o dado depois da `shop.0123`.
  Uma função só (`savedAddressLines`) monta as linhas, no formato do PDV: a rua com o
  número e o complemento ("Rua Belo Horizonte, 88, Apto 12") e, embaixo, o bairro e a
  cidade ("Centro · Londrina/PR"), sem o CEP. Com etiqueta são três linhas (a etiqueta,
  a rua, o bairro e a cidade); sem etiqueta, duas (quem fala é o endereço).
- `*.audit.json`: medição de cada linha dos cartões (tamanho, peso, contraste contra o
  fundo do cartão, corte, transbordo). Título 16 px/600 com contraste 12,76; linhas de
  baixo 14 px com 6,09 (a mesma classe `shop-muted` de antes). Nada cortado, nada
  transbordando, sem rolagem lateral.

Como foi feito: `nuxt dev` da loja contra um mock do Django que devolve a sessão de
um cliente de teste e a lista de endereços no formato de
`shopman/storefront/api/account.py` (`label` é o `display_label` do guestman: "Entrega"
antes, "Outro" depois). Nenhum banco real, nenhum SMS ou e-mail.
