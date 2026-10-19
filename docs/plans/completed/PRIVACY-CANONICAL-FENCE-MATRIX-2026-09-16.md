# Matriz da cerca canônica de privacidade — 2026-09-16

## Decisão invariável

Toda fase de banco que crie, altere, vincule ou autentique dados de um titular
deve adquirir primeiro `Customer SELECT FOR UPDATE` e revalidar `is_active`.
Só depois pode bloquear ou escrever registros-filhos. Efeitos externos nunca
ficam dentro dessa transação: uma intenção durável e não pessoal é confirmada
antes do I/O, e a finalização readquire `Customer` antes do registro-filho.

Ordem global:

```text
PrivacyRequestReceipt (quando houver)
  -> Customer
    -> intenção durável
      -> I/O externo fora da transação
        -> Customer
          -> finalização / registros-filhos / sessão
```

Uma leitura feita antes da trava serve apenas como pista para localizar o
`Customer`; identidade, contato e autorização são revalidados depois da trava.
Se a exclusão vencer, o writer falha fechado e não chama provider externo. Se o
writer vencer, a exclusão espera e precisa alcançar o efeito recém-criado.

## Cobertura implementada neste pacote

| Superfície mutadora | Dono da trava | Ordem esperada | Prova |
| --- | --- | --- | --- |
| Perfil e contatos Guestman | serviço Guestman | Customer -> ContactPoint | unidade + PostgreSQL |
| Endereços | serviço Guestman | Customer -> CustomerAddress | unidade + PostgreSQL |
| Checkout | Orderman commit | Customer -> Session/Order | PostgreSQL; ref+telefone divergentes falham |
| Evento tardio de pedido | `Order.emit_event` | Order lockada -> `OrderEvent`; pedido anonimizado recusa somente `note/reason` | unidade + PostgreSQL delete-first; payload operacional continua permitido |
| Aviso de estoque | serviço storefront | Customer -> Subscription | PostgreSQL |
| Favoritos | serviço storefront | Customer -> Favorite | unidade + PostgreSQL representativo |
| Troca de telefone / OTP | shop auth + Doorman | Customer -> VerificationCode -> ContactPoint | unidade + PostgreSQL; alvo revalidado após espera |
| Passkey | shop auth | Customer -> Passkey -> sessão | unidade + PostgreSQL representativo |
| Dispositivo confiável / step-up | shop auth | Customer -> VerificationCode/TrustedDevice -> sessão | unidade + PostgreSQL representativo |
| AccessLink | Doorman resolver | Customer -> AccessLink -> CustomerUser/sessão | unidade + PostgreSQL nas duas ordens |
| Exportação | privacy/export | Receipt -> Customer -> snapshot -> Receipt COMPLETED | PostgreSQL exportação x exclusão |
| Entrega direta de Marketing | worker de entrega | Customer -> DeliveryTarget/Attempt -> provider | PostgreSQL; nenhum provider se exclusão vence |
| Concierge identify/binding | concierge service | Customer -> Conversation -> Binding | unidade + PostgreSQL nas duas ordens |
| ManyChat sync de cadastro existente | Guestman ManychatService | Customer -> Identifier/ContactPoint/Consent | unidade + PostgreSQL nas duas ordens |
| ManyChat resolve/bootstrap de cadastro existente | Guestman ManychatSubscriberResolver | Customer -> I/O limitado a 10s -> Identifier; resultado externo incerto deixa reconciliação pendente | unidade + PostgreSQL nas duas ordens, zero chamada externa se exclusão vence e falha fechada no resultado incerto |
| OTP de login e verificação de contato | Doorman AuthService | Customer -> VerificationCode PENDING -> I/O -> Customer -> VerificationCode SENT/FAILED | unidade + PostgreSQL nas duas ordens; entrega iniciada e interrompida exige reconciliação com evidência |

## Footprint exportação x exclusão do rastro de pedido

