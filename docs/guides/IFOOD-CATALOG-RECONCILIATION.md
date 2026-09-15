# Reconciliação local do catálogo iFood

O comando compara um inventário já obtido com os produtos canônicos do banco configurado. Não chama a API iFood, não consulta credenciais iFood, não publica anúncios nem grava vínculos, produtos, listings ou diretivas.

```sh
.venv/bin/python manage.py reconcile_ifood_catalog \
  --inventory /caminho/inventario-categorias.json \
  --merchant-id UUID-DA-LOJA \
  --catalog-id UUID-DO-CATALOGO \
  --context DEFAULT
```

O arquivo UTF-8 deve conter a lista completa de categorias, cada uma com `items`, resultante de `GET /catalog/v2.0/merchants/{merchantId}/catalogs/{catalogId}/categories?includeItems=true`. Não misture lojas, catálogos ou contextos. O comando exige o escopo declarado, mas não consegue comprovar a origem ou completude de um arquivo local. Categorias vazias são válidas.

A saída é JSON com `items` e `summary`. Cada ocorrência mantém loja, catálogo, contexto e IDs do item, produto e categoria. `external_code` representa o código efetivo no contexto; `root_external_code` preserva o código raiz. `candidate_skus` contém somente correspondências exatas. Nomes servem apenas para exibição.

`suggested` exige código único nos dois lados e continua dependendo de confirmação posterior. Códigos ou identidades repetidas ficam ambíguos; modificadores malformados e identidades incompletas impedem sugestão. Nenhuma ocorrência é descartada por compartilhar SKU. `summary.pending` inclui todas as ocorrências: executar o comando não conclui adoção ou homologação.

Arquivo ilegível, JSON inválido, escopo ausente, categoria conflitante ou inventário incompleto produzem `CommandError`, sem incluir conteúdo do arquivo ou detalhes de conexão. Arquivo vazio de categorias produz resultado vazio, sem provar que a loja está reconciliada.

Contrato: [referência oficial Catalog v2](https://developer.ifood.com.br/en-US/docs/references), esquemas `GetCategoryDto`, `GetItemDto` e `ItemContextModifierDto`.
