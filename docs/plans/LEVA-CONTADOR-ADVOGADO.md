# Leva única ao contador e pergunta ao advogado

Preparado em 13/10/2026 para o go-live da Nelson Boulangerie (Simples Nacional, Londrina/PR,
NFC-e pela Focus NFe). O dono envia; este arquivo só guarda os textos e a prova de cada "hoje
fazemos X". Os dois textos abaixo estão prontos para colar no e-mail.

Regra seguida: CFOP 5102/5405, CSOSN 102/500 e PIS/COFINS 99 são parametrização formal do
contador (`docs/reference/fiscal-parametrizacao-nfce.md`) e não entram como pergunta.

---

## Texto 1: ao contador

**Assunto:** Nelson Boulangerie: confirmações da NFC-e antes de ligar em produção

Olá,

Vamos ligar a emissão de NFC-e em produção (Focus NFe). Antes, preciso que você confirme como o
sistema está configurado. Em cada item escrevo o que fazemos hoje: basta responder "sim" ou indicar
a alternativa. CFOP, CSOSN e PIS/COFINS seguem a sua parametrização e não estão em discussão.

**1. Forma de pagamento na nota (tPag)**

1.1. Dinheiro 01; maquininha crédito 03 e débito 04; Pix 17 (QR Code gerado na hora para cada
venda). Está certo? (sim / outro: ___)

1.2. Conta na casa (o cliente leva e paga depois): 05, Crédito Loja. (sim / 99 Outros / outro: ___)

1.3. Cartão no site e link de pagamento: 03 ou 04 quando a operadora informa se foi crédito ou
débito; quando não informa, 99 Outros. (sim / outro: ___)

1.4. Pedido do iFood (o cliente pagou ao iFood): 99 Outros, no valor da parte da casa. (sim / outro
código: ___)

1.5. "Outro meio" registrado no PDV: 99 Outros. (sim / outro: ___)

**2. Entrega e iFood**

2.1. Entrega pelos nossos canais (site, balcão, WhatsApp): só aceitamos com CPF ou CNPJ e endereço
completo. A nota sai como entrega a domicílio (indPres 4), com a taxa como frete e a padaria como
transportadora (modFrete 3). Está certo? (sim / outro: ___)

2.2. iFood sem CPF, que é o caso comum: a nota sai presencial (indPres 1), consumidor não
identificado, sem frete e sem transportador. É a prática dos sistemas de restaurante. Podemos
seguir assim? (sim / não, fazer: ___)

2.3. iFood com CPF: nota de entrega (indPres 4) com o destinatário. Como quem entrega é o iFood, a
taxa de entrega fica fora da nota e o frete vai como "por conta de terceiros" (modFrete 2), sem
transportador. (sim / modFrete 9 / outro: ___)

2.4. Grupo do intermediador: CNPJ do iFood 14.380.200/0001-21 e, no identificador da loja na
plataforma, o nome fantasia "Nelson Boulangerie". (sim / usar outro identificador: ___)

2.5. Cupom no iFood: o cupom pago pela loja reduz a base da nota (desconto); o cupom pago pelo
iFood não reduz, porque a casa recebe o valor cheio no repasse. (sim / outro: ___)

2.6. Cliente do iFood altera o pedido depois da NFC-e autorizada: hoje o sistema avisa e não faz
nada fiscal. Qual o procedimento? (a) cancelar, se ainda dentro de 30 minutos, e emitir outra; (b)
nota de estorno e nova nota; (c) outro: ___

**3. NT 2026.002 (em produção desde 05/10/2026)**

Li a versão 1.10a no Portal da NF-e. Ela mantém a exigência de destinatário na NFC-e de entrega
(rejeição 787) e os indicadores de presença aceitos na NFC-e (1, 4 e 5). Pela minha leitura, nada
muda nos itens 2.1 a 2.3. Três pontos dependem do Paraná ou da casa:

3.1. O Paraná permite NFC-e com entrega a domicílio? A NT deixa cada estado proibir (rejeição 785).
Em homologação, a nossa foi autorizada. (sim / não)

3.2. O Paraná fixou limite menor que R$ 10.000,00 para NFC-e sem identificar o consumidor? (não /
sim, R$ ___)

3.3. A NT proíbe NF-e de saída que referencie NFC-e, então não dá mais para trocar a NFC-e por NF-e
depois. Hoje só emitimos NFC-e (com CNPJ, quando a empresa pede). Precisamos emitir NF-e para
cliente empresa? (não / sim, nos casos: ___)

**4. Encomenda paga antes**

Hoje, no pagamento antecipado sai só um recibo não fiscal; a NFC-e sai na saída da mercadoria (na
retirada ou quando a entrega fica pronta para sair), com a forma de pagamento usada. O motivo é que,
no Paraná, a NFC-e só pode ser cancelada em 30 minutos e com a mercadoria na casa.

4.1. Está certo para 2026, no Simples? (sim / emitir no pagamento)

