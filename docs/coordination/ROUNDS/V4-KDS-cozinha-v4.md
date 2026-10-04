# V4-KDS: a Cozinha igual à prévia v4

- **id:** V4-KDS
- **branch:** claude/v4-kds
- **PR:** ver o PR do branch `claude/v4-kds`
- **estado:** PR aberto, auto-merge
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 (ordem do dono, 04/10: "quero tudo igual a v4"). O app da Cozinha
(`surfaces/kds-nuxt`) veste a camada visual da suíte (`data-suite="v3"`, rail,
cabeçalho de uma linha e barra do polegar do kit; modelo: o Gestor, #1448/#1451) e fica
igual às prévias `docs/plans/suite-ux-v2/v4/cozinha-estacao.jpg` e
`cozinha-celular.jpg` (fontes `fontes/v4/cozinha-estacao4.html` e
`cozinha-celular4.html`). Função não regride.

## O que entrou
**Shell:** `data-suite="v3"`; `KdsNav` monta `OperatorSuiteRail` (tablet para cima) e
`OperatorSectionBar` (celular). Seções: Estações, Preparo (a estação deste dispositivo,
lembrada; selo com os pedidos dela), Saída (atalho para a coluna Saída do Gestor, com o
selo dos prontos para sair que o índice já conta; a Cozinha continua sem tela de Saída,
#1431), Painel de retirada (só no rail) e Ajustes no pé. Avisos (`NotificationBell`) no
pé do rail e no cabeçalho do celular.

**Estação (`pages/[ref].vue`):** `OperatorPageHeader` ("Estação X" · Preparo · ao vivo
honesto pelo SSE, busca de 19 rem com "/", Som da estação, Reabrir com contagem, relógio).
Faixa de avisos: "Pedido novo U13" com Visto (diz quais pedidos tocam) e o cancelamento
com "Item cancelado HH:MM · o resto continua" ou "Cancelado". A fazer. Cabeça da grade com
recortes Todos/Entrega/Atrasados. A FILA em foco: colunas pela densidade, linhas pela
altura (3×2 no tablet deitado, 4×2 no desktop, 2×3 no tablet em pé); ticket longo ocupa
duas alturas; o resto vira "+N na fila · todos no prazo, já somados em "A fazer"", que
abre a fila inteira ("Voltar à fila em foco" recolhe). A busca mostra todos.

**Ticket (`KdsTicketCard`):** desenho `.tk` da v4: código, "Retirada · cliente", relógio
(atrasado sólido, perto da meta âmbar, no prazo neutro), pílula (Próximo · atrasado, Novo,
Em preparo, Bloqueado), itens de 17 px, observação curta na linha ("· sem gergelim") e
longa em caixa "Obs.:", notas do pedido depois dos itens, botão de 56 px: o convite do
PRÓXIMO sólido na cor da casa, os outros contornados, Finalizar verde, travado tracejado
com cadeado.

**Bloqueio de pagamento antes do toque (K11):** a projeção do ticket ganhou
`finish_block_label`/`finish_block_reason` (mesma régua de `kds.complete_ticket`: pedido
NEW sem confirmação; ACCEPTED com pagamento digital não capturado pelo `payment_gate`).
O card mostra "Pix não confirmado. Pode adiantar; o Finalizar libera quando o pagamento
entrar." e o toque no Finalizar diz o motivo em vez de abrir a janela de 5 s que voltava
recusada. Iniciar segue livre. Contrato TS regenerado (`export_kds_schema`).

**Celular (`KdsPhoneQueue`):** "Agora" inteiro, Próximo/Depois em linhas de 64 px (tocar
traz para o foco), bloqueio na linha, "+N na fila · A fazer: …" (abre todos), o botão do
ticket em foco no polegar (teleport para `#kds-thumb`).

**Ajustes (`KdsSettingsDialog`):** tamanho do ticket (lembrado no dispositivo) e a data de
consulta, que saíram do cabeçalho. Em consulta, o cabeçalho mostra "Consulta: …" e
"Voltar para hoje".

**Estações (`pages/index.vue`):** cabeçalho de uma linha e cartões da suíte; a Saída do
cadastro diz "Saída · no Gestor".

**Kit:** nada mudou na layer; `guardrails.appBar.test.ts` tira as duas páginas do KDS da
lista de cabeçalhos próprios e põe `KdsNav` entre os migrados.

## Função (não regride)
Mudaram de lugar: densidade e data (Ajustes, a um toque do rail/barra), Visto (faixa de
avisos), Painel de retirada (rail). Todos os gestos (iniciar, finalizar com desfazer,
reabrir, recebi o cancelamento, detalhe, som, busca) seguem a um toque. Testes que
fixavam o visual antigo (cor dos botões, altura h-11 da Padrão, `rounded-md`, `px-4`,
tons `red/amber`, título "Escolha uma estação", `aside[data-rail-state]`) foram reescritos
para o desenho novo; nenhum teste de comportamento afrouxou.

## Evidência (saída de comando, 04/10/2026)
- `surfaces/kds-nuxt`: `npx vitest run` → 8 arquivos, 122 testes passando (novos:
  `tests/sections.test.ts`, fila em foco, pílula, relógio, bloqueio de pagamento);
  `npx nuxi typecheck` limpo; `npx eslint .` limpo.
- e2e do KDS (Playwright, Chromium 1194 desta máquina, mock backend): 4 de 4 passam.
- `surfaces/operator-kit`: `npx vitest run` → 105 arquivos, 1142 testes passando.
- Python: `pytest -k "kds or saida"` em `shopman/backstage/tests` → 255 passando, 3
  pulados; `test_kds_finish_payment_twin.py` (4, novo) + `test_vocabulario_de_tela.py` +
  `test_kds_schema_export.py` → 2268 passando; `ruff check` limpo nos arquivos tocados.
- Sem migração.

## Fora daqui (com nome e motivo)
- "iniciado por Rafael às 21:56 · retira às 22:30": o `KDSTicket` não guarda quem iniciou
  nem quando. Campo novo com migração: decisão do dono.
- Visto registrado no servidor por estação (K20): segue por dispositivo; a faixa diz
  "toca neste dispositivo".
- Push no celular e o aviso de atraso no bolso do gerente (prévia do celular, (c)):
  o KDS não tem push.
- Toque longo (desfazer, reabrir, ver o pedido): gesto novo; os três seguem a um toque.
- Ordem do pé do rail (Ajustes acima de Avisos): é a peça do kit, igual ao Gestor.
- Densidade "da estação provisionada": não há cadastro por estação; fica no dispositivo.

## Prova visual
`scratchpad/ux/v4-kds/index.html` da sessão coordenadora (+ `img/`): estação 1180×820
claro e escuro, fila inteira, desktop 1440×900, tablet em pé 820×1180, celular 390×844
claro e escuro, 320×568, Estações (tablet e celular), Ajustes e o Painel de retirada.
Baselines visuais: o kds-nuxt não tem.
