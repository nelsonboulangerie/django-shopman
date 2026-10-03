# Compras: engenharia reversa por FUNÇÃO

App: `surfaces/purchase-nuxt` (uma página só, `app/pages/index.vue`; as "telas" são estado `useState("purchase-view")` = `panel | buy | receive | base`, e `base` tem as abas `materials | suppliers | costs | count`). Backend: `shopman/backstage/api/purchase.py` → `services/purchase.py` (1.996 linhas), `services/purchase_count.py`, `projections/purchase.py`, `projections/purchase_count.py`, pacotes `buyman` (Material, Supplier, SupplierContact, MaterialConversion, SupplierMaterialCost) e `stockman` (Move BUY/ADJUST, Batch, Quant), `shop/services/sku_namespace.py`, `sku_records.py`, `package_opening.py`, `receiving_position.py`, `invoice_fiscal_check.py`.

Permissão: tudo pede `backstage.operate_purchase`; Contagem pede também `backstage.audit_stock`; Permitir revenda pede também `shop.manage_catalog`.

Lido no ref `cdb1696`.

---

## 1. Mapa das funcionalidades

| ID | trabalho (na língua do operador) | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| C01 | Ver o que precisa de mim hoje no Compras | comprador / gerente | escritório, desktop; celular | início do dia, abrir o app | 1–3×/dia | horas | VIGIAR, TRIAR |
| C02 | Decidir o que repor e quanto | comprador | escritório, desktop | rotina de compra; insumo abaixo do ponto | 1×/dia ou por ciclo de fornecedor | horas a dias | PLANEJAR |
| C03 | Mandar o pedido ao fornecedor | comprador | desktop | decidiu repor | por insumo, alguns/dia | horas | EMITIR, AVISAR |
| C04 | Saber quanto vou gastar e com quantos fornecedores | comprador / dono | desktop | antes de mandar pedidos | 1×/ciclo | horas | ENTENDER |
| C05 | Aprovar a compra antes de mandar | gerente / dono | (sem tela) | (nenhum: endpoint órfão) | 0 | n/a | APROVAR |
| C06 | Ler a nota que chegou com a entrega | recebedor | porta de serviço, celular/tablet com câmera | entregador chegou com NF | 1–5/dia | minutos, **entregador esperando** | LER-CÓDIGO (novo) |
| C07 | Confirmar de quem é a entrega | recebedor | celular/tablet | NF lida ou entrega sem NF | por entrega | minutos | CONFERIR |
| C08 | Dizer qual insumo é cada linha da nota | recebedor | celular/tablet | NF com item novo ou sem de-para | por linha nova (cai com o tempo, a casa aprende) | minutos | TRIAR, LOCALIZAR |
| C09 | Dizer quanto vale cada embalagem em kg/l/un | recebedor | celular/tablet | linha com embalagem nova ou NF que discorda | por embalagem nova | minutos | CONFERIR, CONFIGURAR (inline) |
| C10 | Conferir quantidade e valor de cada linha | recebedor | celular/tablet | cada linha | por linha | minutos | CONFERIR, REGISTRAR-QUANTIDADE |
| C11 | Anotar validade e lote | recebedor | celular/tablet, olhando a embalagem | linha perecível | por linha perecível | minutos | REGISTRAR |
| C12 | Anotar avaria, falta ou ressalva | recebedor | celular/tablet | algo chegou errado | ocasional | minutos | ANOTAR (novo) |
| C13 | Dar o ok em cada linha | recebedor | celular/tablet | linha completa | por linha | minutos | CONFERIR |
| C14 | Descobrir o que ainda falta para fechar a entrada | recebedor | celular/tablet | apertou Confirmar e não deu | por entrada | segundos | CONFERIR (navegação de pendência) |
| C15 | Dar entrada no estoque | recebedor | celular/tablet | todas as linhas ok | 1–5/dia | minutos | AVANÇAR |
| C16 | Recusar/devolver a entrega | recebedor (+ gerente avisado) | celular/tablet | mercadoria errada/avariada | raro | minutos | CORRIGIR, AVISAR |
| C17 | Dar entrada sem nota (romaneio, produtor, feira) | recebedor | celular/tablet | entrega sem NF | ocasional | minutos | COMPOR |
| C18 | Saber se esta nota já entrou | recebedor / gerente | celular/tablet | dúvida, reescaneio, erro "já entrou" | ocasional | segundos | LOCALIZAR (sem tela) |
| C19 | Ver a situação de cada insumo | comprador / gerente | desktop | consulta, alerta do painel | diário | horas | ENTENDER, LOCALIZAR |
| C20 | Definir o estoque mínimo de um insumo | comprador / gerente | desktop | insumo sem consumo medido nunca aparece para compra | raro (implantação) | dias | CONFIGURAR |
| C21 | Pôr um item comprado à venda (preço) | gerente / dono | desktop | decidiu revender (geleia, queijo) | raro | dias | CONFIGURAR |
| C22 | Dizer em que a embalagem vira quando aberta | gerente | desktop | item por unidade que a produção usa em peso | raro | dias | CONFIGURAR |
| C23 | Ver em que receitas o insumo entra | comprador / gerente | desktop | avaliar impacto de falta/troca | ocasional | horas | ENTENDER |
| C24 | Ver quem é o fornecedor e para quem vai o pedido | comprador | desktop | antes de mandar pedido; ligar para cobrar | ocasional | minutos | LOCALIZAR |
| C25 | Lançar a tabela de preços de um fornecedor | comprador | desktop | implantação; tabela nova chegou | raro/mensal | dias | REGISTRAR-QUANTIDADE (lote), CONFIGURAR |
| C26 | Lançar um custo avulso | comprador | desktop | cotação por telefone, preço mudou | semanal | dias | REGISTRAR |
| C27 | Escolher qual custo/fornecedor é o padrão | comprador / gerente | desktop | trocou de fornecedor | raro | dias | CONFIGURAR, APROVAR |
| C28 | Contar o estoque de insumos e acertar o sistema | gerente / dono | estoque/câmara fria, tablet ou celular | rotina (semanal/mensal), desconfiança | semanal–mensal | horas | CONFERIR, REGISTRAR-QUANTIDADE, AUTORIZAR |
| C29 | Resolver nota que discorda do cadastro fiscal | gerente / contador | Admin (fora do app) | NF com NCM/CEST/ST diferente | ocasional | dias | CORRIGIR (fronteira) |

29 trabalhos.

---

## 2. Fichas