4.2. Em 2027, com IBS/CBS, o pagamento antecipado vai exigir algum documento no ato (nota de débito
de antecipação)? (não / sim, a partir de: ___)

**5. Contingência sem internet**

Hoje, sem internet, o caixa vende e guarda a venda; quando a rede volta, a NFC-e é emitida
normalmente, com a data do envio. O plano é instalar o emissor offline da Focus numa máquina Linux
da loja e emitir em contingência no ato: transmitir em até 24 horas, imprimir o DANFE "emitida em
contingência" em duas vias (uma fica na loja até a autorização) e registrar motivo e hora.

5.1. Essa regra (24 horas, duas vias, NPF 100/2014 consolidada com a NPF 036/2015) continua valendo
no Paraná? (sim / mudou: ___)

5.2. Até a contingência estar instalada, emitir quando a rede volta, com a data do envio, é
aceitável? (sim / não, fazer: ___)

**6. CEST e classificação dos itens**

6.1. Bebidas preparadas no balcão (cafés, chás, chocolate, sodas da torneira): NCM 2202.99.00, sem
CEST. (sim / usar CEST: ___)

6.2. Produção própria, com CEST: pães e salgados de forno 1905.90.90 (17.062.00); pão de forma
1905.90.10 (17.060.00); hot dog 1601.00.00 (17.076.00); jambon-beurre 1602.41.00 (17.079.04);
ratatouille e tapenade 2005.99.00 e 2005.70.00 (17.092.00). (sim / ajustar: ___)

6.3. Revenda com ST (CSOSN 500): mostardas Maille 2103.30.21 (17.038.00); cremes de queijo
Pomerode 0406.30.00 como "requeijão e similares" (17.023.00); água mineral Prata (03.005.00).
(sim / creme de queijo como queijo, 17.024.00, sem ST / outro: ___)

6.4. Revenda sem ST, com CEST na nota: queijos (17.024.00), manteiga (17.025.00), geleias
(17.094.00), azeite (17.067.00), relish (17.090.00), presunto cru (17.087.01), chás Kãnfa
0902.10.00 (17.097.00), berinjela Duga e churrasquinho de pimenta 2005.99.00 (17.092.00). A nota do
fornecedor da berinjela vem com 2103.90.99. (sim / ajustar: ___)

Obrigado!

---

## Texto 2: ao advogado

**Assunto:** Nelson Boulangerie: direito de arrependimento na venda online de alimento

Olá,

A padaria vende pelo site e pelo WhatsApp, com retirada ou entrega, pagamento antecipado (Pix ou
cartão) ou na entrega. São pães, doces, salgados e bebidas feitos no dia ou sob encomenda, todos
perecíveis. A mercearia embalada (geleias, chás em lata, queijos) hoje só é vendida no balcão, mas
pode ir para o site.

Os Termos do site dizem hoje, na seção "Cancelamento, troca e devolução":

- pedido não pago: o cliente cancela pela tela de acompanhamento;
- pedido pago, antes do preparo: o cliente pode desistir; vira solicitação com protocolo e a loja
  devolve o valor inteiro;
- depois que o preparo começa: "o pedido é alimento perecível, feito para você, e não volta para a
  prateleira. A partir daí não há desistência sem motivo";
- produto errado ou com problema: o cliente avisa pelo WhatsApp com foto; a loja resolve com troca
  ou devolução do valor, ou crédito se o cliente preferir; "vale sempre o Código de Defesa do
  Consumidor";
- pedido feito no iFood segue a política do iFood.

Perguntas:

1. Para alimento perecível e encomenda, essa redação basta diante do art. 49 do CDC (sem
   desistência depois de iniciado o preparo)? (sim / ajustar: ___)

2. Se a mercearia embalada, não perecível, for vendida pelo site, precisamos aceitar a desistência
   em 7 dias do recebimento, com devolução integral? (sim / não)

3. Na desistência antes do preparo, "valor inteiro" inclui a taxa de entrega. Está certo? (sim / não)

4. Falta alguma informação obrigatória no site ou no checkout sobre desistência (Decreto
   7.962/2013)? (não / sim: ___)

Obrigado!

---

## Prova do "hoje fazemos" (uso interno, não vai no e-mail)

Medido no `main` em 13/10/2026 (`dfda93b44`).

**1. tPag**
- Tabela: `shopman/shop/adapters/fiscal_focusnfe.py:28` (`PAYMENT_METHOD_CODES`): cash 01, credit 03,
  debit 04, account 05, pix 17, external 99; método desconhecido cai em 99 (`:742`).
- Cartão da loja e link: `:51` (`_CARD_BY_GATEWAY`) e `:742`: 03/04 pelo `card_funding` que a Stripe
  devolve (`shopman/shop/adapters/payment_stripe.py:404`), senão 99.
- Maquininha do PDV usa `credit`/`debit` (`shopman/backstage/projections/pos.py:528`).
- iFood grava `payment.method = "external"` e a nota declara a base da casa
  (`shopman/shop/services/fiscal.py`, `_fiscal_payment`).
