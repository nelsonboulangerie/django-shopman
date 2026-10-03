# Produção — engenharia reversa por função

App: `surfaces/production-nuxt` (rotas `/plan`, `/mise-en-place`, `/` (produzir), `/expedite`, `/timers`, `/board`, `/reports`, `/recipes/*`).
Back: `shopman/backstage/api/operations.py` (views de produção), `api/_production_mutations.py`, `api/print_jobs.py`, `api/recipe_book.py`, `api/timer_tags.py`, `projections/production.py` (4.044 linhas), `services/production.py` (3.694), `services/print_jobs.py`, `services/recipe_book.py`, `services/recipe_capture.py`, `shop/services/production.py`, `shop/production_lifecycle.py`, `shop/handlers/production_alerts.py`, `packages/craftsman` (WorkOrder, Recipe, RecipeEntry/Version, `contrib/stockman/handlers.py`).

O ciclo real de um pão, como o código o modela (nomes internos entre parênteses):
**decidir quanto** (planned) → **separar e pesar** (sem estado no servidor; checklist local) → **dizer quanto massa virou peça** (started) → **forno** (fato `oven_arm`/`oven_conclude`, timer local) → **contar o que saiu, por qualidade e perda** (finished + partição QC) → **gestor confirma ou corrige a qualidade** (quality_reviewed / correction).
Efeitos no estoque (via signal `production_changed` → `craftsman/contrib/stockman`): planejar cria quant *planejado* do acabado (a loja já pode vender/encomendar contra ele); produzir move para lote `started`; finalizar consome insumos (ledger `MAKE`) e entra o acabado real com lote/grau; finalizar abre a janela da lista de espera (`waitlist.open_window`); confirmar qualidade libera os avisos de "voltou ao estoque" a clientes.

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| P01 | Decidir quanto produzir de cada produto amanhã | chefe de produção / gerente | escritório ou bancada; desktop/tablet | rotina da tarde (véspera) | 1×/dia, ~20–60 linhas | horas | PLANEJAR |
| P02 | Entender por que o sistema sugere N | chefe de produção | idem | dúvida diante da sugestão | várias por planejamento | minutos | ENTENDER |
| P03 | Corrigir ou zerar uma quantidade já planejada | chefe de produção | idem | mudou a demanda / erro | algumas/dia | horas | CORRIGIR · PLANEJAR |
| P04 | Acrescentar um lote extra a um produto que já está em produção | chefe / padeiro | bancada; tablet | acabou na vitrine, encomenda tardia | 0–5/dia | minutos | PLANEJAR |
| P05 | Resolver "a quantidade não cobre encomendas" / "faltam insumos" | chefe / gerente | onde estiver a ação | recusa do servidor (409) | raro | minutos | TRIAR · AUTORIZAR |
| P06 | Ver quais encomendas dependem desta produção | chefe / padeiro | bancada; tablet | chip "N un." na linha | algumas/dia | minutos | LOCALIZAR · ENTENDER |
| P07 | Separar os insumos do dia (lista agregada) | ajudante / padeiro | despensa/bancada; tablet ou celular | início do turno | 1×/turno, 20–60 itens | minutos | SEPARAR (novo) |
| P08 | Pesar cada preparo conforme a ficha escalada | ajudante de pesagem | bancada com balança; tablet | início do turno | 1×/preparo, 5–30/dia | minutos | SEGUIR-INSTRUÇÃO (novo) |
| P09 | Imprimir etiquetas cegas de pesagem | ajudante / chefe | bancada; tablet + etiquetadora (agente no PC) | antes de pesar | 1–3×/dia | minutos | EMITIR |
| P10 | Imprimir identificação interna do preparo (nome, data, validade) | ajudante / chefe | idem | preparo pronto para guardar | 1–3×/dia | minutos | EMITIR |
| P11 | Confirmar que as etiquetas saíram (ou reimprimir/imprimir pelo navegador) | quem imprimiu | idem | etiqueta saiu (ou não) | por impressão | segundos | CONFERIR · EMITIR |
| P12 | Dizer quantas peças a massa rendeu (vai para o forno/expedição) | padeiro | bancada; tablet | massa dividida/modelada | 1×/lote, 10–40/dia | minutos | REGISTRAR-QUANTIDADE · AVANÇAR |
| P13 | Estornar um lote produzido por engano | padeiro / chefe | bancada; tablet | erro de registro | raro | minutos | CORRIGIR |
| P14 | Armar o timer do forno de uma fornada (declara "enfornou") | forneiro | boca do forno; tablet de parede + teclado numérico | fornada entrou no forno | 10–40/dia | segundos | AVISAR · REGISTRAR-FATO (novo) |
| P15 | Atender o alarme do forno (estender / Visto) | forneiro | idem, à distância | alarme sonoro | 10–40/dia | segundos | AVISAR |
| P16 | Fechar a fornada: contar o que saiu por qualidade e perda, com motivo | forneiro / padeiro | boca do forno; tablet | fornada saiu do forno | 10–40/dia | minutos (pão esfriando, cliente esperando vitrine) | REGISTRAR-QUANTIDADE · AVANÇAR |
| P17 | Registrar um lote que não estava no plano (lote avulso) | forneiro / padeiro | idem | produziu fora do plano | 0–5/dia | minutos | REGISTRAR-QUANTIDADE |
| P18 | Fechar fornadas esquecidas de dias anteriores | chefe / forneiro | idem | aviso no painel / alerta "esquecido" | raro | horas | CORRIGIR · AVANÇAR |
| P19 | Confirmar a qualidade de um lote fechado (libera avisos a clientes) | gestor | qualquer; tablet/desktop | lote aguardando revisão | 10–40/dia | horas | APROVAR |
| P20 | Corrigir a qualidade de um lote fechado (reclassifica estoque) | gestor | idem | erro de classificação / defeito descoberto | raro | horas | CORRIGIR |
| P21 | Disparar um lembrete de chão com um toque (fermentação, descanso) | qualquer do fournil | qualquer tablet do chão | início de etapa física | dezenas/dia | segundos | AVISAR |
| P22 | Criar um timer avulso e, se quiser, guardá-lo como etiqueta da casa | qualquer do fournil | idem | etapa sem etiqueta | algumas/dia | segundos | AVISAR · CONFIGURAR |
| P23 | Ver timers correndo e silenciar o que tocou | qualquer do fournil | idem | alarme / olhar | contínuo | segundos | VIGIAR · AVISAR |
| P24 | Mostrar à loja o que sai do forno e quando (letreiro) | ninguém opera (TV) | parede da loja; TV | aberto o dia todo | contínuo | — | VIGIAR |
| P25 | Responder ao cliente "que horas sai o X?" / "amanhã tem?" | atendente | balcão; olha a TV ou abre no tablet | pergunta do cliente | dezenas/dia | segundos · **cliente esperando** | LOCALIZAR |
| P26 | Ver e reconhecer alertas de produção (atraso, esquecido, rendimento baixo, falta de insumo) | chefe / gerente | sino em toda tela | alerta gerado | algumas/dia | minutos | AVISAR · TRIAR |
| P27 | Acompanhar a gestão do dia (rendimento médio, capacidade, atrasos) | gerente / dono | escritório; desktop | rotina / dúvida | 1–3×/dia | horas | ENTENDER · VIGIAR |
| P28 | Ler histórico, produtividade, desperdício e qualidade por período | gerente / dono | desktop | rotina semanal / investigação | semanal | dias | ENTENDER |
| P29 | Exportar relatório em CSV | gerente / dono / contador | desktop | análise fora do sistema | mensal | dias | EMITIR |
| P30 | Recarregar relatório que mudou durante a paginação | gerente | desktop | aviso "o relatório mudou" | raro | minutos | ENTENDER (técnico) |
| P31 | Descobrir qual preparo corresponde a um código cego | gerente | desktop | etiqueta encontrada / auditoria | raro | minutos | LOCALIZAR |
| P32 | Achar uma receita no inventário | padeiro / chefe | bancada (tablet) ou escritório | precisa consultar/editar | várias/dia | minutos | LOCALIZAR |
| P33 | Marcar receita como favorita | qualquer leitor | idem | uso recorrente | raro | — | CONFIGURAR (pessoal) |
| P34 | Ler a fórmula de uma versão (g, %, hidratação, partes, BOM) | padeiro / chefe | bancada; tablet | vai produzir / estudar | várias/dia | minutos | ENTENDER |
| P35 | Trazer uma receita escrita (foto do caderno / texto colado) para o sistema | chefe / dono | celular (foto) ou desktop (texto) | receita nova / digitalização | semanal | dias | COMPOR |
| P36 | Começar uma receita do zero | chefe | desktop | receita nova | raro | dias | COMPOR |
| P37 | Editar o rascunho (ingredientes, insumo, quantidades, âncora, partes, etapas; padronizar 1000 g) | chefe | desktop | ajuste de fórmula | semanal | dias | COMPOR |
| P38 | Abrir nova versão a partir de uma existente | chefe | desktop | quer testar mudança | semanal | dias | COMPOR |
| P39 | Publicar a versão (vira a ficha que a produção executa) | chefe / dono | desktop | rascunho aprovado | semanal | dias | APROVAR |
| P40 | Comparar duas versões/receitas | chefe / dono | desktop | decidir mudança | raro | dias | ENTENDER |
| P41 | Associar SKU / editar nome, tipo, notas da receita | chefe | desktop | receita vira produto / correção | raro | dias | CONFIGURAR |
| P42 | Avaliar uma versão (0–5 por critério) | padeiros / chefe | tablet/desktop | provou o resultado | raro | dias | AVALIAR (novo) |
| P43 | Registrar de onde a receita veio (livros, vídeos, artigos) | chefe | desktop | documentação | raro | dias | CONFIGURAR |
| P44 | Arquivar / restaurar receita | chefe / dono | desktop | receita saiu de linha | raro | dias | CORRIGIR · CONFIGURAR |
| P45 | Identificar-se no tablet compartilhado (PIN) / estação autônoma | todos | todos os dispositivos | troca de operador / bloqueio | várias/turno | segundos | AUTORIZAR |

