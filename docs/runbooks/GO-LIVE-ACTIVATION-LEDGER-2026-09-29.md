# Go-live activation ledger

Atualizado em: `2026-09-29T17:56:36Z`

Este e o registro canonico da passagem de cada WP e PR ate a operacao no ambiente
Live. Ele nao contem credenciais, valores secretos, dados pessoais nem amostras de
dados de clientes. Nao mantenha outro ledger em paralelo.

## Ambiente alvo e nomes sem ambiguidade

O alvo atual e o **ambiente vivo de pre-go-live**, ainda operado com integracoes
staging/mock/sandbox ate o cutover comercial. Ele e o app DigitalOcean
`shopman-nelson` (`40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`), acessado pelo contexto
operacional `shopman-alpha-deploy`, mas atende os hosts publicos finais:

- loja: `https://www.nelsonboulangerie.com.br`;
- API: `https://api.boulangerie.com.br`;
- Admin: `https://admin.boulangerie.com.br`.

Neste ledger, `Live` significa que o artefato esta rodando nesse ambiente vivo de
pre-go-live. Nao significa que ocorreu o cutover comercial. O host antigo
`api.staging.nelsonboulangerie.com.br` esta aposentado e responde NXDOMAIN; ele
nunca deve ser usado em smoke novo.

## Regra de conclusao

Um item so recebe `DONE` depois que todas as etapas aplicaveis estiverem comprovadas:

1. merge no `main`, com SHA registrado;
2. deploy identificado e concluido no ambiente Live;
3. migrations aplicadas, quando houver;
4. configuracao ou feature flag no valor desejado, quando houver;
5. smoke test no Live aprovado, sem dado pessoal no registro;
6. rollback conhecido e evidencia ligada neste ledger.

`MERGED`, `DEPLOYED` e `ACTIVE` sao estados intermediarios. Um PR apenas documental
ou sem efeito de runtime usa `N/A` nas etapas que realmente nao se aplicam, mas o WP
continua aberto enquanto seus gates operacionais dependentes nao forem comprovados.

## Como atualizar

- Atualize o registro no mesmo PR que muda a etapa, ou em PR pequeno imediatamente
  posterior quando o evento ocorrer fora do GitHub.
- Use horario UTC no formato ISO 8601.
- Evidencia deve ser um link ou identificador sanitizado: PR, SHA, run/deploy ID,
  endpoint de health sem parametros sensiveis, ou relatorio sem PII.
- Nao cole output de banco, nomes de clientes, enderecos, tokens, cookies ou valores
  de variaveis secretas.
- Um unico owner operacional atualiza cada registro por vez para evitar sobrescrita.

## Production Operational Data Readiness

