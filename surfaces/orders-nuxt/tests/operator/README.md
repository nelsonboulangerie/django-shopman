# Suíte de operador do Gestor (Playwright, Django de verdade)

O Gestor **compilado** contra o Django de uma pilha de pé, com as pessoas fazendo o que
fazem: a Gerente entra com senha e abre o dispositivo, o Caixa se identifica na tela de
bloqueio e digita o PIN no teclado da tela, o cliente novo pede pela loja e paga, a Cozinha
dá Pronto na estação. Nenhum estado nasce por API, Admin ou banco.

Regra da casa: `docs/coordination/ROUNDS/EXCELENCIA-base.md`, seção "Teste como um
operador de verdade". As jornadas a canonizar estão na seção 8 de
`docs/plans/EXCELENCIA-GESTOR-PLANO.md`.

| Spec | Jornada | Papéis |
|---|---|---|
| `j1-pedido-de-hoje.spec.ts` | J1: pedido de retirada para hoje, de ponta a ponta | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) · Cozinha (estação, 1366 px) |
| `j2-recusar-com-motivo.spec.ts` | J2: recusar um pedido pago, lendo o destino do dinheiro antes de confirmar | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `j3-aceitar-a-encomenda-com-o-dia.spec.ts` | J3: a cliente encomenda para amanhã e paga; o Caixa lê "Encomenda · Amanhã…" no Painel, na Fila, na Tabela e no sino, e aceita | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `j5-cancelar-encomenda-paga.spec.ts` | J5: cancelar a encomenda paga antes do preparo e ver o estorno ("Estornado") | cliente novo (loja, 375 px) · Gerente com PIN (Gestor, 1366 px) |
| `j7-achar-o-pedido-de-ontem.spec.ts` | J7: achar o pedido de ontem pelo nome, ampliando o período; pede a pilha semeada na véspera, ou num dia em que a cliente ainda não tenha pedido concluído | Gerente com PIN (Gestor, 1366 px) |
| `j8-quem-so-expede-abre-o-sino.spec.ts` | J8: quem só expede abre um aviso de pedido no sino e lê por que o detalhe não abre (#2879) | cliente novo (loja, 375 px) · Gerente e Cozinha (Gestor, 1366 px) |
| `g07-avisar-o-cliente.spec.ts` | WP-G07: avisar o cliente com um toque (vai atrasar, faltou um item), lendo a mensagem antes de enviar; o recibo que falhou traz o WhatsApp com o mesmo texto | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 e 375 px) |

Os papéis vêm de `shopman/shop/management/commands/setup_operators.py` (o `seed` roda o
comando): Gerente `joyce` (senha `admin`, PIN 1234), Caixa `fran` (PIN 1234), Cozinha
`diofer` (PIN 1234). Nunca o superusuário.

## Subir a pilha

Exemplo com as portas do WP-G00 (Django `:8062`, loja `:3180`, Cozinha `:3183`, Gestor
`:3184`, banco `shopman_exc_g00`). Use as suas se outra pilha estiver rodando: confira com
`lsof -nP -iTCP:<porta> -sTCP:LISTEN`.

1. **Ambiente do Django** (na raiz do repositório ou da worktree):

   ```bash
   export DATABASE_URL=postgres://localhost:5432/shopman_exc_g00
   export DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS='*' DJANGO_SECRET_KEY=dev-local-operador-1234567890
   export SHOPMAN_OTP_DELIVERY_CHAIN=console   # código de entrada só no log, nenhum SMS
   export SHOPMAN_STOREFRONT_BASE_URL=http://127.0.0.1:3180 SHOPMAN_KDS_BASE_URL=http://127.0.0.1:3183 SHOPMAN_ORDERS_BASE_URL=http://127.0.0.1:3184
   export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3180,http://127.0.0.1:3183,http://127.0.0.1:3184
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
   createdb shopman_exc_g00
   .venv/bin/python manage.py migrate --noinput
   SHOPMAN_STAGING_AUTOPILOT=true .venv/bin/python manage.py seed --flush   # loja aberta 24h
   .venv/bin/python manage.py runserver 127.0.0.1:8062 --noreload > /tmp/operador-django.log 2>&1 &
   .venv/bin/python manage.py process_directives --watch > /tmp/operador-worker.log 2>&1 &
   ```

   O log do `runserver` é onde a loja escreve o código de entrada: a suíte o lê de lá.

   **Expediente.** A J1 pede retirada para hoje, então a loja tem de estar aberta agora.
   O seed com `SHOPMAN_STAGING_AUTOPILOT=true` abre a loja 24h (é o único efeito dele no
   seed); o `runserver` e o worker sobem SEM essa variável, senão o piloto automático
   daria os passos que a jornada quer ver o Caixa dar. Sem isso, a suíte só passa no
   horário real da casa e falha dizendo que a loja está fechada.

3. **Loja e Cozinha compiladas** (`nuxt dev` recarrega sozinho e derruba jornada longa):

   ```bash
   (cd surfaces/storefront-nuxt && npx nuxt build && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 HOST=127.0.0.1 PORT=3180 node .output/server/index.mjs &)
   (cd surfaces/kds-nuxt && npx nuxt build && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 HOST=127.0.0.1 PORT=3183 node .output/server/index.mjs &)
   ```

4. **O Gestor** só se compila; quem o sobe é a suíte, na porta `OPERATOR_GESTOR_PORT`
   (padrão 3184):

   ```bash
   cd surfaces/orders-nuxt && npx nuxt build
   ```

## Rodar

```bash
cd surfaces/orders-nuxt
OPERATOR_DJANGO_URL=http://127.0.0.1:8062 \
OPERATOR_STORE_URL=http://127.0.0.1:3180 \
OPERATOR_KITCHEN_URL=http://127.0.0.1:3183 \
OPERATOR_DJANGO_LOG=/tmp/operador-django.log \
npm run test:operator
```

Sem essas variáveis a suíte recusa rodar e diz o que falta. As capturas de cada passo vão
para `test-results/operator/` (fora do git).

A suíte roda de novo sem reseed: cada execução cria um cliente novo (telefone sorteado) e
um dispositivo novo (contexto de navegador limpo).

## Armadilhas medidas

- **Cookies em `127.0.0.1` valem para todas as portas.** Loja, Gestor e Cozinha dividem o
  pote; por isso cada papel tem o próprio contexto de navegador. Não junte dois papéis no
  mesmo contexto.
- **Digitar antes da hidratação perde o texto.** Os helpers esperam a tela assentar antes
  de preencher o login.
- **Sem relógio de teste nem adapter fiscal na pilha**: virada do dia, encomenda no dia e
  estados de nota não se exercitam aqui (J4 vive em teste de projeção e componente).
