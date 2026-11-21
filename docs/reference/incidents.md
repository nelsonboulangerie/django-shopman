# Incidentes: alerta de produção com dono, prova de volta e remédio do domínio

Pedido do dono (21/11/2026, `DEV-2026-066`): nenhum alerta de produção fica sem dono,
e o que é básico e crítico o próprio sistema resolve, com segurança e prova.

## O papel de cada peça

A cura mora onde a falha nasce: os retries da Directive, os sweeps e reconciliações
do `maintenance_worker`, os gestos de cada domínio. O Watchman e os incidentes não
consertam nada. Eles fazem três coisas:

1. **Detectar e provar.** As sondas do Watchman e o `OperatorAlert`. O alerta fecha
   por FATO DO DOMÍNIO (ex.: `shopman/shop/handlers/alert_resolution.py`), nunca por
   decisão de quem observa.
2. **Rotear.** Cada tipo de alerta vira uma issue `alerta` com dono, sem duplicar, e a
   issue fecha sozinha depois de 24 h verdes.
3. **Acionar** (fase W2) só remédios que o domínio já oferece, numa lista fechada, e
   conferir que resolveu.

O alerta que volta sempre é defeito: três episódios em sete dias marcam a issue com
`defeito-recorrente`, e a causa se corrige no código.

## Fonte única

O `OperatorAlert` é a fonte. O e-mail crítico (`shopman/shop/services/critical_alerts.py`),
o sino do Gestor e a issue leem dele.

- **Resumo por tipo:** `shopman/backstage/incidents/summary.py` (`summarize`). Janela de
  7 dias, mais os abertos de antes dela. Um *episódio* é um trecho contínuo com alerta
  aberto do tipo; oito alertas na mesma rajada são um episódio só.
- **Dono:** `shopman/backstage/incidents/owners.py`. Sai do público do alerta
  (`orders` → Gestor de pedidos, `production` → Produção, `finance` → Financeiro,
  `operations` → Operação). Os avisos de sistema (`SYSTEM_TYPES`) e as exceções
  nominais (`OWNER_OVERRIDES`) são da Engenharia: hoje a fase travada, a gravação no
  iFood, o evento do iFood sem tratador, a reserva órfã devolvida e a entrega do
  aviso "voltou ao estoque" (triagem da primeira rodada, 21/11/2026).
- **Sem dado de cliente:** a mensagem do alerta nunca sai do resumo. Saem tipo,
  contagens, horários e refs de pedido.

## A porta da ponte

`GET /api/v1/backstage/incidents/` (só leitura). Entra o superusuário logado ou a
credencial da ponte, `IncidentReaderCredential`: bearer `<ref>.<segredo>`, o banco
guarda o HMAC, vale até a data de emissão, revoga-se no Admin (Incidentes,
Credenciais da ponte). Ela não abre nenhuma outra rota.

```json
{
  "schema_version": 1,
  "generated_at": "2026-11-21T18:00:00+00:00",
  "window_days": 7,
  "recurring_episodes": 3,
  "groups": [
    {
      "fingerprint": "shop:lifecycle_phase_stuck",
      "type": "lifecycle_phase_stuck",
      "label": "Fase do pedido travada",
      "owner": "Engenharia",
      "audience": "orders",
      "severity": "critical",
      "open_count": 9,
      "open_since": "…",
      "last_seen": "…",
      "green_since": null,
      "episodes": 2,
      "recurring": false,
      "home": "",
      "order_refs": ["IFOOD-261118-3030"]
    }
  ]
}
```

## A ponte do GitHub

`scripts/incident_bridge.py`, rodado por `.github/workflows/incident-bridge.yml` a cada
2 h (só biblioteca padrão, cerca de 12 minutos de runner por dia).

- Lê o resumo da loja e, quando o `SENTRY_AUTH_TOKEN` lê issues, as issues abertas do
  Sentry em produção. Issue do Sentry sem evento há 24 h conta como verde.
- Lê da DigitalOcean (`DO_READ_TOKEN` = segredo `DIGITALOCEAN_READ_TOKEN`, app em
  `DO_APP_NAME`) os reinícios e a memória de cada componente do app nas últimas 48 h,
  pela API de métricas do App Platform (`/v2/monitoring/metrics/apps/restart_count` e
  `memory_percentage`). Componente que reiniciou nas últimas 24 h, ou passou de 90% de
  memória, abre `do:<componente>:restart` ou `do:<componente>:memoria`, com dono
  Engenharia. O contador é por instância e recomeça no deploy: só a subida conta. Sem
  o escopo `monitoring:read`, a rodada avisa no log e segue com as outras fontes.
- Acha a issue da ponte pelo marcador `<!-- incident:<fingerprint> -->` no corpo, ou
  ADOTA uma issue aberta à mão cujo título cita o tipo como palavra inteira
  (ex.: "Alerta: lifecycle_phase_stuck").
- O estado fica num comentário fixo (`<!-- incident-status:<fingerprint> -->`),
  editado no lugar e só quando muda.
- Verde há 24 h: fecha a issue que ela abriu. A adotada recebe o aviso de verde e fica
  para o PR que corrige a causa fechar.
- Volta de um incidente cuja issue da ponte fechou: reabre, com comentário.

### Ligar

1. No console de produção: `python manage.py issue_incident_reader_credential`. O token
   aparece uma vez.
2. Segredo `INCIDENTS_TOKEN` com o token, e variável `INCIDENTS_URL` com
   `https://api.boulangerie.com.br/api/v1/backstage/incidents/`.
3. Sem `INCIDENTS_URL` o job nem sobe. Com ela e sem o token, a rodada falha e diz o
   que falta.
