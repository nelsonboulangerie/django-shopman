# Suíte de operador da Produção (Playwright, Django de verdade)

A Produção **compilada** contra o Django de uma pilha de pé, com as pessoas fazendo o que
fazem: a Gerente entra com senha e libera o dispositivo, quem opera o chão (a Cozinha) se
identifica na tela de bloqueio e digita o PIN no teclado da tela, e a cliente olha a loja
no celular. Nenhum estado nasce por API, Admin ou banco.

Regra da casa: `docs/coordination/ROUNDS/EXCELENCIA-base.md`, seção "Teste como um
operador de verdade". As jornadas a canonizar estão na seção 8 de
`docs/plans/EXCELENCIA-PRODUCAO-PLANO.md`. Os e2e de mock (`tests/e2e/`, `npm run
test:e2e`) seguem como estão: eles cobrem geometria e acessibilidade; esta suíte cobre o
gesto de verdade.

| Spec | Jornada | Papéis |
|---|---|---|
| `jp1-a-madrugada.spec.ts` | J-P1: a Gerente libera o tablet; a Cozinha entra com PIN, confirma o previsto do lote de hoje do Pain au Chocolat e o finaliza com 2 de perda e o motivo ("Assou demais"); a Gerente, com o PIN dela, confirma a Qualidade (lote com perda é exceção: "Confirmar assim"); a loja mostra o Pain au Chocolat "Pronto agora". Abre e finaliza o lote do dia, então roda **uma vez por seed** | Gerente e Cozinha (Produção, tablet 1024 px com toque) · Gerente com PIN (Produção, celular 375 px) · cliente (loja, 375 px) |
| `jp3-zerar-nao-cancela.spec.ts` | J-P3: a Cozinha corrige um lote planejado para 0 e lê "Cancelar lote é com o gerente." no lugar do botão (nada vai ao servidor); a Gerente, com o PIN dela, abre "Cancelar lote…" no Croissant Manteiga de hoje e lê "N un. encomendadas: M pedidos" e os pedidos antes do botão (tablet e celular), escolhe o motivo e cancela; no celular, tira do plano de amanhã a Focaccia do dia com o motivo escrito. Audita enquadramento e contraste (4,5) do que decide o gesto. Cancela os dois lotes, então roda **uma vez por seed**. A loja não entra: a variável `OPERATOR_STORE_URL` é exigida pela configuração, mas a jornada não a abre | Cozinha e Gerente com PIN (Produção, tablet 1024 px com toque) · Gerente com PIN (Produção, celular 375 px) |

Os papéis vêm de `shopman/shop/management/commands/setup_operators.py` (o `seed` roda o
comando): Gerente `joyce` (senha `admin`, PIN 1234), Cozinha `diofer` (PIN 1234). Nunca o
superusuário. Os gestos (entrar, travar, PIN) são os do operator-kit
(`surfaces/operator-kit/tests/support/operatorGestures.ts`); `support/operator.ts` guarda
só o que é da Produção.

## Subir a pilha

Exemplo com as portas do WP-F00 (Django `:8095`, Produção `:3196`, loja `:3197`, banco
`shopman_exc_f00`). Use as suas se outra pilha estiver rodando: confira com
`lsof -nP -iTCP:<porta> -sTCP:LISTEN`. Builds e a suíte seguram a trava de prévia da
máquina (`lockf /tmp/shopman-previa.lock …`).

