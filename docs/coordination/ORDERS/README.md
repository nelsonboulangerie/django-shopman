# ORDERS — o canal entre o coordenador e as sessões executoras

O coordenador escreve a ordem do turno aqui. A sessão executora lê daqui. **O dono não
transcreve mais nada.**

## Como o dono abre uma sessão

Uma linha só:

> Siga a ordem em `/Users/pablovalentini/Dev/Claude/django-shopman/docs/coordination/ORDERS/next.md` — leia inteira, execute tudo, e registre no BOARD e no ROUNDS.

É sempre a mesma linha. O caminho é absoluto de propósito: a sessão trabalha num worktree, e
worktree não enxerga arquivo solto do checkout principal.

## O contrato

1. **A ordem é o `next.md`.** Ele é reescrito pelo coordenador a cada turno. Leia inteiro.
2. **Antes de começar:** rode `make coordination` e leia `docs/coordination/BOARD.md`. Se a frente
   está `EM_EXECUCAO` por outra sessão nas últimas 12 h, não toque.
3. **Ao pegar uma frente:** acrescente a sua linha no BOARD.
4. **PRIMEIRA COISA ao começar, antes de qualquer frente:** copie este `next.md` para
   `docs/coordination/ORDERS/<data>-<turno>.md` no seu branch, commite junto com o primeiro PR, e
   esvazie o `next.md` do checkout principal. Assim a ordem fica durável no repositório e o canal
   não acumula arquivo solto.
5. **Ao terminar:** `docs/coordination/ROUNDS/<id>-<slug>.md` no formato do README de ROUNDS,
   BOARD atualizado, HANDOFF seção 0 atualizado.

## Por que existe

Duas sessões já abriram PR para a mesma coisa (o #1354 e o #1357, com um minuto de diferença). E o
coordenador apurou o estado lendo prosa escrita por outra sessão, que já mentiu oito vezes em um
único turno. Ordem em arquivo e registro em formato fixo resolvem os dois.
