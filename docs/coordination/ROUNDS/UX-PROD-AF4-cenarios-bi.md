# UX-PROD-AF4 · Cenários salvos do B.I. falam "aproveitamento"

Branch `claude/ux-prod-af4-cenarios-bi`. Seguimento do PR #1439 (UX-PROD-AF2), que
renomeou a métrica `yield_percent` do explorador para "Aproveitamento" e deixou de fora,
deliberadamente, os cenários já salvos pelos gestores (dado, não código).

Decisão do dono (03/10/2026): os cenários salvos acompanham o vocabulário novo.

## O que muda

- `shopman/backstage/migrations/0082_cenarios_de_bi_falam_aproveitamento.py`: migração de
  dados em `BIView` (o cenário salvo do explorador: `name` + `config {metric, by, by2, window}`).
- `shopman/backstage/tests/test_cenarios_de_bi_aproveitamento.py`: critério, colisão,
  volta, banco vazio, e a conferência de que o exemplo do bi-nuxt já diz
  "Aproveitamento por receita".

## Critério

- Só cenários com `config.metric == "yield_percent"` (a única referência a métrica no
  cenário; `by`/`by2` são dimensões).
- Troca a palavra inteira "Rendimento"/"rendimento" (e o plural) por
  "Aproveitamento"/"aproveitamento", preservando a maiúscula inicial. O resto do nome é do
  gestor.
- Pula quando o nome novo colide com outro cenário do mesmo dono (restrição
  `backstage_biview_owner_name`) ou passa de 80 caracteres.
- Volta pela mesma regra, ao contrário. `BIView` não tem descrição nem título além de `name`.

## Fora do escopo

- `BIScenarioReport` (cenários gerados pela IA): append-only por desenho, é o registro do
  que a IA devolveu naquele dia; reescrever seria adulterar o relatório.
- "Rendimento" da ficha técnica e da massa: não mora em `BIView`.
- Seed e fixtures: não criam `BIView`; o exemplo do bi-nuxt já foi trocado no #1439.