1. **Ambiente do Django** (na raiz do repositório ou da worktree):

   ```bash
   export DATABASE_URL=postgres://localhost:5432/shopman_exc_f00
   export DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS='*' DJANGO_SECRET_KEY=dev-local-operador-1234567890
   export SHOPMAN_OTP_DELIVERY_CHAIN=console   # nenhum SMS
   export SHOPMAN_STOREFRONT_BASE_URL=http://127.0.0.1:3197 SHOPMAN_PRODUCTION_BASE_URL=http://127.0.0.1:3196
   export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3196,http://127.0.0.1:3197
   unset REDIS_URL
   ```

   Numa worktree, o `PYTHONPATH` precisa da worktree e de cada `packages/*` (o `.venv` da
   raiz aponta para a árvore principal). Se o Postgres local quebrar com
   `wait_c() got an unexpected keyword argument 'timeout'`, o `.venv` está com
   `psycopg-binary` atrás do `psycopg`: instale `psycopg-binary` na mesma versão com
   `pip install --no-deps --target <pasta>` e ponha a pasta na frente do `PYTHONPATH`, sem
   mexer no `.venv` compartilhado.

2. **Banco, seed, Django e worker**:

   ```bash
   createdb shopman_exc_f00
   .venv/bin/python manage.py migrate --noinput
   SHOPMAN_STAGING_AUTOPILOT=true .venv/bin/python manage.py seed --flush   # loja aberta 24h
   .venv/bin/python manage.py runserver 127.0.0.1:8095 --noreload > /tmp/producao-django.log 2>&1 &
   .venv/bin/python manage.py process_directives --watch > /tmp/producao-worker.log 2>&1 &
   ```

   O `runserver` e o worker sobem SEM `SHOPMAN_STAGING_AUTOPILOT`: o piloto automático
   daria os gestos que a jornada quer ver a pessoa dar.

   O seed planeja para hoje os lotes do Croissant, da Focaccia do dia e do Pain au
   Chocolat; a J-P1 usa o do Pain au Chocolat, que as jornadas do Gestor não tocam (a J6
   cancela o de amanhã). Para rodar a J-P1 de novo, rode o seed de novo.

3. **A loja e a Produção compiladas** (`nuxt dev` recarrega sozinho e derruba jornada
   longa). A loja sobe à parte; a Produção só se compila, quem a sobe é a suíte, na porta
   `OPERATOR_PRODUCTION_PORT` (padrão 3196), com a exceção declarada de teste do envelope
   estrito (`NUXT_SHOPMAN_ENVIRONMENT=test` e `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`, as
   mesmas dos e2e de mock):

   ```bash
   (cd surfaces/storefront-nuxt && npx nuxt build && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8095 HOST=127.0.0.1 PORT=3197 node .output/server/index.mjs &)
   (cd surfaces/production-nuxt && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8095 NUXT_SHOPMAN_ENVIRONMENT=local npx nuxt build)
   ```

## Rodar

```bash
cd surfaces/production-nuxt
OPERATOR_DJANGO_URL=http://127.0.0.1:8095 \
OPERATOR_STORE_URL=http://127.0.0.1:3197 \
npm run test:operator
```

Sem essas variáveis, ou sem a Produção compilada, a suíte recusa rodar e diz o que falta.
As capturas de cada gesto (`01-tablet-liberado.png`, …) vão para
`test-results/operator/` (fora do git).

## Armadilhas medidas

- **Cookies em `127.0.0.1` valem para todas as portas.** Loja e Produção dividem o pote;
  por isso cada papel e cada dispositivo têm o próprio contexto de navegador.
- **Na Produção o PIN entra no quarto dígito.** O gesto do kit espera o "4 de no mínimo" e
  o Confirmar do PDV; aqui a tela de bloqueio sai sozinha. `support/operator.ts` faz o
  gesto da Produção e confirma só se a tela pedir.
- **O tablet deitado tem toque.** Com toque e 1024 px ou mais, "Confirmar" abre o painel
  encaixado "Quanto está previsto?" à direita; sem toque, um modal. A J-P1 usa o tablet de
  verdade (`support/stack.ts`, `device("tablet")`).
- **O seed já põe Pain au Chocolat na vitrine.** A loja mostra "Pronto agora" antes e
  depois da jornada; a parte da loja prova que o lote finalizado não tira o produto da
  vitrine, não a virada de "indisponível" para "disponível" (#3404).
