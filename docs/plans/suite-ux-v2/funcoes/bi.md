# B.I. — engenharia reversa por função

App: `surfaces/bi-nuxt` (8 abas: Produção `/`, Vendas `/sales`, Caixa `/cash`, Clientes `/customers`,
Perfis `/profiles`, Explorar `/explore`, Projeção `/forecast`, Cenários `/scenarios`) sobre
`shopman/backstage/api/bi.py` → `projections/bi_*.py` → `bi/` (sources, alerts, scenarios, ingest).
Gate `backstage.view_bi`; Caixa e métrica `cash_difference` exigem também `cashman.audit_shift`.
Fora do app, mas parte do trabalho de B.I.: Admin (`BIAlertRule`, `BIAlertEvent`, `BIScenarioReport`,
etiquetas de consumo, lugares do salão), comandos (`ingest_yooga`, `import_holidays`, `import_weather`,
`propose_consumption_tags`, `bi_calibrate`, `setup_bi_reference`, `refresh_bi_daily_series`,
`evaluate_bi_alerts` no `maintenance_worker`).

**As perguntas reais do dono** (BI-INSIGHTS-MAP §7, BI-QUESTION-CATALOG mandato 17/08): (1) sobrou ou
faltou pão, por SKU, por dia/clima/feriado; (2) SKU que chega tarde / acaba cedo; (3) quanto assar
amanhã; (4) "e se tivesse mais / mais cedo?"; (5) o que representa mais vendas: levar, local,
local+levar, entrega; (6) mesas: ocupação, ociosidade, quantas; (7) forma de pagamento; e, em segundo
plano, comportamento do cliente (o que se compra em cada hora, o que se compra junto). O B.I. foi
reposicionado pelo próprio plano como **"o ciclo de decisão da fornada", não uma galeria de painéis**
— a tela atual ainda é a galeria.

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| BI-01 | Ver se a produção rendeu (lotes, perda, rendimento) | dono, gerente de produção | escritório/desktop | rotina semanal | 1×/semana | dias | ENTENDER |
| BI-02 | Recalibrar o tempo de forno de cada receita | dono, chefe padeiro | escritório/desktop | desconfiança do tempo armado; rotina mensal | 1×/mês | dias | ENTENDER → CONFIGURAR |
| BI-03 | Saber se o período vendeu mais ou menos que o anterior | dono | desktop/celular | rotina; fim de semana/mês | 1–7×/semana | dias | ENTENDER |
| BI-04 | Ver em que horas e dias a casa vende (escala, horário) | dono | desktop | revisão de escala/horário | 1×/mês | semanas | ENTENDER → PLANEJAR |
| BI-05 | Ver o que mais vende e por qual canal | dono | desktop | revisão de cardápio/canal | 1×/mês | semanas | ENTENDER |
| BI-06 | Auditar a quebra de caixa por dia e operador | dono/auditor | desktop | rotina semanal; alarme de quebra | 1×/semana | dias | CONFERIR |
| BI-07 | Investigar o que a gaveta revelou (sensor mudo, destrave, desistência) | dono/auditor | desktop | anomalia listada | 1×/semana | dias | CONFERIR · TRIAR |
| BI-08 | Cobrar quem deve na conta da casa | dono/gerente | desktop/celular | saldo em aberto | 1×/semana | dias | LOCALIZAR → AVISAR |
| BI-09 | Ver como os clientes pagam (mix de meios; taxa; dinheiro encolhendo) | dono | desktop | rotina mensal; decidir maquininha/troco | 1×/mês | semanas | ENTENDER |
| BI-10 | Ver a saúde da base de clientes (RFM, em risco, novos) | dono, marketing | desktop | rotina mensal; antes de campanha | 1×/mês | semanas | ENTENDER → (PLANEJAR campanha) |
| BI-11 | Entender quem é o cliente de balcão (levar/local/misto, bebida, receita por lugar-hora) | dono | desktop | decisão de salão/mix/cardápio | raro (trimestral) | semanas | ENTENDER |
| BI-12 | Fazer uma pergunta livre: métrica × dimensão × cruzamento | dono | desktop | dúvida específica | 1–3×/semana | horas | ENTENDER |
| BI-13 | Guardar, reabrir, favoritar, apagar um corte (cenário salvo) | dono | desktop | pergunta recorrente | 1×/semana | — | CONFIGURAR (de leitura) |
| BI-14 | Escolher o período e comparar com o anterior | dono | todas as abas | toda leitura | toda visita | — | (modificador de ENTENDER) |
| BI-15 | Saber o que esperar de um dia (provável, ocasião, "e se" chover/esfriar) | dono, chefe padeiro | casa/celular/tablet, véspera à noite | planejar a fornada de amanhã | diário | horas | ENTENDER → PLANEJAR |
| BI-16 | Saber o que esperar da semana/mês | dono | desktop | planejar compras/escala | 1×/semana | dias | PLANEJAR |
| BI-17 | Separar o troco do dia (e da semana) | gerente/caixa de abertura | caixa/celular, véspera | abastecer a gaveta antes do movimento | diário | horas | PLANEJAR → REGISTRAR-QUANTIDADE (no caixa) |
| BI-18 | Pedir à IA cenários sobre os agregados e ler | dono | desktop | curiosidade; revisão mensal | raro | dias | ENTENDER (assistido) |
| BI-19 | Ver o que acabou, ficou sem vender ou sobrou, por SKU | dono, chefe padeiro | desktop (hoje); tela de plano (devia) | rotina diária/semanal; pergunta nº 1 do dono | diário | horas | ENTENDER → PLANEJAR |
| BI-20 | Ver se o salão bate no teto / sobra mesa / quanto rende o lugar-hora | dono | desktop | decisão de mesas | raro | semanas | ENTENDER |
| BI-21 | Ser avisado de que algo saiu da curva (dia fraco, quebra, importação parada, de-para pendente) | dono, gerente | hoje: sino do Admin | `evaluate_bi_alerts` (300 s) | eventos/semana | horas | AVISAR |
| BI-22 | Ajustar réguas dos alarmes | dono | Admin/desktop | alarme barulhento ou mudo | raro | — | CONFIGURAR |
| BI-23 | Curar a vocação de consumo de cada SKU | dono | Admin/desktop | SKU novo; `propose_consumption_tags` | raro (por SKU novo) | dias | CONFIGURAR |
| BI-24 | Carregar histórico e contexto (Yooga, feriados, clima, de-para de produto) | dono/técnico | comando/Admin | importação; ano novo; lote novo | raro | dias | CONFIGURAR |
| BI-25 | Identificar-se para ler (e para ler caixa) | dono/gerente | qualquer | abrir o app | toda visita | segundos | AUTORIZAR |
| BI-26 | Explicar o dia estranho (episódio) para não contaminar a média | gerente de fechamento | app de fechamento | sinal automático (parou de vender, fornada não saiu, casa cheia) | só dias com sinal | minutos | TRIAR (resposta em 1 toque) |

