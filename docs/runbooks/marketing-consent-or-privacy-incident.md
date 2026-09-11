# Marketing — incidente de consentimento ou privacidade

**Owner:** DPO/Security. **Severidade:** crítica imediata.
**Invariante:** envio após opt-out/expiração = 0.

## Quando abrir

- alerta `marketing_consent_violation`;
- suspeita de envio após revogação/expiração;
- recipient, telefone, regra livre, copy ou resposta bruta em log/metric/Sentry;
- snapshot/member exposto fora do boundary autorizado.

## Primeiros 2 minutos

1. Acione o freeze global de Marketing pela Action de emergência autorizada.
2. Preserve receipt/target/attempt refs, timestamps e hashes; não exporte members.
3. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
4. Notifique DPO/Security e SRE; registre escopo como “em apuração”, nunca zero presumido.

## Diagnóstico read-only

O snapshot agregado não contém PII. A identificação de pessoa afetada, quando
legalmente necessária, ocorre somente na interface access-controlled e sob orientação
do DPO. Use o scanner de telemetria do gate MKT042; não copie o dado encontrado.

## Freeze/circuit

Freeze global é obrigatório para violação confirmada ou escopo indeterminado. Mantenha
workers em modo de supressão/reconciliação; não destrua ledger, audit ou evidência.

## Decisões proibidas

- não apagar/editar eventos append-only, logs ou receipts;
- não “corrigir” consentimento concedendo opt-in retroativo;
- não reenviar para testar e não baixar a audiência;
- não comunicar nome/telefone/copy em canal não aprovado;
- não unfreeze sem DPO/Security distinto e reconciliação concluída.

## Comunicação

Use refs técnicas, janela temporal, plataforma, contagem/bucket, tipo de dado e estado
do freeze. DPO define notificações legais e destinatários; nenhuma hipótese é anunciada
como fato antes da reconstrução do histórico.

## Recuperação idempotente

Reconstrua current state pelo ledger append-only, aplique subtract-only ao snapshot e
suprima targets não iniciados. Efeito já confirmado não é apagado. Unfreeze exige TOTP,
duplo controle Security e receipt de reconciliação; replay não amplia audiência.

## Fechamento e reconciliação

Exija escopo fechado, timeline, causa, prova do consent state no instante do claim,
targets terminais, scan PII zero, decisão DPO e autorização independente de unfreeze.

## Drill local

`make marketing-drills` revoga consentimento após fan-out e prova supressão antes do
provider. O operador não autor deve ordenar freeze, preservação e escalada ao DPO antes
de qualquer recuperação.
