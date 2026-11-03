# GO-LIVE-READINESS-PLAN — matriz canônica de prontidão

> **Única fonte operacional de estado de go-live.** Documentos de arquitetura,
> roadmap, credenciais e runbooks apontam para esta matriz; não mantêm cópias do
> status.

- `auditoria_id`: `GLR-2026-10-21`
- `verificado_em`: `2026-10-21T05:25:57Z`
- `baseline_git`: `4541f0a8a04056f89ca673b58819cfaf0ada090d`
- `ambiente_observado`: app DigitalOcean `shopman-nelson`, o app vivo que vira
  produção (D-029), hoje em perfil de ensaio
- `estado_comercial`: `BLOQUEADO`
- `auditor`: reauditoria canônica de 21/10/2026 (só leitura: `origin/main`, spec
  vivo via `doctl --context shopman-do-app-admin`, sondas públicas, `gh`,
  `doctl databases`); auditoria anterior `GLR-2026-10-10`

## Reauditoria técnica parcial de 02/11/2026

A coleta somente leitura de **02/11 às 21:57 BRT (03/11 às 00:57 UTC)** está em
[evidência sanitizada](../reports/go-live-resumption-20261102/evidence/ci-deploy-live-20261103T005747Z.json).
Somente as linhas com esse carimbo foram remedidas. O cabeçalho da auditoria de
21/10 e as demais evidências históricas não recebem uma data nova por inferência.
O estado comercial continua **BLOQUEADO**. A confirmação de produção física é
sempre humana, no equipamento e na operação reais; CI, deploy e HTTP 200 não a substituem.

## Como ler

Estados permitidos:

- `VERIFICADO`: há fonte datada e sanitizada para a afirmação exata;
- `PENDENTE`: trabalho ou evidência ainda precisa ser produzido;
- `BLOQUEADO`: depende de decisão/ação externa identificada;
- `DESCONHECIDO`: o acesso ou a evidência não permite concluir;
- `N/A`: não se aplica ao escopo confirmado.

Um workflow verde não autoriza dinheiro real, emissão fiscal, envio, corrida,
DNS, mudança de credencial ou lançamento comercial.

## Como remedir

A linha `production-readiness` se mede no ALVO, não na árvore local:

```bash
make production-readiness target=1 context=shopman-do-app-admin   # spec vivo + /health/ /ready/
make deploy-spec-drift context=shopman-do-app-admin                # drift do spec
doctl --context shopman-do-app-admin databases backups <id do cluster>
```

