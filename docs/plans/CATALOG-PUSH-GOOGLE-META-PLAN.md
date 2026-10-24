# Envio do catálogo ao Google e à Meta (escritor único)

Decisão do dono, 24/10/2026: a disponibilidade é volátil (o pão acaba no meio do dia), e
o que o Google e a Meta mostram tem de acompanhar o Catálogo do Gestor em minutos, não na
busca diária do feed.

## A decisão: um escritor por plataforma

O nosso sistema é o **único** que escreve o catálogo em cada plataforma, pela API:

| Plataforma | Envio | Fonte na plataforma |
|---|---|---|
| Google | Merchant API, `productInputs:insert` (produto inteiro) | fonte de dados do tipo **API** |
| Meta | Graph `items_batch` | catálogo sem feed agendado |

Feed **e** API na mesma conta seriam duas fontes brigando: a busca do arquivo reescreve o
que a API acabou de mandar. Por isso o envio substitui o feed, não se soma a ele.

**Uma decisão, três tradutores.** Quem decide cada item (entra, preço, disponível,
oculto) é `shopman/shop/services/display_catalog.py`. O XML do feed
(`views/product_feed.py`), o envio ao Google (`adapters/catalog_projection_google.py`) e
o envio à Meta (`adapters/catalog_projection_meta.py`) só traduzem.

| Gesto no Catálogo | Google (API) | Meta |
|---|---|---|
| Pausar | `availability: OUT_OF_STOCK` | `availability: out of stock` |
| Ocultar | `excludedDestinations` = todos os destinos | `status: archived` |
| Saiu da composição do canal | `productInputs.delete` | `status: archived` |

Não usamos `productInputs.patch` para preço e disponibilidade: a atualização rápida por
atributo está restrita a contas liberadas pelo Google
([latest-updates](https://developers.google.com/merchant/api/latest-updates)).

## Quando o envio acontece

Na hora (diretiva `catalog.project_sku`, ADR-003, com retry e 429 respeitado):

- estoque zerou ou voltou (`external_availability.on_offer_changed`);
- Pausar/Ocultar no Catálogo, coleções do canal (`backstage/services/feeds.py`);
- preço da loja (canal de `prices_from`) e dados do produto;
- canal ligado ou desligado (desligado vai como fora de estoque, não some).

Rede de segurança: `sync_platform_catalogs` no `maintenance_worker` reenvia o SKU cujo
último envio passou de 24h (o Google expira produto sem reenvio em 30 dias) e retira o
que saiu do canal.

## Passos do operador (Google)

1. Projeto no Google Cloud da conta da empresa; ativar a **Merchant API**.
2. Criar uma **service account** e gerar a chave JSON.
3. No Merchant Center (conta 5881119366), **Configurações → Pessoas e acesso**: adicionar
   o e-mail da service account com acesso padrão.
4. No Merchant Center, **Fontes de dados**: criar uma fonte primária do tipo **API**
   (Brasil, português) e anotar o id. Depois **apagar a fonte do arquivo**
   (`/feed/google-shopping.xml`), para a API ser a única.
5. No Admin, `Shop.defaults["google_merchant"]` (dado da loja, ADR-042):
   `{"account_id": "5881119366", "data_source_id": "<id da fonte API>"}`
   (opcionais: `content_language`, padrão `pt`; `feed_label`, padrão `BR`).
6. No spec da DigitalOcean: `GOOGLE_MERCHANT_SERVICE_ACCOUNT_JSON` (tipo **SECRET**, o
   JSON inteiro) e `GOOGLE_MERCHANT_PROJECTION=1`.
7. `sync_platform_catalogs --dry-run --channel google-shopping` para conferir;
   `sync_platform_catalogs --force` para o primeiro envio.

## Passos do operador (Meta)

1. Catálogo no Commerce Manager e System User com o catálogo atribuído (já descrito em
   `docs/plans/completed/CATALOG-FEEDS-GOOGLE-META.md`).
2. Spec: `META_CATALOG_ID`, `META_ACCESS_TOKEN` (SECRET), `META_CATALOG_PROJECTION=1`.
3. Sem feed agendado no catálogo.

## Depois que os dois envios estiverem no ar

Apagar o feed XML inteiro (zero legado pré go-live): `ProductFeedView`,
`templates/feed/products.xml`, a rota `feed/<ref>.xml` em `menuboard_urls.py` e
`build_feed_items`. Fica só `display_catalog` com os dois envios. Não acontece neste PR
porque o Merchant Center de teste ainda lê o arquivo.

## Fora daqui

- Produto que entra numa coleção do canal não dispara sinal: chega na reconciliação
  (até 5 min, no ciclo do `maintenance_worker`).
- Frete e devolução do Merchant Center são configuração da conta, não do envio.