---

## 2. Fichas

### P01 Decidir quanto produzir de cada produto amanhã
- **Quem**: chefe de produção (perm `can_edit_planned`), ou operador que só pode aceitar sugestão (`can_edit_suggested`).
- **Onde**: hoje `/plan` (grade Produto · Sugerido · Planejado), tablet/desktop. Faz mais sentido desktop ou tablet sentado; é trabalho de lista longa, não de bancada.
- **Gatilho**: rotina da tarde; a grade abre sozinha em *amanhã* depois do meio-dia (`defaultPlanningDate`).
- **Frequência/urgência**: 1×/dia cobrindo todos os SKUs com receita ativa; horas. Cliente esperando: não.
- **Objetivo real**: fixar, para cada produto, quantas peças sairão amanhã, de modo que pesagem, forno e venda antecipada (quant planejado) tenham um número.
- **Info mínima**: produto; sugestão; encomendas já confirmadas para a data; (idealmente) o que sobrou/perdeu ontem e falta de insumo. **Sobra**: SKU repetido em cada linha e no diálogo; data repetida no diálogo. **Falta**: falta de insumo só aparece na Preparação (coluna Saldo) ou na finalização — não no momento de decidir; a confiança da sugestão só aparece dentro do "por quê".
- **Entrada**: confirmar número pré-preenchido (sugestão) ou digitar número (stepper ±1).
- **Efeito**: cria/ajusta `WorkOrder` planned por receita×data×posição; signal → quant planejado do acabado (vendável antecipado), reserva de insumo (log). Reversível (ajustar/zerar) enquanto não produzido.
- **Custo do erro**: médio — número errado gera pesagem errada e superprodução/falta na vitrine; a loja já vende contra o planejado.
- **Exceções**: posição padrão ausente ("Configure uma posição padrão"); revisão mudou em outra tela (diálogo re-sincroniza mantendo o número digitado); várias WOs planejadas → escolher lote antes do número; quantidade abaixo das encomendas → P05; offline bloqueia.
- **Caminho hoje**: por linha: tocar célula → diálogo → (escolher lote) → ajustar → Confirmar = 2–4 toques × N linhas. → **Mínimo**: grade editável in-line com sugestão pré-aceita; "aceitar todas as sugestões" + exceções; o passo inevitável é o **"sim" do responsável sobre o conjunto**.
- **Fronteira**: vem de histórico de vendas/encomendas (Orderman, `craft.suggest`), estoque de insumo (inventory backend); vai para Preparação (P07/P08), Produção (P12), Letreiro (P24), storefront/POS (quant planejado, encomendas).
- **Padrão**: PLANEJAR.
- **Evidência**: `surfaces/production-nuxt/app/components/ProductionStageGrid.vue` (`openPlan`, `confirmPlan`, `planMode`), `composables/useProductionBoard.ts`, `shopman/backstage/services/production.py::apply_planned`, `shopman/shop/services/production.py::set_planned_quantity`, `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py::_handle_planned`.

### P02 Entender por que o sistema sugere N
- **Quem/onde**: chefe; dentro do P01 (toque no número sugerido → diálogo "Por que N?").
- **Gatilho**: sugestão parece estranha. **Freq.** várias por planejamento; minutos.
- **Objetivo real**: confiar ou não no número antes de aceitar.
- **Info mínima**: média de venda (dias de histórico, mesmo dia da semana), encomendas confirmadas, margem de segurança, desconto por perda histórica, reforço sexta/sábado, estação; confiança. Hoje mostra exatamente isso em frases (`_suggestion_explanation_parts`). **Falta**: sobra/perda real de ontem e ruptura (vendeu tudo cedo?) — o histórico de venda subestima demanda em dia de ruptura e o texto não diz.
- **Entrada**: nenhuma; botão leva direto a planejar com a sugestão.
- **Efeito**: nenhum. **Custo do erro**: baixo.
- **Caminho**: 1 toque + 1 para planejar → **mínimo**: a explicação curta inline (1 linha) na própria linha; zero toques.
- **Padrão**: ENTENDER (informação de decisão fora do lugar da decisão).
- **Evidência**: `ProductionStageGrid.vue` (diálogo `explaining`, `planFromExplanation`), `projections/production.py::_build_suggestion`, `_suggestion_explanation_parts`, `shop/services/production.py::suggest_for`.

