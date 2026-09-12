# Ligar o Sentry (error tracking)

> **Para quem:** o dono. Nenhum passo aqui pode ser feito por um agente — o DSN
> é credencial, e credencial se cola no painel, não no repositório.
>
> **Tempo:** ~10 minutos, incluindo a confirmação de que chegou evento.

## Por que isto importa mais do que parece

O código já está pronto e é bom. `sentry-sdk` está instalado e pinado (2.68.1);
`config/settings.py` tem um `init` cuidadoso, com `send_default_pii=False`, com
um `before_send` que arranca a query string de toda URL (o webhook da Efí
autentica por `?token=`, e sem esse corte o segredo viajaria em texto puro), e
agora com `max_request_body_size="never"`.

E **nada disso roda**, porque `SENTRY_DSN` nunca foi setado. O `init` é
`opt-in`: sem DSN, o bloco inteiro é pulado.

O efeito combina com o outro buraco: `DJANGO_LOG_LEVEL` tem default `INFO`, e
existem **340 `logger.debug` dentro de `except`** em produção que, nesse nível,
não emitem uma linha em lugar nenhum (133 deles são handlers que não fazem
absolutamente mais nada). Somando os dois, um erro de negócio hoje tem
exatamente **um** caminho até você: um cliente reclamando. Números e tabela em
[`docs/reference/silencio-inventario.md`](../reference/silencio-inventario.md).

> **O que já funciona sem esta conta.** Desde o alerta de erro não tratado, todo
> 500 vira um `OperatorAlert` de severidade `error` — sem depender de terceiro
> nenhum, agrupado por (exceção + arquivo:linha), com o traceback resumido e
> higienizado. Os dois não competem: **o Sentry é para depurar** (traceback
> inteiro, variáveis, frequência, histórico) e **o alerta é para saber** — ele
> chega em quem está no balcão, não em quem está no editor. Ligar o Sentry
> continua valendo por tudo que o alerta deliberadamente não guarda.

## Passo 1 — pegar o DSN

1. Entre em <https://sentry.io> com a conta da padaria (crie se não houver — o
   plano gratuito cobre folgado o volume do alpha).
2. **Projects → Create Project → Django**. Nomeie `shopman`.
3. A tela seguinte mostra o snippet de instalação com o DSN dentro. Você quer
   só o DSN — a linha que se parece com:

   ```
   https://<32 caracteres>@o<numero>.ingest.us.sentry.io/<numero>
   ```

4. Se a tela já passou: **Settings → Projects → shopman → Client Keys (DSN)**.

> O DSN não é secreto no sentido de senha — ele vai embutido em app de
> navegador por design. Mesmo assim ele entra como `SECRET` no App Platform: é
> credencial de ingestão, quem tiver pode poluir seu projeto, e não custa nada
> tratá-la direito.

## Passo 2 — colar no App Platform

O spec versionado **já declara a env** (este PR fez isso). Você só preenche o
valor:

1. <https://cloud.digitalocean.com/apps> → **shopman-nelson**.
2. **Settings → App-Level Environment Variables → Edit**.
3. Ache `SENTRY_DSN` (já está lá, vazio, marcado como encrypted).
4. Cole o DSN. **Save**.

O App Platform faz um deploy novo sozinho (~6 min).

### Opcional, e recomendado deixar como está

- `SENTRY_TRACES_SAMPLE_RATE` — default `0` (performance tracing desligado).
  Ligar custa cota e não responde a pergunta nenhuma que você tenha hoje.
- `SHOPMAN_ENVIRONMENT` já é enviado como `environment` do evento, então alpha
  e produção não se misturam no painel quando o segundo subir.

## Passo 3 — confirmar que chegou evento

Não confie no deploy verde: confirme com um evento de verdade.

```bash
# no console do app (Runtime Console da DO), NÃO no seu terminal
python -c "import sentry_sdk; sentry_sdk.capture_message('teste de fumaça do Sentry')"
```

Em até um minuto o evento aparece em **Issues**. Se não aparecer:

| Sintoma | Causa provável |
|---|---|
| Nada em Issues, sem erro no console | DSN colado com espaço ou quebra de linha |
| `sentry_sdk` importa mas nada sai | o deploy ainda não recarregou — confira a hora do último deploy |
| Warning `SENTRY_DSN setado mas sentry-sdk não pôde inicializar` no log | DSN malformado; o `settings.py` já grita isso de propósito |

## Passo 4 — os alertas

Por padrão o Sentry manda e-mail para o dono do projeto a cada issue nova. Isso
basta para o alpha. **Settings → Alerts** se quiser afunilar depois.

## O que o Sentry NÃO vai resolver sozinho

Ele reporta **exceção que sobe**. Ele não reporta exceção que alguém já
capturou e engoliu — que é exatamente a dívida dos 94 sites do inventário. As
duas frentes são complementares:

- **Sentry** pega o que quebra alto e ninguém viu.
- **`make test-silent-swallow`** impede que o próximo conserto deixe o irmão
  calado.

## ⚠️ A bomba do `FOCUS_NFE_ENVIRONMENT` — decisão pendente do dono

Fora do escopo do Sentry, mas encontrado na mesma auditoria e sem lugar melhor
para morar até você decidir:

**`FOCUS_NFE_ENVIRONMENT` não existia em lugar nenhum** — nem no spec
versionado, nem no app vivo. O default do `config/settings.py` é
**`homologacao`**.

Isso significa que **as NFC-e emitidas no alpha até hoje não existem no
SEFAZ**. São válidas como exercício e inválidas como documento fiscal.

Este PR escreveu a linha nos dois specs **com o valor que já vale hoje**
(`homologacao`) — escrever não muda nada, só para de esconder. Trocar para
`producao` é decisão sua, e é de mão única: nota emitida em produção é
documento fiscal de verdade, cancelável só dentro do prazo legal.

⛔ É item de checklist de **go-live**, não de deploy. Ver
[`ativar-focus-nfe.md`](ativar-focus-nfe.md) e
[`go-live-cutover.md`](go-live-cutover.md).
