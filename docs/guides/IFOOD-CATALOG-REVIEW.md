# Revisão local do catálogo iFood

Os produtos locais ainda são exemplos não revisados. O catálogo remoto deve ser preservado. Nenhuma aprovação de código autoriza atualização no iFood real: a revisão do usuário precisa abranger as alterações concretas antes de qualquer envio. Este comando não aprova, vincula, importa produtos, agenda diretivas nem acessa HTTP.

## Entrada completa, sem misturar lojas

`prepare_ifood_catalog_review` aceita um arquivo UTF-8 de até 20 MiB. O envelope abaixo é contrato local, não payload aceito pela API iFood:

```json
{
  "schema_version": 1,
  "merchant_id": "UUID da loja de origem",
  "catalog_id": "UUID do catálogo de origem",
  "context": "DEFAULT",
  "captured_at": "2026-09-14T10:00:00-03:00",
  "source": "imported_file",
  "categories": [],
  "category_items": []
}
```

- `categories`: resposta integral de `GET /catalog/v2.0/merchants/{merchantId}/catalogs/{catalogId}/categories?includeItems=true`.
- `category_items`: uma resposta integral de `GET /catalog/v2.0/merchants/{merchantId}/categories/{categoryId}/items` por categoria, inclusive as vazias. Cada resposta tem `categoryId`, `items` e, quando presentes, `products`, `optionGroups`, `options`.
- Os IDs de itens das duas leituras devem coincidir; repetição, desaparecimento ou mudança de produto exigem nova coleta. Não acrescentar credenciais, headers ou respostas de autenticação ao arquivo.

A leitura de categorias é resumida: seus modificadores de contexto não comprovam ausência de alterações de preço/status/código. A revisão usa os itens completos. Nome, descrição e imagem vêm de `products`, por `productId`; dados ausentes continuam ausentes. Preço/status/código efetivo usam o modificador do contexto selecionado quando o campo está presente, preservando os valores raiz separadamente. `itemContextId` é preservado. Complementos e campos desconhecidos ficam na cópia integral do snapshot; não são reescritos ou achatados.

A origem, loja/contexto e data são declarações de quem preparou o arquivo. O comando verifica consistência interna, não autenticidade nem completude na plataforma. A lista vazia é um arquivo consistente, não evidência de loja vazia. Não usar snapshots de merchants distintos ou de momentos incompatíveis.

## Preparar o relatório

```bash
.venv/bin/python manage.py prepare_ifood_catalog_review \
  --snapshot /caminho/privado/ifood-snapshot.json \
  --channel ifood > /caminho/privado/ifood-review.json
```

O canal local é selecionado explicitamente; seu nome não comprova vínculo com o merchant declarado. Não há leitura das credenciais para inferir essa associação.

O relatório contém SHA-256 dos bytes originais, snapshot preservado, candidatos locais por código exato e dados remotos separados dos dados locais. Números JSON fracionários são representados como strings decimais na saída para preservar precisão; guarde o arquivo original junto do relatório para conferir o hash. Preço base local e todas as faixas de preço da oferta são identificados separadamente, em centavos; não são comparados automaticamente ao preço remoto em reais. Referências de imagens são preservadas; não há download ou comparação visual automática.

Todos os itens continuam pendentes e `write_authorized`/`binding_confirmed` permanecem falsos, mesmo com código único. Códigos repetidos não colapsam ocorrências nem produtos. O campo `identity.status` é diagnóstico da reconciliação; disponibilidade remota está em `remote.item.status` e `remote.effective_context.status`.

O passo seguinte é revisar a evidência, adotar informações reais no cadastro local sob intenção explícita e só então confirmar associações duráveis. O relatório não é consumido por adapters de saída e não destrava sincronização. A gravação de vínculos e eventual publicação real são etapas distintas, ainda não implementadas por esta entrega.

## Fontes oficiais

Contrato consultado em 14/09/2026:

- [Referência OpenAPI oficial](https://developer.ifood.com.br/page-data/en-US/docs/references/page-data.json), especificação `catalog-v2`, schemas `GetCategoryItemsDto`, `ItemDto`, `ProductDto` e `ItemContextModifierDto`.
- [Contextos do catálogo](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/workflow).

A identidade exigida pelo validador é uma condição local para revisão segura. Alguns IDs não constam de `required` na OpenAPI; isso não justifica confirmar recursos sem identidade.

## Captura somente leitura pela API

`capture_ifood_catalog` produz diretamente o envelope aceito acima, com
`source="api_capture"`. Execute somente no runtime autorizado, com configuração do
merchant conferida, destino novo e diretório privado já existente (modo 0700):

```bash
.venv/bin/python manage.py capture_ifood_catalog \
  --merchant-id UUID-EXPLICITO --catalog-id UUID-EXPLICITO --context DEFAULT \
  --output /diretorio/privado/nova-captura.json
```

O comando exige UUIDs canônicos, igualdade exata com `SHOPMAN_IFOOD.merchant_id` e
`api_base` igual a `https://merchant-api.ifood.com.br` (barra final opcional), antes
do OAuth canônico. Força token novo para evitar reutilizar o cache global de outro
cliente/base. Autenticação usa POST OAuth; todas as chamadas de catálogo usam
somente GET. Ambos rejeitam redirects; erros não expõem corpo remoto ou credenciais.
Não há polling, ACK, escrita de catálogo, criação de diretiva ou consulta/escrita de
modelos pelo coletor.

A captura verifica `catalogId` e participação do contexto no array `context` de
GET catalogs, lê categorias com `includeItems=true` e as respostas completas de
itens, inclusive categorias vazias. Os três endpoints não documentam paginação.
Repete cada leitura completa de itens e a leitura de categorias/catálogo no final;
divergência rejeita a captura. Isso detecta mudanças observadas, não oferece snapshot
atômico nem comprova que nada mudou e voltou ao valor anterior entre chamadas.

`provenance` conserva `completed`, `rechecked`, `atomic_snapshot=false` e uma lista
`responses`: método, URL oficial sem headers, status, horário de recebimento,
`raw_body` UTF-8 integral e SHA-256 desses bytes. Números continuam números JSON no
snapshot, inclusive decimais de alta precisão; não se tornam códigos textuais. O
relatório de revisão continua sem atestar autenticidade de arquivo modificado.

Limites: 100 categorias, 5 MiB por resposta, 8 MiB somados nas respostas e 20 MiB no
arquivo final; orçamento de leitura 180 segundos, conexões até 5 segundos e leitura
por socket até 15 segundos. O timeout configurado do OAuth deve estar entre 1 e 30
segundos. Timeouts de socket não são um prazo absoluto para resolução DNS ou toda a
execução. Limite excedido, erro, cobertura divergente ou resposta parcial não produz
arquivo final. Não há retry automático: recapture deliberadamente em novo caminho.

A saída final é publicada somente após validação e gravação completas, com modo
0600 e criação exclusiva; arquivo existente ou symlink não é sobrescrito. As
respostas podem conter dados comerciais sensíveis: mantenha captura e relatório em
armazenamento privado. Este comando não habilita escrita nem concede autorização
para usar catálogo de exemplo em loja real.

Contrato GET catalogs confirmado na [referência oficial de endpoints](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints):
`catalogId` e `context` (array). Categorias e detalhes conforme OpenAPI citada acima.

Uma captura bem-sucedida não é evidência de homologação nem comprova autorização
para outra loja. Credenciais que acessam somente um merchant de teste continuam
restritas àquele escopo; o relatório não demonstra acesso ao catálogo de produção.
