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

## 1. Abrir a janela

1. Registrar horário, incident commander, executor, observador e canal.
2. Congelar merges/deploys não relacionados pelo mecanismo aprovado.
3. Registrar SHA, ambiente, domínio e deployment anteriores.
4. Confirmar ponto de restauração e último restore ensaiado.
5. Registrar decisão **GO** assinada. Ausência de assinatura é **NO-GO**.

## 2. Preparar a release

1. Reexecutar os gates definidos no [pré-flight](go-live-preflight.md).
2. Revisar o plano de migrations e o comportamento de rollback.
3. Criar `go-live-v1` somente se a decisão humana autorizar a virada da
   ADR-015. A tag é uma mudança de política, não um marcador decorativo.
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
  [rollback](rollback-de-deploy.md) quando aplicável e preservar evidência;
- **GO limitado:** abrir somente o volume/canal aprovado e monitorar;
- **expansão:** nova decisão humana após a janela de observação. O GO limitado
  não autoriza automaticamente expansão ou lançamento oficial.

## 6. Encerramento

- registrar deployment/SHA, horário, decisão e owners;
- executar diagnósticos e reconciliação autorizados;
- registrar incidentes, efeitos `unknown` e follow-ups;
- atualizar a matriz canônica sem copiar o estado para outros documentos.