---

## 2. Fichas

### BI-01 · Ver se a produção rendeu
- **Quem:** dono; gerente de produção. **Onde:** desktop; faria sentido num resumo semanal no celular.
- **Gatilho:** rotina semanal. **Freq/urgência:** semanal, dias · cliente esperando: não.
- **Objetivo real:** descobrir se a fornada está perdendo unidades e onde, para corrigir processo/receita.
- **Informação mínima:** perda (un e R$) por receita × defeito na janela, contra a anterior; a receita
  que mais piorou. **Sobra:** "Lotes fechados" (volume não é decisão), duas séries diárias de produção e
  rendimento lado a lado (a mesma informação duas vezes). **Falta:** perda em dinheiro; ranking "o que
  piorou"; defeito (só existe no Explorar); link para os lotes.
- **Entrada:** nenhuma (ler). Período.
- **Efeito:** nenhum no sistema. Decisão fora: ajustar receita, treinar, mexer no plano. Erro: baixo.
- **Exceções:** sem produção → "sem produção"; rendimento = finished/(finished+loss) (perda declarada no
  fim do lote; se ninguém declara, rendimento 100% mente silenciosamente).
- **Caminho hoje:** abrir app → aba Produção (default) → ler 4 tiles + 4 gráficos; para o "porquê",
  ir ao Explorar e montar Perda × defeito × receita (≈6 gestos). **Mínimo:** 1 leitura: "Perda da semana
  R$ X (+Y%), concentrada em Croissant / queimado" com toque que abre os lotes. Inevitável: olhar.
- **Fronteira:** vem da Produção (WorkOrder finish, QC); deveria voltar à ficha da receita/plano.
- **Padrão:** ENTENDER. **Evidência:** `surfaces/bi-nuxt/app/pages/index.vue`, `shopman/backstage/projections/bi_production.py`.

### BI-02 · Recalibrar o tempo de forno
- **Quem:** dono, chefe padeiro. **Onde:** desktop.
- **Gatilho:** desconfiança do tempo armado. **Freq:** mensal · não urgente.
- **Objetivo real:** que o `planned_seconds` da receita reflita o forno real (o timer do kiosk usa ele).
- **Mínimo:** por receita: média/p90 medida vs armado, nº de medições, cobertura. **Sobra:** "Tempo de
  forno por forno" — a casa tem **um forno** (N3 arquivada, dimensão `oven` declarada dormente) e o
  painel e a dimensão continuam vivos. **Falta:** o gesto "usar o medido como novo armado" (hoje é
  outro app/Admin); alerta quando medido ≠ armado por mais de X%.
- **Entrada:** nenhuma aqui; a correção é CONFIGURAR em outra tela.
- **Efeito:** nenhum. **Custo do erro:** médio (receita com tempo errado queima/fica crua).
- **Exceções:** cobertura baixa → tile "Tempo de forno medido %" declara (é o KPI de adoção do timer).
- **Caminho hoje:** aba Produção → ler hbar → abrir Admin/receita → editar. **Mínimo:** sugestão
  empurrada para a receita ("medido 21 min, armado 18; ajustar?") com 1 toque de aceitar.
- **Fronteira:** OvenRun (production-nuxt timer) → receita (craftsman).
- **Padrão:** ENTENDER → CONFIGURAR; candidato a **SUGERIR-AJUSTE** (rótulo novo: o sistema propõe
  um valor de configuração medido, o humano aceita). **Evidência:** `pages/index.vue`, `bi_production.py`, `docs/plans/BI-PLAN.md §4`.

### BI-03 · Vendeu mais ou menos?
- **Quem:** dono. **Onde:** desktop/celular.
- **Gatilho:** rotina. **Freq:** várias por semana · dias.
- **Objetivo real:** saber se o negócio vai bem e, se não, onde olhar.
- **Mínimo:** faturamento, pedidos, ticket vs período anterior (e vs mesmo período do ano passado,
  que existe só como cíclico no Explorar); cancelados. **Sobra:** pouco. **Falta:** YoY direto
  (L5); explicação do dia fora da curva (episódio, clima, feriado — `DayContext` existe mas não aparece
  aqui); cancelados sem valor nem motivo; nenhum link ao dia → pedidos.
- **Entrada:** período. **Efeito:** nenhum. Erro baixo.
- **Exceções:** dia com pedido nativo apaga o Yooga do mesmo dia (conflito declarado em texto).
- **Caminho hoje:** aba Vendas → 4 tiles + série. **Mínimo:** 1 frase-resumo empurrada (semanal) com
  o desvio e a causa provável. Inevitável: nada (pode ser push).
