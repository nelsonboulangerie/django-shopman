# Ensaio local ponta a ponta do Marketing

Este procedimento exercita o caminho real de aprovação, outbox, directive,
fan-out, target, attempt, aggregate, retry seletivo, reconciliação somente
leitura e receipt. O último boundary é substituído por um adapter
`SIMULATION_ONLY` sem rede nem escrita em arquivo.

## Garantias e limites

- Use somente `DJANGO_SETTINGS_MODULE=config.settings_marketing_demo` em uma
  worktree descartável.
- Esse perfil usa o cookie de sessão exclusivo `marketing_demo_sessionid`. Cookies
  de `127.0.0.1` ignoram porta; o isolamento impede que outro app/backend local
  encerre o ensaio ao substituir o `sessionid` genérico. Produção não é alterada.
- Todas as flags de efeitos externos permanecem `False`; o adapter recusa a
  execução se qualquer uma for ligada.
- O horário silencioso pode ser suspenso nesse perfil para ensaio noturno, mas
  somente enquanto o adapter de WhatsApp provar que é hermético. A mesma flag
  isolada não suspende a política.
- O catálogo contém apenas `local_marketing_e2e`. Selecioná-lo ainda exige
  versão, confirmação, TOTP e auditoria.
- “Confirmado” significa confirmado pelo simulador local. Não comprova
  credencial, aceite ou entrega de Instagram/WhatsApp reais.
- Um `unknown` sintético é resolvido pelo método `lookup` do simulador. Esse
  método nunca chama `send`; o log explicita `operation=lookup` e
  `external_effect=false`.
- Não use este perfil como evidência de G-H03, piloto, staging ou produção.

## Preparação uma vez por banco descartável

```bash
DJANGO_SETTINGS_MODULE=config.settings_marketing_demo \
python manage.py seed --flush --profile qa

DJANGO_SETTINGS_MODULE=config.settings_marketing_demo \
python manage.py setup_admin_totp admin
```

O `--flush` é deliberadamente explícito porque apaga o banco selecionado. Ele
cria `admin/admin` e a coorte sintética `QA-MKT-001`…`QA-MKT-012`, com consentimento
verificável e tag `qa-marketing-e2e`. Cadastre o QR do segundo comando em um
autenticador; não existe segredo ou código TOTP fixo no repositório.

## Executar

Em três terminais da mesma worktree:

```bash
DATABASE_URL='' DJANGO_SETTINGS_MODULE=config.settings_marketing_demo \
python manage.py runserver 127.0.0.1:8008

cd surfaces/marketing-nuxt
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8008 \
NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:8008 \
npm run dev -- --port 3008

make marketing-simulator
```

Abra `http://127.0.0.1:3008`, entre com `admin/admin`, vá a **Plataformas →
WhatsApp** e escolha **Fluxo local — sem envio externo**. A mudança passa pelo
gate TOTP normal.

Vá a **Campanhas**, abra **Disparar agora** na campanha ativa e escolha o público.
A contagem vem do backend e o botão permanece bloqueado quando ela é zero ou está
degradada. O primeiro envio abre a confirmação canônica; use a senha da sessão e
digite a frase exibida. A repetição preserva a mesma chave de idempotência.

O comando aceita somente versão e regras de audiência. Ele não recebe corpo de
mensagem nem telefone arbitrário e cria um anúncio **pendente de revisão**, com
snapshot, audit event e comprovante no próprio painel. Nesse ponto nenhum outbox,
directive, target, attempt ou efeito externo existe. Use **Revisar anúncio agora**
para seguir ao card recém-criado.

Abra `/announcements/<pk>#review`, revise e confirme a consequência. Com Instagram
+ WhatsApp, o esperado é 1 target de publicação, 12 targets de mensagem e 13
receipts `sim_…`.

## Conferir sem tocar provider

Copie o receipt de decisão mostrado na tela e execute:

```bash
DJANGO_SETTINGS_MODULE=config.settings_marketing_demo \
make marketing-diagnose receipt=<UUID>
```

O resultado esperado é `result=OK`, dois outboxes `dispatched`, treze targets e
treze attempts `confirmed`, `provider_calls=0` e `pii=false`. A tela de detalhe
deve mostrar Instagram `1/1` e WhatsApp `12/12`.

O alvo `make marketing-simulator` também consome reconciliações pendentes. Ao
ensaiar um estado `unknown`, a UI deve primeiro registrar a consulta e manter o
resultado incerto; somente o ciclo seguinte do worker muda o ledger após o
`lookup`. Repetição seletiva e reconciliação são caminhos diferentes: a primeira
chama de novo apenas `failed_retryable`; a segunda nunca chama `send`.

No desenvolvimento sem Redis, o channel layer é process-local. Como API e worker
rodam em processos separados, a tela pode depender do poll de segurança ou de
uma recarga para refletir a liquidação; o ledger persiste a verdade. Isso não é
evidência suficiente para o gate de SSE/Redis do runtime real.
