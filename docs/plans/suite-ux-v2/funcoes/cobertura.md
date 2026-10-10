# Matriz de cobertura: toda tela, todo estado, um destino

Anexo do [SUITE-UX-FUNCTION-PLAN](../../SUITE-UX-FUNCTION-PLAN.md) (§10). Uma linha para **cada** linha
das tabelas "Cobertura" das sete fichas ([pdv](pdv.md), [gestor](gestor.md), [kds-hub](kds-hub.md),
[producao](producao.md), [compras](compras.md), [marketing](marketing.md), [bi](bi.md)), na mesma
ordem, mais as telas que o plano diz que **precisam existir** e hoje não existem (destino `nova tela`,
no fim de cada app, marcadas `N`).

Convenções:
- **IDs de trabalho são locais ao app** (o `P01` do PDV não é o `P01` do Gestor nem o da Produção).
  Quando a linha cita trabalho de outro app, vem com o nome: `Gestor P11`, `Cozinha K14`.
- **Linha composta do original** (um diálogo com cinco gestos de destinos diferentes) foi aberta em
  sub-linhas `a`, `b`, `c`… para que cada uma tenha um destino só. A ordem continua a do original.
- **forma**: uma das 7 formas (§3.1), `gesto: X` para os gestos transversais (§3.2), `transversal`
  para o chrome do kit (login, trava, rail, instalação), `estado` para estados puros (offline,
  carregando, vazio, erro, redirecionamento).
- **andar**: `Operação` (padrão, no posto) · `Ajustes` (cadastro, configuração, relatório) · `—`
  (chrome e estado, valem nos dois).
- **destino**: `mantém` · `funde com <X>` · `automatiza (L1)` · `muda para <app/posto>` ·
  `some (motivo)` · `nova tela`. Quando há reforma de conteúdo sem troca de casa, o destino é
  `mantém` e a reforma vem entre parênteses.

## Resumo

**271 linhas**: 233 linhas originais das sete tabelas "Cobertura" (7 delas compostas, abertas em 22
sub-linhas) e 16 telas novas `N`. Contagens tiradas da própria matriz por script, não à mão.

### Linhas e destino por app

| app | linhas (orig · sub · novas) | mantém | funde com | automatiza (L1) | muda para | some | nova tela |
|---|---|---|---|---|---|---|---|
| PDV | 55 (44 · 10 de 2 · 3) | 18 | 26 | 3 | 2 | 3 | 3 |
| Gestor de pedidos | 45 (40 · 4 de 2 · 3) | 27 | 10 | 1 | 3 | 2 | 2 |
| Cozinha + Shopman Apps + kit | 41 (38 · 0 · 3) | 26 | 4 | 1 | 5 | 2 | 3 |
| Produção | 32 (31 · 0 · 1) | 20 | 8 | 1 | 1 | 1 | 1 |
| Compras | 31 (28 · 0 · 3) | 19 | 4 | 1 | 3 | 0 | 4 |
| Marketing | 46 (36 · 11 de 3 · 2) | 26 | 10 | 2 | 1 | 2 | 5 |
| B.I. | 21 (16 · 2 de 1 · 4) | 14 | 0 | 0 | 3 | 0 | 4 |
| **total** | **271** | **150** | **62** | **9** | **18** | **10** | **22** |

`nova tela` conta 22 e não 16 porque quatro sub-linhas "(sem tela)" do Marketing e o histórico de
recebimentos do Compras já estavam na tabela original sem tela; e o `N2` do Marketing (cerimônia no
Admin) é `mantém`.

### Forma por app

| app | FILA | CONFERÊNCIA | COMPOSIÇÃO | CADASTRO | LEITURA | FOCO | MONITOR | gesto | transversal | estado |
|---|---|---|---|---|---|---|---|---|---|---|
| PDV | 6 | 5 | 13 | 0 | 1 | 6 | 1 | 16 | 4 | 3 |
| Gestor de pedidos | 9 | 4 | 0 | 16 | 2 | 1 | 0 | 11 | 1 | 1 |
| Cozinha + Shopman Apps + kit | 10 | 0 | 0 | 2 | 1 | 0 | 2 | 6 | 8 | 12 |
| Produção | 4 | 11 | 2 | 2 | 3 | 1 | 1 | 6 | 0 | 2 |
| Compras | 5 | 9 | 1 | 6 | 1 | 3 | 0 | 0 | 2 | 4 |
| Marketing | 8 | 0 | 5 | 11 | 1 | 0 | 0 | 9 | 0 | 12 |
| B.I. | 0 | 0 | 0 | 3 | 11 | 0 | 0 | 3 | 2 | 2 |
| **total** | **42** | **29** | **21** | **40** | **20** | **11** | **4** | **51** | **17** | **36** |

Leitura rápida: 51 linhas são um dos seis gestos (diálogos que hoje existem por app e viram uma peça
só do kit); 62 `funde com` são quase todas isso, mais as duplicatas (despacho, acerto, retirada,
plataformas, custo). Os 18 `muda para` são as fronteiras do §9: Passe (Gestor + Saída da Cozinha),
Fim do dia (fechar caixa, fechar o dia, episódio), Estoque (contagem), Produção › planejar
(Agendados, prévia de data, projeção do dia), Gestor › Canais (avisos transacionais), AVISO no
celular (alarmes do B.I., qualidade).

### Telas sem destino claro

Nenhuma linha está sem destino. Cinco ficam com destino **provisório** (`mantém` fora do app), porque
o plano aponta a lacuna mas não decide se ganham tela; é pergunta para o dono, não omissão:
- **B.I. › Admin** (`BIAlertRule`, etiquetas de consumo, lugares do salão, de-para de lote) e
  **B.I. › comandos de carga** (Yooga, feriados, clima): §11 diz "configuração de terminal, depende de
  técnico". Trabalhos BI-22, BI-23, BI-24.
- **Gestor › editar cadastro do cliente** (hoje no Admin, U05): a ficha mostra, a edição sai do app.
- **Marketing › cerimônia do disparo e mínimo de público** (Admin, M38): raríssimo, de dono.

---

## Mapa de postos (quem abre direto em quê)

| posto | filas e telas desta matriz |
|---|---|
| Balcão | PDV comandas, venda, pagamento, caixa, retirada (`PDV N2`); tablet como segundo posto (`PDV N1`) |
| Passe | `Gestor N1` (Gestor board + Cozinha Saída), interruptores de canal e de produto, Entregador voltou |
| Estação | Cozinha preparo; visão "todas as estações" (`Cozinha N1`) no tablet na mão |
| Forno | Produção expedição, produzir, fechar fornada, mise en place, timers |
| Doca | Compras receber, "a caminho" (`Compras N1`), histórico de recebimentos |
| Estoque | contagem cega (`Compras N3`) |
| Fim do dia | corredor (`PDV N3`): fechar caixa, contar vitrine, episódio, fechar o dia |
| Escritório | Ajustes de todos os apps; planejar (Produção); comprar; B.I. |
| Dono em movimento | fila de decisões do Marketing, aprovação de compra, qualidade, negociação iFood, interruptores, AVISO |
| Parede | Painel de retirada, Letreiro, Tela do cliente, quadro de estação em TV |

---

