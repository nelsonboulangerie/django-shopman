# SSE-PRINT — impressão da DANFE sem clique

**Status: anotado, não iniciado.** Marcador de intenção (24/08/2026); executar
quando o balcão sentir o clique como atrito real, não antes.

## O problema que isto resolve

A emissão da NFC-e é assíncrona: a nota autoriza segundos DEPOIS de a tela de
confirmação da venda passar. Hoje o caminho do papel é a aba "Últimas vendas"
(poll calmo de 5s com o painel aberto) + 1 clique em "DANFE". Funciona e é
robusto — mas no balcão cheio, o clique é um passo que o operador pode querer
não ter.

## O desenho (quando for a hora)

Seguir a ADR-016 (SSE-first sobre fetch canônico; poll como fallback):

1. **Canal SSE por terminal** (`pos-fiscal:<terminal_ref>`), permissão no
   `ShopmanChannelManager` (operador ativo com `cashman.operate_pos`).
2. **Emissor**: no `NFCeEmitHandler._record` (nota autorizada), publicar
   `{order_ref, nfce_number}` no canal do terminal que vendeu
   (`Order.data.pos.terminal_ref`). Mesmo padrão dos emitters de
   disponibilidade (`shop/handlers/_sse_emitters.py`).
3. **BFF**: `proxyEventStream` do operator-kit (`server/utils/eventStream.ts`),
   rota `/events/pos-fiscal/` — mesmo cano do KDS.
4. **PDV**: assinar o canal; no evento, SE a venda tem canal `print` marcado
   (`receipt.channels`), buscar `danfe-escpos` e mandar ao agente (`/print`)
   sem clique. O evento é gatilho de REFETCH, nunca portador do payload
   (fonte da verdade continua o endpoint).
5. **Fallback**: a aba "Últimas vendas" continua exatamente como está — ela é
   o caminho canônico; o SSE só antecipa o clique.

## Pré-condições

- Redis no ambiente (SSE multi-worker exige; o alpha tem Valkey).
- O PDV hoje NÃO assina SSE nenhum — este seria o primeiro canal da superfície;
  o custo de bootstrap (composable de assinatura, reconexão via operator-kit)
  paga-se só com uso real.

## Por que não agora

O clique único na aba cobre o caso com folga durante o alpha, e abrir canal
SSE + permissão + proxy para economizar um clique é peso antes da dor. Quando
a Nelson operar o PDV com volume real e o clique doer, este plano vira WP.
