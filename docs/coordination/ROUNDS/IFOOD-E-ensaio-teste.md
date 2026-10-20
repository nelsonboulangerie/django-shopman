# IFOOD-E — ensaio na loja de teste

- **id:** IFOOD-E
- **sessão:** frente 6, turno 5b, 20/10/2026 (Codex)
- **branch:** `codex/ifood-ensaio`
- **PR:** #1929
- **estado:** EM_PR; turno 5b parou no preço; turno 5c (Claude) corrigiu o preço, provou
  preço, alterações rápidas e descrição, e parou na categoria; item restaurado nas duas vezes
- **execução:** 2026-10-20 20:59:46–20:59:49 UTC (17:59:46–17:59:49 em São Paulo)
- **ordem:** `ORDERS/next-ensaio.md`, autorização expressa para um merchant e um SKU

## Preparação

Atualizado com `origin/main` em `65b658d31`. O conflito de merge estava somente no BOARD;
preservado o BOARD atual, sem ressuscitar a frente de importação/exportação já entregue.
As dependências #1905, #1931, #1947 e #1948 já estavam mergeadas.

Runtime privado com SQLite próprio, cache em memória, nenhum worker compartilhado e execução
manual das diretivas exclusivas do ensaio pelo handler canônico. Código de `packages/*` carregado
explicitamente da worktree; interpretador da `.venv` principal. Credenciais lidas diretamente do
`.env` ignorado, somente em memória. Nenhum segredo copiado para evidência, banco ou Git.

Política somente no processo isolado:

```json
{"environment":"test","merchant_allowlist":["f36a17d0-e10b-4fdd-a16d-c8ffd866e59b"]}
```

O `sync_catalog_ifood --dry-run` confirmou **um** item, `SHOPMAN-TEST-ADAPTER`, por R$ 19,90.
Vínculo local confirmado contra a captura remota, sem diretiva anterior pendente. Uma trava
adicional no transporte limitou as escritas ao merchant e ao item autorizados. Sem loja real,
sem sincronização do catálogo inteiro e sem alteração de código de produção.

## Baseline e identidade

- merchant: `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`, app `NB Teste (C)`;
- catálogo/contexto: `343e3649-18eb-4c08-99b4-4302df1cdf5e` / `DEFAULT`;
- item: `37c7f299-d753-50ed-9393-ec7f62e0af4f`;
- produto: `16baacff-c490-5805-872a-44210ae4d721`;
- categoria: `1d097d39-0ce0-47a6-ad6b-1ab9f4d9692a` (`Categoria Item Normal`);
- estado inicial: `UNAVAILABLE`, preço `{"value":19.9,"originalValue":19.9}`, `imagePath=""`;
- descrição: `Empurrado pelo Ifoodcatalogprojection real.`;
- índice `0`, sem complementos, contexto e identidade preservados.

As capturas integrais ficaram em diretório privado `0700`, fora do Git, com arquivos `0600`.

## Recibos e leituras remotas

Todos os horários abaixo são UTC em 20/10/2026. Endpoints relativos a
`/catalog/v2.0/merchants/f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`.
Todos os HTTP abaixo responderam `200`, sem `Retry-After`.

| Passo | Escrita | Leitura `GET /items/{itemId}/flat` | Resultado |
|---|---|---|---|
| Pausar | 20:59:46.283, `PATCH /items/status`, `UNAVAILABLE` | 20:59:46.903 | Sem diferença do baseline. Diretiva 1, `availability_changed`, recibo `retracted`. |
| Retomar | 20:59:47.303, `PATCH /items/status`, `AVAILABLE` | 20:59:47.852 | Somente status do item/contexto alterado. Diretiva 2, recibo `synced`. |
| Preço | 20:59:48.123, `PATCH /items/price`, `{"itemId":"37c7f299-d753-50ed-9393-ec7f62e0af4f","price":{"value":20.91}}` | 20:59:48.646 | `price={"value":20.91}` no item e no contexto. `originalValue` desapareceu. Diretiva 3, `price_changed`, recibo `synced`. Conferência do ensaio interrompida. |

