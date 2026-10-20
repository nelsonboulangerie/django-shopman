# Ensaio do catálogo iFood na loja de teste

Este roteiro prova preço, disponibilidade, descrição, categoria e foto em um único item descartável
de um merchant comprovadamente de teste. Ele não autoriza escrita na loja real e não contém
credenciais.

## Alvos confirmados

O repositório e uma captura autenticada somente leitura de 20/10/2026 confirmaram os alvos do
ensaio. Não substitua nenhum deles por recurso de outra loja:

1. merchant `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`, “Teste - Nelson Boulangerie”;
2. catálogo `343e3649-18eb-4c08-99b4-4302df1cdf5e`, contexto `DEFAULT`;
3. item `Produto Teste Adapter`, SKU `SHOPMAN-TEST-ADAPTER`, item
   `37c7f299-d753-50ed-9393-ec7f62e0af4f`, produto
   `16baacff-c490-5805-872a-44210ae4d721`;
4. categoria inicial e de restauração `Categoria Item Normal`
   (`1d097d39-0ce0-47a6-ad6b-1ab9f4d9692a`);
5. categoria temporária do movimento `Categoria Bebida`, template `DEFAULT`
   (`e4f00b97-ad97-4fe2-aad6-7c2026815e6c`). A captura da retomada confirmou que o alvo
   originalmente anotado, `Categoria Pizza`, tem template `PIZZA`. Para este item `DEFAULT`,
   o ensaio usa outra categoria já existente do mesmo template, sem criar ou editar categorias.

As credenciais do app de teste já estão no `.env` local ignorado pelo Git, e o `client_id` confere
com o app documentado `NB Teste (C)`. Carregue-as diretamente desse arquivo no runtime isolado; não
copie valores para terminal gravado, arquivo novo, banco, log, captura, documento ou PR.

## Bloqueios obrigatórios

As frentes de categoria, identidade, PATCH, foto e tela precisam estar mergeadas. No turno 5b de
20/10/2026, #1927, #1928, #1905, #1931, #1947 e #1948 já estavam no `main` (`65b658d31`).

A primeira execução desse turno parou ao exigir a preservação de `originalValue` no PATCH de
preço. O contrato oficial foi conferido na retomada autorizada pelo dono em 20/10/2026:

- [Fundamentals, Price](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/fundamentals):
  `value` é o preço cobrado; `originalValue` é opcional e serve para exibir desconto.
- [Endpoints, Update item price](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints):
  o exemplo do PATCH envia `price: {"value":26.00}`, sem `originalValue`.

**Critério deste ensaio sem promoção:** confirmar o valor cobrado no item e no contexto DEFAULT.
A ausência de `originalValue`, ou sua igualdade com `value`, representa preço sem desconto e não
é falha. Não aceitar `originalValue` diferente do preço cobrado, pois isso introduziria uma
promoção não solicitada. Essa equivalência também se aplica à comparação de preço nas etapas
estruturais; todos os outros campos continuam sendo comparados. Não extrapolar esse critério
para um item com promoção ativa, que exige intenção e conferência próprias.

O adapter já envia e confirma `price.value`, de acordo com o contrato. A primeira interrupção
foi causada pelo critério adicional do ensaio. A restauração final continua exigindo igualdade
exata com o baseline, inclusive presença e valor de `originalValue`. Histórico e recibos em
`docs/coordination/ROUNDS/IFOOD-E-ensaio-teste.md`.

## Preparação segura

1. Use um runtime efêmero, banco privado e fila de diretivas exclusiva. Não use alpha nem produção.
2. Configure `SHOPMAN_IFOOD.merchant_id` com o UUID acima e mantenha a origem oficial HTTPS.
3. Defina `SHOPMAN_IFOOD_CATALOG_WRITE_POLICY` somente nesse runtime, com `environment=test` e a
   allowlist contendo apenas `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`.
4. Registre o backend de projeção somente no runtime isolado. Não altere specs de deploy nem ligue
   `IFOOD_CATALOG_PROJECTION` em ambiente compartilhado.
5. Confirme que a seleção local contém apenas o item de teste. `sync_catalog_ifood --dry-run` deve
   mostrar exatamente esse SKU; qualquer item adicional interrompe o ensaio.
6. Crie um diretório privado `0700` fora do repositório. Toda captura usa nome novo e permissão
   privada; nenhuma evidência remota entra no Git.

