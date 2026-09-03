# WP — A linha do PDV ganha identidade própria

> Estado: **em execução**, decidido pelo Pablo em 02/09/2026, pré go-live.
> Substitui a invariante "uma linha por SKU" pela identidade durável que o Core
> **já tem**. Apaga a ponte construída no mesmo dia (contador de rodadas).

## A decisão, em uma frase

**A linha do carrinho deixa de ser identificada pelo SKU e passa a ter `line_id`
próprio. Ela agrega o mesmo SKU apenas enquanto NÃO foi enviada à cozinha.**

## Por que agora, e não depois

O defeito que abriu o assunto: pedir mais um do mesmo item não chegava à cozinha.
A causa não era o botão — era o modelo. Com uma linha por SKU, "mais um chá"
vira `qty: 2` numa linha já disparada, e o ledger do KDS deduplica por `line_id`.
Consertamos com um contador de rodadas (`fired_qty` + ids `<line_id>#r<n>`), que
funciona e está provado, **e é ponte**: ele codifica "duas rodadas" dentro de uma
linha só porque a linha não sabe ser duas.

O que decidiu a favor de mudar agora:

1. **O Core já é identificado por linha.** `Session._normalize_items` preserva
   `raw["line_id"]` e só gera quando falta; `ModifyService.add_line` aceita
   `line_id` explícito — e o comentário lá cita nominalmente o PDV: *"permite
   re-emitir uma linha mantendo sua identidade durável — ex.: o PDV reconstrói a
   comanda no fechamento sem perder o vínculo com o ticket de KDS já disparado"*.
   Quem deduz identidade de SKU é **só a superfície**. Não é migrar o Core; é a
   superfície alcançar o Core.
2. **Identidade derivada de chave de negócio é fábrica de defeito.** O
   `_replace_session_ops` hoje *adivinha* qual linha nova é qual linha velha pelo
   SKU (`line_id_by_sku.pop(sku)`), e o comentário dele já confessa o risco:
   sem esse remendo, "o pedido committado dispara DE NOVO pra cozinha — comanda
   preparada em dobro".
3. **Agregar continua trivial; o contrário é impossível.** Recibo, tela do
   cliente e estoque agrupam por SKU na hora de desenhar. De identidade para
   agregado se vai sempre; de agregado para identidade, nunca.
4. **Destrava o que nenhum contador alcança**: observação e desconto por rodada
   ("o segundo sem lactose"), e status da cozinha por linha.

## Contrato (a fronteira entre as duas frentes)

### Payload de `save_pos_tab` — `items[]`

```jsonc
{
  "line_id": "L-XXXXXXXX",   // NOVO. Gerado pelo cliente ao criar a linha.
  "sku": "CHA-BLEU",
  "name": "Chá Bleu",
  "qty": 2,
  "unit_price_q": 1400,
  "notes": "",
  "discount": { "value": 10, "reason": "cortesia", "type": "percent" }
}
```

- `line_id` **ausente** → o servidor gera (é o que `_normalize_items` já faz).
  Não há compat a manter: o cliente sempre manda.
- Duas linhas com o **mesmo `sku`** são legítimas e não são fundidas por ninguém.

### Projection do tab — `items[]`

Já carrega `line_id`. Passa a valer:

- `fired` — booleano por **linha** (a linha foi inteira; não existe meia-linha).
- `fired_qty` — quanto daquela linha foi à cozinha. **Continua existindo**, com
  uma função só: detectar SOBRA (linha enviada que depois encolheu). Escrito uma
  vez no fire, apagado no unfire.
- `kitchen_status` — passa a ser **por linha**, não por SKU.

## Frente A — Servidor (`shopman/**`, `packages/**`)

1. **`build_session_ops`** (`shopman/shop/services/pos.py`): o `add_line` passa a
   incluir `"line_id": item.get("line_id")` quando o payload traz.
2. **`_replace_session_ops`**: **apaga o `line_id_by_sku`** e a preservação por
   SKU. A identidade vem do payload; o remendo perde a razão de existir.