### C01 · Ver o que precisa de mim hoje
- **Quem**: comprador (na casa, o gerente ou o dono acumulam).
- **Onde**: escritório, desktop hoje (painel com quatro cartões + fila + atalhos laterais). Faz sentido no celular também: é uma lista curta de decisões.
- **Gatilho**: abrir o app; rotina da manhã.
- **Frequência/urgência**: 1–3×/dia · horas · cliente esperando: não.
- **Objetivo real**: saber, em um olhar, se há algo a comprar, algo para receber/terminar de conferir, ou cadastro que impede o Compras de funcionar.
- **Informação mínima**: nº de insumos a repor e o total estimado; se há entrada em conferência inacabada; quais cadastros travam a sugestão (sem consumo, sem custo padrão).
  - **Sobra**: o cartão "Base: N insumos ativos" (número que não pede ação); o cartão "Conversões: custos estimados" (é um aviso de qualidade, não decisão do dia); a lista lateral "Escanear NF / Revisar compras / Entrada sem NF / Consultar Base" repete a navegação da barra; o rótulo "Pronto/Revisar" do recebimento repete o contador.
  - **Falta**: **pedidos já enviados que ainda não chegaram** (não existe esse conceito: "enviado" não liga com a entrega); entregas esperadas hoje; histórico de entradas (projetado e não exibido, ver C18); fila de integridade sem prioridade de impacto (mostra "Sem custo preferencial" do mesmo jeito para 54 insumos).
- **Entrada**: escolher um item da lista curta.
- **Efeito**: só navega. Reversível.
- **Exceções**: fila vazia explicada por `reorderBlockers` (sem insumo / sem consumo medido / sem custo padrão / tudo coberto), cada um com o botão que resolve. Backend fora ou 403 → banner + `readonlyFallback`.
- **Caminho hoje**: 1 tela + 1 toque para ir a cada assunto → **mínimo**: 0 toques para saber; 1 para agir. O passo que não some: escolher qual decisão tomar.
- **Fronteira**: recebe consumo da Produção (baixas `MAKE` ao finalizar ficha), estoque do Stockman; manda para C02, C15, C19/C25.
- **Padrão**: VIGIAR + TRIAR.
- **Evidência**: `pages/index.vue` (seção `view === 'panel'`), `composables/usePurchaseDesk.ts` (`metrics`, `integrityQueue`, `reorderRows`, `reorderBlockers`), `presentation/purchase.ts` (`reorderBlockers`, `materialIssues`).

### C02 · Decidir o que repor e quanto
- **Quem**: comprador.
- **Onde**: desktop.
- **Gatilho**: rotina; insumo cai abaixo do ponto (`coverageDays <= replenishAtDays` ou `stock < minStock`).
- **Frequência/urgência**: diário · horas a dias · não.
- **Objetivo real**: pedir a quantidade certa de cada insumo, a tempo de chegar antes de faltar, sem comprar além do que vence.
- **Informação mínima**: insumo, quanto tem, quanto dura (cobertura em dias vs. prazo do fornecedor), quanto o sistema sugere (na unidade de compra), de quem, quanto custa.
  - **Sobra**: SKU e categoria em cada cartão; status "Revisar/Pronto/Enviado" quando "Pronto" (approved) nunca é atingível pela tela.
  - **Falta**: **não há como mudar a quantidade** sugerida (o servidor manda `suggestedQty` arredondado para a unidade de compra e é isso que vai); não há como escolher outro fornecedor que não o do custo padrão; não há a conta explicada (consumo diário × ciclo prazo+revisão+segurança, teto por validade) no lugar da decisão; não aparece rendimento/perda (`weightedUsableFactor`, `suggestedNetQty` vêm do servidor e só viram texto em `purchaseSuggestionLabel`).
- **Entrada**: confirmar (aceitar sugestão); idealmente digitar número para ajustar.
- **Efeito**: nenhum até C03.
- **Exceções**: sugestão zero sem consumo medido (círculo: sem consumo, mínimo derivado é zero, insumo nunca aparece) → resolve em C20. Sem custo padrão → cartão diz "Definir" fornecedor e o envio falha no servidor (`purchase_preferred_cost_required`).
- **Caminho hoje**: abrir Comprar, ler cartão a cartão → **mínimo**: uma lista agrupada por fornecedor com a sugestão já pronta; 1 toque por fornecedor. O passo que não some: o "sim" do comprador à quantidade.
- **Fronteira**: consumo vem da Produção (`craftsman` finalizar → `Move MAKE`); prazo vem do fornecedor ou do histórico de entregas; vai para C03.
- **Padrão**: PLANEJAR.
- **Evidência**: `projections/purchase.py` (`_material_projection`, `_suggested_qty`, `_lead_time_map`, `_daily_use_map`), `presentation/purchase.ts` (`reorderRows`, `purchaseSuggestionLabel`).

### C03 · Mandar o pedido ao fornecedor
- **Quem**: comprador.
- **Onde**: desktop.
- **Gatilho**: decidiu repor (C02).
- **Frequência/urgência**: por insumo · horas · não.
- **Objetivo real**: o fornecedor recebe, pelo canal dele, o que comprar, quanto e para quando.
- **Informação mínima**: para quem vai (pessoa/canal), o que vai (itens, quantidades, valor estimado), data de entrega pedida.
  - **Sobra**: nada; falta quase tudo.
  - **Falta**: **o pedido é por insumo, não por fornecedor**: cada "Enviar pedido" dispara uma mensagem (`notification.send`) com uma linha só. Três insumos do mesmo atacadista = três e-mails. A "Consolidação" da tela só conta, não junta. Falta **prévia da mensagem** e o destinatário no lugar do botão (só aparece na aba Fornecedores, C24). Falta observação ao fornecedor (`operator_note` existe no contexto, sempre vazio).
- **Entrada**: confirmar.
- **Efeito**: cria Directive `notification.send` deduplicada (material+fornecedor+qty+custo), grava `Material.metadata.purchase.request_status = "sent"` + ref `PC-AAMMDD-XXXXXX`, canal, destinatário. Irreversível (mensagem saiu). Custo do erro: médio (pedido errado ao fornecedor).
- **Exceções**: sem custo padrão, fornecedor inativo, fornecedor sem contato/canal (`supplier_contact_missing`), sugestão zero (`purchase_request_not_needed`). **Bug funcional**: `request_status = "sent"` nunca volta a "review" (nem ao receber, nem com o tempo); a tela desabilita o botão quando `sent`, então **o insumo nunca mais pode ser pedido pela tela** depois do primeiro envio.
- **Caminho hoje**: 1 toque por insumo → **mínimo**: 1 toque por fornecedor (pedido com N linhas). O passo que não some: o envio.
- **Fronteira**: sai para o fornecedor (e-mail/SMS/WhatsApp via ManyChat); deveria virar "entrega esperada" no Receber (C06), e não vira.
- **Padrão**: EMITIR + AVISAR.
- **Evidência**: `services/purchase.py` (`set_purchase_request_status`, `_queue_supplier_purchase_request`, `_supplier_dispatch_route`, `_purchase_request_snapshot`), `usePurchaseDesk.ts` (`sendPurchaseRequest`), `index.vue` (botão "Enviar pedido" com `disabled` em `sent`).

