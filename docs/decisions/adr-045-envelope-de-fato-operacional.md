# ADR-045 — Envelope de fato operacional (ator, dispositivo, workstation, setor, business_date, correlação, causalidade)

**Status:** Aceito
**Data:** 2026-11-10
**Escopo:** packages/refs (ou utils), kernels, orquestrador
**Origem:** auditoria Q14 + decisão do dono (workstation, não post)

## Contexto

Os fatos operacionais (quem, de onde, em qual estação, em qual setor, em qual dia operacional,
por causa de quê) estão fragmentados: custódia de dispositivo no Cashman, device trust no
Doorman, business_date só como scope de refs (POS_TABLE), workstation/setor só em esboço de
UX. RH e Taskman (futuros) consomem exatamente isto, e sem um envelope uniforme cada um
inventaria o seu.

## Decisão

Value object OperationalContext com 7 campos: actor_ref, device_ref, workstation_ref,
sector_ref, business_date, correlation_id, causation_ref. sector é DERIVÁVEL de workstation
(mapeamento workstation→sector com fonte única), nunca duas verdades que possam divergir.
Adoção mínima: lançamentos do Cashman, Directive do Orderman, WorkOrder do Craftsman. Não é
fact-store, não é kernel.

## Consequências

- Fundação para RH e Taskman entrarem sem mudar kernels.
- Nome canônico: workstation (não post).
