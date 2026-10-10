# Engenharia reversa por função: Cozinha (KDS), Shopman Apps (hub) e chrome comum do operador

Escopo lido: `surfaces/kds-nuxt` (páginas `index.vue`, `[ref].vue`, `pickup.vue`; `useKdsBoard`, `useKdsCustomerBoard`, `presentation/board.ts`, cards), backend `shopman/backstage/api/kds.py`, `projections/kds.py`, `services/kds.py`, `services/kitchen_ticket_print.py`, `models/kds.py`, core `shopman/shop/services/kds.py`; `surfaces/hub-nuxt` + `projections/hub.py` + `api/hub.py`; `surfaces/operator-kit/app` (login, lock, identify, station setup, manager auth, PIN, notificações, push, PWA install/update, capacidade, offline, wake lock, kiosk, giro, som).

Prefixos: **K** = Cozinha/KDS, **H** = Shopman Apps, **C** = chrome comum (vale para os oito apps).

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| K01 | Dizer qual estação esta tela é | cozinheiro / gerente que monta | tablet fixo da estação | instalar a tela, trocar de posto | 1× por dispositivo (raro) | minutos | CONFIGURAR |
| K02 | Ver o que fazer agora, na ordem certa | cozinheiro da estação | tablet fixo na bancada | pedido entrou / olhar entre tarefas | contínuo | segundos | VIGIAR |
| K03 | Pegar um pedido (iniciar preparo) | cozinheiro | tablet fixo | decidiu começar | por pedido (dezenas–centenas/dia) | segundos | AVANÇAR |
| K04 | Dar o pedido por pronto (finalizar) | cozinheiro | tablet fixo | terminou de montar | por pedido | segundos · cliente pode esperar | AVANÇAR |
| K05 | Desfazer um finalizar errado (5 s) | cozinheiro | tablet fixo, mesmo card | tocou errado | raro | segundos | CORRIGIR |
| K06 | Reabrir um pedido finalizado (até 30 min) | cozinheiro / chefe | tablet fixo, diálogo | percebeu erro depois | raro | minutos | CORRIGIR |
| K07 | Ler o pedido inteiro (detalhe) | cozinheiro | tablet fixo, diálogo | dúvida sobre item/nota | ocasional | segundos | LOCALIZAR (leitura) |
| K08 | Saber quanto fazer somando tudo ("a fazer") | cozinheiro / mise en place | tablet fixo, faixa | começo de rush, lote | várias/turno | minutos | ENTENDER / PLANEJAR |
| K09 | Espiar encomendas de outro dia (prévia) | chefe / cozinheiro | tablet / desktop | véspera, organizar mise en place | 1–2/dia | horas | PLANEJAR (leitura) |
| K10 | Tomar ciência de cancelamento ("Recebi o cancelamento") | cozinheiro | tablet fixo, cartão vermelho | cliente/operador retirou item ou cancelou | ocasional | segundos (evita desperdício) | TRIAR / AVISAR |
| K11 | Entender por que o pedido não pode ser finalizado (pagamento/confirmação) | cozinheiro | tablet fixo | servidor recusou | raro | segundos | (bloqueio) APROVAR alheio |
| K12 | Ver que falta estoque para separar | separador (estação picking) | tablet fixo | item sem saldo | ocasional | minutos | AVISAR |
| K13 | Reconhecer adicional de comanda e pedido de teste | cozinheiro | tablet fixo | delta de comanda / homologação iFood | ocasional | segundos | TRIAR |
| K14 | Acompanhar quais estações faltam em cada pedido (Saída · "Em preparo") | expedidor / atendente de passe | tablet fixo no passe | pedido em produção | contínuo | minutos | VIGIAR |
| K15 | Dar o "Pronto" da estação sem tela | expedidor (Saída) · caixa (PDV) · leitor na bancada | tablet do passe / PDV / leitor | papel da Via Cozinha voltou montado | por pedido de Lanches | segundos | AVANÇAR |
| K16 | Conferir o que entregar (volumes, itens) | expedidor | tablet do passe | montar sacola | por pedido | segundos · cliente esperando | CONFERIR |
| K17 | Entregar pedido de retirada | expedidor / atendente | tablet do passe | cliente chegou ao balcão | por pedido | segundos · cliente esperando | AVANÇAR |
| K18 | Despachar pedido de entrega | expedidor | tablet do passe | entregador chegou | por pedido de entrega | segundos/minutos · entregador esperando | AVANÇAR |
| K19 | Entender por que não pode sair (pagamento, maquininha, troco, iFood) | expedidor | tablet do passe | card bloqueado | ocasional | segundos | (bloqueio) → Gestor |
| K20 | Ouvir pedido novo e calar o aviso ("Visto") | cozinheiro / expedidor | tablet fixo | ticket novo / cancelado | por pedido | segundos | AVISAR |
| K21 | Garantir que o som está ligado | cozinheiro | tablet fixo | abriu a tela / autoplay bloqueado | 1×/turno | minutos | CONFIGURAR |
| K22 | Ajustar tamanho dos cards (densidade) | cozinheiro / quem monta | tablet fixo | distância de leitura, rush | raro | horas | CONFIGURAR |
| K23 | Achar um pedido específico (busca) | expedidor / atendente | tablet do passe | cliente pergunta "e o meu?" | várias/turno | segundos · cliente esperando | LOCALIZAR |
| K24 | Mostrar ao cliente se o pedido dele está pronto (painel de retirada) | cliente (público) | TV de parede no salão | sempre ligado | contínuo | segundos | VIGIAR (público) |
| K25 | Saber que a tela parou de acompanhar (sem conexão / estação sumiu) | cozinheiro | tablet fixo | rede caiu, estação removida | raro | segundos | AVISAR |
| H01 | Abrir o app do meu trabalho | qualquer operador | celular / tablet / PC | início de turno, troca de tarefa | 1–5×/turno | segundos | LOCALIZAR (navegar) |
| H02 | Descobrir que não tenho acesso e a quem pedir | operador novo | idem | primeiro acesso | raro | minutos | AVISAR |
| H03 | Escolher que avisos chegam a este dispositivo | operador / gerente | celular | quer receber push | raro | dias | CONFIGURAR |
| H04 | Dizer ao suporte que versão está rodando | operador | qualquer | relatar problema | raro | horas | ENTENDER |
| C01 | Entrar com senha | gerente / operador sem estação | qualquer | dispositivo novo, sessão expirada | 1×/dispositivo ou turno | minutos | AUTORIZAR |
| C02 | Transformar este dispositivo em estação | gerente | balcão (hoje só no PDV) | montar balcão | 1×/dispositivo | minutos | CONFIGURAR |
| C03 | Assumir a tela (crachá ou PIN) | operador | tablet/PC de estação | tela travada | várias/turno | segundos | AUTORIZAR |
| C04 | Travar / trocar de operador | operador | rail | sair do posto, troca de turno | várias/turno | segundos | AUTORIZAR |
| C05 | Trocar o próprio PIN | operador | tela de trava | vontade / segurança | raro | dias | CONFIGURAR |
| C06 | Trocar PIN temporário obrigatório | operador | tela de trava | gerente resetou | raro | minutos | AUTORIZAR |
| C07 | Matar crachá perdido | operador | tela de trava | perdeu o crachá | raro | minutos | CORRIGIR |
| C08 | Assinar uma exceção como gerente | gerente | diálogo sobre a tela de outro | sangria, desconto, cancelamento | várias/dia (PDV/Gestor) | segundos · cliente esperando | APROVAR |
| C09 | Ler avisos pessoais e log de acessos (sino) | operador | rail (hoje só no Gestor) | contador | diário | horas | AVISAR / ENTENDER |
| C10 | Ligar push neste dispositivo | operador | convite no app / home | convite | 1×/dispositivo | dias | CONFIGURAR |
| C11 | Instalar o app no dispositivo | operador | convite | primeira visita | 1×/dispositivo | dias | CONFIGURAR |
| C12 | Entrar na versão nova sem perder trabalho | operador / sistema | aviso / automático no ocioso | deploy | várias/semana | minutos | (sistema) |
| C13 | Saber se o serviço vai aguentar o pico | gerente / dono | rail (ponto colorido) | pico | ocasional | minutos | VIGIAR |
| C14 | Saber que está sem rede / servidor indisponível | qualquer | faixa / tela | rede caiu, redeploy | várias/semana | segundos | AVISAR |
| C15 | Travar o giro da tela | quem monta o tablet | rail | tablet gira sozinho | 1×/dispositivo | dias | CONFIGURAR |
| C16 | Voltar ao Shopman Apps / ir para outro app | operador | rail | troca de tarefa | várias/turno | segundos | LOCALIZAR (navegar) |
| C17 | Manter a tela acesa e em tela cheia | sistema | kiosk (KDS, painel) | sempre | contínuo | — | (sistema) |

