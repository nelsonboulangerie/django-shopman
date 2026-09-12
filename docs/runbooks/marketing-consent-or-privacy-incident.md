# Marketing — incidente de consentimento ou privacidade

**Responsável operacional:** Pablo Valentini. **Suplente e representante da
administração:** Laís Kohatsu Kataoka. **Canal:**
`nelson@boulangerie.com.br`. **Severidade:** crítica imediata.

Essas funções não usam o título de encarregado/DPO sem nomeação formal.
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
4. Notifique o responsável operacional e a suplente; registre o escopo como “em apuração”, nunca zero presumido.

## Diagnóstico read-only

O snapshot agregado não contém PII. A identificação de pessoa afetada, quando
legalmente necessária, ocorre somente na interface de acesso restrito e sob
orientação do responsável por privacidade. Use o scanner de telemetria do gate
MKT042; não copie o dado encontrado.

## Freeze/circuit

Freeze global é obrigatório para violação confirmada ou escopo indeterminado. Mantenha
workers em modo de supressão/reconciliação; não destrua ledger, audit ou evidência.

## Decisões proibidas

- não apagar/editar eventos append-only, logs ou receipts;
- não “corrigir” consentimento concedendo opt-in retroativo;
- não reenviar para testar e não baixar a audiência;
- não comunicar nome/telefone/copy em canal não aprovado;
- não retirar o bloqueio sem decisão conjunta do responsável e da suplente, além
  da reconciliação concluída.

## Comunicação

Use referências técnicas, janela temporal, plataforma, contagem/faixa, tipo de
dado e estado do bloqueio. O responsável operacional, com a representante da
administração, decide as notificações legais e os destinatários; nenhuma hipótese
é anunciada como fato antes da reconstrução do histórico.

Quando o incidente puder causar risco ou dano relevante, o controlador deve comunicar
a ANPD e os titulares em até **três dias úteis**, ressalvado prazo específico mais curto.
Se as informações ainda estiverem incompletas, faça comunicação preliminar e complemente
depois; falta de certeza não autoriza esperar em silêncio. Registre a decisão de comunicar
ou não, o responsável, os fatos conhecidos e os horários.

Referência oficial: [Comunicação de Incidente de Segurança — ANPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

## Recuperação idempotente

Reconstrua o estado atual pelo livro append-only, reduza o público calculado e
suprima destinos não iniciados. Efeito já confirmado não é apagado. Retirar o
bloqueio exige TOTP, decisão conjunta do responsável e da suplente e recibo de
reconciliação; reprocessamento não amplia a audiência.

## Fechamento e reconciliação

Exija escopo fechado, timeline, causa, prova do consent state no instante do claim,
targets terminais, varredura de PII zerada, decisão registrada e autorização
conjunta do responsável e da suplente para retirar o bloqueio.
O registro do incidente, das avaliações e das comunicações deve ser preservado por pelo
menos **cinco anos**, conforme a Resolução CD/ANPD nº 15/2024.

## Drill local

`make marketing-drills` revoga consentimento depois da distribuição interna e
prova a supressão antes do provedor. O operador que não tenha autoridade para
decidir deve ordenar bloqueio, preservação e aviso ao responsável e à suplente
antes de qualquer recuperação.