### P03 Corrigir ou zerar uma quantidade já planejada
- **Quem/onde**: chefe; mesma célula do P01 (modo `adjust`).
- **Gatilho**: mudança de demanda, erro de digitação. Algumas/dia; horas.
- **Objetivo real**: trocar o número antes que alguém pese em cima dele.
- **Info mínima**: valor atual, quanto já está comprometido com encomendas. **Falta**: aviso de que a pesagem/etiquetas daquele preparo já podem ter sido impressas (o checklist da Preparação só é limpo quando a revisão muda).
- **Entrada**: digitar número; 0 remove.
- **Efeito**: substitui a quantidade da WO planejada; quant planejado ajusta (`_handle_adjusted`); checklist local de separação é zerado por mudança de revisão. Reversível.
- **Custo**: médio (etiquetas já impressas ficam erradas).
- **Exceções**: abaixo das encomendas → P05 (order_shortage, pode forçar com motivo); revisão alheia → resync.
- **Caminho**: = P01. **Mínimo**: editar o número na grade (1 gesto).
- **Padrão**: CORRIGIR · PLANEJAR (mesmo trabalho que P01, outro estado).
- **Evidência**: `ProductionStageGrid.vue` (`PLAN_TITLE.adjust`, "Substitui #… — 0 remove"), `services/production.py::apply_planned` / `_check_linked_order_coverage`.

### P04 Acrescentar um lote extra a um produto já em produção
- **Quem/onde**: chefe/padeiro; `/plan` com a data de hoje (modo `new-batch`: célula diz "Novo lote").
- **Gatilho**: vitrine acabou, encomenda de última hora. 0–5/dia; minutos.
- **Objetivo real**: mandar fazer mais N hoje, somando ao que já foi.
- **Info mínima**: quanto já foi produzido/concluído hoje; encomendas descobertas. Hoje mostra "Soma ao dia · X produzidas · Y concluídas".
- **Entrada**: digitar N (parte de 0 de propósito para não dobrar).
- **Efeito**: nova WO planned que soma. Reversível (zerar).
- **Custo**: médio.
- **Caminho**: trocar para `/plan`, garantir data = hoje (o default à tarde é amanhã!), achar linha, 3 toques. → **Mínimo**: "+ lote" na própria tela de Produção/Expedição de hoje; 1 número.
- **Fronteira**: frequentemente disparado por ruptura no POS/storefront — esse sinal não chega aqui.
- **Padrão**: PLANEJAR (é o mesmo que P17 "lote avulso", só que antes do forno em vez de depois).
- **Evidência**: `ProductionStageGrid.vue` (`rowPlanMode`, `planCellVerb`), `services/production.py::apply_planned(create_new=…)`.

### P05 Resolver "quantidade não cobre encomendas" / "faltam insumos"
- **Quem**: quem tentou a ação; forçar exige `can_override_shortage` (a possibilidade `force` vem do servidor com prova assinada).
- **Onde**: `ShortageDialog` sobre P01/P03 (order_shortage) e sobre P16/P17 (material_shortage).
- **Gatilho**: 409 estruturado do servidor. Raro; minutos.
- **Objetivo real**: decidir entre honrar a regra (não reduzir/não finalizar) ou assumir conscientemente a exceção, deixando quem e por quê.
- **Info mínima**: o que falta (insumo × precisa × tem × faltam) ou comprometido × solicitado + pedidos. Hoje mostra isso. **Sobra**: nada. **Falta**: para material, o que fazer (comprar? ajustar estoque? trocar insumo?) e se o saldo do sistema está certo — o caso comum é estoque de insumo desatualizado, não falta real.
- **Entrada**: texto livre "quem autorizou e por quê" (obrigatório) + confirmar.
- **Efeito**: refaz a ação com `force` + `approved_shortage`; grava override auditado + alerta ao gerente (`_record_shortage_override`). Irreversível como registro.
- **Custo**: alto se usado por hábito (estoque negativo, encomendas descobertas).
- **Exceções**: sem permissão → só "Cancelar"/"Entendi". **Bug encontrado**: em P12 (Confirmar produzido) o servidor também devolve `order_shortage` (produziu menos do que as encomendas exigem, `_locked_work_order_order_shortage` em `apply_start`), o composable devolve `res.shortage`, mas `confirmStart` em `ProductionStageGrid.vue` não o trata: o diálogo fica aberto sem mensagem.
- **Caminho**: 1 diálogo + texto + confirmar → **mínimo**: igual; o texto de motivo é o passo inevitável (é a autorização). Para material, mostrar a falta **antes** (em P01/P07), evitando a recusa.
- **Padrão**: TRIAR · AUTORIZAR.
- **Evidência**: `components/ShortageDialog.vue`, `services/production.py` (`ProductionStockShortError`, `ProductionOrderShortError`, `_require_approved_shortage_snapshot`, `check_finish_materials`, `_record_shortage_override`), `pages/expedite.vue::retryWithForce`.

### P06 Ver quais encomendas dependem desta produção
- **Quem/onde**: chefe/padeiro; chip "🛍 N un." na linha da grade → diálogo com pedidos (ref, status, quantidade). No `/expedite` aparece só como número no card.
- **Gatilho**: decidir ajuste, priorizar fornada. Algumas/dia.
- **Objetivo real**: saber quantas peças já têm dono e para quando.
- **Info mínima**: unidades comprometidas; horário de retirada/entrega do pedido mais cedo. **Falta**: horário (o que define a prioridade da fornada) não aparece.
- **Entrada**: nenhuma. **Efeito**: nenhum.
- **Caminho**: 1 toque → **mínimo**: 0 (número + hora do primeiro compromisso inline).
- **Fronteira**: Orderman/Pedidos (vínculo production_order_sync).
- **Padrão**: LOCALIZAR · ENTENDER.
- **Evidência**: `ProductionStageGrid.vue` (`commitmentsRow`), `presentation/production.ts::rowCommitments`, `projections/production.py::_order_commitments_for_work_order`.

### P07 Separar os insumos do dia (lista agregada)
- **Quem/onde**: ajudante/padeiro; `/mise-en-place` modo "Por insumo"; tablet (celular faria sentido andando na despensa).
- **Gatilho**: início do turno (ou véspera). 1×/turno; minutos.
- **Objetivo real**: ter na bancada tudo que o plano consome, e descobrir cedo o que falta.
- **Info mínima**: insumo, quantidade total (com margem de rendimento explicada), saldo e "Falta"; opção de explodir pré-preparos até matéria-prima; quebra por receita sob demanda. **Sobra**: SKU sob o nome. **Falta**: ação a partir da falta (avisar Compras/ajustar plano) — a falta é só lida.
- **Entrada**: marcar checkbox por item (lista local por estação/dispositivo — "não é registro de auditoria").
- **Efeito**: nenhum no servidor; checklist em localStorage, zerado se o plano mudar de revisão.
- **Custo**: baixo (é memória auxiliar).
- **Exceções**: plano mudou → aviso "as marcações foram limpas"; sem leituras de estoque → coluna Saldo some; offline → lista velha com chip.
- **Caminho**: abrir aba, alternar modo, marcar N itens → **mínimo**: lista que abre já neste modo para quem separa; o passo inevitável é **olhar/pegar fisicamente**; a marcação é opcional.
- **Fronteira**: vem do plano (P01) e do inventory backend (`INVENTORY_BACKEND`, saldo de insumo); deveria ir a Compras (falta).
- **Padrão**: SEPARAR (novo: cumprir uma lista física item a item, sem registro no sistema; distinto de CONFERIR porque não há "esperado × real" a resolver).
- **Evidência**: `pages/mise-en-place.vue` (modo `insumos`, `expand`), `composables/useMiseEnPlace.ts`, `projections/production.py::build_production_mise_en_place`, `_ingredient_availability`.

