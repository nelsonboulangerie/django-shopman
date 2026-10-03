# PDV: engenharia reversa por função

App: `surfaces/pos-nuxt` (Nuxt) + backend `shopman/backstage/api/operations.py` (views POS*, Operator*, DayClosing), `shopman/backstage/projections/{pos,preorders,cash_session,closing,pos_agent}.py`, `shopman/backstage/services/{pos,closing,pos_hardware,pos_terminal}.py`, `shopman/shop/services/{pos,pos_intent,pos_edit_session,pos_sales_mode,weighed_sale,counter_takeover,operator_orders}.py`, `packages/cashman`, `packages/orderman`.

Rotas: `/` (quadro de comandas → venda → pagamento → resultado, tudo na mesma página), `/session` (antessala do caixa), `/session/report` (leituras X/Z), `/session/closing` (fechamento do dia), `/preorders` e `/preorders/[ref]` (encomendas), `/display` (tela do cliente). Modos especiais de `/`: `?edit=<ref>` (editar encomenda), `?redo=<ref>` (cancelar e refazer), `?new=order` (nova encomenda).

Papéis no código: operador de balcão (`cashman.operate_pos`), gerente (`backstage.perform_closing`, `cashman.adjust_shift`, aprovador por PIN/crachá), auditor (`can_audit_cash`), gestor de operadores (`cashman.manage_operators`), quem lê pedidos (`shop.manage_orders`).

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| P01 | Transformar este computador em estação do balcão | gestor de operadores | PC do balcão | instalação / troca de máquina | raríssimo (1×/dispositivo) | dias | CONFIGURAR, AUTORIZAR |
| P02 | Dizer quem está operando (PIN/crachá) | atendente, gerente | estação | começo de turno, troca de pessoa, tela travada | 5–30×/dia | segundos | AUTORIZAR |
| P03 | Travar o terminal ao sair | atendente / sistema | estação | sair do balcão; ociosidade do dispositivo | 10–40×/dia | segundos | AUTORIZAR |
| P04 | Trocar PIN / avisar crachá perdido | atendente | estação | PIN esquecido, crachá sumiu | raro | minutos | AUTORIZAR, CORRIGIR |
| P05 | Saber se impressora/gaveta/agente funcionam e consertar | atendente, gerente | estação (rail) | papel não saiu, gaveta não abriu | 0–3×/dia | minutos | VIGIAR, CORRIGIR |
| P06 | Ligar a tela virada para o cliente | atendente | PC + 2º monitor | começo do dia | 1×/dia | minutos | CONFIGURAR |
| P10 | Abrir o caixa com o fundo de troco | atendente/gerente | estação, antessala | primeira venda do dia sem turno | 1–2×/dia | minutos (cliente pode estar esperando) | REGISTRAR-QUANTIDADE |
| P11 | Tirar dinheiro da gaveta (sangria) | atendente + gerente | antessala | gaveta cheia, pagar fornecedor, cofre | 1–4×/dia | minutos | REGISTRAR-QUANTIDADE, APROVAR |
| P12 | Pôr dinheiro na gaveta (suprimento) | atendente | antessala | reforço de troco | 0–2×/dia | minutos | REGISTRAR-QUANTIDADE |
| P13 | Pedir troco (cédulas menores) | atendente | antessala | acabaram as notas pequenas | 0–3×/dia | minutos | AVISAR |
| P14 | Entregar o troco pedido (troca net zero) | gerente / quem traz | antessala | pedido de troco pendente | 0–3×/dia | minutos | REGISTRAR-QUANTIDADE, APROVAR |
| P15 | Desistir de um pedido de troco | atendente | antessala | não precisa mais | raro | minutos | CORRIGIR |
| P16 | Abrir a gaveta sem venda / testar a gaveta | atendente | antessala | conferir, trocar nota, testar | 0–5×/dia | segundos | REGISTRAR (rastro) |
| P17 | Destravar o balcão com a gaveta aberta | atendente / gerente | venda | sensor diz "aberta" ao iniciar venda | várias/dia (normal: fechar a gaveta) | segundos, cliente esperando | AUTORIZAR, AVISAR |
| P18 | Devolver o dinheiro de venda cancelada fora do balcão | atendente + gerente | antessala ("Precisa de você") | cancelamento feito no Gestor | raro | minutos, cliente às vezes esperando | CORRIGIR, APROVAR |
| P19 | Registrar estorno feito na maquininha | atendente + gerente | antessala | encomenda paga no cartão ficou mais barata | raro | minutos | CORRIGIR, APROVAR |
| P20 | Receber o acerto de conta na casa | atendente | antessala | cliente veio pagar o que deve | raro–semanal | minutos, cliente esperando | REGISTRAR-QUANTIDADE |
| P21 | Ler o parcial do turno (X), os turnos fechados (Z), reimprimir comprovante | gerente, atendente | antessala → relatório | dúvida, conferência, fim do dia | 1–3×/dia | horas | ENTENDER, EMITIR |
| P22 | Fechar o caixa contando às cegas | gerente | antessala | fim do expediente | 1–2×/dia | minutos | CONFERIR, REGISTRAR-QUANTIDADE |
| P23 | Fechar o dia contando as sobras | gerente | antessala → fechamento | fim do expediente | 1×/dia | horas | CONFERIR, REGISTRAR-QUANTIDADE |
| P30 | Abrir ou retomar uma comanda | atendente | estação, quadro | cliente chega / volta à mesa / pede mais | 100–400×/dia | segundos, cliente esperando | LOCALIZAR, COMPOR |
| P31 | Lançar produto (busca, código de barras, grade, cartão de escolha) | atendente | venda | cliente pede | 500–2000×/dia | segundos, cliente esperando | COMPOR |
| P32 | Lançar peça pesada (valor da etiqueta ou peso) | atendente | venda | queijo/fracionado etiquetado | 5–50×/dia | segundos | COMPOR, REGISTRAR-QUANTIDADE |
| P33 | Lançar produto com escolhas (sabor, adicionais) | atendente | venda | produto com grupos de opção | 10–100×/dia | segundos | COMPOR |
| P34 | Corrigir quantidade / remover item / desfazer | atendente | venda (linhas) | cliente mudou de ideia, erro de toque | 50–200×/dia | segundos | CORRIGIR |
| P35 | Anotar observação do item para a cozinha | atendente | venda (linhas) | "sem cebola" | 5–50×/dia | segundos | COMPOR |
| P36 | Dar desconto num item (% ou R$, com motivo) | atendente (+ gerente acima do limite) | venda (linhas) | cortesia, fidelidade, qualidade | 0–20×/dia | segundos | COMPOR, APROVAR |
| P37 | Mandar itens para a cozinha / desfazer o envio | atendente | venda (linhas) | itens de preparo lançados | 30–200×/dia | segundos | AVANÇAR |
| P38 | Ver o item na cozinha / dar "Pronto" de estação sem tela | atendente | venda (linhas) | cliente pergunta "falta muito?" | 10–50×/dia | segundos | VIGIAR, AVANÇAR |
| P39 | Dividir, transferir ou juntar comandas | atendente | venda | mesa divide, cliente troca de mesa | 0–20×/dia | segundos | COMPOR, CORRIGIR |
| P40 | Renomear / liberar comanda | atendente | venda (barra) | número errado, comanda abandonada | 0–10×/dia | segundos | CORRIGIR |
| P41 | Identificar o cliente (buscar, criar, resolver conflito, unificar) | atendente | venda / pagamento | fidelidade, nota com CPF, encomenda, entrega | 30–150×/dia | segundos, cliente esperando | LOCALIZAR, CORRIGIR |
| P42 | Dizer como o cliente recebe (retirada/entrega, endereço, taxa) | atendente | venda (F7) | encomenda, telefone, delivery próprio | 5–40×/dia | segundos–minuto | COMPOR |
| P43 | Dizer quando (data e janela) e montar encomenda | atendente | venda (F8, assistente) | cliente encomenda para outro dia | 5–40×/dia | minuto, cliente no telefone/balcão | PLANEJAR, COMPOR |
| P44 | Converter encomenda em venda de balcão | atendente | venda | cliente decide levar agora | raro | segundos | CORRIGIR |
| P45 | Dar desconto na venda inteira | atendente (+ gerente) | pagamento (F9) | cortesia, acordo | 0–20×/dia | segundos | COMPOR, APROVAR |
| P46 | Receber o pagamento (formas, cédulas, exato, troco) | atendente | pagamento | cliente vai pagar | 100–400×/dia | segundos, cliente esperando | REGISTRAR-QUANTIDADE |
| P47 | Dividir a conta entre pessoas | atendente | pagamento (F10) | "cada um paga o seu" | 0–20×/dia | segundos | COMPOR |
| P48 | Cobrar na maquininha e confirmar | atendente | pagamento | forma crédito/débito | 50–250×/dia | segundos | CONFERIR |
| P49 | Cobrar por Pix (QR) ou link e esperar | atendente | pagamento / resultado | forma Pix ou link | 20–150×/dia | segundos–minutos | VIGIAR |
| P50 | Escolher quando cobrar (agora, na retirada, na entrega, link) | atendente | pagamento | encomenda / entrega | 5–40×/dia | segundos | COMPOR |
| P51 | Responder à nota fiscal (CPF, impressa, e-mail) | atendente | pagamento | "CPF na nota?" | 100–400×/dia | segundos | EMITIR |
| P52 | Validar a venda / recuperar fechamento incerto | atendente | pagamento | total coberto | 100–400×/dia | segundos | AVANÇAR, CORRIGIR |
| P53 | Entregar troco e papéis, começar a próxima | atendente | resultado | venda fechada | 100–400×/dia | segundos | EMITIR, AVANÇAR |
| P54 | Cancelar venda recém-fechada (≤5 min) | atendente + gerente | resultado / últimas vendas | erro, cliente desistiu | 0–5×/dia | segundos, cliente esperando | CORRIGIR, APROVAR |
| P55 | Saber se a nota autorizou e reimprimir/reenviar/reprocessar | atendente | últimas vendas | cliente pede DANFE, nota falhou | 5–30×/dia | minutos | VIGIAR, EMITIR |
| P56 | Emitir nota que a regra não emitiu | atendente + gerente | últimas vendas | cliente volta pedindo nota | raro | minutos, cliente esperando | EMITIR, APROVAR |
| P57 | Ver a venda na tela virada ao cliente | cliente | 2º monitor | venda em curso | toda venda | contínuo | VIGIAR |
| P60 | Ver o que a casa prometeu (semana/dia, a receber, sem via) | atendente, gerente | encomendas | começo do turno, véspera | 2–10×/dia | horas | VIGIAR, PLANEJAR |
| P61 | Achar a encomenda de quem chegou | atendente | encomendas (busca) | cliente no balcão "vim buscar" | 5–60×/dia | segundos, cliente esperando | LOCALIZAR |
| P62 | Receber o saldo e entregar a encomenda | atendente | detalhe da encomenda | cliente no balcão, encomenda pronta | 5–60×/dia | segundos, cliente esperando | AVANÇAR, REGISTRAR-QUANTIDADE |
| P63 | Saber das encomendas de entrega em endereço | atendente | encomendas | consulta | 0–20×/dia | minutos | VIGIAR (saída é no Gestor) |
| P64 | Mudar a data/janela de uma encomenda | atendente | detalhe | cliente liga para mudar | 0–10×/dia | minutos, cliente no telefone | PLANEJAR, CORRIGIR |
| P65 | Mudar itens de uma encomenda | atendente (+ gerente se paga ficar mais barata) | venda em modo edição | cliente liga para mudar | 0–10×/dia | minutos | CORRIGIR, APROVAR |
| P66 | Cancelar encomenda / cancelar e refazer | atendente (+ gerente se paga) | detalhe | cliente desiste / nota já emitida | raro | minutos | CORRIGIR, APROVAR |
| P67 | Imprimir Via Pedido (lote do dia ou uma) | atendente | encomendas / detalhe / resultado | preparar separação | 1–5×/dia (lote), N unitárias | horas | EMITIR |
| P68 | Comentar no histórico da encomenda | atendente | detalhe | combinado com cliente | raro | minutos | REGISTRAR |
| P70 | Dar "Pronto" lendo o QR do ticket impresso da cozinha | atendente | qualquer tela, leitor HID | prato chegou da estação sem tela | 10–100×/dia | segundos | AVANÇAR |
| P71 | Imprimir pela bobina local (agente) | sistema / atendente | estação | todo papel | toda venda com papel | segundos | EMITIR (infra) |