O PATCH de preço enviou somente `itemId` e `price.value`; nenhum texto, categoria, índice,
turno, imagem ou contexto foi enviado. A confirmação atual do adapter compara `price.value`
e aceitou R$ 20,91. A conferência adicional do ensaio exigiu que `originalValue=19.9` continuasse
presente e falhou. **Isso evidencia uma diferença entre o critério do ensaio e a confirmação
do adapter; não prova, sozinho, defeito do adapter ou rejeição do preço pela API.** Nenhuma
mudança de produção foi inferida a partir dessa exigência adicional.

Conforme o item 4 da ordem, o ensaio parou na primeira divergência, sem repetir a intenção.
**Não executados:** duas alterações rápidas de preço, pausa/retomada rápidas, descrição,
movimento de categoria e foto. Não há evidência de aprovação dessas etapas.

## Restauração

Novas intenções explícitas, sem retentativa do passo interrompido:

1. 20:59:49.185: `PATCH /items/price` com `{"value":19.9,"originalValue":19.9}`;
2. 20:59:49.426: `PATCH /items/status` com `UNAVAILABLE`;
3. 20:59:49.679: GET completo confirmou **zero diferenças** contra o baseline do item,
   incluindo produto, descrição, imagem, categoria, índice, complementos e contextos;
4. fila privada com zero diretivas `queued`/`running`; backend desregistrado e política removida.

A captura integral final terminou às **21:00:18 UTC** (18:00:18 em São Paulo). Comparação exata
de `merchant_id`, `catalog_id`, `context`, `categories` e `category_items`: todos iguais à
captura inicial. O GET flat também é idêntico. Zero diretivas pendentes; banco SQLite privado
fechado e destruído. Token removido do cache e credenciais removidas dos settings do processo,
que foi encerrado. As credenciais originais do dono não foram revogadas nem alteradas.

Verificação documental: `git diff --check` sem erros. Não houve alteração de implementação
nem execução de testes simulados como substituto da evidência remota acima.

## Continuidade

O ensaio completo continua sem aprovação. Antes de um novo ensaio, definir se a conferência do
preço deve preservar `originalValue` ou acompanhar o contrato atual que confirma `price.value`.
Este PR publica a evidência e a interrupção segura; não declara descrição, categoria ou foto
validadas remotamente. Nenhuma nova sessão ou PR duplicado foi aberto.

---

# Turno 5c — 20/10/2026, 21:15–21:20 UTC (Claude, `claude/ensaio-pedidos-execucao-a13c08`)

Segue o adendo do `originalValue` da ordem `next-ensaio.md`: corrigir, provar por payload,
repetir do preço em diante e restaurar.

## Correção

`_patch_item_price` passou a mandar `price = {"value": v, "originalValue": v}`, como o
upsert. Teste de payload: `test_adapter_price_change_uses_specific_patch_and_confirms_read`
exige os dois campos. `test_catalog_projection_ifood.py` + `test_ifood_lifecycle_e2e.py`:
52 passed.

## Runtime

Settings próprios fora do Git (importam `config.settings`), SQLite privado `0700`, cache
em memória, `MEDIA_ROOT` privado. Do `.env` do dono só `IFOOD_CLIENT_ID`,
`IFOOD_CLIENT_SECRET` e `IFOOD_MERCHANT_ID` (conferido igual ao merchant de teste), em
memória. Política só no processo:
`{"environment":"test","merchant_allowlist":["f36a17d0-e10b-4fdd-a16d-c8ffd866e59b"]}`.
Backend registrado só ali. Trava no transporte: escrita fora de `/merchants/f36a17d0…`, de
`itemId` diferente de `37c7f299…` ou GET fora do iFood aborta antes do HTTP.

Fluxo canônico: edição local (`ListingItem`, `Product`, mapa de categorias) → sinal →
`catalog.project_sku` → handler → adapter, com despacho no commit. Dry-run: **1** item,
`SHOPMAN-TEST-ADAPTER`. Identidade derivada = `37c7f299…`/`16baacff…` da captura.
Baseline (GET flat 21:15:20 UTC) igual ao do turno 5b.

## Recibos

UTC, endpoints relativos a `/catalog/v2.0/merchants/f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`,
sem `Retry-After` em nenhum.