### P08 Pesar cada preparo conforme a ficha escalada
- **Quem/onde**: ajudante de pesagem; `/mise-en-place` "Por preparo": cartões por preparo com código cego, ingredientes, peso alvo (arredondado à balança), rendimento, objetivo. Tablet ao lado da balança.
- **Gatilho**: turno; 1×/preparo, 5–30/dia; minutos.
- **Objetivo real**: pôr na bacia o peso certo de cada ingrediente para o lote planejado.
- **Info mínima**: código/preparo, ingrediente, peso alvo (unidade de balança), nota de arredondamento. **Sobra**: SKU de ingrediente; nome da receita convive com o código cego na mesma tela (o "cego" só vale para o papel). **Falta**: nada registra que foi pesado (não há "pesado ✓" nem quem pesou) — a rastreabilidade só começa no P12.
- **Entrada**: nenhuma (leitura).
- **Efeito**: nenhum no sistema. **Custo do erro**: alto no mundo (massa errada), invisível no sistema.
- **Caminho**: abrir, ler → **mínimo**: cartão por preparo em letra de balança, um de cada vez; o passo inevitável é **pesar**.
- **Fronteira**: ficha publicada (P39) → aqui; código cego → etiquetas (P09) → mapa do gestor (P31).
- **Padrão**: SEGUIR-INSTRUÇÃO (novo: ler e executar uma receita/procedimento no mundo; nenhum dos rótulos cobria "ler para fazer").
- **Evidência**: `pages/mise-en-place.vue` (modo `preparos`), `composables/useWeighing.ts`, `projections/production.py::build_production_weighing`, `_build_weighing_ticket`, `blind_prep_code`.

### P09 Imprimir etiquetas cegas de pesagem
- **Quem/onde**: ajudante/chefe com `can_print_prep`; botão "Etiquetas de pesagem" (todas) ou impressora por cartão → `ProductionLabelPrintDialog`: prévia em mm, destino (agente local no PC / relay de estação / navegador).
- **Gatilho**: antes de pesar. 1–3×/dia.
- **Objetivo real**: cada bacia sai com um papel: código do dia + ingrediente + peso + data, **sem o nome da receita** (quem pesa não correlaciona receita).
- **Info mínima**: quantas etiquetas, para quê, impressora pronta. **Sobra**: escolha de transporte técnico (relay × navegador × agente) exposta ao operador.
- **Entrada**: confirmar envio.
- **Efeito**: cria `PrintJob` com documento congelado e hasheado; spooler/agente puxa (`print-agent/jobs/claim`). Reimprimível.
- **Custo**: baixo (papel), médio se a etiqueta mente (plano mudou depois).
- **Exceções**: agente indisponível (tablet não alcança loopback do PC) → relay; relay indisponível → "imprimir neste navegador"; preflight bloqueia se a projeção mudou ("Atualizar etiquetas").
- **Caminho**: 2–3 toques + confirmação física (P11) → **mínimo**: 1 toque "imprimir etiquetas de hoje" na impressora padrão da estação; o inevitável é **destacar e colar**.
- **Padrão**: EMITIR.
- **Evidência**: `components/ProductionLabelPrintDialog.vue`, `composables/useProductionLabelPrinting.ts`, `components/WeighingLabels.vue`, `api/print_jobs.py`, `services/print_jobs.py`.

### P10 Imprimir identificação interna do preparo
- Igual a P09, modo `preparo`: uma etiqueta por preparo com nome, data prevista e **validade**. Servidor **recusa** se a ficha não tem validade configurada ("A etiqueta interna não pode presumir validade. Defina a validade na ficha técnica de: …").
- **Objetivo real**: identificar o pote/massa guardado com validade responsável; nunca é rótulo de venda.
- **Falta**: a correção da causa (validade na ficha) não está a um toque; manda para outra superfície.
- **Padrão**: EMITIR. **Evidência**: `services/print_jobs.py` (validity check ~l.326), `ProductionLabelPrintDialog.vue` ("Preparo interno").

### P11 Confirmar que as etiquetas saíram
- **Quem/onde**: quem imprimiu; dentro do diálogo (estados: Aguardando estação, Enviado à fila, Aguardando confirmação, Saída confirmada, Falha, Envio sem confirmação).
- **Objetivo real**: o sistema só acredita no papel quando a pessoa diz que saiu ("registra somente o que realmente saiu no papel"); senão reimprime ou cai para o navegador.
- **Entrada**: escolher entre "saíram certas" / "Não saíram ou saiu incompleto".
- **Efeito**: `confirm` ou `retry/reprint` no PrintJob. **Custo**: baixo.
- **Caminho**: +1 toque por impressão → **mínimo**: 1 (só quando falha; "saiu" poderia ser presumido após X s sem queixa — decisão de produto).
- **Padrão**: CONFERIR · EMITIR (mesma confirmação física que existe para recibo/cozinha em outros apps).
- **Evidência**: `useProductionLabelPrinting.ts::printJobStatusLabel`, `api/print_jobs.py::ProductionPrintJobConfirmView`.

### P12 Dizer quantas peças a massa rendeu
- **Quem/onde**: padeiro (`can_start`); `/` "Produção" (grade Produto · Planejado · Produzido; só linhas com número), botão "Confirmar" → "Quanto foi produzido?" pré-preenchido com o planejado.
- **Gatilho**: massa dividida/modelada, antes do forno. 1×/lote, 10–40/dia; minutos.
- **Objetivo real**: fixar o número real que entra no forno — é ele que ancora o fechamento (P16) e o rendimento.
- **Info mínima**: produto, lote, planejado. **Sobra**: SKU; "Diferente do planejado" é aviso sem consequência (de propósito: rendimento não é perda).
- **Entrada**: confirmar número pré-preenchido ou ajustar (stepper).
- **Efeito**: WO → started com quantidade; quant move para lote `started`; Letreiro passa a "em produção"; carimbo de hora (base de atraso/esquecimento). Reversível só por estorno (P13).
- **Custo**: médio (ancora o QC e o vínculo com encomendas).
- **Exceções**: vários lotes planejados → escolher; revisão mudou → resync; menos que o comprometido → `order_shortage` **não exibido** (bug, ver P05).
- **Caminho**: 2–3 toques (abrir, [lote], confirmar) → **mínimo**: 1 toque "confirmar como planejado" na linha; editar só se divergir.
- **Fronteira**: plano (P01) → expedição (P14/P16), letreiro (P24).
- **Padrão**: REGISTRAR-QUANTIDADE · AVANÇAR.
- **Evidência**: `ProductionStageGrid.vue` (`openStart`, `confirmStart`), `pages/index.vue`, `services/production.py::apply_start`, `shop/services/production.py::start_work_order`.

### P13 Estornar um lote produzido
- **Quem/onde**: `can_void`; na grade Produção, tocar o número produzido → diálogo "Produzido · … · Estornar… · motivo · Confirmar estorno".
- **Objetivo real**: desfazer um registro errado; o lote volta atrás e o vínculo com pedidos é desfeito.
- **Entrada**: confirmar + motivo opcional (default "Estornado pelo operador").
- **Efeito**: WO void (`CraftExecution.void`), abandona corrida de forno aberta, signal `voided` → estoque desfeito. Irreversível.
- **Custo**: alto (encomendas desvinculadas; dados de rendimento somem).
- **Caminho**: 3 toques + texto → **mínimo**: 2 (abrir, confirmar com motivo).
- **Padrão**: CORRIGIR.
- **Evidência**: `ProductionStageGrid.vue::confirmVoid`, `composables/useProductionKds.ts::voidOrder`, `services/production.py::apply_void`.