59 trabalhos.

---

## 2. Fichas

### Estação e identidade

**P01 · Transformar este computador em estação do balcão**
- Quem: gestor com `cashman.manage_operators`. Onde: o próprio dispositivo (PC/tablet do balcão), uma vez.
- Gatilho: instalação, troca de máquina, revogação. Frequência raríssima; urgência dias; cliente não espera.
- Objetivo real: o dispositivo passa a ser reconhecido como "o balcão X" (cookie HttpOnly durável), para que operadores entrem só com PIN/crachá.
- Info mínima: qual terminal (gaveta) este dispositivo é. Falta: nada relevante.
- Entrada: senha do gestor + escolher terminal de lista curta.
- Efeito: estação vinculada a `cashman.Terminal`; revogável no Admin. Reversível sim. Custo do erro: médio (vendas caem na gaveta errada).
- Exceções: dispositivo sem estação mostra tela de senha de gestor todo dia.
- Caminho hoje: login com senha → setup de estação → escolher terminal. Mínimo: 2 passos (autenticar, escolher). Insubstituível: escolher o terminal.
- Fronteira: Admin (terminais, dispositivos) → PDV.
- Padrão: CONFIGURAR + AUTORIZAR.
- Evidência: `api/operations.py:StationProvisionView`, `components/PosOperatorShell.vue`.

**P02 · Dizer quem está operando (PIN/crachá)**
- Quem: atendente/gerente. Onde: estação; overlay do kit (`OperatorLock`).
- Gatilho: tela travada (início, auto-lock, troca de pessoa). 5–30×/dia; segundos; muitas vezes com cliente esperando.
- Objetivo: cada venda/movimento carrega o autor certo.
- Info mínima: lista de quem pode operar aqui (cards elegíveis) ou leitura do crachá. Sobra: nada. Falta: nada.
- Entrada: tocar o nome + PIN, ou passar crachá (HID com cadência de máquina).
- Efeito: sessão de operador (compartilhada por todos os apps do domínio). Reversível. Custo baixo/médio (venda no nome errado).
- Exceções: antes do destravamento toda leitura dá 403 `station_locked` (a tela não pode dizer "sem rede"); PIN errado; crachá perdido (P04).
- Caminho hoje: 2–5 toques (nome + 4–6 dígitos) ou 1 gesto (crachá). Mínimo: 1 (crachá). Insubstituível: provar identidade.
- Fronteira: kit compartilhado com Gestor/KDS/Produção.
- Padrão: AUTORIZAR. Evidência: `operator-kit` `useOperatorLock`, `OperatorUnlockView`, `PosOperatorShell.vue`.

**P03 · Travar o terminal ao sair**
- Quem: atendente; ou automático. Gatilho: sair do balcão / ociosidade do DISPOSITIVO (nenhum app de operador tocado por `auto_lock_seconds`). Adiado durante pagamento/Pix aguardando.
- Objetivo: ninguém vende no nome de outro.
- Entrada: 1 toque (Travar no rail) ou nada.
- Efeito: `logout` da sessão de operador (todos os apps). Reversível (P02). Custo baixo.
- Exceções: auto-lock não dispara com PDV fora da vista; ao voltar à vista confere o prazo. Display do cliente não alimenta o relógio.
- Mínimo: 0 passos (automático). Padrão: AUTORIZAR. Evidência: `composables/usePosAutoLock.ts`, `pages/index.vue` (`paymentHold`).

**P04 · Trocar PIN / avisar crachá perdido**
- Quem: atendente (próprio), gerente (reset). Raro; minutos.
- Objetivo: credencial volta a ser confiável. Entrada: PIN atual + novo; ou "perdi meu crachá" (revoga ativamente).
- Efeito: credencial alterada/revogada. Custo médio (crachá perdido em mãos erradas autoriza gerente).
- Caminho: kit (dialogs). Padrão: AUTORIZAR, CORRIGIR. Evidência: `OperatorPinChangeView`, `OperatorPinResetView`, `OperatorBadgeLostView`.

**P05 · Saber se impressora/gaveta/agente funcionam e consertar**
- Quem: atendente; gerente. Onde: card de saúde no rail (popover).
- Gatilho: papel não saiu, gaveta não abriu, badge vermelho. Sonda do agente ao montar + 60s.
- Objetivo: o periférico volta a funcionar ou o operador sabe o desvio.
- Info mínima: o que está quebrado (impressora/gaveta/agente) e o próximo passo. A tela já promove a sonda local sobre a config do servidor; ausente = neutro.
- Entrada: confirmar (testar de novo, reiniciar agente, abrir config no Admin).
- Efeito: nenhum dado de negócio. Custo do erro baixo.
- Caminho hoje: rail → popover → ação. Mínimo: aviso aparece sozinho na hora da falha (já existe para DANFE/recibo via toast) + 1 toque.
- Padrão: VIGIAR, CORRIGIR. Evidência: `components/PosTerminalHealth.vue`, `presentation/terminalHealth.ts`, `composables/useAgentHealth.ts`, `projections/pos_agent.py`.

