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
- [x] Restore ensaiado em destino isolado; RTO/RPO e validação de dados anexados.
  01/10/2026: fork pelo painel em cerca de 7 min, ponto mais recente (RPO de minutos), 191
  tabelas conferidas, 0 migração pendente. Evidência: [backup-e-restore.md §1b](backup-e-restore.md).
  Reapontar o app para o cluster restaurado não foi ensaiado.
- [ ] Deployment anterior e procedimento de rollback identificados.
- [ ] [Rollback de deploy](rollback-de-deploy.md) revisado pelo incident commander.

## 4. Integrações externas

> ⛔ **Pix real ensaiado ANTES da virada, não no dia dela.** Efí, Stripe e Focus
> são as últimas chaves a **LIGAR**, não as últimas a **ENSAIAR**.
>
> - [ ] **Ensaio do Pix real no alpha:** Pix em `payment_efi` com
>   `EFI_SANDBOX=true` **e** `SHOPMAN_EXPOSE_MOCK_CAPTURE=false`. Com isso o
>   botão público "Simular pagamento" (o cliente quita o próprio pedido) fecha
>   **por construção**: `mock_capture_allowed`
>   (`shopman/shop/services/payment.py`) exige que o adapter efetivo do método
>   seja o simulado. Não basta desligar só a flag: perde-se o ensaio. Prova
>   esperada: um Pix de sandbox cobrado, webhook recebido, pedido pago pelo
>   caminho real, e a tela de Pix sem o botão.
> - [ ] **Rotacionar `EFI_WEBHOOK_TOKEN` antes de ligar a Efí de produção**
>   (D22, [PENDING-DECISIONS](../reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md)):
>   o token atual é de sandbox e, em produção, é a autenticação única do
>   webhook. Rotacionar = trocar o segredo e recadastrar a URL na Efí.
> - [ ] Stripe (`sk_test_`/webhook de teste) e Focus (homologação) exercidos
>   no alpha pelo caminho real antes de trocar para as chaves de produção.
>
> Origem: D-006 em [DECISIONS](../coordination/DECISIONS.md) (Pix simulado
> permanece no alpha por decisão do dono, aceitável em alpha e **bloqueador em
> produção**). Enquanto este item não estiver `VERIFICADO`, o cutover para na
> regra de parada.

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
