# Go-live activation ledger

Atualizado em: `2026-09-29T15:16:23Z`

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
| Merge | `IN_QUEUE`; head `6cc9041ce2c1db900b7d540b2cc0d7a70ed6daf0`, auto-merge ligado |
| Deploy | `PENDING_MERGE`; sem deploy ID |
| Migration | `PENDING`; `backstage/0078` aditiva, aplicar pelo release apos merge |
| Env/config/flag | `N/A` |
| Valor desejado | Proveniencia sanitizada ativa; `--rebuild` bloqueado em producao; vendas Yooga restritas a `HistoricalSale*` |
| Dependencia/gate | CI obrigatoria verde e merge antes de #1248 |
| Smoke Live | `PENDING`; confirmar migration aplicada, ajuda do importador e invariancia operacional sem executar importacao real |
| Rollback | Reimplantar release anterior; preservar migration aditiva salvo rollback de banco revisado e explicitamente autorizado |
| Evidencia | [PR #1244](https://github.com/nelsonboulangerie/django-shopman/pull/1244) |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `IN_PROGRESS`; nao DONE ate merge, migration, deploy e smoke Live |

### Gate de catalogo Day-1, somente leitura / PR #1248

| Campo | Estado |
|---|---|
| Owner | `execute_proddata_program` |
| Merge | `WAITING_PREDECESSOR`; head `8be4766e6`; auto-merge suspenso ate #1244 integrar; falha de import boundary corrigida pela API publica do Offerman e CI reexecutando |
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
| Merge | `IN_QUEUE`; head `e3498c6e6e2628b5c7262a2ef0caf81c4a39d8e1`, auto-merge ligado |
| Deploy | `PENDING_MERGE`; sem deploy ID |
| Migration | `N/A`, salvo confirmacao diferente no merge final |
| Env/config/flag | `address_map_confirmation_enabled` |
| Valor desejado | `true` apos deploy, canario e smoke; default de codigo permanece `false` |
| Dependencia/gate | Merge, deploy Live, disponibilidade do provedor de mapa ja configurado e canario sem regressao do checkout |
| Smoke Live | `PENDING`; GPS e busca convergem ao mapa, confirmacao persiste coordenadas, fallback sem mapa conclui endereco, telemetria sem PII |
| Rollback | Alterar flag para `false` e, se necessario, reimplantar release anterior |
| Evidencia | [PR #1256](https://github.com/nelsonboulangerie/django-shopman/pull/1256) |
| Ultima atualizacao | `2026-09-29T14:09:57Z` |
| Estado/DONE | `IN_PROGRESS`; nao DONE ate flag ativa em canario, smoke Live e rollback comprovado |

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
