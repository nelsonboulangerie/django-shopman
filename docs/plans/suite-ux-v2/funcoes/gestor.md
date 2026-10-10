# Gestor de pedidos — engenharia reversa por função

App: `surfaces/orders-nuxt` (4 seções: Pedidos `/`, Catálogo `/catalog`, Clientes `/customers`, Canais `/feeds`).
Back: `shopman/backstage/api/operations.py` (views de pedido), `api/catalog.py`, `api/catalog_bindings.py`, `api/feeds.py`, `api/channel_health.py`, `api/ifood_store.py`, `api/customers.py`, `api/alerts.py`; projeções `projections/order_queue.py`, `catalog.py`, `feeds.py`, `channel_health.py`, `channel_attention.py`, `customers.py`, `ifood_handshake.py`; serviços `backstage/services/orders.py`, `order_danfe.py`, `delivery_devices.py`, `catalog.py`, `feeds.py`, `customers.py`; regras de domínio em `shop/services/operator_orders.py`, `shop/services/cancellation.py`, `shop/services/channel_switch.py`.

Leitura essencial: o "Gestor" não é uma tela, são **quatro trabalhos de natureza diferente** colados numa barra:
(1) **despacho em tempo real** (fila: segundos, cliente esperando, de pé no passe);
(2) **cardápio vivo** (pausar o que acabou, segundos/minutos, em plena operação);
(3) **configuração de canal/vitrine** (raro, sentado, com gerente);
(4) **higiene de cadastro** (clientes, vínculos, PIM, fiscal: dias, escritório).
Hoje os quatro moram no mesmo app, com o mesmo peso, no mesmo dispositivo.

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| P01 | Vigiar a fila do dia (o que entrou, o que está parado, o que sai) | atendente de expedição / gerente de turno | passe/balcão; desktop ou tablet | turno aberto | contínuo | segundos | VIGIAR |
| P02 | Perceber que chegou pedido que exige gesto (som, push, "Ciente") | atendente de expedição | idem + celular no bolso | pedido novo tratável | 30–200/dia | segundos | AVISAR |
| P03 | Aceitar pedido novo (um ou em lote) antes do prazo | atendente / gerente | passe; tablet | pedido em "Entrada" com prazo correndo | 30–200/dia | segundos–minutos | TRIAR |
| P04 | Recusar pedido novo com motivo (iFood: motivo codificado) | atendente / gerente | idem | sem estoque, fora de área, loja lotada | 0–5/dia | minutos | TRIAR |
| P05 | Avançar etapa (preparo → pronto → concluído) um ou em lote | atendente de expedição | passe; tablet | cozinha terminou / cliente retirou | 100–400 toques/dia | segundos | AVANÇAR |
| P06 | Assumir / liberar um pedido ("estou atendendo") | qualquer operador | passe | dois operadores na mesma fila | poucas/turno | baixa | ASSUMIR (novo) |
| P07 | Despachar entrega (troco que sai, maquininha, ir junto) | expedição | passe; tablet | sacola pronta + entregador na porta | 10–80/dia | segundos, entregador esperando | AVANÇAR + REGISTRAR-QUANTIDADE |
| P08 | Fechar a saída quando o entregador volta | expedição / caixa | passe/caixa; tablet | entregador voltou com dinheiro e maquininha | 10–80/dia | segundos–minutos | CONFERIR |
| P09 | Registrar maquininha devolvida (avulso) | expedição | passe | maquininha voltou sem acerto pendente | poucas/dia | minutos | REGISTRAR-QUANTIDADE (custódia) |
| P10 | Acertar dinheiro da entrega quando voltou diferente | expedição / caixa / gerente | caixa | valor ≠ esperado | raro | minutos | CONFERIR |
| P11 | Receber pagamento na retirada (encomenda paga no balcão) | atendente | balcão | cliente chegou para retirar | 5–40/dia | segundos, cliente esperando | REGISTRAR-QUANTIDADE |
| P12 | Imprimir / reimprimir DANFE da sacola | expedição / balcão | passe; precisa impressora | DANFE não saiu, cliente pede | poucas/dia | segundos–minutos | EMITIR |
| P13 | Reprocessar NFC-e não autorizada | gerente / expedição | qualquer | card "NFC-e não autorizada" / alerta | raro | horas | CORRIGIR + EMITIR |
| P14 | Responder negociação iFood (cancelamento/reembolso pedido pelo cliente) | gerente | escritório/passe; desktop | iFood abre handshake com prazo | raro (0–3/semana) | minutos (prazo iFood) | APROVAR |
| P15 | Achar um pedido (código, cliente, item) e abrir o detalhe | qualquer | qualquer; celular inclusive | cliente liga/chega, dúvida | dezenas/dia | segundos | LOCALIZAR |
| P16 | Escrever nota da cozinha (tags + texto) | atendente / gerente | passe | cliente pediu ajuste, alergia | poucas/dia | minutos | INSTRUIR (novo) |
| P17 | Comentar no histórico do pedido | qualquer | qualquer | fato a registrar (ligou, reclamou) | poucas/dia | baixa | ANOTAR (novo) |
| P18 | Cancelar pedido não pago (motivo) | atendente/gerente | qualquer | cliente desistiu, erro | poucas/semana | minutos | CORRIGIR |
| P19 | Cancelar pedido pago (segunda assinatura de gerente) | gerente | qualquer | idem com dinheiro capturado | raro | minutos | CORRIGIR + APROVAR + AUTORIZAR |
| P20 | Reenviar link de pagamento | atendente | qualquer | cliente não pagou o link | poucas/dia | minutos | AVISAR |
| P21 | Cotar / chamar / cancelar corrida externa (Machine) | expedição | passe | sem entregador próprio | 0–30/dia (se ligado) | minutos | DELEGAR (novo) |
| P22 | Conferir se o cliente recebeu os avisos | atendente/gerente | qualquer | cliente diz "não recebi" | raro | minutos | ENTENDER |
| P23 | Contatar o cliente (telefone, central iFood com código) | atendente | celular/telefone | dúvida no pedido | poucas/dia | minutos | LOCALIZAR + AVISAR |
| P24 | Ver encomendas agendadas para os próximos dias | gerente / produção | escritório | planejamento do dia seguinte | 1–3/dia | horas | VIGIAR / PLANEJAR |
| P25 | Tratar alertas de pedido (sino: abrir contexto, "Visto") | gerente de turno | passe | DANFE falhou, NFC-e, troco etc. | poucas/dia | minutos | AVISAR → TRIAR |
| P26 | Exportar CSV / imprimir a fila (passagem de turno) | gerente | escritório | troca de turno | 0–2/dia | baixa | EMITIR |
| P27 | Perceber canal de venda fechado/pausado/divergente na fila | expedição/gerente | passe | canal desligado, iFood diverge | raro | minutos | VIGIAR |
| P28 | Identificar-se na estação (PIN/crachá; reidentificar após auto-lock) | qualquer | estação | abertura de turno, auto-lock | várias/turno | segundos | AUTORIZAR |
| C01 | Pausar/ativar um produto num canal (acabou no iFood, voltou) | gerente / atendente | balcão/escritório; tablet ou celular | produto esgotou / voltou | 5–30/dia | minutos (vende o que não tem) | CONFIGURAR (operacional) |
| C02 | Pausar/ativar um produto em todos os canais | gerente | idem | acabou de vez / defeito | poucas/dia | minutos | CONFIGURAR (operacional) |
| C03 | Mudar o preço de um produto num canal | gerente/dono | escritório; desktop | reajuste, margem do iFood | semanal | dias | CONFIGURAR |
| C04 | Ocultar/exibir produto no catálogo (sair do cardápio) | gerente/dono | escritório | sazonal, lançamento | semanal | dias | CONFIGURAR |
| C05 | Publicar/pausar em lote numa superfície (com prévia) | gerente/dono | escritório; desktop | lançamento de coleção, feriado | semanal | horas | CONFIGURAR |
| C06 | Reprecificar em lote (definir, %, R$) com prévia | dono | escritório; desktop | reajuste geral, taxa iFood | mensal | dias | CONFIGURAR |
| C07 | Reordenar coleções (ordem do cardápio em toda parte) | dono/marketing | escritório | campanha, sazonal | mensal | dias | CONFIGURAR |
| C08 | Reordenar produtos dentro de uma coleção manual | dono/marketing | escritório | destaque | mensal | dias | CONFIGURAR |
| C09 | Achar produto / recortar a matriz (busca, filtros, colunas) | qualquer | qualquer | antes de C01–C06 | contínuo | segundos | LOCALIZAR |
| C10 | Reenviar sincronização de um produto a uma plataforma | gerente | escritório | selo de erro de sync | raro | horas | CORRIGIR |
| C11 | Editar o cadastro completo do produto (geral, preço/config, ingredientes/nutrição) | dono/gerente | escritório; desktop | produto novo, ajuste de rótulo | semanal | dias | CONFIGURAR |
| C12 | Pedir sugestão de texto à IA, campo a campo | dono/marketing | escritório | descrição vazia/fraca | semanal | dias | COMPOR |
| C13 | Completar dados de redes sociais (marca, GTIN, categorias, hashtags) | marketing | escritório | selo "Incompleto", feed Google/Meta | mensal | dias | CONFIGURAR |
| C14 | Corrigir dados fiscais (perfil, NCM, CEST, origem; GTIN recusado pela SEFAZ) | dono/contador | escritório | alerta SEFAZ → `?sku=&tab=` | raro | horas–dias | CORRIGIR |
| C15 | "Permitir compra" (ligar o cadastro de compra do mesmo SKU) | dono/comprador | escritório | começar a revender item | raro | dias | CONFIGURAR |
| C16 | Ler o estado do produto (esgotado, pausado, fora do cardápio, resta N, repõe N no lote) | gerente | qualquer | olhar a matriz | contínuo | minutos | VIGIAR |
| K01 | Ligar/desligar um canal por um período, com motivo e gerente | gerente | passe/escritório; tablet/celular | cozinha saturada, falta entregador, feriado | poucas/semana (pico: várias no dia) | minutos | CONFIGURAR + AUTORIZAR |
| K02 | Conferir a saúde do canal e resolver a pendência apontada | dono/gerente | escritório | ponto âmbar em Canais, canal novo | raro | horas | CONFERIR |
| K03 | Parear uma TV (endereço/QR + entrar uma vez) | gerente/instalador | na frente da TV + celular | TV nova / trocada | raríssimo | baixa | AUTORIZAR (dispositivo) |
| K04 | Escolher as coleções que um feed/TV exibe | dono/marketing | escritório | trocar cardápio da parede | mensal | dias | CONFIGURAR |
| K05 | Ajustar rotação de páginas da TV (segundos, itens/tela) | dono | escritório | legibilidade | raríssimo | baixa | CONFIGURAR |
| K06 | Ligar o modo automático da TV e escrever as frases do descanso | dono | escritório | instalação | raríssimo | baixa | CONFIGURAR |
| K07 | Saber se o iFood está recebendo pedidos agora (e por que diverge) | gerente | passe | aviso na fila / dúvida | poucas/dia | minutos | VIGIAR |
| K08 | Abrir/prever a saída de um feed ou TV ("como o cliente vê") | dono | escritório | após configurar | raro | baixa | CONFERIR |
| K09 | Revisar vínculos de catálogo do canal (importar captura iFood, ligar anúncio ↔ SKU) | dono/gerente | escritório; desktop | integração nova, anúncio órfão | raro (meses) | dias | CONFERIR + CONFIGURAR |
| U01 | Achar um cadastro de cliente (busca; duplicados, iFood, sem telefone) | gerente | escritório | dúvida, limpeza | semanal | baixa | LOCALIZAR |
| U02 | Ler a ficha do cliente (identificadores, endereços, pedidos, candidatos) | gerente | escritório | antes de unificar / atender | semanal | baixa | ENTENDER |
| U03 | Unificar dois cadastros (escolher quem fica, prévia, confirmar) | gerente | escritório; desktop | cadastro iFood sem telefone duplicado | semanal | dias | CORRIGIR |
| U04 | Desfazer uma unificação (janela de 24 h) | gerente | escritório | unificou errado | raríssimo | horas (24 h) | CORRIGIR |
| U05 | Editar cadastro do cliente (nome, contato) — sai para o Admin | gerente | escritório | dado errado | raro | dias | CONFIGURAR (fora do app) |