### C04 · Saber quanto vou gastar
- **Quem**: comprador, dono.
- **Onde**: desktop (aside "Consolidação").
- **Gatilho**: antes de enviar.
- **Frequência/urgência**: por ciclo · horas · não.
- **Objetivo real**: ter o total e o número de fornecedores para decidir se cabe no caixa.
- **Informação mínima**: total previsto, total por fornecedor.
  - **Sobra**: "Solicitações = N" (é a lista ao lado). **Falta**: total por fornecedor (é o que o pedido consolidado precisaria); cotejo com o caixa/contas a pagar.
- **Entrada**: nenhuma (leitura).
- **Efeito**: nenhum.
- **Caminho hoje**: visível ao lado → **mínimo**: cabeçalho de cada grupo de fornecedor na lista de C02. Este trabalho é parte de C02, não tela à parte.
- **Padrão**: ENTENDER.
- **Evidência**: `index.vue` (aside da seção `buy`), `purchaseTotalQ`, `purchaseSupplierCount`.

### C05 · Aprovar a compra (endpoint órfão)
- **Quem**: gerente/dono, se houvesse.
- **Onde**: nenhum. `POST /purchase/requests/<sku>/approve/` existe, grava `request_status = "approved"`, e o front tem `approveRequest` no client mas nenhum botão chama.
- **Objetivo real**: alçada de aprovação antes de gastar. Hoje não existe na operação.
- **Efeito**: status "approved" (rótulo "Pronto" na tela) sem efeito nenhum além do rótulo.
- **Caminho mínimo**: decidir se existe. Se o comprador é o dono, é zero passos; se não, é APROVAR em lote por fornecedor.
- **Padrão**: APROVAR (sem uso).
- **Evidência**: `api/purchase.py` (`PurchaseRequestApproveView`), `composables/usePurchaseApi.ts` (`approveRequest`, não usado), `index.vue` (`requestStatusLabels.approved = "Pronto"`).

### C06 · Ler a nota que chegou
- **Quem**: recebedor (quem estiver na porta: padeiro, atendente, gerente).
- **Onde**: porta de serviço, celular ou tablet com câmera. É o único trabalho deste app que pertence ao celular por natureza.
- **Gatilho**: entregador chegou com a DANFE.
- **Frequência/urgência**: 1–5/dia · minutos · **entregador esperando**.
- **Objetivo real**: transformar o papel da nota em uma lista de itens para conferir, sem digitar.
- **Informação mínima**: o código da DANFE (QR da NFC-e ou barras/44 dígitos da NF-e).
  - **Sobra**: três caminhos lado a lado (Escanear NF, campo de texto + "Traduzir NF", "Ler foto da NF") e o par "Com NF / Sem NF"; para quem tem a nota na mão, é **um** gesto (câmera), com os outros como fuga.
  - **Falta**: dizer de cara se o provedor de leitura (`SHOPMAN_PURCHASE_INVOICE_READER`) está ligado. Sem ele, a leitura **só valida a chave e acha o fornecedor pelo CNPJ**; os itens não vêm ("Itens não vieram do provedor fiscal; lance ou importe as linhas") e o recebedor digita tudo à mão, o que muda a natureza do trabalho.
- **Entrada**: ler código (câmera ZXing com lanterna, ou foto, ou colar/digitar).
- **Efeito**: servidor monta rascunho (`activeReceipt`) com fornecedor e linhas; **o rascunho vive só no navegador** (`useState`), o servidor não guarda. Reversível (nada gravado no estoque).
- **Exceções**: chave inválida (`invoice_key_invalid`); câmera indisponível → mensagem e fuga para foto/digitação; fornecedor não cadastrado → é **cadastrado automaticamente** a partir do emitente da nota (`_register_supplier_from_issuer`) ou adotado por nome.
- **Caminho hoje**: abrir Receber → (já está em "Com NF") → Escanear NF → apontar → 3 toques → **mínimo**: 1 (abrir o app já na câmera quando o dispositivo é o da porta). O passo que não some: apontar para o código.
- **Fronteira**: vem do fornecedor (papel); vai para C07–C15. Deveria casar com um pedido enviado em C03, e não casa.
- **Padrão**: LER-CÓDIGO (novo: ler código de barras/QR para trazer um documento ou item; também serve ao PDV e ao KDS).
- **Evidência**: `index.vue` (`openInvoiceScanner`, `readInvoiceImage`, `acceptScannedInvoice`, diálogo `scannerOpen`), `services/purchase.py` (`scan_invoice`, `_invoice_reader_draft`, `parse_invoice_access_key`, `_register_supplier_from_issuer`), `config/settings.py:1877`.

### C07 · Confirmar de quem é a entrega
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: NF lida (já preenchido) ou entrada sem NF (escolher).
- **Frequência/urgência**: por entrega · minutos · sim.
- **Objetivo real**: o estoque, o custo e o de-para aprendido ficam no fornecedor certo.
- **Informação mínima**: nome do fornecedor; com NF, nada (o CNPJ está na chave).
  - **Sobra**: com NF, o seletor de fornecedor é um risco, não uma ajuda: trocar por engano é o erro que o servidor recusa (`supplier_not_issuer`). Documento, prazo de pagamento e lead time ao lado do seletor não pedem decisão na porta.
  - **Falta**: nada essencial.
- **Entrada**: escolher de lista (só sem NF).
- **Efeito**: troca o fornecedor do rascunho e reavalia as conversões permitidas (conversão pode ser por fornecedor).
- **Exceções**: fornecedor inativo recusado no confirmar; fornecedor sem CNPJ cadastrado escapa da checagem de emitente (logado).
- **Caminho hoje**: 1 seletor sempre visível → **mínimo**: 0 com NF; 1 escolha sem NF.
- **Padrão**: CONFERIR.
- **Evidência**: `services/purchase.py` (`_require_supplier_is_issuer`, `confirm_receipt`), `usePurchaseDesk.ts` (`setReceiptSupplier`; `setReceiptMode` **pré-seleciona o primeiro fornecedor da lista**, o que deixa o erro a um toque de distância).

### C08 · Dizer qual insumo é cada linha da nota
- **Quem**: recebedor.
- **Onde**: celular/tablet, gaveta da linha.
- **Gatilho**: linha da NF sem de-para conhecido.
- **Frequência/urgência**: alta nas primeiras notas de cada fornecedor, cai depois (o confirmar grava `invoice_product_map` no fornecedor e as próximas notas já vêm resolvidas) · minutos · sim.
- **Objetivo real**: o código do fornecedor ("MANTEIGA S/SAL CX 5 KG PRESIDENT") vira o insumo da casa uma vez e para sempre.
- **Informação mínima**: descrição da nota; a sugestão (por GTIN = certeza, por nome = palpite com %); busca no cadastro de compra.
  - **Sobra**: nada grave. **Falta**: **criar o insumo** quando ele não existe no Compras: não há caminho no app (cadastro só pelo Admin ou pelo "Permitir compra" do Catálogo); a entrada trava.
