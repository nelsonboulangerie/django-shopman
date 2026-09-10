# Marketing — efeito do provider desconhecido

**Owner:** Platform Owner. **Severidade:** alta após 15 min sem owner.
**Invariante:** resposta perdida nunca vira retry cego.

## Quando abrir

- target/attempt `unknown`;
- alerta `marketing_unknown_stale`;
- timeout ou conexão perdida depois de o provider possivelmente aceitar o efeito.

## Primeiros 2 minutos

1. Copie receipt e plataforma; preserve attempt/target refs técnicas.
2. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
3. Atribua owner e checkpoint antes de 15 min.
4. Bloqueie retry desse conjunto até a consulta de reconciliação terminar.

## Diagnóstico read-only

Confirme contagem `unknown`, attempts e reconciliations pendentes. A consulta local
não chama provider; a Action de reconciliação é lookup-only e separada do boundary de
send. Use apenas erro classificado, nunca resposta bruta do fornecedor.

## Freeze/circuit

Pause a plataforma se unknown crescer ou não houver capacidade de lookup. Freeze
global quando o mesmo incidente puder causar duplicidade em mais de um canal.

## Decisões proibidas

- não converter timeout em failed;
- não executar send novamente, nem por painel do provider;
- não copiar provider response, telefone ou conteúdo para ticket/log;
- não fechar por ausência de confirmação antes do prazo de reconciliação.

## Comunicação

Informe receipt, plataforma, idade do unknown, quantidade, owner da consulta e próximo
checkpoint. Diga explicitamente “efeito incerto; retry bloqueado”.

## Recuperação idempotente

Autorize a Action `reconcile_delivery`. Ela cria/reutiliza uma intenção lookup-only e
nunca chama send. Resultado confirmado encerra o target; falha final encerra sem retry;
outage de lookup mantém o item seguro e reagendado. Retry só depois de resultado
autoritativo `failed_retryable`.

## Fechamento e reconciliação

Feche com unknown=0 ou exceção com owner/prazo explícitos, provider receipt sanitizada,
agregado recalculado e prova de que attempt count não cresceu durante o lookup.

## Drill local

`make marketing-drills` simula outage do lookup e prova requeue segura sem send. O
operador não autor deve escolher reconciliação, recusar retry e registrar owner/15 min.
