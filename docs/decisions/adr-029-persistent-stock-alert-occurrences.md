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
  é irreversível; retomada vale apenas para ocorrências futuras. No aparelho que cadastrou um
  aviso anônimo, a sessão permite recuperar o link após reload somente quando referência, SKU e
  contato conferem com a mesma assinatura. O `POST` anônimo sempre devolve confirmação genérica:
  somente a transação que criou a assinatura vincula o marcador à sessão. Repetir SKU e telefone
  em outra sessão não concede a capacidade, não retoma uma assinatura pausada e não revela se ela
  já existia. Cliente autenticado usa o telefone da identidade canônica e recebe acesso explícito
  à seção de avisos em Preferências. Na confirmação genérica, a próxima ação é entrar com o mesmo
  WhatsApp para conferir ou reativar na conta; a copy não afirma que um aviso pausado está ativo.
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