- **Entrada**: escolher de lista (busca) ou confirmar sugestão ("É este").
- **Efeito**: linha aponta para o Material; ao confirmar a entrada, o de-para é aprendido (sobrescreve com log se mudou).
- **Exceções**: insumo inativo e **SKU produzido aqui** (ficha ativa com aquele output) são recusados no confirmar (`material_is_produced_here`): a mesma peça não entra por duas portas. A tela só descobre no servidor.
- **Caminho hoje**: tocar na linha → gaveta → aceitar sugestão (1) ou buscar (2–3) → **mínimo**: 0 quando o GTIN casa (aceitar automaticamente); 1 quando é palpite.
- **Fronteira**: cadastro de compra (`buyman.Material`) vem do Admin/Catálogo; o de-para fica no `Supplier.metadata`.
- **Padrão**: TRIAR + LOCALIZAR.
- **Evidência**: `components/ReceiptLineSheet.vue` (campo "Item", `UiSelect`, "É este"), `services/purchase.py` (`_resolve_receipt_material`, `_learn_invoice_product_map`).

### C09 · Dizer quanto vale cada embalagem
- **Quem**: recebedor.
- **Onde**: celular/tablet, dentro da gaveta.
- **Gatilho**: linha `requiresConversion` sem conversão, ou NF que discorda da conversão cadastrada.
- **Frequência/urgência**: por embalagem nova (cai com o tempo) · minutos · sim.
- **Objetivo real**: "7 CX" vira "35 kg" no estoque; errar aqui erra estoque e custo por kg de todas as receitas.
- **Informação mínima**: a conta pronta ("4 × saco 25 kg = 100 kg") e de onde ela veio (par tributável da nota ou gramatura no nome).
  - **Sobra**: nada; o desenho já reduz a "Confere / Não é assim". **Falta**: nada essencial.
- **Entrada**: confirmar a conta; ou cadastrar embalagem (texto + número + exato/aproximado); ou escolher uma já cadastrada.
- **Efeito**: cria `MaterialConversion` no servidor (com autor), ligada ao fornecedor; a linha passa a apontar para ela. Fica para sempre (é cadastro). Custo do erro: **alto** (multiplica estoque e custo; "10 unidades" lidas como "10 kg").
- **Exceções**: sem insumo escolhido não há conversão (campo só aparece depois de C08); conversão "aproximada" vira aviso "≈" em estoque e custo daí em diante.
- **Caminho hoje**: 1 toque (Confere) no caso feliz; 4–5 no cadastro manual → **mínimo**: 1 (a conta proposta); o passo que não some: a pessoa assina o fator (R4 da ADR-024: a NF sugere, a pessoa declara).
- **Fronteira**: vira cadastro da Base (Custos/Conversões); alimenta o custo-base usado pelo custeio de receitas.
- **Padrão**: CONFERIR + CONFIGURAR inline.
- **Evidência**: `components/ReceiptConversion.vue`, `usePurchaseDesk.ts` (`acceptReceiptLineConversion`, `acceptReceiptLineInvoiceAxes`, `declareReceiptLineConversion`), `services/purchase.py` (`declare_conversion`, `_conversion_from_invoice_axes`).

### C10 · Conferir quantidade e valor
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: cada linha.
- **Frequência/urgência**: por linha · minutos · sim.
- **Objetivo real**: o que entra no estoque é o que está fisicamente na porta, e o custo é o da nota.
- **Informação mínima**: quantidade da nota vs. contada (na unidade de compra), valor da nota, quanto fica por kg.
  - **Sobra**: o valor é campo editável sempre; com NF, o valor **é** o da nota (só muda se a nota estiver errada, que é caso de ressalva, não de redigitação). **Falta**: o par "nota diz X / chegou Y" explícito: a quantidade vem preenchida com o valor da nota e o recebedor sobrescreve, sem a tela marcar que divergiu da nota; a falta deveria virar ocorrência automática.
- **Entrada**: digitar número (só quando difere).
- **Efeito**: base_qty = qty × fator; custo unitário = total ÷ qty; ao confirmar, o custo vira `SupplierMaterialCost` (preferido se não houver outro).
- **Exceções**: qty ≤ 0 bloqueia; valor vazio só avisa ("Conferir valor").
- **Caminho hoje**: 2 campos por linha → **mínimo**: 0 quando bate; 1 número quando não bate.
- **Padrão**: CONFERIR + REGISTRAR-QUANTIDADE.
- **Evidência**: `ReceiptLineSheet.vue` (bloco `qty`), `services/purchase.py` (`_resolve_receipt_line`, `_write_receipt`, `_upsert_supplier_cost`).

### C11 · Anotar validade e lote
- **Quem**: recebedor.
- **Onde**: celular/tablet, com a embalagem na mão.
- **Gatilho**: insumo perecível (`shelfLifeDays` definido).
- **Frequência/urgência**: por linha perecível · minutos · sim.
- **Objetivo real**: dá para gastar primeiro o que vence primeiro e chamar o lote certo num recall.
- **Informação mínima**: data de validade (da nota, grupo `rastro`, ou da embalagem); lote do fornecedor.
  - **Sobra**: nada. **Falta**: leitura do lote/validade pela câmera (GS1-128 na caixa) seria o caminho natural, e não existe.
- **Entrada**: escolher dia (atalhos) / digitar texto curto.
- **Efeito**: cria `stockman.Batch` com validade; o Move BUY leva o lote.
- **Exceções**: perecível sem validade bloqueia na tela e no servidor (`expiry_required`).
- **Caminho hoje**: 1–2 toques → **mínimo**: 0 quando a nota traz `rastro`; 1 quando não.
- **Padrão**: REGISTRAR (variante de REGISTRAR-QUANTIDADE para data/texto).
- **Evidência**: `ReceiptLineSheet.vue` (bloco `expiry`, `OperatorDayPicker`), `services/purchase.py` (`_batch_ref`, `_write_receipt`).

### C12 · Anotar avaria, falta ou ressalva
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: algo chegou errado.
- **Frequência/urgência**: ocasional · minutos · sim.
- **Objetivo real**: ficar escrito o que chegou diferente, para cobrar o fornecedor.
- **Informação mínima**: o quê, em qual item.
  - **Sobra**: duas caixas de texto diferentes (ocorrência por linha e "Ressalva geral" no rodapé, que no modo sem NF vira "Referência em papel"). **Falta**: ocorrência estruturada (falta N, avaria N, trocado) que reduza a quantidade e gere a cobrança; hoje é texto livre que só vai para a nota do lote e o Move.
- **Entrada**: digitar texto.
- **Efeito**: grava em `Batch.notes` e no Move; é também o "motivo" exigido para C16.
- **Padrão**: ANOTAR (novo: texto livre de exceção preso a um item; aparece também em contagem e devolução).
- **Evidência**: `ReceiptLineSheet.vue` (campo "Ocorrência"), `index.vue` ("Ressalva geral"), `services/purchase.py` (`_receipt_batch_note`).