- **Fronteira:** Orderman + HistoricalSale (Yooga).
- **Padrão:** ENTENDER (e, por desvio, AVISAR — ver BI-21). **Evidência:** `pages/sales.vue`, `projections/bi_sales.py`, `bi/sources/orderman.py`, `bi/sources/historical.py`.

### BI-04 · Quando a casa vende
- **Quem:** dono. **Onde:** desktop.
- **Gatilho:** revisar escala, horário de abertura, horário de fornada. **Freq:** mensal.
- **Objetivo real:** pôr gente, forno e produto na hora em que o cliente vem.
- **Mínimo:** mapa hora × dia-da-semana (pedidos, e quantidade por SKU por hora). **Sobra:** dois
  gráficos separados (hora e dia) que juntos não mostram o cruzamento; o cruzamento existe só como
  exemplo "Movimento por hora × dia da semana" no Explorar e sai como **tabela de 2 colunas**, não mapa.
  **Falta:** sobreposição com equipe escalada / chegada do produto na vitrine (B1).
- **Entrada:** período. **Efeito:** nenhum.
- **Caminho hoje:** Vendas (2 gráficos) ou Explorar → Cenário → exemplo. **Mínimo:** 1 mapa.
- **Padrão:** ENTENDER → PLANEJAR. **Evidência:** `pages/sales.vue`, `presentation/bi.ts` (EXPLORE_EXAMPLES).

### BI-05 · O que mais vende, por canal
- **Quem:** dono. **Onde:** desktop. **Gatilho:** revisão de cardápio/canal. **Freq:** mensal.
- **Objetivo real:** decidir o que fica, sai, sobe de preço, vai para o iFood.
- **Mínimo:** top SKUs (qtd, R$), Pareto, margem. **Sobra:** canal aparece como `channel_ref` cru
  ("pdv", "web"). **Falta:** margem (N7, Buyman F2), Pareto (L7), o que vende junto (L6), link SKU →
  produto no Catálogo / série do SKU no Explorar.
- **Caminho hoje:** Vendas → tabela top 10. **Mínimo:** mesma tabela com toque → ficha do SKU (vendas,
  sobra, falta, margem). **Padrão:** ENTENDER. **Evidência:** `pages/sales.vue`, `bi_sales.py:_top_skus`.

### BI-06 · Auditar a quebra de caixa
- **Quem:** dono/auditor (`cashman.audit_shift`). **Onde:** desktop.
- **Gatilho:** rotina semanal; alarme `cash_variance_by_drawer` (régua R$ 50/7 dias).
- **Objetivo real:** saber se a falta de dinheiro é ruído, sistema ou pessoa, e agir (conversa,
  treinamento, trava).
- **Mínimo:** quebra por turno e por operador (com dono provado), dias sem fechamento. **Sobra:**
  sangrias/suprimentos totais (não são quebra), turnos fechados (volume). **Falta:** o turno — quebra
  por dia não abre o turno (contagem, movimentos, quem estava); correlação com volume/mix (L10).
- **Entrada:** nenhuma. **Efeito:** nenhum. **Custo do erro:** alto em gente (acusação injusta) — por isso
  "difference_q só em turno de dono único".
- **Exceções:** turno com várias mãos → sem quebra atribuída; dia sem fechamento → `closings_missing`.
- **Caminho hoje:** aba Caixa → gráfico divergente + tabela por operador → (não há caminho ao turno; ir ao
  Admin/caixa procurar). **Mínimo:** alarme → turno com a contagem. Inevitável: julgar.
- **Fronteira:** Cashman (livro, contagem cega do fechamento) → Admin de caixa.
- **Padrão:** CONFERIR. **Evidência:** `pages/cash.vue`, `projections/bi_cash.py`, `bi/sources/cashman.py`.

### BI-07 · Investigar a gaveta
- **Quem:** dono/auditor. **Onde:** desktop.
- **Gatilho:** anomalia listada ("Gaveta · o que pede explicação"), sensor mudo.
- **Objetivo real:** reconhecer fraude ou falha de sensor e corrigir (conversa ou manutenção).
- **Mínimo:** a lista de anomalias por turno com o que não fecha. **Sobra:** a tabela de 9 colunas por
  operador e a de gaveta por hora (contexto, não decisão). **Falta:** link `turno #shift_key` → linha do
  tempo de eventos do turno; "sensor mudo" é problema de **equipamento** e deveria virar tarefa de
  manutenção para quem cuida do PDV, não linha de relatório.
- **Entrada:** nenhuma. **Efeito:** nenhum. **Custo:** alto (pessoas).
- **Caminho hoje:** Caixa → rolar até anomalias → anotar o turno → procurar fora. **Mínimo:** aviso com o
  turno aberto em 1 toque. **Padrão:** CONFERIR · TRIAR · AVISAR. **Evidência:** `bi_cash.py` (`BICashDrawerAnomaly`, `_DrawerLedger`).

### BI-08 · Cobrar a conta da casa
- **Quem:** dono/gerente. **Onde:** desktop/celular.
- **Gatilho:** saldo em aberto cresce. **Freq:** semanal.
- **Objetivo real:** receber o fiado.
- **Mínimo:** quem deve, quanto, desde quando. **Sobra:** nada. **Falta:** idade da dívida; o gesto
  de cobrar (mensagem) e o link ao cliente; mostra só top 5.
- **Caminho hoje:** Caixa → seção "Contas na casa" (só aparece se houver dado). **Mínimo:** lista de
  devedores no app do cliente/caixa com "cobrar". Não é B.I.: é LOCALIZAR operacional. **Padrão:**
  LOCALIZAR → AVISAR. **Evidência:** `bi_cash.py:_cash_accounts`.

