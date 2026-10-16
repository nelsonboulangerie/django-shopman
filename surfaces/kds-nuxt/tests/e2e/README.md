# E2E do KDS (kds-nuxt)

Playwright **backend-independente**: o `mockBackend.mjs` ramifica pelo cookie `e2e_session`
que o BFF encaminha ao Django. Sem cookie → 403 nos endpoints de operador (aparece o gate
de login); com `e2e_session=authed` → sessão autenticada + estações + board vazio. O board
público do cliente (`/kds/cliente/`) responde 200 sempre, então `/pickup` renderiza sem
sessão. Um único mock+build cobre gate-de-login E telas de operador E o painel público.

```bash
npm run test:e2e
```

## O que cobre

- **guards.spec** — telas de operador atrás do gate; sessão autenticada → seletor de
  Estações + barra lateral do shell da suíte; `/pickup` (público) renderiza SEM sessão de operador e FORA do shell.
  (Sem teste de 404: `pages/[ref].vue` torna todo path de um segmento um ref de estação
  válido — não há 404 genérico, análogo ao POS view-única.)
- **resilience.spec** — `OfflineBanner` aparece/some com a rede.

## O que fica para o reviewer local (Django real)

Login efetivo, lock (Opção C), ações reais (iniciar e Pronto pelo botão do card, desfazer dentro da janela, recall), o beep
de novo ticket e o SSE ao vivo exigem a stack completa + gateway (SSE é same-origin).

## Prévia dos cards (sem Django)

O mesmo mock tem um modo de prévia (`KDS_MOCK_FIXTURE=preview`): toda requisição entra
autenticada e a estação `bancada` (preparo) serve os pedidos de
`previewFixtures.mjs` — curto, longo com observação e nota de cozinha, atrasado,
iFood, adicional, comanda antiga e o pedido de teste do iFood. Iniciar e Pronto
mudam o quadro; reiniciar volta ao começo.

```bash
npm run preview:cards          # mock :8799 + nuxt dev :3013
# http://127.0.0.1:3013/bancada
node tests/preview/capture.mjs http://127.0.0.1:3013 /tmp/kds-preview after
```

O `capture.mjs` fotografa os dois quadros com relógio fixo. **Não é baseline visual**
e não entra em gate nenhum: é a prévia que se mostra antes de subir.

## Portas

- App (build de produção do e2e): `127.0.0.1:3103` (distinta do dev server em `:3003`)
- Mock backend: `127.0.0.1:8798` (evita colidir com os mocks do Gestor `:8796`/Produção `:8797`)

## Matriz visual (fase 2)

```bash
npm run test:visual   # build de produção + mock de prévia; 390 e 1280, claro e escuro
```

Abre Estações, a bancada e o Painel de retirada na carga direta, reprova erro de página
e aviso de hidratação, e anexa as capturas ao relatório (sem baseline: retrato só pelo
browser da CI). Duas travas de desenho moram lá: na mesa a ordem visual dos tickets é a
ordem da fila (sem mosaico), e no celular o ato do pedido em foco está na ação na base.
Portas próprias (33019/38797), trocáveis por `KDS_VISUAL_APP_PORT`/`KDS_VISUAL_BACKEND_PORT`
(o e2e aceita `KDS_E2E_APP_PORT`/`KDS_E2E_MOCK_PORT`).