O export permite somente `meta.customer_note`, `meta.gift_wrap` e
`meta.customization.{note,text,message}`. A exclusão trata os quatro caminhos de
texto como pessoais em todas as cópias duráveis, mas mantém `gift_wrap`, dados
fiscais, descontos e os identificadores/valores comerciais da customização.

| Representação durável | Footprint pessoal removido | Metadado comercial preservado | Prova |
| --- | --- | --- | --- |
| `OrderItem.meta` | `customer_note`; `customization.note/text/message` | `gift_wrap`, `_disc`, `fiscal`, `customization.choice_ref/price_delta_q` | `test_exclusao_limpa_texto_pessoal_das_tres_copias_do_meta_do_item` |
| `Session.items[*].meta` (`SessionItem.meta`) | `customer_note`; `customization.note/text/message` | mesmos campos comerciais | mesmo teste, com sentinela exclusiva da sessão |
| `Order.snapshot.items[*].meta` | `customer_note`; `customization.note/text/message`; agora também projetados por allowlist no export | mesmos campos comerciais | mesmo teste, com sentinela exportada e depois ausente do snapshot selado |
| `OrderEvent.payload` | `note`; `reason` | `protocol` e todo o restante da evidência operacional | `test_exportacao_e_exclusao_alinham_eventos_e_alerta_de_cancelamento` |
| `SessionEvent.payload` | refs e texto livre (`from_ref`, `to_ref`, `note`, `reason`, `text`, `message`); campos explícitos de cliente, destinatário, entrega, presente e documento; PII fechada em `receipt`, `notification_context` e `context` | SKU, quantidades, totais, contagens, estado de carrinho e marcadores anti-fraude | sentinelas de exportação/exclusão e cerca pós-exclusão; scrub executado sob a mesma trava da `Session` |
| `OperatorAlert(customer_cancellation_requested)` | a mensagem livre é reconstruída sem o motivo a partir de `order_ref` + protocolo estruturado do `OrderEvent` | tipo, severidade, audiência, `order_ref`, protocolo, reconhecimento e resolução | mesmo teste; alertas de outros tipos não entram no artefato |

O export não despeja JSONs ou alertas brutos: `OrderEvent` e `SessionEvent` usam
projeções explícitas de payload, itens do snapshot passam pela mesma allowlist de
`OrderItem.meta`, e somente alertas `customer_cancellation_requested` vinculados
a pedidos do titular entram em `order_cancellation_alerts`. Protocolo e motivo
desse recorte vêm do `OrderEvent` estruturado via subqueries, nunca de parsing da
mensagem livre do alerta.

## Cobertura concluída e limitação externa ManyChat

As superfícies locais inventariadas neste gate estão cobertas por cerca
Customer-first e provas focais. A limitação remanescente não é uma mutação local
aberta: é a necessidade de confirmar o desvínculo no provedor ManyChat antes de
prometer a conclusão da exclusão.