## Baseline

1. Capture o catálogo com `capture_ifood_catalog`, informando merchant, catálogo, contexto e um
   arquivo novo no diretório privado.
2. Registre fora do Git, para o item e a categoria de teste: nome, descrição, preço, status,
   `imagePath`, categoria, índice, turnos, contextos e horário da leitura.
3. Confirme que o vínculo local aponta para o `itemId` e `productId` dessa captura. Se o adapter
   resolver UUID derivado diferente, interrompa sem escrever.
4. Confirme que nenhuma pendência de sincronização anterior está em voo para o SKU.

## Execução e confirmação

Faça uma intenção por vez. Depois de cada uma, espere o recibo local e a leitura remota confirmada.
Se surgir 409, 429, timeout, leitura divergente ou estado desconhecido, preserve a intenção e pare;
não repita manualmente com outra chave.

1. **Pausar:** pause o item pelo controle canônico. Confirme `UNAVAILABLE` no GET remoto e confirme
   que preço, descrição, categoria, índice, turnos, `imagePath` e identidade dos contextos não
   mudaram. O status do contexto DEFAULT deve acompanhar a intenção, sem criar outro contexto.
2. **Retomar:** retome o mesmo item. Confirme `AVAILABLE` e os mesmos campos preservados.
3. **Preço:** aplique um preço temporário inequivocamente diferente. Confirme o valor no GET remoto
   no item e no contexto DEFAULT, aplicando o critério de preço sem promoção acima. Prove que o
   PATCH não enviou texto, categoria, índice, turnos, imagem ou contextos.
4. **Alterações rápidas:** ainda com o envio observado, aplique dois preços em sequência e depois
   pausa/retomada em sequência. O estado final remoto deve ser exatamente a última intenção; não
   pode surgir anúncio paralelo.
5. **Descrição:** altere somente a descrição pelo cadastro canônico, usando uma frase sem marca
   ou caixa mista, por exemplo `Descrição temporária para ensaio autorizado em 20/10/2026.`
   A primeira retomada observou normalização remota de `iFood` para `ifood`; registre a
   ocorrência, restaure e não atribua essa transformação ao adapter. Confirme o texto remoto e
   confira que o envio estrutural preservou preço, status, categoria, índice, turnos, `imagePath`,
   complementos e contextos.
6. **Categoria:** mova explicitamente o item para a categoria de teste. Confirme o `categoryId`
   vinculado, sem criar categoria homônima nem trocar `itemId`/`productId`.
7. **Foto:** envie a foto descartável pelo fluxo próprio. Confirme o `imagePath` novo na leitura
   remota e confirme que nenhum teste ou captura buscou a URL pública da imagem.

Em cada passo, registre: intenção, horário, endpoint/verbo, status HTTP, `Retry-After` quando houver,
identidade resolvida, recibo local e trecho mínimo da leitura confirmatória. Nunca registre header
de autorização, token, segredo ou resposta integral com dados desnecessários.

## Restauração

1. Restaure foto, categoria, descrição, preço e status para os valores exatos do baseline, nessa
   ordem, usando novas intenções explícitas. Foto vazia exige `imagePath=""` explícito.
   Não ecoe cegamente o GET flat no PUT: na retomada de 20/10, um PUT com os overrides de
   contexto lidos respondeu 200, mas não restaurou a categoria. Use o contrato de PUT do
   adapter com categoria explícita e confirme por GET. Em seguida, os PATCHes de preço e
   status devem restaurar também o contexto DEFAULT; status raiz correto não basta.
2. Faça outra captura completa em arquivo novo. Compare item, produto, categoria, complementos,
   índice, turnos e contextos com o baseline.
3. A restauração só termina quando a leitura remota coincide e não há diretiva pendente para o SKU.
4. Desregistre o backend no runtime isolado, remova a política de escrita e destrua o runtime/banco
   efêmeros. Revogue ou remova as credenciais do ambiente conforme a política do provedor.
5. Preserve apenas um resumo sem credenciais no PR. As capturas privadas não entram no Git.

## Critério de aprovação

O ensaio passa somente se as sete intenções forem confirmadas por leitura, as alterações rápidas
convergirem para a última intenção, nenhum campo alheio mudar, nenhuma identidade paralela surgir e
a restauração final coincidir com o baseline. Qualquer dúvida sobre o merchant ou o item encerra o
ensaio sem escrita.