### BI-09 · Como os clientes pagam
- **Quem:** dono. **Onde:** desktop. **Gatilho:** decidir maquininha, troco, taxa. **Freq:** mensal.
- **Objetivo real:** dimensionar dinheiro em caixa e custo de cartão.
- **Mínimo:** recebido por meio ao longo dos meses e por hora; a receber na entrega. **Duplicidade:**
  a aba Caixa lê o mix do **fechamento** (só dias fechados, rótulo cru `method`); o Explorar lê do
  **pedido** (todo dia, `services/payments.py`). Mesma pergunta, duas respostas possíveis.
  **Falta:** taxa de cartão em R$ ($5, depende de N1).
- **Caminho hoje:** Caixa (hbar) ou Explorar → exemplo "Dinheiro ao longo dos meses". **Mínimo:** um só
  lugar, lido do pedido. **Padrão:** ENTENDER. **Evidência:** `pages/cash.vue`, `bi_explore.py` (`payment_*`), `bi_payments.py`.

### BI-10 · Saúde da base de clientes
- **Quem:** dono, marketing. **Onde:** desktop.
- **Gatilho:** antes de campanha; rotina mensal.
- **Objetivo real:** trazer de volta quem está sumindo e reter quem chegou.
- **Mínimo:** quantos em risco/perdidos (e quem), retenção dos novos (coorte, L8). **Sobra:** "Clientes"
  total, "Com histórico analisado" (dado técnico). **Falta:** a **lista** de em risco e o gesto "criar
  audiência no Marketing"; migração de segmento (snapshot RFM decidido, não exibido); coortes.
- **Entrada:** nenhuma. **Efeito:** nenhum. Hoje o número "Em risco de sumir: N" não leva a nada.
- **Caminho hoje:** Clientes → 4 tiles + 2 gráficos → abrir Marketing e remontar a audiência.
  **Mínimo:** no Marketing, "N clientes em risco: criar campanha de resgate" (1 toque).
- **Fronteira:** Guestman (`CustomerInsight`) → Marketing.
- **Padrão:** ENTENDER → AVISAR (empurrar ao Marketing). **Evidência:** `pages/customers.vue`, `projections/bi_customers.py`.

### BI-11 · Quem é o cliente de balcão (Perfis)
- **Quem:** dono. **Onde:** desktop.
- **Gatilho:** decisão de salão, mix, cardápio de bebidas. **Freq:** rara.
- **Objetivo real:** saber quanto do negócio é "levar", "sentar" e "os dois", com honestidade sobre a
  inferência, para decidir investimento em salão, bebida, mesas.
- **Mínimo:** a faixa piso–teto de cada perfil, ticket por perfil, cobertura de etiquetas; % com bebida
  por dia × faixa. **Sobra:** é a tela mais densa do app (três leituras × matriz × estimativa ponderada ×
  conciliação × categorias × bebida × RevPASH); várias delas são a mesma pergunta em três precisões.
  **Falta:** a frase-veredito ("o salão é 33–40% do balcão e gasta 19% mais"); link para a curadoria das
  etiquetas quando a cobertura é baixa.
- **Entrada:** filtros dia-da-semana e faixa horária; select de leitura.
- **Efeito:** nenhum. **Custo:** baixo (é leitura de gestão; regra: inferência nunca manda em operação).
- **Exceções:** SKU sem etiqueta → "sem etiqueta"; entregas fora do balcão, dentro da conciliação.
- **Caminho hoje:** aba Perfis → rolar ≈8 seções. **Mínimo:** 1 veredito com faixa + 1 matriz.
- **Padrão:** ENTENDER. **Evidência:** `pages/profiles.vue`, `projections/bi_profiles.py`, `services/consumption.py`, `docs/plans/BI-CONSUMPTION-PROFILES.md`.

### BI-12 · Pergunta livre (Explorar)
- **Quem:** dono. **Onde:** desktop.
- **Gatilho:** dúvida concreta. **Freq:** semanal · horas.
- **Objetivo real:** responder uma pergunta que nenhum painel responde, sem pedir a um técnico.
- **Mínimo:** métrica, agrupamento, cruzamento, período, **filtro** (ex.: só croissant). **Gramática:**
  27 métricas × ~20 dimensões, até 2 eixos, contexto (feriado/clima) só quando injetado.
  **Falta:** filtro por valor (não dá para "croissant por dia-da-semana" sem cruzar SKU e ler uma tabela
  de centenas de linhas); mapa de calor para 2 eixos (sai tabela); comparação com período anterior
  (os painéis têm, o Explorar não); toque numa linha → registros.
- **Entrada:** 3 selects + período. **Efeito:** nenhum. Erro baixo (combinação inválida nem chega ao
  servidor; agregação declarada pelo servidor evita "ticket 7×").
- **Caminho hoje:** aba Explorar → 3 selects → ler. **Mínimo:** escrever/escolher a pergunta (1 gesto).
- **Padrão:** ENTENDER. **Evidência:** `pages/explore.vue`, `composables/useBiExplore.ts`, `projections/bi_explore.py`.

### BI-13 · Cenários salvos
- **Quem:** dono. **Onde:** desktop. **Gatilho:** pergunta recorrente.
- **Objetivo real:** não remontar o mesmo corte toda semana.
- **Mínimo:** nome + corte + janela relativa ou fixa. Existe (`BIView`, por dono, favoritos; janela
  guarda preset se "acompanha hoje"). **Falta:** compartilhar com a equipe (é por `owner`); agendar
  ("me mande toda segunda"); os ~35 exemplos curados competem no mesmo select com os do dono.
- **Entrada:** texto (nome), confirmar. **Efeito:** grava `BIView`. Reversível (apagar).
- **Caminho hoje:** ⋯ → nome → Salvar (3 gestos); reabrir = 1 select. **Mínimo:** igual.
- **Padrão:** CONFIGURAR. **Evidência:** `composables/useBiViews.ts`, `models/bi_view.py`, `api/bi.py:BIViewListView`.

