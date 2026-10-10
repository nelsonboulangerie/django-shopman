# OBS0310-C · Ocultar indisponíveis no PDV e no Storefront

Pedido do dono (03/10/2026): opção de ocultar itens indisponíveis no PDV e no
Storefront, "ridiculamente fácil para o operador", com olho aberto/fechado ou
switch declarativo.

Branch `claude/obs0310-ocultar-indisponiveis`, PR #1410.

## O que mudou

**Só exibição. Nenhuma regra de disponibilidade mudou** (ver memória
`reference_pdv_e_disponibilidade_nao_era_problema`).

### PDV (`surfaces/pos-nuxt`)

- Botão de olho ao lado do botão de densidade, na linha da busca. Olho aberto =
  mostra tudo (padrão); olho fechado = esconde o que não pode entrar no pedido
  (o mesmo critério do selo do tile: esgotado ou sem preço). Rótulo acessível e
  `title` dizem a ação: "Ocultar indisponíveis" / "Mostrar indisponíveis".
- Fechado, um selo no olho mostra quantos dos resultados atuais estão ocultos.
- Busca ou coleção que só acha indisponível: "Nenhum produto disponível
  encontrado. N indisponíveis ocultos." com o botão "Mostrar indisponíveis".
- Lembrado por dispositivo em `localStorage["pos.hideUnavailable"]` (com
  try/catch). O kit não tem mecanismo de preferência por posto; segui o padrão
  da densidade da grade.
- Opção indisponível sai também do cartão de escolha (choice group).
- Lógica pura em `app/presentation/catalog.ts` (`hideUnavailableProducts`,
  `isUnavailableProduct`, `hiddenUnavailableLabel`, `parseHideUnavailable`).

### Storefront (`surfaces/storefront-nuxt`)

- Chave "Mostrar só disponíveis" no `/menu` e em `/colecao/<ref>`, no mesmo
  formato do filtro de preferências já existente (cartão com switch e linha de
  apoio). A linha diz quantos itens estão escondidos; ligada sem nada a esconder,
  diz que tudo pode ser pedido (zero não é código secreto). A palavra para o
  cliente é só "indisponível".
- A chave aparece quando há indisponível no cardápio, ou quando já está ligada.
- Vazio por causa da chave: "Nada disponível por aqui agora" + "Mostrar
  indisponíveis".
- O padrão é da casa; a escolha do cliente fica no navegador
  (`localStorage["shop.menu.availableOnly"]`) e vence o padrão.
- SEO/JSON-LD da coleção seguem lendo a coleção inteira.

### Casa (Admin)

- Admin › Loja › Cardápio: switch "Esconder indisponíveis no cardápio"
  (`UnfoldBooleanSwitchWidget`). Grava `Shop.defaults["storefront"]["hide_unavailable_by_default"]`
  (JSON que já existia, sem migração), projetado em
  `public_config.hide_unavailable_by_default`. Documentado em
  `docs/reference/data-schemas.md`.

## Fora do escopo

- Home, busca (overlay) e prateleira de favoritos do Storefront seguem mostrando
  tudo: o pedido era o catálogo/cardápio.
- O PDV não tem padrão da casa: é preferência do dispositivo, como a densidade.