### WP principal / PR #1241

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `MERGED`; `f2061447ad91fcb82016150d48d6f9fee110446a` |
| Deploy | `N/A`; PR documental, sem artefato de runtime |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Programa e gates Day-1 versionados; nenhuma carga Live autorizada por este PR |
| Dependencia/gate | #1243, #1244, #1248 e #1250; divergencias de catalogo e receitas exigem decisao humana antes de carga/publicacao |
| Smoke Live | `PENDING`; fechamento do WP depende dos itens operacionais abaixo |
| Rollback | Reverter o merge documental se o plano for formalmente substituido |
| Evidencia | [PR #1241](https://github.com/nelsonboulangerie/django-shopman/pull/1241) |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `IN_PROGRESS`; DONE somente quando os gates Day-1 aplicaveis estiverem comprovados no Live |

### Profiler sanitizado e somente leitura / PR #1243

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `MERGED`; `41849afe31482934a219ea7b27b09d3906d040b9` |
| Deploy | `DEPLOYED`; deployment `791c1bee-a612-4210-a5a4-1dd798e1d168` ficou `ACTIVE` em `2026-09-29T14:25:12Z`; imagem `web` ligada ao run `36579191951` do SHA sucessor `04f7c8db0` que contem o merge |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Comando `profile_data_artifact` disponivel, somente leitura e sem revelar valores ou caminhos |
| Dependencia/gate | `SATISFIED`; manifesto do deploy e digest da DigitalOcean correlacionados |
| Smoke Live | `PASSED`; Pre-go-live Smoke run `36582653085` verde e `/ready/` respondeu 200; o comando foi exercitado pela CI do PR e esta contido na imagem atestada, sem executar leitura de artefato real |
| Rollback | Reimplantar o release Live anterior ao merge |
| Evidencia | [PR #1243](https://github.com/nelsonboulangerie/django-shopman/pull/1243); [Deploy Images run 36579191951](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36579191951); [Pre-go-live Smoke run 36582653085](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36582653085) |
| Ultima atualizacao | `2026-09-29T14:31:09Z` |
| Estado/DONE | `DONE`; merge, deploy correlacionado e smoke Live comprovados; nenhuma carga de dados foi executada |

### Proveniencia e invariantes de importacao / PR #1244

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `MERGED`; `eb0227690b885d46d79a9e1e84ab3890a0cc7f74` em `2026-09-29T15:30:52Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `2418afe3-e47b-4686-abd8-7e47027ad451` ficou `ACTIVE` em `2026-09-29T15:37:45Z`; digest web `sha256:d8250d10371b1749861a63c7f31e14da15882e5a1d2d2ae71f2b779d9eb69975` |
| Migration | `APPLIED`; release registrou `migration-safety: clear`, 1 pendente e 0 destrutivas; `backstage.0078_importbatch_provenance... OK` em `2026-09-29T15:35:09Z` |
| Env/config/flag | `N/A` |
| Valor desejado | Proveniencia sanitizada ativa; `--rebuild` bloqueado em producao; vendas Yooga restritas a `HistoricalSale*` |
| Dependencia/gate | `SATISFIED`; CI, merge, migration aditiva e smoke pre-go-live verdes; #1248 entrou na merge queue, posicao 2 |
| Smoke Live | `PASSED`; Pre-go-live Smoke run `36591163320` verde apos o deployment (`/ready/`, menu, checkout anonimo e SSR); release concluiu `setup_groups: OK`; nenhuma importacao real foi executada |
| Rollback | Reimplantar release anterior; preservar migration aditiva salvo rollback de banco revisado e explicitamente autorizado |
| Evidencia | [PR #1244](https://github.com/nelsonboulangerie/django-shopman/pull/1244); [Deploy Images run 36590773802](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36590773802); [Pre-go-live Smoke run 36591163320](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36591163320); release deployment `2418afe3-e47b-4686-abd8-7e47027ad451` |
| Ultima atualizacao | `2026-09-29T15:39:07Z` |
| Estado/DONE | `DONE`; merge, deploy, migration segura e smoke pre-go-live comprovados; nenhuma carga historica ou operacional foi executada |

### Gate de catalogo Day-1, somente leitura / PR #1248

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `IN_QUEUE`; head `8be4766e6`; #1244 integrado; merge queue posicao 2, aguardando checks |
| Deploy | `PENDING_MERGE`; sem deploy ID |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | `audit_catalog_day1` disponivel somente para relatorio; 76 novos SKUs continuam `draft_only` e nao publicados |
| Dependencia/gate | #1244 mergeado; divergencias fiscais, GTIN, conteudo, imagem, colecao e receitas resolvidas antes de qualquer carga/publicacao |
| Smoke Live | `PENDING`; confirmar ajuda do comando e dry-run sanitizado com escopo explicito, sem aplicar dados |
| Rollback | Reimplantar o release Live anterior; comando nao possui caminho de escrita |
| Evidencia | [PR #1248](https://github.com/nelsonboulangerie/django-shopman/pull/1248) |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `IN_PROGRESS`; nao DONE ate merge, deploy e smoke Live; publicacao nao faz parte deste PR |

### Gate de receitas e insumos Day-1, somente leitura / PR #1250

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `STACKED`; head `9c692a3a0`, rebaseado sobre o head atual de #1248; CI reexecutando |
| Deploy | `PENDING_PREDECESSOR`; sem deploy ID |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | `audit_recipe_material_day1` disponivel somente para relatorio, com escopo de SKU explicito |
| Dependencia/gate | #1248 mergeado; receitas faltantes, rendimentos e montagem final exigem prova e gate humano; baixa na venda continua bloqueada |
| Smoke Live | `PENDING`; confirmar ajuda do comando e dry-run sanitizado, sem escrever receitas/insumos |
| Rollback | Reimplantar o release Live anterior; comando nao possui caminho de escrita |
| Evidencia | [PR #1250](https://github.com/nelsonboulangerie/django-shopman/pull/1250) |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `IN_PROGRESS`; nao DONE ate merge, deploy e smoke Live; carga de receitas permanece fora do escopo sem gate humano |

### Enriquecimento seguro de insumos por GTIN / PR #1265

| Campo | Estado |
|---|---|
| Owner | `gtin_fc_readiness` |
| Merge | `MERGED`; `4fc90509b4f54f4f1efcf7b8a0919c2556288a9c` em `2026-09-29T17:28:08Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `81254754-23a3-47bd-9e7b-877ab18f7fb5` ficou `ACTIVE` em `2026-09-29T17:34:58Z`; Deploy Images run `36605140771`; imagem `web-4fc90509b4f54f4f1efcf7b8a0919c2556288a9c` com digest `sha256:be0ab68ac502bf82dffb682d258aebacf28aca61d9104611b48419cfe8778c46` |
| Migration | `N/A`; release confirmou `migration-safety: clear`, zero migracoes pendentes/destrutivas e `No migrations to apply` |
| Env/config/flag | `N/A`; nenhum provider externo, fetch, staging, aceite ou enriquecimento Live foi ativado |
| Valor desejado | GTIN e demais campos aceitos pertencem ao `Material.metadata`; NF-e e fetch apenas preparam draft com proveniencia, validacao e cobertura, sem aceitacao automatica |
| Dependencia/gate | `HUMAN_SMOKE`; abrir [Materiais no Admin](https://admin.boulangerie.com.br/admin/buyman/material/) com sessao autorizada e revisar a acao `Revisar sugestao do GTIN` sem enviar o formulario nem aplicar dados; release confirmou `setup_groups: OK` |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36605463827` verde apos o deployment, com `/ready/`, cardapio, checkout e SSR aprovados; a tela Admin autenticada nao e automatizada |
| Rollback | Reimplantar o release Live anterior ao merge; nao ha schema, config, flag ou carga de dados a reverter |
| Evidencia | [PR #1265](https://github.com/nelsonboulangerie/django-shopman/pull/1265); [Deploy Images run 36605140771](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36605140771); [Pre-go-live Smoke run 36605463827](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36605463827) |
| Ultima atualizacao | `2026-09-29T17:54:48Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate validar a UI Admin em sessao autorizada, sem aceitar sugestao nem enriquecer Material Live |

### FC ponderado na sugestao de compra / PR #1267

| Campo | Estado |
|---|---|
| Owner | `gtin_fc_readiness` |
| Merge | `MERGED`; `ed49a8624ada61170e7834d124c63dcc29ff9351` em `2026-09-29T17:48:09Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `9cda0674-568b-4333-abef-2b6e9cb99d53` ficou `ACTIVE` em `2026-09-29T17:53:31Z`; Deploy Images run `36607515604`; digests `web` `sha256:ad29f4268106e5b6090c8ef84d86b41a63255489570cdad70c7e12c251899512`, `operator-office` `sha256:5bb48dc910e956441867427f155759cdeb6a51d2c09d3d82bae9fa4a0d361422` e `purchase` `sha256:1b5e290fce31d6b295d43314a543159f5d19ff24f45f80da34106503ecdb6210` |
| Migration | `N/A`; release confirmou `migration-safety: clear`, zero migracoes pendentes/destrutivas e `No migrations to apply` |
| Env/config/flag | `N/A` |
| Valor desejado | Sugestao de compra explica o rendimento ponderado por ficha a partir de consumo finalizado; `suggestedQty` continua bruto e o FC nao e multiplicado novamente, evitando duplicar `gross_quantity` |
| Dependencia/gate | `SATISFIED`; CI cobriu ponderacao por ficha, inversao unica do rendimento, nao duplicacao de `gross_quantity` e a apresentacao da conta; o WP nao declara gate humano ou efeito externo |
| Smoke Live | `PASS`; Pre-go-live Smoke run `36607859250` verde apos o deployment: `/ready/` 200, 40 SKUs (37 disponiveis), checkout anonimo falhou fechado com 403 e SSR respondeu 200 com 143229 bytes; [Compras](https://compras.boulangerie.com.br/) respondeu 200 |
| Rollback | Reimplantar o release Live anterior ao merge; nao ha schema, config, flag ou dado a reverter |
| Evidencia | [PR #1267](https://github.com/nelsonboulangerie/django-shopman/pull/1267); [Deploy Images run 36607515604](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36607515604); [Pre-go-live Smoke run 36607859250](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36607859250) |
| Ultima atualizacao | `2026-09-29T17:56:36Z` |
| Estado/DONE | `DONE`; merge, deploy, release safety e smoke pre-go-live comprovados; nenhuma carga, configuracao ou escrita Live fez parte do WP |

## Operacao, seguranca e marketing

### Lock de estacao sem encerrar a sessao compartilhada / PR #1249

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `b9ee08f4365e1f0d6e32fd2c97bcfc1a208523cf` em `2026-09-29T15:03:33Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `9b995ee3` ficou `ACTIVE` em `2026-09-29T15:15:19Z`; Deploy Images run `36587278842`, do SHA sucessor `63c426f0f` que contem o merge |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Bloquear somente a estacao PDV e preservar a sessao compartilhada do Gestor; desbloqueio exige operador com `cashman.operate_pos` |
| Dependencia/gate | `HUMAN_SMOKE`; CI cobriu lock, unlock e preservacao da sessao, mas o smoke autenticado exige sessao Gestor autorizada e nao usa credenciais ou 2FA automatizados |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36588740546` verde apos o deployment; PDV publico respondeu 200 e o endpoint de sessao de operador falhou fechado com 403 sem autenticacao |
| Rollback | Reimplantar o release Live anterior ao merge; nao ha schema, config ou flag a reverter |
| Evidencia | [PR #1249](https://github.com/nelsonboulangerie/django-shopman/pull/1249); [Deploy Images run 36587278842](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36587278842); [Pre-go-live Smoke run 36588740546](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36588740546) |
| Ultima atualizacao | `2026-09-29T16:39:08Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate validar lock/desbloqueio e continuidade da sessao compartilhada no Live com perfil autorizado |

### Alertas de login e gestao de acessos conectados / PR #1251

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `db6c617af00f7152a6656d6c584384386879e3ca` em `2026-09-29T15:12:51Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `3eed3cec` ficou `ACTIVE` em `2026-09-29T15:21:28Z`; Deploy Images run `36588469237` |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Novo login gera alerta seguro e a pessoa autenticada consegue listar e encerrar acessos conectados sem expor token ou dado sensivel |
| Dependencia/gate | `HUMAN_SMOKE`; comportamento e autorizacao estao cobertos pela CI, mas confirmar a tela e o encerramento de uma sessao real exige login autorizado do owner |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36589196530` verde apos o deployment; storefront respondeu 200 e superficies protegidas permaneceram fail-closed sem autenticacao |
| Rollback | Reimplantar o release Live anterior ao merge; nao ha schema, config ou flag a reverter |
| Evidencia | [PR #1251](https://github.com/nelsonboulangerie/django-shopman/pull/1251); [Deploy Images run 36588469237](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36588469237); [Pre-go-live Smoke run 36589196530](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36589196530) |
| Ultima atualizacao | `2026-09-29T16:39:08Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate validar alerta, listagem e encerramento de acesso em sessao autorizada no Live |

### Reconciliacao do roadmap POS / PR #1252

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `fad34627d5a8eafdb9e783f6ae63822ef9a9b14f` em `2026-09-29T14:42:14Z` |
| Deploy | `N/A`; PR documental, sem artefato de runtime |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Planos POS reconciliados com a implementacao atual, lacunas reais preservadas e trabalho superseded explicitamente encerrado |
| Dependencia/gate | `SATISFIED`; alteracao limitada a documentacao e sem efeito operacional |
| Smoke Live | `N/A`; nenhum runtime foi alterado |
| Rollback | Reverter o merge documental se o plano for formalmente substituido |
| Evidencia | [PR #1252](https://github.com/nelsonboulangerie/django-shopman/pull/1252) |
| Ultima atualizacao | `2026-09-29T16:39:08Z` |
| Estado/DONE | `DONE`; merge comprovado e todas as etapas de runtime sao corretamente N/A |

### Reorganizacao operacional da aba Encomendas do PDV / PR #1263

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `c61fabfce6894b20c9555e36823df002804847f0` em `2026-09-29T16:30:58Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `9fc75aa2` ficou `ACTIVE` em `2026-09-29T16:39:44Z`; Deploy Images run `36598280975` |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Encomendas usa uma unica arvore responsiva, hierarquia operacional clara, busca prioritaria, estados loading/empty/error acionaveis e alvos touch acessiveis, sem alterar contratos ou dados |
| Dependencia/gate | `HUMAN_SMOKE`; testes funcionais, visuais, responsivos, typecheck e build passaram; a confirmacao visual no Live exige sessao PDV autorizada e nao usa credenciais automatizadas |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36599313790` verde apos o deployment; `/ready/` respondeu 200, e `https://pdv.boulangerie.com.br/`, `/preorders` e `/session` responderam 200 com o shell Nuxt renderizado |
| Rollback | Reimplantar o release Live anterior ao merge; nao ha schema, config ou flag a reverter |
| Evidencia | [PR #1263](https://github.com/nelsonboulangerie/django-shopman/pull/1263); [Deploy Images run 36598280975](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36598280975); [Pre-go-live Smoke run 36599313790](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36599313790); [relatorio visual](https://github.com/nelsonboulangerie/django-shopman/tree/c61fabfce6894b20c9555e36823df002804847f0/docs/reports/execution/pos-encomendas-ux-20260929) |
| Ultima atualizacao | `2026-09-29T16:42:33Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate validar hierarquia, busca, periodo, filtros, estados e foco/teclado dentro da sessao PDV autorizada |

### Capacidades de providers no Marketing V2 / PR #1254

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `c1c177b0829788546416393622f16ba06f35b27b` em `2026-09-29T15:09:09Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `3eed3cec` ficou `ACTIVE` em `2026-09-29T15:21:28Z`; Deploy Images run `36588469237`, do SHA sucessor `db6c617af` que contem o merge |
| Migration | `N/A` |
| Env/config/flag | `N/A`; nenhuma integracao externa foi ativada |
| Valor desejado | Composer renderiza capacidades declaradas pelos providers e mantem acoes indisponiveis bloqueadas, sem disparar efeito externo |
| Dependencia/gate | `HUMAN_SMOKE`; CI cobriu o catalogo de capacidades e a UI, mas a confirmacao visual Live exige sessao Marketing autorizada; credencial externa e canario permanecem fora do escopo |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36589196530` verde apos o deployment; host Marketing respondeu 200 e a API permaneceu protegida com 401 sem autenticacao |
| Rollback | Reimplantar o release Live anterior ao merge; nenhuma configuracao de provider externo precisa ser revertida |
| Evidencia | [PR #1254](https://github.com/nelsonboulangerie/django-shopman/pull/1254); [Deploy Images run 36588469237](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36588469237); [Pre-go-live Smoke run 36589196530](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36589196530) |
| Ultima atualizacao | `2026-09-29T16:39:08Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate validar o catalogo visual em sessao autorizada, sem ativar provider externo |

### Reconciliacao do roadmap de sync externo de catalogo / PR #1255

| Campo | Estado |
|---|---|
| Owner | `debt_dormancy_audit` |
| Merge | `MERGED`; `5d76c1eab9e004cbf204df92454ebb727ec99e0e` em `2026-09-29T15:03:33Z` |
| Deploy | `N/A`; PR documental, sem artefato de runtime |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Roadmap externo reconciliado com o estado real; itens concluidos e superseded separados das dependencias ainda abertas |
| Dependencia/gate | `SATISFIED`; nenhum adapter, config, dado ou operacao de catalogo foi alterado |
| Smoke Live | `N/A`; nenhum runtime foi alterado |
| Rollback | Reverter o merge documental se o roadmap for formalmente substituido |
| Evidencia | [PR #1255](https://github.com/nelsonboulangerie/django-shopman/pull/1255) |
| Ultima atualizacao | `2026-09-29T16:39:08Z` |
| Estado/DONE | `DONE`; merge comprovado e todas as etapas de runtime sao corretamente N/A |

## Storefront e operacao

### Availability Admin / PR #1253

| Campo | Estado |
|---|---|
| Owner | `nondata_operational_backlog` |
| Merge | `MERGED`; `c6f8ee1269f0a2e46d0d21cb4678020d856e378f`, contido no SHA sucessor `fad34627d5` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `9dec55ad-dde0-4932-a1f3-8f04240f7763` ficou `ACTIVE` em `2026-09-29T14:49:46Z`; digest `sha256:fb0032d45c9f06b05421f98f2ce5bcf5da3bb59a6442fa9b8d150c3263d81d4d` |
| Migration | `N/A` |
| Env/config/flag | `N/A` |
| Valor desejado | Admin de disponibilidade operacional acessivel somente a perfis autorizados |
| Dependencia/gate | `HUMAN_SMOKE`; precisa sessao Admin autorizada do owner em `https://admin.boulangerie.com.br/admin/shop/shopoperation/` para provar acesso ao calendario operacional |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36585437565`, disparado por `workflow_run` sem input manual, usou `STOREFRONT_URL=https://www.nelsonboulangerie.com.br` e API `https://api.boulangerie.com.br`: `/ready/` 200, menu 40/37, checkout anonimo 403 canonico e SSR 200. O host Admin canonico redireciona anonimo ao login com 302. Acesso autorizado nao foi testado sem credencial do owner |
| Rollback | Reimplantar o release Live anterior; nenhum schema, config ou flag precisa ser revertido |
| Evidencia | [PR #1253](https://github.com/nelsonboulangerie/django-shopman/pull/1253); [Deploy Images run 36584648904](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36584648904); [Pre-go-live Smoke run 36585437565](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36585437565) |
| Ultima atualizacao | `2026-09-29T15:16:23Z` |
| Estado/DONE | `DEPLOYED_PENDING_HUMAN_SMOKE`; nao DONE ate o owner validar acesso autorizado e leitura operacional no Live |

#### Correcao da URL do smoke manual

Em `2026-09-29T15:16:23Z`, uma aba foi aberta manualmente em
`https://api.staging.nelsonboulangerie.com.br/admin/shop/shopoperation/` a partir
de uma copia local desatualizada do workflow. A pagina nunca carregou: DNS e
`curl` devolveram host inexistente. A aba foi fechada. Essa URL nao veio do PR
#1253, deste ledger nem do run `36585437565`, e nunca constituiu evidencia de
smoke.

A separacao comprovada e:

- workflow automatico: `www.nelsonboulangerie.com.br` e
  `api.boulangerie.com.br` no ambiente vivo de pre-go-live;
- smoke humano do Admin: `admin.boulangerie.com.br`, conforme
  `SHOPMAN_ADMIN_HOST` e o ingress de `.do/app.alpha-subdomains.yaml`;
- `api.staging.nelsonboulangerie.com.br`: referencia historica aposentada,
  NXDOMAIN e proibida para novas verificacoes.

Referencias residuais intencionais, auditadas no mesmo horario:

- `docs/reports/IFOOD-HOMOLOGACAO-2026-09-12.md` registra uma configuracao
  externa obsoleta do iFood e ja a identifica como falha de DNS;
- `shopman/shop/management/commands/efi_webhook.py` explica por que o comando
  corrige webhook legado, enquanto `test_do_spec_hosts.py` e
  `test_efi_webhook_command.py` usam o host morto como fixture de regressao;
- tres planos concluidos preservam a topologia historica e agora exibem aviso
  explicito de que o host esta aposentado e nao serve para smoke atual.

Nao ha referencia ao host aposentado em workflow, spec ativo ou runbook
operacional alem deste registro de prevencao.

### Confirmacao visual do endereco no mapa / PR #1256

| Campo | Estado |
|---|---|
| Owner | `nondata_operational_backlog` |
| Merge | `MERGED`; `3471adf6487bce877ee26d59ed575c4a0373c306` em `2026-09-29T15:22:58Z` |
| Deploy | `DEPLOYED_PRE_GO_LIVE`; deployment `038abbca-193f-4458-865b-c28ddb3b391b` ficou `ACTIVE` em `2026-09-29T15:28:53Z`; digest `sha256:e6a34986958f83d2382a6a49567c7f7c43bcbba1b0e7265d5bb0621eed1a5837` |
| Migration | `N/A` |
| Env/config/flag | `address_map_confirmation_enabled` |
| Valor desejado | `true` apos #1261 deployado, sessao Admin autenticada, canario e smoke; valor publico comprovado agora e `false` |
| Dependencia/gate | PR #1261 adiciona o switch Unfold canonico e esta na fila; depois exige sessao Admin autenticada no host canonico para canario e rollback seguro |
| Smoke Live | `PARTIAL_PASS`; Pre-go-live Smoke run `36590337864` verde (`/ready/` 200, menu 40/37, checkout anonimo 403 canonico, SSR 200); home config publico confirma flag `false`. Fluxo com mapa ativo ainda nao foi testado por estar corretamente desligado |
| Rollback | Alterar flag para `false` e, se necessario, reimplantar release anterior |
| Evidencia | [PR #1256](https://github.com/nelsonboulangerie/django-shopman/pull/1256); [PR #1261](https://github.com/nelsonboulangerie/django-shopman/pull/1261); [Deploy Images run 36589761997](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36589761997); [Pre-go-live Smoke run 36590337864](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36590337864) |
| Ultima atualizacao | `2026-09-29T15:29:53Z` |
| Estado/DONE | `DEPLOYED_FLAG_OFF`; nao DONE ate #1261 deployado, flag ativa em canario, smoke pre-go-live e rollback comprovado |

### Divergencia entre localizacao atual e endereco de entrega

| Campo | Estado |
|---|---|
| Owner | `nondata_operational_backlog` |
| Merge | `NOT_STARTED`; PR ainda nao registrado |
| Deploy | `BLOCKED_BY_PREDECESSOR`; sem deploy ID |
| Migration | `TBD` |
| Env/config/flag | Nome a confirmar no PR; deve nascer desligada por padrao |
| Valor desejado | `true` somente depois que #1256 estiver DONE e o canario desta etapa passar |
| Dependencia/gate | #1256 DONE; copy aprovada; tolerancia de distancia e tratamento de permissao/precisao definidos; sem bloquear checkout por geolocalizacao indisponivel |
| Smoke Live | `PENDING`; aviso correto quando ha divergencia, ausencia de falso bloqueio e caminho claro para confirmar/trocar endereco |
| Rollback | Desativar a flag dedicada; reimplantar release anterior se necessario |
| Evidencia | Adicionar PR, merge SHA, deploy ID e smoke quando existirem |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `BLOCKED_BY_PREDECESSOR`; nao DONE ate ativacao controlada e smoke Live |

## Pendencias operacionais imediatas

1. Registrar o deploy Live que contem `41849afe3` ou sucessor e executar o smoke seguro
   do profiler.
2. Integrar #1244; registrar SHA, deploy e aplicacao de `backstage/0078`.
3. Integrar #1248 e depois rebasear/integrar #1250, sempre sem carga ou publicacao.
4. Confirmar a fila de #1253 e #1256; depois de cada merge, registrar deploy e smoke.
5. Ativar `address_map_confirmation_enabled=true` por canario somente apos os gates do
   registro #1256; qualquer falha usa o rollback por flag.