- Mudança desde o lembrete de 17/09: conta na casa já vai como 05 (era 99).

**2. Entrega e iFood** (decisão do dono 24/09; PRs #888 e #897 mergeados)
- Canal próprio exige CPF/CNPJ e endereço na entrada: `shopman/shop/services/delivery_fiscal_identity.py:69`
  (`recipient_gaps`) e `:114`.
- Nota de entrega: `fiscal_focusnfe.py:323` (indPres 4) e `:463` (`_delivery_freight_mode`: 3 da casa, 2 da
  plataforma, configurável por env).
- iFood sem CPF sai presencial: `shopman/shop/fiscal_intermediary.py:378` (`issues_as_presential`).
- idCadIntTran: env `FISCAL_INTERMEDIARY_IFOOD_ID_CAD` vazia (`config/settings.py:1852`) e, vazia, cai no
  `Shop.name` (`fiscal_intermediary.py:152`). O comentário de `settings.py` ainda diz que sem a env o
  grupo não sai; o código atual já preenche com o nome da loja.
- Cupons por patrocinador: `fiscal_intermediary.py:267` (`house_discounts`): só o cupom da loja reduz a base.
- Pedido alterado com NFC-e autorizada: pergunta aberta do #897; o sistema marca `fiscal_authorized` e avisa.

**3. NT 2026.002** (fonte: Portal Nacional da NF-e, "Operações de vendas presenciais e não presenciais
com impressão do DANFE Simplificado Tipo 2", v1.10a, ago/2026)
- Cronograma: W16-40 (limite por UF) produção 15/06/2026; DANFE Simplificado Tipo 2 produção 03/08/2026;
  autorização com alerta (cStat 120, regra 5E17-65 para CNPJ irregular) e BA02-35 produção 05/10/2026.
- indPres 4 passa a ser "Operações não presenciais com NFC-e e NF-e com DANFE Simplificado Tipo 2 (com
  entrega)"; B25b-20 segue aceitando só 1, 4 e 5 na NFC-e (717); E01-20 segue exigindo destinatário com
  indPres 4 (787); B25b-30 deixa a UF proibir entrega em NFC-e (785); X02-10 segue (753).
- B09-40: contingência offline (tpEmis 9) transmitida depois de 24 h volta cStat 150, "autorização fora de prazo",
  a critério da UF.
- BA02-35: NF-e de saída não pode referenciar NFC-e, salvo complementar ou devolução.
- O adapter já cita a NT: `fiscal_focusnfe.py:361` a `:375` e `:553`.

**4. Encomenda paga antes** (o brief dizia "a nota sai no pagamento"; isso mudou em 26/09, commit `478f8aa79`)
- `shopman/shop/services/fiscal.py:336` (regra "Via Recibo primeiro, Nota depois"), `:364`
  (`emission_waits_for_handoff`, com `TODO(2027-01-01)` de IBS/CBS) e `:387` (`emit_on_payment`).
- Prazo de cancelamento no PR: `fiscal.py:194` (`cancellation_path`).
- Memória: `reference_nfce_encomenda_paga_antes.md` (LC 214/2025 art. 10 §4º; NT RTC 2025.002; Simples
  obrigado a IBS/CBS em jan/2027, art. 348).

**5. Contingência**
- Zero suporte a tpEmis 9 no envio; a nota leva `data_emissao` da hora do envio (`fiscal_focusnfe.py:307`).
- O PDV vende sem rede com dinheiro, crédito, débito e outro meio (`shopman/shop/services/pos_offline_sale.py:42`).
- A DANFE e o recibo já reconhecem uma nota em contingência (`shopman/shop/views/fiscal_danfe.py:393`,
  `shopman/backstage/services/receipt_escpos.py:1064`).
- Regra do PR e plano do Comunicador: `docs/plans/WP-PDV-SEM-CONEXAO.md` §5; máquina Linux:
  memória `project_lembrar_hardware_balcao_que_nao_para.md`.

**6. CEST**
- Tabelas: `docs/reference/fiscal-parametrizacao-nfce.md` (seções da produção própria e da revenda) e
  `config/management/commands/apply_grocery_catalog.py` (`FISCAL_NOTES`); bebidas preparadas sem CEST por
  decisão do dono de 23/09 (`docs/reference/ncm-bebidas-preparadas.md`).
- CEST é atributo do produto; obrigatório só no perfil com ST (`packages/fiscalman/shopman/fiscalman/classification.py:21`
  e `:109`).

**Advogado**
- Termos: `surfaces/storefront-nuxt/app/pages/termos.vue:144` (seção `cancellation`) e a seção `ifood-orders` logo
  abaixo. §7 aprovado pelo dono em 24/09 (#1067).
- Mercearia nasce só no PDV, até ter foto: `apply_grocery_catalog.py` (docstring, "Onde se vende").