### C13 · Dar o ok em cada linha
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: linha completa.
- **Frequência/urgência**: por linha · segundos · sim.
- **Objetivo real**: alguém assume que olhou aquele item.
- **Informação mínima**: o item, o que entra, o estoque depois.
  - **Sobra**: o ok é **obrigatório em toda linha** (servidor recusa `receipt_line_unchecked`) mesmo quando nada foi mexido: numa nota de 20 itens que bate, são 20 toques que não acrescentam informação. **Falta**: "conferir todos os que batem" de uma vez.
- **Entrada**: confirmar.
- **Efeito**: `checked = true`; a gaveta fecha.
- **Caminho hoje**: abrir gaveta + "Marcar como conferido" = 2 toques por linha → **mínimo**: 1 toque para a nota inteira + 1 por exceção.
- **Padrão**: CONFERIR.
- **Evidência**: `ReceiptLineSheet.vue` (`onCheck`), `services/purchase.py` (`_resolve_receipt_line`).

### C14 · Descobrir o que falta para fechar
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: apertou Confirmar com pendência, ou olhou o painel "Conferência".
- **Frequência/urgência**: por entrada · segundos · sim.
- **Objetivo real**: ir direto ao campo que falta.
- **Informação mínima**: primeira pendência, em qual item.
  - **Sobra**: a lista de pendências aparece em três lugares (linha da lista, painel lateral, toast do botão) mais avisos "watch" deduplicados. **Falta**: nada; é o trabalho mais bem resolvido do app.
- **Entrada**: tocar na pendência.
- **Efeito**: abre a gaveta, rola, foca e marca o campo.
- **Caminho hoje**: 1 toque → **mínimo**: 0 (o próprio botão Confirmar leva lá, como já faz).
- **Padrão**: CONFERIR (navegação de pendência). Proposta de rótulo: **APONTAR**, o sistema leva o operador até o próximo gesto obrigatório (vale para todos os apps).
- **Evidência**: `index.vue` (`reportReceiptBlocker`, `focusReceiptLine`, `revealTarget`), `presentation/purchase.ts` (`receiptPendingItems`, `receiptFirstReceiptBlocker`), `utils/receiptFocus.ts`.

### C15 · Dar entrada no estoque
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: todas as linhas ok.
- **Frequência/urgência**: 1–5/dia · minutos · sim (entregador quer assinatura/canhoto).
- **Objetivo real**: o estoque sobe, o custo atualiza, o lote nasce, e a casa nunca dá entrada duas vezes na mesma nota.
- **Informação mínima**: nº de itens, valor total, de quem.
- **Entrada**: confirmar.
- **Efeito**: atômico: `Batch` por linha com validade, `Move kind=BUY` no `receiving_position` do SKU (revenda vai para posição vendável, insumo para a de insumos), custo do fornecedor, de-para aprendido, sugestão de catálogo/rascunho fiscal (NCM/CEST/GTIN), `OperatorAlert` se a nota diverge do cadastro fiscal. Idempotente por chave da NF (ou hash do manual): a segunda tentativa responde "Esta nota já entrou em dd/mm às hh:mm por fulano". **Irreversível pela tela** (não há estorno de entrada; só Contagem). Custo do erro: alto.
- **Exceções**: todas as validações de C07–C13 repetidas no servidor; `receipt_in_progress`; `receipt_already_received`.
- **Caminho hoje**: 1 toque → aviso de sucesso com "Escanear outra NF". **Mínimo**: 1. É o passo que não some.
- **Fronteira**: Stockman (estoque visível no PDV/Produção), custeio de receitas, Catálogo (sugestões no Admin), alertas do operador.
- **Padrão**: AVANÇAR (fecha o ciclo pedido → recebido).
- **Evidência**: `services/purchase.py` (`confirm_receipt`, `_write_receipt`, `run_idempotent_mutation`, `_suggest_catalog_from_invoice`, `_alert_fiscal_divergence`), `shop/services/receiving_position.py`.

### C16 · Recusar/devolver a entrega
- **Quem**: recebedor; o gerente/comprador é avisado.
- **Onde**: celular/tablet.
- **Gatilho**: mercadoria errada, vencida, avariada.
- **Frequência/urgência**: raro · minutos · sim.
- **Objetivo real**: a mercadoria volta no caminhão e fica registrado por quê, para cobrar crédito.
- **Informação mínima**: motivo; quais itens.
  - **Falta**: **recusa parcial**: a operação é tudo ou nada sobre o rascunho; para aceitar 9 itens e devolver 1 o recebedor teria de confirmar sem a linha e, depois, remontar a linha para "devolver" (o rascunho zera ao confirmar). Falta avisar o **fornecedor**: o aviso é só interno (`SHOPMAN_PURCHASE_INTERNAL_RECIPIENT`, backend `console` por padrão), com o contato de qualidade do fornecedor dentro do texto.
- **Entrada**: digitar motivo + confirmar.
- **Efeito**: Directive `notification.send` interna, deduplicada; **nenhum movimento de estoque**; rascunho zerado. Reversível (nada mexeu no estoque).
- **Exceções**: sem motivo → botão desabilitado e servidor recusa.
- **Caminho hoje**: digitar ressalva + "Registrar devolução" = 2 → **mínimo**: 2 (motivo + confirmar), por linha quando parcial.
- **Padrão**: CORRIGIR + AVISAR.
- **Evidência**: `services/purchase.py` (`reject_receipt`, `_supplier_contact_line`), `index.vue` (`onRejectReceipt`).

### C17 · Dar entrada sem nota
- **Quem**: recebedor.
- **Onde**: celular/tablet.
- **Gatilho**: produtor, feira, romaneio, compra no atacarejo sem NF.
- **Frequência/urgência**: ocasional · minutos · às vezes.
- **Objetivo real**: o mesmo de C15, sem documento fiscal.
- **Informação mínima**: fornecedor, itens, quantidade, valor, validade.
  - **Sobra**: a referência em papel nasce preenchida com "Romaneio em papel conferido na entrega" (texto fixo que vira "motivo" e entra no hash de idempotência: duas entradas iguais no mesmo dia com o mesmo texto podem colidir). **Falta**: nada essencial.
- **Entrada**: COMPOR: escolher fornecedor, adicionar item (abre a gaveta já no item novo, pré-selecionado com o **primeiro insumo da lista**), preencher.
- **Efeito**: igual a C15, sem de-para/fiscal; aviso "Sem documento fiscal" em toda linha.
- **Caminho hoje**: Sem NF → fornecedor → (+Item → escolher → qty → valor → validade → ok) × N → Confirmar → **mínimo**: fornecedor + por item (insumo, qty, valor) + confirmar.
- **Padrão**: COMPOR.
- **Evidência**: `usePurchaseDesk.ts` (`setReceiptMode`, `addReceiptLine`), `services/purchase.py` (`_manual_source_ref`).

### C18 · Saber se esta nota já entrou
- **Quem**: recebedor, gerente.
- **Onde**: nenhum. O servidor projeta `receiptHistory` (últimas 25 entradas, a partir da trava de idempotência), mas **o tipo do front não tem o campo e nenhuma tela mostra**. A mensagem de erro diz "Confira o histórico de recebimentos", que não existe na tela.
- **Gatilho**: dúvida, reescaneio, nota esquecida na pasta.
- **Objetivo real**: responder "já entrou?" antes de reescanear.
- **Informação mínima**: lista de entradas do dia: fornecedor, itens, valor, quem, quando.
- **Caminho hoje**: impossível (só descobre tentando de novo) → **mínimo**: 0 (o escaneio de uma nota já recebida abre o resumo dela, em vez do rascunho).
- **Padrão**: LOCALIZAR.
- **Evidência**: `projections/purchase.py` (`_receipt_history`, `RECEIPT_HISTORY_LIMIT`), `types/purchase.ts` (`PurchaseProjection` sem `receiptHistory`), `services/purchase.py` (`_receipt_already_received_message`).

### C19 · Ver a situação de cada insumo
- **Quem**: comprador / gerente.
- **Onde**: desktop (tabela com SKU, insumo, estoque, cobertura, mínimo editável, custo-base, status; painel lateral do item).
- **Gatilho**: consulta; alerta do painel.
- **Frequência/urgência**: diário · horas · não.
- **Objetivo real**: saber se um insumo está bem: tem estoque, tem quem venda, tem custo.
- **Informação mínima**: estoque (com "≈" se aproximado), dura quantos dias, custo padrão por unidade-base, o problema (se houver).
  - **Sobra**: SKU como coluna; o status "Em ordem/Revisar/Comprar" repete a lista de problemas do painel lateral. **Falta**: histórico (último recebimento, preço anterior, tendência de consumo); de onde veio o consumo.
- **Entrada**: buscar, filtrar "Atenção", escolher item.
- **Efeito**: nenhum.
- **Padrão**: ENTENDER + LOCALIZAR.
- **Evidência**: `index.vue` (`baseView === 'materials'`), `presentation/purchase.ts` (`enrichMaterial`, `materialIssues`).

### C20 · Definir o estoque mínimo
- **Quem**: comprador / gerente.
- **Onde**: desktop, coluna "Mínimo" da tabela de insumos, salvar em lote.
- **Gatilho**: insumo sem consumo medido (Produção ainda não finaliza fichas no sistema) nunca vira sugestão.
- **Frequência/urgência**: implantação; raro depois · dias · não.
- **Objetivo real**: o insumo volta a ser comprado mesmo sem histórico.
- **Informação mínima**: o mínimo declarado vs. o derivado do consumo (a tela distingue "definido" e "pelo consumo", e de propósito não pré-preenche).
  - **Falta**: dizer o efeito ("com 10 kg, sugere comprar X agora").
- **Entrada**: digitar número (vários); zero apaga.
- **Efeito**: `Material.metadata.purchase.min_stock`. Reversível.
- **Caminho hoje**: digitar N campos + "Salvar mínimos" → **mínimo**: igual. O passo que não some: o número.
- **Fronteira**: é o remendo para a falta de consumo vindo da Produção; deveria ser exceção.
- **Padrão**: CONFIGURAR.
- **Evidência**: `services/purchase.py` (`set_min_stock`), `projections/purchase.py` (`min_stock_declared`), `index.vue` (coluna Mínimo).

### C21 · Pôr um item comprado à venda
- **Quem**: gerente / dono (precisa `shop.manage_catalog`).
- **Onde**: desktop, painel lateral do insumo, "Permitir revenda".
- **Gatilho**: decidiu revender o que compra (geleia, queijo, chá).
- **Frequência/urgência**: raro · dias · não.
- **Objetivo real**: o mesmo SKU, com o mesmo estoque, aparece no PDV com um preço.
- **Informação mínima**: preço (sugerido = custo × markup da categoria, arredondado para cima); "por kg" se `unit == kg` (só balcão).
- **Entrada**: confirmar + digitar preço.
- **Efeito**: cria/religa `offerman.Product` com o mesmo SKU (`start_selling`); desligar pausa e deslista sem apagar. Porteiro: mesmo SKU só com mesma unidade (`sku_namespace.refuse_incoherent_unit`). Reversível.
- **Exceções**: SKU produzido aqui → "a venda dele é do Catálogo"; unidade incoerente → recusa.
- **Caminho hoje**: marcar → preço (pré-preenchido) → "Colocar à venda" = 2–3 → **mínimo**: 2.
- **Fronteira**: espelho do "Permitir compra" no app Catálogo (`CatalogProductPurchaseView`).
- **Padrão**: CONFIGURAR.
- **Evidência**: `services/purchase.py` (`set_sale`), `shop/services/sku_records.py`, `shop/services/sku_namespace.py`, `index.vue` (`onResaleToggle`, `confirmSale`).

### C22 · Dizer em que a embalagem vira quando aberta
- **Quem**: gerente.
- **Onde**: desktop, painel lateral do insumo.
- **Gatilho**: compra-se por unidade (lata, pote), a receita usa em gramas.
- **Frequência/urgência**: raro · dias · não.
- **Objetivo real**: a Produção abre a embalagem sozinha no fechamento da fornada e o estoque em gramas fecha.
- **Informação mínima**: insumo aberto (existente ou criar), quanto vem em uma embalagem, validade depois de aberto.
- **Entrada**: escolher de lista + digitar 2 números.
- **Efeito**: `declare_opening` / `clear_opening` (`shop/services/package_opening.py`). Reversível.
- **Caminho hoje**: Definir → 3 campos → Salvar = 5 → **mínimo**: 3.
- **Fronteira**: consumido pela Produção ao finalizar fornada.
- **Padrão**: CONFIGURAR.
- **Evidência**: `services/purchase.py` (`set_opening`), `presentation/purchase.ts` (`openingView`), `index.vue` (`saveOpening`).

### C23 · Ver em que receitas o insumo entra
- **Quem**: comprador / gerente.
- **Onde**: desktop, lista no fim do painel lateral e embaixo do nome na tabela.
- **Objetivo real**: avaliar o impacto de faltar ou trocar o insumo.
- **Informação mínima**: nomes das receitas; idealmente quanto cada uma consome.
  - **Falta**: o peso de cada receita no consumo; link para a ficha.
- **Entrada**: nenhuma.
- **Padrão**: ENTENDER.
- **Evidência**: `projections/purchase.py` (`_recipes_map`), `index.vue`.

### C24 · Ver quem é o fornecedor e para quem vai o pedido
- **Quem**: comprador.
- **Onde**: desktop, Base › Fornecedores.
- **Gatilho**: antes de enviar pedido (C03); cobrar atraso; recusa.
- **Objetivo real**: saber a quem ligar e para onde o pedido vai sair.
- **Informação mínima**: nome do dia a dia, contato do pedido (pessoa ou central, ou "não tem para onde ir"), prazo, condição de pagamento, contatos ativos.
  - **Sobra**: "SLA %" e "Prefer." nos cartões. **Falta**: esta informação **no botão "Enviar pedido"** (C03), onde a pergunta é feita. Edição é só no Admin (decisão declarada: contato é config).
