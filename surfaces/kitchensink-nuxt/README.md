# Operator Kitchen Sink (`kitchensink-nuxt`)

Superfície interna de referência que estende `../operator-kit`. Ela exercita o mesmo
SSR, hidratação, BFF, proteção e shells das apps de operador, mas não é app operacional
nem participa da matriz PWA operacional. O catálogo e as fixtures vivem no kit; esta app
é apenas o consumidor real usado em desenvolvimento, teste visual e preview protegido.

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

O registro canônico declara `kind: "internal"`, `uses_operator_kit: true` e
`deployment: "preview"`. Assim, qualidade, lint, typecheck, build, guardrails do kit e
teste visual continuam obrigatórios, enquanto matriz PWA, grupos, ingress e deploy
operacional ficam proibidos. Um preview remoto deve usar serviço isolado e autenticação
da plataforma, além da permissão Django `backstage.view_operator_kitchen_sink`.
