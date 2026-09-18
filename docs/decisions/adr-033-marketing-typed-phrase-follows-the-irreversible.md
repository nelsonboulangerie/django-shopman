# ADR-033 — A frase digitada segue o que não tem desfazer

**Status:** Aceito em 2026-09-18
**Emenda:** [ADR-032](adr-032-marketing-ceremony-threshold-is-proportional.md), cujo
limiar proporcional continua valendo inteiro — ele só deixa de governar a **frase** e
passa a governar apenas o **resto** da cerimônia. Não mexe na
[ADR-031](adr-031-marketing-ceremony-proportional-to-consequence.md): o `fire` segue sem
cerimônia nenhuma.

## Contexto

A queixa que abriu esta frente foi, nas palavras do dono: o caminho era *"extremamente
moroso E pedia a frase 2 vezes"* — uma no disparo, que só cria um rascunho em revisão, e
outra na aprovação, pelo mesmo envio. A ADR-031 leu isso como "a frase é cara demais para
o disparo pequeno" e tirou a frase de tudo que estivesse abaixo do limiar.

Era meia leitura. O dono corrigiu: *"Não acho problema pedir a frase no ato final. Só que
tudo já era extremamente moroso e pedia a frase 2 vezes!"*

**A duplicação era o pecado, não a frase.** Cobrar duas vezes pelo mesmo envio é o
defeito; cobrar uma vez, no ato que entrega, é o ritual fazendo o trabalho dele.

E havia um segundo erro embutido: com o limiar governando a frase, mandar mensagem para
uma pessoa passava com um toque. Uma mensagem para uma pessoa é pequena em volume e
**total** em irreversibilidade — ela chega, e não volta.

## Decisão

> **O atrito segue o que não tem desfazer.**

- **Saiu mensagem direta** (`direct_message_recipient_count > 0`) → `confirmation_mode`
  é `typed` **sempre**, com a frase `ENVIAR <pessoas>`. Uma pessoa ou dez mil: digita-se.
- **O `step_up` continua governado pelo limiar da ADR-032** — nenhum abaixo dele, senha a
  partir dele, TOTP + duplo controle a partir do múltiplo. Quem aperta aí é o **tamanho**.
- **Só postagem** → resumo + um toque, qualquer que seja o número de plataformas.
  Inalterado. Postagem se apaga, não custa por pessoa, e o limiar conta PESSOAS: aplicá-lo
  a murais repetiria exatamente o defeito que a ADR-032 corrigiu.
- **Misto** → manda a parte de mensagem, como já mandava.
- **`fire`** → nenhuma cerimônia. Inalterado. É ele que evitava a duplicação, e é por isso
  que a frase do ato final pode existir sem pesar duas vezes.

Em uma linha: **a irreversibilidade manda na frase; o tamanho manda no resto.**

### A frase do disparo misto

O botão do caso só-mensagem diz "Enviar agora" e a frase é `ENVIAR <pessoas>` — casam. No
**misto** o botão diz "Disparar agora", e a frase continua sendo `ENVIAR <pessoas>`:
o que se digita é o **número irreversível**, não o rótulo do ato. Digitar "DISPARAR 502"
pediria ao gestor que confirmasse uma soma de pessoas com murais — a grandeza que a
ADR-032 separou justamente para nunca mais aparecer numa decisão. A tela explica a
diferença; a frase confirma o que não volta.

Vocabulário, fechado com o dono: objeto = **anúncio**; atos = **enviar** (mensagem),
**publicar** (postagem), **disparar** (os dois), **agendar**; resultados = **mensagem**
(direta) e **postagem** (pública). "Publicação" saiu.

### O servidor explica por que pediu

O desafio de confirmação ganha `ceremony_reason`:

- `"direct_message"` — a frase foi pedida porque sai mensagem;
- `""` — nenhuma frase foi pedida.

A tela poderia deduzir isso de `direct_message_count`, mas aí o motivo passaria a morar no
navegador — e este módulo existe para que a política, e a explicação dela, sejam do
servidor. O motivo da **senha** é outro e continua legível em `step_up`/`dual_control`
contra `direct_message_count` e `ceremony_threshold`: ali quem apertou foi o tamanho.

## Consequências

O caminho de um teste para uma pessoa volta a ter uma frase digitada — uma, no ato que
entrega, e nenhuma senha. O que não volta é a duplicação: preparar o rascunho continua
custando zero.

Um efeito colateral desejado: reenviar uma entrega falha (`retry_delivery`) para uma única
pessoa também passa a pedir a frase, porque reenviar é enviar. Reconciliar
(`reconcile_delivery`) não — é consulta, não reenvio, e segue no resumo com TOTP, que é
sobre quem pode olhar, não sobre o que sai.

Nada mais foi endurecido nem afrouxado: RBAC, token de uso único, CAS, idempotência,
comprovante, congelamento, quota diária e teto por comando continuam como estavam.

## Referências

- `shopman/shop/services/marketing_security.py` — `requirement_for`, `_ceremony_reason`
- `shopman/shop/tests/test_marketing_security.py` — um caso por eixo, para que nenhuma das
  duas regras fique sem dono
- `docs/reference/marketing-surface-contract.md`