- **Entrada**: escolher fornecedor.
- **Padrão**: LOCALIZAR.
- **Evidência**: `index.vue` (`baseView === 'suppliers'`, `activeSupplierContacts`, `selectedSupplierPortfolio`), `projections/purchase.py` (`_supplier_projection`).

### C25 · Lançar a tabela de preços de um fornecedor
- **Quem**: comprador.
- **Onde**: desktop, Base › Custos, tabela em lote.
- **Gatilho**: implantação (54 insumos sem custo padrão impedem qualquer pedido); tabela nova recebida.
- **Frequência/urgência**: raro/mensal · dias · não.
- **Objetivo real**: todo insumo tem quem venda e por quanto.
- **Informação mínima**: fornecedor; por insumo: unidade de compra e valor.
- **Entrada**: escolher fornecedor + digitar N valores.
- **Efeito**: `upsert_costs` tudo-ou-nada, com erro por linha; promove a padrão só o primeiro custo de cada insumo (`prefer_if_missing`), de propósito, para não repontar o custeio de dezenas de receitas num gesto.
- **Caminho hoje**: fornecedor → valores → Salvar → **mínimo**: igual; poderia vir de planilha/foto da tabela.
- **Padrão**: REGISTRAR-QUANTIDADE (lote) + CONFIGURAR.
- **Evidência**: `services/purchase.py` (`upsert_costs`), `presentation/purchase.ts` (`costBatchPayload`, `costBatchLineErrors`), `index.vue` (Tabela do fornecedor).

### C26 · Lançar um custo avulso
- **Quem**: comprador.
- **Onde**: desktop, Base › Custos, formulário "Lançar custo"; também chega pelo botão "Lançar custo" de cada cartão de Comprar.
- **Gatilho**: cotação, mudança de preço.
- **Objetivo real**: o preço de um insumo num fornecedor fica atualizado.
- **Informação mínima**: insumo, fornecedor, unidade de compra, valor; o custo por unidade-base derivado.
- **Entrada**: 3 escolhas + 1 número + confirmar.
- **Efeito**: `upsert_cost` (opcionalmente padrão). Reversível (sobrescreve).
- **Exceções**: o recebimento já faz isso sozinho (C15 grava o custo da nota), então o avulso é para cotação, não para o preço pago.
- **Caminho hoje**: 5 → **mínimo**: 2 (valor + salvar) vindo do cartão do insumo.
- **Padrão**: REGISTRAR.
- **Evidência**: `services/purchase.py` (`upsert_cost`), `usePurchaseDesk.ts` (`saveQuote`).

### C27 · Escolher o custo/fornecedor padrão
- **Quem**: comprador / gerente.
- **Onde**: desktop, Base › Custos, tabela "Custos por fornecedor", botão "Usar padrão".
- **Gatilho**: trocou de fornecedor; o mais barato mudou.
- **Objetivo real**: o pedido sai para o fornecedor certo e as receitas custeiam pelo preço certo.
- **Informação mínima**: os custos do mesmo insumo lado a lado por unidade-base, com o atual marcado.
  - **Falta**: a tabela lista todos os custos de todos os insumos misturados; a comparação **por insumo** (quem é mais barato por kg) não está agrupada; `SupplierCostRow` com `deltaPercent` existe no tipo e não é usado na tela.
- **Entrada**: escolher de lista curta.
- **Efeito**: muda `is_preferred`; reponta fornecedor do pedido (C03) e custo das receitas. Custo do erro: médio.
- **Caminho hoje**: achar a linha numa tabela longa + 1 → **mínimo**: 1, dentro do insumo.
- **Padrão**: CONFIGURAR + APROVAR.
- **Evidência**: `usePurchaseDesk.ts` (`setPreferredCost`), `types/purchase.ts` (`SupplierCostRow` sem uso), `index.vue`.

### C28 · Contar o estoque e acertar o sistema
- **Quem**: gerente / dono (`backstage.audit_stock`).
- **Onde**: hoje, tabela no desktop. **Faz sentido no tablet/celular**, dentro da câmara fria e do estoque seco, com a mão ocupada.
- **Gatilho**: rotina semanal/mensal; desconfiança de saldo; antes de pedido grande.
- **Frequência/urgência**: semanal–mensal · horas · não.
- **Objetivo real**: o saldo do sistema volta a ser o físico, com motivo escrito para cada diferença.
- **Informação mínima**: insumo, unidade, quanto contou. O saldo do sistema e a diferença **depois** de digitar (mostrar antes induz a "confirmar o sistema").
  - **Sobra**: a coluna "Sistema" visível antes de contar (contagem cega é o padrão de auditoria). **Falta**: ordem pelo lugar físico (posição/prateleira); contagem por posição (o servidor soma todas as posições e ajusta no quant mais novo); contar em embalagens (3 sacos) e não só em kg; motivos de lista curta (quebra, vencido, erro de lançamento, consumo não lançado) em vez de texto livre; contagem parcial salva (hoje o que foi digitado vive no navegador).
- **Entrada**: digitar número (por insumo) + texto (motivo, só quando diverge) + confirmar no diálogo.
- **Efeito**: por divergência, `stock.adjust` (ou `receive kind=ADJUST` se não há quant), com usuário e motivo no ledger. Irreversível (só nova contagem corrige). Custo do erro: alto.
- **Exceções**: sem permissão → tela "Contagem restrita ao gestor"; saldo mudou entre carregar e confirmar → a divergência recalculada continua exigindo motivo.
- **Caminho hoje**: N números + motivos + Lançar + Confirmar → **mínimo**: N números (+ motivo nas divergências) + 1 confirmação. O passo que não some: contar.
- **Fronteira**: Stockman (ledger); o motivo "consumo não lançado" aponta para a Produção.
- **Padrão**: CONFERIR + REGISTRAR-QUANTIDADE + AUTORIZAR.
- **Evidência**: `services/purchase_count.py` (`submit_count`, `_apply_count`), `projections/purchase_count.py`, `api/purchase.py` (`PURCHASE_COUNT_PERMISSIONS`), `index.vue` (seção count + diálogo).

### C29 · Resolver nota que discorda do cadastro fiscal
- **Quem**: gerente / contador.
- **Onde**: Admin (fora do Compras). O Compras só mostra a divergência na gaveta ("Nada muda no cadastro ao confirmar").
- **Gatilho**: NF com NCM/CEST/ST diferente do produto.
- **Objetivo real**: o cadastro fiscal fica certo para a NFC-e de venda.
- **Efeito no Compras**: rascunho fiscal + `OperatorAlert`; não trava a entrada.
- **Padrão**: CORRIGIR (fronteira com Catálogo/Admin).
- **Evidência**: `ReceiptLineSheet.vue` (`data-receipt-fiscal-divergences`), `services/purchase.py` (`_suggest_catalog_from_invoice`, `_alert_fiscal_divergence`), `shop/services/invoice_fiscal_check.py`.