Total: **59 trabalhos** (28 de pedido, 16 de catálogo, 9 de canal, 5 de cliente + 1 que sai do app).

---

## 2. Fichas

### Pedidos — fila e fluxo

**P01 — Vigiar a fila do dia**
- Quem: atendente de expedição (o "passe"), gerente de turno.
- Onde: hoje desktop-first (3 colunas Entrada/Preparo/Saída, + modo tabela). Sentido: tablet fixo no passe ou monitor de parede para leitura + tablet para gesto.
- Gatilho: abertura de turno; fica aberta o dia todo. Freq.: contínua. Urgência: segundos. Cliente esperando: sim (indireto).
- Objetivo real: saber, num relance, qual pedido precisa de mim agora e qual está atrasando.
- Info mínima: por pedido, código curto + o que falta fazer (verbo) + quanto tempo resta/passou + para onde vai (retirada/entrega) + bloqueio se houver. **Sobra**: prefixo do ref, ícone de canal, pill de pagamento quando já pago, resumo de itens em todos os cards, chips de canal com contagem, ordenação (3 modos), modo tabela, CSV/impressão, indicador "ao vivo". **Falta**: uma ordem única por urgência real (prazo + idade + entregador esperando) em vez de 3 colunas por estado; sinal agregado "X atrasados".
- Entrada: nenhuma (ler); filtros por canal/fulfillment/busca.
- Efeito: nenhum. Erro: n/a.
- Exceções: SSE cai → poll 30 s com sinal "Atualização automática"; leitura falha → mantém última e avisa; estação travada (403) não vira "erro de rede"; pedidos de balcão (PDV) nunca entram; encomenda futura vai para "Agendados"; pedido de teste iFood com aviso.
- Caminho hoje: abrir `/` e ler 3 colunas (rolar cada uma). → Mínimo: 0 passos; uma lista ordenada por "precisa de você agora". Indispensável: olhar.
- Fronteira: entra de Storefront/WhatsApp/iFood (commit), alimenta KDS (preparo) e caixa (acerto).
- Padrão: VIGIAR.
- Evidência: `pages/index.vue`, `presentation/board.ts` (`zonesView`, `triageCards`), `projections/order_queue.py::build_two_zone_queue`.