**P06 · Ligar a tela virada para o cliente**
- Quem: atendente, 1×/dia. Onde: abre segunda janela do MESMO navegador (BroadcastChannel) para arrastar ao monitor do cliente. Só funciona em desktop com 2 monitores.
- Objetivo: cliente vê itens/total/QR. Entrada: 1 toque no rail + arrastar a janela.
- Exceções: pop-up bloqueado (toast com instrução). Tablet: impossível (sem segunda janela/monitor).
- Mínimo: 0 (abrir sozinho na estação que declara monitor do cliente). Padrão: CONFIGURAR. Evidência: `useCustomerDisplayWindow`, `PosDisplayPublisher.vue`, `pages/display.vue`.

### Caixa (antessala `/session`)

**P10 · Abrir o caixa com o fundo de troco**
- Quem: quem chega primeiro (operar POS). Onde: antessala; venda sem turno redireciona para `/session?open=1` com o campo focado.
- Gatilho: primeira venda do dia. 1–2×/dia. Cliente pode estar esperando.
- Objetivo: dizer quanto dinheiro está na gaveta no início, para o livro.
- Info mínima: sugestão do fundo configurado no terminal (`default_float_q`, nunca o contado de ontem: cego). Sobra: nada. Falta: nada.
- Entrada: digitar valor (ou tocar a sugestão) ou contar por cédula (contador opcional) + Enter.
- Efeito: turno aberto na GAVETA (`cashman`, `float_in`); vai direto à venda. Reversível não (vira linha do livro). Custo médio (diferença no fechamento).
- Exceções: valor ilegível bloqueia; vários dispositivos no mesmo balcão (aviso "o caixa já abriu").
- Caminho hoje: redireciona + digitar + Enter (3 gestos). Mínimo: 1 (confirmar a sugestão). Insubstituível: confirmar o valor.
- Fronteira: venda (bloqueada até aqui) ↔ livro do caixa.
- Padrão: REGISTRAR-QUANTIDADE. Evidência: `pages/session/index.vue` (`submitOpen`), `services/pos.py:open_cash_shift`, `presentation/cash.ts:requiresOpenShiftForSale`.

**P11 · Tirar dinheiro da gaveta (sangria / "Saída de caixa")**
- Quem: atendente + 2ª assinatura de gerente (qualquer valor). Antessala, card "Saída".
- Gatilho: gaveta cheia, pagamento em dinheiro a fornecedor, cofre. 1–4×/dia; minutos.
- Objetivo: dinheiro saiu com destino registrado.
- Info mínima: valor + para onde foi (motivo em botões da capability). Falta: nada.
- Entrada: valor, tocar motivo (ou digitar), PIN/crachá do gerente; gaveta abre pelo agente.
- Efeito: `cash_out` no livro com `approved_by`; comprovante imprimível. Irreversível (corrige com suprimento). Custo alto (desfalque).
- Exceções: servidor recusa `manager_approval_required`, diálogo de gerente sobe e reenvia a mesma ação; PIN errado reabre.
- Caminho: card → valor → motivo → confirmar → gerente → (gaveta). Mínimo: 3 (valor, motivo, assinatura).
- Padrão: REGISTRAR-QUANTIDADE + APROVAR. Evidência: `session/index.vue` (`submitMovement`, `managerIntent`), `services/pos.py:register_cash_movement`, `POSMovementView`.

**P12 · Pôr dinheiro na gaveta ("Entrada de caixa")**
- Mesmo diálogo de P11, tipo entrada; sem PIN. Efeito `cash_in`. Mínimo 2 (valor, motivo). Padrão REGISTRAR-QUANTIDADE. Evidência: idem.

**P13 · Pedir troco**
- Quem: atendente. Gatilho: faltam cédulas pequenas. 0–3×/dia.
- Objetivo: alguém traz troco ao balcão (ninguém sai com dinheiro pelo corredor).
- Info mínima: valor + cédulas desejadas (opcional) + nota. Entrada: valor, tocar denominações, texto curto.
- Efeito: pedido pendente (alerta), NÃO mexe no livro (net zero). Reversível (P15). Custo baixo.
- Mínimo: 1 (valor). Padrão: AVISAR. Evidência: `services/pos.py:request_change`, `presentation/cash.ts` (seção Pedido de troco).

**P14 · Entregar o troco pedido**
- Quem: quem trouxe (gerente) assina. Gatilho: pendência em "Precisa de você".
- Objetivo: a troca aconteceu, com duas pessoas.
- Entrada: confirmar + PIN/crachá do gerente. Efeito: pedido servido, alerta resolvido; gaveta abre; sem efeito no esperado.
- Mínimo: 1 toque + assinatura. Padrão: CONFERIR + APROVAR. Evidência: `serve_change_request`, `POSChangeRequestServeView`.

**P15 · Desistir de um pedido de troco**
- Confirmação POR pedido. Efeito: cancelado. Padrão CORRIGIR. Evidência: `cancel_change_request`.

**P16 · Abrir a gaveta sem venda / testar a gaveta**
- Quem: atendente. Gatilho: trocar nota, conferir; teste na instalação.
- Objetivo: abrir deixando rastro (único ato de gaveta sem outra linha no livro).
- Entrada: motivo (botões "Troco", "Conferência" ou texto). Teste: sonda a fila + abre "Teste de gaveta" (olho do operador confirma).
- Efeito: linha de abertura no livro. Custo baixo. Mínimo: 1 (motivo). Padrão: REGISTRAR. Evidência: `session/index.vue` (`openDrawer`, `testDrawer`), `useCounterAgent.ts`, `register_drawer_opening`, `report_drawer_blind`.

**P17 · Destravar o balcão com a gaveta aberta**
- Quem: atendente (fechando a gaveta); gerente só na exceção (gaveta emperrada, sensor morto).
- Gatilho: ao INICIAR venda (abrir comanda ou primeiro item sem comanda) o sensor diz "aberta". Nunca no meio de venda.
- Objetivo: criar o hábito de fechar a gaveta; o mundo físico destrava.
- Info mínima: "a gaveta está aberta". Entrada: fechar a gaveta (0 toques); exceção: PIN gerente.
- Efeito: episódio no livro (`closed`/manager/dismiss/sensor_lost), aviso "gaveta aberta há N min" ao gerente na hora morta (1 aviso por episódio).
- Exceções: sensor não calibrado (sem trava), sensor perdido (exceção com gerente). Fechar o diálogo desiste da venda que esperava.
- Mínimo: 0 (empurrar a gaveta). Padrão: AUTORIZAR + AVISAR; proposta de rótulo **TRAVA-FÍSICA** (o mundo real libera, não um toque). Evidência: `useDrawerLock.ts`, `useDrawerIdleWatch.ts`, `PosDrawerLockDialog.vue`, `POSCashDrawer*View`.

**P18 · Devolver o dinheiro de venda cancelada fora do balcão**
- Quem: atendente com gaveta aberta + gerente. Gatilho: card "Precisa de você" (cancelado pelo Gestor, de noite).
- Objetivo: o dinheiro sai da gaveta para o cliente com linha `refund`.
- Info mínima: pedido, valor, cliente. Entrada: confirmar + assinatura.
- Efeito: `refund` no turno aberto; pendência some. Custo alto. Mínimo: 1 + assinatura. Padrão: CORRIGIR + APROVAR. Evidência: `services/pos.py:refund_cash`, `projections/pos.py:_pending_cash_refunds`.

**P19 · Registrar estorno feito na maquininha**
- Gatilho: encomenda paga no cartão ficou mais barata (edição). O sistema não fala com a maquininha: o operador estorna lá e atesta aqui com PIN.
- Efeito: pendência resolvida, estorno registrado. Padrão: CORRIGIR + APROVAR. Evidência: `record_card_machine_refund`, `_pending_card_machine_refunds`.

**P20 · Receber acerto de conta na casa**
- Quem: atendente; sem PIN (entrada). Gatilho: cliente veio pagar o saldo ("em conta").
- Info mínima: cliente, saldo devido. Entrada: valor (pré-preenchido com o saldo) + forma (dinheiro/pix/crédito/débito/externo).
- Efeito: saldo baixa; em dinheiro entra no turno (gaveta abre). Custo médio. Mínimo: 2 (confirmar valor, forma).
- Exceção de desenho: só aparece como pendência na antessala; cliente no balcão de venda não tem esse caminho a partir do cadastro dele.
- Padrão: REGISTRAR-QUANTIDADE. Evidência: `settle_account`, `POSAccountSettleView`, `account_balances()`.