---

## 3. Padrões neste app

1. **Dois apps num só, com dispositivos opostos.** O *comprador* (C01–C05, C19–C27) é desktop, horizonte de dias, sem ninguém esperando. O *recebedor* (C06–C18) está na porta, de celular, com o entregador esperando. A mesma barra de quatro seções serve aos dois, e o recebedor atravessa "Painel" e o par "Com NF / Sem NF" para chegar à câmera. Contagem (C28) é um terceiro papel (gerente no estoque, tablet) escondido como aba da "Base".
2. **O ciclo não fecha: pedido e recebimento não se conhecem.** "Enviado" é um rótulo no Material, preso para sempre (`request_status` nunca volta); a entrega não abate o pedido; não há "esperando entrega". O painel não sabe dizer o que está a caminho. O mesmo objeto (pedido de compra) deveria nascer em C03 e morrer em C15/C16.
3. **"Pedido" é por insumo, e a consolidação só conta.** C02, C03 e C04 são um trabalho só: *aprovar o pedido de um fornecedor* (lista agrupada, total no cabeçalho, quantidades ajustáveis, uma mensagem com N linhas). Hoje são cartões por insumo + um aside de soma.
4. **Conferir por exceção, não por linha.** C10, C11 e C13 obrigam um gesto por linha mesmo quando a nota bate (ok obrigatório no servidor). O padrão certo é "tudo que bate entra; mexa no que não bate", como já faz o desenho de C09 ("Confere / Não é assim").
5. **Custo é o mesmo trabalho com quatro portas.** Recebimento grava custo (C15), tabela em lote (C25), avulso (C26), "Usar padrão" (C27), "Lançar custo" no cartão de Comprar. O recebimento já é a fonte mais confiável (preço pago); a cotação é exceção.
6. **O sistema pede ao operador o que ele mesmo já sabe.** Fornecedor pré-selecionado (primeiro da lista) quando a NF já disse o CNPJ; quantidade e valor como campos editáveis quando vêm da nota; mínimo declarado como remendo porque o consumo não chega da Produção; insumo pré-selecionado (primeiro da lista) ao lançar sem NF.
7. **A informação não está no lugar da decisão.** "Para quem vai o pedido" mora na aba Fornecedores, não no botão Enviar; "já entrou?" está projetado e não exibido; a conta da sugestão (consumo × ciclo, teto de validade, rendimento) não aparece junto da sugestão; a comparação de preços não está agrupada por insumo.
8. **Texto livre onde o mundo tem uma lista curta.** Ocorrência (avaria/falta/trocado), motivo da recusa, motivo de divergência da contagem. Rótulo novo proposto: **ANOTAR**.
9. **Rascunho frágil.** Recebimento e contagem vivem só no navegador (`useState`); recarregar ou trocar de dispositivo perde a conferência de uma nota de 20 itens.
10. **Rótulos novos propostos**: **LER-CÓDIGO** (trazer documento/item pela câmera: NF aqui, mas também lote GS1, etiqueta no PDV), **ANOTAR** (exceção em texto preso a um item), **APONTAR** (o sistema leva ao próximo gesto obrigatório; C14 é a referência da casa).

---

## 4. Cobertura (telas e estados)

| Tela / estado | Onde no código | Dispositivo que faz sentido | Por quê |
|---|---|---|---|
| Login / bloqueio de operador / sessão indisponível | `app.vue` (`OperatorLogin`, `OperatorLock`, `OperatorSessionUnavailable`) | qualquer | portaria do kit |
| Banner "Conectando" / backend fora / 403 / erro de ação | `index.vue` topo (`readonlyFallback`, `actionError`) | qualquer | estado, não tela |
| Painel (cartões, fila de decisão, fila vazia explicada, atalhos) | `view === 'panel'` | desktop e celular | lista curta de decisões; o celular do gerente serve |
| Comprar: lista de reposição | `view === 'buy'` | desktop | decisão de dias, com números lado a lado |
| Comprar: fila vazia explicada (4 motivos) | `reorderBlockers` | desktop | idem |
| Comprar: aside Consolidação | `view === 'buy'` aside | desktop | deveria ser cabeçalho de grupo |
| Receber: rascunho em branco (convite) | `receiptIsBlank` | celular/tablet | porta de serviço |
| Receber com NF: chave/QR/colar/foto | `receiptMode === 'invoice'` | celular (câmera) | nota na mão, entregador esperando |
| Diálogo Escanear NF (câmera, lanterna) | `scannerOpen` | celular | câmera traseira |
| Receber sem NF: referência em papel | `receiptMode === 'manual'` | celular/tablet | idem |
| Fornecedor da entrada (seletor + documento) | `data-receipt-anchor="supplier"` | celular/tablet | só relevante sem NF |
| Lista de itens da entrada (status por linha) | `receiptRows` | celular/tablet | visão da nota |
| Gaveta do item: insumo/sugestão | `ReceiptLineSheet.vue` | celular/tablet | um item por vez |
| Gaveta: conversão (Confere / Não é assim / Cadastrar embalagem / Escolher) | `ReceiptConversion.vue` | celular/tablet | idem |
| Gaveta: quantidade, valor, validade, lote, ocorrência, estoque depois, divergência fiscal | `ReceiptLineSheet.vue` | celular/tablet | idem |
| Painel Conferência (pendências, ressalva geral, Confirmar, Registrar devolução) | `view === 'receive'` aside | celular/tablet (rodapé fixo) | ação final |
| Aviso de resultado (entrada confirmada / devolução registrada) | `receiptOutcome` | celular/tablet | encadeia a próxima nota |
| Histórico de recebimentos | (projetado em `receiptHistory`, **sem tela**) | celular/tablet | responderia "já entrou?" na porta |
| Base › Insumos: tabela + mínimos em lote | `baseView === 'materials'` | desktop | tabela larga, edição em lote |
| Base › Insumos: painel do item (problemas, Permitir revenda, Quando aberto vira, receitas) | aside `selectedMaterial` | desktop | cadastro raro |
| Base › Fornecedores: cartões + detalhe (contatos, carteira) | `baseView === 'suppliers'` | desktop (consulta) e celular (ligar) | consulta; o telefone serve para ligar |
| Base › Custos: tabela do fornecedor (lote) | `baseView === 'costs'` | desktop | digitação em massa |
| Base › Custos: Lançar custo avulso | aside de costs | desktop | cotação |
| Base › Custos: custos por fornecedor (Usar padrão) | tabela de costs | desktop | comparação |
| Base › Contagem: sem permissão | `countForbidden` | qualquer | estado |
| Base › Contagem: tabela | `baseView === 'count'` | **tablet/celular** | quem conta está na câmara fria, não no escritório |
| Diálogo Confirmar contagem (lista de ajustes) | `countConfirmOpen` | tablet/celular | assinatura final |
| Atalho por URL `?view=` | `app.vue` `applyShortcutView` | qualquer | entrada direta do Hub |