**P02 — Perceber pedido que exige gesto**
- Quem: expedição. Onde: estação + notificação do navegador (celular/desktop).
- Gatilho: projeção nova contém ref "tratável" (pode aceitar, avançar, acertar, maquininha voltar) que antes não era. Freq.: por pedido. Urgência: segundos.
- Objetivo: alguém ouvir e olhar a fila.
- Info mínima: "chegou trabalho" + qual. Sobra: 3 estados do botão de som (ligado/desligado/bloqueado pelo autoplay), botão "Ciente" separado. Falta: dizer *que tipo* de gesto (aceitar vs. entregador voltou) no próprio aviso.
- Entrada: confirmar ("Ciente"); 1º gesto para liberar áudio.
- Efeito: para o alerta sonoro. Reversível: sim. Custo do erro: alto se o som estiver bloqueado e ninguém notar (prazo de aceite vence).
- Exceções: autoplay bloqueado (ponto âmbar), encomenda futura não toca, SSE só dispara refetch.
- Caminho hoje: som → olhar → (opcional) "Ciente". Mínimo: o som para sozinho quando o gesto é feito (o "Ciente" é redundante com agir).
- Padrão: AVISAR.
- Evidência: `composables/useOrdersBoard.ts` (attention), `presentation/board.ts::newlyTreatableOrderRefs`, `utils/treatableNotification.ts`.

**P03 — Aceitar pedido novo**
- Quem: atendente/gerente. Onde: passe; tablet. Gatilho: card na Entrada com ampulheta (prazo `confirmation.timeout`).
- Freq.: por pedido remoto (30–200/dia). Urgência: segundos–minutos; **o prazo pode auto-confirmar OU auto-cancelar** (`confirmation_action`). Cliente esperando: sim.
- Objetivo: comprometer a casa com o pedido (dispara reserva, cozinha, aviso ao cliente/iFood).
- Info mínima: itens (para saber se tem), horário/data combinada, entrega/retirada, prazo restante. Sobra: atribuição, pills, endereço completo nesta etapa. Falta: **disponibilidade dos itens no próprio card** (o operador aceita "no escuro" e só o servidor recusa); para o caso normal (confirmação otimista), o aceite é quase redundante.
- Entrada: confirmar (1 toque); em lote: selecionar + "Aceitar N".
- Efeito: `new → accepted` (via `confirm_order`), notificação ao cliente/iFood. Reversível: só por cancelamento. Custo: médio (aceitar sem estoque gera cancelamento depois).
- Exceções: pagamento não capturado ou guards de confirmação → botão desabilitado com motivo (`confirmation_block_reason`); cancelamento iFood pendente; revisão mudou → 409.
- Caminho hoje: 1 toque no card. Mínimo: **0** quando confirmação otimista está ligada e há estoque (o sistema já faz); 1 toque só para exceção. Indispensável: nenhum no caso normal; a decisão real é "recusar".
- Fronteira: Storefront/iFood → KDS.
- Padrão: TRIAR.
- Evidência: `OrderCard.vue`, `presentation/board.ts::cardAffordances/bulkableRefs`, `services/orders.py::confirm_order`, `operator_orders.py::confirmation_block_reason`, `order_queue.py::_confirmation_deadlines`.

**P04 — Recusar pedido novo**
- Quem: atendente/gerente. Onde: passe. Gatilho: não dá para atender (falta item, área, lotação).
- Freq.: rara. Urgência: minutos (antes do prazo). Cliente esperando: sim.
- Objetivo: devolver o pedido ao cliente com um motivo que ele entenda (e que o iFood aceite).
- Info mínima: motivo. iFood: lista viva de códigos do iFood (obrigatória). Outros canais: texto livre no board, mas **no detalhe** existem presets da casa (Admin) + "Outros" — dois diálogos diferentes para o mesmo gesto. Falta: presets também no board.
- Entrada: escolher de lista curta (iFood) / digitar texto.
- Efeito: `reject_order` → cancelado + aviso ao cliente com o motivo. Irreversível. Custo: alto (perde venda, avaliação iFood).
- Exceções: falha ao buscar motivos iFood → "Nenhuma ação foi aplicada", consultar de novo; iFood sem motivos; texto não salvo protegido.
- Caminho hoje: toque "Recusar" → diálogo → escolher/digitar → "Recusar pedido" (3–4). Mínimo: 2 (gesto + motivo de lista). Indispensável: o motivo.
- Padrão: TRIAR.
- Evidência: `pages/index.vue` (reject dialog), `components/OrderReasonDialog.vue`, `services/orders.py::reject_order`, `operator_orders.py::cancellation_reasons`.

**P05 — Avançar etapa**
- Quem: expedição. Onde: passe; tablet. Gatilho: cozinha terminou (pronto), cliente retirou (concluir), pedido entregue.
- Freq.: 2–4 toques por pedido. Urgência: segundos. Cliente esperando: às vezes.
- Objetivo: refletir no sistema o estado físico (para o cliente ver "pronto", o KDS limpar, o pedido fechar).
- Info mínima: o próximo verbo (`next_action_label`) e se está bloqueado (frase inteira). Sobra: tudo o resto do card. Falta: **as transições que já acontecem em outro lugar** (o KDS marca pronto; o cliente marca "Recebi"; auto-conclusão por ETA) não deveriam exigir o Gestor — hoje o board ainda oferece o toque.
- Entrada: confirmar (1 toque) ou lote.
- Efeito: transição de status (`advance_order`), fulfillment sincronizado, notificação. Reversível: não pelo app. Custo: médio (concluir antes da hora some com o pedido da fila).
- Exceções (bloqueios com frase): pagamento não capturado; encomenda não vencida; fila de espera aguardando fornada; agendamento iFood; iFood aguardando retirada pelo entregador iFood; iFood sem responsável de entrega; cancelamento iFood pendente. Pedido de teste iFood: avançar, nunca produzir/entregar.
- Caminho hoje: 1 toque por pedido. Mínimo: 0 para "pronto" (vem do KDS) e "entregue" (cliente/ETA); 1 para "retirado" (o único fato que só o passe vê).
- Fronteira: KDS ↔ Gestor ↔ Storefront tracking.
- Padrão: AVANÇAR.
- Evidência: `operator_orders.py::advance_block/_NEXT_STATUS_MAP/schedule_delivery_auto_complete/confirm_received`, `presentation/board.ts::cardAffordances`.

**P06 — Assumir / liberar pedido**
- Quem: qualquer operador. Onde: card/tabela. Gatilho: evitar dois operadores no mesmo pedido.
- Freq.: baixa. Urgência: baixa.
- Objetivo: dizer aos colegas "este é meu".
- Info: quem está com ele. Entrada: toque (toggle). Efeito: `assign/unassign` em `Order.data`. Reversível: sim. Custo: baixo.
- Caminho: 1 toque. Mínimo: 0 — poderia ser implícito (quem fez o último gesto/abriu o detalhe). Indispensável: nenhum.
- Padrão: proposto **ASSUMIR** (reclamar posse de um item compartilhado; não muda o estado do item, muda quem responde por ele).
- Evidência: `OrderCard.vue` (toggle-assign), `services/orders.py::assign_order/unassign_order`.

