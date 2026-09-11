# Marketing — command, outbox ou worker travado

**Owner:** SRE/Platform. **Severidade:** alta; crítica se houver risco de opt-out,
expiração ou duplicidade. **SLO:** receipt→fila ≤10 s, agendado ≤30 s.

## Quando abrir

- alerta `marketing_outbox_stuck`, `approved_graph` ou `outbox_directive`;
- receipt aceito sem avanço por 30 s;
- lease vencida, outbox `pending/claimed` antiga ou target sem Action de reparo.

## Primeiros 2 minutos

1. Copie somente a `receipt_ref` e a plataforma do alerta.
2. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
3. Registre o JSON no incidente e marque o estágio: receipt, outbox, directive ou target.
4. Se aparecer opt-out/expiração/duplicidade, aplique o freeze de Marketing e migre
   imediatamente para o runbook indicado pelo próprio diagnóstico.

## Diagnóstico read-only

O comando acima agrega ledger/fila/alertas, faz no máximo oito queries, não mostra
recipient/copy e não chama provider. Confirme também `/health/live/`,
`/health/ready/` e o `/health/ready` do BFF. Liveness verde com readiness vermelha
é dependência degradada, não motivo para reiniciar o processo web.

## Freeze/circuit

Isole a plataforma/receipt afetada. Freeze global só para risco de segurança,
duplicidade confirmada ou alcance indeterminado. Reinício de worker e ativação do
consumer exigem autorização SRE registrada; não são passos de diagnóstico.

## Decisões proibidas

- não usar `--force`, editar tabela, apagar lease ou criar Directive manualmente;
- não repetir publish/send para “ver se destrava”;
- não reiniciar web por falha de banco/fila;
- não trocar receipt, idempotency key, snapshot ou artifact.

## Comunicação

Informe: estágio, receipt técnica, plataforma, idade, contagens agregadas, freeze
aplicado, owner e próximo checkpoint. Nunca cole telefone, membro, copy ou erro bruto.

## Recuperação idempotente

Após autorização, use apenas a Action de reconciliação/retry oferecida pelo backend.
Se o handoff é incerto, reconcilie primeiro; retry só pode selecionar
`failed_retryable`. Lease stale é recuperada pelo worker canônico e o mesmo receipt
deve convergir sem uma segunda Directive.

## Fechamento e reconciliação

Feche quando outbox/targets estiverem terminais, unknown=0 ou com owner/prazo,
diagnóstico repetir `OK`, alertas estiverem reconhecidos e receipt→ledger fechar.
Registre causa, tempo de fila, ação autorizada e prova de não duplicidade.

## Drill local

`make marketing-drills` injeta lease stale e prova reclaim sem duplicar handoff. O
operador não autor deve decidir “diagnosticar → reconciliar → retry seletivo”, anotar
início/fim e confirmar que nenhuma escrita externa ocorreu.
