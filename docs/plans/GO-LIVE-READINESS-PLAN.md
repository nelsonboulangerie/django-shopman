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
| Baseline candidata | VERIFICADO | GitHub `main` | `origin/main` = `4541f0a8a040` (merge #1969, 21/10 00:58Z) | Engenharia | Reauditar quando `main` mudar |
| Gates do commit | VERIFICADO | GitHub Actions | todo merge passa pela fila com os checks obrigatórios de `.github/required-status-checks.json`; no push da baseline, [Security Gate run 39524633755](https://github.com/nelsonboulangerie/django-shopman/actions/runs/39524633755) sucesso | Engenharia | Reexecutar no PR/merge group que alterar a baseline |
| Publicação de imagens | VERIFICADO | GitHub Actions / DOCR | [Deploy Images run 39524633736](https://github.com/nelsonboulangerie/django-shopman/actions/runs/39524633736) sucesso na baseline, sem publicação porque #1969 só mudou documentação. O último merge com código, SHA `921d70c32758`, publicou `web`, `operator-floor` e `operator-office` no [run 39518838524](https://github.com/nelsonboulangerie/django-shopman/actions/runs/39518838524) | Plataforma | Novo merge com componente alterado gera novo manifesto |
| Deployment técnico | VERIFICADO | DigitalOcean `shopman-nelson` | deployment `19612c94-1ba1-4742-9756-8753d6442959`, `ACTIVE` em 21/10 00:12Z, corresponde ao último SHA com código `921d70c32758`; nenhum deployment era esperado para #1969 | Plataforma | Relacionar o próximo manifesto com componentes publicados ao próximo deployment |
| Smoke pós-deploy | VERIFICADO | app vivo | [Pre-go-live Smoke run 39549492431](https://github.com/nelsonboulangerie/django-shopman/actions/runs/39549492431), sucesso na baseline em 21/10 05:25Z | Plataforma | Repetir depois de cada Deploy Images com componentes publicados |
| Banco/cache/migrations do processo vivo | VERIFICADO | app vivo | `/health/` 200; `/ready/` 200 com `database`, `cache`, `migrations` e `queue` `ok` (`make production-readiness target=1`, 21/10) | Plataforma | Repetir no ensaio geral e no dia D |
| Tag `go-live-v1` / ADR-015 | VERIFICADO | Git/GitHub | tag `go-live-v1` remota ausente; ADR-015 **inativa**. A trava `migration_safety` já roda antes do `migrate` no job `release` do spec vivo (`target.release_job` OK) e só endurece com a tag ou `SHOPMAN_GO_LIVE=true` | Engenharia | No corte: tag depois do deploy ACTIVE ([cutover](../runbooks/go-live-cutover.md) §0a, "Dia D · deploy") |
| Versão Django | VERIFICADO | repositório | `pyproject.toml`: `Django>=6.1,<6.2`; `docs/status.md` e runtime apontam para o mesmo contrato | Engenharia | Gate `make canonical-docs` acompanha qualquer bump |
| Onde vira produção | VERIFICADO | DigitalOcean `shopman-nelson` | D-029 (dono, 10/10): no próprio app vivo, mesmo banco (`shopman-staging-postgres`, pg 16, único cluster da conta); apagar o sintético, carregar dados reais, virar as chaves. `.do/app.subdomains.yaml` anotado como referência morta | Pablo | Executar pelo [cutover](../runbooks/go-live-cutover.md) §0a |
| Domínio `www.nelsonboulangerie.com.br` | VERIFICADO | app vivo | spec vivo: PRIMARY no `shopman-nelson`, junto de `api.`, `admin.` e dos apps de operador; com a D-029 é o domínio comercial | Pablo / owner comercial | Nenhum DNS muda na virada |
| Data e degraus da virada | VERIFICADO | produto/operação | D-030 (dono, 10/10): sem data fixa; vira quando esta matriz fechar, nos degraus do [cutover](../runbooks/go-live-cutover.md) (canário autorizado, GO limitado, expansão por nova decisão) | Pablo / owner de produto | Reavaliar quando as linhas abertas fecharem |
| Escopo v1 de iFood, ManyChat/Concierge, Machine, fiscal e Marketing | VERIFICADO | produto/operação | decisão do dono em 01/10/2026 (D-017): fora só Marketing e B.I.; iFood, Concierge, Machine e fiscal entram. Concierge hoje em modo `assist`, só leitura, liberado para um contato (D-018) | Pablo / owner de produto | Abrir a triagem para todos na abertura é decisão pendente (painel B10) |
| Perfil comercial do runtime | BLOQUEADO | app vivo | `make production-readiness target=1` (21/10): `production.profile` FAIL com `SHOPMAN_ENVIRONMENT=staging`, Pix em `payment_mock`, `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` e `SHOPMAN_EXPOSE_MOCK_CAPTURE` ligados; o job de release com `migration_safety` já está resolvido | Plataforma + Pablo | Ensaio do Pix real (D-031); delta do spec do dia D composto do vivo (painel A2) |
| Drift do spec vivo | VERIFICADO | DigitalOcean `shopman-nelson` | 21/10: `make deploy-spec-drift context=shopman-do-app-admin` sai `[OK]` (137 envs no vivo, 144 no arquivo); as nove diferenças são declaradas, inclusive defaults da Machine, ambiente da Focus e o resolver `intermediated_sale` reservado ao corte | Plataforma | Rodar de novo antes de qualquer `apps update` (D-009) |
| Credenciais e integrações externas | BLOQUEADO | app vivo | `target.money_and_fiscal` FAIL (21/10): `EFI_SANDBOX=true`, `FOCUS_NFE_ENVIRONMENT` ausente, Stripe `pk_test_`, resolver fiscal final sem `intermediated_sale` e segredos de produção não demonstrados. O ensaio autorizado da loja de teste do iFood fechou em 20/10 com restauração exata (#1929, #1962), mas não prova homologação comercial/produção. Machine continua sem ensaio em homologação (B7); modelos de WhatsApp sem conferência desde 29/09 (D6). [Matriz de credenciais](GO-LIVE-CREDENTIALS-MATRIX.md) | Owners por integração | Ensaio do Pix real (D-031); chaves e homologações de produção de cada fornecedor no painel deles (D5) |
| Chaves do corte (2FA do Admin e `SHOPMAN_GO_LIVE`) | BLOQUEADO | app vivo | `target.cutover_switches` FAIL (21/10): `SHOPMAN_ADMIN_REQUIRE_2FA` e `SHOPMAN_GO_LIVE` ausentes do spec. 2FA ligado sem cadastro tranca o Admin | Pablo | Sessão curta cadastra o 2FA, troca senha e PIN (D-032); as duas ligam no dia D |
| `production-readiness` com ambiente alvo | BLOQUEADO | app vivo | `make production-readiness target=1 context=shopman-do-app-admin` em 21/10: 5 OK (`target.spec`, `target.in_place`, `target.release_job`, `target.health`, `target.ready`) e 3 FAIL (`production.profile`, `target.money_and_fiscal`, `target.cutover_switches`). Sai 2 enquanto houver FAIL | Engenharia + Plataforma | Verde depois do delta do dia D; junto, `make production-readiness read_only=1` no banco alvo |
| Fallbacks perigosos de dinheiro e fiscal | VERIFICADO | código | [inventário](fallbacks-perigosos-go-live.md): os 18 fechados no código (19/10). Os últimos: resolver fiscal quebrado grita e o `SHOPMAN_E028` reprova no boot (16, #1894), envio sem backend nomeado não cai no console (14, #1898), cancelar venda recente com trava de replay (18, #1918); 4 e 13 já estavam fechados no `main`. Da mesma frente: destrave por PIN com rate-limit (#1906) e teto diário de custo no geocoding reverso (#1909). Valores de ambiente (1 e 2) seguem como trava de deploy (E022/E026) | Engenharia | Nenhum no código; o ensaio geral confere o ambiente |
| Dados do Dia 1 | PENDENTE | app vivo | a loja vende 40 SKUs do seed (`/api/v1/storefront/menu/`, 10/10); catálogo consolidado, preços, fiscal por SKU, fichas, insumos e inventário de abertura por carregar; 4.819 pedidos sintéticos. Gates de leitura no ar (#1248, #1250). 13/10: apagar o sintético ensaiado numa cópia local (porta direta 25060) com `purge_synthetic_data`: 47.693 linhas em 79 tabelas, 84 tabelas de cadastro conferidas, segunda rodada vazia, `/ready/` 200 e nenhum 5xx nas rotas de API | Engenharia + Pablo | Respostas do dono à fila de divergências (painel A3/B5, o que entra no Dia 1); carga do catálogo consolidado e inventário de abertura |
| Arquivos de usuário (R2) | BLOQUEADO | app vivo | D-010 com código pronto e desligado; nenhuma `R2_*` no spec vivo (10/10): arquivo enviado some no próximo deploy. D-033: bucket sim, mas não agora | Pablo | Dono cria bucket e token ([passo a passo](../runbooks/r2-passo-a-passo-do-dono.md)) |
| Contador e advogado | BLOQUEADO | fiscal/jurídico | códigos `tPag`, entrega e iFood (#888, #897), encomenda paga antes, contingência offline, CEST e Imposto Seletivo; advogado: direito de arrependimento de 7 dias | Pablo | Uma leva única ao contador e uma pergunta ao advogado (painel C) |
| Contingência da NFC-e e rede de reserva | BLOQUEADO | loja física | Comunicador Offline da Focus sem build Linux publicada; sem roteador de failover nem nobreaks comprados. O PDV vende sem conexão (#1635), mas cartão e nota precisam de rede | Pablo | Pedido de build Linux à Focus (B9) e compra do hardware (D1 a D3) |
| QA física Omotenashi | PENDENTE | dispositivos reais | não há evidência datada de cliente, operador, cozinha e gerente na baseline | Operação | Roteiro por papel (painel A6) executado no equipamento real, com evidência sem PII |
| Impressão, gaveta e som | PENDENTE | loja física | código e agente existem; funcionamento físico atual não foi comprovado | Operação | Validar as três vias do pedido, gaveta, som e queda de rede no balcão real (painel D4) |
| Backup/PITR | VERIFICADO | `shopman-staging-postgres` | `doctl databases backups` (21/10): 8 backups diários consecutivos de 14/10 a 21/10, último `2026-10-21T00:13:15Z`; PostgreSQL 16 `online` | Plataforma | Repetir na véspera e anotar o ponto UTC no dia D |
| Ensaio de restore | VERIFICADO | banco isolado de recuperação | 01/10/2026: restore lógico ([Ensaio de 01/10/2026](../runbooks/backup-e-restore.md#ensaio-de-01102026)) e **fork pelo painel** (D-021): cluster `shopman-staging-postgres-oct-1-backup`, cerca de 7 min até `online`, 191 tabelas conferidas, 0 migração pendente; cluster apagado pelo dono no mesmo dia | Plataforma + owner | Nenhum até o dia D; o banco de produção é o mesmo (D-029) |
| Reapontar o app para banco restaurado | PENDENTE | app vivo + cluster de ensaio | único passo do rollback de dado nunca ensaiado ([backup-e-restore.md](../runbooks/backup-e-restore.md), "NÃO verificado") | Pablo + Plataforma | Ensaio junto do ensaio geral: [cutover](../runbooks/go-live-cutover.md) §0b |
| Aprovação comercial / GO-NO-GO | BLOQUEADO | lançamento comercial | não existe assinatura contextual do owner/incident commander para esta baseline | Pablo + incident commander | Decisão humana no momento do corte, depois dos demais gates |
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