**P07 — Despachar entrega**
- Quem: expedição. Onde: passe; tablet; entregador à frente. Gatilho: sacola pronta (status `ready`, delivery).
- Freq.: por entrega. Urgência: segundos. Cliente esperando: sim (entregador e cliente).
- Objetivo: registrar o que sai da loja com o entregador: a(s) sacola(s), o troco tirado da gaveta (que entra no livro do caixa), a maquininha (custódia), e se vão juntos.
- Info mínima: troco sugerido (valor pronto), maquininha livre (qual), outros pedidos prontos para a mesma rota. Sobra: nada no diálogo do board (enxuto). **No detalhe há OUTRO diálogo de saída** (checkbox de equipamentos, "Saiu sem troco"/"Levou o troco", sem "ir junto") — mesmo trabalho, duas formas.
- Entrada: confirmar; digitar número (troco, pré-preenchido); escolher de lista curta (maquininha, pedidos juntos).
- Efeito: `ready → dispatched`; `courier_out` no turno de caixa aberto; reserva de `DeliveryDevice`; viagem compartilhada (`trip_ref`); DANFE sai sozinha pela impressora de despacho; agenda auto-conclusão. Reversível: não pelo app. Custo: alto (troco fantasma na gaveta, maquininha perdida).
- Exceções: troco exigido e não informado → 409 com sugestão; valor mal digitado → 400; nenhuma maquininha livre → diálogo diz onde estão ("na rua: pedidos 0415 e 0418") e oferece "Entregador do X voltou"; lote não despacha quem pede troco/maquininha; iFood com entregador iFood bloqueia.
- Caminho hoje: 1 toque quando nada a perguntar (uma maquininha livre escolhida sozinha); senão toque → diálogo → (marcar juntos, ajustar troco) → confirmar (2–4). Mínimo: 1. Indispensável: confirmar que saiu (o fato físico).
- Fronteira: Gestor → caixa (cashman, livro `courier_out`) → fiscal/DANFE → Storefront tracking.
- Padrão: AVANÇAR + REGISTRAR-QUANTIDADE (+ COMPOR quando junta pedidos).
- Evidência: `components/DispatchDialog.vue`, `presentation/board.ts::oneTapDispatch/dispatchSteps/tripCandidates/freeMachines`, `pages/[ref].vue` (dispatch dialog), `services/orders.py::advance_order`, `services/delivery_devices.py`, `services/order_danfe.py`.

**P08 — Fechar a saída quando o entregador volta**
- Quem: expedição/caixa. Onde: passe ou caixa. Gatilho: entregador entra com dinheiro, troco e maquininha.
- Freq.: por saída. Urgência: segundos–minutos; entregador esperando para sair de novo.
- Objetivo: num gesto, marcar entregue, acertar o dinheiro (venda + troco integral voltando), devolver a maquininha e concluir todos os pedidos da viagem.
- Info mínima: a lista curta do que deve estar na mão (`courier_return_lines`: "R$ X em espécie", "Maquininha Azul") e quais pedidos fecha. Sobra: nada. Falta: nada essencial; bom exemplo de trabalho reduzido.
- Entrada: confirmar ("Conferido"); ou "Voltou diferente" → P10.
- Efeito: `courier_returned` → `delivered`, `settle_delivery_cash` (cod + `courier_in`), equipamento devolvido, `completed`. Reversível: não. Custo: alto (dinheiro).
- Exceções: sem turno de caixa aberto → recusa com "Abra um turno de caixa"; terminal ambíguo → 409; saída mudou → 409 "Confira o que voltou"; saída já fechada.
- Caminho hoje: 1 toque no card ("Entregador voltou", único gesto quando existe) → diálogo → "Conferido" (2). Mínimo: 2 (ver o que deveria voltar, confirmar). Indispensável: a conferência.
- Fronteira: Gestor → caixa (turno aberto de quem recebe).
- Padrão: CONFERIR.
- Evidência: `components/CourierBackDialog.vue`, `operator_orders.py::courier_return/courier_returned`, `services/orders.py::courier_returned`.

**P09 — Maquininha voltou (avulso)**
- Quem: expedição. Gatilho: maquininha devolvida sem acerto em dinheiro pendente (pedido no cartão).
- Freq.: poucas/dia. Urgência: minutos (a maquininha fica "na rua" e bloqueia o próximo despacho).
- Objetivo: liberar a maquininha para a próxima saída.
- Info: qual maquininha, de qual pedido. Entrada: confirmar. Efeito: custódia encerrada. Reversível: não. Custo: médio.
- Caminho: 1 toque (card ou detalhe). Mínimo: 0 se coberto por P08 (já é, quando há "Entregador voltou"); senão 1. É **o mesmo trabalho** que P08 em versão parcial.
- Padrão: REGISTRAR-QUANTIDADE (custódia) / CONFERIR.
- Evidência: `cardAffordances` (equipment_back), `services/orders.py::mark_equipment_returned`.

**P10 — Acertar dinheiro da entrega (voltou diferente)**
- Quem: expedição/caixa/gerente. Onde: caixa. Gatilho: "Voltou diferente" ou acerto manual.
- Freq.: rara. Urgência: minutos.
- Objetivo: registrar quanto entrou de venda e quanto de troco voltou, com o diferencial tendo dono.
- Info mínima: total do pedido, troco que saiu, o que o cliente disse que pagaria; o turno que recebe (`settleCustody`). Falta: o valor esperado como número grande (hoje é texto na descrição).
- Entrada: digitar número (valor recebido; vazio = total), digitar troco que voltou (pré-preenchido com o integral), marcar maquininha voltou.
- Efeito: lançamentos no livro do turno aberto. Reversível: não (livro imutável). Custo: alto.
- Exceções: pedido/turno mudou → aviso + "Conferir e manter os valores"; duplo acerto recusado pelo livro; valor inválido → 400.
- Caminho: diálogo com 1–3 campos + confirmar (3–4). Mínimo: 2 (número + confirmar).
- Padrão: CONFERIR + REGISTRAR-QUANTIDADE.
- Evidência: `pages/index.vue` e `pages/[ref].vue` (settle dialogs — dois iguais), `presentation/board.ts::changeBackSuggestionQ`, `services/orders.py::settle_delivery_cash`.

**P11 — Receber pagamento na retirada**
- Quem: atendente. Onde: balcão. Gatilho: cliente chega para buscar encomenda "paga na retirada".
- Freq.: 5–40/dia. Urgência: segundos, cliente à frente.
- Objetivo: receber e entregar a sacola.
- Info mínima: valor devido e forma. Entrada: confirmar (valor em branco = total). Efeito: entra no turno aberto, depois pode concluir.
- Exceções: sem turno → recusa. **É o mesmo diálogo de P10 com outro título** ("Pagamento na retirada"), e o mesmo trabalho que o balcão do PDV faz em "Encomendas" — dois apps para o mesmo gesto.
- Caminho: toque "Receber na retirada" → diálogo → confirmar → depois "Concluir" (3–4). Mínimo: 1 (receber = entregar = concluir).
- Fronteira: deveria ser PDV (o balcão tem a gaveta e a maquininha).
- Padrão: REGISTRAR-QUANTIDADE.
- Evidência: `cardAffordances` (settle_cash pickup), `operator_orders.py::collects_at_handoff/hand_over_at_counter`.

**P12 — Imprimir / reimprimir DANFE**
- Quem: expedição/balcão. Gatilho: DANFE não saiu ("não impressa" + motivo) ou cliente pede no balcão.
- Freq.: poucas/dia. Urgência: segundos–minutos.
- Objetivo: papel fiscal na sacola.
- Info: estado (impressa, saindo, não impressa + motivo, sai no despacho). Entrada: confirmar. Efeito: `PrintJob` na impressora do despacho, ou bytes para o agente local se não houver relay; carimbo `danfe_printed_at` (segunda vez sai "REIMPRESSÃO"). Custo: baixo.
- Exceções: sem impressora de despacho; agente não busca; alerta `danfe_print_failed` fecha sozinho quando sai. Regra dura: falta de NFC-e nunca segura a sacola.
- Caminho: 1 toque no card. Mínimo: 0 no normal (automática), 1 na exceção.
- Padrão: EMITIR.
- Evidência: `presentation/danfe.ts`, `composables/useDanfePrint.ts`, `services/order_danfe.py`.

