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
3. **Acionar** só remédios que o domínio já oferece, numa lista fechada, e conferir
   que resolveu.

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
  nominais (`OWNER_OVERRIDES`) são da Engenharia.
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

## O acionador (W2)

`shopman/backstage/incidents/remedies.py` (a lista FECHADA) e `act.py` (a máquina).

### A lista fechada

Entra só o gesto que o domínio já oferece a uma pessoa e que ele, sozinho, deixou
parado à espera dela. O que o domínio já repete sozinho não entra, porque acionar de
novo não ganharia nada.

| Remédio | Alerta | O gesto do domínio | Regra | Confere por fato | Teto |
|---|---|---|---|---|---|
| Reprocessar a NFC-e | `fiscal_emit_failed` | `requeue_fiscal_emission` (o "Reprocessar NFC-e" do Gestor) | emissão já solicitada, falhou sem resposta do emissor (a janela transitória de ~64 min acabou) | `nfce_access_key` no pedido; falhou de novo = não resolveu | 3 por pedido em 24 h; confere em 5 min, desiste em 90 |
| Reenviar o aceite ao iFood | `ifood_accept_not_delivered` | `ifood_accept_sync.retry` (o "Tentar de novo") | o domínio parou de tentar, ou a próxima tentativa dele cai depois do prazo do iFood (8 min) | aceite `sent` ou `confirmed` | 3 por pedido; confere em 30 s, desiste em 10 min |

Ficaram de fora, com motivo:

- **rodar um sweep agora** (`sweep_stuck_orders`, `reconcile_ifood_orders`): já rodam a
  cada ciclo do `maintenance_worker`;
- **regravar a loja no iFood**: o `check_store` já pede a regravação quando a loja
  diverge (4 min) e a cada 6 h, e o que sobra é 403/400/409, que repetir não resolve;
- **NUNCA**: credencial, dinheiro (estorno, captura, corrida), apagar dado, reseed,
  configuração de produção, reiniciar ou escalar infraestrutura.

### A máquina

O alerta de tipo com remédio ganha, depois do commit, a Directive `incident.act`. Ela
roda no worker de diretivas (segundos, não o ciclo de 5 min) e, a cada passo:

- **planeja:** o remédio diz `act`, `wait` (o domínio ainda está tentando), `no` (fica
  com gente, com o motivo) ou `judge` (a regra não decide: a resposta do emissor, por
  exemplo, pode ser cadastro ou SEFAZ fora);
- **espera** reagendando-se, sem gastar tentativa;
- **aciona** com o ator `watchman:incidentes`, que aparece no histórico do pedido;
- **confere** por fato do domínio e grava "resolveu" ou "não resolveu".

A repescagem `act_on_incidents` (no `maintenance_worker`) refaz a directive perdida e
vence a conferência atrasada. Não aciona nada sozinha.

### O placar

Toda decisão vira linha de `IncidentAction` (Admin, Incidentes, Placar dos remédios),
inclusive a de não agir: quem decidiu (regra ou modelo), confiança, custo, desfecho e
motivo, sem dado de cliente. O resumo da ponte leva o placar por tipo, e a issue mostra
"Remédio do domínio (Reprocessar a NFC-e), 7 dias: 2 resolveu, 1 ficou com gente".

### Modo

`Shop.incident_remedies_mode` (Admin, Loja, Remédios automáticos de incidente):
`on` aciona e confere (padrão, aprovado pelo dono em 21/11), `shadow` só registra o que
faria, `off` não faz nada.