### P14 Armar o timer do forno de uma fornada
- **Quem/onde**: forneiro (`can_record_oven_fact`); `/expedite`: tocar o **corpo** do card abre "Timer do forno" com numpad 4 colunas (+1/+5/+10), teclado físico funciona; tablet de parede.
- **Gatilho**: fornada entrou no forno. 10–40/dia; segundos (mãos ocupadas, luva).
- **Objetivo real**: ser lembrado na hora de tirar, e registrar que enfornou.
- **Info mínima**: qual fornada, minutos (padrão = última duração). **Falta**: tempo de forno da ficha como padrão (usa "último usado" do dispositivo).
- **Entrada**: digitar minutos + Iniciar.
- **Efeito**: servidor carimba `oven_arm` (fato); countdown local (localStorage) só neste dispositivo ("Toca neste dispositivo").
- **Custo**: médio (pão queimado se o timer for de outra fornada/outro tablet).
- **Exceções**: falha ao declarar → timer local não é armado; sem permissão → card não abre timer.
- **Caminho**: 1 toque + 2–3 dígitos + Iniciar → **mínimo**: 1 toque (tempo da ficha pré-carregado).
- **Padrão**: AVISAR · REGISTRAR-FATO (novo: declarar um acontecimento físico sem número, só "aconteceu agora"; distinto de REGISTRAR-QUANTIDADE).
- **Evidência**: `pages/expedite.vue` (`openOven`, `startOven`, `ovenDigit`), `composables/useOvenFacts.ts`, `composables/useFloorTimers.ts`, `services/production.py::apply_oven_arm`.

### P15 Atender o alarme do forno
- **Quem/onde**: forneiro, à distância; o card inteiro oscila em vermelho, som "dim-dom" a cada 45 s até Visto.
- **Objetivo real**: tirar a fornada; ou pedir mais minutos.
- **Entrada**: +N (estende) ou Visto (silencia). Visto **não** fecha a fornada; o fato "retirou" só é carimbado ao abrir o fechamento (P16, `oven_conclude`).
- **Custo**: alto se ignorado (perda).
- **Caminho**: 2 toques (abrir, Visto) → **mínimo**: tocar o botão de fechar a fornada já silencia e declara retirada (hoje funciona assim: `openOrder` conclui e limpa o timer) — portanto "Visto" é um passo a mais no caso feliz.
- **Padrão**: AVISAR.
- **Evidência**: `pages/expedite.vue` (`markOvenSeen`, `ovenAdd`, CSS de alarme), `useFloorTimers.ts`.

### P16 Fechar a fornada: contar o que saiu por qualidade e perda
- **Quem/onde**: forneiro/padeiro (`can_close_qc`); `/expedite` quadrado grande com o número âncora → `QcCloseScreen`: botões de grau (Admin: ex. excelente/padrão/regular/mínimo, cada um com % de remarcação) + Perda; o grau padrão recebe o **saldo automático**; cada bucket ≠ padrão exige motivo de uma lista de defeitos (alguns forçam descarte); dois toques num grau tomam todo o saldo; contagem acima do iniciado exige motivo.
- **Gatilho**: fornada saiu. 10–40/dia; minutos (pão precisa ir para a vitrine).
- **Objetivo real**: transformar a fornada em estoque vendável classificado (preço cheio / com desconto) e registrar perda com causa.
- **Info mínima**: âncora (o que entrou no forno), graus, perda, motivo por bucket. **Sobra**: planejado (já foi intencionalmente retirado do card). **Falta**: nada essencial; aviso de encomendas que dependem desta fornada aparece só como número.
- **Entrada**: caso feliz = 1 toque (Confirmar com tudo no padrão). Exceção = número por grau + escolher motivo de lista curta.
- **Efeito**: WO finished com linhas de output por grau/lote; signal → consumo de insumos (ledger MAKE) + entrada de acabado com lote e grau (preço remarcado nos canais); abre fila de espera; lote vai para "Qualidade (QC)" aguardando revisão; alertas de rendimento baixo. Irreversível (correção só pelo gestor, P20).
- **Custo**: alto (estoque, preço e perda; desperdício nos relatórios).
- **Exceções**: falta de insumo → P05 (force com motivo); quantidade 0 e sem perda → aviso; descartar fechamento pede confirmação; revisão mudou → recusa.
- **Caminho**: 1 toque abre + 1 confirmar (feliz) / +2 por exceção → **mínimo**: 1 toque no caso feliz; o inevitável é **contar**.
- **Fronteira**: P12/P14 → estoque (Stockman), vitrine/POS/storefront (preço por grau), lista de espera, P19.
- **Padrão**: REGISTRAR-QUANTIDADE · AVANÇAR (é o mesmo gesto que "Recebimento" de Compras e "Contagem": partir de um esperado e subtrair exceções com motivo).
- **Evidência**: `components/QcCloseScreen.vue`, `presentation/qc.ts` (modelo subtrativo, `ovenAnchor`), `pages/expedite.vue::onConfirm`, `composables/useQcKiosk.ts`, `services/production.py::apply_finish`, `resolve_partition`, `projections/production.py::build_qc_kiosk`.

### P17 Registrar um lote que não estava no plano (lote avulso)
- **Quem/onde**: `can_quick_finish`, só para hoje; `/expedite` menu ⋯ → "Lote avulso" → lista de receitas → `QcCloseScreen` sem âncora (o grau padrão vira editável).
- **Objetivo real**: dar entrada em estoque a algo produzido fora do plano.
- **Entrada**: escolher receita + digitar quantidades por grau.
- **Efeito**: cria e finaliza a WO num passo (`apply_quick_finish` com recibo idempotente). Irreversível.
- **Caminho**: 3 toques + números → **mínimo**: buscar receita + 1 número.
- **Padrão**: REGISTRAR-QUANTIDADE (mesmo trabalho que P16 sem âncora; e "irmão tardio" do P04).
- **Evidência**: `pages/expedite.vue` (`openOffPlan`, `quickFinishAvailable`), `services/production.py::apply_quick_finish`.

### P18 Fechar fornadas esquecidas de dias anteriores
- **Quem/onde**: chefe/forneiro; aviso tocável em `/expedite` ("N lotes abertos de dias anteriores. Toque para ver.") leva à data mais recente pendente; alerta `production_forgotten`/`production_unfinished` no sino.
- **Objetivo real**: não deixar estoque e rendimento pendurados; fechar com o que de fato aconteceu.
- **Entrada**: = P16 na data passada.
- **Custo**: médio (estoque fantasma "started"; letreiro e lista de espera erradas).
- **Caminho**: 1 toque no aviso + P16 → **mínimo**: igual (bom).
- **Padrão**: CORRIGIR · AVANÇAR.
- **Evidência**: `projections/production.py::QCKioskProjection.previous_open_*`, `pages/expedite.vue`, `shop/handlers/production_alerts.py`.

