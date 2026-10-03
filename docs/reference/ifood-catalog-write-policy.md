# Escrita de catálogo iFood: bloqueio por padrão

O adapter e o comando `sync_catalog_ifood` negam escrita por padrão, antes de OAuth
ou HTTP. A guarda cobre upsert, pausa/retirada e os helpers de transporte chamados
diretamente. Pedidos, polling e negociações não usam esta política.

Para um ensaio autorizado, um arquivo de settings **isolado de teste** pode definir
`SHOPMAN_IFOOD_CATALOG_WRITE_POLICY` como um dicionário com:

| Campo | Contrato |
|---|---|
| `environment` | String exata `test`. Nenhum outro ambiente é aceito. |
| `merchant_allowlist` | Lista não vazia de strings UUID canônicas de merchants comprovadamente de teste. O `SHOPMAN_IFOOD.merchant_id` atual deve pertencer exatamente à lista. |

Ausência, boolean, string no lugar da lista, UUID inválido ou merchant fora da lista
negam o envio. Não há variável de ambiente, boolean de liberação geral ou inferência
pelo nome da loja/host. Nenhuma configuração real é alterada por esta implementação.
`IFOOD_CATALOG_PROJECTION=1` apenas registra o backend e **não** autoriza escrita.
`--dry-run` continua disponível sem essa permissão e não solicita OAuth.

A natureza de teste do merchant é uma declaração explícita do administrador, não
uma certificação consultada na API. Quem controla settings pode declarar um UUID de
produção; portanto a lista precisa ser conferida no portal e aplicada apenas ao
runtime isolado autorizado. A guarda não promete impedir alteração maliciosa de
código/configuração por um administrador.

## Caminhos automáticos e limites

Sinais de produto/preço/disponibilidade, publicação pelo Gestor e reenvio podem
continuar enfileirando `catalog.project_sku` quando o backend está registrado. A
execução passa pelo adapter, que retorna erro de bloqueio sem OAuth/HTTP. O handler
existente registra erro de sincronização e aplica sua política normal de retries;
a guarda não descarta diretivas nem finge sincronização bem-sucedida.

`CatalogService.project_listing`, o CLI e os helpers diretos também são protegidos.
A guarda não cria uma exclusão mútua entre o CLI e workers: a proteção de concorrência
existente do handler continua limitada ao caminho `catalog.project_sku`.

Se a política mudar durante uma chamada HTTP já iniciada, não é possível desfazer
essa chamada. A validação é repetida antes de cada PUT/PATCH; uma chamada já em voo
não é cancelada retroativamente. Para ensaio de catálogo, não habilitar envio do
catálogo local de exemplo para o merchant de produção.

## Estoque: o item esgotado sai indisponível

Desde a UX-R2 (decisão do dono, 03/10/2026) o status enviado não olha só
publicado/vendável: o upsert sai `UNAVAILABLE` quando o produto não tem estoque
para oferecer, e volta `AVAILABLE` quando tem. A regra é a do portão de pedido
(`availability.decide` com uma unidade, no escopo do canal `ifood`), via
`shopman/shop/services/external_availability.py`: produto sem rastreio de estoque
e política `demand_ok` seguem disponíveis; fornada planejada aceita pela política
`planned_ok` conta como disponível. A pausa (global ou do canal) continua vencendo.

O gatilho é a passagem por zero e a volta registradas pelo `ShelfOutage`
(`backstage/services/shelf_outages._apply`, por evento de estoque/reserva e pela
reconciliação periódica do `maintenance_worker`): cada transição enfileira
`catalog.project_sku` com `trigger="stock_changed"` para os canais empurrados cujo
estoque vem daquele canal. Diretiva ainda na fila absorve a seguinte, e o handler
lê o estado na hora de enviar: zerar e voltar em seguida converge para o estado
final. O mesmo vale para o catálogo da Meta (`catalog_projection_meta`), que lê o
estoque do canal apontado por `display.prices_from`. O feed público Google/Meta
(`views/product_feed.py`) calcula o mesmo na hora em que a plataforma o busca.

Tudo isso passa pela política de escrita acima: sem ela, a diretiva registra o
bloqueio como antes.