---

## 2. Fichas

### K01 · Dizer qual estação esta tela é
- **Quem**: quem monta o posto (gerente) ou o cozinheiro que chega e acha a tela na lista.
- **Onde**: tablet fixo da estação. Hoje é uma lista (`/`) com nome, tipo (Preparo/Separação/Saída) e contagem de ativos; o ref vira URL (`/<ref>`). Faria mais sentido: escolha 1× e o dispositivo lembra (hoje lembra só porque a URL fica aberta/instalada).
- **Gatilho**: dispositivo novo ou troca de posto. **Frequência** rara · **urgência** minutos · cliente esperando: não.
- **Objetivo real**: amarrar esta tela física aos tickets roteados para este posto.
- **Info mínima**: nome do posto. Contagem de ativos ajuda a confirmar que é o certo. **Sobra**: ícone de tipo. **Falta**: dizer que a escolha fica guardada; a estação SEM tela (impressora) aparece na lista como se tivesse tela? (a lista não distingue `print_terminal`).
- **Entrada**: escolher de lista curta. **Efeito**: navegação; nada muda no servidor. Reversível, custo baixo (tela errada = cozinheiro vê pedidos de outro posto; se agir, conclui ticket alheio — médio).
- **Exceções**: estação removida → 404 vira "Esta estação não existe mais. Escolha a estação deste dispositivo na lista" (K25). Lista vazia: "Nenhuma estação configurada".
- **Caminho hoje**: abrir app → lista → tocar (2 toques). **Mínimo**: 0 no dia a dia (o dispositivo lembra); 1 na montagem.
- **Fronteira**: Admin cadastra `KDSInstance` (coleções roteadas, meta de tempo, impressora) → K02.
- **Padrão**: CONFIGURAR (de dispositivo).
- **Evidência**: `surfaces/kds-nuxt/app/pages/index.vue`, `projections/kds.py::build_kds_index` (monta um board inteiro por estação só para contar), `models/kds.py`.

### K02 · Ver o que fazer agora, na ordem certa
- **Quem**: cozinheiro/padeiro/barista de uma estação (Lanches, Confeitaria, Café, Encomendas).
- **Onde**: tablet fixo na bancada, leitura a 0,5–2 m, mãos ocupadas/molhadas. Correto hoje.
- **Gatilho**: ticket novo (SSE + som), ou olhar entre tarefas. Contínuo · segundos · cliente esperando: sim para balcão/retirada.
- **Objetivo real**: saber qual é o próximo prato e o que vai nele, sem esquecer nenhum pedido.
- **Info mínima por ticket**: código chamável, tempo decorrido contra meta (cor), itens qty × nome, observações (podem ser alergia), estado (na fila / em preparo / quem pegou). **Sobra**: ícone de canal, rótulo "Retirada/Entrega" no topo de todo card (só importa quando muda a embalagem), nome do cliente no card de preparo (útil na Saída, não na bancada), comanda riscada, relógio com segundos no cabeçalho, ícone "i". **Falta**: quem pegou o pedido (o estado é do ticket, mas não diz qual cozinheiro/tablet), horário prometido de retirada para pedidos agendados do dia (só tempo decorrido).
- **Entrada**: nenhuma (vigiar). Ordenação automática: atrasado > atenção > no prazo, depois mais antigo; o primeiro é "o próximo" (pintado).
- **Efeito**: nenhum. **Exceções**: erro com cache mantém a grade e mostra "Sem conexão, mostrando o último estado"; poll 15 s + SSE; tablet que acorda refaz o fetch.
- **Caminho hoje**: 0 toques. **Mínimo**: 0.
- **Fronteira**: PDV/Storefront/iFood → lifecycle `dispatch()` → `fire_lines` roteia por coleção/receita (prep se tem receita ativa, senão picking; venda de balcão presencial só manda o que tem receita) → ticket.
- **Padrão**: VIGIAR.
- **Evidência**: `pages/[ref].vue`, `presentation/board.ts::sortByUrgency/nextTicketPk/boardView`, `components/KdsTicketCard.vue`, `shop/services/kds.py::dispatch/_customer_holds_the_goods`.

