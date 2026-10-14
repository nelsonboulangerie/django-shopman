# Admin fora do ar com instância única: sondas, access log e a 2ª instância

> **Nada aqui foi aplicado na DigitalOcean.** O PR que trouxe este runbook muda o
> arquivo `.do/app.alpha-subdomains.yaml` (e o modelo `.do/app.subdomains.yaml`)
> e o código que as chaves novas usam. Mudar arquivo de spec no repositório não
> aplica nada: a aplicação no app vivo é um `doctl apps update` e pede a palavra
> do dono.

## O que aconteceu (13/10/2026)

Entre ~17:35 e ~17:45 UTC o Admin (`admin.boulangerie.com.br`) respondeu **503**.
Quem serve o Admin é o componente `web-operator`: `instance_count: 1`,
`apps-d-1vcpu-2gb`. Investigação só de leitura:

- **não foi deploy**: o deploy medido no período passou 493/493 respostas 200;
- **causa provável**: a instância única reiniciou ou travou, e não havia outra
  atrás. Um 503 da borda com zero instância saudável nunca chega ao Django;
- **logs perdidos**: o `daphne` roda com `--access-log=/dev/null` e o log da
  aplicação não registra request bem-sucedido, então não há rastro do que a
  instância atendia antes de cair.

## As quatro recomendações, e o estado de cada uma

| # | Recomendação | Estado |
|---|---|---|
| 1 | Alertas `RESTART_COUNT`, `MEM_UTILIZATION` e `CPU_UTILIZATION` no `web-operator` | **Já estão no vivo** (lido em 13/10 por `spec get`): CPU > 80 % e memória > 85 % por 5 min, mais de 2 reinícios em 10 min. Iguais no `web-storefront`. Nada a aplicar. O que faltava era o drift-check enxergar alerta e sonda: agora enxerga (ver abaixo). ⚠️ Conferir na caixa de e-mail da conta DigitalOcean se o `RESTART_COUNT` disparou às ~17:35 UTC: é a prova mais barata da causa. |
| 2 | Readiness separada, tocando o banco | **No arquivo**: `health_check` dos dois services Django → `/health/database/` (novo). Liveness segue `/health/live/`. |
| 3 | Access log, enxuto, sem dado pessoal | **No arquivo**: `SHOPMAN_ACCESS_LOG=true` nos dois services Django. O `--access-log=/dev/null` do daphne **fica**. |
| 4 | `instance_count: 2` no `web-operator` | **Não adotado (decisão do dono 13/10)**: nada de servidor extra. Avaliação registrada na última seção. |

### 2. Por que `/health/database/` e não `/health/ready/`

App Platform tem duas sondas, e elas fazem coisas diferentes:

- `liveness_health_check` falhou N vezes → **reinicia** o contêiner;
- `health_check` (readiness) falhou N vezes → a borda **para de mandar tráfego**
  para a instância, sem reiniciar. É também o que segura um deploy novo fora da
  rota até ele ficar pronto.

O `/health/ready/` completo (banco, cache, migrations, fila e workers vivos)
**não** pode ser readiness da plataforma: um `directive-worker` parado tiraria o
Admin, o PDV e os webhooks do ar sem curar nada, e montar o grafo de migrations a
cada 10 s foi o custo que o #780 removeu. O `/health/database/` faz **um**
`SELECT 1` pelo pool **deste processo** e nada mais.

O que ele ganha, dito sem exagero:

- **com 1 instância**: só segura um deploy novo que não alcança o banco (o release
  já roda `migrate`, então é rede de segurança rara). Em incidente de banco não
  muda nada para quem usa: o 500 do Django vira 503 da borda;
- **com 2 instâncias**: é o que tira da rota a instância cujo pool travou enquanto
  a irmã atende. É a peça que faz a 2ª instância valer.

Banco fora **não** reinicia contêiner: a liveness segue sem banco.

### 3. Por que o access log não é o do daphne

O access log do daphne grava o request-target cru, com query string, e o webhook
da Efí autentica por `?token=` (o comentário no spec conta a história). Grava
também o IP do cliente, e o formato não tem opção. Por isso o `/dev/null` fica.

No lugar, o `AccessLogMiddleware` (primeiro da cadeia, `shopman/shop/middleware.py`)
escreve uma linha por request no logger `shopman.access`, em JSON:

```json
{"duration_ms":41,"http_method":"GET","http_route":"/api/v1/backstage/orders/<str:ref>/","http_status":503,"level":"WARNING","logger":"shopman.access","message":"access GET /api/v1/backstage/orders/<str:ref>/ 503 41ms","streaming":false,"timestamp":"…"}
```

