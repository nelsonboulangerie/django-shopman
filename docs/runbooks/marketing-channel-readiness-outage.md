# Marketing — readiness de canal degradada ou indisponível

**Owner:** Platform Owner. **Severidade:** alta antes de blast.
**SLO:** evidência de readiness com menos de 5 min.

## Quando abrir

- `ready` muda para `degraded`, `blocked` ou `unknown`;
- alerta `marketing_readiness_stale`;
- flow/template ativo não pode ser confirmado ou adapter/credencial fica indisponível.

## Primeiros 2 minutos

1. Identifique plataforma e state/reason code apresentados pela Action.
2. Verifique `/health/live/`, `/health/ready/` e o `/health/ready` do BFF.
3. Rode `make marketing-diagnose platform=<platform>`.
4. Bloqueie approve/fire naquela plataforma; preserve draft e horário do operador.

## Diagnóstico read-only

Health testa BFF→Django→DB/cache/fila, nunca provider. Readiness de canal usa evidência
cacheada com `checked_at/facts_as_of`; uma fonte fora não é audiência zero nem licença
para aceitar uma ref arbitrária.

## Freeze/circuit

O backend já deve bloquear a Action do canal. Pause somente o canal afetado; freeze
global se a falha impedir revalidar consentimento/expiração ou se houver configuração
compartilhada insegura.

## Decisões proibidas

- não digitar flow/template ID manual para contornar outage;
- não habilitar adapter console em produção;
- não chamar provider em cada health probe;
- não publicar com readiness stale, unknown ou “último bom” expirado.

## Comunicação

Informe plataforma, state/reason, idade da evidência, última verificação boa, impacto em
campanhas agendadas, owner e novo checkpoint. Não exponha token ou erro bruto.

## Recuperação idempotente

Use a Action canônica de recheck/configuração com CAS, step-up e confirmação. Refetch
deve preservar draft; mudança concorrente retorna conflito e exige revisão. Reative
approve/fire somente após `ready` fresco e safe test autorizado.

## Fechamento e reconciliação

Feche quando readiness estiver fresca, a configuração versionada/auditada, campanhas
pendentes revalidadas e nenhuma tenha sido publicada durante o bloqueio.

## Drill local

`make marketing-drills` simula probe do transport falhando e exige state `unknown`. O
operador não autor deve manter a Action bloqueada e autorizar apenas recheck seguro.