**P21 · Ler X/Z e histórico; reimprimir comprovante de movimento**
- Quem: atendente (X do seu balcão), gerente. Onde: `/session/report`.
- Objetivo: saber quanto entrou por forma e o que saiu, SEM ver o esperado da gaveta (cego).
- Info mínima: fundo, movimentos, vendas por método, (Z) contado. Falta: nada; sobra: nada (deliberadamente cego).
- Entrada: nenhuma (leitura); 2ª via de movimento só com agente.
- Exceções: 409 `pos_terminal_mismatch`/`pos_station_required` (balcão errado), dito como tal.
- Padrão: ENTENDER, EMITIR. Evidência: `pages/session/report.vue`, `projections/cash_session.py`, `PosCashReadingCard.vue`.

**P22 · Fechar o caixa contando às cegas**
- Quem: SÓ gerência (`can_close_day`); decisão do dono. Fim do expediente.
- Objetivo: registrar o que de fato está na gaveta; a diferença é calculada na retaguarda.
- Info mínima: nenhuma além da gaveta física. Entrada: contar (valor ou contador por cédula) + observação + confirmação que ECOA o valor.
- Efeito: turno fechado (`count`), venda bloqueada até nova abertura. Irreversível no PDV. Custo alto.
- Exceções: sem gerente presente a gaveta fica aberta e as vendas do dia seguinte caem no turno de ontem (risco documentado no código).
- Caminho: card → contar → confirmar → confirmar de novo. Mínimo: 2 (número, confirmar). Insubstituível: contar.
- Fronteira: → P23 (fim de dia encadeado) → P21.
- Padrão: CONFERIR + REGISTRAR-QUANTIDADE. Evidência: `services/pos.py:close_cash_shift`, `session/index.vue` (closing dialog), `PosDenominationCounter.vue`.

**P23 · Fechar o dia contando as sobras**
- Quem: gerente (`backstage.perform_closing`). Onde: `/session/closing` (PDV); antes no Admin.
- Gatilho: fim do dia. Objetivo: o que sobrou de produção da casa vira estoque de ontem (com validade) ou perda.
- Info mínima: lista do que a casa PRODUZ (ficha ativa), em ordem de nome (etiqueta). Antes de contar não mostra feito/vendido (cego); produção aberta aparece só como bloqueio.
- Entrada: contar um número inteiro por item, Enter avança; botão preso ao pé.
- Efeito: `DayClosing` + movimentos no Stockman (fica / vira perda pelo lote). Irreversível (1 por dia). Custo alto (estoque e D-1 errados).
- Exceções: produção pendente bloqueia (link à Produção na data da ordem mais velha); já fechado hoje.
- Caminho: 1 campo por SKU (~30). Mínimo: N contagens + 1 confirmar. Insubstituível: contar.
- Padrão: CONFERIR. Evidência: `pages/session/closing.vue`, `presentation/closing.ts`, `services/closing.py`, `projections/closing.py`.

### Venda

**P30 · Abrir ou retomar uma comanda**
- Quem: atendente. Onde: quadro (primeira tela de `/`).
- Gatilho: cliente chega (pega ficha/número), volta para pedir mais, vem pagar.
- Objetivo: amarrar o atendimento a um identificador físico (número da ficha) para não se perder.
- Info mínima: número/nome; estado (livre, em uso, disparado e não pago, selecionada). Já tem filtro por nome/ref e "próxima livre" de 1 toque.
- Entrada: digitar número (Enter), tocar card, ou "próxima livre". Enter com 1 card filtrado abre ele.
- Efeito: sessão Orderman aberta/retomada, autosave contínuo; trava de gaveta morde aqui. Reversível (liberar). Custo baixo.
- Exceções: comanda mudou em outro dispositivo (conflito, "Descartar minhas alterações e atualizar"); autosave falhou ("Não salvo"); canal pode exigir comanda para lançar (`tabRequiredForCart`) ou permitir venda direta sem comanda (venda comum neste balcão).
- Caminho hoje: F2/digitar/Enter (2) ou 1 toque. Mínimo: 0 quando a venda é direta (o 1º produto abre a venda) ou 1 (número da ficha).
- Fronteira: KDS (comanda disparada), tela do cliente.
- Padrão: LOCALIZAR + COMPOR. Evidência: `PosTabBoard.vue`, `presentation/tabBoard.ts`, `utils/posTabLifecycle.ts`, `services/pos.py:open_pos_tab/save_pos_tab`.

**P31 · Lançar produto**
- Quem: atendente. O gesto mais frequente do app.
- Gatilho: cliente pede. Objetivo: o item entra no pedido pelo preço do canal.
- Info mínima: nome, preço, disponível/esgotado/"sem caixa" (kit sem embalagem), quantos já estão no pedido (selo). Sobra: imagens grandes em densidade "Ampla". Falta: nada crítico.
- Entrada: (a) letra fora de campo inicia busca (search-as-you-type, sem acento, prefixo de palavra primeiro), Enter lança o 1º disponível e mantém foco; (b) leitor de código de barras = teclado (GTIN casa inteiro); (c) toque no tile; (d) cartão de escolha (`choice_group`) abre os irmãos; categorias/favoritos no rail.
- Efeito: linha nova ou soma (mesma assinatura de opções); autosave; tela do cliente atualiza. Reversível. Custo baixo.
- Exceções: esgotado/sem preço não entra; kit sem caixa inerte "Sem caixa"; trava de gaveta no 1º item de venda sem comanda.
- Caminho: 1 toque ou 2–4 teclas + Enter. Mínimo: 1 (bipar ou tocar).
- Padrão: COMPOR. Evidência: `PosProductGrid.vue`, `PosProductTile.vue`, `PosProductGroupTile.vue`, `presentation/catalog.ts`, `projections/pos.py:_load_products/_kits_without_box/_sold_out_skus`.

**P32 · Lançar peça pesada**
- Gatilho: queijo/fracionado pesado e etiquetado à mão. Objetivo: o valor da etiqueta vira PESO (qtd), preço continua o do kg.
- Info mínima: preço/kg; prévia do peso derivado. Entrada: digitar valor da etiqueta (padrão) ou peso (só com balança ligada, `weighed_weight_entry`).
- Efeito: linha com qtd em kg; servidor recalcula. Linha pesada não aceita +/− nem desconto em R$ (só %); para trocar: remover e lançar outra etiqueta.
- Mínimo: tocar produto + digitar valor + confirmar (3). Insubstituível: o número da etiqueta (ou leitura do código de balança, que não existe hoje).
- Padrão: COMPOR + REGISTRAR-QUANTIDADE. Evidência: `PosWeighedEntryDialog.vue`, `presentation/weighed.ts`, `shop/services/weighed_sale.py`.

**P33 · Lançar produto com escolhas**
- Gatilho: produto com `option_groups` (sabor obrigatório, adicionais com preço). Info: regra do grupo ("Escolha 1", "Opcional, até 2"), acréscimo, total ao vivo.
- Entrada: tocar opções, "Lançar" habilita com mínimos cumpridos. Efeito: linha "Croque (+ Ovo frito)"; servidor reprecifica.
- Mínimo: 1 toque no produto + 1 por grupo obrigatório + confirmar. Padrão: COMPOR. Evidência: `PosProductOptionsDialog.vue`, `presentation/productOptions.ts`, `shop/product_options`.

**P34 · Corrigir quantidade / remover item / desfazer**
- Quem: atendente. Onde: área de linhas da comanda.
- Info mínima: a linha certa (nome, qtd, total, se já foi à cozinha). Entrada: +/− na linha ativa; dígitos (teclado físico ou numpad da tela) substituem a qtd; zero/Backspace até 0/− em 1 pedem confirmação de remoção (sempre modal, decisão do balcão) e depois toast "Desfazer"; remoção em lote via seleção.
- Efeito: linha alterada (autoria registrada: "Lançado por/Editado por"). Remover linha já disparada não tira do fogão (aviso). Custo baixo/médio.
- Mínimo: 1 toque (+/−) ou 1 tecla; remoção 2 (pedir + confirmar).
- Padrão: CORRIGIR. Evidência: `PosCartPanel.vue` (`bump`, `askRemove`, `removeWithUndo`, `commitQty`), `presentation/numpad.ts`, `presentation/lineAuthorship.ts`.

**P35 · Anotar observação do item**
- Entrada: modo "Obs." do console ou "Observação" nos detalhes → diálogo de texto. Efeito: viaja ao KDS. Bloqueado no modo edição de encomenda (serviço não grava). Mínimo: 2 (abrir, digitar+salvar). Padrão: COMPOR. Evidência: `PosCartPanel.vue` (`noteDialog`).