- `http_route` é o **padrão** da rota resolvida, nunca o caminho pedido: ref,
  token de link mágico e código de recibo ficam de fora por construção. Request
  sem rota (404, host recusado) sai com `-`;
- sem IP, usuário, query string ou corpo; método fora da lista vira `OTHER`;
- `5xx` sai como `WARNING`; sonda da plataforma com 2xx não é registrada, sonda que
  falha é;
- SSE: a duração é até os cabeçalhos, não a vida do stream (`streaming: true`).

Sem `SHOPMAN_ACCESS_LOG=true` o middleware sai da cadeia na subida e não custa
nada. Achar os 5xx:

```bash
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator --type run \
  | grep '"logger":"shopman.access"' | grep '"http_status":5'
```

Retenção: o App Platform guarda pouco log de execução. Para guardar mais é
preciso log forwarding (pago ou externo), que não está neste PR.

## Como aplicar (pede a palavra do dono)

**Pré-condição**: o PR deste runbook **mergeado e no ar** (push no `main` é o
deploy, ~6 min). Sem o código novo, a readiness apontaria para uma rota que não
existe e o deploy da aplicação do spec não ficaria `ACTIVE`. Conferir:

```bash
curl -fsS https://admin.boulangerie.com.br/health/database/
# {"status": "ok", "checks": {"database": "ok"}}
```

O update parte do **spec vivo**, não do arquivo do repositório: assim só entra o
que este runbook descreve, mesmo que o arquivo carregue mudança de outra frente
ainda não aplicada (em 13/10, `MACHINE_COMPANY_NAME`).

```bash
APP=40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
CTX=shopman-do-app-admin            # lê databases; o token de deploy NÃO serve (incidente de 29/09)
STAMP=$(date -u +%Y%m%dT%H%MZ)

# 1. Drift ANTES: o arquivo do repositório contra o vivo.
#    Tem de sair só com as linhas da tabela "Delta esperado" abaixo. Qualquer
#    linha em SUMIRIAM, ou "leitura cega" (exit 2): PARE.
make deploy-spec-drift context=$CTX

# 2. Guardar o spec de antes (fora do repositório: tem segredos cifrados).
doctl --context $CTX apps spec get $APP --format yaml > ~/spec-antes-webop-$STAMP.yaml
shasum -a 256 ~/spec-antes-webop-$STAMP.yaml

# 3. Montar o spec de depois a partir do de antes: só as duas sondas e a env.
.venv/bin/python - ~/spec-antes-webop-$STAMP.yaml ~/spec-depois-webop-$STAMP.yaml <<'PY'
import sys, yaml
src, dst = sys.argv[1], sys.argv[2]
spec = yaml.safe_load(open(src))
for service in spec["services"]:
    if service["name"] in ("web-operator", "web-storefront"):
        assert service["health_check"]["http_path"] == "/health/live/", service["name"]
        service["health_check"]["http_path"] = "/health/database/"
        envs = service.setdefault("envs", [])
        if not any(e["key"] == "SHOPMAN_ACCESS_LOG" for e in envs):
            envs.append({"key": "SHOPMAN_ACCESS_LOG", "scope": "RUN_TIME", "type": "GENERAL", "value": "true"})
yaml.safe_dump(spec, open(dst, "w"), sort_keys=False, allow_unicode=True)
PY

# 4. Conferir o de depois contra o vivo: exatamente as 4 linhas abaixo, nada em SUMIRIAM.
.venv/bin/python scripts/check_do_spec_drift.py --context $CTX --spec ~/spec-depois-webop-$STAMP.yaml

# 5. Aplicar (gera um deploy; ~6 min).
doctl --context $CTX apps update $APP --spec ~/spec-depois-webop-$STAMP.yaml
```

### Delta esperado (passos 1 e 4)

```
➕ nasceriam — (serviço web-operator):   SHOPMAN_ACCESS_LOG
➕ nasceriam — (serviço web-storefront): SHOPMAN_ACCESS_LOG
⚠️ componente services/web-operator:   `health_check` diverge — vivo=…/health/live/… versionado=…/health/database/…
⚠️ componente services/web-storefront: `health_check` diverge — vivo=…/health/live/… versionado=…/health/database/…
```

No passo 1 pode aparecer também o que outra frente deixou no arquivo e não
aplicou (13/10: `MACHINE_COMPANY_NAME` em "nasceriam"). Ela **não** entra pelo
passo 5, porque o spec de depois sai do vivo; quem a trouxe aplica.

### Conferir depois

- `doctl --context $CTX apps get $APP` → deployment novo `ACTIVE`;
- `curl -fsS https://admin.boulangerie.com.br/admin/login/ -o /dev/null -w '%{http_code}\n'` → `200`;
- o log tem linhas `shopman.access` e **nenhum** segredo ou IP:

  ```bash
  doctl --context $CTX apps logs $APP web-operator --type run | grep '"logger":"shopman.access"' | head
  doctl --context $CTX apps logs $APP web-operator --type run | grep shopman.access | grep -c 'token='   # 0
  ```

