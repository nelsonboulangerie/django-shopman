# Operator Kitchen Sink (`kitchensink-nuxt`)

Superfície de referência gerada por `make new-surface`. Ela estende `../operator-kit`
e executa o mesmo SSR, hidratação, BFF, proteção, shells e PWA das apps de operador.
O catálogo e as fixtures vivem no kit; esta app é apenas o consumidor real usado em
desenvolvimento, teste visual e preview protegido.

```bash
npm ci && npm run dev   # http://127.0.0.1:3009
```

Use `?state=<cenário>` para os estados determinísticos e `?mode=operational` para a
receita de operação contínua. A matriz completa, o léxico e as regras de consumo estão
em [`../../docs/reference/operator-kitchen-sink.md`](../../docs/reference/operator-kitchen-sink.md).

```bash
npm test
npm run typecheck
npm run build
npm run test:visual
```

O registro `deployment: "preview"` impede que esta superfície entre nos grupos de
produção. Um preview remoto deve usar serviço isolado e autenticação da plataforma,
além da permissão Django `backstage.view_operator_kitchen_sink`.
