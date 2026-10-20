# IFOOD-E — ensaio na loja de teste

- **id:** IFOOD-E
- **sessão:** frente 6, turno 5b e retomada autorizada em 20/10/2026 (Codex)
- **branch:** `codex/ifood-ensaio-completo` (seguimento de `codex/ifood-ensaio`)
- **PR anterior:** #1929 (evidência da primeira interrupção)
- **PR de seguimento:** #1962
- **estado:** EM_PR; ensaio completo confirmado na retomada, restauração exata concluída
- **execução final:** 2026-10-20 21:16:14–21:17:22 UTC (18:16:14–18:17:22 em São Paulo)
- **execução inicial:** 2026-10-20 20:59:46–20:59:49 UTC
- **ordem:** `ORDERS/next-ensaio.md`, autorização expressa para um merchant e um SKU

## Histórico: primeira execução (20:59 UTC)

### Preparação

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

## Encaminhamento da primeira execução

A primeira execução não aprovou o ensaio completo. O dono pediu conferir o contrato de
`originalValue`, corrigir o critério ou o adapter conforme a evidência e retomar o roteiro.
O resultado dessa retomada está abaixo. O seguimento usa outro branch porque #1929 já estava
na fila; a regra do repositório impede novos pushes no branch enfileirado.

## Retomada: contrato verificado e critério corrigido

Consulta em 20/10/2026 à documentação oficial da Catalog API v2.0:

- [Fundamentals, Price](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/fundamentals):
  `value` é o preço cobrado; `originalValue` é opcional e apresenta o preço anterior ao desconto.
- [Endpoints, Update item price](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints):
  o exemplo do PATCH envia apenas `price.value`.

Para este item **sem promoção**, o teste confirma `value` no item e no contexto DEFAULT.
Ausência de `originalValue` e `originalValue == value` são equivalentes em termos de preço
sem desconto. Um valor diferente continua sendo reprovação: seria uma promoção não solicitada.
Essa equivalência é usada apenas nas conferências intermediárias; o baseline final exige
igualdade exata. A omissão no GET já observada confirma que a expectativa anterior do ensaio
estava excessiva. **Nenhuma correção do adapter de produção foi necessária.**

### Tentativa de 21:14 UTC, interrompida e restaurada

Com o preço aprovado pelo critério corrigido, as alterações rápidas também convergiram. Às
21:14:56.330, o GET da descrição mostrou `Ensaio autorizado do catálogo ifood em 20/10/2026.`
para o texto enviado `Ensaio autorizado do catálogo iFood em 20/10/2026.`. O payload comprova
que o adapter enviou a caixa original; a transformação aconteceu no provedor. A comparação
exata interrompeu a tentativa. Restauração do item às 21:14:59.527 sem diferenças e captura
integral às 21:15:02.806 com categorias/itens iguais. Banco privado destruído.

A nova execução usa `Descrição temporária para ensaio autorizado em 20/10/2026.`, cuja leitura
remota foi comparada literalmente. Não foi afrouxado o critério da descrição.

### Correção do alvo temporário de categoria

A captura confirmou `Categoria Pizza` com template `PIZZA` e o item com tipo `DEFAULT`.
Para manter o mesmo template no movimento, foi escolhida a categoria **já existente**
`Categoria Bebida` (`e4f00b97-ad97-4fe2-aad6-7c2026815e6c`), template `DEFAULT`, do mesmo merchant.
Nenhuma categoria foi criada ou editada. O item continuou sendo o único alvo de escrita.
A categoria original permaneceu sendo o destino obrigatório da restauração.

## Execução completa de 21:16 UTC

Novo runtime privado, nova captura inicial, um único SKU no dry-run, mesmo merchant, catálogo,
contexto, item, produto e vínculo confirmados. Código da worktree e política isolada de teste
iguais aos da preparação acima. Nenhuma chamada à loja real ou ao storage compartilhado.

Todos os horários são UTC em 20/10/2026. PATCH/PUT e GET abaixo retornaram **200**;
o upload da foto retornou **201**. Nenhum `Retry-After`, conflito ou retentativa automática.

| Passo | Escrita | GET confirmatório | Evidência |
|---|---|---|---|
| Pausar | 21:16:14.751, PATCH status `UNAVAILABLE` | 21:16:15.378 | Sem diferença do baseline. Diretiva 1: `retracted`. |
| Retomar | 21:16:15.799, PATCH status `AVAILABLE` | 21:16:16.357 | Somente status item/DEFAULT alterado. Diretiva 2: `synced`. |
| Preço | 21:16:16.646, PATCH `price.value=20.91` | 21:16:17.217 | Item/DEFAULT por R$ 20,91, sem `originalValue`; nenhum campo alheio alterado. Diretiva 3: `synced`. |
| Dois preços rápidos | Intenções locais R$ 21,92 e R$ 22,93 antes do processamento | 21:16:18.715 | Duas diretivas leram o estado atual e enviaram R$ 22,93; ambas `synced`. Última intenção confirmada. |
| Pausa/retomada rápidas | Duas intenções antes do processamento; PATCH `AVAILABLE` | 21:16:19.615 | Uma diretiva agrupada, `synced`; estado final disponível. |
| Descrição | 21:16:19.979, PUT pelo cadastro/projeção canônicos | 21:16:20.267 | Frase temporária exata. Preço sem promoção, status, categoria, índice, imagem, complementos e contexto preservados. Diretiva 7: `synced`. |
| Categoria | 21:16:20.635, PUT com mapa explícito da coleção local | 21:16:20.938 | Somente `categoryId` mudou para a categoria DEFAULT escolhida. Mesmos itemId/productId/itemContextId. Diretiva 8: `synced`. |
| Foto | 21:16:21.326, POST image/upload; 21:16:21.659, PUT do item | 21:16:21.982 | `imagePath` novo e não vazio, único campo alterado. Diretiva 9: `synced`. |