### K03 · Pegar um pedido (Iniciar preparo)
- **Quem**: cozinheiro. **Onde**: botão na base do card.
- **Gatilho**: decidiu começar este pedido. Por pedido · segundos.
- **Objetivo real**: dizer às outras telas (e ao pedido) que alguém já está fazendo isto, para ninguém duplicar; leva o pedido a PREPARING quando o pagamento deixa.
- **Info mínima**: o card. **Sobra**: nada. **Falta**: quem iniciou.
- **Entrada**: confirmar (1 toque). **Efeito**: ticket `pending → in_progress`; tenta pedido `ACCEPTED → PREPARING` (silenciosamente não avança se o pagamento bloqueia). Reversível? Não há "despegar". Custo baixo.
- **Exceções**: encomenda de data futura → recusa "A prévia é somente para consulta". Otimista com reversão + toast em falha. Iniciar nunca é bloqueado por cancelamento.
- **Caminho hoje**: 1 toque. **Mínimo**: 1 (ou 0, se finalizar direto fosse aceito; hoje finalizar exige iniciar antes porque o botão só oferece finalizar após iniciar). Botão "arma" após 900 ms para o duplo toque não finalizar.
- **Fronteira**: muda o status do pedido visto no Gestor e no painel de retirada ("Em preparo").
- **Padrão**: AVANÇAR.
- **Evidência**: `useKdsBoard.ts::start`, `services/kds.py::start_ticket`, `shop/services/kds.py::_start_ticket_locked`.

### K04 · Dar o pedido por pronto (Finalizar preparo)
- **Quem**: cozinheiro. **Onde**: o mesmo botão, segundo estado.
- **Gatilho**: terminou de montar. Por pedido · segundos · cliente esperando.
- **Objetivo real**: liberar o pedido para a Saída/cliente; quando é o último ticket do pedido, o pedido vira READY (e venda de balcão vira COMPLETED se o pagamento libera).
- **Info mínima**: o card. **Falta**: aviso ANTES do toque de que o pagamento ainda não liberou (a Saída tem; o preparo não).
- **Entrada**: confirmar. **Efeito**: o card fica 5 s no lugar, apagado, com "Desfazer"; só então sai o POST (`done`). Ticket → done; `on_all_tickets_done` → READY; cliente é avisado. Reversível por K05 (5 s) ou K06 (30 min, enquanto o pedido não saiu). Custo médio (cliente avisado errado).
- **Exceções**: item cancelado sem ciência → botão vira "bloqueado" com toast "Confirme o cancelamento no cartão vermelho"; pagamento não confirmado / pedido não confirmado → servidor recusa (`TicketCompletionBlocked`) depois dos 5 s, card volta com toast; data futura → recusa. Tablet que dorme durante a janela confirma na hora (`keepalive`).
- **Caminho hoje**: 1 toque (+5 s de espera invisível). **Mínimo**: 1.
- **Fronteira**: → K14/K17/K18 (Saída), painel de retirada (K24), notificação ao cliente, PDV (venda de balcão fecha).
- **Padrão**: AVANÇAR.
- **Evidência**: `useKdsBoard.ts::finalize/commitFinish`, `presentation/board.ts::ticketAction`, `shop/services/kds.py::_complete_ticket_locked/on_all_tickets_done`.

### K05 · Desfazer finalizar (janela de 5 s)
- **Quem**: cozinheiro. **Onde**: no próprio card, onde o dedo acabou de tocar.
- **Gatilho**: toque errado. Raro · segundos.
- **Objetivo real**: impedir que um toque errado avise o cliente.
- **Entrada**: 1 toque. **Efeito**: nada sai para o servidor. Custo zero.
- **Caminho**: 1 toque. Mínimo 1.
- **Padrão**: CORRIGIR (preventivo).
- **Evidência**: `KdsTicketCard.vue` (bloco `finishing`), `useKdsBoard.ts::undoFinish`.

### K06 · Reabrir pedido finalizado (até 30 min)
- **Quem**: cozinheiro/chefe. **Onde**: botão com contador no cabeçalho → diálogo "Concluídos recentes" (12 últimos, 30 min) → "Reabrir".
- **Gatilho**: percebeu que faltou algo / bump errado. Raro · minutos · cliente pode estar esperando.
- **Objetivo real**: devolver o trabalho à grade e tirar o pedido de "pronto".
- **Info mínima**: código, cliente, hora da conclusão. **Falta**: os itens (para saber se é o certo).
- **Entrada**: escolher de lista + confirmar. **Efeito**: ticket → in_progress; pedido READY → PREPARING. Não "desavisa" o cliente. Recusado se o pedido já saiu (despachado/entregue/concluído/cancelado); a lista já esconde esses.
- **Caminho hoje**: 2 toques + achar. **Mínimo**: 2.
- **Padrão**: CORRIGIR.
- **Evidência**: `[ref].vue` (diálogo recall), `shop/services/kds.py::recall_block_reason/_reopen_ticket_locked`, `projections/kds.py` (`RECENT_DONE_WINDOW`).

### K07 · Ler o pedido inteiro (detalhe)
- **Quem**: cozinheiro. **Onde**: toque na área de leitura do card → diálogo só leitura (canal, horário, meta, cliente, notas, itens).
- **Gatilho**: dúvida. Ocasional · segundos.
- **Objetivo real**: ler o que não coube. Mas o card já não trunca nada (itens e notas quebram linha) — o detalhe repete o card com meta de tempo e horário.
- **Sobra**: quase tudo (duplica o card). **Falta**: nada essencial.
- **Entrada**: toque/fechar. Sem efeito.
- **Caminho**: 2 toques. **Mínimo**: 0 (o card completo já é o detalhe no tablet; no celular o detalhe faz sentido).
- **Padrão**: LOCALIZAR/leitura. Candidato a remover no tablet.
- **Evidência**: `components/KdsTicketModal.vue`.

### K08 · Saber quanto fazer somando tudo ("A fazer")
- **Quem**: cozinheiro em rush, mise en place.
- **Onde**: faixa sob o cabeçalho, uma pílula por item com a soma das quantidades dos tickets ativos (exclui os em janela de desfazer).
- **Gatilho**: rush; fazer em lote (6 croissants de uma vez). Várias/turno · minutos.
- **Objetivo real**: produzir em lote em vez de pedido a pedido.
- **Info mínima**: item × total pendente. **Falta**: separar "na fila" de "já em preparo"; quanto já tem pronto na vitrine (estoque) para não fazer de novo.
- **Entrada**: nenhuma. **Padrão**: ENTENDER/PLANEJAR. É o mesmo trabalho da "fila agregada" da Produção (pedido × lote).
- **Evidência**: `presentation/board.ts::allDayCounts`, `[ref].vue` (faixa "A fazer").

### K09 · Espiar encomendas de outro dia (prévia)
- **Quem**: chefe/cozinheiro na véspera. **Onde**: seletor nativo de data no cabeçalho, só com datas que têm trabalho vivo.
- **Gatilho**: organizar amanhã. 1–2/dia · horas.
- **Objetivo real**: ver o que esta estação terá de fazer numa data futura, sem poder agir.
- **Info mínima**: itens por pedido e total do dia (a faixa "A fazer" também aparece). **Sobra**: o card com botão inerte "Prévia · começa em dd/mm". **Falta**: horário de retirada de cada encomenda (há `scheduled_time_display` na projeção do ticket agendado).
- **Entrada**: escolher data. Sem efeito; som nunca toca; servidor recusa qualquer ação (`FutureWorkBlocked`).
- **Caminho**: 2 toques. **Mínimo**: 1. Melhor lugar: Produção (plano), não a tela da bancada.
- **Padrão**: PLANEJAR (leitura).
- **Evidência**: `[ref].vue::selectServiceDate`, `projections/kds.py::build_kds_board` (`preview_order_for_instance`, `_available_service_dates`).