O modo alvo lê o spec vivo com `doctl apps spec get` (só leitura), avalia o
ambiente efetivo de cada componente Django e sonda `/health/` e `/ready/`.
Detalhe em [commands.md](../reference/commands.md#modo-alvo-target1-o-app-vivo-não-esta-árvore).

## Matriz corrente

O carimbo `verificado_em` do cabeçalho vale para todas as linhas, salvo quando a
evidência informa outro instante.

<!-- canonical-readiness:start -->
| Critério | Estado | Ambiente | Fonte / evidência sanitizada | Owner | Próximo evento |
|---|---|---|---|---|---|
| Baseline candidata | VERIFICADO | GitHub `main` | 02/11 21:57 BRT: fonte observada `0dc8b733032cf91b4bfff4c02f65fc62ce538236`; o manifesto do último deploy com componentes usa `dcec2e7fab6c09c014560ad957ce05b657f9ff07`. São fontes distintas, não uma afirmação de imagem publicada por todo commit de documentação. | Engenharia | Reauditar quando `main` mudar |
| Gates do commit | VERIFICADO | GitHub Actions | 02/11: [Security Gate 41542567718](https://github.com/nelsonboulangerie/django-shopman/actions/runs/41542567718) sucesso; merges passam pela fila e pelos checks obrigatórios versionados. Fila observada vazia na coleta. | Engenharia | Reexecutar no PR/merge group que alterar a baseline |
| Publicação de imagens | VERIFICADO | GitHub Actions / DOCR | 02/11: [Deploy Images 41542566743](https://github.com/nelsonboulangerie/django-shopman/actions/runs/41542566743) sucesso, `nothing_published`; último manifesto com componentes no [run 41536727986](https://github.com/nelsonboulangerie/django-shopman/actions/runs/41536727986), SHA `dcec2e7fab6c`, digests de storefront/floor/office preservados na evidência. Digest efetivo de `web` não foi exposto pela API e não é inferido da tag. | Plataforma | Relacionar manifesto e deployment quando houver componente publicado |
| Deployment técnico | VERIFICADO | DigitalOcean `shopman-nelson` | 02/11 21:57 BRT: `70137568-85dd-4460-82f2-1489f1d8bafb` ACTIVE, atualizado em `2026-11-02T22:34:16Z`; mesmo ID do manifesto 41536727986. | Plataforma | Relacionar o próximo manifesto publicado ao próximo ACTIVE |
| Smoke pós-deploy | VERIFICADO | app vivo | 02/11: [Pre-go-live Smoke 41542715496](https://github.com/nelsonboulangerie/django-shopman/actions/runs/41542715496) sucesso às 23:06Z; `/ready/` 200 e catálogo com 40 SKUs, 18 disponíveis. | Plataforma | Repetir depois de cada deploy publicado |
| Banco/cache/migrations do processo vivo | VERIFICADO | app vivo | 02/11 21:57 BRT: `/health/` e `/ready/` 200; `database`, `cache`, `migrations` e `queue` `ok` na evidência alvo. | Plataforma | Repetir no ensaio geral e no dia D |
| Tag `go-live-v1` / ADR-015 | VERIFICADO | Git/GitHub | tag `go-live-v1` remota ausente; ADR-015 **inativa**. A trava `migration_safety` já roda antes do `migrate` no job `release` do spec vivo (`target.release_job` OK) e só endurece com a tag ou `SHOPMAN_GO_LIVE=true` | Engenharia | No corte: tag depois do deploy ACTIVE ([cutover](../runbooks/go-live-cutover.md) §0a, "Dia D · deploy") |
| Versão Django | VERIFICADO | repositório | `pyproject.toml`: `Django>=6.1,<6.2`; `docs/status.md` e runtime apontam para o mesmo contrato | Engenharia | Gate `make canonical-docs` acompanha qualquer bump |
| Onde vira produção | VERIFICADO | DigitalOcean `shopman-nelson` | D-029 (dono, 10/10): no próprio app vivo, mesmo banco (`shopman-staging-postgres`, pg 16, único cluster da conta); apagar o sintético, carregar dados reais, virar as chaves. `.do/app.subdomains.yaml` anotado como referência morta | Pablo | Executar pelo [cutover](../runbooks/go-live-cutover.md) §0a |
| Domínio `www.nelsonboulangerie.com.br` | VERIFICADO | app vivo | spec vivo: PRIMARY no `shopman-nelson`, junto de `api.`, `admin.` e dos apps de operador; com a D-029 é o domínio comercial | Pablo / owner comercial | Nenhum DNS muda na virada |
| Data e degraus da virada | VERIFICADO | produto/operação | D-030 (dono, 10/10): sem data fixa; vira quando esta matriz fechar, nos degraus do [cutover](../runbooks/go-live-cutover.md) (canário autorizado, GO limitado, expansão por nova decisão) | Pablo / owner de produto | Reavaliar quando as linhas abertas fecharem |
| Escopo v1 de iFood, ManyChat/Concierge, Machine, fiscal e Marketing | VERIFICADO | produto/operação | decisão do dono em 01/10/2026 (D-017): fora só Marketing e B.I.; iFood, Concierge, Machine e fiscal entram. Concierge hoje em modo `assist`, só leitura, liberado para um contato (D-018) | Pablo / owner de produto | Abrir a triagem para todos na abertura é decisão pendente (painel B10) |
| Perfil comercial do runtime | BLOQUEADO | app vivo | 02/11 21:57 BRT: `production.profile` FAIL, `SHOPMAN_ENVIRONMENT=staging`, Pix `payment_mock`, mocks e captura de teste ligados. | Plataforma + Pablo | Ensaio do Pix real e delta do spec do dia D, sem ligar automaticamente |
| Drift do spec vivo | VERIFICADO | DigitalOcean `shopman-nelson` | 02/11 19:37Z: `deployment_drift` PASS no [Watchman 41511486984](https://github.com/nelsonboulangerie/django-shopman/actions/runs/41511486984). O perfil global está WARN por prazos de credenciais, não por drift. | Plataforma | Repetir antes de qualquer apps update |
| Credenciais e integrações externas | BLOQUEADO | app vivo | 02/11 21:57 BRT: `target.money_and_fiscal` FAIL; Efí sandbox, Stripe `pk_test_`, ambiente Focus e resolver final não comprovados para produção. Sete segredos de produção continuam DESCONHECIDOS, sem baseline de rotação. Ensaios comerciais de iFood/Machine/WhatsApp não foram refeitos nesta coleta. [Matriz de credenciais](GO-LIVE-CREDENTIALS-MATRIX.md). | Owners por integração | Credenciais e homologações de produção, com ensaio autorizado pelo dono |
| Chaves do corte (senha e 2FA do Admin, `SHOPMAN_GO_LIVE`) | BLOQUEADO | app vivo | 02/11 21:57 BRT: `target.cutover_switches` FAIL, 2FA e GO_LIVE ausentes. A permissão histórica de `admin/admin` no alpha não dispensa trocar a senha, cadastrar 2FA e trocar PIN antes da virada; credencial não foi testada nesta coleta. | Pablo | Sessão humana de segurança antes do corte; não ligar 2FA sem cadastro |
| `production-readiness` com ambiente alvo | BLOQUEADO | app vivo | 02/11 21:57 BRT: modo alvo somente leitura, 5 PASS (`target.spec`, `target.in_place`, `target.release_job`, `target.health`, `target.ready`) e 3 FAIL (`production.profile`, `target.money_and_fiscal`, `target.cutover_switches`). Evidência JSON sanitizada, sem alteração no vivo. | Engenharia + Plataforma | Aplicar delta autorizado do dia D e repetir no alvo |
| Fallbacks perigosos de dinheiro e fiscal | VERIFICADO | código | [inventário](fallbacks-perigosos-go-live.md): os 18 fechados no código (19/10). Os últimos: resolver fiscal quebrado grita e o `SHOPMAN_E028` reprova no boot (16, #1894), envio sem backend nomeado não cai no console (14, #1898), cancelar venda recente com trava de replay (18, #1918); 4 e 13 já estavam fechados no `main`. Da mesma frente: destrave por PIN com rate-limit (#1906) e teto diário de custo no geocoding reverso (#1909). Valores de ambiente (1 e 2) seguem como trava de deploy (E022/E026) | Engenharia | Nenhum no código; o ensaio geral confere o ambiente |
| Dados do Dia 1 | PENDENTE | app vivo | a loja vende 40 SKUs do seed (`/api/v1/storefront/menu/`, 10/10); catálogo consolidado, preços, fiscal por SKU, fichas, insumos e inventário de abertura por carregar; 4.819 pedidos sintéticos. Gates de leitura no ar (#1248, #1250). 13/10: apagar o sintético ensaiado numa cópia local (porta direta 25060) com `purge_synthetic_data`: 47.693 linhas em 79 tabelas, 84 tabelas de cadastro conferidas, segunda rodada vazia, `/ready/` 200 e nenhum 5xx nas rotas de API | Engenharia + Pablo | Respostas do dono à fila de divergências (painel A3/B5, o que entra no Dia 1); carga do catálogo consolidado e inventário de abertura |
| Arquivos de usuário (R2) | BLOQUEADO | app vivo | D-010 com código pronto e desligado; nenhuma `R2_*` no spec vivo (10/10): arquivo enviado some no próximo deploy. D-033: bucket sim, mas não agora | Pablo | Dono cria bucket e token ([passo a passo](../runbooks/r2-passo-a-passo-do-dono.md)) |
| Contador e advogado | BLOQUEADO | fiscal/jurídico | códigos `tPag`, entrega e iFood (#888, #897), encomenda paga antes, contingência offline, CEST e Imposto Seletivo; advogado: direito de arrependimento de 7 dias | Pablo | Uma leva única ao contador e uma pergunta ao advogado (painel C) |
| Contingência da NFC-e e rede de reserva | BLOQUEADO | loja física | Comunicador Offline da Focus sem build Linux publicada; sem roteador de failover nem nobreaks comprados. O PDV vende sem conexão (#1635), mas cartão e nota precisam de rede | Pablo | Pedido de build Linux à Focus (B9) e compra do hardware (D1 a D3) |
| QA física Omotenashi | PENDENTE | dispositivos reais | não há evidência datada de cliente, operador, cozinha e gerente na baseline | Operação | Roteiro por papel (painel A6) executado no equipamento real, com evidência sem PII |
| Impressão, gaveta e som | PENDENTE | loja física | código e agente existem; funcionamento físico atual não foi comprovado | Operação | Validar as três vias do pedido, gaveta, som e queda de rede no balcão real (painel D4) |
| Backup/PITR | VERIFICADO | `shopman-staging-postgres` | 02/11 21:57 BRT: PG16 online, um nó de 1 GB; 8 backups diários de `2026-10-27T00:13:18Z` a `2026-11-03T00:13:23Z`. PITR é capacidade do serviço, não prova de um novo ensaio de restore ou reapontamento; nenhum foi executado nesta coleta. | Plataforma | Repetir na véspera e registrar ponto UTC no dia D |
| Ensaio de restore | VERIFICADO | banco isolado de recuperação | 01/10/2026: restore lógico ([Ensaio de 01/10/2026](../runbooks/backup-e-restore.md#ensaio-de-01102026)) e **fork pelo painel** (D-021): cluster `shopman-staging-postgres-oct-1-backup`, cerca de 7 min até `online`, 191 tabelas conferidas, 0 migração pendente; cluster apagado pelo dono no mesmo dia | Plataforma + owner | Nenhum até o dia D; o banco de produção é o mesmo (D-029) |
| Reapontar o app para banco restaurado | PENDENTE | app vivo + cluster de ensaio | único passo do rollback de dado nunca ensaiado ([backup-e-restore.md](../runbooks/backup-e-restore.md), "NÃO verificado") | Pablo + Plataforma | Ensaio junto do ensaio geral: [cutover](../runbooks/go-live-cutover.md) §0b |
| Banco de um nó, sem standby | VERIFICADO | `shopman-staging-postgres` | decisão do dono em 23/10/2026: cluster de **um nó** (1 GB, pool PgBouncer de 5 conexões de servidor, `max_connections` 25; `config/settings.py`), **sem nó de reserva por ora**; perda do nó é recuperação pela DO ou restore ([backup-e-restore.md](../runbooks/backup-e-restore.md)), com indisponibilidade enquanto isso. O estado verificado é a decisão, não a redundância | Pablo | Reavaliar quando a loja online pesar no faturamento (laudo GLR de 23/10, O10) |
| Aprovação comercial / GO-NO-GO | BLOQUEADO | lançamento comercial | não existe assinatura contextual do owner/incident commander para esta baseline | Pablo + incident commander | Decisão humana no momento do corte, depois dos demais gates |
| Monitoramento de infraestrutura | VERIFICADO | app vivo / CI | 02/11 19:37Z: Watchman `production_contract`, `deployment_drift` e `external_monitoring` PASS; `expiry_lifecycle` WARN, dois recursos exigem ação. Workflow verde não significa ausência de avisos. | Plataforma | Acompanhar os prazos abaixo |
| Renovação de credenciais de infraestrutura | PENDENTE | DigitalOcean / CI | 02/11: token de deploy vence 30/12/2026 (D-58) e token administrativo vence 31/12/2026 (D-59), conforme Watchman; nenhum token foi rotacionado nesta auditoria. | ti@boulangerie.com.br | Inventariar consumidores e rotacionar com sobreposição antes do vencimento |
| Bootstrap administrativo atual | DESCONHECIDO | job release do deployment ACTIVE | 02/11 21:57 BRT: logs de release acessíveis, 358 linhas, sem erro; há marcador de setup_groups, mas não marcador suficiente de bootstrap. ACTIVE e ausência de erro não provam credencial ou bootstrap atual. | Plataforma + Pablo | Evidência datada do bootstrap e confirmação humana da troca da credencial no corte |
| Vulnerabilidade transitiva do lint | PENDENTE | dependências de desenvolvimento / CI | Correção de segurança #2093 mantém onze alertas moderados de minimatch somente sob eslint-plugin-import-x 4.17.1: dev=true, padrões vindos da configuração do repositório; plugin ainda exige makeRe removido em minimatch 11. Sem allowlist nova nem redução de gate. [Análise](../reports/go-live-resumption-20261102/security-glob-minimatch.md). | Engenharia / ti@boulangerie.com.br | Rever até 09/11/2026 e quando houver plugin compatível com versão corrigida |
<!-- canonical-readiness:end -->


## Leitura da baseline técnica

O ambiente observado está vivo e recebeu a baseline auditada. A cadeia
`main → Deploy Images → deploy_on_push → deployment ACTIVE → Pre-go-live Smoke`
foi comprovada. (Desde 30/09/2026 o elo `deploy_on_push` virou UM deployment
criado pelo próprio Deploy Images, `deploy_mode: single_deployment`; ver
[deploy.md](../guides/deploy.md).) Isso é **produção técnica de software** no sentido de haver um
serviço acessível e operado; não significa lançamento oficial, tráfego aprovado
ou autorização para efeitos externos.

Desde a D-030 (10/10/2026) não há fases com data: a virada acontece quando esta
matriz fechar, nos degraus do cutover. Os termos históricos abaixo seguem com
uso restrito:

| Termo histórico | Uso permitido agora |
|---|---|
| `staging` | somente quando uma fonte datada nomeia explicitamente o ambiente |
| `alpha` / `beta` / `soft launch` | rótulos históricos; não expressam estado corrente |
| produção técnica | app vivo com deployment e smoke comprovados |
| produção comercial | requer domínio, escopo, provedores e GO/NO-GO aprovados |
| lançamento oficial | marco comercial humano; nunca inferido de CI/deploy |

## Evidência que não pode ser promovida por inferência

- Variável declarada no spec não comprova valor válido.
- Adapter construído não comprova adapter selecionado no ambiente.
- Processo `ACTIVE` não comprova o perfil de boot de produção comercial.
- Fixture, teste hermético ou provider mock não comprova sandbox.
- Sandbox não comprova produção.
- Smoke HTTP não comprova pagamento, estorno, emissão fiscal, mensagem ou corrida.
- Domínio roteado não comprova aprovação comercial.

## Gates para cutover

Antes de abrir o [runbook de cutover](../runbooks/go-live-cutover.md), todas as
linhas aplicáveis precisam estar `VERIFICADO` ou `N/A`, com a decisão humana
registrada. `DESCONHECIDO`, `PENDENTE` e `BLOQUEADO` impedem o corte.

Fontes de procedimento:

- [Pré-flight](../runbooks/go-live-preflight.md)
- [Matriz de credenciais](GO-LIVE-CREDENTIALS-MATRIX.md)
- [Cutover](../runbooks/go-live-cutover.md)
- [Rollback](../runbooks/rollback-de-deploy.md)
- [Backup e restore](../runbooks/backup-e-restore.md)
