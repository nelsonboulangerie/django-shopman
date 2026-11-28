# E2E (Playwright) — storefront

Dois níveis, por dependência de dados:

## 1. Independentes de backend (rodam aqui, no CI)

`resilience.spec.ts` e `guards.spec.ts` cobrem comportamentos do app que não
precisam de dados de negócio: shell degradado com backend vazio, banner offline
(reconexão), guard de `/conta` (redireciona ao login), página 404 (noindex), e o
documento com cookie de sessão saindo `private, no-store` em qualquer rota (#3474).

Sobem automaticamente um **mock backend** (`mockBackend.mjs`, respostas `{}`
rápidas) e o `nuxt preview` apontado a ele.

```bash
npm run build          # e2e roda sobre o preview de produção
npm run test:e2e
```

## 2. Fluxo crítico com dados no CI: o E2E do Django

O caminho do Dia 1 (PDP → sacola → OTP → checkout → pedido → acompanhamento)
precisa do Django real semeado, e por isso não vive aqui. Ele está em
`shopman/shop/tests/e2e/test_storefront_e2e.py`, dirigido por esta loja Nuxt
(build de produção) contra o Django semeado, no job **Storefront E2E
(Playwright)** do `omotenashi-gate.yml`, em todo PR e na fila de merge:

- `test_11`: retirada com Pix, e o pedido aparece na fila do operador.
- `test_12`: **entrega com cartão**, e o pedido aparece no acompanhamento
  (`/pedido/<ref>`) já com o pagamento autorizado. O cartão passa pelo adapter
  `payment_stripe` de produção contra um Stripe falso local
  (`shopman/shop/tests/e2e/fake_stripe.py`): sem rede e sem credencial.
- `test_experience_e2e.py` (OC-21, X14): a versão de experimento que o servidor
  decidiu. A coorte nasce pelo servidor (`seed_experience.py`, uma `RuleConfig` com
  `CLI-003` na coorte `internal`, gravada antes de o Django subir), nunca por query:
  fora da coorte e anônimo veem `a`; na coorte, `b`, sem alternar na recarga, com o
  documento e o shell saindo `private, no-store`. Documento com sessão (#3474): com
  a cliente logada (`CLI-005`), cardápio, produto, páginas legais e home saem
  `private, no-store`; anônimas (`TestSessionDocumentIsNeverShared`), as mesmas
  páginas seguem sem `no-store`.

Para rodar localmente, da raiz do repositório:

```bash
make storefront-e2e                       # seed + Django + loja + Stripe falso
make storefront-e2e args="-k test_12"     # só o Dia 1
make storefront-e2e args="-k Experience"  # só a versão de experimento (OC-21)
```

O antigo `criticalFlow.spec.ts` (sempre `skip`) foi apagado: o fluxo que ele
prometia é o `test_12`. Os dois testes param antes do aceite; a jornada inteira, com a
operadora aceitando pela tela, é a J1 da seção 3.

## 3. Jornadas da cliente de verdade (`tests/journeys/`, contra uma pilha de pé)

A loja **compilada** e o Gestor compilado contra o Django de uma pilha já de pé, com as
pessoas fazendo o que fazem: a cliente nova abre o cardápio, põe um item na sacola, entra
pelo código que chegou, escolhe retirada para hoje, paga o Pix simulado e fica olhando o
acompanhamento; a operadora entra no Gestor com o usuário e a senha dela e aceita; a tela da
cliente muda sozinha. Nenhum estado nasce por API, Admin ou banco. Regra da casa:
`docs/coordination/ROUNDS/EXCELENCIA-base.md`, seção "Teste como um operador de verdade".
As jornadas a canonizar estão na seção 8 de `docs/plans/EXCELENCIA-STOREFRONT-PLANO.md`.

| Spec | Jornada | Papéis |
|---|---|---|
| `j1-retirada-hoje-pix.spec.ts` | J1: retirada para hoje com Pix, do cardápio ao aceite | cliente nova (375 e 1366 px) · Gerente no Gestor (1366 px) |
| `j3-loja-viva.spec.ts` | J3: o produto que acaba muda sozinho na tela de quem está olhando (pelo aviso da vitrine, pela consulta de reserva e pela recusa ao tocar) | duas clientes na loja: A olhando (375 e 1366 px) · B levando as últimas unidades (1366 px). Não usa o Gestor, mas a suíte pede a variável dele mesmo assim |
| `x9-tipografia-decisiva.spec.ts` | X9 e X11 (OC-30): em home, cardápio, produto, entrar, sacola, finalizar, acompanhamento e conta, todo `[data-decisive]` tem 14 px e contraste AA (tema claro e escuro), todo `.shop-reading` tem 16 px, e com a fonte raiz a 200 % nenhum decisivo nem ação some ou é cortado. A medida mora em `support/typographyAudit.mjs` | cliente nova, medida a 320, 375 e 390 px (projeto 375) e a 1366 px. Não usa o Gestor |

A suíte **não sobe servidor nenhum** e recusa rodar sem as três variáveis abaixo. Cada
projeto (`cliente-375`, `cliente-1366`) é uma cliente nova, com telefone sorteado, e faz um
pedido de verdade na pilha. A operadora é a Gerente `joyce` (senha `admin`) do elenco de dev
(`shopman/shop/management/commands/setup_operators.py`, que o `seed` roda). Nunca o
superusuário.

### Subir a pilha

O exemplo usa as portas e o banco do WP-L00 (Django `:8090`, loja `:3190`, Gestor `:3194`,
banco `shopman_exc_l00`). Outra sessão pode estar com as suas: confira com
`lsof -nP -iTCP:<porta> -sTCP:LISTEN` e troque as portas em todos os lugares.

Use **hosts próprios `*.localhost`**, não `127.0.0.1`: o navegador divide os cookies de um
host entre todas as portas, e a sessão de outra pilha (ou do Gestor) apaga a da loja. O
Chromium resolve `*.localhost` para o próprio computador sem mexer no `/etc/hosts`.

1. **Ambiente do Django** (na raiz do repositório ou da worktree; Node 22 no `PATH`):

   ```bash
   export DATABASE_URL=postgres://localhost:5432/shopman_exc_l00
   export DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS='*' DJANGO_SECRET_KEY=dev-local-jornadas-1234567890
   unset REDIS_URL
   # O código de entrada sai num arquivo, como o SMS da cliente (E2EFileSender).
   mkdir -p /tmp/shopman-jornadas && chmod 700 /tmp/shopman-jornadas
   export SHOPMAN_E2E_OTP_FILE=/tmp/shopman-jornadas/code
   export DOORMAN_MESSAGE_SENDER_CLASS=shopman.shop.tests.e2e.otp_sender.E2EFileSender
   export SHOPMAN_OTP_DELIVERY_CHAIN=""
   # O settings do harness (sem limite de taxa por IP) exige as chaves falsas do Stripe.
   # A J1 é Pix: o Stripe falso não precisa estar de pé.
   export SHOPMAN_E2E_STRIPE_API_BASE=http://127.0.0.1:12190
   export STRIPE_SECRET_KEY=sk_test_e2e_fake_local_only STRIPE_PUBLISHABLE_KEY=pk_test_e2e_fake_local_only STRIPE_WEBHOOK_SECRET=whsec_e2e_fake_local_only
   export SHOPMAN_STOREFRONT_BASE_URL=http://loja.l00.localhost:3190
   export SHOPMAN_ORDERS_BASE_URL=http://gestor.l00.localhost:3194
   export CSRF_TRUSTED_ORIGINS=http://loja.l00.localhost:3190,http://gestor.l00.localhost:3194
   ```

   Numa worktree, o `PYTHONPATH` precisa da worktree e de cada `packages/*` (o `.venv` da
   raiz aponta para a árvore principal):
   `PP="$PWD"; for d in "$PWD"/packages/*/; do PP="$PP:${d%/}"; done; export PYTHONPATH="$PP"`.
   Se o Postgres local quebrar com `wait_c() got an unexpected keyword argument 'timeout'`,
   o `.venv` está com `psycopg-binary` atrás do `psycopg`: instale a mesma versão com
   `.venv/bin/python -m pip install --no-deps --target <pasta> "psycopg-binary==<versão do psycopg>"`
   e ponha a pasta na frente do `PYTHONPATH`, sem mexer no `.venv` compartilhado
   (`PSYCOPG_IMPL=python` também serve, mas é lento demais para o seed).

2. **Banco e seed, com a loja aberta a qualquer hora.** A J1 é "retirada para hoje": com o
   horário real da casa (9h às 18h), a jornada só roda de dia. O mesmo interruptor do
   piloto de staging abre a loja 24/7 no seed; restrito a um canal que não existe, ele
   não aceita nenhum pedido sozinho. Só o seed o recebe: o `runserver` sobe sem ele, e
   quem aceita é a operadora.

   ```bash
   createdb shopman_exc_l00
   .venv/bin/python manage.py migrate --noinput
   SHOPMAN_STAGING_AUTOPILOT=true SHOPMAN_STAGING_AUTOPILOT_CHANNELS=nenhum-canal \
     .venv/bin/python manage.py seed --flush --profile qa
   ```

   Use o perfil `qa`: o `demo` não termina numa máquina carregada. O `qa` deixa o
   Croissant pronto na vitrine, que é o item da J1.

3. **Django e worker de directives**, com o settings do harness:

   ```bash
   DJANGO_SETTINGS_MODULE=shopman.shop.tests.e2e.settings_e2e \
     .venv/bin/python manage.py runserver 127.0.0.1:8090 --noreload > /tmp/shopman-jornadas/django.log 2>&1 &
   DJANGO_SETTINGS_MODULE=shopman.shop.tests.e2e.settings_e2e \
     .venv/bin/python manage.py process_directives --watch > /tmp/shopman-jornadas/worker.log 2>&1 &
   ```

4. **Loja e Gestor compilados** (`nuxt dev` recarrega sozinho e derruba jornada longa;
   rode `npm ci` de verdade em `surfaces/operator-kit`, `surfaces/storefront-nuxt` e
   `surfaces/orders-nuxt` antes, numa worktree também):

   ```bash
   (cd surfaces/storefront-nuxt && npx nuxt build)
   (cd surfaces/orders-nuxt && npx nuxt build)
   (cd surfaces/storefront-nuxt && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8090 HOST=127.0.0.1 PORT=3190 node .output/server/index.mjs > /tmp/shopman-jornadas/loja.log 2>&1 &)
   (cd surfaces/orders-nuxt && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8090 NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:8090 HOST=127.0.0.1 PORT=3194 node .output/server/index.mjs > /tmp/shopman-jornadas/gestor.log 2>&1 &)
   ```

### Rodar

```bash
cd surfaces/storefront-nuxt
JOURNEY_STORE_URL=http://loja.l00.localhost:3190 \
JOURNEY_GESTOR_URL=http://gestor.l00.localhost:3194 \
JOURNEY_OTP_FILE=/tmp/shopman-jornadas/code \
npm run test:journeys
```

Só uma largura: `npm run test:journeys -- --project=cliente-375`. As capturas de cada passo
ficam em `test-results/journeys/` e no relatório (`--reporter=html`).

**J9 (um toque, uma reserva) precisa do proxy lento.** Ele fica entre a loja e o Django só
na pilha de teste e atrasa UMA resposta a pedido da jornada, para ela passar do prazo do
BFF. A loja aponta para o proxy, e o proxy, para o Django:

```bash
(cd surfaces/storefront-nuxt && SLOW_PROXY_PORT=8091 SLOW_PROXY_TARGET=http://127.0.0.1:8090 node tests/journeys/support/slow-proxy.mjs > /tmp/shopman-jornadas/proxy.log 2>&1 &)
(cd surfaces/storefront-nuxt && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8091 HOST=127.0.0.1 PORT=3190 node .output/server/index.mjs > /tmp/shopman-jornadas/loja.log 2>&1 &)
```

e a jornada recebe a porta de controle: `JOURNEY_PROXY_CONTROL=http://127.0.0.1:8091`. Sem
essa variável, a J9 pula e diz por quê. As outras jornadas não notam o proxy.

**J14 (entrar pelo WhatsApp) precisa do ManyChat falso** (`shopman/shop/tests/e2e/fake_manychat.py`,
#3272). A resposta da loja ("Liberar o Chrome", "Encerrar acesso") sai pelo adapter de
produção e cai nele, que a guarda; a jornada lê os botões em `GET /__sent?subscriber=<id>`.
O Django e o worker sobem com `MANYCHAT_API_BASE` apontando para ele (o `settings_e2e` põe o
token falso e troca o endereço do resolvedor de assinantes do Guestman, que acha ou cria o
contato do telefone: o aviso do pedido de quem entrou por código também chega nele, e a
jornada o lê em `GET /__sent?phone=<dígitos>`, #3282), e a jornada recebe o endereço e o do
Django:

```bash
.venv/bin/python -m shopman.shop.tests.e2e.fake_manychat --port 12191 > /tmp/shopman-jornadas/manychat.log 2>&1 &
export MANYCHAT_API_BASE=http://127.0.0.1:12191/fb   # antes do runserver e do worker
# na jornada: JOURNEY_MANYCHAT_URL=http://127.0.0.1:12191 JOURNEY_DJANGO_URL=http://127.0.0.1:8090
```

O `scripts/run_storefront_journeys.sh` faz tudo isso sozinho (porta em `JOURNEYS_MANYCHAT_PORT`).

**J15 (entrega fora da área, taxa por distância) precisa dos mapas falsos**
(`shopman/shop/tests/e2e/fake_maps.py`, #2569 item 4). O endereço digitado chega sem
coordenada e o servidor o geocodifica pelo texto; o fake responde o Geocoding do Google a
partir de uma tabela fixa (um endereço a 2,5 km, um a 7,2 km, um a 14,8 km da loja do
seed) e também o ViaCEP, que a jornada desvia do navegador para ele. A distância é
haversine local: não há API de rotas a imitar. O Django e o worker sobem com
`SHOPMAN_E2E_MAPS_API_BASE` apontando para ele (o `settings_e2e` troca o endereço do
geocoding e põe a chave de servidor falsa), e a jornada recebe `JOURNEY_MAPS_URL`. O
script sobe sozinho (porta em `JOURNEYS_MAPS_PORT`, padrão 12192).

### Desligar

Derrube o que subiu (`kill` nos processos do `runserver`, do worker e dos dois
`node .output/server/index.mjs`) e, se o banco era só da jornada, `dropdb shopman_exc_l00`.

## 4. Comparação A/B supervisionada (`tests/e2e/journeys/`, OC-23)

As jornadas essenciais do §5.1 do plano da Etapa II omnicanal, escritas uma vez e rodadas
para a versão A e para a B na pilha da seção 3, com a mesma cliente (CLI-003) e o mesmo
seed. Quem decide a versão é o servidor (a cliente fora ou dentro da coorte das
`RuleConfig` do harness, `shopman/shop/tests/e2e/seed_experience.py --cohort
--experiment`, que liga o de prova e todo `EXPERIMENT(<ref>)` da loja), nunca a URL.
Cada passo é auditado em 320/375/390 px e no computador: captura, axe, X9
(`data-decisive`) e X11 (fonte raiz a 200 %), com a medida da fila
(`tests/journeys/support/typographyAudit.mjs`). Config própria
(`playwright.experience.config.ts`); a suíte com servidor de mentira ignora esta pasta.

```bash
DATABASE_URL=postgres://localhost:5432/<banco só de jornada> \
  lockf /tmp/shopman-previa.lock make experience-compare
```

Relatório em `test-results/experience-compare/relatorio.html`. Protocolo completo, com a
sessão humana: [`docs/guides/comparacao-ab-supervisionada.md`](../../../../docs/guides/comparacao-ab-supervisionada.md).