## PDV

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| Tela de senha (dispositivo sem estação) / setup de estação | transversal | Balcão | Ajustes | desktop | funde com Kit "iniciar este dispositivo" (provisionamento único para todos os postos, Cozinha incluída) | P01 |
| Overlay de identificação (PIN/crachá) | transversal | Balcão | — | desktop · tablet fixo · tablet na mão | funde com Kit trava (C03), igual nos oito apps | P02, P03, P04 |
| Banner offline / re-gate 401 | estado | Todos | — | desktop · tablet fixo · tablet na mão · celular | funde com Kit faixa offline / sessão indisponível | P02 |
| `/` quadro de comandas (grade/lista, filtro, próxima livre) | FILA | Balcão | Operação | desktop · tablet na mão | mantém (porta de entrada do atendente; ordem por urgência; "aguardando PIX", "na cozinha" e "pronto" como estado do item) | P30 |
| `/` "não foi possível ler as comandas" / carregando | estado | Balcão | — | desktop · tablet na mão | mantém (desatualizado explícito, padrão da FILA) | P30 |
| `/` venda: grade de produtos + busca + categorias + densidade | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | mantém (zona fonte: busca e leitor no desktop, grade grande no tablet; densidade derivada do posto, seletor some) | P31, P33 |
| `/` venda: comanda (linhas, console numpad, seleção múltipla, detalhes, rodapé) | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | mantém (§10.1: lista + total + Pagamento numa faixa só; instrumento só ao tocar a linha; teclado físico no desktop; Transferir no modo seleção; envio à cozinha automático) | P34, P35, P36, P37, P38, P39 |
| `/` barra de contexto (modo Balcão/Encomendas, nº comanda, chips F6/F7/F8, liberar, "Não salvo", conflito) | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | mantém (zona de fatos da transação, do começo ao fim) | P40, P41, P42, P43, P44 |
| `/` assistente da encomenda (`PosOrderEntry`) | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão · celular | funde com a faixa de fatos da COMPOSIÇÃO (quem, quando, como recebe) | P41, P42, P43 |
| `/` pagamento (`PosPaymentWorkspace`: formas, numpad, cédulas, linhas, resumo, nota, Validar) | FOCO | Balcão | Operação | desktop · tablet na mão | mantém (FOCO; no tablet só PIX e maquininha, dinheiro vai ao caixa; nota fiscal como pergunta curta no fim) | P46, P50, P51, P52 |
| Modal Maquininha | FOCO | Balcão | Operação | desktop · tablet na mão | funde com o FOCO de pagamento (passo, não modal) | P48 |
| Modal Dividir conta | FOCO | Balcão | Operação | desktop · tablet na mão | funde com o FOCO de pagamento (passo, não modal) | P47 |
| Modal Desconto + autorização do gerente | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop · tablet na mão | funde com EXCEÇÃO ASSINADA única da suíte (assinatura só acima do limite; zero passos com gerente logado) | P36, P45 |
| `/` tela de resultado (troco, QR, papéis, nova venda, cancelar) | FOCO | Balcão | Operação | desktop | mantém (troco + próxima venda; papel é efeito colateral, só a falha vira AVISO) | P53, P54 |
| Chip "PIX aguardando" | gesto: AVISO | Balcão | Operação | desktop · tablet na mão | funde com o estado do item na FILA de comandas ("aguardando PIX", com push ao confirmar) | P49 |
| Faixa "fechamento incerto" + diálogo "Você conferiu?" | gesto: AVISO | Balcão | Operação | desktop | automatiza (L1) (o sistema reconcilia sozinho; só o que não resolve vira item com motivo) | P52 |
| `PosCustomerModal` (busca, cadastro, memória, padrões, 5 decisões de conflito, unificar, liberar contato) | gesto: LOCALIZAR | Balcão | Operação | desktop · tablet na mão | funde com LOCALIZAR da suíte (cliente); unificar segue para Gestor › Clientes (Ajustes) | P41 |
| `PosFulfillmentModal` (retirada/entrega, endereço, taxa) | COMPOSIÇÃO | Balcão | Operação | desktop | funde com a faixa de fatos da COMPOSIÇÃO | P42 |
| `PosScheduleModal` / `PosSchedulePicker` | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | funde com a faixa de fatos da COMPOSIÇÃO (o mesmo seletor reagenda encomenda) | P43, P64 |
| `PosWeighedEntryDialog` | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | automatiza (L1) (leitor lê EAN-13 de balança com preço/peso; o diálogo fica só para etiqueta ilegível) | P32 |
| `PosProductOptionsDialog` | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | mantém (instrumento sob demanda, aberto pela fonte) | P33 |
| Cartão de escolha (`PosProductGroupTile`) | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | funde com a zona fonte (grade) | P31, P33 |
| `PosMoveLinesDialog` (dividir/transferir/juntar) | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | funde com o modo seleção da conta | P39 |
| `PosTabPickerDialog` (associar comanda) | gesto: LOCALIZAR | Balcão | Operação | desktop · tablet na mão | funde com LOCALIZAR (comanda por número ou código) | P30, P39 |
| Diálogo observação da linha | gesto: ANOTAR | Balcão | Operação | desktop · tablet na mão | funde com ANOTAR (lista curta da casa + "Outro") | P35 |
| Diálogo remover item / lote | gesto: SELO / DESFAZER | Balcão | Operação | desktop · tablet na mão | some (remoção é reversível: desfazer por N s, sem diálogo) | P34 |
| `PosKitchenTicketDialog` | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | automatiza (L1) (envio à cozinha ao salvar ou pagar; o fato "na cozinha 21:52" aparece na linha) | P37, P38 |
| `PosDrawerLockDialog` + gerente | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop | mantém (TRAVA-FÍSICA como estado do balcão; destrave por EXCEÇÃO ASSINADA) | P17 |
| `PosCancelSaleDialog` | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop · tablet na mão | funde com EXCEÇÃO ASSINADA (ato + motivo + assinatura) | P54 |
| Converter para balcão (confirmação) | gesto: SELO / DESFAZER | Balcão | Operação | desktop · tablet na mão | some (é reversível: vira desfazer em vez de confirmação) | P44 |
| `PosOrderEditReview` + gerente (modo `?edit=`) | CONFERÊNCIA | Balcão | Operação | desktop | mantém (revisão da diferença; assinatura só quando a encomenda paga fica mais barata) | P65 |
| `PosRecentSales` (fiscal, DANFE, recibo, e-mail, reprocessar, emitir avulsa, cancelar, consulta pública) | FILA | Balcão | Operação | desktop | mantém (últimas vendas como FILA curta; nota não autorizada vira AVISO no item com o motivo da SEFAZ; avulsa = SELO + EXCEÇÃO ASSINADA) | P54, P55, P56 |
| `PosShortcutsHelp` | transversal | Balcão | — | desktop | mantém (só existe com teclado) | — |
| `PosTerminalHealth` (popover do rail) | gesto: AVISO | Balcão | Operação | desktop | funde com AVISO (periférico só aparece quando falha, como item com o conserto) | P05, P71 |
| `PosFunctionRail` (Comandas, Caixa, Encomendas, Tela do cliente, Saúde, Atualizar, Travar, Apps) | transversal | Balcão | — | desktop · tablet na mão | funde com o rail do kit (Operação na barra; Ajustes num item só) | P03, P06 |
| `/session` antessala: Abrir caixa / Continuar; "Precisa de você"; Gaveta; Fim do expediente | FILA | Balcão | Operação | desktop | mantém (FILA do caixa: devoluções, maquininha, troco, contas como itens com dono; o bloco Fim do expediente segue para o posto Fim do dia) | P10, P11, P12, P13, P16, P18, P19, P20 |
| a. Diálogo abrir caixa (+ contador por cédula) | CONFERÊNCIA | Balcão | Operação | desktop | mantém (com o troco provável do B.I. no lugar, EXPLICAR-NO-LUGAR) | P10, B.I. BI-17 |
| b. Diálogos movimento (sangria/suprimento) e abrir gaveta (motivo, teste) | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop | funde com EXCEÇÃO ASSINADA (motivo de lista curta; suprimento sem assinatura) | P11, P12, P16 |
| c. Diálogos pedir troco e pedidos de troco (servir/cancelar) | gesto: AVISO | Balcão | Operação | desktop | funde com AVISO (pedido de troco vira item na fila de quem traz; servir = fato) | P13, P14, P15 |
| d. Diálogos devoluções e estornos na maquininha | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop | funde com EXCEÇÃO ASSINADA (o item nasce sozinho na FILA do caixa) | P18, P19 |
| e. Diálogo contas na casa (acertar) | FOCO | Balcão | Operação | desktop | funde com RECEBER (o mesmo FOCO de pagamento e de retirada) | P20 |
| f. Diálogo fechar caixa (contagem cega + confirmação + contador) | CONFERÊNCIA | Fim do dia | Operação | tablet na mão · desktop | muda para Fim do dia (primeiro passo do corredor, cego) | P22 |
| `/session/report` (X, Z, histórico, 2ª via de movimento) | LEITURA | Escritório | Ajustes | desktop · tablet na mão | mantém (LEITURA em Ajustes; 2ª via como ação rara) | P21 |
| `/session/closing` (antes da contagem: lista + bloqueio de produção; depois: quadro do dia) | CONFERÊNCIA | Fim do dia | Operação | tablet na mão · celular | muda para Fim do dia (corredor: fechar caixa, contar a vitrine, fechar o dia) | P23 |
| `/preorders` (busca "Cliente veio buscar", Hoje, recortes, Filtrar, semana/dia, lote de vias, Nova encomenda) | FILA | Balcão | Operação | desktop · tablet na mão · parede | funde com a FILA de retirada única PDV + Gestor (`N2`); visão de semana segue para Produção › planejar; lote de vias vira efeito do ato | P60, P61, P63, P67 |
| `/preorders/[ref]` (Receber e entregar, Editar, Reagendar, Imprimir Via Pedido, Cancelar, Comentar) | FILA | Balcão | Operação | desktop · tablet na mão | mantém (detalhe do item da retirada, endereçável; um gesto: Entregar) | P62, P64, P65, P66, P67, P68 |
| a. Diálogo receber e entregar (forma, troco) | FOCO | Balcão | Operação | desktop · tablet na mão | funde com RECEBER (o FOCO de pagamento; dinheiro só no desktop com gaveta) | P62, Gestor P11 |
| b. Diálogo reagendar | COMPOSIÇÃO | Balcão | Operação | desktop · tablet na mão | funde com o seletor de data da faixa de fatos | P64 |
| c. Diálogo cancelar (motivo + gerente) | gesto: EXCEÇÃO ASSINADA | Balcão | Operação | desktop · tablet na mão | funde com EXCEÇÃO ASSINADA + ANOTAR (assinatura só se paga) | P66 |
| d. Diálogo "pago online" | estado | Balcão | Operação | desktop · tablet na mão | some (vira estado do item; o gesto é só Entregar) | P62 |
| `/display` tela do cliente (boas-vindas, venda, pagamento com QR, resultado) | MONITOR | Balcão | Operação | parede | mantém (2º monitor do desktop; não existe no tablet) | P06, P57 |
| Leitor de ticket da cozinha (global, sem tela própria) | gesto: LOCALIZAR | Balcão | Operação | desktop | mantém (leitura de código global; o "Pronto" é o mesmo do Passe) | P38, P70 |
| N1. Balcão no tablet: segundo posto sem dinheiro (fila longa, comanda de mesa, fonte em grade, comanda como folha de baixo, pagar só eletrônico) | COMPOSIÇÃO | Balcão | Operação | tablet na mão | nova tela | P30, P31, P34, P46, P48, P49 |
| N2. Retirada do dia: uma FILA + RECEBER, aberta pelo PDV e pelo Gestor (ler QR, receber saldo, entregar com desfazer) | FILA | Balcão | Operação | desktop · tablet na mão | nova tela | P60, P61, P62, Gestor P11 |
| N3. Fim do dia: corredor em sequência (fechar caixa cego, contar vitrine, pergunta de episódio, fechar o dia) | CONFERÊNCIA | Fim do dia | Operação | tablet na mão | nova tela | P22, P23, B.I. BI-26 |