> **Atualizado em 23/09/2026 — o bloqueio virou trabalho.** O parágrafo abaixo
> descrevia a decisão anterior: vínculo ManyChat comprovado RECUSAVA a exclusão,
> e o cliente recebia 409 com "peça à equipe para desvincular". Como o ManyChat
> é o caminho do login por WhatsApp, isso alcançava a maioria dos clientes — e
> contradizia a promessa escrita na página de privacidade ("você pode excluir a
> conta na hora, sem pedir para ninguém"). A LGPD trata exclusão como direito do
> titular exercível por ele; mandar pedir à equipe é o oposto. Ver
> `shopman/shop/services/manychat_erasure.py`.

O lock resolve a corrida concorrente do ManyChat, mas não resolve sozinho um
webhook novo recebido depois de a exclusão já ter removido os identificadores.
Esse caminho — a RESSURREIÇÃO — era a razão de fato do bloqueio, e agora ele é
fechado por uma lápide: `ProviderErasureTombstone` guarda o HMAC do
`subscriber_id` (nunca o valor em claro) e `ManychatService.sync_subscriber`
recusa o assinante sepultado. O identificador local continua sendo apagado, mas
não é mais ele que carrega a garantia.

Medição de 23/09/2026 que muda o desenho: **a API pública do ManyChat não tem
verbo de exclusão de assinante.** O inventário completo é `getInfo`,
`findByName`, `findByCustomField`, `findBySystemField`, `getInfoByUserRef`,
`createSubscriber`, `updateSubscriber`, `addTag(ByName)`, `removeTag(ByName)`,
`setCustomField(s)`, `setCustomFieldByName`, `verifyBySignedRequest` e os três
de envio. Nenhum apaga. Portanto "apagar lá primeiro" tem um teto, e ele é:

1. **o que dá para apagar** — os campos personalizados que esta casa empurrou
   para o perfil do assinante são zerados um a um por `setCustomFieldByName`, e
   cada gravação devolve confirmação própria. A primeira que não confirmar
   interrompe a exclusão inteira;
2. **o que não dá** — a linha de contato do ManyChat (telefone e nome vindos do
   WhatsApp) só sai pela mão de um humano na interface deles. Isso NÃO fica como
   pendência silenciosa: a conclusão abre `manychat_contact_erasure_due`,
   alerta crítico com o assinante, a instrução e o prazo de 15 dias.

A ordem segue a deste documento — intenção durável (`manychat_erasure_pending`,
sem PII) → I/O fora da transação → readquirir `Customer` → finalizar — e a
pegada do provedor é **relida com o `Customer` travado** na finalização: vínculo
que apareceu durante a limpeza não foi alcançado por ela, então a exclusão falha
fechada (`manychat_link_appeared_during_erasure`) em vez de se declarar
concluída. Limpeza não confirmada não vira "pronto": o recibo fica incompleto, a
operação é chamada e o titular vê "tente de novo", nunca "peça para alguém".

O resolvedor outbound também serializa pelo `Customer` antes de qualquer I/O.
A chamada externa usa o timeout já limitado a dez segundos. Se o provedor não
devolver um resultado conclusivo depois de iniciada a resolução, fica no
cadastro apenas o estado operacional, sem PII,
`manychat_resolution_pending=true`; esse estado impede uma exclusão que, de
outro modo, poderia prometer sucesso enquanto uma criação externa tivesse sido
aceita. A exclusão não recusa mais por causa dele: ela RESOLVE, chamando
`reconcile_pending` dentro da própria fase de I/O. Encontrou o assinante, ele
entra na limpeza e ganha lápide; ausência conclusiva libera; incerteza falha
fechada.
Timeout, erro HTTP ou qualquer resposta sem identificador continuam incertos:
o provedor documenta que contato já existente também produz erro, portanto erro
não prova ausência. O caminho operacional
`reconcile_manychat_privacy --customer-ref ...` faz somente consultas de leitura:
materializa o vínculo quando encontrado, libera a pendência apenas diante de
resposta bem-sucedida e vazia do lookup oficial, e preserva o bloqueio em todo
resultado ambíguo. Não há limpeza automática por tempo nem edição manual como
atalho.

## Critério de encerramento técnico

As provas concorrentes usam duas conexões e sincronização observável por lock do
banco, sem `sleep` frágil.

⚠️ **As provas de ManyChat × exclusão nunca rodaram até 23/09/2026.** Elas
moravam em `packages/guestman/shopman/guestman/tests/`, cujo rootdir carrega
`guestman_test_settings` — que não instala `shopman.shop`. O `skip` de módulo
disparava sempre, inclusive no CI, e skip de MÓDULO não passa pelo coletor de
`run_runtime_tests.py`, então o gate nem reprovava. O arquivo é monolítico por
natureza (importa `shopman.storefront.services.account_privacy`) e foi movido
para `shopman/storefront/tests/test_manychat_privacy_postgres.py`, onde executa.

A limitação externa ManyChat acima deixou de bloquear o fluxo: a exclusão
conclui sozinha, e o que a API do provedor não faz vira tarefa datada do
operador. O resíduo — a linha de contato no ManyChat — continua declarado, não
ocultado como sucesso local. Produção, segredos, jobs e descarte de legado
permanecem fora deste gate.
