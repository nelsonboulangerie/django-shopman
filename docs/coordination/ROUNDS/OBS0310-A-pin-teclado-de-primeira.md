# OBS0310-A: a trava do operador escuta o teclado de primeira

Branch `claude/obs0310-pin-teclado`, PR #1413.

## O pedido (dono, 03/10/2026)

> "quando a tela do PDV trava, na tela do PIN parece que nunca 'pega' o número
> que digito logo de primeira! Parece que tenho que clicar na tela [...] Não tem
> como deixar ficar escutando o teclado de primeira?"

## A causa

A captura de PIN/crachá (`operator-kit/app/composables/useIdentityCapture.ts`)
já ouvia no documento, em fase de captura. O problema era o que ela considerava
"campo de texto do dono": qualquer `INPUT` focado. O PDV trava por ociosidade com
a busca de produto focada (`PosProductGrid`, `autofocus`), atrás do overlay. A
captura via o alvo da tecla como um campo de texto, deixava a tecla seguir, e o
número ia parar na busca escondida. Tocar no overlay tirava o foco da busca, e só
então o teclado "pegava".

Causa secundária: `useOperatorLock` criava a lista de quem destrava (`eligible`)
vazia a cada montagem da trava. O `OperatorIdentify` (que é quem ouve o teclado)
só montava quando a busca voltava, então o que se digitava nesse meio-tempo se
perdia.

## A cura (no kit, vale para os oito apps que usam a trava)

1. `useIdentityCapture` ganhou `frame`: campo de texto só é do dono se estiver
   DENTRO da moldura modal (overlay da trava ou diálogo). Foco fora dela é foco
   esquecido: dígitos, Backspace e Enter vão para a identificação, com
   `preventDefault` + `stopPropagation` (o Enter da busca, que adiciona produto,
   não chega lá).
2. `OperatorIdentify` passa como moldura o `[data-operator-lock]` ou o
   `[role='dialog']` mais próximo. No cancelamento de venda do PDV, o campo de
   motivo (dentro do diálogo, fora do `OperatorIdentify`) continua recebendo
   texto.
3. `OperatorLock` toma o foco ao subir (overlay com `tabindex="-1"`, sem anel) e
   de novo quando a janela volta a ter foco (`window focus`) ou a aba volta a
   ficar visível (`visibilitychange`). Não rouba foco de quem já está dentro da
   trava (campo da troca de PIN, botão).
4. `useOperatorLock.eligible` virou `useState` por permissão: da segunda trava em
   diante, a lista já está lá e o teclado ouve desde o primeiro instante.

Toque no pad e crachá seguem pelos mesmos caminhos (testes antigos verdes).

## Limite que o código não resolve

Se a janela do navegador inteira não tem o foco do sistema operacional (o kiosk
ficou atrás de outra janela), nenhuma página recebe tecla: o primeiro toque ou
clique é do sistema. Quando a janela volta, a trava retoma o foco sozinha.
