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

## 3. Rollback de código

1. Identificar o último deployment comprovadamente verde.
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
   registrada antes do incidente;
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
