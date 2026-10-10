# Matriz visual do B.I.

O B.I. abre sem Django: `mockBackend.mjs` repete respostas GRAVADAS de um Django real
com o seed sintético (Nelson), guardadas em `fixtures/recorded-django.json`. Nada ali é
dado de pessoa: o operador é "Admin" e os clientes são os do seed.

```bash
npx playwright test -c playwright.visual.config.ts
```

O config sobe o mock na porta 38794 e o `nuxt dev` na 33017 (as do Gestor são outras).
O spec `bi.spec.ts` abre as 8 rotas e confere o título e a ausência de erro de página.
Não há baseline de retrato: retrato só se grava com o browser da CI.

## Os três cenários

O mock troca de cenário por `GET /__visual/scenario?set=<nome>`:

- `normal`: o gravado, como veio do Django.
- `empty`: a mesma forma de cada leitura do B.I., com as listas vazias e os números
  zerados. É o estado vazio de cada tela ("sem lote fechado", "sem venda").
- `error`: 500 em toda leitura de `/api/v1/backstage/bi/`, para ver o "Tentar de novo".

Sessão, posto, avisos e nome da casa seguem o gravado nos três, porque o que se quer
ver é a tela do B.I., não o login.

## Por que o mock casa pelo caminho e ignora a query

Toda leitura do B.I. leva a janela na query (`date_from`, `date_to`, `day`, `target`,
`compare`, `metric`...), e a janela é relativa a HOJE. Uma fixture gravada em 08/10
tem `date_from=2026-09-11`; aberta em outro dia, o app pede outras datas e nenhuma
chave exata bateria. Por isso o mock tenta primeiro a chave exata (caminho + query) e,
sem ela, devolve a gravação do mesmo caminho com qualquer query (o mesmo `recordedFor`
do Gestor). Consequência: trocar o período, o dia ou a métrica na tela não muda os
números do mock. Para retrato isso basta; para conferir filtro, use o Django.

Os POST respondem sem estado: "Levar ao plano" devolve `{plan_day, carried}` e o resto
devolve `{}`.

## Como regravar

1. Banco novo, com nome único (nunca o de outra sessão nem o do alpha):
   ```bash
   createdb shopman_bi_rec_$(date +%s)
   export DATABASE_URL=postgres://localhost/shopman_bi_rec_<sufixo>
   .venv/bin/python manage.py migrate
   .venv/bin/python manage.py seed
   ```
2. Sessão de superusuário: entre no Admin com o superusuário do seed e copie o valor
   do cookie `sessionid` para um arquivo (por exemplo `/tmp/bi-sessionid.txt`).
3. Django no ar: `.venv/bin/python manage.py runserver 127.0.0.1:8000`.
4. O proxy gravador entre o app e o Django (porta do proxy, porta do Django, arquivo da
   sessão, arquivo de saída):
   ```bash
   node tests/visual/recordProxy.mjs 38795 8000 /tmp/bi-sessionid.txt /tmp/recorded-django.json
   ```
5. O app apontando para o proxy:
   ```bash
   NUXT_DJANGO_BASE_URL=http://127.0.0.1:38795 NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38795 npm run dev
   ```
6. Percorra as 8 telas (`/`, `/sales`, `/cash`, `/customers`, `/profiles`, `/explore`,
   `/forecast`, `/scenarios`), no desktop e no celular, abrindo o que lê do servidor.
7. Encerre o proxy com SIGTERM (`kill <pid>`) ou Ctrl+C: é aí que ele grava. Copie o
   arquivo para `fixtures/recorded-django.json` e confira que não entrou e-mail,
   telefone ou CPF de gente de verdade antes de commitar.
8. Apague o banco de gravação.
