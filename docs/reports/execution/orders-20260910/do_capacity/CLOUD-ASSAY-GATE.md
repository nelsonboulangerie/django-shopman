# Decisão concreta: laboratório temporário na DigitalOcean

Estado: proposta pronta para decisão de custo; NÃO autorizado nem provisionado.
A autorização de publicar a integração transmitida pela tarefa PDV não inclui
novos recursos pagos. A publicação existente segue condicionada à validação.

## Por que esta ação

O backend ativo é1CPU/1GB em App Platform, com PostgreSQL16/Valkey8 gerenciados.
Os ensaios com teto equivalente no CI reprovaram500ms backend/1500ms browser;
candidato5leitores também reprovou em runner4CPU. O host local e o runner não são
a plataforma gerenciada: essa evidência impede liberar capacidade, mas não é
base suficiente para comprar aumento permanente. Precisamos medir nessa plataforma
com dados sintéticos e recursos separados, sem carga nos pedidos reais.

Não há promessa de que o teste passará. Um resultado negativo encerra a hipótese
de infraestrutura ensaiada e volta ao trabalho de capacidade; limites não mudam.

## Ação limitada submetida à aprovação

- Um app de laboratório novo emNYC, nome único `orders-capacity-<run-id>`.
- Backend Django: primeiro1 réplica1CPU/1GB; comparar até5 réplicas do mesmo porte,
  somente no laboratório. Gestor Nuxt:1 réplica1CPU/512MB.
- PostgreSQL16 novo1GB e Valkey8 novo1GB; banco/pool/usuário exclusivos do laboratório.
  Não usar os clusters shopman-staging existentes nem copiar dados ou credenciais deles.
- Imagens da fonte técnica exata, tag de laboratório exclusiva; nunca main/latest
  nem tags assinadas pelo app existente. Nenhum worker de efeitos.
- Mesma fixture500 pedidos/3 itens/6 eventos/10 aparelhos, mesmas permissões e
  confirmação; adapters inertes. Sem DNS da loja, gateways, mensagens, fiscal,
  courier real, despacho físico ou movimentação financeira.
- Duração máxima24h desde a primeira alocação; encerrar antes assim que houver
  evidência suficiente. Teto de cobrança adicional do provedor **US$5**, antes de
  impostos/câmbio. Não alocar se a cotação atual não couber nesse teto.
- Esta autorização, se concedida, inclui remover exclusivamente os recursos
  temporários criados para o ensaio após exportar métricas/evidência sanitizada.
  Não inclui mudança permanente de capacidade da loja nem relaxamento de budgets.

## Estimativa e fontes

API DO consultada11/09: backend1CPU/1GB US$12/mês por réplica, Nuxt512MB US$5/mês;
valores/hora-segundo estão em instance-prices.json. Documentação oficial:
[PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/)
e [Valkey](https://docs.digitalocean.com/products/databases/valkey/details/pricing/)
indicam entrada de US$15/mês por cluster1GB. Total nominal do conjunto: US$47/mês
com1 réplica backend, atéUS$95/mês com5. Para24h, reservar atéUS$5 como teto;
reconfirmar cálculo proporcional/arredondamentos antes de criar. Não é cobrança
mensal autorizada: são recursos temporários com encerramento obrigatório.

## Execução e retirada controladas

Preparar imagens/adapters e validar spec novo antes da alocação. Capturar IDs dos
recursos criados em manifesto privado, com instante inicial e prazo; conferir
permissão de removê-los antes de criar. Credenciais novas ficam somente no ambiente
privado do laboratório. Nunca aplicar um spec de teste sobre shopman-alpha.

A criação/teste deve estar encapsulada em limpeza `always/finally`, além de revisão
do manifesto após falha/cancelamento. Se permissão de exclusão ou o controle do prazo
não estiverem disponíveis, não criar os recursos. Não usar deleção por prefixo ou
varredura: apagar apenas IDs retornados por esta criação e confirmados no manifesto.

Conferir ausência desses IDs no fim, guardar resultado de limpeza e custo estimado.
Falha de preparação, timeout, OOM, falha de cleanup ou ensaio incompleto são resultados
explícitos; nenhum deles é passe/skips. Os recursos existentes não são rollback do
laboratório e não serão tocados. Piloto e rollout mantêm seus próprios gates.

## Decisão solicitada

Autorizar ou recusar exclusivamente esse laboratório temporário de até24h/US$5.
Silêncio não autoriza criação, gasto ou deployment de laboratório. O restante da
preparação técnica sem custo/efeitos reais permanece dentro do mandato existente.
