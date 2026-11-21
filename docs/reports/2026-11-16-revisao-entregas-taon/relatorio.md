# Revisão adversarial das Entregas (Gestor + TaOn)

Base: o código no ar (HEAD 54e75d0df, #2476), mais o PR #2477, que conferi agora com `gh pr view 2477`: **OPEN**, com auto-merge ligado. Conferi de novo, nesta rodada, as quatro provas centrais:
- `grep will_reopen` em shopman e packages volta vazio.
- O padrão do motivo de cancelamento é 1 (`config/settings.py:1128`, `courier_machine.py:477`).
- `links[0]` aparece em `courier.py:1129-1133`.
- O corpo cru é logado em `webhooks/machine.py:101`.

As issues #2463, #2465, #2466, #2468 e #2428 estão OPEN. Foram 90 achados sobreviventes, que fundi em 41 itens.

## 1. Resumo (para o dono)

1. **Estado.** A seção Entregas funciona no caminho feliz. Nas bordas reais da TaOn ela erra: quando o entregador desiste, no cancelamento e nas várias paradas. Juntar corridas ainda custa N+1 toques e é feito às cegas, sem preço e sem ordem verdadeira.
2. **Maior risco, dinheiro.** Quando um entregador desiste, a TaOn redistribui a corrida sozinha. O Gestor trata isso como "cancelada" e manda chamar de novo, e o resultado são duas corridas pagas. Além disso, "Cancelar" antes do aceite sempre falha (motivo 1, a TaOn exige 10).
3. **Maior risco, cliente.** Na corrida juntada, todo cliente recebe o link de rastreio da primeira parada, que é de outra pessoa. Facilitar o juntar sem consertar isso multiplica o vazamento.
4. **Maior ganho.** Chamar uma corrida e chamar uma corrida junta viram o mesmo gesto, com dois toques. A casa já monta o grupo, a ordem real, a cotação "juntas contra separadas" e o troco e a maquininha antes do toque.
5. **API ignorada que mais vale.** Na v2 da TaOn: agrupar uma corrida já chamada, aumentar a oferta quando ninguém aceita e tirar uma parada. Hoje cada um desses casos vira telefonema.

## 2. Achados que sobreviveram (fundidos, P0 → P3)

### P0

**P0-1. Desistência do entregador vira "corrida cancelada" e manda chamar de novo (corrida em dobro)** (TAON-02, com parte do ENT-SEC-02)
- **Prova:**
  - A doc v1 de Webhooks, seção "Campo will_reopen", diz: com true, "não abra outra solicitação".
  - `grep will_reopen` volta vazio. `machine.py:172-173` aplica C. `courier.py:1038-1041` arquiva e tira o id_mch. `_alert_ride_failed` (`courier.py:1165/1171`) diz "chame o entregador de novo".
  - No polling, `courier.py:1225-1226` conclui C pela simples presença de `cancellation[]`.
  - A idempotência usa (corrida, letra), não `event_id` (`machine.py:149-152`). O A do novo entregador vira replay.
- **Impacto:** dois entregadores no balcão para um pedido, duas corridas pagas, e o troco devolvido à gaveta no meio da rota.
- **Solução:**
  - C com `will_reopen=true` chama `courier.record_reopen`: mantém o id_mch, status D, limpa o entregador e grava `block["reopens"]`. Não arquiva, não alerta e não devolve a custódia.
  - Chave de idempotência por `event_id`. O polling só conclui C quando a letra lida é C.
  - Um webhook vivo para um id arquivado gera alerta e restaura a corrida.
  - Tela: "Fulano desistiu às 14:32. A TaOn já procura outro.", sem "Chamar de novo".
  - Registrar `courier.reopens` em data-schemas.md.

**P0-2. "Cancelar corrida" antes do aceite sempre falha, e a falha é muda** (ENT-02, ENT-SEC-05 e TAON-20; fecha a #2463)
- **Prova:**
  - `settings.py:1128` tem o padrão `MACHINE_CANCEL_REASON_ID` igual a 1, usado em `courier_machine.py:477`.
  - O OpenAPI v1 POST /cancelar diz: para usuário de empresa, em D/T/P/G só 10; depois, a lista 1, 2, 6, 12, 18 e 32 a 41; fora disso, erro 102.
  - `courier_cancel.py:52-56` grava `not_applied` sem alerta e sem SSE.
  - `deliveries.py` não lê `latest_cancellation` e continua oferecendo `cancel_action`. O T fica fora de `CANCELLABLE_STATUSES`.
- **Impacto:** no caso mais comum ("ninguém aceitou, cancela"), o toast diz "pedido", a corrida segue procurando e o entregador pode vir buscar uma sacola de pedido cancelado. `on_order_cancelled` usa o mesmo caminho.
- **Solução:**
  - `cancel_reason_for(status, intent)`: D/T/P/G vai 10. A/S vai o motivo escolhido; por padrão 12, ou 33 no cancelamento pela casa.
  - Reler a letra antes do POST e reenviar uma vez se vier 102.
  - Apagar `MACHINE_CANCEL_REASON_ID` (settings, .do e runbook).
  - Pôr T em `CANCELLABLE_STATUSES`.
  - A recusa gera alerta crítico, SSE `cancel_failed` e a mensagem traduzida "A TaOn não cancelou a corrida 3. Cancele pela central da TaOn."
  - A projeção de Entregas ganha `cancel_state` (pending/unknown/failed), com um helper único também usado pelo order_queue. Com cancelamento pendente, aparece "Pedido de cancelamento enviado. Esperando a TaOn confirmar." e o botão some.
  - UX: antes do aceite, um toque e uma confirmação. Depois do aceite, a confirmação traz três botões que já são o motivo: "O entregador não está vindo" (12), "Está demorando demais" (37) e "Não consegui falar com o entregador" (40).

### P1

**P1-1. Link de rastreio e código da parada 1 vão para todos os clientes da corrida** (TAON-01, J06 e ENT-03)
- **Prova:** `courier.py:1129-1133` e `:1309-1316` usam `links[0]` em cada pedido. A notificação põe o `tracking_url` no aviso de saída (`notification.py:919-925`). O adapter recebe uma lista por parada (`courier_machine.py:483-496`). `test_courier_group_ride.py` não testa o tracking.
- **Impacto:** o cliente B vê a entrega de A (risco de LGPD), e o código não confere na porta.
- **Solução:**
  - `link_for_order` casa por `id_externo`/`numero_pedido` da leitura da corrida. Sem isso, casa por `parada_id` gravado ou pela posição, e só quando os tamanhos batem.
  - Se o casamento não fica provado, ou se a resposta vem no formato `{"link"}` único numa corrida de várias paradas, não grava nada (falha fechada). O sufixo e o botão somem sozinhos.
  - Buscar os links uma vez por corrida. O mock passa a devolver uma entrada por parada.
  - Teste com 3 paradas embaralhadas.
  - Passo 6 do runbook: medir o link numa corrida de 2 paradas.

**P1-2. Cancelar corrida de várias paradas prende os companheiros, e o aceite tardio de pedido cancelado fica aberto e pago** (ENT-01 e ENT-SEC-03)
- **Prova:**
  - `courier_cancel.py:82-87` aplica C só ao pedido principal. `courier_sync.py:44-46` sai calado quando o principal perdeu o id_mch. Sonda: "OTHER CR-A D True".
  - `courier_dispatch.py:196-225` (`_adopt`) vincula o id_mch a um pedido já cancelado e só emite um alerta falso ("chame de novo").
- **Impacto:** o pedido fica "Procurando entregador" para sempre, segurando número e cor, com o troco e a maquininha presos. Ou a casa paga uma corrida para um pedido que não existe.
- **Solução:**
  - Ler `ride_companions` antes do C e aplicar C a cada companheiro (`ride_continues=False`).
  - Dedupe por `courier.cancel:{id_mch}`, com o payload apontando para o pedido principal.
  - O sync reconcilia os presos a partir de `attempts[-1]`.
  - No `_adopt`: sem pedido vivo, `cancel_ride` uma vez só. Com mistura, `on_order_cancelled` para cada cancelado. `ride_companions` passa a contar só os vivos.
  - Copy: "O pedido A47 foi cancelado enquanto a TaOn abria a corrida. Pedimos à TaOn o cancelamento da corrida."

**P1-3. Webhook aplica letra fora de ordem: corrida coletada volta a "aceita" e o cancelamento reabre** (ENT-SEC-01, com o ENT-SEC-02 fundido)
- **Prova:** `courier.py:1014-1016` só recusa letra terminal. `_STATUS_RANK` (`:1203`) vale só no polling. Sonda: "after late A … A dispatched". O A de um novo entregador é descartado como replay (`machine.py:149-152`).
- **Impacto:** com a sacola na moto, o botão "Cancelar corrida" volta a aparecer.
- **Solução:**
  - A régua do rank entra em `apply_status`. A única volta legítima é A/S para D/G/P antes da coleta, e ela limpa o entregador.
  - O webhook passa `at=event.datetime` e ganha `last_provider_at`.
  - Predicado único `courier.ride_cancellable(block)` (exige sem `dispatched_at`) nas 4 portas.
  - Recusa vira `courier_status_ignored` com 200 `stale`.
  - O replay também agenda `schedule_sync(0)`.

**P1-4. Agrupamento da própria TaOn (U) aparece como "Ninguém aceitou ainda"** (TAON-03)
- **Prova:** `deliveries.py:193-195` trata U como searching e depois late. O adapter mapeia U como GROUPED (`courier_machine.py:269`). Na v2, consultar devolve 97 com `solicitacao_agrupadora_id`.
- **Impacto:** o operador cancela ou chama de novo uma corrida que já tem entregador.
- **Solução:**
  - (A, já) Estado `grouped` com o rótulo "Junto com outra corrida": nunca late, sem lembrete, sem "Chamar de novo".
  - (B, depois da homologação) `grouped_into` sem sobrescrever o id_mch, e o sync passa a ler a corrida agrupadora.

**P1-5. Dado pessoal de entregador e cliente no log** (TAON-04 e ENT-SEC-12)
- **Prova:** `machine.py:101` loga `raw=body[:2000]` em todo POST, antes da assinatura, inclusive os lotes de posição. A doc da TaOn manda não logar `pix_key` nem `photo_url`. `telemetry_redaction.py:86-91` não pega a chave entre aspas.
- **Impacto:** risco de LGPD, com CPF, chave Pix, foto, telefone e coordenadas em log de produção.
- **Solução:**
  - Log de lista fechada depois do parse: ids, status, event_id, stop_id, will_reopen, tamanho e sha256[:12]. Para formato desconhecido, só as chaves.
  - Diagnóstico de assinatura com hash e os 8 primeiros caracteres da assinatura.
  - `redact_text` passa a aceitar a forma JSON.
  - Teste com o corpo A documentado nos dois formatters.
  - O token em query fica como está, documentado no runbook.

**P1-6. A chamada de corrida em grupo (`courier-ride`) fura o protocolo de intenção** (ENT-SEC-04 e J15)
- **Prova:** `operations.py:4591-4636` não confere ator, Idempotency-Key nem `base_revision`. O front manda só `{refs, change_out, machine}` (`deliveries.vue:163-167`, `CourierRideMenu.vue:89`, `useOrderDetail.ts:326`). A resposta não devolve o `ride_number`.
- **Impacto:** uma corrida sai com endereço ou troco que o operador não viu, o retry depois de rede caída dá "já pedida", e com o PIN de outra pessoa a corrida sai no nome errado.
- **Solução:**
  - Extrair `_intention_response`.
  - Corpo `{refs, base_revisions, change_out, machine, expected_actor_id}`, com a revisão conferida sob `select_for_update` ANTES de gravar o bloco.
  - 409 `revision_changed` com `errors{ref}`. Replay devolve 200 `replayed`. `already_called` conta como sucesso.
  - Uma Idempotency-Key por corrida, guardada até o sucesso.
  - `group_action` na projeção.

**P1-7. "Entregue" só no fim da corrida inteira: ER e stop_id ignorados** (J07, ENT-04, TAON-08 e ENT-API-07; dentro da #2428)
- **Prova:** `machine.py:130-141` descarta o ER. `snapshot_from_details` não lê `stops` (`courier_machine.py:328-376`). `record_arrival` desiste em corrida de várias paradas (`courier.py:1430-1432`). O plano registra a limitação (`DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:179-182`).
- **Impacto:** o primeiro cliente recebe "entregue" 30 a 40 min depois, e a tela mostra "0 de 3 entregues" a rota inteira. Juntar piora a experiência do cliente, o que desestimula o juntar.
- **Solução:**
  - Gravar `courier.stop_id` casado por `id_externo`.
  - ER com stop_id chama `record_stop_delivered` só daquele pedido.
  - Idempotência por (corrida, "ER", stop_id). O F fecha o resto sem notificar de novo, e o AP vai para a próxima parada aberta.
  - `stops[].status` só como convergência. Fica atrás de `STOP_DONE_CODES`, vazio até a corrida de prova.
  - Tela: "Indo para C12 (2 de 3)" e "Entregue às 14:41".

**P1-8. Entrega que falha na porta vira "entregue"** (ENT-05)
- **Prova:** `courier.py:1046-1047` chama `confirm_received` em todo F, e não há caminho de "voltou sem entregar".
- **Impacto:** o cliente recebe "entregue" com a sacola de volta na loja, e estoque, NFC-e, cobrança e B.I. ficam errados.
- **Solução:**
  - Em corrida com retorno (`needs_return`), o F não confirma. O "Entregador voltou" pergunta por pedido, com "Entregue" já marcado e a alternativa "Voltou com a sacola".
  - A alternativa abre duas saídas: "Entregar de novo" ou "Devolver e estornar" (RETURNED canônico).
  - Na voz da concierge: "Não conseguimos entregar seu pedido. Podemos combinar uma nova entrega?"
  - **Tensão com o P1-7:** o ER por parada é fato da TaOn e confirma na hora. Este item segura só o F sem ER. A regra fina pede a palavra do dono (seção 6).

**P1-9. Juntar não é tão fácil quanto chamar uma: não há plano, só chip por nome de bairro** (J01, J02, TAON-07 etapa 2, UXE-01, ENT-13, J10 e J18)
- **Prova:**
  - `deliveries.vue:110-118` conta o texto de `place`. `fill` (`:86-93`) substitui a seleção e inclui pedido em preparo.
  - A decisão escrita é contra pré-marcar (`DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:193-194`, `CourierRideMenu.vue:34-37`).
  - `_ride_offer` (`order_queue.py:2527-2543`) não tem raio nem prazo e oferece "a 11,0 km".
- **Impacto:** no pico ninguém junta, vizinhos de bairros com nomes diferentes nunca são sugeridos, e as pontas opostas do mesmo bairro são.
- **Solução:** o desenho do juiz (seção 4), com `courier.ride_plan` único alimentando sheet, cartão e `ride_offer`.

**P1-10. A página Entregas não cota nada** (UXE-02, J04 e TAON-07 etapa 1)
- **Prova:** `useRideQuote` só aparece em `CourierRideMenu.vue:44` e `OrderCourierPanel.vue:291`. A cotação recusa 1 ref (`operations.py:4658`).
- **Solução:**
  - O quote aceita de 1 a 4 refs e devolve `separate_value_q` e `saving_q` só quando todas as sozinhas cotaram.
  - Uma linha por corrida em Editando: "Juntas: R$ 18,40 · 24 min · 5,7 km. Separadas sairiam R$ 26,90."
  - Quando separadas saem mais barato: "Separadas sai mais barato: R$ 14,20."
  - Barra: "5 pedidos em 2 corridas · R$ 31,30". A falha nunca trava o Chamar.

**P1-11. Gestos destrutivos de um toque na página Entregas** (UXE-04, UXE-05, ENT-10 e ENT-11)
- **Prova:** a projeção pede `confirmation.required` (`deliveries.py:142`). `deliveries.vue:202-214` executa direto. O `CourierBackDialog` não é usado ali (só em `index.vue:2305` e `[ref].vue:1626`).
- **Impacto:** um toque no espelho errado fecha dinheiro, troco e maquininha sem conferência, e um toque perto do rodapé cancela a corrida de 4 pedidos.
- **Solução:**
  - Regra única: toda Action com `confirmation.required` passa por confirmação.
  - "Entregador voltou" abre o mesmo `CourierBackDialog`, generalizado para `{orders, lines}`, com "Voltou diferente" e "Conferido".
  - Cancelar arma um segundo toque, como no `OrderCourierPanel`, com a frase do servidor: "Cancelar a corrida 2? A05 e C12 voltam para Aguardando."
  - Teste: um toque nunca chama `execute`.

**P1-12. Chamar várias corridas manda a mesma maquininha para todas** (UXE-06 e ENT-12)
- **Prova:** `presentation/deliveries.ts:67`, com um `machineRef` só (`deliveries.vue:125`, `:373-377`).
- **Solução:**
  - `assignMachines` pré-atribui maquininhas distintas, com a linha "Maquininha:" dentro de cada corrida.
  - Quando falta maquininha, "Faltam maquininhas: 2 corridas levam cartão e só 1 está livre." e o atalho "Juntar numa corrida só".

**P1-13. A página Entregas sabe menos que o painel do pedido e oferece gesto que falha** (ENT-09, UXE-09, ENT-SEC-06, UXE-19 e J11)
- **Prova:** `DeliveryRideProjection` (`deliveries.py:80-108`) não tem `sync_since`, `charge_outdated`, `cancel_state` nem "dispatch-again". `deliveries.py:177-178` oferece "Chamar sozinho" a pedido com despacho pendente, que o servidor recusa (`courier.py:521-523`). `group_refusal` é ignorado no toggle (`deliveries.vue:74-85`). O quinto toque é ignorado sem aviso (`:82`). Corrida N/C volta a Aguardando sem dizer por quê.
- **Solução:**
  - `courier.ride_health(order)` vira fonte única para o Painel e para Entregas, com teste de contrato de paridade.
  - `dispatch_again_action`: "A TaOn não respondeu a última chamada. Confira na central e toque em Chamar de novo."
  - `last_failure` com `retry_group`: "Ninguém aceitou a corrida 2 (14:20)." [Chamar de novo]
  - Dado parado: "A TaOn não dá notícias desta corrida desde 14:05." Cobrança mudou: "Avise o entregador: cobrar R$ 58,00 em dinheiro." [Ligar]
  - Linha recusada com o motivo e sem toggle. O quinto toque abre a corrida 2 com aviso.
  - "late" mostra os minutos: "Ninguém aceitou em 12 min".

**P1-14. Encaixar pedido numa corrida já chamada** (TAON-06; fase 2)
- **Prova:** a v2 tem POST `/entregas/{id}/agrupar`, que recusa T/E/F/C/U e exige que a agrupadora tenha a maior prioridade (A, S, G, P, D, N). Hoje só se junta antes de chamar.
- **Solução:**
  - Directive `courier.attach`: abrir a solicitação e chamar agrupar.
  - Chip "Encaixar na corrida 2 · +0,8 km". Se falhar, o pedido volta a Aguardando ou sai sozinho, com o motivo.
  - Atrás da homologação da v2 com a mesma api-key. Até lá, o chip não aparece.

### P2

- **Ordem mostrada diferente da ordem enviada à TaOn** (UXE-03 e J03).
  - Prova: `deliveries.vue:335-343` numera pela ordem dos toques e diz que "A TaOn leva na ordem do percurso". O mapa desenha a mesma ordem (`CourierDeliveriesMap.vue:170`), mas `_route` reordena (`courier.py:271-290`).
  - Solução: `routeOrder` puro no front, com fixture JSON compartilhada entre pytest e vitest. Copy: "O entregador sai da loja e segue esta ordem."
- **Despacho sem resultado vira conferência manual** (TAON-16 e ENT-08).
  - Prova: `courier_dispatch.py:179-183`.
  - Solução: Directive `courier.reconcile`, só leitura, aos 45 s e aos 3 min, via GET /solicitacao, exigindo que TODAS as paradas batam. Achou uma: adota. Achou duas: avisa. Ausente: "Conferimos na TaOn: a corrida não foi aberta." e "Chamar de novo" vira o botão primário. A chave de busca depende da homologação.
- **Falhas da corrida juntada** (J08, J14 e UXE-18).
  - Prova: `_record_terminal_failure` gera um alerta crítico por pedido (`courier_dispatch.py:228-252`). O laço em `deliveries.vue:150-188` para no primeiro erro e mostra mensagem genérica, sem X.
  - Solução: um aviso por corrida e um cartão "A corrida 2 não abriu (A47, C03)" com [Chamar de novo] e [Chamar separadas], com a custódia já preenchida. Balanço por corrida: o 4xx segue para a próxima, rede ou 5xx param. NuxtAlert com X preso ao cartão.
- **Custo exibido mente** (J13 e UXE-22).
  - Prova: `deliveries.py:239-240` mostra a cotação solo antiga do pedido principal.
  - Solução: `estimate.stops`, com a cotação da rota gravada no principal. Rótulos "Cotação da corrida" e "Valor pago à TaOn". Custo contra frete: "Sobra" ou "Falta", em tom neutro.
- **Três telas para juntar** (UXE-13 e J09; #2468).
  - Prova: popover em `index.vue:1564/1959`, "Vai junto nesta corrida?" em `OrderCourierPanel.vue:621` e a página Entregas. `MAX_RIDE_STOPS` está duplicado em `board.ts:1441`.
  - Solução: o `CourierCallSheet` único (seção 4). Troco editável na página ANTES de tirar o popover.
- **Aguardando não mostra tempo nem prontidão** (UXE-10, UXE-11 e J05).
  - Solução: `ready_at`, `ready_eta` e `promised_at` vindos dos helpers existentes. Ordem por hora combinada. "Pronto há 14 min" e "Fica pronto 12:35". Parada em preparo marcada também dentro da corrida em Editando, e o primário vira "Chamar mesmo assim (D12 em preparo)".
- **Espera no balcão invisível; AN, AW e T ignorados** (TAON-12).
  - Solução: relógio a partir de `arrived_pickup_at`: "Fulano espera na loja há 7 min. Entregue as 2 sacolas de A47." O AW força o alerta. AN grava `near_pickup_at`. T vira "A TaOn está trocando de entregador", nunca falha.
- **Posição do entregador** (TAON-13, ENT-16 e UXE-14).
  - Prova: `get_position` não tem chamador. A posição vem só do cache do webhook, com TTL de 120 s e sem hora. O fit refaz a cada posição (`CourierDeliveriesMap.vue:56-61`, `:149`).
  - Solução: `store_position` único com `at` e `source`. O poll entra só quando o webhook falta. SSE `backstage-courier-position` com throttle de 10 s. Idade visível: "Posição agora", "de há 40 s", "Última posição há 2 min" com o marcador esmaecido. O fit não acompanha a moto, e aparece "Ver tudo" depois do gesto do operador. Sonda do watchman com `list_webhooks`.
- **Identificar quem leva dinheiro e maquininha** (TAON-14).
  - Prova: `_enrich_accepted` lê `driver.vehicle_*`, mas o webhook manda `vehicle{}`. A foto é descartada.
  - Solução: ler `vehicle.*` (com a cor). Foto baixada pelo backend e guardada só em cache com TTL até o fim da corrida, servida `no-store`. Na entrega: "Moto prata · ABC1D23". Com custódia: "Leva a maquininha e o troco. Confira a placa antes de entregar."
- **"Ninguém aceitou" sem gesto; a v2 permite impulsionar** (TAON-05).
  - Solução: atrás da homologação. "Aumentar a oferta" com +R$ 3, +R$ 5 ou +R$ 8 (configurável na Shop). Confirmação: "A corrida passa de R$ 9,00 para R$ 14,00." Uma vez por corrida, com o boost somado ao custo. Gastar dinheiro pede a palavra do dono.
- **Pedido cancelado em corrida juntada manda "fale com a central"** (TAON-10).
  - Solução: DELETE de parada na v2, via Directive `courier.remove_stop` antes do E. Copy: "A47 saiu da corrida 2. Ficaram 2 entregas, 5,4 km, R$ 23,50." Depende do `stop_id` (P1-1 e P1-7).
- **Cobrança que mudou depois da chamada** (TAON-9).
  - Solução: sonda de PUT na v2 na homologação. Com resposta 2xx, "Atualizar a cobrança na TaOn". Sem ela, "Ligar para o entregador". Corrigir a docstring de `courier.py:219-220`.
- **Comprovante e taxa de cancelamento** (TAON-18 e ENT-21).
  - Solução: "Ver foto da entrega" lida na hora via v2, por proxy, sem guardar a URL. `cancel_fee_q` num campo próprio, somado no B.I. Distância e duração reais já vêm nas leituras atuais.
- **Encomenda futura chamável por API** (ENT-LIM-15).
  - Solução: régua única `not_today_refusal`. Copy: "A encomenda A47 é para amanhã, 17/11. O entregador se chama no dia." O teto de paradas fica no código.
- **A auto-conclusão marca entregue com o entregador na rua** (ENT-14).
  - Solução: com corrida viva e leitura em dia, reagendar para o ETA da TaOn mais a folga. Com o dado parado, concluir e alertar.
- **O lembrete morre depois da primeira chamada** (ENT-15).
  - Solução: o predicado passa a ser "sem corrida viva nem chamada em curso", valendo em PREPARING e em READY. Volta 2 min depois de N/C.
- **Programada para encomenda** (ENT-18; anexar à #2465).
  - Solução: `id_mch_programada`, `consultarProgramada` em lote e `cancelarProgramada`.
- **Acessibilidade do mapa e tema** (UXE-07, UXE-08 e UXE-16).
  - Prova: só a cor distingue as corridas. Medido: amarelo 1,47:1 e laranja 3,13:1, e a 50% tudo fica abaixo de 3:1. No escuro há texto claro sobre `bg-white`.
  - Solução: aba com o número da corrida em toda parada. Contorno `ink` sob a linha, com o recuo dado pela espessura. Tokens de mapa fixos. Trava de contraste no teste. Prévia local antes de enfileirar.

### P3

- **Número da corrida sem trava; a sétima repete** (ENT-CON-11 e UXE-20). Advisory lock em `next_ride_number`, `ride_number` devolvido, identidade por `ride.key`, sufixo "1b" e `next_number` vindo do servidor.
- **429 e Retry-After** (TAON-21). `CourierRateLimited` transitório, sem contar falha de sync e reagendando o despacho. Entra na F1 como pré-requisito do juiz.
- **Desempenho do selo** (ENT-PERF-14 e J12). Contagem em uma consulta, falha devolve `null` e "?", Directives pré-carregadas, teto de queries.
- **Batida de polling morre em 6 h e com poll 0** (ENT-07). Batida lenta a cada 10 min e estado "Aberta há muito tempo" com "Encerrar aqui".
- **Código de entrega** (TAON-11 e J17; executar a #2466). Código nosso, um por pedido. Atenção ao erro 118 se a central não exigir o código.
- **`info_antes_aceite`** (TAON-17). "Ida e volta · 3 paradas · cobrar R$ 58,00 em dinheiro", com corte nosso em 70 caracteres. Testar na v1.
- **Categoria do veículo** (TAON-19 e J17). Medir `GET /categoria`. Com uma categoria só, fechar como not planned.
- **`valor_cobrar`** (J16 e ENT-17). Semântica não documentada: homologar antes. Já gravar `door_charge_sent` na abertura.
- **Copy** (UXE-12). Trocar "Saída fechada" por "Corrida 2 encerrada", sem zeros soltos, e "Separe 3 sacolas para Diego".
- **Loja sem coordenada desenha a loja na casa de um cliente** (UXE-15).
- **Alvos de 36 px e pinos sobrepostos** (UXE-17). Também o aria-label "corrida 0".
- **Celular** (UXE-21). Legenda some, botão dentro de link, `animate-pulse` sem `motion-safe`.
- **NFC-e e DANFE invisíveis na página Entregas** (ENT-19). Só aviso, nunca portão.

## 3. API da TaOn: capacidade, uso hoje e uso proposto

| Capacidade (doc) | Hoje | Uso proposto |
|---|---|---|
| v1 abrirSolicitacao `paradas[]`, `retorno`, `id_externo` | usada | mantida, na ordem de `_route` |
| v1 abrirSolicitacao `data`/`hora`/`antecedencia` (programada) + consultarProgramada/cancelarProgramada | ignorada (#2465) | encomenda de hora marcada (ENT-18) |
| v1 `info_antes_aceite` | ignorada | resumo antes do aceite (TAON-17) |
| v1 `codigo_confirmacao`/`exigir_codigo_confirmacao` por parada | ignorada (o código só é lido) | regra do Admin, #2466 |
| v1 `valor_cobrar` por parada | ignorada | só depois de homologar o efeito |
| v1 `categoria_id` + GET /categoria | ignorada | medir; seletor se houver mais de uma |
| v1 GET /estimarSolicitacao (`latlng_paradas`, `com_retorno`) | subusada: não na página Entregas, não para 1 ref, sem comparação com separadas | cotação viva, "juntas contra separadas", portão da sugestão |
| v1 GET /solicitacao (listagem: `paradas[].numero_pedido`, `link_rastreio_pedido`, `taxas_cancelamento`) | subusada (só a segunda via de leitura) | casar link por parada, reconciliar o despacho unknown, taxa de cancelamento |
| v1 GET /v1/request/{id} `stops[]` | ignorada | `stop_id` por pedido, convergência por parada |
| v1 obterLinkRastreio (lista por parada) | **usada errada** (`links[0]`) | casar por parada, falha fechada |
| v1 POST /cancelar com motivo por fase | **usada errada** (motivo 1) | tabela letra → motivo |
| v1 GET /posicaoCondutor | ignorada (sem chamador) | poll quando o webhook falta |
| Webhook status: `event_id`, `will_reopen`, `datetime`, AN/AP/AW/ER/`stop_id`, `vehicle{}`, `photo_url` | subusado (só AP; chave por letra) | idempotência, reabertura, ordem, espera no balcão, entrega por parada, identificação |
| Webhook posição (lote com `timestamp`) | usado sem hora e sem SSE | `at`, idade visível, SSE leve |
| listarWebhook | só no comando | sonda do watchman |
| 429 + Retry-After + X-RateLimit-* | ignorado | transitório, reagendado |
| v2 POST /entregas/{id}/agrupar | ignorada | encaixar numa corrida viva (fase 2) |
| v2 POST /entregas/{id}/impulsionar | ignorada | "Aumentar a oferta" |
| v2 DELETE /entregas/{id}/paradas/{parada_id} | ignorada | tirar o pedido cancelado da corrida |
| v2 PUT /entregas/{id} | ignorada | atualizar a cobrança (se a central habilitar) |
| v2 GET status (`fase`, `data_hora_*`) | ignorada | terceira via, depois da habilitação |
| v2 detalhes `stops[].comprovante` | ignorada | "Ver foto da entrega" |
| v2 consulta: erro 97 com `solicitacao_agrupadora_id` | ignorada | seguir a agrupadora no U |

Toda linha v2 depende de homologar a mesma api-key na v2 (base `/api/v2/integracao`, ids compatíveis com a v1).

## 4. Juntar corridas é chamar uma: o desenho final do juiz

**Veredito:** a proposta "Chamada única inteligente" vence, com enxertos.
- Ela recebe cartões de sugestão, balanço por corrida, encaixe na fase 2, rota-fantasma, trava de sanidade da cotação, número devolvido pelo servidor e cotação de 1 a 4 refs.
- O laço no mapa perde: disputa o gesto com o pan.
- Sem cotação, nada vem pré-marcado: dinheiro da casa falha fechado.

**Princípio:** um componente (`CourierCallSheet`) e um plano (`courier.ride_plan(waiting, now)`) no servidor. O sheet, o cartão das Entregas e o `ride_offer` leem a MESMA partição, então o Painel e as Entregas nunca discordam.

| Situação | Gesto 1 | Gesto 2 | Hoje |
|---|---|---|---|
| Sozinho, Painel | "Chamar entregador" no cartão Pronto | "Chamar entregador" | 3 gestos (o cartão Pronto não tem o botão) |
| Junto, Painel ou detalhe | o mesmo "Chamar entregador" | "Chamar corrida com A47 e C03" | 2 gestos mais 1 por companheiro, às cegas |
| Junto, Entregas | "Chamar juntas" no cartão | confirmar no mesmo sheet | N+1 |
| Várias sugestões | "Chamar as 2 corridas sugeridas" | confirmar | sem equivalente |

Maquininha com 2 ou mais livres soma 1 gesto, e troco a corrigir pede digitar. Isso vale igual no sozinho e no junto. "Chamar só A47" fica ao lado do primário. Aceitar uma sugestão soma ao que já foi escolhido e nunca apaga. O chip por bairro sai.

**Regra:**
1. **Quem entra:** passa em `_rides_with_others`, tem coordenada e está Pronto. Em preparo nunca vem marcado (não há previsor; #2465).
2. **Proximidade pelo desvio:** é candidato se o desvio for de até 2,5 km E de até 40% da perna maior. Agrupamento guloso pelo `ready_at`, até `MAX_RIDE_STOPS`. O excedente vira a próxima sugestão.
3. **Ordem:** `_route`, espelhada no front como `routeOrder`. Quando a cotação chega, vale `estimate.stops`.
4. **Prazo:** dentro do `delivery_time_slot`, e o último cliente espera no máximo 10 min a mais.
5. **Preço:** pré-marca só quando todas as cotações existem, a economia é de pelo menos R$ 3,00 E 15%, e a trava de sanidade passa (o km junto não pode ser menor que o maior km sozinho).
6. **Freio:** cache de 60 s, nunca no selo nem no push, no máximo 3 sugestões. "Agora não" esconde o par.
7. **Parâmetros:** em `Shop.defaults["delivery"]["ride_suggestion"]`, declarados antes em data-schemas.md. São palpites até o B.I. medir.

**Copy-chave:**
- "Sugestão da casa: juntas R$ 11,00, separadas R$ 17,00. C03 chega uns 6 min depois."
- "Ordem: A47, depois C03. Ida e volta."
- Sem cotação: "A TaOn não cotou agora. Marque C03 se quiser levar junto."
- Corrida cheia: "Cabem 4 por corrida: … D15 fica para a próxima."
- Sucesso: "Corrida 3 chamada com A47 e C03. A TaOn avisa quando alguém aceitar."

**Pré-requisitos que bloqueiam a pré-marcação:** link por parada (P1-1), intenção no `courier-ride` (P1-6), 429, estado U, reabertura (P0-1), separador de `latlng_paradas` homologado, teto de paradas da empresa medido, e o sim do dono para inverter a decisão escrita.

## 5. Prévias para o dono decidir (máximo 6)

1. **Sheet de chamada.**
   - Mostra: o pedido A47 Pronto com um companheiro C03 a 0,6 km, troco R$ 50,00 / R$ 20,00 e uma maquininha azul.
   - Lado a lado: (A) C03 já marcado como "Sugestão da casa" com economia; (B) C03 desmarcado, só com a distância.
   - Mais os estados "sem cotação" e "C03 em preparo".
   - Decide: pré-marcar ou não.
2. **Sugestões no topo de Aguardando, com rota-fantasma.**
   - Mostra: 7 pedidos fictícios, 2 sugestões ("A47 + C03", "B12 + D14 + E02") e o cartão "2 corridas sugeridas: 5 pedidos. Juntas R$ 31,30, separadas R$ 44,10."
   - Lado a lado: (A) cartão com "Chamar juntas"; (B) só realce no mapa, com o operador montando à mão.
3. **Coluna Editando renovada.**
   - Mostra: 2 corridas em edição com numeração na ordem real, linha de cotação (as três variantes: economia, separadas mais barato e falha), "Maquininha:" por corrida (duas livres e uma faltando) e troco editável.
   - Lado a lado: antes (hoje) e depois.
4. **Painel unificado (#2468).**
   - Mostra: coluna Prontos com "Chamar entregador" no cartão, faixa "Aguardando entregador: 5 · Montar corridas (2 sugeridas)" e dois espelhos de corrida viva.
   - Lado a lado: (A) faixa mais espelhos; (B) só espelhos, com a faixa no topo do quadro.
5. **Corrida em apuros.**
   - Mostra: o detalhe da corrida em quatro estados:
     - "Ninguém aceitou em 12 min", com (A) "Aumentar a oferta +R$ 3/5/8" ou (B) só "Chamar de novo";
     - "Fulano desistiu às 14:32. A TaOn já procura outro.";
     - "Fulano espera na loja há 7 min";
     - "A TaOn não dá notícias desde 14:05".
   - Decide: o boost (gasto) e o tom dos avisos.
6. **Volta e entrega ao entregador.**
   - Mostra:
     - o "Entregador voltou" por pedido, com "Entregue" marcado e "Voltou com a sacola" (ENT-05);
     - a entrega das sacolas com foto, "Moto prata · ABC1D23" e "Leva a maquininha e o troco. Confira a placa antes de entregar.";
     - a confirmação armada de "Cancelar corrida" com os três motivos depois do aceite.
   - Lado a lado: (A) "entregue" só depois da volta, na corrida com retorno; (B) "entregue" no F, como hoje.

A acessibilidade do mapa (aba de número, contorno, modo escuro) vai como prévia local dentro do PR da F7, não como decisão.

## 6. Plano de execução (uma frente = um branch = um PR)

1. **F1a. Cancelamento** (P0-2, P1-2, a parte de cancelamento do P1-13). Sem dependência. Closes #2463.
2. **F1b. Webhook e estado** (P0-1, P1-3, P1-4 camada A, P1-5, 429). Sem dependência.
3. **F2a. Link por parada com falha fechada** (P1-1). Sem dependência. A parte que casa por id espera a F6.
4. **F3. Protocolo de intenção do `courier-ride`** (P1-6, número da corrida com lock, `group_action`). Sem dependência.
5. **F4a. Paridade e gestos na página Entregas** (P1-11, P1-13, ENT-SEC-06, copy UXE-12, UXE-15, ENT-LIM-15). Depende da F1a (`cancel_state`).
6. **F4b. Editando honesto** (P1-10, P1-12, ordem `routeOrder`, troco editável, balanço por corrida, aviso por corrida, custo J13). Depende da F3.
7. **F5. `ride_plan` + `CourierCallSheet` + Painel** (P1-9, #2468, J18). Depende de F1b, F2a, F3, F4b. Sem o sim do dono, sai com as sugestões desmarcadas.
8. **F6. Roteiro de homologação** (um PR só no runbook) com todas as sondas:
   - corrida de 2 paradas: links, ER, `stops[]`, `numero_pedido`;
   - `will_reopen` na desistência;
   - v2 com a mesma api-key: agrupar, impulsionar, DELETE, PUT, detalhes;
   - separador de `latlng_paradas` e teto de paradas;
   - `/categoria`, `valor_cobrar`, `info_antes_aceite`, `id_externo` repetido (código 8).
   - Rodar as sondas pede a conta de homologação. Se a credencial for do dono, pede a palavra dele.
9. **F2b. Entrega por parada e falha na porta** (P1-7, P1-8, TAON-10). Depende da F6 e da decisão sobre ENT-05.
10. **F7. Tempo real e mapa** (posição, fit, acessibilidade, tema, toque, celular). Independente. Prévia local antes de enfileirar.
11. **F8. Corrida em apuros** (espera no balcão AN/AW/T, identificação, reconcile unknown, auto-conclusão, lembrete, ENT-07). Depende da F1b.
12. **F9. Extras da v2, um PR por item depois da F6:** encaixe (P1-14), boost, cobrança, comprovante e taxa, categoria, `info_antes_aceite`, `valor_cobrar`. Também: código de entrega (#2466) e programada (#2465, por comentário).
13. **F10. Desempenho do selo e NFC-e** (P3). Independente.

Cada adiamento vira issue `ficou-de-fora` no mesmo PR, e as issues existentes (#2428, #2465, #2466, #2468) são reaproveitadas.

**Pede a palavra do dono:**
1. Pré-marcar a sugestão, o que inverte `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:193-194`.
2. "Aumentar a oferta": se o operador pode gastar, e quanto.
3. Corrida com retorno: o cliente recebe "entregue" no ER ou F (hoje) ou só depois da volta; e o fluxo "Voltou com a sacola" com estorno.
4. Credencial para rodar a homologação, se for a dele.
5. Parâmetros iniciais da sugestão (2,5 km, R$ 3 / 15%, 10 min).
6. Foto do entregador em cache durante a corrida (LGPD).

## 7. Refutados (não reabrir)

- **"Programada ignorada contra decisão do dono"**: já está adiada e rastreada na #2465. O WP prefere a Directive local, que pode ser adiantada pelo Pronto.
- **"valor_cobrar, código, programada e condutor ignorados" (pacote)**: o código já é lido e mostrado. `valor_cobrar` não tem semântica documentada. A programada foi preterida de propósito. Condutor dirigido não tem prova.
- **"enviarMensagem, reciboEntrega, multicategoria"**: a mensagem é entre central e condutor, não da empresa. O recibo v1 não existe na doc. Multicategoria não foi achada e o "volume" do domínio não existe.
- **"Erro do courier-ride fora do dialeto"**: 409 só com `detail` está dentro do contrato, e a recusa já é filtrada pela projeção antes do clique.
- **"Entregas expõe PII a quem só expede"**: o quadro do Gestor já expõe o mesmo dado com a mesma permissão, de propósito.
- **"Caminhos de falha sem teste"**: os testes existem em outros arquivos. O resto duplica achados que já trazem o próprio teste.
- **"Reatribuição diverge para sempre"**: o polling ligado (60 s) corrige o entregador em uma batida, e a volta A→D não tem prova. O risco latente entra na F1b.
- **"Estado 'back' diz 'está voltando' depois do F"**: o runbook diz que o F é na porta, e a premissa não está homologada.

Nada foi alterado no repositório. Só rodei leitura, grep e `gh view`.