---

## Gestor de pedidos

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| `/` board (3 colunas) | FILA | Passe | Operação | parede · tablet fixo | funde com a Saída da Cozinha no posto Passe (`N1`); a coluna Entrada fica como FILA de aceite do Gestor; "pronto" avança sozinho quando a Cozinha conclui | P01, P03, P05, P06 |
| `/` modo tabela + seleção em lote | FILA | Escritório | Operação | desktop | mantém (exibição desktop da mesma FILA, densa, com lote) | P01, P03, P05 |
| `/` "Negociações iFood pendentes" | FILA | Escritório | Operação | desktop · celular | mantém (item no topo da fila com prazo; push ao gerente fora do passe) | P14 |
| `/` "Agendados" | LEITURA | Escritório | Operação | desktop | muda para Produção › planejar (encomendas por data e horário, `Produção N1`) | P24 |
| `/` filtros, busca, ordenar, CSV, imprimir | gesto: LOCALIZAR | Escritório | Operação | desktop | mantém (busca filtra ao digitar; só recortes que mudam o trabalho; ordem fixa por urgência; CSV e imprimir como ação rara) | P15, P26 |
| `/` overlay de identificação (PIN/crachá/estação travada) | transversal | Todos | — | desktop · tablet fixo · tablet na mão · celular | funde com Kit trava (C03) | P28 |
| Diálogo Recusar | gesto: ANOTAR | Passe | Operação | tablet fixo | funde com ANOTAR único (o mesmo do detalhe; iFood com motivo codificado) | P04 |
| Diálogo Saída para entrega (board) | FILA | Passe | Operação | tablet fixo | muda para Passe (despachar: troco e maquininha como estado do item, desfazer por N s) | P07 |
| Diálogo Entregador voltou | CONFERÊNCIA | Passe | Operação | tablet fixo · desktop | mantém (CONFERÊNCIA por exceção no Passe: o que bate fecha sozinho) | P08, P09 |
| a. Diálogo Acerto | CONFERÊNCIA | Passe | Operação | tablet fixo | mantém (diferença com motivo + EXCEÇÃO ASSINADA) | P10 |
| b. Diálogo Pagamento na retirada | FOCO | Balcão | Operação | tablet fixo · desktop | funde com RECEBER da retirada única (`PDV N2`) | P11 |
| Sino de alertas, sino de notificações, som/Ciente | gesto: AVISO | Passe | Operação | celular · tablet fixo | funde com AVISO único (item na fila do dono + push; "visto" e som no servidor; NFC-e com o motivo da SEFAZ no item) | P02, P13, P25 |
| Sinal de canal na fila | gesto: INTERRUPTOR | Passe | Operação | parede · tablet fixo | mantém (estado no topo da fila, com o interruptor ao lado) | P27, K07 |
| `/:ref` detalhe | FILA | Todos | Operação | celular · tablet na mão | mantém (painel no tablet, tela cheia no celular; volta com contexto) | P15, P22, P23 |
| `/:ref` nota da cozinha (editor) | gesto: ANOTAR | Passe | Operação | tablet fixo · tablet na mão | mantém (tags = lista curta da casa + texto) | P16 |
| `/:ref` comentário | gesto: ANOTAR | Todos | Operação | desktop · tablet na mão · celular | funde com ANOTAR (linha do tempo do item) | P17 |
| `/:ref` painel da corrida (Machine) | FILA | Passe | Operação | tablet fixo · tablet na mão | mantém (DELEGAR como estado do item do Passe) | P21 |
| `/:ref` negociações iFood | FILA | Escritório | Operação | desktop | funde com o item de negociação da fila (mesmo prazo, mesma decisão) | P14 |
| `/:ref` diálogo Recusar/Cancelar (com presets) | gesto: ANOTAR | Todos | Operação | tablet na mão | funde com ANOTAR + EXCEÇÃO ASSINADA (cancelar pago pede assinatura) | P04, P18, P19 |
| `/:ref` diálogo saída (versão do detalhe) | FILA | Passe | Operação | tablet fixo | some (duplicata do despacho; o detalhe abre o mesmo gesto do Passe) | P07 |
| `/:ref` diálogo acerto | CONFERÊNCIA | Passe | Operação | tablet fixo | some (duplicata do acerto do board) | P10 |
| `/:ref` diálogo de gerente | gesto: EXCEÇÃO ASSINADA | Todos | Operação | tablet na mão · desktop | funde com EXCEÇÃO ASSINADA (Kit C08) | P19 |
| `/:ref` recibos de aviso, contato/relay | LEITURA | Todos | Operação | celular | mantém (no detalhe; reenviar link como ação frequente) | P20, P22, P23 |
| `/catalog` matriz produto × canal | CADASTRO | Escritório | Ajustes | desktop | mantém em Ajustes (pausar sai do escritório: automático + interruptor no posto, `N3`) | C01, C02, C03, C04, C09, C16 |
| `/catalog` pills de coleção (arrastar) | CADASTRO | Escritório | Ajustes | desktop | mantém | C07, C08 |
| `/catalog` edição de preço na célula | CADASTRO | Escritório | Ajustes | desktop | mantém (edição em linha do campo mais frequente) | C03 |
| `/catalog` barra de lote + prévia publicação + prévia preço | CADASTRO | Escritório | Ajustes | desktop | mantém (revisão antes de confirmar) | C05, C06 |
| `/catalog` rascunho de ordem em conflito | estado | Escritório | Ajustes | desktop | mantém | C07, C08 |
| `/catalog` lightbox de foto | CADASTRO | Escritório | Ajustes | desktop · celular | mantém | C11 |
| `/catalog` painel do produto: Geral · Preço e config · Ingredientes e nutrição · Redes sociais · Fiscal | CADASTRO | Escritório | Ajustes | desktop | mantém ("N campos alterados · Salvar") | C10, C11, C12, C13, C14, C15 |
| `/catalog?sku=&tab=` | CADASTRO | Escritório | Ajustes | desktop | mantém (bilhete de volta do AVISO fiscal) | C14 |
| a. `/feeds` cards de canais de venda: toggle | gesto: INTERRUPTOR | Passe | Operação | tablet fixo · celular | muda para Passe e celular do gerente (interruptor no posto da urgência; o card de Ajustes continua mostrando o estado) | K01, K07 |
| b. `/feeds` cards de canais de venda: saúde, iFood loja | CADASTRO | Escritório | Ajustes | desktop | mantém | K02, K07 |
| `/feeds` cards de feeds/TV (coleções, rotação, automático, mensagens, abrir saída) | CADASTRO | Escritório | Ajustes | desktop | mantém | K04, K05, K06, K08 |
| `/feeds` diálogo do toggle (período, calendário, motivo, gerente) | gesto: INTERRUPTOR | Dono em movimento | Operação | celular · tablet na mão | funde com INTERRUPTOR + EXCEÇÃO ASSINADA (motivo de lista curta) | K01 |
| `/feeds` parear TV (endereço + QR) | CADASTRO | Parede | Ajustes | celular | mantém | K03 |
| `/feeds?focus=<ref>` | CADASTRO | Escritório | Ajustes | tablet na mão · desktop | mantém (bilhete de volta vindo da fila) | K02, K07 |
| `/channels/:ref/catalog` revisão de vínculos | CONFERÊNCIA | Escritório | Ajustes | desktop | mantém (de-para por exceção) | K09 |
| `/customers` lista + filtros | CADASTRO | Escritório | Ajustes | desktop | mantém | U01 |
| `/customers/:ref` ficha + candidatos | CADASTRO | Escritório | Ajustes | desktop | mantém (edição de nome/contato hoje no Admin, U05) | U02, U05 |
| `/customers/:ref` diálogo Unificar (busca, quem fica, prévia) | CADASTRO | Escritório | Ajustes | desktop | mantém (recebe também a unificação que hoje começa no PDV) | U03 |
| `/customers/merges` + diálogo Desfazer | CADASTRO | Escritório | Ajustes | desktop | mantém | U04 |
| N1. Passe: uma fila de saída (Gestor + Saída da Cozinha): preparo, prontos, entregar/despachar com desfazer, DANFE como efeito | FILA | Passe | Operação | tablet fixo · celular · parede | nova tela | P01, P05, P07, P12, Cozinha K14, K15, K16, K17, K18, K19 |
| N2. Gestor › Canais › Avisos transacionais (pedido, pagamento, fila, fidelidade ligados ao modelo aprovado) | CADASTRO | Escritório | Ajustes | desktop | nova tela | Marketing M31 |
| N3. Pausa automática por esgotado (fato com desfazer) + interruptor de produto no Passe e no celular do gerente | gesto: INTERRUPTOR | Passe | Operação | tablet fixo · celular | automatiza (L1) | C01, C02 |

