# ADR-029 — “Avise-me” é assinatura persistente com ocorrências distintas

**Data:** 2026-09-11
**Emenda de comprovação de identidade web:** 2026-09-14

**Status:** aceito
**Escopo:** Storefront, disponibilidade, produção/QC e entrega de comunicação com finalidade específica

## Contexto

O modelo anterior consumia `StockAlertSubscription` no primeiro aceite remoto por meio de
`notified_at`. Isso confundia três fatos: autorização durável do cliente, evento real e tentativa
de entrega. Também permitia que movimentos repetidos fossem interpretados como um novo aviso e
não oferecia pausa da autorização específica.

## Decisão

- A assinatura persiste entre ocorrências por SKU, tipo de evento, canal da loja, finalidade e
  contato até o cliente pausar ou cancelar. Não há expiração automática. A migração remove o prazo
  somente de linhas verificadas e não revogadas; não reativa cancelamentos nem promove legado sem
  prova. O campo `expires_at` permanece durante o rollout para compatibilidade de schema.
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
- Pausa, cancelamento, opt-out global e disponibilidade são rechecados sob o mutex do
  canal imediatamente antes do adapter. Resultado incerto fica `indeterminate`, alerta o operador
  e não é reenviado sem reconciliação.
- Cada aviso oferece controle no aparelho atual e por uma capacidade opaca, restrita à finalidade
  e revogável, enviada no fragmento de um link “Gerenciar este aviso”. A página remove o fragmento
  imediatamente, `GET` apenas consulta e `PATCH`/`DELETE` pausam, retomam ou cancelam. Cancelamento
  é irreversível; retomada vale apenas para ocorrências futuras. No web, novo opt-in exige a
  identidade autenticada e usa o telefone canônico da conta. Antes da entrada, a pessoa aceita
  explicitamente a declaração 18+; só então o servidor registra na sessão uma prova opaca, curta,
  versionada e sem PII. A tela preserva página, filtros, âncora, SKU e a referência dessa intenção;
  ao voltar, revalida sessão, SKU e aniversário conhecido e conclui automaticamente sem pedir o
  mesmo consentimento duas vezes. Uma query isolada ou intenção de outra sessão não autoriza a
  criação. Depois de concluída, a intenção fica vinculada à assinatura original: replay de resposta
  perdida apenas lê esse resultado e nunca desfaz pausa nem recria cancelamento. Um `POST` anônimo
  no endpoint de assinatura continua respondendo `401`, ignora telefone,
  CPF e e-mail digitados e não cria opt-in. A migração
  marca assinaturas web ativas
  sem `customer_ref` como `legacy_unverified`, preservando histórico e recibos, impedindo novas
  entregas e invalidando sua capacidade de gestão; após entrar, a pessoa pode criar uma assinatura
  nova. Outros canais podem usar contato sem `customer_ref` quando o evento de entrada já fornece
  prova de identidade.
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
Retenção de recibos e dados históricos continua sendo uma decisão separada: sua janela permanece
pendente e os recibos protegidos atuais não são apagados por idade.

O flow atual do ManyChat não recebe variáveis de forma transitória: ele lê campos personalizados.
Por isso `management_note`, que contém a capacidade, fica armazenado no perfil do assinante no
provedor e pode permanecer ali até ser sobrescrito ou removido conforme a política do ManyChat.
A capacidade autoriza somente uma assinatura, não revela telefone nem abre a conta, e deixa de
resolver após cancelamento. Ainda assim, deve ser tratada como segredo. Não há no adapter atual um
caminho transitório equivalente para flows; usar `sendContent` evitaria o campo, mas não substitui
com segurança um flow/template aprovado fora da janela do WhatsApp. A retenção e a limpeza desse
campo no provedor fazem parte da decisão de retenção ainda pendente.
