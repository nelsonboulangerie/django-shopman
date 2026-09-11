# ADR-029 — “Avise-me” é assinatura persistente com ocorrências distintas

**Data:** 2026-09-11

**Status:** aceito
**Escopo:** Storefront, disponibilidade, produção/QC e entrega de comunicação com finalidade específica

## Contexto

O modelo anterior consumia `StockAlertSubscription` no primeiro aceite remoto por meio de
`notified_at`. Isso confundia três fatos: autorização durável do cliente, evento real e tentativa
de entrega. Também permitia que movimentos repetidos fossem interpretados como um novo aviso e
não oferecia pausa da autorização específica.

## Decisão

- A assinatura permanece ativa por SKU, tipo de evento, canal da loja, finalidade e contato até
  pausa, cancelamento ou expiração. A proteção atual de 30 dias permanece enquanto a retenção
  definitiva estiver pendente.
- `stock_back` nasce uma vez por ciclo indisponível→disponível. Movimentos e retries enquanto o
  ciclo segue disponível reutilizam a ocorrência aberta. Nova indisponibilidade fecha o ciclo.
- `production_ready` usa a identidade estável da ordem/fornada. O fechamento cria a ocorrência
  como `pending`, sem entrega. A gestão confirma o QC no painel já existente de Expedição; o
  `WorkOrderEvent.QUALITY_REVIEWED` (ou uma `QUALITY_CORRECTED`) é o fato imutável que autoriza a
  reavaliação. Repetir qualquer desses sinais não cria outra ocorrência.
- A política canônica do canal decide quais grupos revisados podem ser vendidos: no canal remoto,
  somente `excellent`/Ótimo e `standard`/Normal contam. `fair`, `minimal`, perda ou
  indisponibilidade fecham apenas a ocorrência como bloqueada; a assinatura permanece ativa.
- Cada entrega tem unicidade por assinatura, ocorrência, finalidade e canal. A `Directive`
  existente é a outbox; seu recibo permanente impede recriação depois da conclusão.
- Pausa, cancelamento, expiração, opt-out global e disponibilidade são rechecados sob o mutex do
  canal imediatamente antes do adapter. Resultado incerto fica `indeterminate`, alerta o operador
  e não é reenviado sem reconciliação.
- Uma correção de QC antes do adapter suprime recibos ainda enfileirados ou reclamados. Se o
  provedor já aceitou a entrega, o fato não é apagado e um alerta operacional exige conciliação.
- O contato pode ser usado apenas para a finalidade e ocorrência autorizadas. Quando outra fonte
  participa da mesma comunicação, a entrega deve deduplicar o destinatário e preservar a
  atribuição das fontes; isso não autoriza marketing genérico.

## Consequências

`notified_at` permanece temporariamente como horário da última aceitação para compatibilidade,
sem controlar atividade. `StockAlertOccurrence` registra o evento e seu motivo; `StockAlertDelivery`
registra fila, claim, aceite, falha recuperável, supressão ou incerteza. O Admin é somente leitura e
o runbook orienta a ação sem oferecer reenvio cego. A tela de Expedição identifica fornadas que
aguardam revisão e oferece a ação gerencial na mesma projeção e permissão usadas pela correção.
