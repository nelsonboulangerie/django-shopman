# V6-CAIXA: gaveta aberta pelo tablet, com autoria, e a tolerância do caixa

- **id:** V6-CAIXA
- **branch:** `claude/v6-caixa`
- **início (UTC):** 2026-10-04
- **prévias:** `docs/plans/suite-ux-v2/v4/pos-tablet-fluxo.jpg` (passo 3 e "Uma gaveta, um turno, um
  fechamento"), `fim-do-dia.jpg`; plano `SUITE-UX-FUNCTION-PLAN.md` §16 e §17.

## Decisões do dono (04/10/2026)

1. **Gaveta aberta pelo tablet, com autoria.** No tablet, ao receber em dinheiro, o operador do
   tablet (o PIN dele, independente de quem esteja logado no PC do Balcão) toca "Abrir gaveta" e o
   agente do Balcão dispara o pulso. Toda abertura fica no livro-caixa com quem, de qual
   dispositivo, quando e por quê. Abertura sem venda exige motivo e a permissão dos movimentos de
   caixa (`cashman.operate_pos`). A gaveta segue uma só por terminal; o fechamento segue cego; as
   aberturas aparecem no relatório do gerente. Funciona também no próprio Balcão (mesmo registro).
   Offline ou agente sem resposta: a tela diz isso, sem fingir sucesso. "Enviar cobrança para a
   fila do Caixa" foi descartado.
2. **Tolerância do caixa**, padrão 0,5% do dinheiro do dia, mínimo R$ 2, máximo R$ 20, por loja e
   por terminal. O operador nunca vê o veredito. O gerente vê "dentro/fora" no relatório do turno;
   fora abre um `OperatorAlert`.

## O que entrou

**Livro (`packages/cashman`).** `drawer_open` deixa de ser "sem venda": o rótulo vira "Gaveta
aberta" (`cashman.0007`, só choices) e o porquê mora em `payload.purpose` (`sale` com `order_ref`,
`no_sale` com `reason`), cobrado pelo escritor único (`ledger.record`). O Admin do turno
(`cashman.audit_shift`) ganhou as colunas **Tolerância** (dentro/fora) e **Aberturas da gaveta**
(total, por venda, sem venda, pelo tablet), e a linha do tempo diz de cada abertura o porquê, o
caminho e o dispositivo, com a resposta do agente ao pulso logo abaixo.

**Pulso pelo relay (`backstage/services/drawer_pulse.py`).** O dono único das aberturas.
`via=local`: o Balcão grava e chuta pelo agente da própria máquina. `via=relay`: o tablet pede, o
servidor grava a linha e cria um `PrintJob` `kind=drawer_pulse` (`backstage.0084`) com os cinco
bytes `ESC p` (`receipt_escpos.drawer_kick`, com o pino e o pulso do terminal) na mesma transação;
o agente do terminal busca pelo relay que já existia e entrega à impressora sem saber que é
gaveta (nenhuma mudança no agente; teste prova que o claim passa). O pulso vale 30 s e expira:
nunca abre a gaveta minutos depois, sem ninguém na frente. A resposta do agente volta ao livro como
nota filha da abertura (`drawer_pulse_result`). Rotas: `POST pos/cash/drawer-open/` (`purpose`,
`order_ref`, `reason`, `via`) e `GET pos/cash/drawer-pulse/<ref>/`. A Projection do PDV leva
`drawer_relay` (há caminho? o agente respondeu há pouco?). O B.I. não conta abertura por venda
como "abertura sem venda".

**Tolerância (`backstage/services/cash_tolerance.py`).** `Shop.defaults["pos"]["cash_tolerance"]`
(ShopAdmin, Ponto de venda) e `Terminal.metadata["cash_tolerance"]` (Admin do terminal, chave a
chave por cima da loja); valor ilegível nunca desliga a régua. O veredito nasce ouvindo
`shift_closed` (e é refeito a cada `count_correction`) numa nota do livro que congela a régua do
dia; fora dela, `OperatorAlert` `cash_out_of_tolerance` no público `finance`. Nenhuma projection
de operador lê a nota.

**PDV (`surfaces/pos-nuxt`).** `useDrawerOpening`: no Balcão (o agente responde na loopback) a
venda em dinheiro chuta como sempre e registra a abertura por venda; no tablet a gaveta nunca abre
sozinha e a venda vira o cartão **"Dinheiro da comanda · troco · leve ao Balcão"** com o botão
**"Abrir gaveta do Balcão"** (`PosDrawerPulseCard`), na tela de resultado e, depois da "Nova
venda", no topo da venda até abrir. O estado acompanha o pulso (abrindo, aberta, não respondeu,
sem confirmação, sem conexão) e oferece "Abri com a chave". A sessão de caixa abre sem venda pelo
relay quando o dispositivo é o tablet. Trava de teste: nenhuma tela do PDV fala em tolerância.

## Fora daqui (com nome e motivo)

- Layout da folha de pagamento do tablet e do Fim do dia: da frente V6-PDV. Aqui entra só o cartão
  do dinheiro e o slot na tela de resultado; o passo 3 do Fim do dia continua dizendo "Caixa
  fechado · contagem cega registrada" (sem veredito, por decisão do dono).
- "Enviar cobrança para a fila do Caixa": descartado pelo dono.
- Abertura na chave física: fora do sistema por natureza ("Abri com a chave" só tira o cartão).
