# WP-PDV-SEM-CONEXAO: o balcão não para

**Decisão do dono (10/10/2026):** no lugar de um servidor local, três camadas: internet
redundante, nobreak (hardware, com o dono) e um PDV (`surfaces/pos-nuxt`) que vende sem
conexão e sincroniza na volta. Quedas são comuns em dia chuvoso de movimento. Este documento
é o desenho da terceira camada. A implementação do que não depende de decisão está na PR da
fila (ver §8).

> **ADR-013 §1** ("POS não faz commit offline") fica superado por esta decisão. Os
> pré-requisitos que o próprio ADR exigia para o dia em que houvesse venda offline (fila com
> `client_request_id`, reenvio idempotente, fechamento de caixa barrado com fila pendente,
> reconciliação auditável, testes de queda de rede e de reload) são exatamente o que §3 a §6
> descrevem.

## 1. Inventário: o que a venda pede ao servidor hoje

| Etapa | Endpoint / peça | Sem rede |
|---|---|---|
| Catálogo, preços, disponibilidade | `GET /api/v1/backstage/pos/` (`build_pos`, `usePosTerminal`) | A última leitura fica na memória da aba. Disponibilidade congela no último retrato. |
| Abrir comanda | `POST pos/tabs/<ref>/open/` (cria `Session`) | **Não abre no servidor.** A comanda livre abre só na tela (§3.4). |
| Salvar comanda (autosave) | `POST pos/tabs/save/` com `expected_revision` (`@tab_command`) | Falha; a tela marca "não salvo". O fechamento leva os itens inteiros (§3.3). |
| Total da venda | `POST pos/sale/review/`; com comanda, `tabs/save/?review=1` (#1627) | Total montado na tela pela última leitura (§4). |
| Fechar | `POST pos/sale/close/` (`close_sale`, `require_expected_total=True`) | Vai para a fila local (§3). |
| Enviar à cozinha | `POST pos/tabs/fire/` (ledger por `line_id`) | Não envia. Cozinha avisada de voz. |
| Pagamento | `settle_terminal_tenders` (dinheiro, crédito/débito atestados, `external`); `initiate` para Pix/link/cartão online | Dinheiro e maquininha seguem. **Pix, link e cartão online param.** |
| NFC-e | `fiscal.emit_on_payment` → Directive `FISCAL_EMIT_NFCE` → Focus NFe (nuvem) | Não emite. Ver §5. |
| Impressão | bytes ESC/POS do servidor (`receipt-escpos`) → agente local `127.0.0.1:47811/print`; plano B `window.print()` do recibo montado na tela | Só o plano B (`PosReceipt.vue`), pela impressão do navegador. |
| Gaveta | no Balcão, `useDrawerOpening.afterCashSale` chuta primeiro no agente local e registra depois (fire-and-forget); no tablet, relay pelo servidor | No Balcão abre. No tablet não (o relay é do servidor): abre na chave. |
| Caixa/turno | `pos/cash/open|close|movement/` (idempotentes por `client_request_id`) | Abrir, fechar e movimentar exigem rede. A venda guardada entra no turno aberto quando sobe. |
| Cliente | `pos/customer/lookup/`, `search/`, `resolve/` | Só o que já estava na tela. CPF na nota viaja no corpo e o servidor usa no envio. |
| iFood | webhooks/polling no servidor | Fora do PDV. Para durante a queda (é do servidor e da internet). |

**O que já existia no servidor e sustenta o desenho** (não foi preciso tocar no Core):

- `close_sale` é idempotente por `client_request_id`, com trava no banco
  (`_claim_sale_request`, `IdempotencyKey` escopo `pos_sale:<canal>`). O replay devolve o mesmo
  pedido; a projeção já publicava `idempotent_replay.safe_for_offline_queue: True` e
  `cash_management.blocks_close_when_offline_queue_pending: True`.
- `_ensure_expected_total` confere o total da tela pela mesma conta da revisão
  (`_payload_total_q`: preço × quantidade enviado, linha pesada pelo catálogo, desconto, taxa).
  Na venda sem desconto e sem taxa a conta é a mesma que a tela faz sozinha.
- O replay de uma chave que já virou pedido não passa pelo total: preço que mudou depois não
  transforma venda feita em recusa.

## 2. O que funciona sem rede e o que não

**Funciona:** comanda livre aberta na tela e a comanda já aberta neste dispositivo; dinheiro;
maquininha com chip e 4G próprios, registrada como crédito/débito (o operador atesta, como hoje);
gaveta do Balcão pelo agente; recibo pela impressão do navegador; CPF na nota (a nota sai no envio).

**Não funciona:** Pix, link de pagamento, cartão online; encomenda, entrega, receber depois;
desconto (passa por gerente conferido no servidor); comanda em uso aberta em outro dispositivo;
envio à cozinha; abrir/fechar caixa e sangria; iFood; NFC-e no ato (§5).

## 3. A fila local

### 3.1 Forma

IndexedDB do dispositivo (`shopman-pos-offline` / `sales`, chave = `client_request_id`).
Cada venda guardada leva: `id`, `capturedAt` (hora da cobrança, ISO com fuso), `pricesAt` (hora da
leitura de preços usada), `body` (o mesmo corpo do `close_sale`, com `expected_total_q`), total,
itens, rótulo do pagamento, `status` (`pending` | `conflict`), tentativas e último erro. Sem
IndexedDB a fila cai para a memória da aba e a lista avisa que fechar a aba perde as vendas.
A escrita resolve no `oncomplete` da transação: a tela só mostra "guardada" depois disso.

### 3.2 Envio

- Gatilhos: volta da conexão (`useConnectivity().onReconnect`), abertura da tela (resto de antes
  do reload) e a cada 30 s enquanto houver pendente.
- Ordem: hora da cobrança. Uma rodada por vez (guarda na aba + `navigator.locks` entre abas).
- Destino de cada resposta (`classifyOfflineSend`):
  - `ok + order_ref` → sai da fila; a tela de resultado, se ainda de pé, troca para
    "Enviada: pedido NB-…";
  - status 0, 5xx, 408, 429, 401, 403 `station_locked` → para a rodada, nada marcado (tenta depois);
  - outra recusa 4xx → `conflict` com o motivo do servidor; a rodada segue para a próxima venda;
  - `order_created` com `order_ref` (cobrança incerta do lado do servidor) → sai da fila: a venda existe.

### 3.3 Reconciliação de conflitos

Decisões do dono (10/10/2026, perguntas 3 e 4 da §9): a venda guardada **não é recusada** por
preço nem por comanda mudada. O dinheiro já entrou; o servidor registra e avisa o gerente. Código:
`shop/services/pos_offline_sale.py`, chamado pelo `close_sale`.

**Preço (D).** O servidor precifica a venda **na hora da cobrança** (`offline_captured_at`), não na do
envio: os modifiers que leem o relógio (Happy Hour, promoções, cupom, aniversário, frete promocional)
leem `modifiers.pricing_now(ctx)`, que é `ctx["priced_at"]` quando presente e `now()` no resto. A
venda das 15h enviada às 17h30, com o Happy Hour no ar, sobe sem o desconto; a promoção que venceu
durante a queda vale para a venda feita antes; o aniversário é o do dia da venda. Se mesmo assim a
conta do servidor divergir do cobrado (preço de catálogo editado na queda, linha pesada, Happy Hour
que a tela sem conexão não sabia), **vale o total cobrado**: a sessão é regravada com os preços
cobrados (política `external`, sem modifiers de desconto) e a diferença fica em
`order.data.pos.offline.pricing`, no aviso do gerente e no relatório do caixa.

**Comanda mudada em outro dispositivo (C).** A venda fecha **exatamente** as linhas que este dispositivo
cobrou (por `line_id`). O que só a comanda tem (linha que o outro dispositivo lançou, ou a quantidade a
mais numa linha cobrada aqui) segue aberto numa comanda nova com o **mesmo número**; a linha que já
estava na cozinha não volta ao KDS (`kds_inherited_lines`). Linha que o outro tirou ou cuja quantidade
mudou e este cobrou: vale o cobrado, e o ajuste fica registrado. Comanda **já paga** no outro
dispositivo: as linhas já pagas não viram pedido de novo; o resto sobe como venda de balcão (as formas
descem ao total novo, o dinheiro primeiro); se **todas** já estavam pagas, nenhum pedido nasce, o
reenvio devolve o pedido pago e a cobrança em dobro fica em `pos.offline_duplicates` dele, com a
frase "Devolva ao cliente." ao gerente. Comanda **limpa** no outro dispositivo: sobe como balcão.
Uma linha que este dispositivo tirou sem conexão também aparece como "só a comanda tem" e fica
aberta: deixar à vista é o lado seguro.

**Proteção.** Só vale para a venda que passa nas travas da venda sem conexão (sem desconto, sem taxa,
sem entrega, sem encomenda, dinheiro ou maquininha), cujas linhas somam o total cobrado e cuja hora é
plausível: não no futuro (folga de 5 min no relógio do dispositivo), não mais velha que 24 h nem que o
turno aberto. Fora disso, a régua de sempre: precificada no envio, `total_changed` e
`tab_revision_conflict`.

**Quem vê o quê.** O operador, no caso comum, nada além de "Venda guardada enviada: pedido NB-…";
quando a comanda mudou, o aviso traz uma frase ("Itens lançados em outro dispositivo seguem abertos
na comanda 12." ou "A comanda 12 já tinha sido paga em outro dispositivo. O gerente foi avisado.").
O gerente recebe um aviso `pos_offline_sale_adjusted` no Gestor (abre o pedido) e vê as mesmas
frases em "Vendas sem conexão com ajuste" no relatório do caixa (leitura X/Z, só com permissão de
auditar o caixa).

| Conflito | Quem detecta | Saída |
|---|---|---|
| Preço mudou (Happy Hour, promoção, catálogo, linha pesada) | o servidor, na hora da cobrança | Nenhuma no balcão: vale o cobrado, diferença registrada. Fora das travas: `total_changed`, "Enviar com R$ X" ou "Tentar de novo" |
| Comanda editada, paga ou limpa em outro dispositivo | o servidor, por `line_id` | Nenhuma no balcão: fecha o cobrado, o resto segue aberto, nada é cobrado duas vezes no sistema. Fora das travas: `tab_revision_conflict` |
| Turno fechado / sem turno | `cash_shift_required` | Abrir o caixa e "Tentar de novo" |
| Estoque | não recusa: o balcão vende o que está na mão; o ledger registra no envio | nada |
| Cliente em conflito (CPF/e-mail) | `customer_conflict` | "Tentar de novo" depois de resolver no Gestor |

O fechamento do caixa é barrado enquanto houver venda na fila (pendente ou recusada), com a frase
"N vendas feitas sem conexão ainda não foram enviadas. Envie antes de fechar o caixa."

### 3.4 Comanda sem conexão

Toda venda do PDV passa por comanda. Sem rede, a comanda **livre** abre só na tela
(`cart.localTab`), sem sessão no servidor, e sobe como venda de balcão direta (sem `tab_ref`); o
número fica na tela e no recibo. A comanda **já aberta neste dispositivo** fecha com a revisão que
a tela conhecia (`expected_revision`). Comanda em uso em outro dispositivo não abre.

### 3.5 Rede caindo com o fechamento em voo

Antes: a trava contra cobrança dupla acendia e o balcão parava até alguém conferir. Agora, se a
venda pode esperar (dinheiro/maquininha) e o navegador está sem rede, ela vai para a fila com a
**mesma chave**. Se o servidor chegou a fechar, o reenvio devolve o mesmo pedido; se não chegou,
fecha agora. Pix e cartão online seguem com a trava de sempre.

### 3.6 Registro no pedido

`close_sale` aceita `offline_captured_at` e `offline_prices_at` (só registro) e grava
`order.data.pos.offline = {captured_at, prices_at}` (documentado em `data-schemas.md`).

## 4. O total sem conexão

Regra do dono: total que pode mudar não aparece como final. Sem conexão o total é a soma da tela
pela última leitura de preços, e a tela diz isso: o botão mostra "total sem conexão R$ 11,50" e o
Pagamento mostra "Sem conexão: total pelos preços das 10:06. A venda é enviada quando a conexão
voltar." O número só existe para a venda que passa nas travas (sem desconto, sem taxa, sem
entrega), em que a conta da tela é a mesma que o servidor confere. É provisório na redação, e é
a **pergunta 1**.

## 5. NFC-e sem internet

Fatos (fontes oficiais):

- NFC-e em contingência offline é `tpEmis = 9` (NT 2015.002). A modalidade é da UF (Ajuste SINIEF
  19/16, cl. 11ª). No **Paraná**, a NPF 100/2014 (consolidada com a NPF 036/2015) não exige
  autorização prévia, trata como exceção, manda transmitir **em até 24 horas** da emissão, imprimir
  DANFE com "EMITIDA EM CONTINGÊNCIA" em duas vias (uma fica na loja até a autorização) e registrar
  motivo e hora de entrada em contingência. Vigência da NPF sob o RICMS atual (Decreto 7.871/2017):
  **não confirmada**, pedir ao contador.
- O QR Code da contingência carrega o DigestValue do XML assinado: a nota precisa ser gerada e
  assinada **na loja**, sem internet (certificado A1 acessível no ponto de venda).
- A NFC-e normal (`tpEmis 1`) com mais de 5 min entre emissão e recepção é rejeitada (Rejeição 704,
  NT 2015.002). Hoje o adapter calcula `data_emissao` na hora do envio
  (`fiscal_focusnfe.py`), então a venda guardada sai com a nota datada do envio: a venda existiu
  sem documento durante a queda.
- **Focus NFe:** a API em nuvem aceita `forma_emissao=offline` e trata SEFAZ fora do ar, mas com a
  loja sem internet o PDV não a alcança. Para isso existe o **Comunicador Offline**: executável
  desktop (Windows, `C:\Comunicador\`, instalador e ativação via suporte@focusnfe.com.br), com API
  local (`POST /v2/fiscal/nfce?ref=…&tipo_contingencia=offline`, porta padrão 55555), efetivação
  automática em 4 tentativas a cada 30 min, manual por `PUT /v2/fiscal/nfce/REF/efetivar`, pendentes
  em `GET /v2/fiscal/nfce/pendentes`. Requisitos: A1, NFC-e habilitada, CSC/ID_TOKEN, empresa na Focus.
  Páginas: `doc.focusnfe.com.br/reference/comunicador.md`, `emitir_nfce_local.md`,
  `efetivar_nfce_contingencia_local.md`, `listar_nfces_pendentes_local.md`.
- No repositório hoje: zero suporte a `tpEmis`/contingência (`fiscal_focusnfe.py`,
  `services/fiscal.py`, `handlers/fiscal.py`, `packages/fiscalman`). Retry da Directive soma ~63 min
  e depois vira alerta `fiscal_emit_failed`.

Desenho, se o dono quiser contingência de verdade (**pergunta 2**): o PDV, sem rede, manda a nota
ao Comunicador pela rede da loja (via agente local do Balcão, que já fala com a impressora), com
referência = `order_ref` futuro (ou o `client_request_id`), imprime o DANFE de contingência que ele
devolve, e guarda na venda da fila a chave e o XML provisórios. No envio, o servidor registra a
nota provisória em vez de emitir de novo (idempotência pela referência, que o handler já consulta
antes de reenviar: `query_status`/`_adopt_existing`) e acompanha a efetivação. Depende do dono:
PC Windows ligado no nobreak, ativação com o suporte da Focus e confirmação do contador.

## 6. Caixa e gaveta sem rede

- A venda guardada não abre turno nem fecha: ela entra no turno aberto quando sobe (o servidor
  injeta `cash_shift_id` pelo terminal). Fechar o caixa com fila é barrado na tela.
- Sangria, suprimento e abrir/fechar exigem rede (são escritas no livro do servidor).
- Gaveta: no Balcão abre pelo agente com a venda guardada (o registro da abertura falha calado e o
  livro recebe a venda no envio). No tablet não abre (o relay é do servidor): abre na chave.

## 7. O que a tela diz

- Aviso do cabeçalho (`alerts`, sempre com ação que abre a lista "Vendas sem conexão"):
  - sem rede, sem fila: "Sem conexão. O balcão continua vendendo." / ação "O que funciona agora";
  - sem rede, com fila: "Sem conexão. 2 vendas esperando envio." / "Ver vendas guardadas";
  - com rede, enviando: "Enviando 2 vendas guardadas…";
  - recusa: "1 venda guardada não entrou. Cada uma diz por quê. O caixa só fecha depois de resolver." / "Resolver".
- Tela de resultado: "Venda guardada neste dispositivo. É enviada sozinha quando a
  conexão voltar. A nota fiscal sai depois do envio." e, enviada, "Enviada: pedido NB-…".
- Avisos (toast) no envio: "Venda guardada enviada: pedido NB-2002."
- Nenhuma perda silenciosa: recusa fica na lista até resolver; fila só em memória é dita.

## 8. Riscos e o que fica de fora

- **Recarregar a tela sem internet** cai no `offline.html` do PWA (navegação é `NetworkOnly`). A
  fila sobrevive (IndexedDB) e sobe quando a tela volta com rede, mas a venda para até lá. Próximo
  passo: casco offline para `/` no PDV (cache da última navegação), que mexe no `operator-kit` e no
  que fica guardado no dispositivo (lista de operadores e gerentes no HTML).
- **Gaveta sem rede abre sem registro prévio** (no Balcão já era assim na venda em dinheiro: chuta e
  registra depois). O registro vem com a venda.
- **Preço trocado durante a queda**: vale o cobrado (§3.3). O preço do catálogo ainda é o de agora
  (a vitrine com validade por DATA não é relida na hora da cobrança); quando diverge, a diferença
  fica registrada, e não recusa. O navegador só decide o preço dentro das travas e da janela.
- **Cobrança em dobro** (comanda já paga no outro dispositivo): o sistema não registra a venda de
  novo, mas o dinheiro entrou duas vezes. A devolução é do gerente, pelo aviso. Em dinheiro, até lá
  a gaveta tem a sobra.
- **Comanda que seguiu aberta**: a linha que já estava na cozinha conta como enviada
  (`kds_inherited_lines`); desfazer o envio dela na comanda nova não alcança o ticket da antiga.
- **Nota fiscal** (§5): sem Comunicador, a venda guardada sai com nota datada do envio.
- Fora desta frente: KDS/cozinha sem rede, iFood, Pix com QR offline, desconto offline com PIN
  local, casco offline (acima).

## 9. Decisões para o dono

1. **Total sem conexão.** Mostrar o total da última leitura com "total sem conexão" e a hora dos
   preços (1), ou esconder o número e cobrar só por "Exato" (2)? *Recomendo 1*: o balcão precisa do
   número para dar troco, e a tela diz de onde ele veio.
2. **NFC-e na queda.** Instalar o Comunicador Offline da Focus num PC Windows no nobreak e emitir
   em contingência no ato (1), ou aceitar que a venda guardada sai com nota no envio, datada do envio
   (2)? *Recomendo 1*, depois de o contador confirmar a regra do PR (24 h, duas vias). Depende de PC
   Windows ligado no nobreak e da ativação com o suporte da Focus.
3. **Comanda mudada em outro dispositivo durante a queda.** **Decidido (10/10/2026):** sem recusa e
   sem cobrança dupla. Fecha exatamente as linhas cobradas (por `line_id`); o que o outro dispositivo
   acrescentou segue aberto na comanda; linha tirada ou mudada lá e cobrada aqui vale o cobrado, com
   registro; comanda já paga não é cobrada de novo no sistema (sobe só o que não estava pago; tudo
   pago, nenhum pedido nasce e o gerente é avisado para devolver). Ver §3.3.
4. **Preço que mudou.** **Decidido (10/10/2026):** o servidor precifica no horário da venda
   (`offline_captured_at`); se ainda divergir, vale o total cobrado e a diferença fica no pedido, no
   aviso do gerente e no fechamento do caixa. Só dentro das travas e da janela plausível. Ver §3.3.