### K10 · Tomar ciência de cancelamento
- **Quem**: cozinheiro. **Onde**: cartão vermelho no topo da grade ("Cancelado às HH:MM", código, itens) com botão "Recebi o cancelamento".
- **Gatilho**: pedido cancelado ou item retirado de um pedido em preparo (gera ticket cancelado com os itens retirados). Ocasional · segundos (parar de fazer).
- **Objetivo real**: parar de fazer o que não vai ser vendido; provar que a cozinha viu.
- **Info mínima**: código, itens retirados. **Falta**: se o resto do pedido continua (item retirado vs pedido inteiro) — a tela trata igual.
- **Entrada**: confirmar. **Efeito**: `acknowledged_at`; some do quadro; destrava o finalizar dos tickets vivos do mesmo pedido nesta estação. Some sozinho após 10 min se não há ticket vivo do pedido. Custo do erro: alto se ignorado (produção perdida), mas bloqueio força a ciência.
- **Exceções**: estação sem tela: o papel CANCELADO impresso conta como ciência automática no "Pronto" (K15). Mensagem do servidor ainda diz "toque em Ciente" (nome antigo do gesto; a tela diz "Recebi o cancelamento").
- **Caminho**: 1 toque. **Mínimo**: 1.
- **Fronteira**: PDV (unfire), Gestor/cliente (cancelar), `reconcile_to_lines` (pedido alterado).
- **Padrão**: TRIAR + AVISAR (ciência). Rótulo novo proposto: **ACUSAR-RECEBIMENTO** (o operador não decide nada; só prova que viu).
- **Evidência**: `[ref].vue` (TransitionGroup cancelados), `shop/services/kds.py::_acknowledge_ticket_locked`, `projections/kds.py` (`RECENT_CANCELLED_WINDOW`).

### K11 · Entender bloqueio de pagamento/confirmação no preparo
- **Quem**: cozinheiro. **Onde**: hoje só como toast vermelho depois do finalizar (o pedido volta à grade 5 s depois).
- **Gatilho**: pedido aceito com pagamento não capturado (Pix pendente, link). Raro · segundos.
- **Objetivo real**: não entregar mercadoria não paga; o cozinheiro pode fazer, mas não liberar.
- **Info mínima**: "aguardando pagamento" no card ANTES do toque. **Falta**: exatamente isso — a Saída tem `advance_block_label`, o card de preparo não.
- **Entrada**: nenhuma (esperar). **Efeito**: nenhum.
- **Padrão**: bloqueio; o "sim" vem de outro (pagamento). Rótulo proposto: **ESPERAR-LIBERAÇÃO**.
- **Evidência**: `shop/services/kds.py::_advance_to_preparing_block_reason`, `useKdsBoard.ts::commitFinish` (catch).

### K12 · Ver que falta estoque para separar
- **Quem**: separador da estação tipo `picking` (Encomendas/prateleira). **Onde**: linha "Sem estoque" / "Últimas N un." sob o item.
- **Gatilho**: saldo físico ≤ 0 ou abaixo do mínimo de alerta. Ocasional · minutos.
- **Objetivo real**: saber antes de ir à prateleira que não tem; pedir reposição/avisar.
- **Falta**: o que fazer (avisar Produção, substituir, avisar cliente). Nenhuma ação sai daqui.
- **Padrão**: AVISAR. **Evidência**: `projections/kds.py::_add_stock_warnings` (só `instance.type == "picking"`).

### K13 · Reconhecer adicional e pedido de teste
- **Quem**: cozinheiro. **Onde**: selo "Adicional" (ticket novo de pedido que já passou pela estação: item novo numa comanda gera só o delta) e faixa de pedido de teste do iFood ("não produzir"; o servidor já não cria ticket, a faixa cobre o que estava no painel).
- **Objetivo real**: não fazer em dobro; não fornar o que é teste.
- **Padrão**: TRIAR (sem entrada; é marca). **Evidência**: `presentation/board.ts::additionTicketPks`, `KdsTestOrderBanner.vue`, `shop/services/kds.py::dispatch` (`is_test_order`).

### K14 · Acompanhar quais estações faltam (Saída · "Em preparo")
- **Quem**: expedidor/atendente do passe. **Onde**: tablet fixo da estação tipo `expedition`, coluna esquerda; um card por pedido, uma linha por estação (na fila / em preparo / pronto; para estação sem tela: "impresso às HH:MM", "na fila da impressora", "não imprimiu" em vermelho; itens cancelados).
- **Gatilho**: pedido em produção. Contínuo · minutos.
- **Objetivo real**: saber o que está para sair e cobrar a estação que atrasa; descobrir papel que não imprimiu.
- **Info mínima**: código, tempo desde o disparo, estações pendentes. **Sobra**: estações já prontas ocupando linha cheia. **Falta**: a meta/atraso por estação (só tempo total).
- **Entrada**: nenhuma, exceto K15. **Efeito**: quando a última estação conclui, o card muda de coluna sozinho com som.
- **Padrão**: VIGIAR. **Evidência**: `KdsExitPreparingCard.vue`, `projections/kds.py::_build_exit_preparing(_card)`, `kitchen_ticket_print.py::paper_states`.

### K15 · Dar o "Pronto" da estação sem tela
- **Quem**: três portas para o mesmo ato — expedidor na Saída (botão "Pronto" na linha da estação), caixa no PDV (card do ticket), leitor de código na bancada (QR assinado da Via Cozinha).
- **Onde**: Saída (tablet), PDV, leitor USB. **Gatilho**: a bandeja/papel voltou montado de Lanches. Por pedido de estação sem tela · segundos.
- **Objetivo real**: concluir o ticket de quem não tem tela, para o pedido poder ficar pronto.
- **Info mínima**: pedido + estação + "papel saiu às". **Entrada**: confirmar (ou ler código). **Efeito**: tickets abertos daquela estação daquele pedido → done (`completed_via` = exit/pos/scanner); cancelamentos impressos viram ciência automática. Reversível só via K06 numa tela da estação (que não existe) — na prática, irreversível pelo KDS. Custo médio.
- **Exceções**: estação com tela → recusa "tem tela: o pronto é dado lá"; ticket cancelado → "foi cancelado, não prepare"; data futura; pagamento. Replay = sucesso.
- **Caminho**: 1 toque / 1 leitura. **Mínimo**: 0 toques com o leitor (a leitura É o gesto).
- **Fronteira**: impressão (relay `PrintJob`) → bancada → Saída/PDV/leitor → K17/K18.
- **Padrão**: AVANÇAR (por procuração). Mesmo trabalho que K04, com outra porta.
- **Evidência**: `api/kds.py` (`KDSExitPrintedStationDoneView`, `KDSPrintedTicketDoneView`, `KDSPrintedTicketScanView`), `services/kds.py::mark_printed_*`, `services/kitchen_ticket_print.py`.