---

## Cozinha (KDS), Shopman Apps e chrome comum

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| KDS `/` lista de estações | CADASTRO | Estação | Ajustes | tablet fixo | funde com Kit "iniciar este dispositivo" (o tablet provisionado abre direto na sua estação) | K01 |
| KDS `/` vazio "Nenhuma estação configurada" | estado | Escritório | Ajustes | desktop | mantém (estado com saída para quem resolve) | K01 |
| KDS `/<ref>` preparo, grade com próximo destacado | FILA | Estação | Operação | tablet fixo · celular | mantém (4 a 6 em foco + "+N" + "A fazer"; no celular da estação pequena 1 em foco + 3 a 5 linhas, com push e vibração) | K02, K03, K04 |
| Card: pendente / em preparo (armando) / finalizando com Desfazer / bloqueado por cancelamento / prévia | FILA | Estação | Operação | tablet fixo · celular | mantém (bloqueio de pagamento e falta de estoque no card antes do toque, L3; quem pegou visível) | K03, K04, K05, K09, K10, K11, K12 |
| Faixa "A fazer" | FILA | Estação | Operação | tablet fixo · parede | mantém (agregado do excedente, com o que já está pronto na vitrine) | K08 |
| Cartões vermelhos de cancelamento | gesto: AVISO | Estação | Operação | tablet fixo · celular | mantém (ciência por ticket, no servidor) | K10 |
| Seletor de data (prévia, somente leitura) | LEITURA | Escritório | Operação | desktop · tablet na mão | muda para Produção › planejar (quem executa o hoje não planeja) | K09 |
| Diálogo detalhe do pedido | FILA | Estação | Operação | celular | some (no tablet o card já é o pedido inteiro; no celular é o item em foco expandido) | K07 |
| Diálogo "Concluídos recentes" | FILA | Estação | Operação | tablet fixo | mantém (reabrir até 30 min) | K06 |
| Busca + "Nenhum pedido para X" + Limpar busca | gesto: LOCALIZAR | Passe | Operação | tablet fixo · celular | funde com LOCALIZAR da suíte (código, câmera) | K23 |
| Vazio "Tudo em dia" (som ligado/desligado + "Ligar o som") / "Nada agendado" | estado | Estação | Operação | tablet fixo | mantém (diz se vai avisar) | K02, K21 |
| Botão som (ativo / desligado / bloqueado) + "Visto" | gesto: INTERRUPTOR | Estação | Operação | tablet fixo | automatiza (L1) (som lido de `sound_enabled` da estação; "visto" no servidor, igual em todas as telas da estação) | K20, K21 |
| Densidade (3 níveis) | transversal | Estação | Ajustes | tablet fixo | some (densidade derivada do posto, fixada pela atenção) | K22 |
| Estação removida (404) | estado | Estação | — | tablet fixo | mantém (volta à lista) | K25 |
| Sem conexão com cache / sem conexão sem cache | estado | Todos | — | tablet fixo · celular | mantém | K25 |
| KDS `/<ref>` Saída: "Em preparo" + "Prontos para sair" | FILA | Passe | Operação | tablet fixo · celular | muda para Passe (fila de saída única com o Gestor, `Gestor N1`) | K14, K15, K16, K17, K18, K19 |
| Card Saída: pronto / bloqueado (rótulo+motivo) / prévia / itens expandidos | FILA | Passe | Operação | tablet fixo · celular | muda para Passe (Entregar e Despachar ganham desfazer; notas visíveis na conferência) | K16, K17, K18, K19 |
| Card Em preparo: chips por estação, "Pronto" da estação sem tela, papel não imprimiu | FILA | Passe | Operação | tablet fixo | muda para Passe | K14, K15 |
| Saída vazia | estado | Passe | Operação | tablet fixo | muda para Passe | K14 |
| Banner pedido de teste (preparo e Saída) | estado | Estação | Operação | tablet fixo · celular | mantém | K13 |
| KDS `/pickup` painel público (ao vivo / atualiza sozinho) | MONITOR | Parede | Operação | parede | mantém (12 a 24 códigos; saída declarada; tela acesa) | K24, C17 |
| Rotas antigas `/estacao/*`, `/cliente`, `/retirada`, `/expedicao` → 301 | estado | Estação | — | tablet fixo · parede | mantém (301 preserva bookmark de kiosk) | — |
| Hub: grade de tiles | FILA | Todos | Operação | celular · tablet na mão · desktop | funde com "Precisa de você", a fila das filas (soma das filas do operador, com o item exato; para quem tem um app só, nem aparece) | H01, C16 |
| Hub: vazio sem apps | estado | Todos | — | celular | mantém (diz a quem pedir acesso) | H02 |
| Hub: sessão expirou / estação travada / sem acesso / indisponível (+Tentar de novo) | estado | Todos | — | celular · tablet na mão · desktop | mantém (cada causa com sua saída) | H02, C14 |
| Hub: avisos deste dispositivo + versão | CADASTRO | Dono em movimento | Ajustes | celular | mantém (Ajustes pessoais) | H03, H04 |
| Kit: login com senha (página) | transversal | Todos | — | desktop · tablet na mão · celular | mantém | C01 |
| Kit: trava (lista + PIN, crachá) | transversal | Todos | — | tablet fixo · desktop | mantém | C03, C04 |
| Kit: troca de PIN voluntária / forçada | transversal | Todos | — | tablet fixo · desktop | mantém | C05, C06 |
| Kit: "Perdi meu crachá" | transversal | Todos | — | tablet fixo · desktop | mantém | C07 |
| Kit: autorização do gerente (diálogo) | gesto: EXCEÇÃO ASSINADA | Todos | Operação | desktop · tablet fixo · tablet na mão | mantém (é a peça única da EXCEÇÃO ASSINADA; zero passos com gerente logado) | C08 |
| Kit: iniciar este dispositivo (oferta de estação) | transversal | Todos | Ajustes | tablet fixo · desktop | mantém (estendido a todos os postos, KDS incluído) | C02 |
| Kit: sessão indisponível | estado | Todos | — | desktop · tablet fixo · tablet na mão · celular | mantém | C14 |
| Kit: faixa offline | estado | Todos | — | desktop · tablet fixo · tablet na mão · celular | mantém | C14 |
| Kit: convite de instalação / de push | transversal | Todos | — | celular · tablet na mão | mantém (push passa a ser pedido no KDS do celular e no Dono em movimento) | C10, C11 |
| Kit: aviso de versão nova / troca automática no ocioso | estado | Todos | — | desktop · tablet fixo · tablet na mão · celular | mantém | C12 |
| Kit: rail (voltar ao hub, Estações, operador/travar, capacidade, tema, giro) | transversal | Todos | — | tablet fixo · desktop · celular (gaveta) | mantém (capacidade, giro e versão saem do chrome do cozinheiro para Ajustes) | C04, C13, C15, C16, C17 |
| Kit: sino de avisos + log de acessos (só Gestor) | gesto: AVISO | Todos | Operação | celular · desktop | funde com AVISO único nos oito apps (hoje só no Gestor) | C09 |
| N1. Cozinha: visão "todas as estações" (o que está atrasado em qualquer estação; corrigir) | FILA | Estação | Operação | tablet na mão | nova tela | K14, K06 |
| N2. Cozinha: quadro de estação em TV (6 a 8 tickets, gesto no tablet pequeno ou no leitor) | MONITOR | Parede | Operação | parede | nova tela | K02, K15 |
| N3. Cozinha: alerta de atraso no celular do gerente (push, sem quadro) | gesto: AVISO | Dono em movimento | Operação | celular | nova tela | K14 |

