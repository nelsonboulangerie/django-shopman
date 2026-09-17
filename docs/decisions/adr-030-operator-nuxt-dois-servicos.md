# ADR-030 — Os oito apps Nuxt de operador em dois services

**Status:** Aceito · 2026-09-17 (decisão do Pablo)
**Escopo:** `surfaces/*-nuxt` de operador, `surfaces/operator-router`, deploy no App Platform
**Origem:** [WP-DO-ECONOMIA E2](../plans/WP-DO-ECONOMIA-2026-09.md#e2--os-8-nuxt-de-operador-em-um-único-service)
e [WP-PERFORMANCE P9](../plans/WP-PERFORMANCE-2026-09.md#p9--consolidação-dos-nuxt-o-que-medir-antes)

## Contexto

Cada app de operador era um service de US$ 5 (512 MB). Medido no painel em 17/09, nenhum
passa de 113 MB: PDV 77–113, KDS 51–108, Pedidos 72–94, Produção 72–97, Central 51–67,
Marketing 67–82, B.I. 51–72, Compras 41–51. Oito services pagam 4 GB de reserva para
~680 MB de uso de pico.

## Decisão

Troca-se **isolamento por custo**, em dois grupos com perfis de uso diferentes:

| Service | Apps | Slug | US$/mês |
|---|---|---|---:|
| `operator-floor` (chão da loja) | pos, kds, orders, production, hub | `apps-s-1vcpu-1gb-fixed` | 10 |
| `operator-office` (gestão) | marketing, bi, purchase | `apps-s-1vcpu-0.5gb` | 5 |

De US$ 40 para 15: **US$ 25/mês**. Picos somados: chão ≈ 480 MB de 1 GB, gestão ≈ 205 MB de
512 MB, mais ~35 MB do roteador em cada. `storefront-nuxt` e `web` ficam fora.

**Desenho (opção b do WP):** N processos Nitro por contêiner e um roteador por `Host`.

1. Cada app é construído como sempre (`npm run build` → `.output/`), sem mudar o build.
   `surfaces/Dockerfile.operator-group` tem um estágio por app e um por grupo;
   `OPERATOR_GROUP` (build arg) escolhe o grupo.
2. `surfaces/operator-router` (Node puro, **zero dependências**) sobe cada Nitro como
   filho numa porta interna (127.0.0.1) e encaminha pelo `Host`: streaming sem buffer
   (SSE), upgrade/WebSocket (nenhum app usa hoje) e corte do filho quando o cliente sai.
   Não reescreve cabeçalho de segurança nem corpo e **não acrescenta `X-Forwarded-For`**
   — o Django conta saltos dessa cadeia. Só remove hop-by-hop (RFC 9110 §7.6.1).
3. **Envs:** os apps leem os mesmos nomes (`NUXT_*`). Sem prefixo, a chave é do grupo;
   `<APP>__<CHAVE>` chega só àquele app. Prefixo de app de outro grupo, prefixo
   desconhecido em chave de runtime ou tentativa de fixar `PORT`/`HOST` derruba o boot.
   `OPERATOR_HOSTS` mapeia hostname → app; app sem host derruba o boot.
4. **Supervisão:** filho que morre volta com backoff (0,5 s dobrando até 30 s; zera depois
   de 60 s de pé). Enquanto está fora, o roteador responde 503 **só no host dele**.
5. **Saúde:** para a sonda da plataforma (Host que não é de app), `/health/live` responde
   200 só se TODOS os filhos estiverem de pé e o `/health/live` de cada um devolver 200
   em JSON (200 em HTML não conta: app com catch-all renderiza a página para qualquer
   caminho). Os dois services usam esse `/health/live` agregado no `health_check` e no
   `liveness_health_check`: probe de plataforma nunca aponta para readiness (P1, #780).
   `/health/ready` agregado existe para diagnóstico, com o `readyPath` de cada app (o do
   Marketing inclui o Django), e não é sonda. No hostname de um app, o caminho é do app.
6. **Encerramento (SIGTERM):** 3 s servindo tudo (a saída do balanceador é simultânea ao
   sinal), depois fecha a porta, termina os SSE com fim de stream limpo (o EventSource
   reconecta no contêiner novo), espera pedidos comuns até 15 s, SIGTERM nos filhos,
   SIGKILL em 5 s.
7. **Envelope de segurança (ADR-026):** CSP/nonce seguem por app, gerados por cada Nitro.
   Nenhum opt-in muda.

## Por que "todos os filhos" na saúde

A sonda é o **gate de deploy**: imagem em que um app não sobe não pode substituir a que
está no ar. Com um único service, o gate só existe se a saúde exigir todos. O custo é o
raio de explosão em runtime: um filho que não volta tira o grupo inteiro do tráfego depois
de 60 s (readiness, 6 × 10 s — tolera um restart supervisionado) e reinicia o contêiner
depois de ~90 s (liveness, 3 × 30 s), que derruba os SSE dos irmãos e dispara
`RESTART_COUNT`. Preferimos um grupo que grita a um PDV no ar ao lado de uma Central morta
em silêncio.

## Consequências

- **Raio de explosão:** crash do contêiner derruba os cinco apps do chão juntos; um crash
  de app isolado não (o supervisor reinicia só ele).
- **Deploy:** qualquer mudança em app do chão republica e reinicia o grupo, e os SSE do KDS
  e do PDV reconectam. Antes só o app tocado reiniciava.
- **CPU:** uma vCPU compartilhada entre os event loops do grupo. Alerta de CPU e memória
  > 80 % por 5 min em cada service novo.
- **Marketing sem Django:** o probe do `operator-office` é liveness, como o dos outros
  services depois do P1. Django fora não tira Marketing, B.I. nem Compras do tráfego; o
  `/health/ready` do Marketing continua sendo pergunta do smoke, no host `mkt.`.
- **Dependência de ordem (cumprida):** as rotas `/health/live` dos apps chegam pela layer
  `operator-kit` (P1, #780, no `main` desde 17/09). Sem elas a saúde agregada reprovava
  (medido antes do #780: KDS 404, Central 200 em HTML) e o deploy dos grupos não ficaria
  verde.
- **Rollback:** reaplicar o spec anterior (8 services). As imagens por app seguem sendo
  publicadas (`OPERATOR_PER_APP_IMAGES` em `deploy-images.yml`) até 14 dias de prova.

## Prova exigida para encerrar a janela de 14 dias

Sem `RESTART_COUNT` nos services novos; SSE do KDS e do PDV reconectando depois de deploy;
TTFB das shells ≤ baseline do WP-PERFORMANCE §2; memória de pico < 80 % nos dois; fatura
com 6 services a menos. Só então `OPERATOR_PER_APP_IMAGES: "false"` e limpeza das tags por
app.