O recibo HTTP completo de cada passo está na evidência privada; os instantes de PATCH acima
são transcritos dos recibos, não estimativas. O PATCH de preço não enviou texto, categoria,
índice, turnos, imagem ou contextos. O envio rápido usou o handler real e estado local atual,
sem simular a resposta remota e sem criar outro anúncio.

A foto foi uma fixture PNG local, lida diretamente do storage privado pelo fluxo de upload
canônico. O GET retornou `imagePath` terminado em `202610201816_h1k0mszoyqq.png`. A trava de
transporte permitiu somente a origem Merchant API oficial; nenhuma URL pública da foto foi
acessada. Todos os GET flat conservaram item, produto e identidade do contexto DEFAULT.

## Restauração da execução completa

A restauração teve duas conferências que impediram declarar sucesso cedo demais:

1. 21:16:22.921: PUT explícito de `imagePath=""`; GET 21:16:23.178 confirmou remoção da foto.
2. 21:16:23.837: PUT da categoria original com o objeto completo do GET, incluindo
   `contextModifiers`; o GET 21:16:24.165 ainda mostrou a categoria temporária. HTTP 200 sozinho
   não foi aceito como confirmação. O ensaio permaneceu encerrado e a restauração continuou.
3. 21:16:54.062: nova intenção explícita com os dados originais, omitindo os overrides de
   contexto do GET, como no PUT do adapter. Categoria, descrição, foto, preço e status raiz
   voltaram. A comparação encontrou **apenas** status DEFAULT ainda `AVAILABLE`.
4. 21:17:18.558: PATCH do preço inicial completo, `{"value":19.9,"originalValue":19.9}`.
5. 21:17:18.834: PATCH status `UNAVAILABLE`, restaurando também DEFAULT.
6. 21:17:19.113: GET flat **idêntico** ao baseline, sem normalizar ou excluir nenhum campo.
7. 21:17:22.620: captura integral final com `merchant_id`, `catalog_id`, `context`, `categories`
   e `category_items` exatamente iguais à captura inicial. Mesmo número de categorias e itens,
   sem anúncio paralelo e sem mudanças nos demais itens.
8. 21:17:22.623: zero diretivas pendentes, backend/política removidos, token/configuração de
   credenciais retirados da memória do processo, banco SQLite e mídia privada destruídos.

SHA-256 dos arquivos flat inicial **e** restaurado:
`e960d75376c28a1e9893d2135d3ecd08ab204b893bf0e88a4e5aa61b08b878a4`.
A captura de catálogo tem horários e recibos diferentes, por isso sua igualdade foi conferida
nos campos de domínio acima, não pelo hash do arquivo integral. Evidências privadas `0700/0600`
fora do Git; credenciais originais do dono mantidas no `.env` ignorado.

**Resultado final:** etapas do roteiro e convergência confirmadas, com restauração integral.
As intercorrências de descrição e restauração permanecem registradas. O ensaio cobre somente
esse item sem promoção e esse contexto; não demonstra concorrência PostgreSQL, promoção ativa,
catálogo de produção ou tipos PIZZA. Não houve alteração de implementação do adapter.


## Encerramento e acompanhamento dos merges

O dono pediu acompanhar #1929 e #1962 até o merge, resolver falhas e encerrar a frente.
O encerramento documental está em preparação no branch `codex/ifood-e-encerramento`.
**Não publicar como concluído antes dos dois merges efetivos.**

| PR | Entrega | Merge confirmado |
|---|---|---|
| #1929 | Registro da primeira interrupção e restauração | aguardando checks/fila |
| #1962 | Contrato conferido, roteiro completo e restauração exata | aguardando checks/fila |

Conferência inicial do acompanhamento em 20/10/2026: ambos abertos, mergeáveis e com
merge automático habilitado; nenhuma falha nos checks naquele momento. #1929 ainda aguardava
`Backstage rest`; #1962 tinha testes em execução e aguardando capacidade dos runners.
A conclusão vai registrar os horários e commits de merge observados na API do GitHub.

### Sobreposição de outra sessão

O inventário encontrou #1963 (`claude/ensaio-pedidos-execucao-a13c08`), que parte do registro
#1929 e altera os mesmos documentos, além do payload de preço para enviar também
`originalValue=value`. O PR relata o adendo de coordenação e uma tentativa adicional, com
preço/alterações rápidas/descrição confirmados e interrupção na categoria PIZZA, seguida de
restauração. Isso não invalida o contrato oficial nem a evidência da execução completa de #1962.

O encerramento deve preservar os históricos e conferir a integração dessa frente para não
reintroduzir a alegação de que categoria DEFAULT e foto ainda não foram provadas. Não houve
nova execução ou escrita remota no iFood durante este acompanhamento. Nenhum PR de outra sessão
foi fechado, alterado ou reenfileirado por este trabalho.