---

## Produção

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| `/plan` grade (Sugerido · Planejado), seletor de data, filtro por ficha-base | CONFERÊNCIA | Escritório | Operação | desktop · tablet fixo | mantém (sugestão já preenchida como plano; ao lado: sobra/falta e projeção do B.I., falta de insumo antes do gesto, encomendas do dia) | P01, P03, P04 |
| `/plan` diálogo Planejar / Ajustar / Novo lote | CONFERÊNCIA | Escritório | Operação | desktop · tablet fixo | funde com a grade (edição em linha) | P01, P03, P04 |
| `/plan` diálogo "Por que N?" | CONFERÊNCIA | Escritório | Operação | desktop · tablet fixo | funde com a linha ("a conta da sugestão" inline, com o número do B.I.) | P02 |
| Diálogo Encomendas comprometidas | CONFERÊNCIA | Escritório | Operação | desktop · tablet fixo | funde com a linha (o chip "N un." abre no lugar) | P06 |
| `ShortageDialog` (insumo / encomendas, motivo de autorização) | gesto: EXCEÇÃO ASSINADA | Forno | Operação | tablet fixo · desktop | funde com EXCEÇÃO ASSINADA (a falta aparece antes do gesto, L3; fecha o defeito do diálogo parado em `order_shortage`) | P05 |
| `/` Produção grade (Planejado · Produzido) | CONFERÊNCIA | Forno | Operação | tablet fixo | mantém (o planejado é o real por padrão; confirma-se o conjunto) | P12 |
| `/` diálogo "Quanto foi produzido?" | CONFERÊNCIA | Forno | Operação | tablet fixo | some (a quantidade já escrita é o real; só a exceção abre o número) | P12 |
| `/` diálogo Produzido (conferência + estorno) | gesto: EXCEÇÃO ASSINADA | Forno | Operação | tablet fixo | funde com EXCEÇÃO ASSINADA (estornar produção) | P13 |
| `/mise-en-place` Por insumo (checklist, saldo, explodir, quebra por receita) | CONFERÊNCIA | Forno | Operação | celular · tablet na mão | mantém (checklist no servidor, L7; separação registrada) | P07 |
| `/mise-en-place` Por preparo (cartões com código cego) | FOCO | Forno | Operação | tablet fixo | mantém (pesagem registrada: rastreabilidade) | P08 |
| `ProductionLabelPrintDialog` (prévia mm, destino, estados do job, confirmação física, fallback navegador) | gesto: AVISO | Forno | Operação | tablet fixo · desktop | automatiza (L1) (etiqueta é efeito colateral do ato; só a falha vira AVISO) | P09, P10, P11 |
| `/expedite` painel Expedição (cards, alarme, aviso de dias anteriores, menu ⋯) | FILA | Forno | Operação | tablet fixo · parede | mantém (porta de entrada do forneiro; esquecidas como itens com dono) | P14, P15, P16, P17, P18 |
| `/expedite` diálogo Timer do forno (numpad, correndo, tocando) | FILA | Forno | Operação | tablet fixo | mantém (timer no servidor, toca em todos os tablets do fournil, L7) | P14, P15 |
| `/expedite` sheet Lote avulso (lista de receitas) | CONFERÊNCIA | Forno | Operação | tablet fixo | mantém | P17 |
| `QcCloseScreen` fechamento (graus, perda, sheet de motivos, overshoot) | CONFERÊNCIA | Forno | Operação | tablet fixo | mantém (por exceção; perda com ANOTAR) | P16, P17 |
| `/expedite#quality` aba Qualidade (aguardando revisão / revisada) | FILA | Dono em movimento | Operação | celular · desktop | muda para a FILA do gestor no celular (sai do tablet do forno) | P19 |
| `QcCloseScreen` modo correção | CONFERÊNCIA | Escritório | Operação | tablet na mão · desktop | mantém (gestor) | P20 |
| `/timers` Disparar + Em andamento; `FloorTimerCreateDialog` | FILA | Forno | Operação | tablet fixo · parede | mantém (timers no servidor) | P21, P22, P23 |
| Botão de timers no cabeçalho (contador) | gesto: AVISO | Forno | Operação | tablet fixo | mantém | P23 |
| `AlertsBell` | gesto: AVISO | Todos | Operação | celular · tablet fixo · desktop | funde com AVISO único (push no celular do gerente) | P26 |
| `/board` letreiro (kiosk, tela cheia, paginação, sem sinal) | MONITOR | Parede | Operação | parede | mantém (saída declarada; "amanhã tem?" vai ao LOCALIZAR do PDV) | P24, P25 |
| `/reports` Gestão do dia (KPIs, atrasos) | LEITURA | Escritório | Ajustes | desktop · celular | mantém (olhada no celular) | P27 |
| `/reports` relatórios por período (4 abas, filtros, paginação, CSV, "relatório mudou") | LEITURA | Escritório | Ajustes | desktop | mantém (rolagem no lugar de paginação; CSV como ação rara) | P28, P29, P30 |
| `/reports` mapa código-cego (sem perm: estado calmo) | gesto: LOCALIZAR | Escritório | Ajustes | desktop | funde com LOCALIZAR (código) | P31 |
| `/recipes` lista (filtros, favoritas, sem permissão) | CADASTRO | Escritório | Ajustes | desktop · tablet na mão | mantém | P32, P33 |
| `/recipes/[ref]` lente, linha do tempo, nota, referências, diálogos publicar/dados/arquivar, SKU inline | CADASTRO | Escritório | Ajustes | desktop · tablet na mão | mantém (leitura no tablet da bancada; tempo de forno medido chega como proposta, `B.I. N3`) | P34, P38, P39, P41, P42, P43, P44 |
| `/recipes/[ref]/edit` editor + prévia da lente + padronizar 1000 g | COMPOSIÇÃO | Escritório | Ajustes | desktop | mantém | P37 |
| `/recipes/new` Anotação / Foto / Manual, conferência do rascunho lido, estado 503 | COMPOSIÇÃO | Escritório | Ajustes | celular · desktop | mantém (foto no celular, conferência no desktop) | P35, P36 |
| `/recipes/compare` | LEITURA | Escritório | Ajustes | desktop | mantém | P40 |
| Estados transversais: carregando, erro, "sem atualizar", offline, resync, PIN/lock, atalhos | estado | Todos | — | desktop · tablet fixo · tablet na mão · celular | funde com os estados do Kit | P45 |
| Rotas legadas `/planejamento` `/preparacao` `/expedicao` `/painel` → 301 | estado | Forno | — | tablet fixo · parede | mantém (301 preserva bookmark de kiosk) | — |
| N1. Planejar: encomendas por data e horário (recebe "Agendados" do Gestor e a prévia de data da Cozinha) | CONFERÊNCIA | Escritório | Operação | desktop · tablet fixo | nova tela | P01, P06, Gestor P24, Cozinha K09 |