### BI-14 · Período e comparação
- **Quem:** todos. **Onde:** barra superior de todas as abas (exceto Projeção e Cenários).
- **Objetivo real:** dizer "de quando" uma vez para o app inteiro.
- **Mínimo:** preset (Dia…Máx, default 28D), ‹ ›, personalizado; comparação automática com o período
  anterior de mesmo tamanho. **Falta:** escolher a base de comparação (ano anterior, mesmo dia-da-semana
  alinhado); Explorar e Perfis-por-categoria não comparam.
- **Padrão:** modificador transversal. **Evidência:** `components/BiTopBar.vue`, `composables/useBiWindow.ts`.

### BI-15 · O que esperar de um dia (Projeção + "e se")
- **Quem:** dono, chefe padeiro. **Onde:** véspera à noite, celular/tablet em casa ou no balcão.
- **Gatilho:** planejar a fornada de amanhã. **Freq:** diária · horas.
- **Objetivo real:** decidir **quanto assar de cada coisa** e quanta gente pôr.
- **Mínimo:** por **SKU**: quantidade provável com faixa, ajustada a ocasião/clima. **O que existe:**
  só nível casa — faturamento e pedidos prováveis (mediana de dias parecidos, faixa p25–p75), ocasião
  (véspera de data comercial lidera), ramos de clima ("se fizer calor / frio / chover"), base explicada,
  "não sei" quando a amostra não sustenta. **Falta:** o número que vira ação (unidades por SKU) — o
  plano decidiu deixar SKU para a fórmula do Craftsman, mas a ponte (F7/F8: frase da ocasião na tela de
  plano, fator em `FORMULA_FACTOR_PROVIDERS`) **não foi construída**; o padeiro nunca vê esta tela no
  lugar da decisão. Não há "acerto da projeção" (previsto × realizado), que o próprio plano exige antes
  de alertar.
- **Entrada:** escolher o dia (default amanhã). "E se": ler o ramo que corresponde à janela.
- **Efeito:** nenhum. **Custo do erro:** médio-alto (sobra ou falta de pão) — mas a decisão é tomada em
  outro app.
- **Caminho hoje:** abrir B.I. → Projeção → ler → abrir Produção → plano → digitar quantidades.
  **Mínimo:** 0 passos no B.I.: o plano de produção já abre com "véspera de feriado, 1,4× uma quarta
  comum" ao lado da sugestão. Inevitável: confirmar o plano (no app de Produção).
- **Fronteira:** HistoricalSale + DayContext + DailySalesFact → (devia) craftsman `suggest` / production-nuxt plano.
- **Padrão:** ENTENDER → PLANEJAR; deveria ser **EXPLICAR-NO-LUGAR** (rótulo novo: o número analítico
  aparece como justificativa da decisão operacional, não como tela própria).
  **Evidência:** `pages/forecast.vue`, `composables/useBiForecast.ts`, `projections/bi_forecast.py`, `docs/plans/BI-FORECAST-PLAN.md §6, §7, §12.6`, `packages/craftsman/shopman/craftsman/conf.py` (FORMULA_FACTOR_PROVIDERS vazio).

### BI-16 · O que esperar da semana/mês
- **Quem:** dono. **Onde:** desktop. **Gatilho:** compras, escala. **Freq:** semanal.
- **Objetivo real:** dimensionar compra de insumo e escala.
- **Mínimo:** total provável com faixa, dia a dia, dias sem base declarados (total não sai se um dia não
  tem base — honesto). **Falta:** conversão em insumo (Buyman tem dono próprio, não há ponte); em escala.
- **Caminho hoje:** Projeção → trocar horizonte. **Padrão:** PLANEJAR. **Evidência:** `bi_forecast.py:_totals`.

### BI-17 · Separar o troco
- **Quem:** gerente / caixa de abertura. **Onde:** hoje na aba Projeção do B.I. (gestor); o lugar do ato é
  o caixa (abertura de turno, PDV).
- **Gatilho:** véspera. **Freq:** diária · horas.
- **Objetivo real:** gaveta abastecida antes da fila, sem correr ao banco/vizinho no pico.
- **Mínimo:** "separe R$ X, dos quais R$ Y em moeda". Existe (`bi_change`: hábito de troco por venda em
  dinheiro × pedidos em dinheiro prováveis; piso em moeda). **Falta:** chegar a quem abre o caixa — está
  atrás do gate `view_bi`, numa aba de gestor; não vira sugestão no "abrir turno" do Cashman.
- **Entrada:** nenhuma aqui; no mundo: contar e colocar o fundo (REGISTRAR-QUANTIDADE no caixa).
- **Caminho hoje:** gestor abre B.I. → Projeção → lê → avisa alguém. **Mínimo:** a abertura de turno
  sugere o fundo; 1 toque "conferido". **Padrão:** PLANEJAR → empurrar como TAREFA.
  **Evidência:** `composables/useBiChange.ts`, `projections/bi_change.py`, comentário em `pages/forecast.vue`.

### BI-18 · Cenários com IA
- **Quem:** dono. **Onde:** desktop. **Gatilho:** curiosidade/revisão. **Freq:** rara.
- **Objetivo real:** receber hipóteses que o dono não formulou, com base e incógnitas.
- **Mínimo:** propostas com "o que sustenta" e "o que os dados não dizem". Existe (foco vendas ou
  produção; só agregados; relatório versionado; falha registrada). **Falta:** janela (usa default, não a
  barra); o gesto "transformar em corte no Explorar" ou "em tarefa"; desligado sem `AI_ASSIST_API_KEY`.
- **Entrada:** escolher foco, Gerar (segundos). **Efeito:** grava `BIScenarioReport`. Erro baixo.
- **Padrão:** ENTENDER (assistido). **Evidência:** `pages/scenarios.vue`, `bi/scenarios.py`, `projections/bi_scenarios.py`.