### P19 Confirmar a qualidade de um lote fechado
- **Quem/onde**: gestor (`card.can_correct`); `/expedite` aba "Qualidade (QC)" com badge de pendentes → "Confirmar qualidade" → `window.confirm` nativo ("Isso libera os avisos de disponibilidade autorizados pelos clientes").
- **Gatilho**: lote fechado aguardando revisão. 10–40/dia; horas (mas atrasa avisos a clientes).
- **Objetivo real**: dar o aval de quem responde pela qualidade antes de avisar clientes que o produto voltou.
- **Info mínima**: partição (cheio / desconto / perda + motivos). **Falta**: em lote, aprovar vários de uma vez; o gestor raramente está no tablet do forno.
- **Entrada**: confirmar.
- **Efeito**: evento `quality_reviewed`; signal libera notificações de estoque (`StockAlertSubscription`). Irreversível como registro.
- **Custo**: médio.
- **Caminho**: 2 toques por lote → **mínimo**: "confirmar todos os revisados sem exceção" (1 toque) — ou confirmação automática quando não há perda/desconto (decisão de produto).
- **Padrão**: APROVAR.
- **Evidência**: `pages/expedite.vue::confirmQuality`, `services/production.py::apply_quality_review`, `_emit_quality_reviewed`, `contrib/stockman/handlers.py` (`quality_reviewed`).

### P20 Corrigir a qualidade de um lote fechado
- **Quem/onde**: gestor; aba QC → "Corrigir qualidade" → `QcCloseScreen` modo correção (partição atual pré-carregada).
- **Objetivo real**: reclassificar peças (ex.: descobriu defeito) sem reescrever o fechamento original.
- **Entrada**: redistribuir números entre graus/perda + motivo (servidor exige motivo; a tela envia texto fixo "Revisão do QC registrada no quiosque." — o servidor pede motivo e a tela o fabrica).
- **Efeito**: novo evento de correção; reclassificação de estoque por lote (`_apply_quality_stock_reclassification`), realoca holds; campanha/preço afetados. Irreversível (corrigível de novo).
- **Custo**: alto (estoque e reservas de clientes).
- **Padrão**: CORRIGIR.
- **Evidência**: `QcCloseScreen.vue` (`auditReason`), `services/production.py::apply_quality_correction`.

### P21 Disparar um lembrete de chão com um toque
- **Quem/onde**: qualquer do fournil; `/timers` bloco "Disparar": fileira de etiquetas do servidor (nome + minutos); botão no cabeçalho de toda tela leva para lá com contador.
- **Gatilho**: começou fermentação/descanso. Dezenas/dia; segundos.
- **Objetivo real**: ser lembrado; nada no processo depende disso ("nenhum timer bloqueia").
- **Entrada**: 1 toque.
- **Efeito**: timer local (localStorage) neste dispositivo. **Custo**: médio (esquecimento se o tablet errado tocar).
- **Caminho**: ir a /timers + 1 toque → **mínimo**: 1 toque (bom); a ida à página é o custo.
- **Padrão**: AVISAR.
- **Evidência**: `pages/timers.vue`, `composables/useTimerTags.ts`, `api/timer_tags.py`, `useFloorTimers.ts`.

### P22 Criar um timer avulso / guardar como etiqueta
- **Onde**: `/timers` "Novo timer" → `FloorTimerCreateDialog` (numpad, nome opcional, "guardar como etiqueta" — vale para todo o fournil).
- **Entrada**: dígitos + nome opcional + opção guardar.
- **Efeito**: timer local; etiqueta nova no servidor (compartilhada). O timer é armado antes; falha ao guardar não o derruba.
- **Padrão**: AVISAR · CONFIGURAR.
- **Evidência**: `components/FloorTimerCreateDialog.vue`, `useTimerTags.ts`.

### P23 Ver timers correndo e silenciar
- **Onde**: `/timers` bloco "Em andamento" (cards estilo KDS: toque faz a única ação do estado — Visto, estender); contador pulsante no cabeçalho.
- **Objetivo real**: consciência do que está por vencer.
- **Falta**: os timers de um tablet não aparecem no outro (local ao dispositivo) — no fournil com várias telas, "quem armou ouve".
- **Padrão**: VIGIAR · AVISAR (mesmo mecanismo do P14/P15).
- **Evidência**: `pages/timers.vue`, `components/FloorTimerCard.vue`, `presentation/timers.ts`.

### P24 Mostrar à loja o que sai do forno e quando (letreiro)
- **Quem/onde**: ninguém opera; `/board` em modo kiosk numa TV (split-flap Solari, tela cheia, wake lock, recarga ociosa, vira o dia à meia-noite, paginação de 12 s).
- **Objetivo real**: cliente e atendente veem sem perguntar: produto, quantidade, horário (previsto pelo histórico ou real), status (programado / em produção / atrasado / chegou; "chegou" sai após TTL).
- **Info mínima**: exatamente isso. **Sobra**: nada. **Falta**: disponibilidade real na vitrine (chegou ≠ ainda tem).
- **Entrada**: nenhuma (toque destrava som; data discreta).
- **Efeito**: nenhum. Estação autônoma resolvida por cookie de estação sob `/api/v1/backstage/production/`.
- **Padrão**: VIGIAR.
- **Evidência**: `pages/board.vue`, `composables/useProductionForecast.ts`, `useBoardPages.ts`, `projections/production.py::build_production_forecast`.

### P25 Responder ao cliente "que horas sai o X?" / "amanhã tem?"
- **Quem/onde**: atendente de balcão; olha a TV ou abre `/board` e anda a data (‹ ›) para amanhã.
- **Cliente esperando**: sim; segundos.
- **Objetivo real**: dizer hora/quantidade prevista ou se dá para encomendar.
- **Falta**: no PDV, onde o atendente está, essa informação não existe; e amanhã pode não ter previsão de hora.
- **Caminho**: trocar de app, mudar data, ler → **mínimo**: a promessa do produto visível no próprio PDV (já existe `catalog/promise` no back) — 0 trocas.
- **Padrão**: LOCALIZAR.
- **Evidência**: `pages/board.vue` (data "o vendedor consulta Amanhã"), `api/product_promise.py`.

### P26 Ver e reconhecer alertas de produção
- **Onde**: `AlertsBell` no cabeçalho de toda tela (poll); alertas: `production_late`, `production_forgotten`, `production_unfinished`, `production_low_yield`, `production_stock_short`/`stock_shortfall`, `production_batch_traceability`, `production_cancelled`. Ação contextual vem do backend; reconhecer ≠ resolver.
- **Objetivo real**: alguém agir antes do prejuízo (fornada esquecida, insumo faltando).
- **Entrada**: abrir, tocar ação ou reconhecer.
- **Padrão**: AVISAR · TRIAR.
- **Evidência**: `components/AlertsBell.vue`, `composables/useAlerts.ts`, `shop/handlers/production_alerts.py`.

### P27 Acompanhar a gestão do dia
- **Quem/onde**: gerente (`can_view_reports`, perm fina `backstage.view_production_reports`); `/reports` bloco "Gestão do dia": rendimento médio, capacidade %, tabela de atrasos (WOs iniciadas há mais que `max_started_minutes`).
- **Objetivo real**: saber se o dia está no trilho e onde intervir.
- **Falta**: os atrasos não levam à ação (abrir a fornada).
- **Padrão**: ENTENDER · VIGIAR.
- **Evidência**: `pages/reports.vue`, `useProductionManagement.ts`, `projections/production.py::build_production_dashboard`, `_late_projection`.