---

## Compras

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| Login / bloqueio de operador / sessão indisponível | transversal | Todos | — | desktop · tablet na mão · celular | mantém (portaria do Kit) | — |
| Banner "Conectando" / backend fora / 403 / erro de ação | estado | Todos | — | desktop · tablet na mão · celular | mantém | — |
| Painel (cartões, fila de decisão, fila vazia explicada, atalhos) | FILA | Escritório | Ajustes | desktop · celular | mantém (fila do comprador, entrada do andar Comprar) | C01 |
| Comprar: lista de reposição | FILA | Escritório | Ajustes | desktop | mantém (pedido agrupado por fornecedor; fecha o defeito `request_status = "sent"`) | C02, C03 |
| Comprar: fila vazia explicada (4 motivos) | estado | Escritório | Ajustes | desktop | mantém | C02, C20 |
| Comprar: aside Consolidação | FILA | Escritório | Ajustes | desktop | funde com o cabeçalho do grupo por fornecedor (total e nº de fornecedores no lugar) | C04 |
| Receber: rascunho em branco (convite) | FOCO | Doca | Operação | celular · tablet na mão | mantém (rascunho no servidor, L7) | C06, C17 |
| Receber com NF: chave/QR/colar/foto | FOCO | Doca | Operação | celular | mantém | C06 |
| Diálogo Escanear NF (câmera, lanterna) | FOCO | Doca | Operação | celular | funde com LOCALIZAR por câmera da suíte (o mesmo leitor) | C06 |
| Receber sem NF: referência em papel | COMPOSIÇÃO | Doca | Operação | celular · tablet na mão | mantém | C17 |
| Fornecedor da entrada (seletor + documento) | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | automatiza (L1) (vem do CNPJ da NF; seletor só sem NF) | C07 |
| Lista de itens da entrada (status por linha) | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | mantém (por exceção: o que bate entra sozinho; acaba o ok linha a linha) | C10, C13, C14 |
| Gaveta do item: insumo/sugestão | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | mantém (só linha sem de-para; a casa aprende) | C08 |
| Gaveta: conversão (Confere / Não é assim / Cadastrar embalagem / Escolher) | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | mantém | C09 |
| Gaveta: quantidade, valor, validade, lote, ocorrência, estoque depois, divergência fiscal | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | mantém (ocorrência por ANOTAR; divergência fiscal mostrada aqui, correção no Gestor › Catálogo › Fiscal) | C10, C11, C12, C29 |
| Painel Conferência (pendências, ressalva geral, Confirmar, Registrar devolução) | CONFERÊNCIA | Doca | Operação | celular · tablet na mão | mantém (selo que aponta a primeira pendência) | C14, C15, C16 |
| Aviso de resultado (entrada confirmada / devolução registrada) | estado | Doca | Operação | celular · tablet na mão | mantém (encadeia a próxima nota) | C15, C16 |
| Histórico de recebimentos (projetado em `receiptHistory`, sem tela) | LEITURA | Doca | Operação | celular · tablet na mão | nova tela (responde "já entrou?" na porta) | C18 |
| Base › Insumos: tabela + mínimos em lote | CADASTRO | Escritório | Ajustes | desktop | mantém | C19, C20 |
| Base › Insumos: painel do item (problemas, Permitir revenda, Quando aberto vira, receitas) | CADASTRO | Escritório | Ajustes | desktop | mantém | C21, C22, C23 |
| Base › Fornecedores: cartões + detalhe (contatos, carteira) | CADASTRO | Escritório | Ajustes | desktop · celular | mantém (celular para ligar) | C24 |
| Base › Custos: tabela do fornecedor (lote) | CADASTRO | Escritório | Ajustes | desktop | mantém (porta única do custo de insumo) | C25 |
| Base › Custos: Lançar custo avulso | CADASTRO | Escritório | Ajustes | desktop | funde com a tabela de custos (uma porta para custo) | C26 |
| Base › Custos: custos por fornecedor (Usar padrão) | CADASTRO | Escritório | Ajustes | desktop | funde com a tabela de custos | C27 |
| Base › Contagem: sem permissão | estado | Estoque | Operação | tablet na mão · celular | muda para Estoque | C28 |
| Base › Contagem: tabela | CONFERÊNCIA | Estoque | Operação | tablet na mão · celular | muda para Estoque (`N3`, CONFERÊNCIA cega, rascunho no servidor) | C28 |
| Diálogo Confirmar contagem (lista de ajustes) | CONFERÊNCIA | Estoque | Operação | tablet na mão · celular | muda para Estoque (selo com assinatura do gerente) | C28 |
| Atalho por URL `?view=` | transversal | Todos | — | desktop · tablet na mão · celular | mantém (porta do Hub, agora por andar e posto) | C01 |
| N1. "A caminho": pedidos enviados esperando entrega, abatidos pelo recebimento | FILA | Doca | Operação | celular · desktop | nova tela | C03, C15 |
| N2. Aprovar pedido de compra (endpoint `/approve/` sem botão), item na fila de decisões do dono | FILA | Dono em movimento | Operação | celular · desktop | nova tela | C05 |
| N3. Estoque: contagem cega como posto próprio (gerente, câmara fria) | CONFERÊNCIA | Estoque | Operação | tablet na mão · celular | nova tela | C28 |