- `make deploy-spec-drift context=$CTX` → só o que outra frente ainda tiver pendente.

## Como voltar

- **Tudo**: reaplicar o spec de antes, que preserva os segredos cifrados.
  Conferir antes: `scripts/check_do_spec_drift.py --context $CTX --spec ~/spec-antes-webop-$STAMP.yaml`
  tem de listar só o delta acima, invertido. Depois
  `doctl --context $CTX apps update $APP --spec ~/spec-antes-webop-$STAMP.yaml`.
- **Só o access log** (log demais, por exemplo): apagar `SHOPMAN_ACCESS_LOG` dos
  dois services no painel. O middleware sai da cadeia no próximo boot.
- **Só a readiness** (se ela tirar a instância da rota sem motivo): no painel,
  Settings → `web-operator` → Health Checks → path `/health/live/`.
- O código não precisa voltar: sem a env o middleware é inerte, e a rota
  `/health/database/` sem sonda apontada para ela é só uma rota.

Depois de qualquer volta pelo painel, alinhar o arquivo num PR de seguimento
(o drift-check passa a acusar).

## 4. Duas instâncias no `web-operator`: não adotado (decisão do dono 13/10)

> O dono decidiu em 13/10/2026 não pagar servidor extra ("preciso de performance,
> mas também economizar"). Fica só o que é grátis: alertas, readiness pelo banco
> e access log. A avaliação abaixo fica registrada para quando a pergunta voltar.

**Custo**: +1 × `apps-d-1vcpu-2gb` = **+US$ 39/mês**. A conta da DO já passa de
US$ 100/mês; é decisão do dono.

**O que ganha**: se a causa de 13/10 foi a instância (reinício, travamento, OOM),
a irmã teria atendido e o Admin não cairia. Se foi plataforma, região ou banco,
duas instâncias caem juntas.

### O SSE funciona com 2 instâncias? Sim, sem mudar código

- `EVENTSTREAM_REDIS` é derivado do `REDIS_URL` (`config/settings.py`, bloco de
  `CACHES`). Com ele, o `django-eventstream` 5.3.4 **publica** todo `send_event`
  no canal Redis `events_channel`, e **cada** processo daphne assina esse canal
  (`RedisListener`) e entrega aos seus `EventSource` locais. Não há fila em
  memória por processo no caminho.
- Isso **já roda entre processos hoje**: `directive-worker`, `maintenance-worker`
  e `web-storefront` emitem eventos que o `web-operator` entrega. Uma segunda
  instância é mais um assinante.
- Histórico e retomada (`Last-Event-ID`) vêm do `DjangoModelStorage`, no Postgres:
  o cliente que reconecta na outra instância retoma do mesmo ponto. Os canais
  efêmeros (`stock-*`, `fomo-*`, `pickup-board`) não têm histórico de propósito: no
  reconnect a tela refaz o fetch canônico (ADR-016).
- A borda não tem afinidade, e não precisa: cada stream fica na instância em que
  abriu; o fan-out é pelo Redis.

O resto do estado também é compartilhado: sessão e rate limit no Valkey, CSRF em
cookie, lock do ManyChat em `pg_advisory_lock`, portão de alerta de erro no banco.
O que é por processo (limitador das sondas, migrations verificadas, cache de token
do Google) é por processo de propósito.

### O que faltaria antes de subir para 2

1. **Arquivos de usuário fora do disco local.** O vivo não tem
   `SHOPMAN_MEDIA_STORAGE`, então o default é disco da instância. A foto do selo
   do Marketing (`shopman/backstage/api/marketing_seal.py`, `default_storage.save`)
   e o `Shop.logo` gravados na instância A dão 404 quando a leitura cai na B. Hoje
   eles já somem a cada deploy. Precisa de `SHOPMAN_MEDIA_STORAGE=r2` com as
   credenciais (D6; [r2-passo-a-passo-do-dono.md](r2-passo-a-passo-do-dono.md)).
2. **A readiness deste runbook aplicada**: sem ela, a instância travada segue
   recebendo metade do tráfego.
3. **Conexões de banco**: cada processo abre até `DATABASE_POOL_MAX_SIZE=8`
   conexões de cliente no PgBouncer, que tem 5 de servidor. A carga se divide, não
   dobra, mas conferir no painel do banco que o pool aguenta o cliente a mais.
4. **Se um dia for adotado**: `instance_count: 2` no `web-operator`, pelo mesmo
   procedimento acima (spec de depois montado do vivo, drift, update). Voltar = `1`.