**P36 · Dar desconto num item**
- Entrada: modo "Desc %" ou "Desc R$" (por unidade) do console; dígitos aplicam ao vivo; motivo num select (Cortesia/Fidelidade/Qualidade ou do contrato). Em seleção múltipla, o numpad vira desconto em lote.
- Regras: servidor descarta o % de linha quando desconto automático maior venceu ("maior desconto ganha"); acima do limite da loja pede gerente no Validar; preço digitado à mão foi removido.
- Efeito: selo na linha e na tela do cliente. Custo médio (margem). Mínimo: selecionar linha + modo + número + motivo (4).
- Padrão: COMPOR + APROVAR. Evidência: `PosCartPanel.vue` (`commitDiscount`), `presentation/lineDiscounts.ts`, `shop/services/pos.py:validate_manager_approval`.

**P37 · Mandar itens para a cozinha / desfazer envio**
- Gatilho: itens de preparo lançados numa comanda. Info mínima: quantos não enviados (badge no botão). Entrada: "Enviar" (F9) manda tudo não enviado; seleção envia linhas escolhidas; "Cancelar envio" por linha ou lote.
- Efeito: tickets no KDS (idempotente por `session_key`); desfazer cancela ticket e torna a linha re-disparável (reimpressão = cancelar + enviar). Custo médio (comida feita à toa).
- Mínimo: 1 toque. Ideal: automático conforme regra do canal (ex.: enviar ao salvar/ao pagar) para o que vai à cozinha.
- Padrão: AVANÇAR. Evidência: `services/pos.py:fire_pos_tab/cancel_fired_pos_tab_lines`, `presentation/kitchen.ts`, `PosCartPanel.vue` (`fireBar`).

**P38 · Ver o item na cozinha / dar "Pronto" de estação sem tela**
- Info: selo por linha (enviado, preparando, pronto, cancelado, divergência) via SSE `tabs`; card do ticket (estação, itens, hora, estado). Para estação sem tela, o card traz "Pronto" (mesma régua da Saída do KDS).
- Mínimo: olhar (0); pronto: 2 toques. Padrão: VIGIAR + AVANÇAR. Evidência: `PosKitchenTicketDialog.vue`, `projections/pos.py:_kitchen_status_by_line/_kitchen_tickets_by_line`.

**P39 · Dividir, transferir ou juntar comandas**
- Gatilho: "pagamos separado", cliente mudou de mesa, duas fichas viram uma. Config por canal (`tab_manipulation`).
- Info mínima: linhas da comanda, comandas abertas, sugestão de ref filho no dividir. Seleção começa VAZIA (escolher o que sai).
- Entrada: modo (Dividir/Transferir/Juntar), marcar linhas, destino. Efeito: linhas movidas com preço congelado; juntar libera a origem vazia. Custo baixo.
- Mínimo: 3 (modo, linhas, destino). Padrão: COMPOR/CORRIGIR. Evidência: `PosMoveLinesDialog.vue`, `presentation/moveLines.ts`, `services/pos.py:move_pos_tab_lines`.

**P40 · Renomear / liberar comanda**
- Renomear (número errado) e liberar (com confirmação) na barra de contexto. Efeito: `rename_pos_tab`, `clear_pos_tab`. Padrão CORRIGIR. Evidência: `PosTabHeader.vue`.

**P41 · Identificar o cliente**
- Quem: atendente. Onde: chip de cliente (F6), modal tela cheia, picker primeiro.
- Gatilho: fidelidade, CPF na nota, encomenda/entrega (obrigatório), conta na casa.
- Info mínima: resultados ricos (nome, telefone mascarado, último pedido); memória (favorito, último pedido, restrições, aniversário, alertas do balcão); padrões do cliente (nota, recibo) aplicáveis nesta venda.
- Entrada: digitar telefone/nome/CPF; escolher; ou criar com o MESMO formulário.
- Efeito: cliente na sessão; preço por faixa do cadastro passa a valer; "repetir último pedido"/"favorito" lançam itens.
- Exceções (5 casos nomeados): contato já é de outro cadastro (escolha explícita), mudança de contato do associado ("de X para Y"), dono desativado (liberar contato), vários intrusos (lista), valor órfão (dono sem nome); unificar dois cadastros da mesma pessoa. Na edição de encomenda o cliente é travado.
- Caminho: 2–4 (abrir, digitar, escolher). Mínimo: 1 (ler telefone/CPF e resolver sozinho quando é único).
- Padrão: LOCALIZAR + CORRIGIR. Evidência: `PosCustomerModal.vue`, `PosCustomerSearch.vue`, `presentation/customerDecision.ts`, `POSCustomer{Lookup,Search,Resolve,Merge,ContactRelease,Profile}View`.

**P42 · Dizer como o cliente recebe**
- Onde: chip "Recebimento" (F7), mesma caixa na venda e no pagamento. Só no modo Encomendas.
- Info mínima: retirada/entrega; se entrega: endereço (autocomplete Google, endereços salvos), número, complemento, instruções; taxa com ORIGEM explicada (distância/faixa/zona); exceção de taxa digitável.
- Efeito: taxa entra no total; janelas mudam; entrega pede cliente (telefone). Custo médio.
- Exceções: taxa só resolve na review (fora dela a caixa diz isso); pedido mínimo de entrega; identidade fiscal da entrega (CPF obrigatório em certos casos).
- Mínimo: 1 toque (retirada) / endereço (entrega). Padrão: COMPOR. Evidência: `PosFulfillmentModal.vue`, `PosAddressAutocomplete.vue`, `services/pos.py:_require_delivery_*`.

**P43 · Dizer quando e montar a encomenda**
- Onde: chip "Quando" (F8; padrão afirmativo "Para hoje"); assistente da encomenda (etapas cliente → recebimento → endereço → data) quando a venda está no modo Encomendas ou vem de "Nova encomenda".
- Info mínima: datas que a casa opera, janelas do dia anotadas com a prontidão DESTE carrinho (gargalo, "pronto às"), limite de dias. Janela que vira impossível ao lançar item deixa o chip em conflito.
- Entrada: escolher data e janela de listas curtas.
- Efeito: `delivery_date/time_slot`; servidor recusa encomenda anônima (`customer_required_for_scheduled`) → chip de cliente pulsa.
- Mínimo: 2 (data, janela). Padrão: PLANEJAR + COMPOR. Evidência: `PosScheduleModal.vue`, `PosSchedulePicker.vue`, `PosOrderEntry.vue`, `presentation/{schedule,orderSetup}.ts`, `POSScheduleView`, `shop/services/pos_sales_mode.py`.

**P44 · Converter encomenda em venda de balcão**
- Confirmação: remove entrega, agendamento e cobrança na entrega; mantém itens e cliente. Bloqueado na edição de encomenda. Padrão CORRIGIR. Evidência: `pages/index.vue` (`confirmCounterMode`).

**P45 · Dar desconto na venda inteira**
- Onde: pagamento, modal Desconto (F9). Info: tipos (%/R$), motivos do contrato. Acima de `discount_approval_threshold_q` → gerente (crachá/PIN; sem autoassinatura; aprovador VERIFICADO grava).
- Mínimo: 3 (tipo/valor, motivo, [assinatura]). Padrão: COMPOR + APROVAR. Evidência: `PosPaymentWorkspace.vue` (modal Desconto, autorização), `shop/services/pos.py:validate_manager_override`.

**P46 · Receber o pagamento**
- Quem: atendente; cliente na frente. Onde: pagamento (3 colunas: instrumento / valor / contexto).
- Info mínima: total (da review do servidor), quanto falta, troco (só do excedente em DINHEIRO), linhas de pagamento. Sobra no 1º plano: resumo do pedido completo e bloco fiscal disputam a mesma tela. Falta: nada.
- Entrada: tocar forma (ou tecla R/P/C/D/L) lança o que falta; numpad edita a linha selecionada (reais primeiro, vírgula = centavos); cédulas SOMAM ao recebido (1ª cédula substitui o auto-preenchido); "Exato" (=); "Em conta" só para cliente com conta.
- Efeito: tenders no intent; nada é gravado até Validar. Custo médio (troco errado).
- Exceções: excedente em cartão é erro, não troco (aviso); Pix proibido na cobrança na entrega (exige confirmação automática).
- Caminho: venda exata em dinheiro: F4 → R → Enter (3). Mínimo: 2 (forma, validar).
- Padrão: REGISTRAR-QUANTIDADE. Evidência: `PosPaymentWorkspace.vue`, `presentation/payment.ts`, `presentation/paymentConstraints.ts`, `usePosSale.ts` (tender*).

**P47 · Dividir a conta entre pessoas**
- Modal Dividir (F10; 2–6). Não cria linhas: muda o tamanho da PRÓXIMA (acumulação para os centavos fecharem); contador por PESSOA (não por linha). "R$ 33,34 · 1 de 3".
- Mínimo: 1 (escolher N) + 1 por pessoa. Padrão: COMPOR. Evidência: `presentation/payment.ts` (DIVIDIR A CONTA), `usePosSale.ts` (`splitCount`).

