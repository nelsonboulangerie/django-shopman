# Pedido remoto preso

## Sintoma visivel

Cliente veio por WhatsApp/Nuxt/Ionic, mas o pedido nao avanca: pagamento nao
aparece, tracking fica parado, AccessLink expirou, ManyChat nao responde, hold
sumiu ou directive falhou.

## Impacto

Cliente perde confianca, estoque pode ficar reservado indevidamente e operador
pode tentar corrigir pelo caminho errado.

## Diagnostico

Comece pelo pedido especifico:

```bash
python manage.py diagnose_remote_order ORDER-REF
```

Depois rode apenas os diagnosticos relacionados ao achado:

```bash
make diagnose-worker
make diagnose-payments
make diagnose-webhooks
python manage.py release_expired_holds --dry-run
python manage.py auth_cleanup --dry-run
```

Leia `result=OK/WARN/FAIL` e as linhas `recommendation=...`. O comando
`diagnose_remote_order` nao altera estado; ele so le Order, Payman, Directives,
Stockman, channel policy e projection conversacional.

## Acao imediata segura

1. Nao editar `Order.status` direto.
2. Nao marcar pagamento manualmente para liberar pedido digital.
3. Nao recriar regra de disponibilidade/preco no ManyChat.
4. Preservar `order_ref`, `intent_ref`, directive ids, hold ids e horario.

## Recuperacao por causa

### Aguardando pagamento

- Se o cliente diz que pagou, validar gateway/Payman.
- Rodar primeiro:

```bash
python manage.py reconcile_payments --since=4h --dry-run
```

- Executar sem `--dry-run` apenas se o dry-run e o gateway concordarem.

### Aguardando confirmacao

- Verificar se `confirmation.timeout` existe e se o worker esta processando.
- Se o pedido esta `new` com pagamento capturado, operador deve confirmar ou
  rejeitar pelo fluxo canonico; gateway nao confirma pedido operacionalmente.

### Directive failed/running/queued

Primeiro classifique a evidência no pedido e no diagnóstico existente. Status de
worker não prova ausência de efeito remoto. `started`/`unknown` em notificação ou
courier significa que o fornecedor pode ter aceitado; `done` sem comprovante não
prova que o cliente recebeu/leu. Não apagar receipt/chave nem editar payload para
liberar a fila. Ack de alerta não resolve a pendência do pedido ou do livro.

| Evidência | Responsável pela retomada | Próxima ação no recurso original | Encerramento comprovado |
| --- | --- | --- | --- |
| Comando local aplicado, resposta perdida | Operador autenticado do pedido | Consultar resultado com a mesma intenção; a interface retoma o receipt | Estado/evento local e receipt concordam, sem segundo efeito |
| Base alterada por outra pessoa | Operador autorizado para o campo | Conferir estado atual, preservar rascunho e confirmar a nova intenção explicitamente | Revisão atual aceita e resultado consultável |
| `started`/`unknown` externo | Responsável técnico do turno; dono nominal/SLA dependem do gate operacional | Conferir a tentativa existente pelo procedimento homologado do fornecedor; conservar chave e contexto | Aceite/referência remota ou prova de não aplicação; nunca idade/timeout sozinhos |
| Recusa comprovada, sem efeito | Responsável pelo tópico | Corrigir causa no recurso/configuração canônica; só então permitir o retry existente | Tentativa faltante concluída com prova, sem repetir as aceitas |
| Caixa físico pendente, inclusive pedido completed | Operador com permissão e custódia/turno válidos | Abrir acerto do pedido, conferir dinheiro/equipamento e confirmar os campos físicos | Entry e Shift canônicos correspondentes; não basta fechar alerta |
| Leitura indisponível/obsoleta | Operador do recurso | Conservar leitura/rascunho e atualizar; não executar ação sobre base desconhecida | Nova leitura válida com horário, contexto mantido |

Correlacione `request_id` → digest da intenção → pedido → Directive/Entry/Shift nos
logs `shopman.operational`. `operator.command.local_result` após commit é distinto
de `operator.request.finished`: um 500 de projeção pode ocorrer depois do efeito.
`operator.command.receipt` é consulta, não um novo efeito. `operator.effect.state`
indica started/accepted/unknown. Não inserir contato, token ou texto de cliente em
métricas; identificadores ficam somente na trilha controlada.

`process_directives` é consumidor com efeitos, não diagnóstico. Não executar um
lote genérico para “destravar” unknown. Consumidores anteriores aos fences não
podem coexistir nem voltar via rollback sobre essas tentativas: parar/drenar e
preservar banco/chaves antes da troca. Em ambiente real, execução/reconciliação
exige autorização específica; preparação do piloto não a concede.

### AccessLink expirado ou usado

- Gerar novo AccessLink pelo Doorman/adaptador autorizado.
- Nao reutilizar token antigo; token bruto nao e persistido.
- Rodar `python manage.py auth_cleanup --dry-run` para avaliar lixo expirado.

### ManyChat indisponivel

- A cadeia configurada em `ChannelConfig.notifications` permanece a autoridade.
  Fallback só é seguro após recusa comprovada; resposta perdida/unknown não
  autoriza enviar pelo próximo canal.
- Se for entrega de AccessLink, usar SMS/email apenas se o cliente puder ser
  identificado com seguranca.
- Registrar indisponibilidade ManyChat e manter Shopman como fonte de verdade.

### Stock hold expirado/divergente

```bash
python manage.py release_expired_holds --dry-run
```

- Se o hold expirou antes do commit, refazer availability/check pelo fluxo
  canonico.
- Se a divergencia for fisica, pausar SKU afetado e seguir runbook de estoque.

## Escalar

Escalar se ha pagamento capturado sem pedido confirmavel, directive failed
apos retries, hold divergente em pedido pago, AccessLink gerado para cliente
errado, ou ManyChat indisponivel impactando pedidos ativos.

## Evidencia minima

`order_ref`, canal, `Order.status`, `intent_ref`, status Payman/gateway, ids de
directive, ids de hold, AccessLink id/audience/source, saida de
`diagnose_remote_order`, horario e acao tomada.