---

## Marketing

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| `/` (redireciona 301 para `/v2?area=today`) | estado | Dono em movimento | — | celular · desktop | some (a raiz passa a ser a FILA de decisões, `N1`) | — |
| `/v2?area=today` Hoje: contadores, 4 pendentes, conexões com atenção, link histórico | FILA | Dono em movimento | Operação | celular · desktop | funde com a FILA de decisões (`N1`) | M01 |
| `/v2?area=today` erro de board / dados não frescos | estado | Dono em movimento | Operação | celular | funde com os estados da FILA de decisões | M01 |
| `/v2?area=campaigns` destinos ativos + 5 campanhas + Nova campanha + Modelos | CADASTRO | Escritório | Ajustes | desktop | mantém em Ajustes | M16, M19 |
| `/v2?area=offers` lista de ofertas/cupons, Criar, campanha com oferta | CADASTRO | Escritório | Ajustes | desktop | mantém (ganha editar e desativar, `36d`) | M26, M27, M28 |
| Diálogo Criar oferta / Criar cupom (`MarketingOfferForm`) | CADASTRO | Escritório | Ajustes | desktop | mantém | M26, M27 |
| `/v2?area=platforms` catálogo de destinos com estado e formatos | CADASTRO | Escritório | Ajustes | desktop | funde com `/platforms` (uma tela de plataformas) | M29 |
| `/campaigns` lista com busca, filtros, paginação, liga/desliga, editar, preparar disparo | CADASTRO | Escritório | Ajustes | desktop · celular | mantém (rolagem no lugar de paginação; o interruptor também no celular, em Operação) | M17, M18, M19, M20 |
| `/campaigns?new=1` / editar → `CampaignForm` (etapas 1 a 5) | COMPOSIÇÃO | Escritório | Ajustes | desktop | mantém (recebe o filtro do evento, hoje só no Admin) | M16, M17, M21, M22 |
| Estado rascunho em conflito (`DraftRecoveryNotice`) | estado | Escritório | — | desktop · celular | automatiza (L1) (rascunho no servidor, L7; o conflito some como estado comum) | M36 |
| `FireCampaignPanel` ("Definir público") com contagem viva, exclusões, produto | COMPOSIÇÃO | Escritório | Operação | desktop · tablet na mão · celular | mantém (audiência "em risco" do B.I. pronta como público) | M20 |
| Erros do disparo (409, 429, contagem falhou, zero) | estado | Escritório | Operação | desktop · celular | mantém | M20 |
| `/templates` lista / vazio | CADASTRO | Escritório | Ajustes | desktop | mantém | M23 |
| `AnnouncementTemplateForm` + `PlatformCompositionEditor` + `GoogleBusinessPostOptions` + prévia | COMPOSIÇÃO | Escritório | Ajustes | desktop | mantém | M23, M24 |
| Diálogo Apagar modelo (em uso / livre) | gesto: SELO / DESFAZER | Escritório | Ajustes | desktop | mantém (dependências visíveis antes do gesto) | M25 |
| `/announcements/:id` → `AnnouncementCard` (pendente) | FILA | Dono em movimento | Operação | celular | funde com a FILA de decisões (o item aberto) | M02, M03, M04, M07, M08 |
| Prévia simulada por plataforma (`AnnouncementPreview`, `AnnouncementSimulatedPreview`) | FILA | Dono em movimento | Operação | celular | mantém (dentro do item) | M06 |
| Bloco sugestão de IA | COMPOSIÇÃO | Dono em movimento | Operação | celular | mantém | M05 |
| Silêncio do WhatsApp / ensaio local / horário ambíguo | estado | Dono em movimento | Operação | celular | mantém | M08 |
| Prazo vencido | estado | Dono em movimento | Operação | celular | mantém | M03 |
| Diálogo Recusar (motivo) | gesto: ANOTAR | Dono em movimento | Operação | celular | funde com ANOTAR | M10 |
| `MarketingCommandConfirmationDialog` (resumo / `ENVIAR N` / senha / TOTP / duplo controle / reautenticação) | gesto: SELO / DESFAZER | Dono em movimento | Operação | celular | mantém (uma confirmação só quando autor = aprovador, L4) | M09 |
| Faixa de resultado + `AnnouncementResultPanel` (acompanhamento por plataforma) | FILA | Dono em movimento | Operação | celular · desktop | mantém (item "em andamento" até assentar) | M11 |
| a. Recuperação: Repetir falhas | gesto: EXCEÇÃO ASSINADA | Escritório | Operação | desktop | mantém (só falhas seguras, com desafio) | M12 |
| b. Recuperação: Consultar incerto | FILA | Escritório | Operação | desktop | automatiza (L1) (consulta sem efeito; o sistema reconcilia sozinho) | M13 |
| c. Recuperação: Cancelar com motivo | gesto: ANOTAR | Dono em movimento | Operação | celular · desktop | mantém (ação no item agendado) | M14 |
| `/announcements/:id` erro de carga / não encontrado | estado | Dono em movimento | — | celular · desktop | mantém | — |
| `/campaign/announcements/:id` (alias que redireciona) | estado | Dono em movimento | — | celular | mantém (links antigos de notificação) | M02 |
| `/history` (filtros, lista, vazio, erro parcial, carregar mais) | LEITURA | Escritório | Ajustes | desktop | mantém | M34 |
| `/platforms` sem plataforma (redireciona) | estado | Escritório | Ajustes | desktop | funde com a tela única de plataformas | M29 |
| a. `/platforms?platform=whatsapp`: estado, modelo aprovado do anúncio, teste seguro, recibo | CADASTRO | Escritório | Ajustes | desktop · celular | mantém (celular de teste na mão) | M30, M32, M33 |
| b. `/platforms?platform=whatsapp`: avisos automáticos (pedido, pagamento, fila, fidelidade) | CADASTRO | Escritório | Ajustes | desktop | muda para Gestor › Canais (Ajustes) (`Gestor N2`) | M31 |
| `/platforms?platform=instagram\|facebook\|google_business` modal | CADASTRO | Escritório | Ajustes | desktop | funde com a tela única de plataformas (estado e motivo) | M29 |
| Diálogo confirmar modelo (TOTP) | gesto: SELO / DESFAZER | Escritório | Ajustes | desktop | mantém | M30, M31 |
| Sino (Novo/Visto/Resolvido/Expirado, Revisar, Visto, carregar mais) | gesto: AVISO | Dono em movimento | Operação | celular | funde com a FILA de decisões (sino e fila são a mesma lista) | M02, M35 |
| `error.vue` | estado | Todos | — | desktop · celular | mantém | — |
| `/health/*`, `/sse/notifications`, `/api/v1/**` (BFF) | estado | Todos | — | desktop · celular | mantém (infraestrutura, não é tela) | — |
| `visual/VisualBoardPage.vue` (`MarketingBoard`) | estado | Escritório | — | desktop | some (sobra de código; a fila que mostrava ganha casa em `N1`) | — |
| a. (sem tela) Reagendar anúncio | FILA | Dono em movimento | Operação | celular · desktop | nova tela (ação no item agendado) | M15 |
| b. (sem tela) Congelar efeitos externos | gesto: INTERRUPTOR | Dono em movimento | Operação | celular | nova tela (botão de pânico) | M37 |
| c. (sem tela) Duplo controle solicitado | FILA | Dono em movimento | Operação | celular | nova tela (item na fila do segundo aprovador) | M09 |
| d. (sem tela) Editar / desativar oferta e cupom | CADASTRO | Escritório | Ajustes | desktop | nova tela (ação no cadastro de ofertas) | M26, M27 |
| e. (sem tela) Filtro do evento das campanhas automáticas (só Admin) | COMPOSIÇÃO | Escritório | Ajustes | desktop | funde com `CampaignForm` (etapa do evento) | M21 |
| f. (sem tela) `notify_users` | gesto: AVISO | Dono em movimento | Operação | celular | funde com AVISO único | M02 |
| N1. FILA de decisões: anúncios esperando o sim, ordenados por prazo (é Hoje, sino e push ao mesmo tempo) | FILA | Dono em movimento | Operação | celular · desktop | nova tela | M01, M02, M03, M11, M14, M35 |
| N2. Cerimônia do disparo e mínimo de público do WhatsApp (Admin › Loja › Integrações; sem linha no original) | CADASTRO | Escritório | Ajustes | desktop | mantém (Admin, fora do app) | M38 |

