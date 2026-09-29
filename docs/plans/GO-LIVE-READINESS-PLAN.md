# GO-LIVE-READINESS-PLAN — matriz canônica de prontidão

> **Única fonte operacional de estado de go-live.** Documentos de arquitetura,
> roadmap, credenciais e runbooks apontam para esta matriz; não mantêm cópias do
> status.

- `auditoria_id`: `GLR-2026-09-29`
- `verificado_em`: `2026-09-29T03:06:10Z`
- `baseline_git`: `1f497db90f150b0a497cd7001d11df19fc7491b0`
- `ambiente_observado`: app DigitalOcean `shopman-nelson`, ambiente técnico vivo
  de pré-go-live
- `estado_comercial`: `DESCONHECIDO`
- `auditor`: execução R6 do programa de recuperação

## Como ler

Estados permitidos:

- `VERIFICADO`: há fonte datada e sanitizada para a afirmação exata;
- `PENDENTE`: trabalho ou evidência ainda precisa ser produzido;
- `BLOQUEADO`: depende de decisão/ação externa identificada;
- `DESCONHECIDO`: o acesso ou a evidência não permite concluir;
- `N/A`: não se aplica ao escopo confirmado.

Um workflow verde não autoriza dinheiro real, emissão fiscal, envio, corrida,
DNS, mudança de credencial ou lançamento comercial.

## Matriz corrente

O carimbo `verificado_em` do cabeçalho vale para todas as linhas, salvo quando a
evidência informa outro instante.

<!-- canonical-readiness:start -->
| Critério | Estado | Ambiente | Fonte / evidência sanitizada | Owner | Próximo evento |
|---|---|---|---|---|---|
| Baseline candidata | VERIFICADO | GitHub `main` | `origin/main` = `1f497db90`; merge #1226 em 2026-09-29T02:26:37Z | Engenharia | Reauditar quando `main` mudar |
| Gates do commit | VERIFICADO | GitHub Actions | Check-runs do SHA: Runtime, Surfaces, Omotenashi, Security, Production Contract, Operator Groups e Coverage concluíram com sucesso | Engenharia | Reexecutar no PR/merge group que alterar a baseline |
| Publicação de imagens | VERIFICADO | GitHub Actions / DOCR | [Deploy Images run 36515098853](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36515098853), sucesso, SHA `1f497db90`, 2026-09-29T02:59:03Z–03:01:52Z | Plataforma | Novo merge em `main` gera novo manifesto |
| Deployment técnico | VERIFICADO | DigitalOcean `shopman-nelson` | deployment `57e43069-0a75-47ec-badb-7fbecd8f635f`, criado 2026-09-29T03:00:54Z, `ACTIVE` às 03:05:16Z; imagens com `deploy_on_push=true` | Plataforma | Relacionar o próximo manifesto ao próximo deployment |
| Smoke pós-deploy | VERIFICADO | ambiente técnico vivo | [Pre-go-live Smoke run 36515319701](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36515319701), sucesso no mesmo SHA; `/ready/`, menu, checkout não mutante e SSR verificados | Plataforma | Repetir depois de cada Deploy Images com componentes publicados |
| Banco/cache/migrations do processo vivo | VERIFICADO | ambiente técnico vivo | `/ready/` retornou 200 no run 36515319701; o endpoint falha fechado para DB, cache, migrations pendentes e workers/filas | Plataforma | Preservar saída do smoke do próximo candidato |
| Tag `go-live-v1` / ADR-015 | VERIFICADO | Git/GitHub | tag remota ausente; ADR-015 **inativa**. O repositório tem 268 migration files na baseline; isso não autoriza novo squash/reset | Engenharia | No corte autorizado: backup/restore, decisão de migration e só então tag |
| Versão Django | VERIFICADO | repositório | `pyproject.toml`: `Django>=6.1,<6.2`; `docs/status.md` e runtime apontam para o mesmo contrato | Engenharia | Gate `make canonical-docs` acompanha qualquer bump |
| Domínio `www.nelsonboulangerie.com.br` | DESCONHECIDO | ambiente técnico vivo | spec vivo comprova domínio PRIMARY apontando para `shopman-nelson`; não há evidência de aprovação como produção comercial | Pablo / owner comercial | Registrar decisão explícita: domínio técnico, comercial ou ambos |
| Nomenclatura de fases | DESCONHECIDO | produto/operação | documentos históricos usam `staging`, `alpha`, `beta`, `soft` e `oficial`; não há confirmação atual de que sejam fases oficiais | Pablo / owner de produto | Aprovar nomes, critérios de entrada/saída e responsáveis |
| Escopo v1 de iFood, ManyChat/Concierge, Machine, fiscal e Marketing | DESCONHECIDO | produto/operação | capacidade de código não prova inclusão comercial | Pablo / owner de produto | Assinar inclusão/exclusão por frente antes do pré-flight final |
| Credenciais e integrações externas | PENDENTE | ambiente técnico vivo | [matriz de credenciais](GO-LIVE-CREDENTIALS-MATRIX.md) separa nome declarado, adapter, boot gate e exercício; nenhuma presença de variável prova operação | Owners por integração | Produzir probes sanitizados no ambiente e nível aprovados |
| `production-readiness` com ambiente alvo | PENDENTE | ambiente comercial a definir | não há artefato datado anexado para a configuração comercial final | Plataforma + Pablo | Rodar o perfil após domínio, escopo e credenciais aprovados |
| QA física Omotenashi | PENDENTE | dispositivos reais | não há evidência datada de cliente, operador, cozinha e gerente na baseline | Operação | Executar roteiro em aparelho/equipamento real e anexar evidência sem PII |
| Impressão, gaveta e som | PENDENTE | loja física | código e agente existem; funcionamento físico atual não foi comprovado nesta auditoria | Operação | Validar equipamento, origem autorizada e procedimento de fallback |
| Backup/PITR | DESCONHECIDO | banco do ambiente alvo | leitura de bancos via API DigitalOcean retornou 403; alegações antigas não foram tratadas como prova | Plataforma | Anexar política real, janela, referência e owner sem expor credenciais |
| Ensaio de restore | DESCONHECIDO | banco isolado de recuperação | nenhuma evidência datada e recuperável foi localizada | Plataforma | Restaurar em cluster isolado, validar dados e registrar RTO/RPO |
| Aprovação comercial / GO-NO-GO | BLOQUEADO | lançamento comercial | não existe assinatura contextual do owner/incident commander para esta baseline | Pablo + incident commander | Decisão humana no momento do corte, depois dos demais gates |
<!-- canonical-readiness:end -->

## Leitura da baseline técnica

O ambiente observado está vivo e recebeu a baseline auditada. A cadeia
`main → Deploy Images → deploy_on_push → deployment ACTIVE → Pre-go-live Smoke`
foi comprovada. Isso é **produção técnica de software** no sentido de haver um
serviço acessível e operado; não significa lançamento oficial, tráfego aprovado
ou autorização para efeitos externos.

Até o gate humano de fases ser resolvido, os termos históricos abaixo têm uso
restrito:

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