### BI-19 · O que acabou, ficou sem vender, sobrou
- **Quem:** dono, chefe padeiro. **Onde:** hoje só no Explorar, como 8 exemplos ("Produtos que mais
  acabam", "Horas sem poder vender", "Sobra por produto", "Falta por dia da semana"…).
- **Gatilho:** é a **pergunta nº 1 do dono**. **Freq:** diária/semanal · horas.
- **Objetivo real:** produzir a quantidade certa por SKU: nem sobrar, nem faltar.
- **Mínimo:** por SKU, lado a lado: sobra (un/R$) e falta (horas sem vender, hora em que esgotou, hora em
  que chegou) — B1/B2. **O que existe:** métricas `soldout_days`, `hours_without_stock`,
  `unavailable_hours/share`, `paused_hours`, `leftover`, e o `soldout_at` já alimenta a sugestão
  (`LedgerAwareDemandBackend`). **Falta:** um painel; sobra e falta no **mesmo** quadro (hoje são
  métricas separadas, uma de cada vez); hora de chegada; venda estimada perdida (B4); e sobretudo
  aparecer **na tela de plano do dia seguinte** e no fechamento.
- **Caminho hoje:** Explorar → Cenário → achar o exemplo entre ~35 → ler; repetir para a outra cara.
  **Mínimo:** plano de amanhã com "Croissant: acabou 10h40 em 3 dos últimos 4 sábados; sobrou 0" ao
  lado da sugestão. **Padrão:** ENTENDER → PLANEJAR / EXPLICAR-NO-LUGAR.
  **Evidência:** `bi_explore.py` (famílias `shelf`, `outage`), `presentation/bi.ts` EXPLORE_EXAMPLES, `shopman/shop/adapters/demand.py`, `docs/plans/BI-INSIGHTS-MAP.md §7`.

### BI-20 · Salão
- **Quem:** dono. **Onde:** Explorar (6 exemplos: "Quando sobra mesa", "Quando o salão bate no teto",
  "Faturamento por lugar-hora"…) e Perfis (RevPASH).
- **Gatilho:** decisão de mesas. **Freq:** rara.
- **Objetivo real:** decidir acrescentar/retirar mesas e o horário de reforço.
- **Mínimo:** vezes no teto por faixa × dia, faturamento por lugar-hora (faixas grossas, não %).
  **Falta:** veredito; ligação ao episódio "teve fila/desistência" (M7, sinal existe, pergunta não).
- **Padrão:** ENTENDER. **Evidência:** `bi_explore.py` (família `room`), `docs/plans/BI-QUESTION-CATALOG.md §3.2, §8.3`.

### BI-21 · Ser avisado (alarmes do B.I.)
- **Quem:** dono, gerente. **Onde:** hoje **só** o painel do Admin (`OperatorAlert` não resolvidos);
  o sino do Gestor de pedidos filtra `scope=orders` e o próprio app de B.I. não mostra alarme nenhum.
- **Gatilho:** `evaluate_bi_alerts` a cada ciclo do `maintenance_worker`.
- **Regras existentes (5):** silêncio de importação; dia abaixo do baseline do mesmo dia-da-semana
  (abstém com < 3 amostras); pedido nativo apagou histórico; quebra acumulada por gaveta (mensagem cega
  ao operador, detalhe só a quem audita); de-para de produto pendente.
- **Objetivo real:** ficar sabendo sem ter de abrir o B.I.
- **Mínimo:** a frase + o link para o registro. **Falta:** chegar ao celular do dono; link do aviso ao
  dia/turno/lote; os alarmes que importam para a operação **de amanhã** (vai faltar X, troco, receita
  com tempo errado) não existem — os 5 olham para trás ou para a infraestrutura de dados.
- **Entrada:** ack. **Efeito:** grava `BIAlertEvent`, `OperatorAlert`. **Custo do erro:** baixo-médio
  (alarme mudo = número que ninguém vê; alarme barulhento = equipe que ignora).
- **Padrão:** AVISAR. **Evidência:** `shopman/backstage/bi/alerts.py`, `surfaces/orders-nuxt/app/composables/useAlerts.ts` (comentário "B.I. ficam no Admin"), `projections/dashboard.py:_operator_alerts`.

### BI-22 · Ajustar réguas dos alarmes
- **Quem:** dono. **Onde:** Admin (`BIAlertRuleAdmin`). **Freq:** rara.
- **Objetivo real:** calibrar sensibilidade (ex.: R$ 50 em 7 dias de quebra).
- **Mínimo:** régua, janela, severidade, cooldown, ligado/desligado; último valor lido e "não opinou
  porque…". **Padrão:** CONFIGURAR. **Evidência:** `shopman/backstage/admin/bi_alerts.py`, `models/bi_alerts.py`.

### BI-23 · Curar a vocação de consumo dos SKUs
- **Quem:** dono (só quem conhece o cardápio: "o nome engana"). **Onde:** Admin.
- **Gatilho:** SKU novo; `propose_consumption_tags` propõe com `reviewed=False`.
- **Objetivo real:** classificar cada SKU como consome aqui · leva · híbrido, para os Perfis e o modo de
  consumo não mentirem.
- **Mínimo:** lista dos não revisados, escolha entre 3. **Falta:** chegar ao dono quando um SKU novo
  entra no catálogo (hoje: cobertura cai em silêncio na tela de Perfis); reetiquetar muda números
  passados e deveria ser evento datado.
- **Entrada:** escolher de lista de 3. **Efeito:** muda leituras históricas. **Custo:** médio.
- **Padrão:** CONFIGURAR (e TRIAR a fila de propostas). **Evidência:** `management/commands/propose_consumption_tags.py`, `docs/plans/BI-QUESTION-CATALOG.md §3.1.1.1, §5-F3`.

### BI-24 · Carregar histórico e contexto
- **Quem:** dono/técnico. **Onde:** comandos (`ingest_yooga`, `import_holidays`, `import_weather`,
  `setup_bi_reference`, `apply_catalog_taxonomy`) e Admin (de-para de produto do lote,
  `ImportBatch`). **Freq:** rara (feriado municipal: anual).
- **Objetivo real:** dar ao B.I. contexto (feriado, clima) e passado (Yooga) para comparar dias.
- **Regra transversal:** sem dado, a dimensão nem aparece. **Falta:** tela para o dono (é tudo
  linha de comando); clima diário automático (F4b aberto).
- **Padrão:** CONFIGURAR. **Evidência:** `shopman/backstage/bi/ingest/yooga.py`, `bi/mapping.py`, `management/commands/import_*.py`, `docs/plans/BI-DATA-FOUNDATION-PLAN.md`.

### BI-25 · Identificar-se
- **Quem:** gestor. **Onde:** `OperatorLogin`/`OperatorLock` do kit.
- **Regra:** `backstage.view_bi`; Caixa e a métrica de quebra exigem `cashman.audit_shift` (o Explorar
  esconde a família `cash` de quem não audita). **Padrão:** AUTORIZAR. **Evidência:** `app/app.vue`, `api/bi.py` (`BICashView.required_permission`, `can_audit_cash`).

### BI-26 · Explicar o dia estranho
- **Quem:** quem faz o fechamento. **Onde:** app de fechamento (não o B.I.).
- **Gatilho:** sinal automático (parou de vender, dia sem venda, fornada que não saiu, casa cheia
  sustentada `room_full_minutes`). **Freq:** só em dia com sinal.
- **Objetivo real:** tirar da amostra o dia em que a venda foi atrapalhada, para não virar previsão
  ruim. **Entrada:** escolher de lista (nunca digitar). **Efeito:** dia sai da base da sugestão e da
  projeção. **Falta:** "casa cheia → teve fila/desistência?" (M7) ainda não ligado.
- **Padrão:** TRIAR em 1 toque; é o modelo do que o B.I. deveria fazer em toda parte (o sistema nota, a
  pessoa explica). **Evidência:** `docs/plans/BI-INSIGHTS-MAP.md §13`, `bi/alerts.py` (`revenue_vs_baseline` exclui dia atrapalhado).

---

## 3. Padrões que enxergo neste app

### 3.1 Número → decisão → onde a decisão acontece (o eixo pedido)

| Número | Decisão que muda | Quem decide, onde | Devia ser empurrado como | Drill-down que falta |
|---|---|---|---|---|
| Sobra × falta × hora de esgotamento por SKU (BI-19) | quanto assar amanhã de cada SKU | chefe padeiro, **plano da Produção** | justificativa ao lado da sugestão; alerta "acabou antes das 11h em 3 de 4 sábados" | SKU → dias → lotes e hora do último `Move` |
| Projeção do dia + ocasião + clima (BI-15) | tamanho da fornada e da equipe | plano da Produção (véspera) | frase da ocasião na tela de plano; fator medido em `FORMULA_FACTOR_PROVIDERS` | dia projetado → os dias parecidos usados |
| Troco provável (BI-17) | fundo de caixa | caixa de abertura, **Cashman/PDV** | sugestão no "abrir turno" | — |
| Tempo de forno medido ≠ armado (BI-02) | `planned_seconds` da receita | chefe padeiro, receita | proposta de ajuste com aceitar | receita → OvenRuns |
| Perda por receita × defeito (BI-01) | processo/treino | produção | resumo semanal | perda → lotes/QC |
| Quebra por turno/gaveta, anomalia de gaveta (BI-06/07) | conversa, trava, manutenção do sensor | dono/auditor; técnico do PDV | alarme (existe, só no Admin); "sensor mudo" como tarefa de manutenção | `turno #shift_key` → eventos do turno → contagem |
| Em risco / perdidos (BI-10) | campanha de resgate | **Marketing** | audiência pronta no Marketing | segmento → lista de clientes |
| Contas em aberto (BI-08) | cobrar | gerente, cliente/caixa | lista de devedores com idade | devedor → cliente/vendas em conta |
| Dia abaixo do baseline (BI-21) | investigar o dia | dono | push (existe, só no Admin) | dia → pedidos, episódios, clima |
| Cobertura de etiquetas cai (BI-11/23) | etiquetar SKU novo | dono, Admin | tarefa "N SKUs novos sem vocação" ao cadastrar produto | cobertura → SKUs sem etiqueta |
| Faturamento/ticket/canal/hora (BI-03/04/05), Perfis (BI-11), Salão (BI-20), Pagamento (BI-09) | escala, horário, cardápio, mesas, maquininha | dono, raramente | resumo semanal/mensal; ficam como leitura | dia/SKU/canal → pedidos |

**Leitura:** só a última linha é "B.I. de visitar". Todo o resto é **um número que serve a uma
decisão tomada em outro app**, e hoje mora numa aba que o decisor (padeiro, caixa, marketing) não abre e
muitas vezes nem tem permissão de abrir.

### 3.2 Padrões
1. **O B.I. é destino, mas devia ser fonte.** Projeção, troco, sobra/falta, tempo de forno e em-risco são
   computados com cuidado e entregues à pessoa errada no lugar errado. O próprio plano escreveu o alvo
   ("o B.I. deixa de ser uma tela que se visita e vira a explicação do número que o padeiro já usa") e a
   ponte (F7/F8) não foi feita. Proposta de padrão: **EXPLICAR-NO-LUGAR**.
2. **A pergunta nº 1 do dono não tem painel.** Sobra/falta vive só como exemplos de Explorar; a aba
   "Produção" (default, primeira) mostra lotes, rendimento e forno — as perguntas do BI-PLAN v1, não as do
   dono (§7 do INSIGHTS-MAP).
3. **Zero drill-down.** Nenhum número do app é clicável para o registro operacional (pedido, turno, lote,
   SKU, cliente). As anomalias de gaveta citam `turno #N` sem link; "em risco: N" sem lista. O B.I. é
   honesto sobre a origem do número (cobertura, fonte, "não opinou porque") e mudo sobre **quais**
   registros o compõem.
4. **Alarmes existem e ninguém os vê.** 5 regras, worker, cooldown, mensagens com redação por persona —
   e o destino é o painel do Admin. Nem o app de B.I. nem o celular do dono recebem. E os alarmes que
   mudariam o amanhã (vai faltar, troco, receita fora do tempo) não existem; o plano adia corretamente
   "amanhã vai faltar" até haver **acerto da projeção medido** — que também não existe.
5. **A mesma pergunta com duas respostas.** Mix de pagamento: Caixa lê `DayClosing` (só dias fechados),
   Explorar lê o pedido (todo dia). Cruzamento hora × dia: dois gráficos na Vendas e uma tabela no
   Explorar. Perfis: três leituras × estimativa ponderada × faixa honesta respondem "quanto é salão" em
   três precisões na mesma página.
6. **Restos de decisões já tomadas.** "Tempo de forno por forno" e a dimensão `oven` seguem vivos com a
   casa tendo um forno (N3 arquivada). Rótulos crus (`channel_ref`, `method`) onde o resto do app fala
   português.
7. **Explorar é agrupar, não perguntar.** Falta filtro por valor ("só croissant", "só sábados"), mapa
   para dois eixos e comparação com período anterior — as três coisas que tornam uma resposta legível.
   Os ~35 exemplos curados são, na prática, a lista de perguntas do dono escondida num select.
8. **O sistema nota, a pessoa explica (o padrão bom).** Episódios no fechamento, "sem amostra não opina",
   dimensão de contexto que só aparece com dado, proposta de etiqueta com `reviewed=False`. É o padrão a
   generalizar: em vez de painéis, **perguntas pontuais empurradas a quem sabe responder**, só quando há
   sinal.
9. **Configuração do B.I. é de terminal.** Feriados, clima, Yooga, etiquetas e réguas vivem em comandos e
   Admin; o dono depende de um técnico para que a dimensão "feriado" exista.
10. **Mesmo trabalho, nomes diferentes:** "Cenários" (IA) × "Cenário" (corte salvo do Explorar) ×
    "cenário curado" (exemplo) — três coisas chamadas cenário. BI-15 (projeção) e BI-19 (abastecimento)
    são o mesmo trabalho (planejar a fornada) partido em duas abas que não se citam.

---

## 4. Cobertura (telas e estados)

| Rota / estado | O que é | Dispositivo que faz sentido | Por quê |
|---|---|---|---|
| `OperatorLogin` / `OperatorLock` / `OperatorSessionUnavailable` | identificação, troca de senha, rede caída | qualquer | gate genérico do kit |
| `/` Produção (carregando / erro / sem medição / com dados) | lotes, perda, rendimento, forno por receita e **por forno** | desktop (resumo no celular) | leitura semanal; painel "por forno" deveria sumir |
| `/sales` Vendas (com/sem histórico Yooga, com conflito de fonte) | tiles, série, hora, dia-da-semana, canal, top SKUs | desktop; resumo celular | comparação de períodos pede largura; o resumo cabe numa frase |
| `/cash` Caixa (403 sem `audit_shift`; sem fechamento; contas na casa opcional; anomalias opcionais) | quebra, contas, operador, gaveta, meios, gaveta por hora | desktop | tabelas de 6–9 colunas; auditoria é sentada. Anomalia e quebra deveriam chegar como push no celular |
| `/customers` Clientes | RFM, novos por semana | desktop | o gesto que importa (resgatar) mora no Marketing |
| `/profiles` Perfis (filtros dia/faixa; select de leitura; cobertura baixa) | perfis levar/local/misto, faixa, conciliação, categorias, bebida, RevPASH | desktop | densidade alta, decisão rara e estratégica |
| `/explore` Explorar (série / ranking / tabela 2 eixos / truncado / erro de gramática / vazio) | construtor métrica × dimensão × cruzamento | desktop | três selects + tabela longa; não serve ao celular |
| `/explore` menu ⋯ (salvar / favoritar / apagar) | diálogo de cenário salvo | desktop | — |
| `/forecast` horizonte dia (fechado / com ocasião / sem ocasião / sem base) + ramos "e se" + troco | projeção do dia | **celular/tablet** na véspera | decisão de fim de dia, em pé ou em casa; devia viver no plano da Produção |
| `/forecast` horizonte semana/mês (total / total ausente por dia sem base) | projeção do período + troco | desktop | planejamento de compras/escala |
| `/scenarios` (desligado sem credencial / gerando / falhou / relatórios) | cenários IA | desktop | leitura longa, rara |
| Barra de período (`OperatorPeriodPicker`, presets, personalizado, ‹ ›) | janela compartilhada | todas | — |
| `OfflineBanner`, `OperatorPwaRuntime` | offline / PWA | — | — |
| Fora do app: Admin `BIAlertRule`, `BIAlertEvent`, `BIScenarioReport`, etiquetas de consumo, lugares do salão, de-para de lote; painel do Admin com `OperatorAlert` | configuração e o único lugar onde alarmes de B.I. aparecem | desktop | configuração rara; os alarmes deveriam ir ao celular |
| Fora do app: comandos `ingest_yooga`, `import_holidays`, `import_weather`, `propose_consumption_tags`, `bi_calibrate`, `setup_bi_reference`, `refresh_bi_daily_series`, `evaluate_bi_alerts` | carga e manutenção | terminal | hoje exigem técnico |
| Fora do app: pergunta de episódio no fechamento | o sistema nota, a pessoa explica | tablet do fechamento | modelo a generalizar |