**P48 · Cobrar na maquininha e confirmar**
- Gatilho: linha crédito/débito no balcão. Objetivo: o valor digitado na maquininha é o mesmo da tela (sem TEF).
- Info mínima: valor por linha, forma. Entrada: "OK, cobrei na maquininha" ou Voltar (recusou, trocar forma).
- Na entrega: "Levar maquininha", cartão pendente até o acerto.
- Mínimo: 1 confirmar; com TEF futuro: 0 (a lista `machineTenderLines` é o interruptor). Padrão: CONFERIR. Evidência: `PosPaymentWorkspace.vue` (modal MAQUININHA).

**P49 · Cobrar por Pix ou link e esperar**
- Pix: QR grande no resultado e na tela do cliente; polling por pedido (`polling|paid|expired`); sair vira chip "PIX aguardando" no topo com polling seguindo; resolve com toast. Auto-lock adiado.
- Link: exige modo Encomendas e contato; prazo de vencimento em frase ("hoje às 18h"); reenviar link e "aviso de pagamento" (recusas com motivo).
- Exceção: cobrança não criada (gateway) = tela própria, Enter não engole.
- Mínimo: 0 enquanto espera (cliente paga no celular). Padrão: VIGIAR. Evidência: `usePosSale.ts` (PIX polling, `resendingLink`), `POSPaymentStatusView`, `POSResendPaymentLinkView`, `POSSendPaymentNoticeView`.

**P50 · Escolher quando cobrar**
- Encomenda: "No balcão" / "Na retirada" / "Na entrega" (coleções por recebimento) + link. Frase de consequência que o operador repete ao cliente. Troco para quanto (dinheiro na entrega, aviso se menor que o total).
- Mínimo: 1. Padrão: COMPOR. Evidência: `presentation/payment.ts` (collections), `PosPaymentWorkspace.vue` (QUANDO COBRAR).

**P51 · Responder à nota fiscal**
- Três perguntas: CPF na nota (F; eco do documento), impressa (I; bobina), por e-mail (M). Padrões do cliente pré-marcam; bloco só existe quando `supports_fiscal_document`.
- Efeito: pedido fiscal no intent; emissão assíncrona após fechar. Custo médio (nota com CPF errado).
- Mínimo: 0 (padrão "sem nota/sem CPF") ou 1 tecla + CPF. Padrão: EMITIR. Evidência: `PosPaymentWorkspace.vue` (NOTA FISCAL), `presentation/{taxId,receiptRequest,receiptContact}.ts`, `shop/services/pos_receipt_identity.py`.

**P52 · Validar a venda / recuperar fechamento incerto**
- Gatilho: total coberto; Enter ou botão fixo no fim da coluna do pedido. Antes: review do servidor (total, avisos, aprovação, disponibilidade, agenda). Fechamento idempotente (`client_request_id`, Web Lock por aba).
- Exceções: resposta sem prova (`ok + order_ref`) → faixa vermelha "Conferir últimas vendas / Gestor" + liberar tentativa só após declarar que conferiu; PIN de gerente errado reabre diálogo; `focus: customer` abre a identificação.
- Efeito: Order criado, pagamento, estoque, KDS, fiscal enfileirado. Irreversível (só P54). Custo alto.
- Mínimo: 1. Padrão: AVANÇAR + CORRIGIR. Evidência: `services/pos.py:review_sale/close_sale/_claim_sale_request`, `shop/services/pos_sale_recovery.py`, `presentation/closeGuard.ts`.

**P53 · Entregar troco e papéis, começar a próxima**
- Tela de resultado: troco congelado como herói (dinheiro com troco nunca some sozinho); exato/cartão/Pix pago → auto-avanço curto cancelável; encomenda → leitura de volta ("como e quando") e Via Pedido.
- Papéis: Via Pedido, recibo (agente; fallback `window.print` avisado), DANFE só quando a nota EXISTE (auto-impressão se pedida impressa: espera até ~90 s); "Ver a nota" (quem tem acesso).
- Entrada: Nova venda (F2/Enter). Mínimo: 0 (auto) ou 1.
- Padrão: EMITIR + AVANÇAR. Evidência: `PosSaleResult.vue`, `presentation/saleResult.ts`, `pages/index.vue` (`autoPrintDanfe`, `printReceipt`).

**P54 · Cancelar venda recém-fechada**
- Janela: 5 min (`RECENT_SALE_MAX_AGE_MINUTES`), só canal PDV, status NEW/ACCEPTED/PREPARING (ou COMPLETED se o canal permite). Motivo + gerente (crachá/PIN), mesmo diálogo no resultado e nas últimas vendas.
- Efeito: cancela, KDS some, estoque volta, NFC-e desfeita, dinheiro sai da gaveta do TERMINAL da venda (exige turno aberto). Custo alto.
- Mínimo: 3 (abrir, motivo, assinatura). Padrão: CORRIGIR + APROVAR. Evidência: `services/pos.py:cancel_recent_order/reopen_recent_order_for_correction`, `PosCancelSaleDialog.vue`, `POSCancelRecentSaleView`.

**P55 · Saber se a nota autorizou e reimprimir/reenviar/reprocessar**
- Onde: painel "Últimas vendas" (botão no topo). Lista 24 h + vendas cuja mercadoria saiu na janela fiscal; poll calmo enquanto aberto.
- Ações por FATO: imprimir DANFE (carimbo 2ª via pelo servidor), recibo, reenviar e-mail (abre campo), reprocessar falha, consulta pública; cancelar (P54).
- Padrão: VIGIAR + EMITIR. Evidência: `PosRecentSales.vue`, `projections/pos.py:build_pos_recent_sales`, `POS{Danfe,SaleReceipt}EscposView`, `POSResendFiscalEmailView`.

**P56 · Emitir nota avulsa**
- Cliente volta pedindo a nota que a regra não emitiu. Sempre gerente. Erro de PIN inline; recusa de negócio vira toast.
- Padrão: EMITIR + APROVAR. Evidência: `PosRecentSales.vue` (emissão avulsa), `POSEmitFiscalView`.

**P57 · Ver a venda na tela virada ao cliente**
- Quem: cliente. Fases: boas-vindas → itens ao vivo com descontos rotulados e total (o mesmo número da estação) → pagamento (QR Pix) → resultado (troco, obrigado) → volta sozinha.
- Sem interação, sem trava, sem servidor (BroadcastChannel). Padrão: VIGIAR. Evidência: `pages/display.vue`, `presentation/customerDisplay.ts`, `PosCustomerDisplayShell.vue`.

### Encomendas

**P60 · Ver o que a casa prometeu**
- Onde: `/preorders` (rail, com selo das de hoje por entregar). Corte: todo pedido com recebimento (retirada/entrega), qualquer canal, pela data combinada (nota de escopo na tela).
- Info mínima: linha "Hoje" (quantas entregar, quanto falta receber, vias faltando, pagamentos a conferir); semana (padrão) ou dia por janela; recortes de 1 toque (A receber, Sem Via Pedido, Retiradas, Entregas); estado na URL.
- Padrão: VIGIAR + PLANEJAR. Evidência: `pages/preorders/index.vue`, `presentation/preorders.ts`, `projections/preorders.py`, `POSPreorderListView`.

**P61 · Achar a encomenda de quem chegou**
- Campo "Cliente veio buscar" sempre no topo e focado: nome, telefone, CPF/CNPJ, endereço, número (inclusive iFood); em aberto de QUALQUER data; concluídas 30 dias sob demanda; 1 resultado + Enter abre; leitor/teclado fora de campo cai na busca.
- Mínimo: 1 (digitar/bipar) + Enter. Padrão: LOCALIZAR. Evidência: `pages/preorders/index.vue`, `POSPreorderSearchView`.

**P62 · Receber o saldo e entregar a encomenda (retirada)**
- Info mínima: saldo devido, estado (pronta?), forma combinada. Botão "Receber e entregar R$ X" ou "Entregar" (paga); se não pode, a frase do porquê (não pronta, entrega em endereço, iFood pendente, pagamento online pendente, pagamento ilegível).
- Entrada: forma (dinheiro com troco, cartão na maquininha), valor recebido (vazio = exato), confirmar.
- Efeito numa transação: `cod_settled` no turno da gaveta desta estação + pedido COMPLETED; Pix/link ainda vivo é cancelado antes (takeover) ou recusa `preorder_paid_online` (cliente pagou segundos antes → só entregar). Idempotente. Custo alto.
- Caminho: busca → detalhe → botão → confirmar (4). Mínimo: 2 (achar, confirmar).
- Padrão: AVANÇAR + REGISTRAR-QUANTIDADE. Evidência: `PosPreorderHandOverDialog.vue`, `presentation/preorderActions.ts`, `POSPreorderHandOverView`, `shop/services/operator_orders.py:hand_over_at_counter/counter_hand_over_block`, `counter_takeover.py`.

