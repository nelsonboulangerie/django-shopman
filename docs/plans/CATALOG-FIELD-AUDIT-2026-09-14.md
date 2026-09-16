# Auditoria de atributos de catálogo

Data: 2026-09-14. Base de código: `4fd373df05bfc369ec32d9d39c565e946bdd33f0`, worktree `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-ifood-catalog-safety-20260913`. Somente leitura do repositório; nenhum envio externo. Fontes oficiais consultadas nesta data; não equivale a homologação remota.

## Conclusão e prioridades

**P1: feed XML Google/Meta descarta atributos existentes e inventa ausência de identificador.** `shopman/shop/views/product_feed.py:102` monta itens sem ler `Product.metadata.social`; `shopman/shop/templates/feed/products.xml:14` fixa `condition=new`, usa uma marca global e envia `identifier_exists=no` incondicionalmente. GTIN, MPN, marca específica, condição específica, categoria Google e galeria podem estar cadastrados e não chegar ao feed. O teste `shopman/shop/tests/test_product_feed.py:50` fixa o comportamento incorreto de identificador.

**P1: não trocar o erro por outra inferência.** GTIN vazio significa dado não informado, não declaração de inexistência. Não gerar MPN a partir de SKU silenciosamente. Não usar nome da loja para produtos de outra marca. Google exige que `identifier_exists=no` seja sustentado pelo conhecimento de que não há identificadores atribuídos; identificador desconhecido deve permanecer desconhecido. [Google: identifier_exists](https://support.google.com/merchants/answer/6324478?hl=en).

**P2: dados de origem existem, mas não têm o mesmo significado entre plataformas.** Categoria Google é taxonomia comercial; coleção é curadoria local; categoria iFood é identidade remota. Não reutilizar uma string como se fossem equivalentes.

**P2: foto do produto não chega ao iFood.** `catalog_projection_ifood.py:131` explicitamente omite imagens. Existe `Product.image_url`, mas iFood usa upload e `imagePath`, não simplesmente URL externa. Preservar a imagem remota reconciliada antes de atualizar item completo; envio de nova foto exige fluxo próprio, não acrescentar uma chave `image_url` ao PUT.

**P2: TikTok não tem transporte de catálogo implementado nesta base.** Existe campo `tiktok_category_id` no cadastro, mas nenhum adapter de catálogo TikTok; `_AVAILABILITY` e validação do feed aceitam apenas Google/Meta. Mostrar atributo salvo não pode significar integração ativa.

## Matriz de envio demonstrada no código

| Atributo canônico | Google XML | Meta XML | Meta Graph adapter | iFood adapter | TikTok |
|---|---|---|---|---|---|
| SKU | g:id | g:id | retailer_id | externalCode e UUIDs derivados | Sem saída |
| Nome / descrições | Envia; descrição longa > curta > nome | Idem | Envia ProjectedItem + fallback nome | Envia ProjectedItem | Sem saída |
| Preço | resolve_prices(prices_from), fallback base | Idem | ListingItem.price_q em centavos | ListingItem.price_q convertido em reais | Sem saída |
| Pausa/publicação | Flags produto e paused_skus | Idem | Produto AND listing | Produto AND listing; retract UNAVAILABLE | Sem saída |
| Imagem principal | Envia URL; omite produto sem foto | Idem | Envia URL | Não envia | Sem saída |
| Galeria metadata.gallery | Não envia | Não envia | Envia até 10 adicionais | Não envia | Sem saída |
| social.brand | Ignora; marca global Shop.name | Idem | Envia; fallback default_brand | Não mapeia | Sem saída |
| social.gtin | Não envia | Não envia | Envia | Não mapeia para ean | Sem saída |
| social.mpn | Não envia | Não envia | Não envia | Sem equivalência afirmada | Sem saída |
| social.condition | Ignora; new fixo | Idem | Envia | Sem equivalência afirmada | Sem saída |
| social.google_product_category | Não envia | Não envia | Envia | Não é categoryId | Sem saída |
| Coleção primária/curadoria | product_type/custom_label da coleção do feed | Idem | custom_label_0 | map/default categoryId | Sem saída |
| social.tiktok_category_id | Não aplicável | Não aplicável | Não envia | Não aplicável | Cadastrado, não consumido |
| hashtags/social_caption | Não envia | Não envia | Não envia | Não envia | Conteúdo social, não contrato de catálogo demonstrado |

A coluna Meta Graph é inspeção do código existente, não confirmação de validade de cada nome de campo no contrato Meta atual. Não transpor nomes de campos RSS diretamente para Graph sem conferir referência específica.

## Reaproveitamento preciso

- `packages/offerman/shopman/offerman/contrib/social/schema.py:54`: `ProductSocialAttributes` já valida GTIN e condição e oferece parser de metadata. Reaproveitar no feed; não manter segundo parser divergente.
- Corrigir também documentação/help text desse schema e `contrib/social/admin.py:50`: ambos associam vazio a ausência de identificador. Se houver declaração explícita nova, preservar três estados: desconhecido, identificadores existentes, ausência confirmada.
- `packages/offerman/shopman/offerman/service.py:393`: `get_projection_items` já carrega social e gallery em ProjectedItem.metadata. Meta os recebe; iFood ignora o bloco.
- `shopman/shop/adapters/catalog_projection_meta.py:116`: já exporta marca, GTIN, condição, categoria e imagens adicionais. MPN está ausente, mas nome do atributo Graph adequado precisa de confirmação oficial antes da alteração.
- Nome da loja como marca é aceitável quando ela é fabricante ou marca própria, não como preenchimento indiscriminado de revenda. O próprio fabricante pode atribuir MPN próprio conscientemente; isso não justifica inferir para produtos de terceiros. [Google: identificadores únicos](https://support.google.com/merchants/answer/160161?hl=en).

## Especificidades oficiais e limites

**Google:** identificação depende de categoria e identificadores atribuídos; omissão não autoriza valor falso. Não adicionar atributos de vestuário (cor, gênero, tamanho) à padaria por existirem no schema geral. [Especificação](https://support.google.com/merchants/answer/7052112?hl=en-IE).

**iFood FOOD:** documentação atual de endpoints apresenta upload base64 de JPG/JPEG/PNG até 5 MB e retorno `imagePath` reutilizável. Inventário usa `productId` e quantidade em endpoint próprio; não confundir com status AVAILABLE. [Endpoints FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints). Guia oficial de uso apresenta campos `ean`, `additionalInformation`, `serving`, além de `imagePath`; `social.gtin` não deve ser copiado para `ean` sem compatibilidade de formato e contexto (GTIN admite mais formatos que EAN). Não inferir porções a partir de peso nem alergênicos a partir do nome. [Uso da API](https://developer.ifood.com.br/en-US/docs/guides/modules/catalog/using-api).

**TikTok Ads Catalog:** a página oficial lista nove obrigatórios: sku_id, title, description, availability, condition, price, link, image_link, brand. Opcionais incluem gtin/mpn, google_product_category, product_type, additional_image_link e shipping_weight. Não aparece `tiktok_category_id` nessa referência. Portanto o campo atual pode pertencer a outro produto/contrato e não deve ser enviado arbitrariamente. TikTok Ads Catalog não equivale a TikTok Shop. [Parâmetros oficiais](https://ads.tiktok.com/resources/help/article/catalog-product-parameters?lang=en) (página informa atualização fevereiro/2025, consultada hoje).

**Meta:** tentativa de abrir a referência oficial `developers.facebook.com/docs/marketing-api/catalog/guides/product-catalog/` falhou na ferramenta e buscas específicas não retornaram referência utilizável. Requisitos atuais do Graph, incluindo nome de MPN e limites de imagem, permanecem NÃO VERIFICADOS nesta auditoria. Isso não invalida os gaps demonstrados no código, mas impede classificá-los como exigência contratual atual. Não recorrer a blogs como autoridade técnica substituta.

## Testes mínimos antes de corrigir/publicar

1. XML com GTIN válido, MPN e marca específicos: mantém valores exatos, escapa XML e nunca emite identifier_exists=no por padrão.
2. Produto sem identificadores preenchidos: mantém estado desconhecido; ausência explicitamente declarada recebe regra separada; cadastro contraditório é rejeitado ou diagnosticado.
3. Revenda com marca específica e produção própria: fallback da loja não sobrescreve nem inventa marca de terceiros.
4. Condition used/refurbished não vira new; categoria Google é exportada sem usar coleção como taxonomia.
5. Galeria: ordem, dedupe da principal, limites por plataforma, URLs válidas e escape; manter principal existente.
6. Preço no feed coincide com canal de compra e landing page, inclusive preço diferente do base; alteração de atributos não muda preço.
7. iFood: imagem remota preservada em atualização parcial; upload falho não apaga foto nem marca sincronização completa; EAN só para valor compatível; estoque e porções não inferidos.
8. Separar testes XML, Graph e FOOD: sucesso em um formato não aprova outro. A integração TikTok deve continuar explicitamente indisponível até existir transporte validado.
9. Regressão de cadastro: campos apenas informativos de integrações não entram automaticamente no patch genérico de produto.

## Correção preparada após a auditoria

O XML passa a ler `get_social_attributes(product)` e exportar marca, GTIN, MPN, condição e categoria Google cadastrados. Não usa Shop.name como marca de cada produto nem afirma `identifier_exists=no` incondicionalmente. A marca da loja continua apenas no título do feed. Não há novo campo ou migração. A declaração explícita de ausência de identificadores permanece uma lacuna identificada; até ser modelada, desconhecimento não é exportado como ausência comprovada.

Validação: 33 testes de feed e schema social aprovados, incluindo escape XML, marcas de revenda, GTIN, MPN sem GTIN, condição, pausa por canal e preço da oferta de destino. `make admin`: gate canônico e 270 testes aprovados. A alteração de Admin é somente texto de ajuda. Não houve inspeção visual atual no navegador nem homologação remota.
