# T1 — PDV: as formas de pagamento esperam a revisão do total

- **id:** T1
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; frentes T1 a T5 executadas por subagentes em worktree próprio)
- **branch:** claude/pdv-pagamento-espera-revisao
- **PR:** #1380
- **estado final:** na fila #1380 (auto-merge ligado; às 16:55 UTC só o "Marketing — cadeia completa" vermelho, não obrigatório)
- **início / fim (UTC):** 2026-10-02 16:33 / 2026-10-02 16:40

## O que mudou
Opção (b) do dono. `surfaces/pos-nuxt/app/components/PosPaymentWorkspace.vue`: `awaitingReviewReason()` (:685)
reusa o `needsReview` do "Validar"; `paymentMethodBlockedReason` (:693) o consulta primeiro, então o botão
da forma fica desabilitado com o motivo no `title` ("Atualizando o total. A forma libera assim que ele
chegar." / "O total não atualizou. Toque em Tentar de novo."); `pressMethodKey` (:1177) consome a tecla e
mostra o mesmo motivo. A conta do total interino (`usePosSale.ts:926-928`) e o `posIntent.ts` intocados.

## Prova
Teste novo `surfaces/pos-nuxt/tests/components/PosPaymentWorkspace.awaitsReview.test.ts`, que clica NA FORMA
durante a janela: contra o código antigo `Tests 3 failed | 1 passed (4)`; com a mudança `4 passed` (o 4º
confere que libera quando a revisão chega). pos-nuxt inteiro: `Tests 1421 passed`; typecheck 0. A trava do
total interino (`usePosSale.payment.test.ts`) segue verde.

## O que ficou de fora
- O passo 2 (total esperado no pedido + recusa se mudar): virou D42 no PENDING-DECISIONS (no próprio #1380).
- O "Exato" (tecla `=`) tinha a mesma corrida: virou T1b (BOARD), PR de seguimento depois do #1380.

## Perguntas ao dono
D42: o PDV passa a mandar o total esperado e o servidor recusa a venda quando ele mudou? (sim/não)

## Armadilhas novas
16 testes do operator-kit (`useOrientationLock`, `usePwaInstall`, `OperatorRail`) reprovam no Node 26 local
(`localStorage` indefinido); sob o Node 22 da CI passam. Não é regressão.

## Próximo passo
T1b, desta sessão (subagente esperando o #1380 entrar).
