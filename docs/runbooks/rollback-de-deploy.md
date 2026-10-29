# Rollback de deploy

> Resposta a regressão técnica. Estado corrente e referência do ambiente devem
> vir da [matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md), não deste arquivo.

## Quando usar

Health/readiness falha, há 5xx em massa, regressão crítica em checkout/operação,
worker/queue indisponível ou migration incompatível.

## 1. Conter e preservar

1. Parar expansão e novos deploys pelo mecanismo aprovado.
2. Registrar horário, SHA, deployment, primeiro sintoma e superfícies afetadas.
3. Preservar logs e métricas; não apagar fila, receipt, webhook ou registro de
   reconciliação.
4. Se houver risco de dado, registrar imediatamente a referência de
   restauração disponível. Não afirmar backup/PITR sem prova do ambiente.

## 2. Classificar antes de reverter

| Classe | Ação inicial |
|---|---|
| Só código | candidato a rollback do deployment |
| Migration aditiva | código anterior pode ser compatível; confirmar antes |
| Backfill/data migration | verificar idempotência e efeitos parciais |
| Contract/destrutiva | não reverter código às cegas; escalar para plano de restore |
| Efeito externo | congelar novos efeitos e reconciliar provider antes de repetir |

Consulte [production-upgrades](../guides/production-upgrades.md) e a
[ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md). A ADR só
está ativa quando `go-live-v1` existe.

### A tag `go-live-v1` no rollback

- **NO-GO no dia D:** a tag não existe, porque só nasce depois do GO
  ([cutover §0a](go-live-cutover.md#0a-sequência-do-dia-d-painel-de-go-live-10102026)).
  Se foi criada antes da decisão, apague local e remota no mesmo turno
  (`git tag -d go-live-v1`, `git push origin :refs/tags/go-live-v1`), com a
  palavra do incident commander, e confira com
  `git ls-remote --tags origin go-live-v1` (saída vazia). As chaves do corte
  voltam aos valores anotados na abertura, inclusive `SHOPMAN_GO_LIVE`.
- **Rollback depois do GO** (loja aberta, dado real): a tag fica. Ela não marca
  um deploy, marca a política; reverter código não devolve o projeto ao
  pré-go-live.

## 3. Rollback de código

Muda o app vivo `shopman-nelson`: quem age é o incident commander (Pablo), ou um
agente com a palavra dele dada no momento. Os alvos `make deploy-*` são locais
(docker desta máquina) e não revertem nada no vivo; `make deploy-ps target=1`
imprime os comandos de leitura do vivo.

1. Identificar o último deployment comprovadamente verde
   (`doctl --context shopman-do-app-admin apps list-deployments 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`).
2. Confirmar que o rollback não dispara migration incompatível.
3. Usar o mecanismo de rollback/redeploy aprovado para o ambiente; não mover
   tags ou aplicar spec incompleto.
4. Esperar o deployment correto ficar pronto.
5. Validar `/health/`, `/ready/`, loja, login e um fluxo **não mutante** antes
   de considerar qualquer canário real.

## 4. Migration ou dado

Para contract/destrutiva, divergência financeira/fiscal ou corrupção:

1. manter tráfego/efeitos congelados;
2. chamar owner de banco e incident commander;
3. restaurar somente em destino/procedimento aprovado, usando referência
   registrada antes do incidente, e reapontar o app pelo
   [cutover §0b](go-live-cutover.md#0b-ensaio-de-reapontar-o-app-para-o-banco-restaurado):
   esvaziar o Valkey depois de reapontar (o cache guarda o estado do banco de
   antes) e trocar o `cluster_name` também no spec versionado
   `.do/app.alpha-subdomains.yaml`, no PR do incidente;
4. validar integridade e reconciliação em dry-run;
5. promover o resultado apenas após decisão humana.

Nunca restaurar por cima do banco vivo apenas para acelerar a recuperação.

## 5. Efeitos externos

- Pagamento: reconciliar antes de estornar ou repetir.
- Fiscal: conferir status no provider antes de emitir/cancelar.
- Mensagem/Marketing: preservar receipts/outbox; efeito `unknown` não é retry.
- Delivery: conferir corrida antes de abrir/cancelar outra.

Qualquer ação real nessas linhas exige autorização específica no momento.

## 6. Evidência mínima

- SHA/deployment com problema e SHA/deployment recuperado;
- classe da mudança;
- horários de detecção, contenção e recuperação;
- health/readiness e superfície validada;
- referência de backup/restore quando usada;
- reconciliação de efeitos externos;
- owner e próximo evento.
