# bi-nuxt — B.I. do gestor

Leitura analítica cross-suite (ADR-021): produção (tempo real de forno,
rendimento, perdas, qualidade), vendas, caixa e clientes. Consome
`GET /api/v1/backstage/bi/*` via BFF Nitro (operator-kit), gate
`backstage.view_bi`.

- Dev: `npm run dev` → http://127.0.0.1:3007 (Django em :8000).
- Contrato TS gerado: `python manage.py export_bi_schema` (teste de drift no backstage).
- Gráficos: HTML/CSS monocromáticos, cor só funcional (quebra de caixa negativa
  = destructive); toda métrica de forno declara cobertura.