### K16 · Conferir o que entregar
- **Quem**: expedidor. **Onde**: card de "Prontos para sair": número de volumes em destaque, linhas e total em R$; "Ver itens (n)" expande qty × nome.
- **Gatilho**: montar/entregar a sacola. Por pedido · segundos · cliente esperando.
- **Objetivo real**: não sair sacola incompleta.
- **Info mínima**: volumes + lista de itens. **Sobra**: total em R$ (só importa se cobra na porta), contagem de linhas. **Falta**: notas do pedido (ex.: "sem cebola", nome no copo) na Saída; marcar item a item conferido.
- **Entrada**: tocar para expandir. **Padrão**: CONFERIR. **Evidência**: `KdsExpeditionCard.vue`, `projections/kds.py::_build_expedition_card` (`units_count`).

### K17 · Entregar pedido de retirada
- **Quem**: expedidor/atendente. **Onde**: botão "Entregar pedido".
- **Gatilho**: cliente no balcão (chamado pelo painel K24). Por pedido · segundos · cliente esperando.
- **Objetivo real**: registrar que a mercadoria saiu e fechar o pedido.
- **Entrada**: confirmar (1 toque; sem desfazer). **Efeito**: `advance_order` (a mesma porta do Gestor) → COMPLETED; sai do painel de retirada. Irreversível pelo KDS. Custo médio (entregar o pedido errado não se detecta).
- **Exceções**: K19. Replay = sucesso.
- **Caminho**: 1 toque (+ busca K23 se muitos). **Mínimo**: 1; o passo que não se elimina é confirmar QUAL pedido foi entregue (código do cliente).
- **Padrão**: AVANÇAR. **Evidência**: `useKdsBoard.ts::expedite`, `shop/services/kds.py::expedition_action`.

### K18 · Despachar pedido de entrega
- **Quem**: expedidor. **Onde**: botão "Despachar pedido".
- **Gatilho**: entregador chegou. Por entrega · segundos/minutos · entregador esperando.
- **Objetivo real**: entregar a sacola ao entregador e iniciar a entrega (fulfillment, auto-conclusão).
- **Info mínima**: código, volumes, se precisa maquininha/troco. **Falta**: identificação do entregador; quando há troco/maquininha a tela não pergunta, manda ao Gestor.
- **Entrada**: confirmar. **Efeito**: → DISPATCHED (fulfillment, aviso fiscal). Irreversível pelo KDS.
- **Padrão**: AVANÇAR. **Evidência**: idem K17, `expedition_block_reason`.

### K19 · Entender por que não pode sair
- **Quem**: expedidor. **Onde**: botão inerte com rótulo (mesmo do Gestor) + frase: pagamento não capturado; "Abra este pedido no Gestor e confirme a maquininha"; "…informe o troco que o entregador leva"; regras do iFood (cancelamento pendente, janela, entregador).
- **Objetivo real**: não liberar mercadoria indevida; mandar à tela que sabe perguntar.
- **Falta**: um atalho para o pedido no Gestor (hoje é "abra no Gestor", sem link).
- **Padrão**: bloqueio → outro app. **Evidência**: `KdsExpeditionCard.vue` (`blocked`), `shop/services/kds.py::expedition_block_reason`.

### K20 · Ouvir pedido novo e calar ("Visto")
- **Quem**: cozinheiro/expedidor. **Onde**: fanfarra de ~2,3 s que repete a cada 8 s até alguém tocar "Visto" (ou até o limite de repetições); dispara por IDENTIDADE de ticket ativo/cancelado não visto, guardado por dia por estação no `localStorage`. Data futura nunca toca.
- **Objetivo real**: chamar o olho para a tela quando chega trabalho, sem repetir o que já foi visto.
- **Entrada**: 1 toque. **Efeito**: local ao dispositivo (outra tela da mesma estação continua tocando).
- **Padrão**: AVISAR. **Evidência**: `useKdsBoard.ts::KDS_ALERT/kdsAttentionDecision`, `operator-kit/.../useAlertSound.ts`.

### K21 · Garantir que o som está ligado
- **Quem**: cozinheiro. **Onde**: botão de som no cabeçalho (estado bloqueado em âmbar quando o autoplay impediu); estado vazio diz se o próximo vai avisar e oferece "Ligar o som".
- **Gatilho**: abrir a tela (autoplay exige um toque). 1×/turno.
- **Objetivo real**: o aviso de K20 funcionar. Preferência por estação, no dispositivo; `KDSInstance.sound_enabled` existe no modelo mas a tela não o lê.
- **Padrão**: CONFIGURAR. **Evidência**: `[ref].vue::handleSoundAction`, `useAlertSound.ts`.

### K22 · Ajustar densidade
- **Quem**: quem monta o tablet. **Onde**: botão que cicla Compacta (≥260 px) / Padrão (≥320) / Ampla (≥390); a grade preenche quantas colunas couberem. Guardado no dispositivo (`kds.density`), não por estação.
- **Objetivo real**: ajustar à distância de leitura e ao tamanho da tela.
- **Padrão**: CONFIGURAR. Deveria ser derivado da tela/estação, não do toque.
- **Evidência**: `[ref].vue` (`DENSITIES`).

### K23 · Achar um pedido (busca)
- **Quem**: expedidor/atendente ("e o meu pedido?"). **Onde**: campo de busca no cabeçalho; filtra por código, cliente, item (preparo) e por estação (coluna "Em preparo" da Saída). Contadores e "A fazer" não filtram.
- **Gatilho**: cliente pergunta. Várias/turno · segundos · cliente esperando.
- **Objetivo real**: responder ao cliente em que pé está o pedido dele.
- **Entrada**: digitar texto (teclado na tela). **Mínimo**: digitar 2–3 dígitos do código.
- **Padrão**: LOCALIZAR. **Evidência**: `[ref].vue::matchesQuery/matchesPreparing`.

### K24 · Painel público de retirada
- **Quem**: cliente no salão (o leitor); ninguém opera. **Onde**: TV de parede, `/pickup`, sem login, sem rail; poll 10 s + SSE com indicador honesto ("ao vivo" só com SSE conectado).
- **Gatilho**: sempre ligado. **Objetivo real**: o cliente saber, sem perguntar, que o pedido dele está pronto.
- **Info mínima**: código público (nunca nome; comanda sem número vira código opaco) em duas colunas: Pronto para retirar / Em preparo; só retirada, só do dia; até 24, prontos primeiro. **Falta**: nada essencial; som/chamada para quem não olha.
- **Padrão**: VIGIAR (público). **Evidência**: `pages/pickup.vue`, `useKdsCustomerBoard.ts`, `projections/kds.py::build_kds_customer_status/_public_comanda_code`.