**P13 — Reprocessar NFC-e não autorizada**
- Quem: gerente. Gatilho: card "NFC-e não autorizada · abrir e reprocessar" / alerta.
- Freq.: rara. Urgência: horas (obrigação fiscal, não operacional).
- Objetivo: recolocar a emissão na fila depois de corrigir a causa (ex.: GTIN/NCM do produto).
- Info mínima: **por que** a SEFAZ recusou e o que corrigir. Falta: o motivo e o atalho para o produto (C14) no lugar da decisão — hoje o botão reenfileira às cegas.
- Entrada: confirmar. Efeito: novo `Directive` fiscal. Reversível: n/a. Custo: baixo (reemite).
- Caminho: card → detalhe → "Reprocessar NFC-e" (2–3). Mínimo: 1 após corrigir causa.
- Padrão: CORRIGIR + EMITIR.
- Evidência: `OrderCard.vue` (fiscal failed), `pages/[ref].vue`, `services/orders.py::requeue_fiscal_emission`.

**P14 — Responder negociação iFood**
- Quem: gerente. Onde: desktop. Gatilho: iFood abre solicitação (cancelamento total/parcial, reembolso) com prazo; aparece em "Negociações iFood pendentes" no topo da fila, inclusive de pedidos encerrados.
- Freq.: rara. Urgência: minutos (prazo; o iFood diz o que acontece ao vencer: aceita, recusa ou nada).
- Objetivo: decidir se aceita ou recusa a solicitação do cliente, com motivo exigido pelo iFood.
- Info mínima: tipo de pedido, valor, prazo e consequência do vencimento, evidências (fotos), motivos aceitos. Sobra: contrapropostas exibidas sem poder negociar.
- Entrada: escolher decisão (lista curta) + motivo (lista curta) + texto (aceite) + marcar confirmação → enviar.
- Efeito: resposta enviada ao iFood (pode autorizar reembolso/cancelamento). Irreversível. Custo: alto (dinheiro + reputação).
- Exceções: envio incerto → "Verificar mesmo envio" (idempotência); negociação mudou → revisar; não aplicado → atualizar.
- Caminho: aviso → detalhe → seção → 4–5 interações. Mínimo: 2 (decisão+motivo, confirmar).
- Padrão: APROVAR (TRIAR de uma reclamação).
- Evidência: `components/OrderIFoodNegotiations.vue`, `projections/ifood_handshake.py`, `order_queue.py` (`ifood_negotiation_orders`).

**P15 — Achar um pedido e abrir o detalhe**
- Quem: qualquer. Onde: qualquer; celular quando atende telefone. Gatilho: cliente liga/chega, dúvida.
- Info mínima: código ou nome. Entrada: digitar texto (busca no board, `/` atalho) → tocar card.
- Efeito: nenhum. Exceções: busca só cobre a fila ativa (pedidos concluídos/cancelados não são achados aqui — falta).
- Caminho: digitar + toque (2). Mínimo: 2.
- Padrão: LOCALIZAR.
- Evidência: `presentation/board.ts::matchesQuery`, `pages/[ref].vue`, kit `OperatorOrderDetail.vue`.

**P16 — Escrever nota da cozinha**
- Quem: atendente/gerente. Gatilho: cliente pediu ajuste/alergia por telefone; observação a traduzir para a cozinha.
- Freq.: poucas/dia. Urgência: minutos (antes do preparo).
- Objetivo: que o ticket do KDS diga o que fazer de diferente.
- Info: observação do cliente (já no detalhe) + tags configuradas. Entrada: escolher tags (toque) + texto livre → salvar.
- Efeito: `kitchen_note` no pedido, aparece no KDS. Reversível: sim. Custo: médio (alergia).
- Exceções: conflito de revisão (nota mudou enquanto escrevia) → manter meu texto / usar do servidor.
- Caminho: detalhe → tags/texto → "Salvar nota" (3+). Mínimo: 2.
- Padrão: proposto **INSTRUIR** (passar instrução a outra etapa da cadeia, sem mudar o estado do item).
- Evidência: `pages/[ref].vue` (kitchen-note), `services/orders.py::save_kitchen_note`.

**P17 — Comentar no histórico**
- Quem: qualquer. Gatilho: fato a registrar. Entrada: texto + enviar. Efeito: evento na timeline. Reversível: não. Custo: baixo.
- Mínimo: 2. Padrão: proposto **ANOTAR** (deixar registro textual para quem vier depois; distinto de INSTRUIR porque não tem destinatário operacional).
- Evidência: kit `OperatorOrderDetail.vue`, `services/orders.py::add_comment`.

**P18 — Cancelar pedido não pago**
- Quem: atendente/gerente (status avançado exige permissão elevada). Gatilho: desistência/erro.
- Info mínima: motivo (opcional; presets da casa ou iFood codificado). Efeito: `cancel` + aviso ao cliente (nota separada do código interno). Irreversível. Custo: alto.
- Exceções: estado não permite (frase no lugar do botão); cancelamento iFood pendente; status avançado só gerente.
- Caminho: detalhe → "Cancelar" → motivo → confirmar (3–4). Mínimo: 2.
- Padrão: CORRIGIR.
- Evidência: `pages/[ref].vue`, `order_queue.py::_cancel_capability`, `shop/services/cancellation.py::operator_cancel_policy`.

**P19 — Cancelar pedido pago (gerente)**
- Quem: operador inicia, gerente assina. Gatilho: dinheiro capturado ou incerto (falha fechado).
- Objetivo: cancelar com estorno/aviso, com duas pessoas olhando.
- Info: motivo; lista de gerentes. Entrada: motivo + escolher gerente + PIN ou crachá.
- Efeito: cancela, estorno, notificação. Irreversível. Custo: alto.
- Exceções: assinatura inválida → mensagem no diálogo; pagamento/estado mudou → 409.
- Caminho: "Cancelar (gerente)" → motivo → confirmar → diálogo gerente → escolher → PIN (5–6). Mínimo: 3 (motivo, gerente, PIN/crachá).
- Padrão: CORRIGIR + APROVAR + AUTORIZAR. (Mesmo diálogo do PDV — bom.)
- Evidência: `pages/[ref].vue` (OperatorManagerAuth), `cancellation.py`.

**P20 — Reenviar link de pagamento**
- Quem: atendente. Gatilho: cliente diz que não recebeu/perdeu o link; pedido de link cobrável, não pago, não vencido.
- Entrada: confirmar. Efeito: reenvio (cadência controlada no servidor). Custo: baixo.
- Caminho: detalhe → 1 toque. Mínimo: 1 (poderia estar no card de pedido parado por pagamento).
- Padrão: AVISAR.
- Evidência: `pages/[ref].vue`, `order_queue.py::_payment_link_fields`.

**P21 — Corrida externa (Machine)**
- Quem: expedição. Gatilho: sem entregador próprio. Freq.: depende de integração.
- Info: cotação (valor · min · km), status por etapas, motorista, rastreio, código de confirmação. Entrada: confirmar (cotar, chamar, cancelar com 2º toque).
- Efeito: corrida solicitada/cancelada na central. Custo: médio-alto (corrida paga, duplicada).
- Exceções: despacho sem resultado confirmado → conferir na central antes de abrir outra; cancelamento incerto.
- Caminho: detalhe → cotar → chamar (2–3). Mínimo: 1 (chamar já com cotação automática).
- Padrão: proposto **DELEGAR** (entregar a execução a um terceiro e acompanhar).
- Evidência: `components/OrderCourierPanel.vue`, `order_queue.py::_courier_block`, `services/orders.py::courier_*`.

