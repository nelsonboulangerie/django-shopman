# Go-live — sequência de cutover

> Procedimento do dia D. Não executar sem a
> [matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md) fechada e uma autorização
> GO contextual do incident commander/owner. Este runbook nunca concede essa
> autorização por si só.

## 0. Regra de parada

Parar antes de qualquer mutação quando:

- houver `PENDENTE`, `BLOQUEADO` ou `DESCONHECIDO` aplicável na matriz;
- SHA, manifesto, deployment ou ambiente não coincidirem;
- backup/restore ou rollback não estiverem comprovados;
- o **ensaio do Pix real** do [pré-flight §4](go-live-preflight.md#4-integrações-externas)
  não estiver feito (Pix em `payment_efi` com `EFI_SANDBOX=true` e
  `SHOPMAN_EXPOSE_MOCK_CAPTURE=false`, o que fecha o botão público de simular
  pagamento; D-006) ou o `EFI_WEBHOOK_TOKEN` não tiver sido rotacionado (D22).
  Efí, Stripe e Focus são as últimas chaves a ligar, não as últimas a ensaiar;
- faltar autorização específica para pagamento, estorno, emissão/cancelamento
  fiscal, envio, corrida, credencial/2FA/DNS ou tráfego comercial.

## 0a. Sequência do dia D (painel de go-live, 10/10/2026)

A loja vira produção **no próprio app vivo `shopman-nelson`, no mesmo banco**
(D-029): sem app novo, sem banco novo, sem DNS. **Sem data fixa** (D-030): a
sequência abaixo só começa quando a matriz fechar. As seções 1 a 6 detalham cada
passo; aqui está a ordem.

| Quando | Passo | Quem |
|---|---|---|
| Uma semana antes | **Ensaio geral** no vivo, sem ligar dinheiro: o roteiro de QA física inteiro (cliente, balcão, cozinha, gerente), inclusive desligar a rede do balcão com o PDV vendendo sem conexão; **e o ensaio de reapontar o app para um banco restaurado** (§0b). A parte técnica, fora do vivo (cópia do banco pela `25060`, app local com o spec do dia D, delta, E026/E027, gates e a volta), é o [ensaio geral da virada](ensaio-geral-da-virada.md). Congelar o escopo. | Pablo + equipe; agente prepara os roteiros |
| Véspera | Export curado (cofre de dados, `export_backup`); conferir o backup do dia (`doctl databases backups`); inventário físico de abertura; comunicar a equipe. | Pablo + equipe |
| Dia D · abrir a janela | Nomear quem comanda, quem executa e quem observa. Congelar merges. Anotar o SHA, o deployment atual e o **instante UTC do ponto de restauração**. Guardar o spec vivo fora do repositório (`~/golive-spec-antes.yaml`, ver [delta do spec](go-live-delta-do-spec.md)), rodar `make production-readiness target=1 context=shopman-do-app-admin` e guardar a saída (o "antes"). | Incident commander |
| Dia D · fechar antes de apagar | Nada pode escrever no banco enquanto o sintético sai. (1) Fechar os canais no Gestor, aba Canais, toggle "Ativo" desligado **sem prazo**: loja online, iFood (vira interrupção no iFood) e WhatsApp (o concierge deixa de oferecer pedido); o PDV não tem toggle, o caixa fica fechado. (2) Esperar a fila esvaziar: `/health/ready/` com `queue` `ok` e `ready backlog` zero (`DJANGO_DEBUG=true DATABASE_URL='<conexão direta 25060>' make diagnose-worker`). (3) Numa gravação só do painel: parar `ifood-poll-worker`, `directive-worker` e `maintenance-worker` e tirar o mock de pagamento, deixando o estado já ensaiado do Pix real (§0): Pix em `payment_efi` com `EFI_SANDBOX=true` e `SHOPMAN_EXPOSE_MOCK_CAPTURE=false`, o que fecha o botão público de simular pagamento. Nunca `apps update` de arquivo (D-009). Como parar um worker no App Platform sem apagá-lo do spec ainda **não foi medido**: o ensaio geral mede e anota aqui o gesto exato; sem gesto ensaiado, os workers ficam de pé, a fila vazia e os canais fechados, e o `lock_timeout` de 15 s do purge aborta e desfaz se algo segurar tabela. (4) Conferir no `doctl apps logs` que nenhum worker escreve. | Pablo (painel e Gestor); agente confere |
| Dia D · dados | Apagar o sintético com `purge_synthetic_data --apply --confirm-database shopman` e carregar os dados reais pelo plano ensaiado (catálogo consolidado, preço, fiscal, fichas, insumos, operadores, inventário de abertura), conferindo as contagens contra o ensaio ([comando](../reference/commands.md#purge_synthetic_data)). **O ensaio (sem `--apply`) nunca roda no vivo**: ele executa os `DELETE` de verdade e só desfaz no fim, segurando os locks das tabelas durante toda a transação. O ensaio roda numa **cópia** do banco (dump pela porta direta, restaurado num Postgres de ensaio, [ensaio geral §1 e §2](ensaio-geral-da-virada.md#1-guardar-o-spec-e-copiar-o-banco-pela-porta-direta)), na véspera, com `time` na frente para medir a duração; o de 13/10, numa cópia do alpha, apagou 47.693 linhas em 79 tabelas e conferiu 84 tabelas de cadastro, mas **não registrou quanto tempo levou**. **De onde roda o `--apply`:** desta máquina, numa worktree no SHA do deployment `ACTIVE`, com `DATABASE_URL` apontando para a **conexão direta** do cluster (porta `25060`, banco `shopman`), nunca para o pool PgBouncer (`25061`, `shopman-staging-pool`): o pool em modo transaction já quebrou o `directive-worker` três vezes depois de uma cópia (CLAUDE.md). Roda antes do `SHOPMAN_ENVIRONMENT=production` e do `SHOPMAN_GO_LIVE`, que fazem o `--apply` recusar. | Agente executa com a palavra do Pablo no momento; Pablo confere |
| Dia D · chaves | Pablo cola no painel, numa gravação só, o [delta do spec](go-live-delta-do-spec.md) (`scripts/golive_spec_delta.py` imprime o que falta): `SHOPMAN_ENVIRONMENT=production`, `SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_efi`, `EFI_SANDBOX=false`, sai `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` e `SHOPMAN_EXPOSE_MOCK_CAPTURE`, Stripe live (chave publicável `pk_live_` e segredos live), `FOCUS_NFE_ENVIRONMENT=producao` com o token de produção, `SHOPMAN_ADMIN_REQUIRE_2FA=true` (só com o 2FA de todo staff cadastrado), `SHOPMAN_GO_LIVE=true`. Os checks de deploy recusam virada pela metade. A mesma gravação religa `directive-worker`, `maintenance-worker` e `ifood-poll-worker`. Nunca `apps update` de arquivo (D-009). | Pablo |
| Dia D · deploy | Esperar `ACTIVE`; conferir `/ready/`, loja, PDV, cozinha, Gestor e Admin. `make production-readiness target=1 context=shopman-do-app-admin baseline=~/golive-spec-antes.yaml` tem de sair **verde** (o "depois"; o `baseline` prova que os segredos de produção foram colados). A tag `go-live-v1` **ainda não**: ela só nasce depois do GO. | Executor + observador |
| Dia D · canário de um | Religar só a loja online (Gestor, Canais) para Pablo comprar com Pix e com cartão; a NFC-e sai de verdade, e ele faz um estorno. Conferir no gateway e na Focus (§4). iFood e WhatsApp seguem fechados. | Pablo |
| Dia D · decisão | **GO limitado** (abrir a loja e os canais aprovados) ou **NO-GO** (rollback abaixo). Observar o primeiro dia antes de expandir canais (§5). | Incident commander |
| Dia D · depois do GO | Só com o GO assinado: criar e empurrar a tag `go-live-v1` no SHA do deployment `ACTIVE` (`git tag -a go-live-v1 <sha> -m "GO de <data>"` e `git push origin go-live-v1`). A tag arma a política de migrações da ADR-015 (expand-contract, aliases com prazo); o `SHOPMAN_GO_LIVE=true` das chaves já endureceu a trava `migration_safety` no ambiente. Atualizar a linha da tag na [matriz](../plans/GO-LIVE-READINESS-PLAN.md). | Incident commander |

**Rollback.** Código: refazer o deployment anterior
([rollback-de-deploy.md](rollback-de-deploy.md)). Chaves: voltar os valores
anotados na abertura (inclusive `SHOPMAN_GO_LIVE`, que sai). Dado: restaurar o
ponto UTC anotado num cluster novo e reapontar o app, pelo procedimento ensaiado
em §0b, **com o Valkey limpo e o `cluster_name` do spec versionado atualizado**
(passos 4 e 5 do §0b). Canais: seguem fechados até nova decisão. A trava
`migration_safety` já roda antes do `migrate` em todo deploy e, com
`SHOPMAN_GO_LIVE` ou a tag, recusa migração destrutiva sem ponto de restauração
anotado.

**A tag num NO-GO.** A tag `go-live-v1` não nasce: ela só existe depois do GO.
Se alguém a criou antes da decisão, apague-a no mesmo turno, local e remota
(`git tag -d go-live-v1` e `git push origin :refs/tags/go-live-v1`), com a
palavra do incident commander, e confira que `git ls-remote --tags origin
go-live-v1` sai vazio: com a tag de pé a ADR-015 fica ativa sem a loja ter
virado, e o gate `make canonical-docs` passa a exigir a matriz dizendo
"presente". Um NO-GO depois do GO (rollback de uma loja já aberta) não apaga a
tag: a política de produção continua valendo enquanto houver dado real.

## 0b. Ensaio de reapontar o app para o banco restaurado

É o **único passo do rollback de dado nunca ensaiado**: o restore foi provado em
01/10 ([backup-e-restore.md](backup-e-restore.md), fork pelo painel e lógico),
mas o app nunca falou com um cluster restaurado. Ensaia-se junto do ensaio geral,
antes do dia D, enquanto o dado ainda é sintético. Muda o banco do app vivo,
então é **palavra e mão do dono** (tabela "Quem faz o quê" do backup-e-restore);
o agente prepara o spec e confere.

Como o app acha o banco hoje (spec vivo, 10/10): o componente `postgres` do
bloco `databases` aponta para o cluster `shopman-staging-postgres`, e
`DATABASE_URL` vale `${postgres.shopman-staging-pool.DATABASE_URL}` (o pool
PgBouncer daquele cluster). Reapontar é trocar esse alvo.

1. **Antes.** Congelar merges. Guardar o spec vivo (`doctl --context
   shopman-do-app-admin apps spec get <app>`, fora do repositório, com sha256) e
   rodar `make deploy-spec-drift context=shopman-do-app-admin` (tem de sair
   `[OK]`). Anotar as contagens de referência do passo 3 do backup-e-restore
   (pedidos, último pedido, `django_migrations`).
2. **Restaurar.** Pelo painel, `shopman-staging-postgres` → Restore from backup →
   Restore to New Cluster (D-021), no ponto mais recente. Esperar `online`
   (cerca de 7 min em 01/10).
3. **Preparar o restaurado.** No cluster novo, criar o pool com o **mesmo nome**
   (`shopman-staging-pool`, banco `shopman`, modo transaction) e incluir o app
   nas fontes confiáveis, se o cluster de origem as tiver. Conferir por leitura,
   pela porta direta `25060` (nunca pelo pool `25061`), que as contagens batem.
4. **Reapontar.** A partir do spec guardado no passo 1, trocar **só**
   `cluster_name` do componente `postgres` para o cluster restaurado. Diff de
   uma linha, como na D-011; os segredos `EV[...]` ficam intactos. Aplicar e
   anotar o deployment criado e o tempo até `ACTIVE`. **No mesmo PR do
   incidente** (no ensaio, só anotar), trocar o `cluster_name` do componente
   `postgres` também no spec versionado `.do/app.alpha-subdomains.yaml`: sem
   isso o `make deploy-spec-drift` acusa o vivo e o próximo spec aplicado a
   partir do arquivo reaponta o app para o cluster antigo.
5. **Limpar o Valkey.** O cache (`shopman-staging-cache`, sem backup por
   desenho) continua com o estado do banco de antes: catálogo, disponibilidade,
   contadores de rate limit e chaves que apontam para linhas que o restaurado
   não tem. Com o app já no restaurado, esvaziar o cache pelo console do
   `web-operator` (mesma mão do passo 4):

   ```bash
   doctl --context shopman-do-app-admin apps console 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator
   python manage.py shell -c "from django.core.cache import cache; cache.clear()"
   ```

   Sessões de login moram no banco, não no cache: ninguém é deslogado por isto.
6. **Provar.** `/ready/` 200 com `database` e `migrations` `ok`; loja, PDV e
   Admin abrem; um pedido de teste feito antes do passo 2 aparece; o
   `directive-worker` processa (sem `relation ... does not exist`, o sintoma de
   `search_path` grudado no pool); `make production-readiness target=1` com
   `target.ready` OK.
7. **Voltar.** Restaurar o spec guardado (o `cluster_name` original), esperar
   `ACTIVE`, limpar o Valkey de novo (passo 5) e repetir o passo 6 contra a
   origem. O que foi escrito durante a janela no restaurado se perde, por isso
   o congelamento.
8. **Descartar** o cluster de ensaio no painel e registrar a evidência: horário
   de cada passo, deployments, tempo total de indisponibilidade, contagens e o
   que precisou de ajuste (pool, fontes confiáveis, cache, spec versionado). Atualizar a linha
   "Reapontar o app para banco restaurado" da
   [matriz](../plans/GO-LIVE-READINESS-PLAN.md).

Regra de parada do ensaio: qualquer `[FAIL]` no drift do passo 1, contagem que
não bate no passo 3, ou `/ready/` diferente de 200 no passo 6. Nesses casos,
voltar (passo 7) e registrar a causa antes de tentar de novo.

## 1. Abrir a janela

1. Registrar horário, incident commander, executor, observador e canal.
2. Congelar merges/deploys não relacionados pelo mecanismo aprovado.
3. Registrar SHA, ambiente, domínio e deployment anteriores.
4. Confirmar ponto de restauração e último restore ensaiado.
5. Registrar decisão **GO** assinada. Ausência de assinatura é **NO-GO**.

## 2. Preparar a release

1. Reexecutar os gates definidos no [pré-flight](go-live-preflight.md).
2. Revisar o plano de migrations e o comportamento de rollback.
3. Não criar `go-live-v1` aqui: a tag nasce só depois do GO assinado (§0a,
   "Dia D · depois do GO"). A tag é uma mudança de política, não um marcador
   decorativo, e num NO-GO ela não existe.
4. Configurar gates de migration do ambiente somente pelo canal aprovado, com
   referência de backup sanitizada.

Mudança de secret, 2FA, ingress ou DNS exige autorização específica e dupla
checagem no momento. Nunca substituir o spec vivo por um arquivo local que não
preserve secrets e configuração atual.

## 3. Deployment

1. Promover/publicar exatamente o SHA aprovado pelo fluxo vigente.
2. Acompanhar o release job e migrations; não seguir se houver warning não
   classificado.
3. Esperar o deployment correto ficar `ACTIVE`.
4. Confirmar `/ready/`, `/health/`, menu, SSR, login e superfícies do escopo.
5. Relacionar manifesto, deployment e smoke na matriz.

O fluxo normal é `main → Deploy Images (publica e cria UM deployment,
`deploy_mode: single_deployment`) → Pre-go-live Smoke`. Um deploy manual excepcional precisa de registro e da mesma
rastreabilidade; não pode produzir uma segunda fonte de verdade.

## 4. Canário autorizado

Executar somente as ações individualmente autorizadas. Para cada uma:

1. registrar intenção, valor/efeito esperado e responsável;
2. executar uma unidade;
3. confirmar webhook/lifecycle/idempotência;
4. reconciliar o efeito no sistema e no provider;
5. confirmar rollback/estorno/cancelamento apenas se também autorizado;
6. parar diante de efeito `unknown`, duplicidade ou divergência.

Não automatizar pagamento, estorno, emissão fiscal, envio ou corrida para
“completar o checklist”.

## 5. GO/NO-GO final e expansão

O incident commander avalia evidência técnica, física, financeira e fiscal:

- **NO-GO:** congelar expansão, seguir
  [rollback](rollback-de-deploy.md) quando aplicável e preservar evidência; a
  tag `go-live-v1` não é criada (§0a, "A tag num NO-GO");
- **GO limitado:** criar a tag `go-live-v1`, abrir somente o volume/canal
  aprovado e monitorar;
- **expansão:** nova decisão humana após a janela de observação. O GO limitado
  não autoriza automaticamente expansão ou lançamento oficial.

## 6. Encerramento

- registrar deployment/SHA, horário, decisão e owners;
- executar diagnósticos e reconciliação autorizados;
- registrar incidentes, efeitos `unknown` e follow-ups;
- atualizar a matriz canônica sem copiar o estado para outros documentos.
