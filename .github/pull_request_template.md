## O que muda

<!-- Descreva resumidamente o que esta PR faz e por quê. -->

## Checklist Omotenashi

- [ ] **Copy**: mudanças em texto UI usam `{% omotenashi KEY %}`, ou têm `{# copy-ok: <razão> #}` justificando a exceção.
- [ ] **Admin/Unfold**: backstage novo ou alterado passou `make admin`.
- [ ] **5 testes Omotenashi**: invisível (zero onclick/document.*), antecipação (dado conhecido pré-preenchido), ma (espaço em branco generoso), calor (tom acolhedor, sem formalidade), retorno (cliente recorrente recebe sinal de reconhecimento).
- [ ] **Acessibilidade**: contraste ≥ AAA em copy principal; touch targets ≥ 48 px; heading levels corretos (sem pulos de h1→h3).
- [ ] **Mobile-first**: testado em viewport 375 px (iPhone SE); nada quebrado em telas pequenas.
- [ ] **HTMX ↔ servidor / Alpine ↔ DOM**: zero `onclick=`, `onchange=`, `document.getElementById`, `classList.toggle/add/remove` em templates; toda comunicação com servidor via HTMX; todo estado local via Alpine.

## Atenção do revisor

<!-- Marque só o que se aplica; apague o resto. Cada linha aqui é uma armadilha
     que já custou trabalho neste repositório. -->

- [ ] **Migração nova** — confira colisão de numeração antes de abrir: `ls <app>/migrations | sed 's/_.*//' | sort | uniq -d`. Duas branches criando `0002` no mesmo app só acusam quando alguém roda `migrate`.
- [ ] **Muda dado de seed** — não aparece no alpha sem reseed. Diga aqui o que só aparece depois dele, e **não reseede por conta própria**: a autorização é do Pablo, por evento.
- [ ] **Muda contrato de projection** — regenere `contracts/projections/*.json` e commite os dois lados juntos; o front consome esse arquivo.
- [ ] **Exige ação humana no deploy** (variável nova, segredo, comando a rodar) — descreva o quê:
