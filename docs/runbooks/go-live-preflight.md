# Pré-flight de go-live

> Verificações antes do corte. Estado, owner e evidência ficam somente na
> [matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md). Este runbook não contém
> cronologia nem autoriza efeitos externos.

## Pré-condições

- commit candidato e ambiente alvo identificados;
- fases, domínio comercial e escopo v1 aprovados pelo owner;
- cada integração aplicável classificada na
  [matriz de credenciais](../plans/GO-LIVE-CREDENTIALS-MATRIX.md);
- incident commander, janela e canal de comunicação definidos;
- autorização contextual reservada para qualquer pagamento, estorno, emissão
  fiscal, envio ou corrida real.

Se qualquer pré-condição estiver ausente, registrar `PENDENTE`, `BLOQUEADO` ou
`DESCONHECIDO` na matriz e parar.

## 1. Identidade da release

- [ ] `git rev-parse HEAD` coincide com o SHA candidato da matriz.
- [ ] Gates exigidos pelo branch estão verdes no PR/merge group.
- [ ] `Deploy Images` produziu manifesto para o SHA correto.
- [ ] O deployment do ambiente nasceu depois do manifesto e ficou `ACTIVE`.
- [ ] `Pre-go-live Smoke` terminou no mesmo SHA.

## 2. Runtime e migrations

- [ ] `make test-migrations` e `make production-contract` verdes.
- [ ] `make production-readiness` executado no ambiente alvo, com evidência
  externa e QA exigidas pelo perfil.
- [ ] `/ready/` confirma banco, cache, migrations e workers/filas.
- [ ] `git tag -l go-live-v1` e o estado da ADR-015 coincidem com a matriz.
- [ ] Qualquer plano de migration foi classificado como aditivo, backfill ou
  contract antes do deploy.

Não executar reset/squash como “limpeza”. Se houver decisão específica de
compactação no corte, ela exige plano próprio, backup, restore ensaiado e
autorização.

## 3. Recuperação

- [ ] Política real de backup/PITR identificada no ambiente alvo.
- [ ] Referência/ponto de restauração pré-corte registrado sem segredo.
- [ ] Restore ensaiado em destino isolado; RTO/RPO e validação de dados anexados.
- [ ] Deployment anterior e procedimento de rollback identificados.
- [ ] [Rollback de deploy](rollback-de-deploy.md) revisado pelo incident commander.

## 4. Integrações externas

Para cada integração aprovada no escopo v1:

- [ ] nome da credencial declarado no secret store correto;
- [ ] adapter selecionado e boot gate aprovado;
- [ ] sandbox/homologação exercida, quando aplicável;
- [ ] webhook, replay/idempotência e evento fora de ordem verificados;
- [ ] reconciliação/dry-run sem divergência;
- [ ] fallback e kill switch conhecidos pelo operador.

Presença de variável, fixture ou teste hermético não fecha esses itens. Probes
com efeito real só acontecem com autorização explícita no momento da ação.

## 5. Segurança e operação física

- [ ] contas reais sem credenciais triviais;
- [ ] enrollment/recovery de 2FA concluído antes de qualquer flag global;
- [ ] ingress/admin aprovado; origem e proxy validados;
- [ ] alerta sintético recebido por pessoa autorizada;
- [ ] QA física de loja, operador, cozinha e gerente anexada com data/aparelho;
- [ ] impressão, gaveta, som e rede degradada testados no equipamento real;
- [ ] catálogo, estoque, preços, parâmetros fiscais e validade aprovados pelos
  respectivos owners.

## 6. Resultado

Atualizar a matriz canônica. Só abrir o [cutover](go-live-cutover.md) quando toda
linha aplicável estiver `VERIFICADO` ou `N/A`. CI verde isoladamente não atende
este critério.