| Passo | Escrita | Leitura flat | Resultado |
|---|---|---|---|
| (preço com item pausado) | 21:17:34.702 `PATCH /items/status` `UNAVAILABLE`, 200 | 21:17:35.570 | Sem diferença. Pausado, o handler **recolhe** em vez de mandar preço (por desenho). Diretiva 2, `retracted`. |
| Retomar | 21:17:47.274 `PATCH /items/status` `AVAILABLE`, 200 | 21:17:48.161 | Só o status (item e contexto). Diretiva 3, `synced`. |
| **Preço** | 21:17:49.961 `PATCH /items/price` `{"value":20.93,"originalValue":20.93}`, 200 | 21:18:00.166 | `value` **e** `originalValue` = 20.93 no item e no contexto; nada mais mudou. Diretiva 4, `synced`. **A divergência do 5b está resolvida: enviado, o iFood guarda o `originalValue`.** |
| Rápidas, 2 preços | 21:18:09.557 e 21:18:10.163 `PATCH /items/price` `22.49/22.49`, 200 | 21:18:10.995 | 21,37 e 22,49 na mesma transação: duas diretivas (5, 6), as duas leram o estado na hora e mandaram 22,49. Convergiu para a última intenção. |
| Rápidas, retomar→pausar→retomar | 21:18:13.076 `PATCH /items/status` `AVAILABLE`, 200 | 21:18:14.894 | Três saves viraram **uma** diretiva (7), que mandou o estado final. Sem anúncio paralelo. |
| **Descrição** | 21:18:23.818 `PUT /items`, 200 | 21:18:25.014 | Só `products[0].description`. `serving`, `tags`, `weight`, `imagePath`, `index`, contexto preservados. Diretiva 8, `synced`. |
| **Categoria** | 21:18:32.980 `PUT /items` com `categoryId=1470ab8d…` (Pizza), **400** | 21:18:33.879 | **Falhou. Nada mudou no remoto.** Diretiva 9 ficou na fila de retentativa e foi neutralizada à mão (`failed`), sem nova tentativa. |

Causa, só por leitura (captura inicial): `Categoria Pizza` tem `template: PIZZA`; o item é
`DEFAULT`. O destino do roteiro estava errado, não o adapter. A única outra categoria
`DEFAULT` do catálogo é `Categoria Bebida` (`e4f00b97-ad97-4fe2-aad6-7c2026815e6c`); o
roteiro agora aponta para ela. Conforme o item 4 da ordem, não troquei o destino no meio do
ensaio: parei e restaurei. **Não executados: categoria (com destino válido) e foto.**

## Restauração

| Passo | Escrita | Leitura flat | Resultado |
|---|---|---|---|
| Mapa local de volta para `Categoria Item Normal` | nenhuma | 21:19:09.842 | — |
| Descrição | 21:19:11.798 `PUT /items`, 200 | 21:19:12.445 | Leitura ~0,3 s depois **ainda com o texto temporário**; a de 21:19:14.519 já com o original. O PUT é eventualmente consistente. |
| Preço | 21:19:14.246 `PATCH /items/price` `19.9/19.9`, 200 | 21:19:15.109 | Preço do baseline, com `originalValue`. |
| Status | 21:19:16.885 `PATCH /items/status` `UNAVAILABLE`, 200 | 21:19:17.905 | **Zero diferenças contra o baseline.** |

Captura integral final às 21:19:40 UTC: `merchant_id`, `catalog_id`, `context`,
`categories` e `category_items` iguais à captura inicial; GET flat de 21:19:42 com zero
diferenças. Zero diretivas `queued`/`running`. SQLite e mídia privados apagados; processo
encerrado; credenciais não alteradas. Capturas e recibos ficaram fora do Git, `0600`.

## O que o ensaio ensinou (registrado em `docs/reference/ifood-catalog-write-policy.md`)

1. Preço manda `value` e `originalValue` (corrigido neste PR).
2. Categoria remota tem template; item `DEFAULT` só cabe em categoria `DEFAULT`.
3. `PUT /items` é eventualmente consistente; `PATCH` de preço/status confirmou na primeira leitura.

Pendências com nome, fora deste PR: o erro `400` chega ao recibo sem o corpo da resposta do
iFood (`raise_for_status` descarta o motivo), e o handler trata `400` como transitório e
retentaria 5 vezes. Nenhum dos dois mudou o resultado do ensaio.

## Continuidade

Próximo ensaio: do movimento de categoria em diante (para `Categoria Bebida`), depois foto e
restauração completa, incluindo provar que `PUT items` com `imagePath: ""` limpa a foto. A
frente só fecha quando esse trecho fechar.
