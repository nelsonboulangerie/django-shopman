# Baselines visuais e o tema compartilhado do operator-kit

O `operator-kit` é uma layer Nuxt consumida por `extends`. O tema que ele define não
pertence ao kit: pertence a toda app que o herda. Este documento é o processo que
liga uma mudança de tema à regeneração das baselines das consumidoras, e o gate que
se recusa a deixar as duas coisas separadas.

## O problema, medido

As baselines visuais são por app (`surfaces/<app>/tests/visual/baselines/`), mas o
tema é um só. Quando o tema do kit muda, a MESMA alteração reaparece nas baselines
das consumidoras sem que ninguém tenha tocado nelas: um `app.config.ts` novo no kit
deixou quatro retratos de Marketing diferentes e o job `Marketing — cadeia completa`
vermelho por um PR que não era de Marketing.

Consumidoras hoje (derivadas do disco, não escritas à mão):

- `marketing-nuxt` — `surfaces/marketing-nuxt/tests/visual/baselines/`;
- `pos-nuxt` — `surfaces/pos-nuxt/tests/visual/baselines/`.

## O contrato e o gate

O aceite do tema vive em
[`operator-theme-baseline-contract.json`](operator-theme-baseline-contract.json). Ele
registra as fontes do tema, as apps consumidoras e um `themeFingerprint` (sha256 do
conteúdo das fontes). O gate
[`scripts/check_theme_baseline_contract.py`](../../scripts/check_theme_baseline_contract.py)
reprova quando:

1. aparece arquivo de tema fora do contrato (arquivo novo em
   `surfaces/operator-kit/app/assets/css/` ou `app.config.ts`);
2. o fingerprint do tema difere do aceito — o tema mudou e o aceite não;
3. uma app consumidora declarada perdeu o diretório de baselines.

Rode com:

    make theme-baselines     # gate (também roda em `make test-operator-ux` e na CI)

As fontes cobertas hoje: `surfaces/operator-kit/app/app.config.ts` e todo
`surfaces/operator-kit/app/assets/css/*.css`. Mudança de componente ou de
`nuxt.config.ts` também pode mexer no retrato; o contrato não a captura, e a regra
abaixo vale para ela também.

## Processo de regeneração (o único aceito)

1. **Mude o tema no PR.** Não regenere baseline em PR separado.
2. **Gere os retratos no navegador pinado da CI** (`macos-15` + Chromium do
   Playwright). A baseline canônica só nasce ali; rasterização de outra máquina não
   promove. Quando o download local do Chromium estiver bloqueado, use o artefato
   `marketing-browser-gates` da execução oficial e promova os `actual.png`
   inspecionados — foi o que o `V6-SEG-MKT-VISUAL-GATE` fez.
3. **Separe mudança intencional de regressão funcional.** No V6-SEG, das 62 falhas,
   a maioria era retrato anterior e contrato de teste velho, e havia uma regressão
   real (`Criar cupom` inalcançável no celular). Baseline regerada sem essa separação
   esconde a regressão em vez de registrá-la.
4. **Revise o antes/depois com o dono** e commite as baselines NO MESMO PR do tema.
5. **Regrave o aceite:**

       make theme-baselines-accept owner="<quem aceitou>"

   `owner` é obrigatório e fica no contrato. O aceite não regenera baseline: ele
   registra que um humano revisou o antes/depois.

## Regras curtas

- **Nunca regenerar baseline cega.** "O CI ficou verde" não é motivo para trocar um
  retrato; o motivo é a mudança de tema revisada.
- **Tema e baseline no mesmo PR.** PR de tema que não toca baseline fica vermelho no
  gate, de propósito.
- **Uma fonte de verdade por retrato.** Se o retrato mudou, pelo menos uma linha de
  tema ou de componente mudou. Se nenhuma mudou, o retrato está errado.
- **Aceite com nome.** `make theme-baselines-accept owner=` sem dono é recusado.

## Onde o audit entra (e onde não entra)

O `npm audit` das superfícies NÃO mora no job de cada app. Ele vive no job dedicado
`Supply chain — npm audit` do `surfaces-gate.yml`, com a allowlist versionada em
[`surfaces/npm-audit-allowlist.json`](../../surfaces/npm-audit-allowlist.json). O
histórico de por que ele saiu do job de Marketing está em
[`docs/reports/2026-10-06-marketing-ci-health.md`](../reports/2026-10-06-marketing-ci-health.md).
