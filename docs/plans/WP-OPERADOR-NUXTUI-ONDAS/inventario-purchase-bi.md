> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# Onda 0: inventário de Compras (purchase-nuxt) e B.I. (bi-nuxt) para a migração ao Nuxt UI canônico

Auditoria de leitura, sem build e sem teste. Worktree `operador-nuxt-ui-migracao-16676a`, branch `claude/operador-nuxtui-onda0-base` (HEAD `e79ed522d`, pilha #1528 + #1521). Caminhos `arquivo:linha` são relativos ao diretório do app, salvo quando escritos por inteiro.

Observação de base: o `docs/plans/WP-GESTOR-CANON-LAUDO.md` **não existe nesta branch**. Ele está no `main` (commit `2ef7e958b`). Li a versão de lá.

## 0. Números de abertura

| | Compras | B.I. |
|---|---|---|
| Rotas (páginas) | 1 (`/`), com 4 vistas por estado e 4 cadastros na Base | 8 (`/`, `/sales`, `/cash`, `/customers`, `/profiles`, `/explore`, `/forecast`, `/scenarios`) |
| Linhas em `app/` (vue+ts) | ~9.400 (página única de 2.868) | ~5.100 (maior página: 467) |
| Componentes locais | 9 | 20 (3 deles são gráficos) |
| `<button>/<select>/<textarea>` crus (métrica do ledger) | **132** (teto do ledger: 132) | **24** (teto: 24) |
| `<input>` cru | 14 | 1 |
| `<table>` cru | 4 | 8 |
| `<Nuxt*>` de UI usados | 0 | 0 |
| `:ui=` por instância | 0 | 0 |
| `type="date|time|..."` nativo | 0 | 0 |
| Valores arbitrários `[...]` | 47 | 12 |
| Travessão (U+2014) visível ao usuário | 5 (fallbacks em `presentation/purchase.ts`) | 0 |
| Endpoints próprios do app | 1 GET de projeção + 1 GET de contagem + 13 POST | 11 GET + 1 POST + CRUD de cenários salvos (GET/POST/PATCH/DELETE) + 1 POST de IA |
| Schema TS exportado do Django | **não** (tipos à mão, 723 linhas) | **sim** (`export_bi_schema` → `app/generated/biContract.ts`, com teste de deriva) |
| Mock backend / e2e / visual | **não** | **não** |
| SSR | `ssr: false` | SSR ligado (default) |
| Testes vitest | 10 arquivos, 156 `it` | 7 arquivos, 91 `it` |

## 1. Compras (purchase-nuxt)

### 1.1 Telas

O app tem **uma rota só**, `app/pages/index.vue` (2.868 linhas, template de 1133 a 2868). As "seções" não são rotas: são `useState("purchase-view")` (`composables/usePurchaseDesk.ts`), trocadas pelo rail e pela barra do polegar (`components/PurchaseNav.vue:66`). Deep link por query: `/?view=panel|buy|receive|base` (`app.vue:12-21`, atalho do PWA "Recebimento" em `nuxt.config.ts:43-45`) e `/?view=base&material=SKU` ou `&supplier=REF` (`app.vue:23-30`, destino da busca da suíte).

Shell (`app.vue:35-75`): `<div data-suite="v3">` com `OfflineBanner`, `PurchaseNav place="rail"` (`OperatorSuiteRail`), coluna com `<NuxtPage>`, `PurchaseNav place="bar"` (`OperatorSectionBar`), `OperatorSessionUnavailable`, `OperatorLogin`, `OperatorLock`, `OperatorStationSetup`, `OperatorSonner`, `OperatorPwaRuntime`. **Não usa `OperatorAppRoot` nem `OperatorSuiteShell`**, ao contrário do Gestor (`orders-nuxt/app/app.vue`).

Vistas internas de `pages/index.vue`:

| Vista | Linhas | O que mostra |
|---|---|---|
| Cabeçalho | 1138-1355 | `OperatorPageHeader` com 8 slots usados (ver 1.4) |
| Faixa de estado | 1358-1394 | "Conectando ao Core de compras", modo só leitura, erro de ação + Atualizar |
| **Painel** | 1397-1543 | 4 cartões-atalho (Comprar, Receber, Conversões, Base), lista "Precisa de você" (bloqueios da fila, 5 reposições, recebimento em conferência, 4 de integridade), coluna de atos (Escanear NF, Digitar chave, Sem NF, Revisar compras, Consultar Base) |
| **Comprar** | 1546-1627 | vazio explicado (bloqueios com gesto), cartões de reposição (cobertura, sugestão, fornecedor, estimado; Lançar custo / Enviar pedido), aside "Consolidação" |
| **Receber: começo** | 1678-1763 | aviso de resultado (1641-1673), "Em conferência · Continuar", "Entradas de hoje" (comprovante), campo de chave + "Traduzir NF" + "Ler foto da NF", input file oculto (1751), "Escanear NF" grande |
| **Receber: conferência** | 1766-1906 | fornecedor/papel (Sem NF), vínculo de fornecedor (Com NF), `ReceiptExceptionFlow`, lista "Itens da entrada" (Item, Ler EAN, linhas com Remover), `ReceiptConferencePanel` (tablet) |
| Gaveta do item | 1911-1935 | `ReceiptLineSheet` (encaixada no tablet, folha à direita no resto) |
| Painel da conferência | 1937-1946 | `ReceiptConferencePanel` no desktop |
| Polegar do celular | 1952-2010 | Escanear NF / Digitar chave / Sem NF; "Contei N volumes" / "Algo não bate"; "Confirmar entrada" com o primeiro bloqueio |
| Câmeras | 2013-2042 | 3× `CodeScannerSheet` (EAN, bipar volumes contínuo com Zerar/Usar N, ler embalagem GS1) |
| Comprovante | 2045-2068 | `UiSheet` bottom com dl + Compartilhar |
| Ressalva geral | 2071-2087 | `UiSheet` bottom com textarea + Pronto |
| **Base › Insumos** | 2093-2411 | cartões no celular (2096-2151), tabela de 6 colunas (2152-2242), barra "N mínimos alterados" (2246-2275), painel docado do insumo 372 px (2279-2410: situação, papéis, Permitir revenda + preço, Quando aberto vira, Receitas) |
| **Base › Fornecedores** | 2414-2507 | cartões e aside (prazo, entrega, última, pagamento, contatos, carteira) |
| **Base › Custos** | 2510-2698 | "Tabela do fornecedor" em lote (2514-2632), "Lançar custo" (2635-2669), "Custos por fornecedor" (2671-2696) |
| **Base › Contagem** | 2701-2787 | bloqueio por permissão, tabela Sistema/Contado/Diferença/Motivo, Limpar/Lançar contagem |
| Diálogo de contagem | 2791-2831 | `UiDialog` "Lançar a contagem no estoque?" |
| Câmera da NF | 2833-2866 | `UiDialog fullscreen` preto com vídeo, lanterna, "Ler foto da NF" |

### 1.2 Gestos (inventário de zero regressão)

Endpoints: `composables/usePurchaseApi.ts:19-39`, base `/api/v1/backstage/purchase/`. Toda mutação devolve `{ok, purchase}` (a projeção inteira) e passa por `runBackendAction` (`usePurchaseDesk.ts:712`).

**Cabeçalho e chrome**

| Gesto | Onde | Efeito / endpoint |
|---|---|---|
| Trocar de vista (Painel, Comprar, Receber, Base) | `PurchaseNav.vue:66` via rail e barra | estado `view` |
| "‹ Voltar ao começo do Receber" (celular, NF aberta) | `index.vue:1143-1151` | `receiptParked = true` |
| Segmentado da Base (Insumos, Fornecedores, Custos, Contagem), desktop | `index.vue:1182-1200` | `baseView` |
| Segmentado da Base, celular, slot `#below` | `index.vue:1332-1353` | `baseView` |
| Busca da Base (insumos/contagem por nome ou SKU; custos na tabela) | `index.vue:1203-1211` | `query` ou `batchQuery` |
| Busca de item da entrada | `index.vue:1213-1220` | `receiveQuery` (filtro local) |
| Lupa de 48 px que abre a busca (tablet) | `index.vue:1251-1260` | `receiveSearchOpen` |
| Com NF / Sem NF (começo do Receber) | `index.vue:1269-1278` | `setReceiptMode` |
| Ordenar insumos (Nome, Situação, Estoque, Cobertura): `<select>` invisível sobre rótulo | `index.vue:1284-1295` | `baseSort` local |
| Atualizar (ícone) | `index.vue:1296` | `refresh()` → GET projeção |
| ⋯ / ⋮ (`PurchaseMoreMenu`) | `index.vue:1234, 1239, 1240, 1297-1302`; itens `index.vue:960-976` e `refreshMenuItems`/`baseMenuItems` `:843-847` | Lançar item, Trocar NF, Lançar sem NF, Lançar com NF, Ressalva geral, Atualizar (R), Registrar devolução, Contagem de estoque (`onMoreMenu` `:978-993`) |
| Chip Atenção | `index.vue:1308-1311` | `onlyAlerts` |
| Chips "Compras hoje" (urgentes → Comprar, sem preferencial → Custos só faltantes, custos estimados → Custos) | `index.vue:1315-1329` | navegação |

**Painel e Comprar**

| Gesto | Onde | Efeito |
|---|---|---|
| 4 cartões-atalho | `index.vue:1400, 1408, 1416, 1424` | navegação |
| Ação do bloqueio (ex.: abrir Custos) | `index.vue:1455-1463`, `1567-1575` | `openBase` |
| Linha de reposição / recebimento / integridade | `index.vue:1466, 1484, 1494` | navegação, `selectMaterialAndView` |
| Escanear NF / Digitar chave / Sem NF / Revisar compras / Consultar Base | `index.vue:1517, 1525, 1529, 1534, 1538` | `openReceive`, `openReceiveTyping` (foco no campo da chave) |
| Lançar custo (cartão de reposição) | `index.vue:1600` | `openQuoteFor` → Base › Custos com insumo/fornecedor |
| Enviar pedido | `index.vue:1601-1603` | POST `requests/<sku>/send/` |
| Fornecedores / Custos e conversões | `index.vue:1617, 1621` | navegação |

**Receber**

| Gesto | Onde | Efeito / endpoint |
|---|---|---|
| Escanear outra NF / Lançar outra entrada; Fechar aviso | `index.vue:1662, 1666` | `startNextReceipt`, `dismissReceiptOutcome` |
| Continuar conferência | `index.vue:1694` | `receiptParked = false` |
| Abrir comprovante de entrada de hoje | `index.vue:1706` | `receiptSheetEntry` |
| Compartilhar comprovante | `index.vue:2062` | `navigator.share` ou clipboard (`:1034-1056`) |
| Digitar/colar chave (textarea) | `index.vue:1725` | `invoiceInput` |
| Traduzir NF | `index.vue:1728-1736` | POST `receipts/scan-invoice/` `{qrPayload}` |
| Ler foto da NF (input file `capture="environment"`) | `index.vue:1737-1745, 1751`; `readInvoiceImage` `:478-500` | decodifica com `@zxing` e chama scan-invoice |
| Escanear NF (câmera, `getUserMedia`) | `index.vue:1754, 1959`; `openInvoiceScanner` `:446-472` | diálogo `:2833-2866`, scan-invoice ao ler |
| Lanterna; fechar câmera; Ler foto a partir da câmera | `index.vue:2843, 2836, 2860` | `toggleScannerTorch`, `stopInvoiceScanner` |
| Fornecedor da entrada (`UiNativeSelect`) | `index.vue:1772-1775, 1790-1793` | `setReceiptSupplier` |
| Referência em papel (textarea) | `index.vue:1779` | `receiptNote` |
| Item (+), Ler EAN | `index.vue:1832, 1836` | `addAndOpenReceiptLine`, `CodeScannerSheet` EAN |
| Abrir linha / Remover linha (sem confirmação) | `index.vue:1853-1875, 1876-1884` | `openReceiptLine`, `removeReceiptLine` |
| Bipar volumes: Zerar / Usar N | `index.vue:2028, 2031` | contagem local → `setReceiptVolumesCounted` → POST `receipts/volumes/` (`usePurchaseDesk.ts:782-792`) |
| Contei N volumes / Algo não bate (polegar) | `index.vue:1978-1991` | `onExceptionCount`; `onSomethingOff` (`scrollIntoView` ad hoc `:949-952`) |
| Confirmar entrada (polegar) | `index.vue:1994-2004` | bloqueio vira toast com "Ir até lá" (`:662-673`), senão POST `receipts/confirm/` |
| Ressalva geral: texto + Pronto | `index.vue:2081-2084` | `receiptNote` |
| `ReceiptExceptionFlow`: Detalhes; ±1 na quantidade; abrir item; Ver os N itens; atalho de validade; Ler da embalagem; Outra data (`OperatorDayPicker`); Trocar validade; Recontar; ±1 volume; Bipar cada volume; Contei N volumes; itens que batem; Devolver só este item | `ReceiptExceptionFlow.vue:198, 204, 208, 214, 251, 263, 302, 316, 326, 335, 353, 386, 401, 419, 430, 441, 459, 482, 497, 508` | emits `count`, `expiry`, `open`, `scan-volumes`, `read-package`, `qty`, `reason`, `reject-line` (`:46-56`); devolver item = POST `receipts/reject/` |
| `ReceiptLineSheet`: anterior/próximo; Item (`UiSelect` pesquisável); Ler EAN; "É este"; campo Qtd / campo Valor; teclado numérico próprio (0-9, vírgula, ±1, Limpar, apagar, Próximo); Ler da embalagem; Validade (`OperatorDayPicker`); Lote; Ocorrência; Marcar como conferido / desmarcar; Fechar; Devolver só este item; Remover item | `ReceiptLineSheet.vue:219, 222, 266, 276, 296, 320, 336, 355-371, 397, 402, 409, 413, 455, 466, 478, 485, 495` | emits para `index.vue:1922-1934` |
| `ReceiptConversion` (na gaveta): Confere; Não é assim; Escolher uma já cadastrada (`UiNativeSelect`); Cadastrar embalagem (rótulo, fator, tipo) + Salvar/Cancelar; Voltar | `ReceiptConversion.vue:104, 113, 128-160, 169-201` | POST `conversions/` |
| `ReceiptDifference`: motivo da diferença (`UiRadioGroup`) | `ReceiptDifference.vue:57-62` | `lineNote` |
| `ReceiptConferencePanel`: ir ao bloqueio (NF, fornecedor, volumes, linha); Confirmar entrada; Ressalva geral; Registrar devolução | `ReceiptConferencePanel.vue:87, 97, 107, 116, 133, 149, 158` | âncoras; POST `receipts/confirm/`; POST `receipts/reject/` |
| Ler da embalagem (GS1: validade e lote) | `index.vue:1111-1130` | local |

**Base**

| Gesto | Onde | Efeito / endpoint |
|---|---|---|
| Abrir insumo (cartão ou nome na tabela) | `index.vue:2103, 2176` | `selectMaterial` |
| Mínimo por insumo (input decimal, celular e tabela) | `index.vue:2119-2126, 2199-2206` | rascunho |
| Limpar / Salvar mínimos | `index.vue:2258-2274` | POST `materials/min-stock/` |
| Permitir revenda (`UiCheckbox`) | `index.vue:2312-2318`; `onResaleToggle` `:209-223` | ligar abre preço; desligar = POST `materials/<sku>/sale/` |
| Preço + Colocar à venda (form) | `index.vue:2325-2344` | POST `materials/<sku>/sale/` |
| Quando aberto vira: Definir/Alterar, select do insumo aberto (`<select>` cru), quantidade, validade em dias, Salvar, Cancelar, Não abre mais | `index.vue:2354-2400` | POST `materials/<sku>/opening/` |
| Abrir fornecedor | `index.vue:2416` | `selectSupplier` |
| Tabela do fornecedor: fornecedor (`UiNativeSelect`), "Só os que faltam" (chip), unidade por linha (`UiNativeSelect`), valor por linha (input), Limpar, Salvar N como padrão | `index.vue:2524-2629` | POST `costs/batch/` |
| Lançar custo: insumo, fornecedor, unidade (3× `UiNativeSelect`), valor; Salvar custo / Salvar como padrão | `index.vue:2638-2667` | POST `costs/` |
| Usar padrão (por linha de custo) | `index.vue:2687-2690` | POST `costs/` com preferido |
| Contagem: contado e motivo por linha; Limpar; Lançar contagem → diálogo Voltar / Confirmar ajustes | `index.vue:2725-2783, 2816-2828` | GET `count/`; POST `count/confirm/` |

Endpoint declarado e **sem uso**: `approveRequest` (`usePurchaseApi.ts:91`, POST `requests/<sku>/approve/`).

**Não há upload de XML de NF-e.** A NF entra por QR/código de barras (câmera), foto (input file) ou chave digitada; o cliente manda só `qrPayload` (`types/purchase.ts:517-519`).

### 1.3 Atalhos e SSE

- `/` foca a busca da Base (exceto Fornecedores): listener manual em `window` (`index.vue:786-792, 800-801`).
- `R` atualiza, fora de campo e de diálogo: `onKeyStroke` (`index.vue:794-799`).
- Do kit: `Alt+1..4` nas seções (`withSectionShortcuts`, `operator-kit/app/presentation/suiteChrome.ts:31`), `?` abre `OperatorShortcutsHelp`, `/` na `OperatorSuiteSearch` (`:286`).
- **Sem SSE próprio** (comentário em `index.vue:750`). O kit faz poll de avisos (`useNotifications.ts:110-113`) e de capacidade (`useOperatorCapacity.ts:55-58`) pelo `OperatorInbox` do rail.

### 1.4 Peças do operator-kit usadas

| Peça | Usos | Onde |
|---|---|---|
| `OperatorPageHeader` | 1 (8 slots: `#lead`, `#subtitle`, `#status`, `#search` ×2 condicionais, `#phone-actions`, `#actions`, `#filters`, `#below`) | `index.vue:1139-1354`; `#below` em **`:1332`** |
| `OperatorLiveStatus` | 1 | `index.vue:1160-1166`, tons `off/calm/live` (`:765`) |
| `OperatorSuiteSearch` | 2 | `index.vue:1204, 1214` |
| `OperatorSuiteRail` / `OperatorSectionBar` | 1 + 1 | `PurchaseNav.vue:72, 82` (com `:current` + `@select`) |
| `OperatorDayPicker` | 2 | `ReceiptExceptionFlow.vue:335`, `ReceiptLineSheet.vue:402` |
| `UiNativeSelect` | 9 | `index.vue:1772, 1790, 2524, 2575, 2639, 2644, 2649`; `ReceiptConversion.vue:145, 186` |
| `UiFilterChip` | 5 | `index.vue:1308, 1315, 1320, 1325, 2540` (todos com slot `#icon`) |
| `UiSheet` (+Content/Header/Title/Description/X) | 4 folhas | `index.vue:2045, 2071`; `CodeScannerSheet.vue:37`; `ReceiptLineSheet.vue:518` |
| `UiDialog` (+Content/Title/Description) | 2 | `index.vue:2791, 2833` (`fullscreen hide-close`) |
| `UiPopover` | 1 | `PurchaseMoreMenu.vue:31` (menu de ação feito com popover + `role="menu"`) |
| `UiSelect` (pesquisável, `NuxtSelectMenu`) | 1 | `ReceiptLineSheet.vue:266` |
| `UiRadioGroup` | 1 | `ReceiptDifference.vue:57` |
| `UiCheckbox` | 1 | `index.vue:2312` |
| `UiIconButton` | 1 | `index.vue:1296` |
| `UiButton` | 0 | |
| `UiDate*` / `UiTime*` / `OperatorPeriodPicker` | 0 | |
| `FilterBar`, `MoreBelow`, charts | 0 | |
| Shell | `OfflineBanner`, `OperatorSessionUnavailable`, `OperatorLogin`, `OperatorLock`, `OperatorStationSetup`, `OperatorSonner`, `OperatorPwaRuntime` | `app.vue:39-73` |
| Composables do kit | `useOperatorLock`, `useStationSetupOffer`, `useOperatorWindowTitle`, `useSonner` (alias de `vue-sonner`, `nuxt.config.ts:62`) | `app.vue`, `index.vue` (8 toasts), `usePurchaseDesk.ts` (17 toasts) |

### 1.5 Componentes locais

| Componente | Linhas | Papel | Destino |
|---|---|---|---|
| `PurchaseNav.vue` | 91 | adapta seções (estado) ao rail e à barra | **morre**: `OperatorSuiteShell` já aceita `current` + `@select` (`OperatorSuiteShell.vue:17, 22, 47`) |
| `PurchaseMoreMenu.vue` | 65 | ⋯/⋮ com itens, divisor, perigo, tecla | **morre** em `NuxtDropdownMenu` (frente F6 do laudo: "⋯ = DropdownMenu"); o kit poderia oferecer o mesmo menu para B.I. e Marketing |
| `CodeScannerSheet.vue` | 77 | folha de câmera (EAN, volumes, GS1) com lanterna e progresso | fica local (domínio), sobre `NuxtDrawer`/`NuxtSlideover`; candidata a kit se outro app ler código |
| `ReceiptExceptionFlow.vue` | 520 | conferência por exceção: volumes, validade uma por vez, itens que batem | fica local; precisa trocar 19 `<button>` e 18 tamanhos arbitrários de fonte |
| `ReceiptLineSheet.vue` | 529 | gaveta do item, docada no tablet ou folha, com teclado numérico próprio | fica local; teclado numérico deveria ser o `OperatorNumpad` do kit; folha → `NuxtSlideover` |
| `ReceiptConferencePanel.vue` | 169 | resumo, pendências como gesto, Confirmar/Ressalva/Devolução | fica local, sobre `NuxtCard` + `NuxtProgress` + `NuxtButton` |
| `ReceiptConversion.vue` | 207 | conta da embalagem e cadastro de conversão | fica local, `NuxtForm`/`NuxtFormField` |
| `ReceiptDifference.vue` | 70 | nota × chegou × diferença e motivo | fica local |
| `ReceiptField.vue` | 44 | cartão de campo que pede decisão | **morre** em `NuxtCard`/`NuxtAlert` com slot |

Seções internas de `pages/index.vue` que viram componente (proposta de corte, nesta ordem de risco crescente):

1. `PurchaseHeader` (1138-1355): os 8 slots e a lógica de quem aparece em qual largura.
2. `PurchasePanel` (1397-1543) e `PurchaseBuy` (1546-1627): leitura e atalhos, quase sem estado.
3. `BaseMaterials` (2093-2411), com `MaterialPanel` (2279-2410: revenda e "quando aberto") separado.
4. `BaseSuppliers` (2414-2507), `BaseCosts` (2510-2698: `CostBatchTable`, `QuoteForm`, `CostTable`), `BaseCount` (2701-2831 com o diálogo).
5. `ReceiveStart` (1641-1763), `ReceiveConference` (1766-1906), `ReceiveThumbBar` (1952-2010), `InvoiceCameraDialog` (2833-2866) e `ReceiptVoucherSheet` (2045-2068). O Receber é o núcleo de risco: estado cruzado (`receiptParked`, `keyEntryOpen`, `splitDrawer`, `isWide`, `exceptionFlowOn`, `thumbCount`, `openLineId`) declarado em `index.vue:855-912`.

O script (1-1131) concentra 60 funções de tela; o domínio já mora em `usePurchaseDesk.ts` (1.307 linhas, ~30 `useState`) e `presentation/purchase.ts` (1.324 linhas, puro e testado).

### 1.6 Escapes do cânon

Contagens (script de varredura em `onda0-inventario/escapes.py`): 127 `<button>`, 14 `<input>`, 2 `<select>`, 3 `<textarea>`, 4 `<table>`, 2 `<form>`, 6 `<dl>`, 1 `<kbd>`, 1 `type="file"`, 17 classes `pill-*`, 18 selos `inline-flex h-6 rounded-full` à mão, 47 valores arbitrários, 2 menus `role="menu"` à mão, 0 `:ui=`, 0 temporal nativo, 5 travessões (U+2014).

Os 30 mais relevantes:

| # | Tipo | Onde | Hoje | Componente certo |
|---|---|---|---|---|
| 1 | b | `index.vue:1284-1295` | `<select>` invisível sobre rótulo (Ordenar) | `NuxtSelect` ou `NuxtDropdownMenu` com `NuxtButton` gatilho |
| 2 | b | `index.vue:1182-1200`, `1335-1352`, `1269-1278` | três segmentados à mão (Base desktop, Base celular, Com/Sem NF) | `NuxtTabs` (Base) e `NuxtRadioGroup variant="card"` ou `NuxtTabs` (Com/Sem NF) |
| 3 | b | `PurchaseMoreMenu.vue:31-64` | popover com `role="menu"` e `<button role="menuitem">` | `NuxtDropdownMenu` (com `kbds` para o R) |
| 4 | b | `index.vue:2156-2240` | tabela de insumos com `colgroup` e colunas que somem | `NuxtTable` (colunas com `meta.class`) |
| 5 | b | `index.vue:2557-2603` | tabela em lote com inputs | `NuxtTable` + `NuxtInput`/`NuxtSelect` em célula |
| 6 | b | `index.vue:2676-2694` | custos por fornecedor | `NuxtTable` |
| 7 | b | `index.vue:2713-2767` | contagem | `NuxtTable` + `NuxtInput` |
| 8 | b | `index.vue:2119-2126`, `2199-2206` | `<input>` dentro de `<label>` estilizado (mínimo + unidade) | `NuxtInput` com slot `#trailing` |
| 9 | b | `index.vue:2329, 2379, 2383, 2655` | `<input>` com classes de campo | `NuxtFormField` + `NuxtInput` |
| 10 | b | `index.vue:1725, 1779, 2081` | `<textarea>` com classes | `NuxtTextarea` |
| 11 | b | `index.vue:2371-2374` | `<select>` cru (insumo aberto) | `NuxtSelect` |
| 12 | b | `index.vue:2325-2344`, `2368-2401` | `<form>` à mão | `NuxtForm` + `NuxtFormField` |
| 13 | d | `index.vue:1480, 1489, 1505, 1588, 2131, 2226, 2422, 2737` e `ReceiptLineSheet.vue` | pílula de estado `inline-flex h-6 rounded-full px-2 pill-*` com ponto | `NuxtBadge` (`variant="subtle"`, `leading-icon`) |
| 14 | d | `index.vue:1400-1431` | cartões-atalho `<button rounded-xl border bg-card p-4>` | `NuxtCard` com `NuxtLink`/`NuxtButton` ou `NuxtPageCard` |
| 15 | d | `index.vue:1434-1511` | lista "Precisa de você" com `divide-y` e `<button>` por linha | `NuxtCard` + lista de `NuxtButton variant="ghost" block` ou `NuxtTable` |
| 16 | d | `index.vue:1517-1541`, `1754-1762`, `1959-1975` | botões grandes (Escanear NF) feitos com `rounded-2xl bg-primary` | `NuxtButton size="xl" block` com slot |
| 17 | d | `index.vue:1600-1603`, `2258-2274`, `2387-2399`, `2613-2629`, `2665-2666`, `2777-2783`, `2816-2828` | botões primário/contorno por classe (`bg-primary`, `border border-border`) | `NuxtButton` (`color`, `variant`, `loading`) |
| 18 | d | `index.vue:1358-1394` | faixas de estado e de erro por classe | `NuxtAlert` |
| 19 | d | `index.vue:1641-1673` | aviso de resultado com ícone e ações | `NuxtAlert` com `actions` |
| 20 | d | `index.vue:2292-2299`, `1747-1749` | alertas inline por `toneClasses` | `NuxtAlert` |
| 21 | f | `ReceiptLineSheet.vue:355-371` | teclado numérico próprio | `OperatorNumpad` do kit |
| 22 | f | `index.vue:2833-2866` | câmera em `UiDialog fullscreen` preto com botões redondos à mão | `NuxtModal fullscreen` + `NuxtButton color="neutral" variant="ghost"` |
| 23 | f | `index.vue:2045-2087`, `CodeScannerSheet.vue:37`, `ReceiptLineSheet.vue:518` | `UiSheet` (Ui* do kit) | `NuxtDrawer` (baixo) / `NuxtSlideover` (lado) |
| 24 | f | `index.vue:786-801` | listener de `keydown` manual para `/` ao lado de `onKeyStroke` | `defineShortcuts` do Nuxt UI (ou o mapa de atalhos do kit) |
| 25 | e | `ReceiptExceptionFlow.vue:182-421` | 17 tamanhos de fonte/raio arbitrários (`text-[19px]`, `text-[34px]`, `rounded-[14px]`…) | papéis `op-*` e escala do tema |
| 26 | e | `index.vue:1521, 1656, 1759, 1963` | `text-[22px]`, `text-[19px]`, `text-[20px]` | `op-title`/`op-display` |
| 27 | e | `index.vue:1954, 2248` | `bottom-[calc(4rem+1px+env(safe-area-inset-bottom))]`, `shadow-[...]` | token da altura da barra do kit (motivo existe, falta nome) |
| 28 | e | `index.vue:2281`, `2557`, `2676`, `2713` | `xl:w-[372px]`, `min-w-[36rem]`, `min-w-[40rem]`, `min-w-[48rem]` | `NuxtDashboardPanel`/`NuxtTable` responsivo |
| 29 | f | `index.vue:949-952`, `615-631` | `scrollIntoView` ad hoc e `revealTarget` | `useNextFocus` (regra site-wide do CLAUDE.md) |
| 30 | g | `presentation/purchase.ts:52, 79, 128, 130, 863` | travessão (U+2014) como valor vazio (dinheiro, quantidade, data, diferença zero) | texto ("sem custo", "sem data", "igual") pela regra "Copy sem travessão" |

### 1.7 Testes e travas que mudam

No app:

- `tests/camada-visual-da-suite.test.ts:39-61`: exige `data-suite="v3"` no shell, `<PurchaseNav\n      v-if="canIdentify"\n      place="rail"` literal, `<OperatorSuiteRail`/`<OperatorSectionBar` no `PurchaseNav`, `<OperatorPageHeader` e `<OperatorLiveStatus` na página. **Quebra** se o shell for `OperatorSuiteShell`. O Gestor proíbe `data-suite` e este teste exige (o laudo, Anexo D, chama de "duas travas com verdades opostas").
- `tests/v6-conformidade.test.ts:58-131`: 17 `it`, quase todos `toContain` de string em `index.vue`, `ReceiptLineSheet.vue`, `PurchaseMoreMenu.vue` e no `OperatorPageHeader` do kit (`:60-63`, regex do `v-if="$slots.search"`). Ex.: `:124` exige o texto exato `<PurchaseMoreMenu v-if="view === 'panel' || view === 'buy'" vertical :items="refreshMenuItems"`; `:129` exige `pointer-fine:inline`. **Quebra** em qualquer reescrita.
- `tests/components/ReceiptLineSheet.test.ts:112-122`: procura `[data-slot="sheet-title"]` (anatomia do `UiSheet`). **Quebra** com `NuxtSlideover`.
- `tests/components/ReceiptExceptionFlow.test.ts:65`: acha botão por `wrapper.findAll("button")` + texto. Sobrevive se `NuxtButton` renderizar `<button>` no harness.
- `tests/purchase.test.ts` (74), `recebimento-*` (24), `selos`, `sugestao-por-gtin`, `nf-confere-cadastro-fiscal`, `receiptFocus`: presentation pura, ficam.
- `tests/securityConfig.test.ts`: lê `nuxt.config.ts` (`operatorPermissionsAllow: { camera: "self" }`); fica se o config não mudar.

No kit e no repositório:

- `operator-kit/tests/guardrails.appBar.test.ts:96, 127`: `PurchaseNav.vue` está na lista "migrados" e deve conter `<OperatorSuiteRail` e `<OperatorSectionBar`. Sair do `PurchaseNav` exige mover o arquivo para a regra do piloto (`:108-116`, que exige `<OperatorSuiteShell` no `app.vue`).
- `operator-kit/tests/guardrails.phoneBar.test.ts:111`: exige que a varredura ache bloco de barra de 56 px em `purchase-nuxt/app/pages/index.vue`. Se o `#phone-actions` sair da página, o teste cai.
- `operator-kit/tests/guardrails.pendingAction.test.ts:183-186`: `KNOWN_INERT` lista `addAndOpenReceiptLine` e `toggleScannerTorch`. Só encolhe; renomear a função sem tirar daqui quebra.
- `scripts/check_operator_component_ledger.py`: teto `native_control_occurrences=132` (`docs/reference/operator-component-ledger.json`), só pode cair; **`CANONICAL_STRUCTURE` reprova `NuxtDashboard*`, `NuxtNavigationMenu`, `NuxtPage*`, `NuxtSidebar` fora do kit** (`:34-38, 297-306`). O Compras não pode usar essas estruturas na página; tem que vir por peça do kit (foi o que reprovou o Gestor).
- Ledger declara uma superfície só (`purchase-workspace`, 11 variantes, `pending`).

### 1.8 Mock visual e fixtures

Não há `playwright.config`, `tests/e2e`, `tests/visual` nem `@playwright/test` no `package.json`.

Endpoints do app (todos via BFF do kit `operator-kit/server/api/v1/[...path].ts`):

| Método | Caminho | View Django | Projection |
|---|---|---|---|
| GET | `/api/v1/backstage/purchase/` | `PurchaseBoardView` (`shopman/backstage/api/purchase.py:47`) | `build_purchase` (`shopman/backstage/projections/purchase.py:289`, 1.093 linhas) |
| POST | `.../receipts/scan-invoice/` | `PurchaseScanInvoiceView` `:60` | devolve projeção com `active_receipt` |
| POST | `.../receipts/confirm/`, `.../receipts/reject/`, `.../receipts/volumes/` | `:77`, `:111`, `:94` | idem |
| POST | `.../costs/`, `.../costs/batch/` | `:128`, `:145` | idem |
| POST | `.../materials/min-stock/`, `.../materials/<sku>/opening/`, `.../materials/<sku>/sale/` | `:168`, `:191`, `:210` | idem |
| POST | `.../conversions/` | `:233` | idem + `conversionId` |
| GET / POST | `.../count/`, `.../count/confirm/` | `:271`, `:284` | `projections/purchase_count.py` (84 linhas) |
| POST | `.../requests/<sku>/send/` (`approve/` sem uso) | `:318`, `:301` | idem |

Do kit (qualquer app): `operator/session/`, `operator/lock|unlock|eligible|station|pin/change|badge/lost|login`, `notifications/`, `notifications/push/`, `sign-ins/`, `search/`, `/health/capacity`.

**Schema TS: não existe.** `app/types/purchase.ts` (723 linhas) é escrito à mão. Existem `export_orders_schema`, `export_kds_schema`, `export_production_schema`, `export_recipe_book_schema`, `export_bi_schema`, `export_pos_schema`; não há `export_purchase_schema`. O módulo comum `shopman.backstage.contracts.render_contract_module` (usado pelo B.I.) serviria.

Como os modelos sobem:

- **Gestor visual** (`orders-nuxt/playwright.visual.config.ts`): `defineOperatorVisualConfig` do kit; dois `webServer`: `node tests/visual/mockBackend.mjs` (porta 38793) e `nuxt dev` client-only (`ORDERS_VISUAL_CLIENT_ONLY=1`) apontando `NUXT_DJANGO_BASE_URL` para o mock. O mock (185 linhas) lê fixtures gravadas do seed (`tests/visual/fixtures/*.json`, 1,6 MB, incluindo `recorded-django.json` casado por caminho+query), troca cenário por `GET /__visual/scenario?set=normal|empty|dense|error|gallery`, responde `operator/session/` fixo, `204` para SSE e `{}` no resto. Não há script de gravação no repositório: as fixtures foram capturadas à mão.
- **Gestor e2e** (`tests/e2e/mockBackend.mjs`, 147 linhas) e **Hub e2e** (`hub-nuxt/tests/e2e/mockBackend.mjs`, 88 linhas): projeção literal no próprio arquivo; o Hub sobe `nuxt build && node .output/server/index.mjs` contra o mock na porta 8797.
- O runner do ledger (`scripts/run_operator_visual.py`) só executa apps com `playwright.visual.config.ts` (hoje: orders, pos, marketing, kitchensink, operator-kit).

Trabalho para o Compras: **alto**. A projeção é uma só, mas o app é de escrita: 13 POSTs que devolvem a projeção inteira, e o estado do Receber (NF lida, linhas, volumes, validade) vem do servidor (`active_receipt`). O mock precisa de pelo menos 6 cenários com estado (base, comprar vazio, NF lida com exceção, NF com tudo batendo, sem NF, contagem proibida), de uma resposta canônica de scan-invoice (uma chave de 44 dígitos do seed) e de transições nos POSTs. Câmera e `@zxing` não se exercitam em headless sem `--use-fake-device-for-media-stream` e vídeo Y4M; o caminho "digitar chave" cobre o resto. Estimativa: 2 a 3 dias, mais 1 dia para um `export_purchase_schema` que tire a deriva dos tipos.

### 1.9 Riscos específicos

1. **Página única de 2.868 linhas com estado de tela cruzado**: quebrar em componentes é pré-requisito, e é onde mora a regressão. O Receber decide layout por quatro media queries (`isPhone`, `splitQuery`, `isWideQuery`, `receiveMounted`) e sete refs.
2. **Seções por estado, não por rota**: o shell canônico do Gestor navega por rota; `OperatorSuiteShell` aceita `select`, mas `NuxtNavigationMenu`/voltar do navegador não. Deep link `?view=` precisa continuar (atalho do PWA).
3. **`#below` e `#phone-actions`**: o laudo (P0-2) já viu o `#below` sumir (corrigido em #1521, presente aqui em `OperatorPageHeader.vue:188`). O `#phone-actions` agora renderiza no `#right` sem `md:hidden` (`OperatorPageHeader.vue:151`): a página contorna com `v-if="!isPhone"` no `#actions`, mas no desktop o `⋮` vertical do `#phone-actions` (`index.vue:1239-1240`) aparece ao lado do `⋯` do `#actions` (`:1297`). Conferir em tela.
4. **`OperatorLiveStatus` binário** (laudo P0-5): o Compras passa `calm` enquanto lê (`index.vue:765`) e hoje sai verde "On".
5. **Toque**: `UiFilterChip` virou `NuxtButton` (sem `min-h-control`), alvo cai de 48 para 44 px (laudo Anexo D, purchase 31 ocorrências de `h-control`). O Receber é usado na doca, de luva.
6. **Câmera e PWA**: a exceção de `Permissions-Policy` (`camera: "self"`) e o `getUserMedia` dentro de `UiDialog fullscreen` precisam sobreviver à troca para `NuxtModal` (foco preso, Esc, `stopInvoiceScanner` no fechar).
7. **`UiSelect` dentro da gaveta tem véu próprio e engole o Esc** (`ReceiptLineSheet.vue:37-40`): trocar a gaveta por `NuxtSlideover` sem refazer esse acordo fecha a gaveta inteira no Esc da lista.
8. **Sem confirmação** em "Remover item" (`index.vue:1876`) e "Devolver só este item" (POST `receipts/reject/`, `ReceiptExceptionFlow.vue:508`): migrar sem perceber pode manter ou piorar.
9. Sem mock nem e2e: hoje nada prova o Receber em tela; a migração seria a primeira vez.

## 2. B.I. (bi-nuxt)

### 2.1 Telas

Shell (`app.vue:22-53`): igual ao do Compras (`data-suite="v3"`, `BiNav` rail + barra, sem `OperatorSuiteShell`). Seções com rota e a janela de análise na query (`presentation/biSections.ts:6-22`, `composables/useBiSections.ts`). Cada página: `<div>` + `OperatorPageHeader` + `<main class="px-4 pt-3 pb-4">` + `BiSwipeHint`. SSR ligado.

| Rota | Arquivo | O que mostra |
|---|---|---|
| `/` | `pages/index.vue` (467) | "Sobrou ou faltou ontem?": dia no cabeçalho (`?day=`, `?compare=`), resposta + 3 números, tabela por produto com veredito e detalhe (lotes, vendas por hora, depois que acabou), "+N produtos"; embaixo "Como foram os lotes no período?" com a janela própria, 4 números, 2 séries e 2 listas de tempo de forno |
| `/sales` | `pages/sales.vue` (333) | "Quanto vendemos?": comparar com, chips de canal, números (celular e desktop separados), faturamento por dia, por hora, por dia da semana, por canal, top produtos; CSV por quadro |
| `/cash` | `pages/cash.vue` (278) | "O caixa fechou certo?": 4 números, quebra por dia (divergente), contas na casa, por operador, anomalias da gaveta, gaveta por operador (9 colunas), meios de pagamento, gaveta por hora |
| `/customers` | `pages/customers.vue` (81) | "Os clientes estão voltando?": 4 números, segmentos, novos por semana |
| `/profiles` | `pages/profiles.vue` (398) | "Quem compra no balcão?": filtros dia/faixa, 4 números, 3 leituras em tabela, estimativa ponderada, faixa honesta, conciliação, matriz faixa × perfil, categoria, bebida, receita por assento-hora |
| `/explore` | `pages/explore.vue` (290) | "O que você quer cruzar?": construtor (cenário, métrica, dimensão, cruzamento, ⋯ salvar/favoritar/apagar) e resultado (série, ranking ou tabela) |
| `/forecast` | `pages/forecast.vue` (325) | "O que esperar?": período planejado (`OperatorPeriodPicker`), um dia (ocasião, faixa, ramos do tempo, troco) ou período (totais, dia a dia) |
| `/scenarios` | `pages/scenarios.vue` (118) | "Que cenários a IA propõe?": foco + Gerar, rodadas em acordeão |

### 2.2 Gestos

Endpoints: `useBiReport.ts:14-19` (`/api/v1/backstage/bi/<kind>/`), `useBiOverShort.ts:19`, `useBiExplore.ts:21`, `useBiProfiles.ts:19`, `useBiForecast.ts:37`, `useBiChange.ts:14`, `useBiViews.ts:11-45`, `useBiScenarios.ts:7-17`. Leitura calma, sem poll (`useBiReport.ts:1-2`).

| Gesto | Onde | Efeito / endpoint |
|---|---|---|
| Trocar de seção (rail, barra, Mais) | `BiNav.vue:23-37` | rota com a janela na query |
| Deslizar para o lado no celular; "Deslize para X" | `BiSwipeHint.vue:32-55, 73-81` | `router.push` |
| Período de análise (popover: chips, ‹ ›, personalizado) | `BiWindowPicker.vue:11-20` (`OperatorPeriodPicker`), em `sales.vue:133`, `cash.vue:94`, `customers.vue:43`, `profiles.vue:91`, `explore.vue:123`, `index.vue:411` | `useBiWindow` (`router.replace` `:46`) |
| Período no celular (chip "28D ⌄": últimos, período atual, De/Até com `UiDateField`, "Ver este período") | `BiPeriodChip.vue:46-98` | `setPreset`, `applyCustom` |
| Período planejado (Projeção) | `forecast.vue:69` (`OperatorPeriodPicker`) | `target`/`horizon` |
| Dia da leitura ‹ / calendário / › | `BiDayStepper.vue:29-65` (`UiDateField` com `#trigger` `:40-54`) | `setDay` → `?day=` |
| ⋯ da página: Copiar link desta leitura (+ "Como é calculado" no `/`) | `BiPageMenu.vue:25-44`; `index.vue:246-251` | clipboard |
| ⋮ do quadro: Exportar CSV | `BiChartMenu.vue:43-55`, usado em `sales.vue:254, 267, 273, 282, 302` | download local |
| Compartilhar (celular) | `BiShareButton.vue:40-50` em todas as páginas | Web Share ou clipboard |
| Levar ao plano do próximo X (desktop e celular) | `index.vue:252-261, 346-355`; ação `:119-137` | POST `/api/v1/backstage/bi/over-short/carry/`; toast com "Abrir o plano" |
| Comparar com (`<select>` invisível sobre rótulo) | `index.vue:267-286`, `sales.vue:141-159` | `?compare=` |
| Chips de veredito (Todos, Faltou, Sobrou, Na medida) | `index.vue:288-302` | filtro local |
| Coleção (`<select>` invisível) | `index.vue:305-316` | filtro local |
| Busca de produto ou SKU | `index.vue:233-235` | filtro local |
| Ver lotes e vendas (abre linha) | `OverShortRow.vue:70-81` | `openSku` |
| Lote → Fechamento da Produção; pedidos do dia → Gestor; "nos N dias" e dia do histórico | `OverShortDetail.vue:61-75, 142-149, 150-157, 161-167` | links entre apps (`useOperatorAppLink`) e `?day=` |
| "+N produtos" | `index.vue:391-400` | `showAll` |
| Tentar de novo | `BiPageState.vue:15-22` | `refresh()` |
| Chips de canal | `sales.vue:161-175` | `?channel=` |
| Maior canal (celular) | `sales.vue:207-216` | `scrollIntoView` ad hoc (`:121-123`) |
| Dia da semana / faixa de hora (`UiNativeSelect`) | `profiles.vue:101-118` | GET consumption-profiles com filtro |
| Leitura da matriz (`UiNativeSelect`) | `profiles.vue:279-281` | local |
| Cenário, Métrica, Dimensão, Cruzamento (4 `UiNativeSelect`) | `explore.vue:136-185` | GET explore |
| ⋯ do cenário (overlay à mão): nome + Salvar (Enter), Favoritar, Apagar (sem confirmação) | `explore.vue:188-241` | POST `bi/views/`, PATCH e DELETE `bi/views/<id>/` |
| Foco (`UiNativeSelect`) + Gerar cenários | `scenarios.vue:49-60` | POST `bi/scenarios/` |
| Abrir/Fechar rodada | `scenarios.vue:73-91` | local |

### 2.3 Atalhos e SSE

- `[` e `]`: dia anterior/seguinte; `/`: busca (`index.vue:146-158`, `onKeyStroke`).
- Do kit: `Alt+1..8` nas seções, `?` ajuda, `/` na busca.
- Gesto de deslizar no celular (`BiSwipeHint.vue`).
- **Sem SSE e sem poll** no app; só o poll de avisos e capacidade do kit.

### 2.4 Peças do operator-kit usadas

| Peça | Usos | Onde |
|---|---|---|
| `OperatorPageHeader` | 8 | uma por página; slots `#status` (7), `#search` (1, `index.vue:233`), `#actions` (8), `#phone-actions` (8), `#filters` (3: `index.vue:266`, `sales.vue:140`, `profiles.vue:98`); `#below` não usado |
| `OperatorLiveStatus` | 1 componente, 7 telas | `BiLiveStatus.vue:25-31` (tons `off`/`live`), em `sales/cash/customers/profiles/explore/forecast/scenarios`; o `/` não tem |
| `OperatorPeriodPicker` | **2** | `BiWindowPicker.vue:11` (com `custom`, usado em 6 telas), `forecast.vue:69` |
| `UiDateField` | **3** | `BiPeriodChip.vue:89, 92`, `BiDayStepper.vue:40` |
| `UiTime*`, `UiDateRangeField`, `UiDateTimeField` | 0 | |
| `UiNativeSelect` | 8 | `explore.vue:136, 157, 166, 177`, `profiles.vue:101, 111, 279`, `scenarios.vue:49` |
| `UiFilterChip` | 4 | `index.vue:288, 292`, `sales.vue:161, 165` |
| `UiButton` | 3 | `index.vue:252, 346`, `BiPeriodChip.vue:95` |
| `UiIconButton` | 2 | `BiPageMenu.vue:27`, `BiChartMenu.vue:45` |
| `UiPopover` | 3 | `BiPeriodChip.vue:46`, `BiPageMenu.vue:25`, `BiChartMenu.vue:43` (dois são menus de ação feitos com popover) |
| `OperatorSuiteSearch` | 1 | `index.vue:234` |
| `OperatorSuiteRail` / `OperatorSectionBar` | 1 + 1 | `BiNav.vue:23, 31` |
| `MoreBelow` | 1 | `index.vue:464` (as outras 7 páginas não têm) |
| `FilterBar` | 0 | |
| Charts | **nenhum do kit**: 3 locais em CSS (`components/chart/BarSeries.vue` 119, `HBarList.vue` 31, `DivergingBars.vue` 67), 17 usos. O kit tem `OperatorKitchenSinkChart.client.vue` sobre `@unovis/vue` (dependência só do kit, fixture de demonstração) |
| Shell | os mesmos 7 do Compras | `app.vue:25-52` |
| Composables do kit | `useOperatorLock`, `useStationSetupOffer`, `useOperatorWindowTitle`, `usePendingAction`, `useOperatorAppLink`, `httpErrorMessage`, `useSonner` | |

### 2.5 Componentes locais

| Componente | Linhas | Papel | Destino |
|---|---|---|---|
| `BiNav` | 38 | seções ao rail e à barra | **morre** em `OperatorSuiteShell` (seções com rota, como o Gestor) |
| `BiWindowPicker` | 21 | `OperatorPeriodPicker` com a janela da URL | fica (fino) |
| `BiPeriodChip` | 99 | período no celular, popover com chips e De/Até | **morre**: é o mesmo `OperatorPeriodPicker` com outro gatilho; o kit ganha variante "chip" (e acaba o "dois seletores no desktop", ver 2.9) |
| `BiDayStepper` | 68 | ‹ dia › com calendário | sobe ao kit como `OperatorDayStepper` (o Gestor e a Produção têm "dia da leitura" parecido) ou vira `NuxtFieldGroup` + `NuxtButton` + `UiDateField` |
| `BiPageMenu` | 45 | ⋯ copiar link + itens da tela | **morre** em `NuxtDropdownMenu` |
| `BiChartMenu` | 56 | ⋮ exportar CSV | **morre** em `NuxtDropdownMenu`; o `exportCsv` sobe a util do kit |
| `BiShareButton` | 51 | Web Share ou copiar | sobe ao kit (o Compras faz o mesmo em `index.vue:1034-1056`) |
| `BiLiveStatus` | 32 | carimbo da última leitura | fica; depende da decisão F3 do laudo |
| `BiSwipeHint` | 83 | deslizar entre seções no celular | sobe ao kit se o `OperatorSectionBar` quiser o gesto para todos; senão fica |
| `BiPageState` | 24 | carregando / erro + Tentar de novo | **morre** em `NuxtSkeleton` + `NuxtAlert` com `actions` (ou `NuxtEmpty`) |
| `BiSection` | 23 | cartão com título, legenda, aside | **morre** em `NuxtCard` (`#header`) |
| `BiAnswer` | 13 | "A resposta" | **morre** em `NuxtCard` |
| `StatTile` | 66 | número, unidade, delta em pílula, dica | sobe ao kit (Hub, Marketing e Gestor têm números parecidos) sobre `NuxtCard` + `NuxtBadge` |
| `OverShortRow` | 87 | linha em grade com veredito e abrir | fica (domínio); veredito → `NuxtBadge`; abrir → `NuxtButton` |
| `OverShortDetail` | 172 | lotes, vendas por hora, depois que acabou | fica; links → `NuxtLink`/`NuxtButton :to` |
| `OverShortBar` | 28 | barra fez × vendeu × típico | fica |
| `chart/BarSeries`, `HBarList`, `DivergingBars` | 119, 31, 67 | gráficos em CSS | **decisão**: ficam (são leves, testados, acessíveis) ou passam a `@unovis/vue` via peça do kit. Não é Nuxt UI: Nuxt UI não tem chart |

### 2.6 Escapes do cânon

Contagens: 21 `<button>`, 3 `<select>`, 1 `<input>`, 8 `<table>`, 1 `<form>`, 2 `<a>` crus, 5 `role="menu"` à mão, 1 overlay à mão, 3 `pill-*`, 12 valores arbitrários, 0 `:ui=`, 0 temporal nativo, 0 travessão.

Os 30 mais relevantes:

| # | Tipo | Onde | Hoje | Componente certo |
|---|---|---|---|---|
| 1 | b | `explore.vue:188-241` | overlay à mão (`absolute right-0 top-full`), sem Esc nem clique fora | `NuxtPopover` ou `NuxtDropdownMenu` + `NuxtInput` |
| 2 | b | `explore.vue:204-211` | `<input>` cru | `NuxtInput` |
| 3 | b | `explore.vue:212-219, 223-238` | Salvar/Favoritar/Apagar `<button>` | `NuxtButton` / itens de `NuxtDropdownMenu`; Apagar com confirmação |
| 4 | b | `index.vue:267-286` | `<select>` invisível sobre rótulo (Comparar com) | `NuxtSelect` com slot `#default` |
| 5 | b | `index.vue:305-316` | idem (Coleção) | `NuxtSelect` |
| 6 | b | `sales.vue:141-159` | idem (Comparar com) | `NuxtSelect` |
| 7 | b | `BiPageMenu.vue:25-44` | popover + `role="menu"` | `NuxtDropdownMenu` |
| 8 | b | `BiChartMenu.vue:43-55` | idem | `NuxtDropdownMenu` |
| 9 | b | `cash.vue:171-202` | tabela por operador | `NuxtTable` |
| 10 | b | `cash.vue:230-257` | tabela de 9 colunas, `min-w-160` | `NuxtTable` |
| 11 | b | `sales.vue:304-325` | top produtos com barra | `NuxtTable` (célula com `NuxtProgress`) |
| 12 | b | `profiles.vue:163-193, 285-303, 340-362, 374-391` | 4 tabelas | `NuxtTable` |
| 13 | b | `explore.vue:262-283` | tabela de cruzamento | `NuxtTable` |
| 14 | b | `scenarios.vue:67-112` | acordeão à mão com `aria-expanded` | `NuxtAccordion` ou `NuxtCollapsible` |
| 15 | b | `scenarios.vue:52-60` | botão primário por classe | `NuxtButton :loading` |
| 16 | b | `BiPageState.vue:15-22` | botão de contorno por classe | `NuxtButton` em `NuxtAlert` |
| 17 | b | `BiShareButton.vue:40-50` | `<button>` ícone | `NuxtButton icon square` |
| 18 | b | `BiDayStepper.vue:29-65` | grupo de três segmentos à mão | `NuxtFieldGroup` + `NuxtButton` |
| 19 | b | `BiPeriodChip.vue:48-56, 67-84` | gatilho e 8 chips `<button>` com `CHIP` | `NuxtButton` (`variant` por estado) ou `NuxtRadioGroup variant="card"` |
| 20 | b | `OverShortRow.vue:70-81` | abrir linha | `NuxtButton` + `NuxtCollapsible` |
| 21 | b | `OverShortDetail.vue:61-75, 142-149` | `<a>` cru entre apps | `NuxtLink` / `NuxtButton :to target` |
| 22 | b | `OverShortDetail.vue:150-157`, `index.vue:391-400`, `sales.vue:207-216` | botões-link por classe | `NuxtButton variant="link"`/`ghost` |
| 23 | d | `OverShortRow.vue:46-48`, `StatTile.vue:54-61` | pílulas por classe (`PILL`, `h-5 rounded-full`) | `NuxtBadge` |
| 24 | d | `BiSection.vue`, `BiAnswer.vue`, `StatTile.vue:45`, `forecast.vue:88, 107, 160, 190, 223, 310`, `profiles.vue:154, 198, 235, 253, 269, 308, 323, 367`, `explore.vue:133, 247` | `rounded-lg border bg-card px-4 py-3` repetido 20+ vezes | `NuxtCard` |
| 25 | d | `sales.vue:293-295` | barra de parte por canal | `NuxtProgress` |
| 26 | f | `components/chart/*` | gráficos próprios | peça de gráfico do kit (decisão) |
| 27 | f | `BiPeriodChip.vue` inteiro | segundo seletor de período paralelo ao `OperatorPeriodPicker` | variante do `OperatorPeriodPicker` |
| 28 | f | `sales.vue:121-123` | `scrollIntoView` ad hoc | `useNextFocus` |
| 29 | e | `index.vue:99` | grade de 7 colunas em px (`104px`, `minmax(200px,230px)`, `92px`, `118px`, `168px`) | `NuxtTable` com colunas ou tokens nomeados |
| 30 | e | `BiPeriodChip.vue:62`, `OverShortDetail.vue:83`, `OverShortRow.vue:33`, `OverShortBar.vue:14`, `cash.vue:106`, `customers.vue:55`, `sales.vue:220`, `index.vue:338` | `w-[min(22rem,calc(100vw-1rem))]`, `h-[86px]`, `min-h-[50px]`, `max-w-[200px]`, grades `xl:grid-cols-[1.4fr_1fr_...]` | `NuxtPopover :content`/`:ui` do tema; `NuxtPageGrid`-like do kit para a fileira de números |

### 2.7 Testes e travas que mudam

No app:

- `tests/components/charts.test.ts:15-28`: procura `.rounded-t-sm` e `[data-chart-peak]` nos gráficos locais. **Quebra** só se os gráficos mudarem.
- `tests/guardrails.vocabulary.test.ts` (2) e `tests/lotVocabulary.test.ts:50-52` (lê `pages/index.vue`, exige "Aproveitamento do período"): ficam se a copy ficar.
- `tests/presentation.test.ts` (46), `tests/overShort.test.ts` (28): puros, ficam.
- `tests/securityConfig.test.ts`: lê `nuxt.config.ts`.
- **Nenhum teste monta página ou o shell**: o B.I. não tem trava de template como `v6-conformidade` do Compras.

No kit e no repositório:

- `operator-kit/tests/guardrails.appBar.test.ts:93, 126`: `BiNav.vue` na lista "migrados" (mesma situação do Compras).
- `operator-kit/tests/guardrails.test.ts:163`: `bi-nuxt` está em `TYPOGRAPHY_ENFORCED` (nada de `text-2xl`/`text-[..]` avulso); hoje passa, e a migração tem de manter (o Compras **não** está na lista).
- `operator-kit/tests/guardrails.pendingAction.test.ts:162`: `KNOWN_INERT` com `explore.vue: removeLoaded`.
- `shopman/backstage/tests/test_bi_schema_export.py`: deriva do `biContract.ts`; só muda se a projeção mudar.
- Ledger: teto `native_control_occurrences=24`; 8 superfícies `pending` com variantes **genéricas que não batem com as telas** (ex.: `/` declarado como `kpis/alerts/sources`, `/profiles` como `list/profile/orders/preferences`): o runner visual (`run_operator_visual.py --scenario`) não vai achar cenários reais sem corrigir o ledger.

### 2.8 Mock visual e fixtures

Não há Playwright nem mock.

| Método | Caminho | View (`shopman/backstage/api/bi.py`) | Projection | No `biContract.ts`? |
|---|---|---|---|---|
| GET | `bi/production/` | `BIProductionView` | `bi_production.py` (349) | sim |
| GET | `bi/over-short/` | `BIOverShortView` | `bi_over_short.py` (806) | sim |
| POST | `bi/over-short/carry/` | `BIOverShortCarryView` | escreve no plano | n/a |
| GET | `bi/sales/` | `BISalesView` | `bi_sales.py` (366) | sim |
| GET | `bi/cash/` | `BICashView` | `bi_cash.py` (517) | sim |
| GET | `bi/customers/` | `BICustomersView` | `bi_customers.py` (106) | sim |
| GET | `bi/explore/` | `BIExploreView` | `bi_explore.py` (1.226) | sim |
| GET | `bi/consumption-profiles/` | `BIConsumptionProfilesView` | `bi_profiles.py` (576) | sim |
| GET | `bi/forecast/` | `BIForecastView` | `bi_forecast.py` (604) | sim |
| GET | `bi/change/` | `BIChangeView` | `bi_change.py` (395) | sim |
| GET/POST, PATCH/DELETE | `bi/views/`, `bi/views/<pk>/` | `BIViewListView`, `BIViewDetailView` | modelo de cenário salvo | não (tipo local `SavedView`) |
| GET/POST | `bi/scenarios/` | `BIScenariosView` | `bi_scenarios.py` (85) | sim |

Trabalho para o B.I.: **baixo a médio**. São leituras puras com a janela na query; o mock pode casar por caminho e ignorar a query (como o `recordedFor` do Gestor), com 1 fixture por endpoint gravada do seed (11 GET), mais `operator/session/` e `{}` no resto. Cenários: normal, vazio (sem lote fechado, sem venda), erro (500), e "dia com ocasião" na Projeção. Os POSTs são poucos e sem estado relevante para retrato (carry devolve `{plan_day, carried}`; views e scenarios podem ecoar). Os tipos já vêm do Django, então a fixture tem contrato. Estimativa: 1 dia, com o molde do Gestor copiado (`playwright.visual.config.ts` + `mockBackend.mjs` + `fixtures/`). Atenção ao SSR: o Gestor roda o visual em client-only (`ORDERS_VISUAL_CLIENT_ONLY`); o B.I. precisa decidir o mesmo ou provar o SSR (P1-3 do laudo).

### 2.9 Riscos específicos

1. **Dois seletores de período no desktop** (laudo Anexo D): `#phone-actions` já não é `md:hidden`, e cada página põe `BiWindowPicker` em `#actions` e `BiPeriodChip` em `#phone-actions` (`cash.vue:93-100` e as outras 5). As páginas mitigam com `class="max-md:hidden"` no `BiWindowPicker`, mas o `BiPeriodChip` não tem `md:hidden`: no desktop aparecem os dois.
2. **`OperatorPeriodPicker` já está regredido nesta branch** (laudo P1-1): `operator-kit/app/components/OperatorPeriodPicker.vue:248, 259, 294` usam `type="date"` nativo (conferido). O "Personalizado" do `BiWindowPicker` (6 telas) e o período da Projeção aparecem hoje como `mm/dd/yyyy`, no formato do dispositivo. O `BiPeriodChip` do celular não sofre, porque usa `UiDateField`. O B.I. é o maior consumidor e é onde a frente F2 se prova; a contagem "0 temporal nativo" do item 2.6 é só do código do app, não do kit que ele herda.
3. **SSR + media query**: `isPhone` no título (`index.vue:64-68`, `sales.vue:34`) e no `BiSwipeHint` gera mismatch de hidratação (P1-3).
4. **Gráficos**: trocar por `@unovis` mudaria leitura, acessibilidade (`role="img"` + rótulo) e os testes; não há componente de gráfico no Nuxt UI. Melhor deixar fora da migração.
5. **Apagar cenário salvo sem confirmação** (`explore.vue:233-238`).
6. **Ledger com variantes fictícias**: a evidência visual não fecha sem reescrever as 8 superfícies.
7. **`OperatorLiveStatus` binário** (P0-5): "Atualizado" vira "On".

## 3. O que vale para os dois

- Nenhum dos dois usa `NuxtButton`, `NuxtCard`, `NuxtTable`, `NuxtBadge`, `NuxtAlert` diretamente; tudo é `Ui*` do kit ou HTML com classes. Migrar é reescrever o template, não trocar prefixo.
- Os dois têm `data-suite="v3"` no shell, que o Gestor eliminou; o kit ainda lê o atributo em primitivos (comentário `app.vue:20-21` do B.I.). Tirar o atributo pode mudar o visual de peças do kit nos dois.
- Os dois montam `PurchaseNav`/`BiNav` em vez de `OperatorSuiteShell`. O Gestor provou o shell (`orders-nuxt/app/app.vue`); a trava `guardrails.appBar` tem as duas regras (lista "migrados" e regra do piloto) e o app sai de uma para a outra.
- `useSonner` (vue-sonner) + `OperatorSonner`: a frente F6 do laudo prevê `useToast` no kit. O Compras tem 25 chamadas, o B.I. 13 (incluindo ação "Abrir o plano").
- O ledger proíbe estrutura canônica (`NuxtDashboard*`, `NuxtNavigationMenu`, `NuxtPage*`) fora do kit: layout tem de vir por peça do kit.

## 4. Recomendação: o B.I. é o melhor piloto

1. **Menor risco funcional.** O B.I. é leitura: 1 POST de negócio (levar ao plano) e o CRUD de cenários salvos. O Compras escreve estoque, custo, preço de venda e contagem (13 POSTs), e o Receber tem estado de servidor, câmera e quatro layouts por largura. Errar um gesto no B.I. mostra um número no lugar errado; errar no Compras dá entrada errada no estoque.
2. **Mais prova de método por esforço.** Oito rotas pequenas (81 a 467 linhas) permitem migrar uma tela por PR, cada uma com retrato antes e depois. O Compras exige primeiro desmontar uma página de 2.868 linhas, e essa desmontagem já é uma frente de regressão sem relação com o Nuxt UI.
3. **Mock barato e com contrato.** O B.I. tem schema TS exportado do Django e leituras puras: o mock no molde do Gestor sai em cerca de um dia. O Compras precisa de um mock com estado e transição e, idealmente, de um `export_purchase_schema` que ainda não existe.
4. **Prova as frentes abertas do kit que afetam todos.** O B.I. é o maior consumidor de período (`OperatorPeriodPicker` em 6 telas, `UiDateField` 3 vezes, além do `BiPeriodChip` paralelo): é onde F2 (data, hora, período) e o defeito de `#phone-actions` (dois seletores no desktop) se provam em tela. Também prova F3 (`OperatorLiveStatus`), F6 (⋯ como `NuxtDropdownMenu`, 2 menus no B.I. contra 1 no Compras), `NuxtTable` (8 tabelas só de leitura) e `NuxtCard` (20+ cartões repetidos).
5. **Mais reuso para o kit.** Sobem do B.I.: `StatTile`, `BiShareButton`, o menu de exportar CSV, possivelmente `BiDayStepper` e o gesto de deslizar. Do Compras sobe pouco além do `PurchaseMoreMenu` (que o mesmo `NuxtDropdownMenu` resolve) e do teclado numérico (que já existe no kit como `OperatorNumpad`).
6. **Menos travas a reescrever.** O B.I. não tem teste de template de página; o Compras tem `v6-conformidade` (17 `it` de string) e `camada-visual-da-suite`, que quebram em qualquer reescrita.

Ressalvas para o piloto B.I.: deixar os 3 gráficos fora (não há equivalente no Nuxt UI); decidir SSR (client-only no visual, como o Gestor, ou corrigir a hidratação no shell, frente F5); reescrever as variantes do B.I. no ledger antes de gravar retrato; colocar `@playwright/test` na mesma versão dos outros apps (`check_surface_versions.py`).

O Compras fica para depois do B.I., em duas etapas: (a) quebrar `index.vue` nos componentes do item 1.5 sem mudar markup, com mock e retratos gravados antes; (b) migrar componente a componente, começando pela Base (tabelas e formulários, onde o ganho é maior) e deixando o Receber por último.