### P28 Ler relatórios por período
- **Onde**: `/reports` abas Histórico (por OP) · Produtividade (por operador) · Desperdício (por ficha) · Qualidade (receita × grau × defeito); filtros datas (7 dias padrão), ficha, posto, operador, "Aplicar"; paginação por cursor.
- **Objetivo real**: decidir mudanças (receita, plano, pessoas) a partir de perda/rendimento.
- **Falta**: ligação desperdício → sugestão do plano é implícita (`waste_rate` entra na sugestão) mas não é mostrada aqui; sem gráfico por decisão explícita.
- **Padrão**: ENTENDER.
- **Evidência**: `pages/reports.vue`, `useProductionReports.ts`, `useReportFilters.ts`, `presentation/reports.ts`, `projections/production.py::build_production_report_page`.

### P29 Exportar CSV
- Link direto por relatório; servidor faz streaming com teto (`ProductionReportExportLimitExceeded`) e recusa se mudou durante a exportação.
- **Padrão**: EMITIR. **Evidência**: `services/production.py::iter_reports_csv`, `prepare_reports_csv`.

### P30 Recarregar relatório que mudou durante a paginação
- Aviso "O relatório mudou enquanto você navegava" + "Reconciliar relatório"; navegação bloqueada até reaplicar.
- **Objetivo real**: não misturar páginas de duas versões dos dados. É um trabalho que o sistema impõe; poderia reaplicar sozinho mantendo a página 1.
- **Padrão**: ENTENDER (técnico; candidato a eliminação).
- **Evidência**: `pages/reports.vue` (`cursorStale`), `projections/production.py::production_report_revision`.

### P31 Descobrir qual preparo corresponde a um código cego
- **Quem/onde**: gerente (`can_reveal_blind_map`); `/reports` bloco "Mapa código-cego ↔ preparo" por dia.
- **Objetivo real**: auditar/rastrear uma bacia sem que o chão conheça a correspondência.
- **Padrão**: LOCALIZAR.
- **Evidência**: `useBlindMap.ts`, `projections/production.py::build_production_blind_map`, `blind_prep_code`.

### P32 Achar uma receita no inventário
- **Onde**: `/recipes`: busca, chips por tipo, "sem SKU", "com rascunho", favoritas, arquivadas ocultas; cartão: tipo, SKU/produto, versão atual, hidratação.
- **Padrão**: LOCALIZAR. **Evidência**: `pages/recipes/index.vue`, `useRecipeBook.ts`, `api/recipe_book.py::RecipeBookListView`.

### P33 Marcar favorita
- Estrela por operador (basta leitura). **Padrão**: CONFIGURAR (pessoal). **Evidência**: `useRecipeFavorite.ts`, `services/recipe_favorites.py`.

### P34 Ler a fórmula de uma versão
- **Onde**: `/recipes/[ref]` → `FormulaLens`: âncora e base, tabela g/%, métricas de padaria com faixa de referência (só âncora farinha), partes, mistura final, BOM; linha do tempo das versões (`?v=`).
- **Objetivo real**: saber como fazer / avaliar a fórmula. Para a bancada, a pesagem escalada (P08) já é a versão útil; esta é a de estudo.
- **Padrão**: ENTENDER. **Evidência**: `pages/recipes/[ref]/index.vue`, `components/FormulaLens.vue`.

### P35 Trazer uma receita escrita para o sistema (foto / anotação)
- **Quem/onde**: chefe/dono; `/recipes/new` portas "Anotação" (colar texto) e "Foto" (câmera/arquivo, redimensionada no navegador) → `POST recipes/capture/` lê nome, língua, rendimento, ingredientes casados com candidatos, papel → conferência local (trocar candidato de insumo, papel, nome) → "Continuar no editor" cria entry + versão rascunho com `origin`.
- **Exceções**: leitura automática indisponível (503) → tela diz e aponta "Manual".
- **Dispositivo certo**: celular para foto; desktop para conferir.
- **Padrão**: COMPOR. **Evidência**: `pages/recipes/new.vue`, `useRecipeCapture.ts`, `services/recipe_capture.py`, `services/recipe_matching.py`.

### P36 Começar uma receita do zero
- `/recipes/new` porta "Manual" → editor vazio. **Padrão**: COMPOR.

### P37 Editar o rascunho
- **Onde**: `/recipes/[ref]/edit?v=n`: rendimento, âncora, tabela (nome, insumo com busca `IngredientPicker`, quantidade, unidade, papel), partes, etapas, notas; prévia da lente recalculada no servidor (debounce); "Padronizar para 1000 g" com antes/depois e desfazer; `origin` visível; "Salvar rascunho" / "Salvar e publicar".
- **Entrada**: muita digitação; desktop.
- **Exceções**: insumo sem SKU permitido em rascunho, bloqueia publicação.
- **Padrão**: COMPOR. **Evidência**: `pages/recipes/[ref]/edit.vue`, `useFormulaLens.ts`, `useIngredientSearch.ts`, `api/recipe_book.py::FormulaStandardizeView`.

### P38 Abrir nova versão a partir de uma existente
- "Nova versão" copia a selecionada em rascunho e abre o editor. **Padrão**: COMPOR. **Evidência**: `api/recipe_book.py::RecipeVersionCreateView`.

### P39 Publicar a versão
- **Quem/onde**: `can_edit`; diálogo "o que muda contra a atual".
- **Objetivo real**: a fórmula passa a ser **a ficha que a produção executa** (escreve `craftsman.Recipe`/`RecipeItem`, desativa outra ficha ativa do mesmo SKU; versão anterior vira superseded).
- **Exceções/recusas**: não-rascunho, receita arquivada, sem SKU, item sem SKU, métrica fora do invariante, invariante de massa.
- **Efeito**: muda pesagem (P08), consumo de insumo (P16), etiquetas (P09/P10) de amanhã em diante; WOs já planejadas guardam sua própria composição (`_work_order_recipe_items`).
- **Custo**: alto.
- **Padrão**: APROVAR. **Evidência**: `packages/craftsman/shopman/craftsman/services/recipe_book.py::publish_version`, `api/recipe_book.py::RecipeVersionPublishView`.

### P40 Comparar duas versões/receitas
- `/recipes/compare?a=ref@n&b=ref@n`: deltas por ingrediente e métrica. **Padrão**: ENTENDER. **Evidência**: `pages/recipes/compare.vue`, `useRecipeCompare.ts`.

### P41 Associar SKU / editar dados da receita
- Edição inline do SKU (validação no back; coerência com catálogo/compras, `sku_namespace`), diálogo "Dados da receita" (nome, tipo, notas). **Padrão**: CONFIGURAR. **Evidência**: `pages/recipes/[ref]/index.vue`, `useRecipeEntry.ts`.

### P42 Avaliar uma versão
- `RecipeVersionRating`: 0–5 por critério configurado no Admin; rascunho também; reavaliar substitui a nota do operador.
- **Padrão**: AVALIAR (novo: registrar juízo subjetivo de uma pessoa sobre um resultado; não é quantidade nem aprovação). **Evidência**: `components/RecipeVersionRating.vue`, `services/recipe_ratings.py`.

### P43 Registrar referências externas
- `RecipeExternalReferences`: livros/vídeos/artigos da receita (todas as versões); grava a lista inteira por PATCH. **Padrão**: CONFIGURAR. **Evidência**: `components/RecipeExternalReferences.vue`, `services/recipe_external_references.py`.

### P44 Arquivar / restaurar receita
- Diálogo destrutivo com confirmação; arquivadas somem da lista e não publicam. **Padrão**: CORRIGIR · CONFIGURAR. **Evidência**: `pages/recipes/[ref]/index.vue` (Arquivar/restaurar).

