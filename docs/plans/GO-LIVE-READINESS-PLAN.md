# GO-LIVE-READINESS-PLAN — matriz canônica de prontidão

> **Única fonte operacional de estado de go-live.** Documentos de arquitetura,
> roadmap, credenciais e runbooks apontam para esta matriz; não mantêm cópias do
> status.

- `auditoria_id`: `GLR-2026-09-29`
- `verificado_em`: `2026-09-29T04:45:00Z`
- `baseline_git`: `ab148fbd85d50865bf107e95298b712decd9d7f4`
- `ambiente_observado`: app DigitalOcean `shopman-nelson`, ambiente técnico vivo
  de pré-go-live
- `estado_comercial`: `BLOQUEADO`
- `auditor`: execução R8 C0–C2 do programa de recuperação

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
| Baseline candidata | VERIFICADO | GitHub `main` | `origin/main` = `ab148fbd85d5`; merges #1233 e #1232 integrados | Engenharia | Reauditar quando `main` mudar |
| Gates do commit | VERIFICADO | GitHub Actions | Check-runs do SHA: Runtime, Surfaces, Omotenashi, Security, Production Contract, Operator Groups e Coverage concluíram com sucesso | Engenharia | Reexecutar no PR/merge group que alterar a baseline |
| Publicação de imagens | VERIFICADO | GitHub Actions / DOCR | [Deploy Images run 36521413976](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36521413976), sucesso no SHA `ab148fbd85d5`; manifesto contém os três componentes alterados | Plataforma | Novo merge em `main` gera novo manifesto |
| Deployment técnico | VERIFICADO | DigitalOcean `shopman-nelson` | deployment `02527053-d135-4bd3-9d32-d09dd367be19`, criado 2026-09-29T04:25:44Z, `ACTIVE` às 04:31:54Z; digest `web` confere com o manifesto | Plataforma | Relacionar o próximo manifesto ao próximo deployment |
| Smoke pós-deploy | VERIFICADO | ambiente técnico vivo | [Pre-go-live Smoke run 36521633479](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36521633479), sucesso no mesmo SHA; `/ready/`, menu, checkout não mutante e SSR verificados | Plataforma | Repetir depois de cada Deploy Images com componentes publicados |
| Banco/cache/migrations do processo vivo | VERIFICADO | ambiente técnico vivo | `/ready/` retornou 200 com DB, cache, migrations e queue `ok`; o token de auditoria recebeu 403 na API de databases | Plataforma | Preservar o smoke e obter evidência de cluster/backup com escopo mínimo |
| Tag `go-live-v1` / ADR-015 | VERIFICADO | Git/GitHub | tag remota ausente; ADR-015 **inativa**. O repositório tem 268 migration files na baseline; isso não autoriza novo squash/reset | Engenharia | No corte autorizado: backup/restore, decisão de migration e só então tag |
| Versão Django | VERIFICADO | repositório | `pyproject.toml`: `Django>=6.1,<6.2`; `docs/status.md` e runtime apontam para o mesmo contrato | Engenharia | Gate `make canonical-docs` acompanha qualquer bump |
| Domínio `www.nelsonboulangerie.com.br` | DESCONHECIDO | ambiente técnico vivo | spec vivo comprova domínio PRIMARY apontando para `shopman-nelson`; não há evidência de aprovação como produção comercial | Pablo / owner comercial | Registrar decisão explícita: domínio técnico, comercial ou ambos |
| Nomenclatura de fases | DESCONHECIDO | produto/operação | documentos históricos usam `staging`, `alpha`, `beta`, `soft` e `oficial`; não há confirmação atual de que sejam fases oficiais | Pablo / owner de produto | Aprovar nomes, critérios de entrada/saída e responsáveis |
| Escopo v1 de iFood, ManyChat/Concierge, Machine, fiscal e Marketing | DESCONHECIDO | produto/operação | capacidade de código não prova inclusão comercial | Pablo / owner de produto | Assinar inclusão/exclusão por frente antes do pré-flight final |
| Perfil comercial do runtime | BLOQUEADO | ambiente técnico vivo | [pré-flight R8](../reports/2026-09-29-r8-cutover-preflight.md): vivo ainda é staging, Pix mock, Efí sandbox, mock/debug expostos e release job sem `migration_safety` | Plataforma + Pablo | Compor o spec a partir do vivo somente após autorização; nunca aplicar o arquivo versionado sobre `EV[...]` |
| Drift do spec vivo | BLOQUEADO | DigitalOcean `shopman-nelson` | `check_do_spec_drift.py` saiu 1; envs/segredos somente no vivo seriam apagados por `apps update --spec` | Plataforma | Resolver semanticamente o drift preservando todos os valores secretos no console seguro |
| Credenciais e integrações externas | BLOQUEADO | ambiente técnico vivo | [matriz de credenciais](GO-LIVE-CREDENTIALS-MATRIX.md) e [pré-flight R8](../reports/2026-09-29-r8-cutover-preflight.md): nomes existem, mas adapter/ambiente comercial e exercício externo não fecham | Owners por integração | Aprovar escopo e produzir probes sanitizados no ambiente correto |
| `production-readiness` com ambiente alvo | BLOQUEADO | ambiente comercial a definir | o comando atual escreve fixtures em transação rollback e não possui `--read-only`; não foi executado no banco vivo | Engenharia + Plataforma | Entregar/provar modo estritamente read-only ou executar no clone descartável restaurado |
| QA física Omotenashi | PENDENTE | dispositivos reais | não há evidência datada de cliente, operador, cozinha e gerente na baseline | Operação | Executar roteiro em aparelho/equipamento real e anexar evidência sem PII |
| Impressão, gaveta e som | PENDENTE | loja física | código e agente existem; funcionamento físico atual não foi comprovado nesta auditoria | Operação | Validar equipamento, origem autorizada e procedimento de fallback |
| Backup/PITR | VERIFICADO | banco técnico observado | [auditoria somente leitura](../reports/2026-09-29-backup-pitr-verification.md): PostgreSQL 16 online, 8 backups diários consecutivos, último em `2026-09-29T00:13:26Z`, retenção/PITR de 7 dias; o 403 anterior era do contexto sem `database:read` | Plataforma | Repetir no cluster comercial final caso o cutover troque o banco |
| Ensaio de restore | BLOQUEADO | banco isolado de recuperação | a auditoria confirmou backups, mas não localizou evidência datada de restore; nenhum fork foi criado por envolver escrita e custo | Plataforma + owner | Autorizar fork temporário, validar dados por conexão direta, registrar RTO/RPO e remover com autorização |
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
