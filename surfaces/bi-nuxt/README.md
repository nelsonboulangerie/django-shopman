# bi-nuxt — B.I. do gestor

Leitura analítica cross-suite (ADR-021): produção ("Sobrou ou faltou?" do dia,
tempo real de forno, aproveitamento, perdas, qualidade), vendas, caixa e clientes. Consome
`GET /api/v1/backstage/bi/*` via BFF Nitro (operator-kit), gate
`backstage.view_bi`.

- Dev: `npm run dev` → http://127.0.0.1:3007 (Django em :8000).
- Contrato TS gerado: `python manage.py export_bi_schema` (teste de drift no backstage).
- Gráficos: HTML/CSS no latão da suíte (`primary`), traço de comparação na cor do
  texto, cor de estado só funcional (faltou = destructive, sobrou = warning, na
  medida = success); toda métrica de forno declara cobertura.
- Casca: a canônica do kit (`OperatorSuiteShell`, como o Gestor), sem a pele legada
  `data-suite`: rail de ícones com as oito leituras do tablet deitado para cima, barra
  de seções com "Mais" no celular.
- Visual (V4-BI): cabeçalho de uma linha em toda tela com a PERGUNTA como título e,
  logo abaixo, "A resposta" em uma frase (prévia `docs/plans/suite-ux-v2/v4/bi-sobra.jpg`).