**P63 · Encomendas de entrega em endereço**
- O PDV lista e mostra, mas "a saída é pelo Gestor de pedidos" (bloqueio explícito). Acerto do entregador também é do Gestor (`OrderSettleDeliveryCashView`). Padrão: VIGIAR. Evidência: `counter_hand_over_block`.

**P64 · Reagendar**
- Datas/janelas combináveis para ESTES itens (mesma `/pos/schedule/`); janela inalcançável apagada com motivo; botão diz o destino. Orquestrador move despertador, lembrete, reservas, produção.
- Mínimo: 2 (data, confirmar). Padrão: PLANEJAR + CORRIGIR. Evidência: `PosPreorderRescheduleDialog.vue`, `shop/services/reschedule.py`.

**P65 · Mudar itens de uma encomenda**
- "Editar" abre a tela de venda em modo edição (`/?edit=`): comanda virtual pré-montada, carrinho + grade + F7/F8, "Salvar alterações" no lugar do pagamento; sem desconto/observação de item; cliente travado; sem cozinha; não exige caixa aberto. Prévia do servidor antes de gravar; encomenda paga que fica mais barata pede gerente e gera estorno (dinheiro P18 / maquininha P19). Cliente avisado. NFC-e autorizada fecha a edição → "Cancelar e refazer".
- Padrão: CORRIGIR + APROVAR. Evidência: `pages/index.vue` (`usePosOrderEdit`), `PosOrderEditReview.vue`, `presentation/orderEdit.ts`, `shop/services/pos_edit_session.py`, `POSPreorderEditSessionView`.

**P66 · Cancelar encomenda / cancelar e refazer**
- Diálogo de motivo do kit (motivos da casa ou texto que vai ao cliente); paga → gerente. Refazer: cancela e abre comanda "Refazer <ref>" pré-montada (sem caixa → antessala primeiro); data inválida é dita.
- Padrão: CORRIGIR + APROVAR. Evidência: `PosPreorderCancelDialog.vue`, `POSPreorderRedoTabView`, `presentation/preorderActions.ts`.

**P67 · Imprimir Via Pedido**
- Lote: do que está VISÍVEL, só as que ainda não saíram. Unitária: detalhe (reimprime) e resultado da venda de encomenda. Padrão: EMITIR. Evidência: `usePosOrderTickets.ts`, `OrderTicketBatchEscposView`, `OrderTicketEscposView`.

**P68 · Comentar no histórico**
- Atalho do painel do balcão ao campo do histórico do `OperatorOrderDetail` (mesmo detalhe do Gestor). Padrão: REGISTRAR. Evidência: `pages/preorders/[ref].vue`.

### Periféricos

**P70 · Dar "Pronto" lendo o QR do ticket impresso**
- A Via Cozinha (estação sem tela) termina num QR `KT-<pk>-<assinatura>`; o leitor HID "digita" em qualquer tela do PDV; rajada de máquina é reconhecida, teclas de dedo são devolvidas ao campo. Som + aviso.
- Mínimo: 1 bipada. Padrão: AVANÇAR. Evidência: `useKitchenTicketScanner.ts`, `presentation/ticketScan.ts`, `KDSPrintedTicketScanView`.

**P71 · Imprimir pela bobina local**
- O servidor compõe ESC/POS; a página relaia ao agente na loopback (o servidor não alcança). Mesmo agente abre a gaveta (RJ11 da impressora) nos quatro momentos (venda em dinheiro, sangria, suprimento, sem venda). Leitura da gaveta com timeout 1 s ("não sei" nunca para a fila). Sem agente: `window.print` avisado.
- Padrão: EMITIR (infra). Evidência: `useCounterAgent.ts`, `services/receipt_escpos.py`, `services/pos_hardware.py`.

---

## 3. Padrões que enxergo neste app

1. **Três trabalhos são o mesmo "receber dinheiro e dar baixa"**: pagar a venda (P46), receber e entregar encomenda (P62) e acertar conta na casa (P20) pedem forma + valor + troco e lançam no turno da gaveta. Cada um tem tela, regra de troco e teclado próprios (workspace de 3 colunas; diálogo do detalhe; diálogo da antessala).
2. **Todas as exceções de dinheiro usam a mesma assinatura do gerente** (sangria, troco servido, devolução, estorno na maquininha, desconto acima do limite, cancelar venda, emitir nota avulsa, edição que fica mais barata, gaveta emperrada). O app já unificou o diálogo (`OperatorManagerAuth`, crachá ou PIN). Padrão claro: **ATO + MOTIVO + ASSINATURA**.
3. **CONFERIR às cegas aparece duas vezes, com a mesma forma**: fechar caixa (P22) e fechar dia (P23). Contar sem gabarito, eco do número, confirmar. Mesmo dono (gerência), mesmo momento (fim do expediente), telas diferentes. São um corredor só ("fim do dia"), e o código já encadeia um no outro.
4. **Trabalhos que o sistema poderia fazer sozinho**:
   - Enviar à cozinha (P37) é um toque manual por comanda; o canal poderia disparar ao salvar/pagar o que tem preparo.
   - Abrir a tela do cliente (P6) todo dia; a estação poderia lembrar.
   - Abrir caixa (P10) pede digitar o fundo que o terminal já sugere; confirmar a sugestão poderia ser o padrão de 1 toque (hoje é 1 toque para preencher + Enter).
   - Estorno na maquininha (P19) é atestado à mão porque não há TEF (já previsto como interruptor).
   - Peça pesada (P32): o operador digita o valor da etiqueta que poderia ser lido do código de balança (EAN-13 com preço/peso embutido); hoje o leitor de código de barras só casa GTIN inteiro.
5. **A informação está longe da decisão em quatro lugares**:
   - Contas na casa (P20) só aparecem como pendência da antessala; quando o cliente devedor está na comanda, o cadastro dele não oferece "acertar".
   - Encomenda de hoje do cliente identificado na venda não aparece na venda; para entregar é preciso sair para `/preorders`.
   - Entrega em endereço aparece no PDV mas a ação mora no Gestor.
   - "Últimas vendas" é a casa da nota fiscal, mas está num ícone no topo; o estado da nota de cada venda some com a tela de resultado.
6. **COMPOR o pedido tem dois tempos que o app já separou bem**: fatos do PEDIDO (cliente F6, recebimento F7, quando F8) ficam na barra e valem da abertura ao troco; fatos do PAGAMENTO (forma, troco, nota) ficam no pagamento. O assistente de encomenda é só a mesma barra perguntada em ordem.
7. **Um ator invisível: o mundo físico como autorização** (trava da gaveta, leitor de ticket, crachá). Proponho rótulo **TRAVA-FÍSICA**: o sistema espera um fato físico (gaveta fechada, papel bipado) em vez de um toque.
8. **Duplicação real**: total parcial do carrinho, total interino do pagamento e total da tela do cliente já foram três contas e hoje são uma (`cartNetTotalQ`). Restam duplicados de forma: os três "receber dinheiro" (item 1) e os dois "contar às cegas" (item 3).

### 3.1 A área de linhas da comanda: o que precisa e quanto espaço

**O que o operador faz ali**, em ordem de frequência: (1) **ler de volta** o pedido para o cliente ("dois croissants, um café...") e conferir o total; (2) corrigir quantidade da última linha; (3) remover; (4) ver se foi à cozinha / se está pronto; (5) anotar observação; (6) descontar; (7) selecionar várias para enviar/remover/descontar/mover.

**Informação mínima por linha**: qtd (ou peso), nome com opções, total da linha. Secundário e só quando existe: observação, selo de desconto, selo da cozinha. Preço unitário ("R$ 4,50 cada") é ruído na leitura de volta: só importa quando há desconto ou peso. Autoria/hora: só nos detalhes.

**Orçamento vertical hoje** (coluna fixa de 360 px, `PosCartPanel.vue`):
- cabeçalho da comanda ≈ 53 px;
- console do item (numpad 3×4 de 44 px + coluna de 4 modos) ≈ 204 px, sempre visível quando há linha ativa (e há sempre: a última);
- linha extra de desconto (só nos modos Desc) ≈ 40 px;
- rodapé: total parcial + Enviar/Transferir empilhados ao lado de Pagamento ≈ 140 px;
- **fixo ≈ 400 px**. Cada linha ≈ 56 px (nome + preço unitário); a linha ativa ganha o stepper/remover inline (≈ +44 px).
- Resultado: tela útil de 1080 px (desktop) mostra ~8–9 linhas; 768 px (tablet deitado, ou notebook 1366×768) mostra **4–5 linhas**; tablet em pé (768×1024) mostra ~9 linhas mas a grade de produtos fica com ~2 colunas.
- Ou seja, no tablet o numpad ocupa cerca de metade da comanda, e a lista que o operador lê para o cliente fica com um terço.

**O que isso revela**:
- Com teclado físico (desktop), os dígitos já editam a linha ativa e +/−/Delete funcionam na seleção. O numpad da tela duplica o teclado e rouba ~200 px da lista. Ele é indispensável **só** no toque (tablet), que é justamente onde falta altura.
- O stepper inline na linha ativa e o numpad fazem a mesma coisa (qtd). Dois instrumentos para uma pergunta.
- Desconto e observação são raros (0–20×/dia contra 100–400 vendas): não justificam modos permanentes no console. São do detalhe da linha (que já existe, expandindo a linha).
- "Enviar à cozinha" e "Transferir" disputam o rodapé com "Pagamento"; em balcão sem comanda/cozinha eles somem (correto).
- Necessidade mínima real: **lista + total + 1 CTA (Pagamento)**, com o instrumento de edição aparecendo **sob demanda** (tocar a linha) e não fixo.

### 3.2 O que muda no tablet × desktop para este job

| Aspecto | Desktop (PC do balcão, teclado, leitor, agente, 2º monitor) | Tablet (toque) |
|---|---|---|
| Lançar produto | busca por digitação (letra fora de campo), leitor HID, Enter em sequência | teclado virtual cobre metade da tela: a grade, as categorias e os favoritos viram o caminho principal; busca é secundária |
| Atalhos F2–F10, R/P/C/D/L, = | o caminho mais rápido | inexistentes; todo gesto precisa de alvo de toque visível |
| Numpad da comanda | redundante (teclado físico) | indispensável, mas deveria aparecer sob demanda |
| Altura da comanda | 8–9 linhas | 4–5 linhas (deitado) |
| Pagamento (3 colunas) | cabe em 1440 px | as laterais encolhem; o resumo do pedido e a nota competem com o numpad de valor |
| Gaveta/impressora | agente na loopback abre gaveta, imprime bobina, sensor da trava | sem agente local: impressão cai em `window.print`, gaveta não abre pelo sistema, trava da gaveta não existe |
| Tela do cliente | segunda janela no 2º monitor | impossível (BroadcastChannel do mesmo navegador) |
| Leitor de ticket/código | HID USB | só leitor Bluetooth em modo teclado; câmera não é usada |
| Encomendas, X/Z, últimas vendas | usáveis | usáveis e naturais no tablet (leitura + toque) |
| Fechamento do dia (contar a vitrine) | possível, mas o operador anda até a vitrine | **melhor no tablet/celular**: contar andando |

Conclusão de dispositivo: o PDV de venda é **desktop-first por causa do periférico** (agente, gaveta, impressora, leitor, 2º monitor), não por causa da tela. No tablet ele é viável como **segundo posto** (fila longa, comanda de mesa, encomendas, contagem), sem dinheiro físico.

---

## 4. Cobertura (telas e estados)

| Rota / estado / diálogo | Dispositivo que faz sentido | Por quê |
|---|---|---|
| Tela de senha (dispositivo sem estação) / setup de estação | desktop | ato de gestor, 1×, digitar senha |
| Overlay de identificação (PIN/crachá) | desktop e tablet | crachá precisa de leitor; PIN funciona em toque |
| Banner offline / re-gate 401 | todos | transversal |
| `/` quadro de comandas (grade/lista, filtro, próxima livre) | desktop e tablet | número digitado ou toque no card |
| `/` "não foi possível ler as comandas" / carregando | todos | estado |
| `/` venda: grade de produtos + busca + categorias + densidade | desktop (busca/leitor); tablet (grade) | ver 3.2 |
| `/` venda: comanda (linhas, console numpad, seleção múltipla, detalhes, rodapé) | desktop; tablet com console sob demanda | ver 3.1 |
| `/` barra de contexto (modo Balcão/Encomendas, nº comanda, chips F6/F7/F8, liberar, "Não salvo", conflito) | desktop e tablet | fatos do pedido |
| `/` assistente da encomenda (`PosOrderEntry`) | desktop e tablet (também celular, atendimento por telefone) | formulário sequencial |
| `/` pagamento (`PosPaymentWorkspace`: formas, numpad, cédulas, linhas, resumo, nota, Validar) | desktop; tablet deitado com aperto | três colunas |
| Modal Maquininha | desktop e tablet | confirmação |
| Modal Dividir conta | desktop e tablet | escolha curta |
| Modal Desconto + autorização do gerente | desktop e tablet | |
| `/` tela de resultado (troco, QR, papéis, nova venda, cancelar) | desktop (papel depende do agente) | impressão |
| Chip "PIX aguardando" | desktop e tablet | |
| Faixa "fechamento incerto" + diálogo "Você conferiu?" | desktop | exceção rara |
| `PosCustomerModal` (busca, cadastro, memória, padrões, 5 decisões de conflito, unificar, liberar contato) | desktop (digitação pesada); tablet ok com teclado virtual | formulário |
| `PosFulfillmentModal` (retirada/entrega, endereço, taxa) | desktop | endereço digitado com autocomplete |
| `PosScheduleModal` / `PosSchedulePicker` | desktop e tablet | toque em datas/janelas |
| `PosWeighedEntryDialog` | desktop e tablet | numpad próprio |
| `PosProductOptionsDialog` | desktop e tablet | toque |
| Cartão de escolha (`PosProductGroupTile`) | desktop e tablet | toque |
| `PosMoveLinesDialog` (dividir/transferir/juntar) | desktop e tablet | marcar linhas |
| `PosTabPickerDialog` (associar comanda) | desktop e tablet | |
| Diálogo observação da linha | desktop (texto) | digitação |
| Diálogo remover item / lote | todos | confirmação |
| `PosKitchenTicketDialog` | desktop e tablet | |
| `PosDrawerLockDialog` + gerente | desktop (só existe com sensor/agente) | gaveta física |
| `PosCancelSaleDialog` | desktop e tablet | |
| Converter para balcão (confirmação) | todos | |
| `PosOrderEditReview` + gerente (modo `?edit=`) | desktop | edição de encomenda |
| `PosRecentSales` (painel: fiscal, DANFE, recibo, e-mail, reprocessar, emitir avulsa, cancelar, consulta pública) | desktop (bobina) | impressão |
| `PosShortcutsHelp` | desktop | só existe com teclado |
| `PosTerminalHealth` (popover do rail) | desktop | periféricos da estação |
| `PosFunctionRail` (Comandas, Caixa, Encomendas, Tela do cliente, Saúde, Atualizar, Travar, Apps) | desktop e tablet | navegação |
| `/session` antessala: card Abrir caixa / Continuar vendendo; "Precisa de você" (devoluções, maquininha, troco, contas); Gaveta (pedir troco, entrada, saída, abrir sem venda); Fim do expediente (fechar caixa, fechamento do dia, relatório) | desktop (gaveta física); tablet para leitura | dinheiro físico |
| Diálogos: abrir caixa (+ contador por cédula), movimento (tipo, valor, motivo), pedir troco (denominações), pedidos de troco (servir/cancelar), abrir gaveta (motivo, teste), devoluções, estornos na maquininha, contas na casa (acertar), fechar caixa (contagem cega + confirmação + contador) | desktop | gaveta e PIN no balcão |
| `/session/report` (X, Z, histórico, 2ª via de movimento) | desktop e tablet | leitura; 2ª via precisa de agente |
| `/session/closing` (antes da contagem: lista + bloqueio de produção; depois: quadro do dia, próximo passo) | **tablet/celular** | contar andando pela vitrine |
| `/preorders` (busca "Cliente veio buscar", Hoje, recortes, Filtrar, semana/dia, lote de vias, Nova encomenda) | desktop e tablet; parede para a semana | agenda |
| `/preorders/[ref]` (detalhe do kit + painel do balcão: Receber e entregar/Entregar, Editar, Reagendar, Imprimir Via Pedido, Cancelar, Comentar) | desktop e tablet | dinheiro da retirada pede gaveta (desktop) |
| Diálogos: receber e entregar (forma, troco), reagendar, cancelar (motivo + gerente), "pago online" | desktop (dinheiro); tablet (só entregar/cartão) | |
| `/display` tela do cliente (boas-vindas, venda, pagamento com QR, resultado) | parede / 2º monitor | só leitura, à distância |
| Leitor de ticket da cozinha (global, sem tela própria) | desktop com leitor HID | periférico |
