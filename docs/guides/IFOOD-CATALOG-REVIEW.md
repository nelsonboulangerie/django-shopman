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