**P22 — Conferir avisos entregues** — ler recibos de notificação no detalhe. Padrão ENTENDER. Evidência: `OrderNotificationReceipts.vue`, `projections/notification_receipts.py`.

**P23 — Contatar o cliente** — telefone mascarado ou central iFood + código (com validade). Entrada: tocar para ligar. Melhor no celular. Padrão LOCALIZAR+AVISAR. Evidência: kit `OperatorOrderDetail.vue` (relay).

**P24 — Ver agendados** — encomendas de datas futuras agrupadas por data, sob a fila do dia; podem ter "Aceitar". Útil para planejar produção, mas mora no fundo do board operacional. Padrão VIGIAR/PLANEJAR. Evidência: `presentation/board.ts::preorderGroups`, `order_queue.py` (`future_preorders`).

**P25 — Alertas do sino** — lista com severidade, "abrir contexto", "Visto" (registra leitura; o alerta só some quando a causa acaba). Padrão AVISAR→TRIAR. Evidência: `AlertsBell.vue`, `useAlerts.ts`, `api/alerts.py`.

**P26 — Exportar CSV / imprimir fila** — passagem de turno. Raro, de escritório. Padrão EMITIR. Evidência: `presentation/board.ts::rowsToCsv`.

**P27 — Sinal de canal na fila** — uma linha por canal de venda desligado/pausado/divergente; segue para o card do canal em Canais (`?focus=`). Padrão VIGIAR. Evidência: `ChannelQueueSignal.vue`, `projections/channel_attention.py`.

**P28 — Identificar-se** — PIN/crachá no overlay; estação travada pelo servidor; troca de pessoa recria página e rascunhos. Padrão AUTORIZAR. Evidência: `app.vue`, kit `useOperatorLock`.

### Catálogo

**C01 — Pausar/ativar produto num canal**
- Quem: gerente/atendente. Onde: hoje matriz desktop com rolagem horizontal; deveria estar a um toque no celular/tablet do passe.
- Gatilho: acabou o produto e o iFood/loja online continua vendendo; voltou.
- Freq.: 5–30/dia. Urgência: **minutos** (cada minuto é pedido de algo que não existe → recusa/cancelamento). Cliente esperando: indireto.
- Objetivo: parar de vender o que não tem, naquele canal.
- Info mínima: produto, canal, estado atual. Sobra: preço, sync, PIM, filtros. Falta: ligação com o estoque (**"Esgotado" já é conhecido pelo sistema** — `row.sold_out` — e mesmo assim a pausa é manual por canal).
- Entrada: toque na célula (toggle). Efeito: `ListingItem.is_sellable` (ou `paused_skus` do feed) + push para plataforma. Reversível: sim. Custo: médio.
- Exceções: célula "Não ofertado" não aceita; revisão mudou → conflito; sync falha → selo de erro.
- Caminho: Catálogo → buscar → rolar até a coluna → toque (3–4). Mínimo: 0 quando o estoque zera (sistema pausa); 1 (buscar+toque) para decisão humana.
- Fronteira: estoque (stockman) / produção → vitrine dos canais.
- Padrão: CONFIGURAR (mas de natureza operacional — propor **DISPONIBILIZAR**? manter CONFIGURAR com marca "operacional").
- Evidência: `pages/catalog.vue::toggleCell`, `presentation/catalog.ts::cellState/rowStatus`, `services/catalog.py::set_cell`.

**C02 — Pausar/ativar em todos os canais** — menu ⋯ da linha; `Product.is_sellable`. Mesmo trabalho que C01 com escopo "todos". Caminho 3 toques. Mínimo 1. Evidência: `toggleProduct`, `services/catalog.py::set_product`.

**C03 — Mudar preço num canal**
- Quem: gerente/dono. Gatilho: reajuste, margem iFood.
- Info: preço base, preço atual da célula (só aparece quando difere), canal. Entrada: digitar número → salvar.
- Efeito: `ListingItem.price_q` + push. Reversível: sim. Custo: alto (preço errado vende errado).
- Exceções: preço mudou enquanto editava → mantém digitado + "Conferir e manter"; negativo recusado; tier mínimo.
- Caminho: toque no $ da célula → digitar → salvar (3). Mínimo: 2.
- Padrão: CONFIGURAR. Evidência: `startEdit/commitPrice`, `presentation/catalog.ts::cellPrice`.

**C04 — Ocultar/exibir produto** — `Product.is_published` pelo menu ⋯; "Oculto" (deliberado) ≠ "Pausado" ≠ "Esgotado" ≠ "Fora do cardápio" (coleção desativada — não há gesto aqui para reativar a coleção: falta). Padrão CONFIGURAR. Evidência: `toggleProductPublish`, `rowStatus`.

**C05 — Publicar/pausar em lote (prévia)**
- Quem: gerente/dono. Gatilho: lançar/retirar um conjunto.
- Entrada: selecionar linhas + escolher superfície + gesto → prévia (N células, estado novo) → confirmar.
- Efeito: várias células; sync separado. Exceções: prévia vencida → atualizar; feed só pausa/ativa.
- Caminho: 5–6. Mínimo: 3 (recorte, gesto, confirmar prévia).
- Padrão: CONFIGURAR. Evidência: `bulk/confirmPublication`, `services/catalog.py::preview_bulk_publication/apply_bulk_publication_intention`.

**C06 — Reprecificar em lote** — definir / ±% / ±R$ sobre seleção numa superfície; prévia obrigatória (1º clique prevê, 2º aplica). Custo alto. Padrão CONFIGURAR. Evidência: `applyBulkPrice`, `services/catalog.py::preview_bulk_price`.

**C07 — Reordenar coleções** — arrastar pills (ou setas); grava ao soltar com revisão; conflito mostra "Seu arraste / Ordem atual". Ordem é global (vale em TV, loja, feeds). Padrão CONFIGURAR. Evidência: `useDragReorder`, `services/catalog.py::reorder_collections`.

**C08 — Reordenar produtos na coleção** — só em coleção manual, sem busca/filtro. Padrão CONFIGURAR. Evidência: `canReorderRows`, `reorder_collection_items`.

**C09 — Achar/recortar** — busca (nome, SKU, keyword), coleção (servidor), filtros por dimensão (envio, canal, publicação, venda, estoque, PIM), colunas ocultáveis (cookie por estação), deep-link `?surface=&sync=error`. Padrão LOCALIZAR. Evidência: `presentation/catalogFilters.ts`.

**C10 — Reenviar sincronização** — toque no selo ▲ da célula ou "reenviar tudo" da linha. Padrão CORRIGIR. Falta: a causa do erro no lugar (só no title). Evidência: `resyncCell/resyncRow`, `apply_resync_intention`.

**C11 — Editar cadastro completo**
- Quem: dono/gerente. Onde: desktop (painel lateral de 5 abas, ~40 campos).
- Gatilho: produto novo/ajuste. Freq.: semanal. Urgência: dias.
- Objetivo: manter a "verdade" do produto (nome, descrições, foto, preço base, unidade/"vendido por peso", política de disponibilidade, validade, ciclo de produção, lote, venda D+1, ingredientes, alérgenos, nutrição ANVISA, porções).
- Entrada: digitar texto/números; salvar (patch só do que mudou).
- Exceções: conflito de revisão campo a campo (manter meu rascunho / usar atual); campos derivados de receita bloqueados.
- Caminho: ⋯ → Editar → aba → campos → salvar. Mínimo: n/a (é COMPOR de cadastro).
- Fronteira: não cria produto (criação segue no Admin); bundles/listings/coleções no Admin.
- Padrão: CONFIGURAR. Evidência: `components/CatalogProductPanel.vue`, `services/catalog.py::update_product_detail`.

**C12 — Sugestão de IA por campo** — botão por campo, prévia, Aceitar escreve só no rascunho; deliberadamente sem "sugerir tudo". Padrão COMPOR. Evidência: `CatalogAiSuggest.vue`, `services/catalog.py::ai_assist_field`.

**C13 — Dados de redes sociais (PIM)** — marca, GTIN, MPN, condição, categoria Google, TikTok, hashtags, legenda; selo "Incompleto" na linha. Padrão CONFIGURAR. Evidência: aba "social" do painel, `presentation/catalog.ts::pimSummary`.

**C14 — Dados fiscais / GTIN recusado** — perfil fiscal, NCM, CEST, unidade, origem; alerta SEFAZ abre `?sku=X&tab=...`; confirmar GTIN fecha os alertas. Padrão CORRIGIR. Falta: ligação de volta para reprocessar as NFC-e travadas por este produto (P13). Evidência: `services/catalog.py::_confirm_rejected_gtin/_close_gtin_rejected_alerts`.

**C15 — Permitir compra** — interruptor no painel: cria/reativa `buyman.Material` do mesmo SKU/unidade; recusa se há ficha ativa ("é produzido aqui"); vale na hora, fora do rascunho. Selos Comprável/Vendável/Produzido/Usado em receita. Padrão CONFIGURAR. Evidência: `CatalogProductPanel.vue::onPurchaseChange`, `services/catalog.py::set_purchasable`.

**C16 — Ler estado do produto** — linha esmaecida + selo (Oculto · Pausado · Fora do cardápio · Esgotado · Indisponível), "Resta N", "Repõe N no lote". Padrão VIGIAR. Evidência: `presentation/catalog.ts::rowStatus`.

### Canais

**K01 — Ligar/desligar canal com período**
- Quem: gerente (quem não é gerente chama um: PIN/crachá). Onde: passe ou celular.
- Gatilho: cozinha saturada, sem entregador, chuva, feriado, manutenção. Freq.: poucas/semana, em rajada nos dias ruins. Urgência: minutos (pedidos continuam entrando).
- Objetivo: parar (ou voltar a) receber pedidos de um canal por um tempo, voltando sozinho ao fim.
- Info mínima: canal, estado atual, por quanto tempo, motivo. Sobra: calendário para o caso comum (30 min/1 h/hoje). Falta: atalho direto da fila (hoje só o sinal, o controle mora em outra seção).
- Entrada: escolher período (lista curta) + motivo (lista curta ou texto; obrigatório para desligar) + autorização de gerente.
- Efeito: janela em `Channel.config.activation`; commit recusa (loja/WhatsApp), iFood fechado (renovado a cada 7 dias se "sem prazo"), TV tela preta, feed itens fora de estoque; LogEntry. Reversível: sim (outra janela). Custo: alto (desligar o iFood errado num sábado).
- Exceções: horário da loja sempre prevalece no sentido de fechar; ligar fora do horário não é oferecido; PDV não tem toggle; agendamento futuro ("Agendar o desligamento").
- Caminho: Canais → toggle → período → motivo → confirmar → gerente → PIN (5–7). Mínimo: 3 (período, motivo, autorizar); para gerente logado, 2.
- Padrão: CONFIGURAR + AUTORIZAR (é a única configuração com urgência operacional).
- Evidência: `components/ChannelSwitchDialog.vue`, `presentation/channelSwitch.ts`, `shop/services/channel_switch.py`, `api/feeds.py::FeedSwitchView`.

**K02 — Saúde do canal** — checklist vivo por canal; pendências primeiro, cada uma com o gesto que resolve (rota do Gestor, Admin, Django, parear, coleções); pronto = "Tudo certo" recolhido. Padrão CONFERIR. Evidência: `ChannelHealthChecklist.vue`, `presentation/channelHealth.ts`, `projections/channel_health.py`.

**K03 — Parear TV** — mostrar endereço + QR; na TV, entrar uma vez com operador; TV fica autorizada. Trabalho feito **na frente da TV**, com o celular — não na estação. Padrão AUTORIZAR (de dispositivo). Evidência: `ChannelHealthChecklist.vue` (pairing).

**K04 — Coleções do feed/TV** — marcar coleções; nenhuma = nada a exibir; conflito de revisão preserva seleção. Padrão CONFIGURAR. Evidência: `pages/feeds.vue::applyEdit`, `services/feeds.py::set_collections`.

**K05 — Rotação de páginas** — segundos + itens por tela (zero e zero = tudo numa tela). Padrão CONFIGURAR. Evidência: `set_rotation`.

**K06 — Modo automático + descanso** — horário da loja ±15 min; 1–2 frases do descanso de tela; só menuboard. Padrão CONFIGURAR. Evidência: `set_automatic`.

**K07 — Estado da loja no iFood** — "iFood: aberto/fechado (conferido às HH:MM)" e divergência com a casa. Padrão VIGIAR. Evidência: `IFoodChannelStore.vue`, `presentation/ifoodStore.ts`, `projections/ifood_store.py`.

**K08 — Abrir/prever a saída** — link para `output_path` no Django. Padrão CONFERIR.

**K09 — Revisar vínculos de catálogo do canal**
- Quem: dono/gerente. Onde: desktop. Gatilho: integração iFood nova ou anúncios órfãos.
- Objetivo: dizer qual produto nosso é cada anúncio da plataforma (identidade), sem copiar nada nem enviar à plataforma.
- Entrada: carregar arquivo JSON da captura (até 20 MiB) → guardar; escolher captura; por anúncio, escolher SKU de uma lista → confirmar vínculo local.
- Efeito: `CatalogSnapshot` e vínculos locais. Reversível: sim (revincular). Custo: médio (pedido iFood mapeado para produto errado).
- Exceções: arquivo não UTF-8; vínculo de outra captura → revisar; revisão mudou.
- Caminho: N anúncios × 3 interações. Mínimo: sugestão automática por nome/código + confirmar em lote.
- Padrão: CONFERIR + CONFIGURAR.
- Evidência: `pages/channels/[ref]/catalog.vue`, `CatalogBindingReview.vue`, `composables/useCatalogBindings.ts`, `api/catalog_bindings.py`.

### Clientes (só com `shop.manage_customers`)

**U01 — Achar cadastro** — busca (debounce, na URL) + filtros Todos / Possíveis duplicados / iFood / Sem telefone; paginação. Nasceu do cadastro iFood sem telefone. Padrão LOCALIZAR. Evidência: `pages/customers/index.vue`, `presentation/customers.ts`.

**U02 — Ficha** — contato, CPF, aniversário, identificadores por canal, endereços, pedidos, "Pode ser a mesma pessoa" com motivo. Edição sai para o Admin. Padrão ENTENDER. Evidência: `pages/customers/[ref].vue`.

**U03 — Unificar**
- Quem: gerente. Gatilho: candidato sugerido / filtro de duplicados.
- Info mínima: os dois lado a lado; o que passa para quem fica; quem fica (sugestão: quem tem telefone > não-iFood > o aberto).
- Entrada: escolher o outro (vem pronto ou busca) → trocar quem fica (opcional) → ler prévia (real, feita e desfeita no servidor) → unificar.
- Efeito: `MergeService` move pedidos, contatos, endereços, pontos; desativa o que sai. Reversível: 24 h (pontos não voltam). Custo: médio-alto.
- Caminho: 3–4. Mínimo: 2 (abrir par, confirmar prévia).
- Padrão: CORRIGIR. Evidência: `CustomerMergeDialog.vue`, `services/customers.py::preview_merge/merge_customers`.