3. **`fire_pos_tab`**: volta a ser "dispara as linhas ainda não disparadas"
   (dedupe por `line_id` contra o ledger). **Somem**: o cálculo de diferença, os
   ids de rodada `<line_id>#r<n>` e a regra de transição da ausência de
   `fired_qty`. **Fica**: gravar `fired_qty[line_id] = qty` no disparo.
4. **`cancel_fired_pos_tab_lines`**: some a expansão de rodadas (`#r`); segue
   limpando `fired_qty` das linhas alvo.
5. **`_kitchen_status_by_sku` → por `line_id`** (`shopman/backstage/projections/pos.py`).
   Os *itens* do ticket já carregam `line_id`; a docstring que diz o contrário
   fala do ticket, não do item. Empate entre estações: vence o MENOS avançado,
   como hoje.
6. **`_manual_discount_originals` → por `line_id`**: o `DiscountModifier`
   (`shopman/shop/modifiers.py`, `discounts_applied.append`) passa a gravar
   `"line_id": item.get("line_id")` junto do `sku`. A projection lê por
   `line_id`. Sem isso, o desconto de uma linha vaza para a outra do mesmo SKU.
7. **Docs**: `docs/reference/data-schemas.md` — reescrever a linha do `fired_qty`
   (some a rodada) e registrar que `items[].line_id` vem do cliente.
8. **Testes**: duas linhas do mesmo SKU sobrevivem a save/reload com os ids;
   desconto e observação não vazam entre elas; fire dispara só a nova; commit não
   re-dispara (o teste que já existe tem que continuar verde); status da cozinha
   por linha.

## Frente B — Superfície (`surfaces/pos-nuxt/**`)

1. **`POSCartItem.line_id` passa a ser a chave da linha.** O cliente gera ao
   criar (`L-` + 8 chars). Nada mais é chaveado por SKU.
2. **`pushProduct`**: procura linha do mesmo SKU **que não tenha sido enviada**;
   achou, incrementa; não achou, **cria linha nova**.
3. **Re-chavear por `line_id`**: `setQty`, `increment`/`decrement`, `remove`,
   `restoreItem`, `setLineNotes`, `setLineDiscount`, `freshLineIdsForSkus` (vira
   por linha), a seleção múltipla (`presentation/selection.ts`), `selectedSku`/
   `activeSku`, o `:key` da lista e o diálogo de observação.
4. **`productQty(sku)`** (o contador no grid de produtos) passa a **somar todas
   as linhas** daquele SKU — é a única leitura que continua agregando, e é view.
5. **`presentation/kitchen.ts`**: `pendingKitchenQty` some (linha é enviada ou
   não). `unfiredCount` segue contando UNIDADES das linhas não enviadas.
   `kitchenSurplusQty` e o selo âmbar **ficam** (linha enviada pode encolher).
   Some o selo "X de Y na cozinha" — não existe mais meia-linha.
6. **Não tocar** em `app/generated/posContract.ts` (é da Frente A).
7. **Testes**: `pushProduct` cria segunda linha depois do envio e agrega antes;
   desconto/observação/qty operam na linha certa com SKU repetido; o badge do
   grid soma as duas; a seleção múltipla distingue as linhas.

## O que NÃO muda

- **A conta do cliente continua agregando por SKU** onde já agregava (recibo,
  tela do cliente): é decisão de renderização, e ela não muda com este WP.
- O ledger do KDS segue autoritativo e por `line_id`.
- O `fired` continua vindo da Projection, nunca decidido na tela.

## Aceitação (verificação ao vivo, no `:3012`)

1. Toca chá → envia → toca chá de novo: nasce **segunda linha**, o botão acende
   "Enviar 1", e a cozinha recebe um ticket novo com **1**.
2. Antes de enviar, tocar duas vezes continua fazendo **uma linha com qty 2**.
3. Desconto e observação numa das linhas não aparecem na outra.
4. Uma linha "Pronto" e a outra "A enviar", ao mesmo tempo, no mesmo SKU.
5. Reduzir/remover linha enviada acende o selo âmber de sobra.
6. Fechar a venda não re-dispara nada para a cozinha.

## Risco conhecido

O toque no `DiscountModifier` é **core de pricing**. É uma linha (gravar o
`line_id` no registro), mas mexe no caminho de preço de toda a casa — roda
`make test` inteiro antes de commitar, não só os testes do PDV.