---

## B.I.

| tela / estado | forma | posto | andar | dispositivos | destino | trabalhos |
|---|---|---|---|---|---|---|
| `OperatorLogin` / `OperatorLock` / `OperatorSessionUnavailable` | transversal | Todos | — | desktop · celular | mantém (gate do Kit) | BI-25 |
| `/` Produção (carregando / erro / sem medição / com dados) | LEITURA | Escritório | Ajustes | desktop · celular | mantém (estudo semanal; painel "por forno" some, a casa tem um forno; tempo de forno vira proposta na receita, `N3`) | BI-01, BI-02 |
| `/sales` Vendas (com/sem histórico Yooga, conflito de fonte) | LEITURA | Escritório | Ajustes | desktop · celular | mantém (resumo de uma frase no celular; uma leitura por pergunta) | BI-03, BI-04, BI-05 |
| `/cash` Caixa (403 sem `audit_shift`; sem fechamento; contas na casa; anomalias) | LEITURA | Escritório | Ajustes | desktop | mantém (quebra e anomalia de gaveta também empurradas como AVISO ao celular; aprofundar até o turno) | BI-06, BI-07, BI-08, BI-09 |
| `/customers` Clientes | LEITURA | Escritório | Ajustes | desktop | mantém ("em risco" vai ao Marketing como audiência pronta) | BI-10 |
| `/profiles` Perfis (filtros dia/faixa; select de leitura; cobertura baixa) | LEITURA | Escritório | Ajustes | desktop | mantém (uma precisão por pergunta, não três) | BI-11, BI-20 |
| `/explore` Explorar (série / ranking / tabela 2 eixos / truncado / erro / vazio) | LEITURA | Escritório | Ajustes | desktop | mantém (filtro por valor, comparação com período anterior, perguntas curadas visíveis) | BI-12, BI-14 |
| `/explore` menu ⋯ (salvar / favoritar / apagar) | CADASTRO | Escritório | Ajustes | desktop | mantém | BI-13 |
| `/forecast` horizonte dia (fechado / com ocasião / sem ocasião / sem base) + "e se" + troco | LEITURA | Escritório | Operação | celular · tablet na mão | muda para Produção › planejar (ao lado da sugestão) e PDV › abrir caixa (troco), EXPLICAR-NO-LUGAR | BI-15, BI-17 |
| `/forecast` horizonte semana/mês (total / ausente por dia sem base) | LEITURA | Escritório | Ajustes | desktop | mantém (planejamento de compras e escala) | BI-16, BI-17 |
| `/scenarios` (desligado sem credencial / gerando / falhou / relatórios) | LEITURA | Escritório | Ajustes | desktop | mantém | BI-18 |
| Barra de período (`OperatorPeriodPicker`, presets, personalizado, ‹ ›) | transversal | Escritório | — | desktop · celular | mantém (período sempre na URL) | BI-14 |
| `OfflineBanner`, `OperatorPwaRuntime` | estado | Todos | — | desktop · celular | mantém | — |
| a. Fora do app: painel do Admin com `OperatorAlert` / `BIAlertEvent` (único lugar onde alarmes aparecem) | gesto: AVISO | Dono em movimento | Operação | celular | muda para AVISO no celular do dono e na fila do papel certo | BI-21 |
| b. Fora do app: Admin `BIAlertRule`, `BIScenarioReport`, etiquetas de consumo, lugares do salão, de-para de lote | CADASTRO | Escritório | Ajustes | desktop | mantém (Admin; ver "telas sem destino claro") | BI-22, BI-23, BI-24 |
| Fora do app: comandos `ingest_yooga`, `import_holidays`, `import_weather`, `propose_consumption_tags`, `bi_calibrate`, `setup_bi_reference`, `refresh_bi_daily_series`, `evaluate_bi_alerts` | estado | Escritório | Ajustes | desktop | mantém (terminal; ver "telas sem destino claro") | BI-24 |
| Fora do app: pergunta de episódio no fechamento | gesto: ANOTAR | Fim do dia | Operação | tablet na mão | muda para Fim do dia (passo do corredor, `PDV N3`; padrão a generalizar) | BI-26 |
| N1. Sobra / falta / hora de esgotamento por produto (a pergunta nº 1 do dono) | LEITURA | Escritório | Ajustes | desktop | nova tela (e o número segue para o plano da Produção) | BI-19 |
| N2. Alarme "vai faltar" + acerto da projeção medido | gesto: AVISO | Dono em movimento | Operação | celular | nova tela | BI-15, BI-21 |
| N3. Proposta de tempo de forno na receita (medido ≠ armado, com aceitar) | CADASTRO | Escritório | Ajustes | desktop | nova tela | BI-02 |
| N4. Aprofundar até o registro (todo número abre pedido, turno, lote, produto ou cliente) | LEITURA | Escritório | Ajustes | desktop · celular | nova tela | BI-01, BI-03, BI-05, BI-06, BI-07, BI-08, BI-10, BI-19 |

---

## Trabalhos sem tela

Conferido por script contra a coluna ID do "Mapa das funcionalidades" de cada ficha (PDV 59, Gestor 58,
Cozinha/Apps/kit 46, Produção 45, Compras 29, Marketing 38, B.I. 26 = **301 IDs**; a ficha do Gestor
anuncia 59 contando a edição de cliente duas vezes, a tabela tem 58).

**Nenhum ID fica sem linha.** Todo trabalho aparece em pelo menos uma linha da matriz.

Trabalhos que **hoje não têm tela** e só estão cobertos por linha `nova tela` (a cobertura é a
promessa do plano, não o código de hoje):
- Compras **C05** (aprovar compra: endpoint sem botão), **C18** (já entrou? histórico projetado sem tela).
- Marketing **M15** (reagendar anúncio), **M37** (congelar efeitos externos); **M09** em parte (duplo
  controle solicitado); **M26/M27** em parte (editar/desativar oferta e cupom).
- B.I. **BI-19** (sobra/falta por produto: só como exemplo do Explorar), **BI-21** (alarmes: só no
  painel do Admin), **BI-02** em parte (proposta de tempo de forno na receita).
- Cozinha **K14** em parte (visão "todas as estações" para o chefe).

Trabalhos que continuam **fora dos apps** (Admin ou terminal), com destino provisório: Gestor **U05**,
Marketing **M38**, B.I. **BI-22**, **BI-23**, **BI-24**.