**U04 — Desfazer** — lista de unificações com tempo restante; confirmar desfazer (avisa que pontos não voltam). Padrão CORRIGIR. Evidência: `pages/customers/merges.vue`, `services/customers.py::undo_merge`.

**U05 — Editar cadastro** — link para Admin. Fora do app.

---

## 3. Padrões que enxergo neste app

1. **O Gestor carrega quatro naturezas de trabalho com o mesmo peso.** Fila (segundos, de pé), cardápio vivo (minutos), configuração de canal/vitrine (dias, sentado, com gerente) e higiene de cadastro (escritório). A barra de seções as trata como iguais; o dispositivo do passe e o do escritório são o mesmo.
2. **AVANÇAR é feito à mão onde o sistema já sabe.** "Pronto" vem do KDS, "entregue" vem do cliente ("Recebi") e da auto-conclusão por ETA, "aceitar" vem da confirmação otimista — e o board ainda oferece os toques como trabalho principal. O único fato que só o passe vê é *saiu* e *retirou*.
3. **O mesmo trabalho com duas formas.** Despacho: diálogo do board (troco + maquininha + ir junto, 1 toque quando possível) vs. diálogo do detalhe (checkboxes, sem "ir junto"). Recusa: texto livre no board vs. presets da casa no detalhe. Acerto: dois diálogos idênticos copiados. "Receber na retirada" (Gestor) = entrega de encomenda no balcão (PDV). P08/P09/P10 são o mesmo CONFERIR da custódia da saída em três granularidades.
4. **"Esgotado" é conhecido e a pausa é manual.** `row.sold_out` e "Resta N" existem; C01/C02 continuam pedindo um toque por canal. A disponibilidade deveria seguir o estoque, e o gesto humano ficar só para a exceção deliberada (pausar com estoque).
5. **Informação de decisão longe da decisão.** Aceitar sem ver disponibilidade dos itens; reprocessar NFC-e sem ver o motivo da SEFAZ nem o produto a corrigir; erro de sync só em tooltip (inexistente no tablet); "Fora do cardápio" sem o gesto de reativar a coleção; canal pausado aparece na fila mas o controle está em outra seção.
6. **Um padrão de segurança comum e bom, repetido em toda escrita:** prévia/revisão + idempotência + conflito "manter o meu / usar o atual". É o mesmo trabalho (CONFIRMAR COM PROVA) em 12 lugares, cada um com sua frase; pode virar uma primitiva única.
7. **AUTORIZAR é um passo, não uma tela.** Cancelar pago, ligar/desligar canal e (no PDV) outras ações usam o mesmo diálogo de gerente — o padrão já convergiu; falta tratar "gerente logado" como 0 passos em todos.
8. **Rótulos novos propostos:** ASSUMIR (posse de item compartilhado), INSTRUIR (mensagem para outra etapa: nota da cozinha), ANOTAR (registro textual sem destinatário), DELEGAR (passar execução a terceiro e acompanhar: corrida externa). E sugiro marcar CONFIGURAR **operacional** (C01, C02, K01) separado de CONFIGURAR **cadastral**: têm urgência de minutos e devem estar no dispositivo do passe.

---

## 4. Cobertura (telas/estados) e dispositivo que faz sentido

| Rota / estado | O que é | Dispositivo certo | Por quê |
|---|---|---|---|
| `/` board (3 colunas) | fila do dia | parede (leitura) + tablet (gesto) | vigiar à distância; gesto curto de pé |
| `/` modo tabela + seleção em lote | fila densa | desktop | power-user, lote, teclado |
| `/` "Negociações iFood pendentes" | topo da fila | desktop | decisão de gerente, lê evidências |
| `/` "Agendados" | encomendas futuras | desktop/tablet do escritório | planejamento, não turno |
| `/` filtros, busca, ordenar, CSV, imprimir | triagem | desktop | escritório / passagem de turno |
| `/` overlay de identificação (PIN/crachá/estação travada) | antessala | todos | qualquer estação |
| diálogo Recusar | motivo | tablet | 2 toques com lista |
| diálogo Saída para entrega (board) | troco/maquininha/juntos | tablet | entregador à frente |
| diálogo Entregador voltou | conferência | tablet/caixa | lista curta + 1 toque |
| diálogo Acerto / Pagamento na retirada | valores | tablet no caixa (ou PDV) | onde está a gaveta |
| sino de alertas, sino de notificações, som/Ciente | avisos | celular (push) + estação | gerente circula |
| sinal de canal na fila | aviso | parede/tablet | só leitura |
| `/:ref` detalhe | pedido inteiro | celular/tablet | atender telefone, consultar |
| `/:ref` nota da cozinha (editor) | instrução | tablet | texto curto + tags |
| `/:ref` comentário | anotação | qualquer | texto |
| `/:ref` painel da corrida (Machine) | delegação | tablet | acompanhar e ligar ao motorista |
| `/:ref` negociações iFood | aprovação | desktop | evidências, prazo |
| `/:ref` diálogo Recusar/Cancelar (com presets) | motivo | tablet | lista curta |
| `/:ref` diálogo saída (versão do detalhe) | duplicata de P07 | — | deveria ser o mesmo do board |
| `/:ref` diálogo acerto | duplicata de P10 | — | idem |
| `/:ref` diálogo de gerente | assinatura | tablet | PIN/crachá |
| `/:ref` recibos de aviso, contato/relay | consulta | celular | ligar ao cliente |
| `/catalog` matriz produto × canal | cardápio | desktop (configurar) / **celular para pausar** | matriz larga é de escritório; pausar é de passe |
| `/catalog` pills de coleção (arrastar) | ordem | desktop | arrastar com precisão |
| `/catalog` edição de preço na célula | preço | desktop | digitar com contexto |
| `/catalog` barra de lote + prévia publicação + prévia preço | lote | desktop | revisão de N células |
| `/catalog` rascunho de ordem em conflito | conflito | desktop | raro |
| `/catalog` lightbox de foto | consulta | qualquer | — |
| `/catalog` painel do produto: Geral · Preço e config · Ingredientes e nutrição · Redes sociais · Fiscal | cadastro | desktop | ~40 campos, IA por campo |
| `/catalog?sku=&tab=` | entrada por alerta | desktop | correção fiscal |
| `/feeds` cards de canais de venda (toggle, saúde, iFood loja) | canais | tablet/celular para o toggle; desktop para saúde | toggle é urgente; saúde é setup |
| `/feeds` cards de feeds/TV (coleções, rotação, automático, mensagens, abrir saída) | vitrine | desktop | configuração rara |
| `/feeds` diálogo do toggle (período, calendário, motivo, gerente) | janela | celular/tablet | gerente pode estar fora |
| `/feeds` parear TV (endereço + QR) | instalação | celular na frente da TV | o trabalho acontece na TV |
| `/feeds?focus=<ref>` | vindo da fila | tablet | foco no card |
| `/channels/:ref/catalog` revisão de vínculos (importar captura, lista, vincular) | integração | desktop | arquivo + lista longa |
| `/customers` lista + filtros | cadastro | desktop | escritório |
| `/customers/:ref` ficha + candidatos | cadastro | desktop | comparação |
| `/customers/:ref` diálogo Unificar (busca, quem fica, prévia) | correção | desktop | lado a lado |
| `/customers/merges` + diálogo Desfazer | auditoria | desktop | raro |