### P45 Identificar-se no tablet / estação autônoma
- `useOperatorLock("backstage.operate_production")`, PIN do kit; painel de parede usa confiança de estação restrita ao prefixo da Produção (`station_trust.PRODUCTION_API_PREFIX`) para não destravar o PDV no mesmo dispositivo. Mutations levam ator + prova de ação projetada + idempotência + `expected_rev`.
- **Padrão**: AUTORIZAR. **Evidência**: `nuxt.config.ts` (`operatorSessionPath`), `composables/useProductionMutationGuard.ts`.

---

## 3. Padrões neste app

1. **Um só gesto, repetido em quatro lugares: "partir do esperado e registrar o real"**. Planejar (sugestão → planejado), Produzir (planejado → produzido), Fechar fornada (produzido → graus+perda), Corrigir QC (fechado → reclassificado). Todos são *número pré-preenchido + confirmar + exceção com motivo*. Hoje são três UIs (grade com célula, diálogo com stepper, quiosque com buckets). É o mesmo trabalho com nomes diferentes; P04 (novo lote) e P17 (lote avulso) são também o mesmo (produção fora do plano), separados só por "antes ou depois do forno".
2. **O caso feliz ainda custa toques que o sistema poderia dar**: P12 abre diálogo para confirmar o número que já está escrito; P15 pede "Visto" quando o próximo toque (fechar a fornada) já silencia e declara a retirada; P19 confirma lote a lote mesmo quando não há exceção; P30 obriga a "reconciliar" algo que o sistema detectou sozinho.
3. **Informação de decisão fora do lugar da decisão**: falta de insumo só aparece na Preparação ou como recusa na finalização (nunca no Planejar); "por que N?" está atrás de um toque; horário das encomendas não aparece em nenhum lugar da produção; promessa de horário (letreiro) não chega ao PDV onde o cliente pergunta; validade ausente só é descoberta na recusa da etiqueta interna.
4. **Trabalho físico sem registro, registro sem trabalho físico**: separar (P07) e pesar (P08) não deixam rastro no sistema, enquanto a impressão (P11) exige confirmação física explícita. O ponto cego de rastreabilidade está exatamente onde o erro é mais caro (massa pesada errada).
5. **Estado local que deveria ser compartilhado**: timers (P14/P21/P23) e checklist de separação (P07) vivem no localStorage de cada tablet; num fournil com várias telas, "quem armou ouve" é uma limitação, não uma regra.
6. **Bug de função**: `order_shortage` devolvido por `apply_start` (P12) não é exibido por `ProductionStageGrid.vue::confirmStart` — o diálogo fica parado sem explicação.
7. **Exposição de mecanismo**: escolha de transporte de impressão (agente/relay/navegador), revisões/`rev`, "lote #ref" quando há vários lotes na mesma linha — tudo legítimo no servidor, ruído para o operador.
8. **Duas personas no mesmo app**: chão (P07–P18, P21–P23, toque, mão suja, segundos) e gestor (P01, P19–P20, P27–P44, desktop, horas/dias). Receitas e Relatórios são de gestor/estudo; QC-revisão é de gestor mas mora na tela do forno.
9. **Rótulos novos propostos**: SEPARAR (cumprir lista física), SEGUIR-INSTRUÇÃO (ler para executar), REGISTRAR-FATO (declarar acontecimento sem número), AVALIAR (juízo subjetivo).

---

## 4. Cobertura (telas/estados → dispositivo que faz sentido)

| Rota / estado | O que é | Dispositivo certo e porquê |
|---|---|---|
| `/plan` grade (Sugerido · Planejado), seletor de data, filtro por ficha-base | P01–P04 | desktop/tablet sentado: lista longa, decisão de horas |
| `/plan` diálogo Planejar / Ajustar / Novo lote (escolha de lote, stepper) | P01, P03, P04 | idem; deveria ser edição in-line |
| `/plan` diálogo "Por que N?" | P02 | idem; deveria ser inline |
| diálogo Encomendas comprometidas | P06 | tablet/desktop |
| `ShortageDialog` (insumo / encomendas, motivo de autorização) | P05 | onde a ação acontece (tablet/desktop) |
| `/` Produção grade (Planejado · Produzido) | P12 | tablet de bancada: toque, segundos |
| `/` diálogo "Quanto foi produzido?" | P12 | tablet |
| `/` diálogo Produzido (conferência + estorno) | P13 | tablet; estorno raro, poderia exigir gestor |
| `/mise-en-place` Por insumo (checklist, saldo, explodir, quebra por receita) | P07 | celular/tablet: anda na despensa |
| `/mise-en-place` Por preparo (cartões com código cego) | P08 | tablet na balança, letra grande |
| `ProductionLabelPrintDialog` (prévia mm, destino, estados do job, confirmação física, fallback navegador) | P09–P11 | tablet/PC ao lado da etiquetadora |
| `/expedite` painel Expedição (cards, alarme, aviso de dias anteriores, menu ⋯) | P14–P18 | tablet de parede na boca do forno + teclado numérico; legível a distância |
| `/expedite` diálogo Timer do forno (numpad, correndo, tocando) | P14, P15 | idem |
| `/expedite` sheet Lote avulso (lista de receitas) | P17 | idem |
| `QcCloseScreen` fechamento (graus, perda, sheet de motivos, overshoot) | P16, P17 | idem |
| `/expedite#quality` aba Qualidade (aguardando revisão / revisada) | P19 | gestor: celular/desktop, não o tablet do forno |
| `QcCloseScreen` modo correção | P20 | gestor: tablet/desktop |
| `/timers` Disparar + Em andamento; `FloorTimerCreateDialog` | P21–P23 | qualquer tablet do chão; idealmente parede compartilhada |
| botão de timers no cabeçalho (contador) | P23 | todas as telas de chão |
| `AlertsBell` | P26 | todas; push no celular do gerente faria mais sentido |
| `/board` letreiro (kiosk, tela cheia, paginação, sem sinal) | P24, P25 | TV de parede (loja); consulta de amanhã deveria estar no PDV |
| `/reports` Gestão do dia (KPIs, atrasos) | P27 | desktop/celular do gerente |
| `/reports` relatórios por período (4 abas, filtros, paginação, CSV, "relatório mudou") | P28–P30 | desktop |
| `/reports` mapa código-cego (sem perm: estado calmo) | P31 | desktop |
| `/recipes` lista (filtros, favoritas, sem permissão) | P32, P33 | desktop; tablet para consulta |
| `/recipes/[ref]` lente, linha do tempo, nota, referências, diálogos publicar/dados/arquivar, SKU inline | P34, P38–P44 | desktop (edição); tablet (leitura) |
| `/recipes/[ref]/edit` editor + prévia da lente + padronizar 1000 g (estado "sem rascunho") | P37 | desktop: digitação densa |
| `/recipes/new` Anotação / Foto / Manual, conferência do rascunho lido, estado 503 | P35, P36 | foto: celular; conferência: desktop |
| `/recipes/compare` | P40 | desktop |
| Estados transversais: carregando, erro sem dado, chip "sem atualizar" com dado velho, offline bloqueando mutação, revisão mudou (resync), PIN/lock, atalhos de teclado (`ProductionShortcutsHelp`) | P45 e todos | — |
| Rotas legadas `/planejamento` `/preparacao` `/expedicao` `/painel` → 301 | bookmarks de kiosk | — |