### K25 · Saber que a tela parou de acompanhar
- **Quem**: cozinheiro. **Onde**: faixa "Sem conexão, mostrando o último estado. Reconectando…"; 404 da estação; `OfflineBanner`; sessão indisponível (redeploy) separada de sessão morta.
- **Objetivo real**: não confiar num quadro velho sem saber.
- **Padrão**: AVISAR. **Evidência**: `[ref].vue`, `useKdsBoard.ts::stationMissing`, `operator-kit/.../OperatorSessionUnavailable.vue`.

### H01 · Abrir o app do meu trabalho
- **Quem**: qualquer operador. **Onde**: celular/tablet/PC; home pós-login (`central.`). Grade de tiles só com o que a pessoa pode abrir (mesma regra de permissão do app de destino); Loja só para superusuário (nova aba). Instalado, cada app abre na própria janela.
- **Gatilho**: começo de turno, troca de tarefa. 1–5×/turno · segundos.
- **Objetivo real**: chegar ao app certo. Para quem tem um app só, é um passo a mais.
- **Info mínima**: nome do app. **Sobra**: descrição de uma linha em cada tile, saudação. **Falta**: estado de cada app (pedidos esperando no Gestor, tickets atrasados na Cozinha) — a home não diz onde está a urgência.
- **Entrada**: escolher de lista curta. **Caminho**: 1 toque. **Mínimo**: 0 para quem tem um único app (ir direto).
- **Padrão**: LOCALIZAR (navegar). **Evidência**: `hub-nuxt/app/app.vue`, `presentation/hub.ts`, `projections/hub.py`.

### H02 · Descobrir que não tenho acesso
- **Quem**: operador novo. **Onde**: estado vazio "Sua conta ainda não tem acesso a nenhuma superfície. Fale com o gerente." e falhas classificadas (sessão expirou / estação travada / sem acesso / indisponível com "Tentar de novo").
- **Padrão**: AVISAR. **Evidência**: `presentation/hub.ts::hubFailure/hubFailureCopy`.

### H03 · Escolher avisos deste dispositivo
- **Quem**: operador/gerente. **Onde**: `OperatorPushSettings` só na home; por app, com motivo quando não dá (instalação sem chave vs navegador sem push).
- **Padrão**: CONFIGURAR. **Evidência**: `operator-kit/.../OperatorPushSettings.vue`, `useWebPush.ts`.

### H04 · Dizer a versão ao suporte
- Rodapé da home com a versão do build. ENTENDER. `hub-nuxt/app/app.vue`.

### C01 · Entrar com senha
- **Quem**: gerente; qualquer operador em dispositivo que não é estação. **Onde**: `OperatorLogin` (tela cheia), cada app.
- **Gatilho**: dispositivo novo / sessão expirada (401/403 `not_authenticated`). Distingue "servidor não respondeu" (C14) de "sessão morta".
- **Entrada**: digitar usuário e senha. **Padrão**: AUTORIZAR. **Evidência**: `OperatorLogin.vue`, `useOperatorSession.ts`, `kds-nuxt/app/app.vue`.

### C02 · Transformar este dispositivo em estação
- **Quem**: gerente com senha. **Onde**: oferta `OperatorStationSetup` (escolher terminal; avisa outros dispositivos/caixa aberto no mesmo balcão). Montado só no PDV.
- **Objetivo real**: que o dispositivo abra de manhã pedindo só PIN/crachá. Sem isso, a tela da cozinha precisa de senha de gerente para chegar ao PIN.
- **Falta**: o KDS não monta a oferta; um tablet de cozinha só vira estação se alguém abrir o PDV nele.
- **Padrão**: CONFIGURAR. **Evidência**: `OperatorStationSetup.vue`, `useStationProvision.ts`, `pos-nuxt/app/components/PosOperatorShell.vue`.

### C03 · Assumir a tela (crachá ou PIN)
- **Quem**: operador. **Onde**: `OperatorLock` cobre a tela inteira quando ninguém está identificado (sem interruptor: sem pessoa, não se opera). Crachá (leitor HID digita 12 hex + Enter, capturado no documento, decide por cadência) ou escolher o nome na lista numerada + PIN no pad. Lista restrita a quem tem a permissão do app (`backstage.operate_kds`).
- **Gatilho**: tela travada. Várias/turno · segundos.
- **Entrada**: ler código / escolher + digitar número. **Efeito**: capability do app abre para essa pessoa; ações gravam `actor`. **Caminho**: 1 leitura ou 2 gestos. **Mínimo**: 1 leitura de crachá.
- **Padrão**: AUTORIZAR. **Evidência**: `OperatorLock.vue`, `OperatorIdentify.vue`, `useIdentityCapture.ts`, `presentation/operatorLock.ts`.

### C04 · Travar / trocar de operador
- Item do rail com o nome; travar fecha a capability só deste app (sessão compartilhada segue). Não há auto-trava por ociosidade no kit (só o PDV tem lock próprio). AUTORIZAR. `OperatorRail.vue`, `useOperatorLock.ts::lock`.

### C05 · Trocar o próprio PIN · C06 · PIN temporário obrigatório
- Pad em três passos (atual → novo → confirma); provar o atual é a autorização. Forçado após reset do gerente (`must_change`): não se opera antes. CONFIGURAR / AUTORIZAR. `OperatorPinChange.vue`, `OperatorLock.vue`.

### C07 · Matar crachá perdido
- Na própria trava: escolher-se + PIN → o crachá é revogado na hora. CORRIGIR. `OperatorLock.vue` ("Perdi meu crachá"), `useOperatorLock.ts`.

### C08 · Assinar exceção como gerente
- **Quem**: gerente, sobre a tela de outro operador (PDV, Gestor). Mesmo `OperatorIdentify` (crachá funciona); título é o ato ("Quem autoriza?"), deixa claro que o operador continua o mesmo; recusa autoassinatura; grava `approved_by`. Campo de nome livre só se a lista vier vazia. APROVAR. Não usado no KDS. `OperatorManagerAuth.vue`, `presentation/managerAuth.ts`.

### C09 · Avisos pessoais (sino)
- Contador discreto (9+), lista com log de acessos, suspeitos realçados na mesma lista; sem som, sem modal; SSE `user-<id>` + poll 60 s. Montado só no Gestor (`orders-nuxt`); KDS e home não têm. AVISAR. `NotificationBell.vue`, `useNotifications.ts`.

### C10 · Ligar push · C11 · Instalar o app
- Convite automático pelo `OperatorPwaRuntime` (instalação: caminho por sistema+navegador, ou nada; "Agora não" segura 1 semana; "Já instalei" 1 ano). Push: convite por app quando o app declara `push` — o KDS NÃO declara. CONFIGURAR. `OperatorPwaInstallInvite.vue`, `usePwaInstall.ts`, `installGuide.ts`, `OperatorPushInvite.vue`.

### C12 · Entrar na versão nova sem perder trabalho
- Sonda a cada 30 min e ao voltar do segundo plano; aplica sozinho só em rota liberada, sem razão de espera (`useOperatorReloadHold`) e ocioso; senão aviso para o operador. KDS: `idleReloadPaths: ["*"]` (pode recarregar em qualquer rota quando ocioso; finalizar pendente é enviado no `pagehide`). (sistema). `usePwaAutoUpdate.ts`, `presentation/pwaRuntime.ts`, `kds-nuxt/nuxt.config.ts`.

### C13 · Saber se o serviço aguenta
- Ponto no rail (neutro/âmbar/vermelho por limites do Admin) com memória/CPU do contêiner e idade da leitura; poll 45 s; some sem permissão. VIGIAR. `OperatorCapacityStatus.vue`, `presentation/capacity.ts`. Para o cozinheiro é ruído; é trabalho do gerente.

### C14 · Sem rede / servidor indisponível
- `OfflineBanner` (só offline), reconexão refaz fetch, `OperatorSessionUnavailable` ("Não consegui conferir seu acesso", único botão: tentar de novo). AVISAR. `OfflineBanner.vue`, `useConnectivity.ts`, `OperatorSessionUnavailable.vue`.

### C15 · Travar giro
- Item do rail só em dispositivo de toque com a API; recusa dita ("use o bloqueio de rotação do sistema"); preferência do dispositivo, reaplicada no boot. CONFIGURAR. `useOrientationLock.ts`.

### C16 · Voltar ao Shopman Apps / outro app
- Item do rail (janela do app instalado). No KDS o rail também tem "Estações" (voltar a K01). LOCALIZAR. `OperatorRail.vue`, `presentation/appLaunch.ts`.

### C17 · Tela acesa e cheia
- Wake Lock e tela cheia progressiva (kiosk) no KDS; falha silenciosa. (sistema). `useWakeLock.ts`, `useKioskMode.ts`.

---

## 2b. Quem usaria o KDS em TABLET e em CELULAR, e quantos tickets por tela

### O que um ticket precisa mostrar de relance (o núcleo)
Ordem de leitura real da bancada: **qual pedido → quanto tempo → o que fazer → o gesto**.
1. **Código chamável** (4–6 caracteres) — a âncora para conversar e chamar.
2. **Tempo contra a meta** — um número + cor (no prazo / atenção / atrasado). A barra de SLA e o chip de tempo dizem a mesma coisa; basta um.
3. **Itens: qty × nome** — inteiros, sem truncar.
4. **Observações e alergias** — inteiras, destacadas (é o que causa devolução).
5. **Estado + um gesto** (Iniciar → Finalizar; bloqueado com motivo).
Só quando muda o trabalho: Adicional, Teste, Cancelado, Entrega (embalagem diferente), Aguardando pagamento.
**Não precisa estar no card de preparo**: ícone de canal, nome do cliente, comanda riscada, "i" de detalhe, relógio com segundos no cabeçalho. Na **Saída** o núcleo muda: código + cliente (para chamar) + volumes + entrega/retirada + bloqueio + gesto; os itens ficam sob demanda.

### Tablet FIXO (montado na bancada ou na parede, 10–13", paisagem)
- **Cozinheiro de estação** (Lanches, Confeitaria, Café): K02–K10, K20. Mãos ocupadas, 0,5–2 m, toque com nó do dedo. Trabalha 1–2 pedidos por vez; precisa ver o próximo e a profundidade da fila. **4–6 tickets** (3 colunas × 2 linhas em ~1280 px úteis, densidade Padrão/Ampla). Mais que isso o olho não usa; a profundidade vai para a faixa "A fazer" e para um contador "+N na fila". Ticket com 6+ itens ocupa duas alturas: aceitar.
- **Expedidor no passe (Saída)**: K14–K19, K23. **Prontos para sair: 3–4 cards** com botão grande; **Em preparo: 5–8 linhas compactas** (código, tempo, estações faltando). O que importa é a coluna da direita; a esquerda é monitor.
- **Separador de encomendas (picking)**: K02, K12, K04; tickets mais longos (muitos itens), **2–4 tickets**, com aviso de estoque por item.

### Tablet NA MÃO (7–11", retrato, levado pelo chefe ou atendente)
- **Chefe de cozinha / gerente andando**: precisa de K14 (o que está atrasado em qualquer estação) e K06 (corrigir) — hoje não existe visão "todas as estações"; a coluna "Em preparo" da Saída é o mais próximo. **6–10 linhas** (lista, não grade): código, estação atrasada, tempo.
- **Atendente de salão / balcão**: K17 e K23 — achar o pedido do cliente e entregar. **4–6 cards** em 2 colunas.

### CELULAR (bolso, uma mão, tela que apaga)
- **Expedidor/atendente que leva o pedido à mesa ou à porta**: K17/K18 + K16 (conferir volumes). Lista de "Prontos para sair" com o mais antigo no topo; cada linha = código + cliente/mesa + volumes + botão "Entregar". **3–5 linhas** visíveis; só o primeiro expandido com itens.
- **Cozinheiro de estação pequena sem tablet** (barista, Lanches que hoje recebe papel): K02–K04 da própria estação. **1 ticket em foco + 2–3 linhas de fila** ("próximo", depois "depois"); um botão na zona do polegar. Exige **vibração/push**, porque a tela do celular apaga e o som do navegador não toca com a tela apagada — o KDS não declara push hoje.
- **Gerente fora da cozinha**: só alerta de atraso (push), não quadro. O trabalho é "ser avisado quando passar da meta", não vigiar.
- **Entregador**: não usa o KDS (quem despacha é o expedidor; troco e maquininha são do Gestor).

### Parede/TV (24"+, a 3–6 m)
- **Painel de retirada** (K24): **12–24 códigos**, só código e coluna. Já correto.
- **Quadro de estação em TV** (cozinha grande): 6–8 tickets em Ampla; só leitura, o gesto fica num tablet pequeno ou no leitor de código.

Regra de densidade que sai disso: **o número de tickets por tela é fixado pela capacidade de atenção (≈ 4–6 pedidos simultâneos numa estação), não pelos pixels**. Tela maior aumenta a distância de leitura (letra maior), não a contagem. O excedente vira número ("+7 na fila") e agregado ("A fazer"), nunca cards minúsculos.

---

## 3. Padrões neste app

1. **Um ciclo, várias portas, mesmo ato**: concluir ticket = K04 (estação de tela), K15 Saída, K15 PDV, K15 leitor, e o "Marcar pronto" do Gestor (`close_open_tickets`, `via=order_advanced`). A saída do pedido = K17/K18 no KDS e `advance_order` no Gestor (mesma implementação). O núcleo AVANÇAR é um só; a tela é só a porta.
2. **Todo ato irreversível ganha "tempo para errar"**: armar 900 ms (K03→K04), desfazer 5 s (K05), reabrir 30 min (K06). Mas Entregar/Despachar (K17/K18), os atos com o cliente na frente, não têm nenhum desfazer.
3. **Bloqueio aparece onde a decisão é tomada em um lugar e não no outro**: a Saída mostra o bloqueio de pagamento ANTES do toque (K19); o preparo só descobre DEPOIS, num toast, 5 s depois (K11). Mesma regra (`payment_gate`), dois comportamentos.
4. **Ciência obrigatória como gesto** (K10, K20 "Visto"): operador não decide, prova que viu. Proposta de rótulo: ACUSAR-RECEBIMENTO. Um é por ticket e servidor (cancelamento), o outro é por dispositivo e local (Visto) — duas telas da mesma estação discordam sobre o que foi visto.
5. **O sistema pede o que poderia saber**: estação (K01) poderia vir do dispositivo provisionado; densidade (K22) e som (K21; `sound_enabled` existe no modelo e não é lido) poderiam vir da estação; o detalhe (K07) repete o card.
6. **Informação de decisão longe da decisão**: a faixa "A fazer" (K08) não diz o que já está pronto na vitrine; a Saída não mostra as notas do pedido na conferência (K16); "abra no Gestor" sem link (K19); quem pegou o pedido (K03) não aparece.
7. **Planejar dentro da tela de executar**: prévia de data futura (K09) no quadro da bancada é trabalho da Produção/Encomendas; ocupa cabeçalho de quem só faz o de hoje.
8. **Chrome igual para dispositivos diferentes**: capacidade (C13), giro (C15) e versão (H04) são do gerente/montador e aparecem para o cozinheiro; push (C10) e sino (C09), que fariam sentido no celular, faltam justamente no KDS.
9. **Provisionamento só no PDV** (C02): o tablet da cozinha, o dispositivo mais "estação" da casa, não tem caminho próprio para virar estação.
10. **Hub é um passo de navegação sem informação**: H01 não diz onde está a urgência (pedido esperando, ticket atrasado); para quem tem um único app, é um toque desnecessário.

---

## 4. Cobertura (telas e estados)

| Rota / estado | O que é | Dispositivo que faz sentido | Por quê |
|---|---|---|---|
| KDS `/` lista de estações | K01 | tablet (montagem) | uso 1×; no dia a dia deveria pular |
| KDS `/` vazio "Nenhuma estação configurada" | erro de cadastro | desktop (Admin) | quem resolve é o gestor |
| KDS `/<ref>` preparo, grade com próximo destacado | K02–K04 | tablet fixo; celular só p/ estação pequena | leitura à distância, mãos ocupadas |
| card estado pendente / em preparo (armando) / finalizando com Desfazer / bloqueado por cancelamento / prévia | K03–K05, K09, K10 | tablet fixo | gesto no mesmo ponto |
| faixa "A fazer" | K08 | tablet fixo; TV | lote |
| cartões vermelhos de cancelamento | K10 | tablet fixo | ciência imediata |
| seletor de data (prévia, somente leitura) | K09 | desktop/tablet do chefe | planejamento |
| diálogo detalhe do pedido | K07 | celular (no tablet é redundante) | card já completo |
| diálogo "Concluídos recentes" | K06 | tablet | correção rara |
| busca + "Nenhum pedido para X" + Limpar busca | K23 | tablet do passe / celular | cliente perguntando |
| vazio "Tudo em dia" (som ligado/desligado + "Ligar o som") / "Nada agendado" | K02/K21 | tablet fixo | diz se vai avisar |
| botão som (ativo / desligado / bloqueado) + "Visto" | K20/K21 | tablet fixo | ruído da cozinha |
| densidade (3 níveis) | K22 | tablet (montagem) | derivável |
| estação removida (404) | K25 | tablet | volta à lista |
| sem conexão com cache / sem conexão sem cache | K25 | todos | honestidade |
| KDS `/<ref>` Saída: "Em preparo" + "Prontos para sair" | K14–K19 | tablet fixo no passe; lista no celular do atendente | monitor + gesto |
| card Saída: pronto / bloqueado (rótulo+motivo) / prévia / itens expandidos | K16–K19 | tablet / celular | conferir e entregar |
| card Em preparo: chips por estação, "Pronto" da estação sem tela, papel não imprimiu | K14/K15 | tablet do passe | cobrar estação |
| Saída vazia | K14 | tablet | — |
| banner pedido de teste (preparo e Saída) | K13 | todos | segurança |
| KDS `/pickup` painel público (ao vivo / atualiza sozinho) | K24 | TV de parede | cliente a distância |
| rotas antigas `/estacao/*`, `/cliente`, `/retirada`, `/expedicao` → 301 | bookmarks de kiosk | — | — |
| Hub: grade de tiles | H01 | celular/tablet/PC | índice |
| Hub: vazio sem apps | H02 | celular | operador novo |
| Hub: sessão expirou / estação travada / sem acesso / indisponível (+Tentar de novo) | H02/C14 | todos | cada causa sua saída |
| Hub: avisos deste dispositivo + versão | H03/H04 | celular (push) | config pessoal |
| Kit: login com senha (página) | C01 | todos | primeiro acesso |
| Kit: trava (lista + PIN, crachá) | C03 | tablet/PC de estação | troca de pessoa |
| Kit: troca de PIN voluntária / forçada | C05/C06 | tablet/PC | raro |
| Kit: "Perdi meu crachá" | C07 | tablet/PC | raro |
| Kit: autorização do gerente (diálogo) | C08 | PDV/Gestor (desktop/tablet) | exceção no balcão |
| Kit: iniciar este dispositivo (oferta de estação) | C02 | tablet/PC de balcão (hoje só PDV) | montagem |
| Kit: sessão indisponível | C14 | todos | redeploy |
| Kit: faixa offline | C14 | todos | wi-fi instável |
| Kit: convite de instalação / de push | C10/C11 | celular/tablet | 1× |
| Kit: aviso de versão nova / troca automática no ocioso | C12 | todos | deploy |
| Kit: rail (voltar ao hub, Estações, operador/travar, capacidade, tema, giro) | C04/C13/C15/C16 | tablet/PC; no celular vira gaveta | chrome comum |
| Kit: sino de avisos + log de acessos (só Gestor) | C09 | celular/desktop | pessoal |
