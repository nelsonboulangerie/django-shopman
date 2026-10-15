# Watchman no Sentry: configuração única pelo dono

> **Estado em 15/10/2026:** ainda não aplicado. A única regra viva é “Send a
> notification for high priority issues” e ela notifica a conta pessoal do dono.
> Este roteiro altera o Sentry e só é executado pelo dono no painel. O Watchman
> confere depois por leitura; não cria, edita ou apaga regra pela API.

## Decisão recomendada

Usar a opção **2**: criar os monitores uma vez no painel e entregar à CI apenas
uma credencial de leitura. É a opção que respeita a regra operacional de que o
painel externo muda pelo dono, reduz o impacto de vazamento do secret e ainda
mantém o contrato versionado e o drift verificável.

O `SENTRY_DSN` que já existe não substitui essa credencial. O DSN é a porta de
entrada para a aplicação enviar eventos; ele não permite listar monitores,
workflows ou destinatários. Para a conferência, o token precisa de `alerts:read`
ou `org:read`, nunca `alerts:write`.

## Antes de salvar qualquer coisa

Abra `ops/watchman/sentry.json` ao lado do painel. Os nomes e números abaixo vêm
desse arquivo. Se o painel não oferecer um campo descrito aqui, pare e registre
a diferença; não escolha um valor “parecido”.

Organização: `nelson-boulangerie`. Projeto: `shopman`. Ambiente: `production`.

## 1. Monitor de disponibilidade do operador

Em **Alerts → Create Monitor → Uptime**:

- nome: `Watchman — web-operator readiness`;
- URL: `https://api.boulangerie.com.br/health/ready/`;
- método: GET;
- intervalo: 1 minuto;
- timeout: 10 segundos;
- abrir depois de 3 falhas;
- resolver depois de 2 sucessos;
- captura de resposta: desligada;
- ambiente: `production`.

Salvar sem associar ainda à regra antiga de prioridade.

## 2. Monitor de disponibilidade da loja online

Criar outro Uptime com os mesmos números e:

- nome: `Watchman — web-storefront readiness`;
- URL: `https://api.boulangerie.com.br/api/v1/health/ready/`.

São dois monitores porque os dois paths são servidos por processos diferentes.

## 3. Monitor de volume de erros

Em **Alerts → Create Monitor → Metric**:

- nome: `Watchman — error volume`;
- dataset: events;
- medida: `count()`;
- filtro: `is:unresolved level:[error,fatal]`;
- janela: 5 minutos;
- abrir acima de 20;
- resolver em 5 ou menos;
- ambiente: `production`.

Isso percebe o mesmo erro repetido centenas de vezes; a regra antiga de issue de
alta prioridade não faz essa pergunta.

## 4. Workflow de aviso

Criar um workflow com:

- nome: `Watchman — operações ti@`;
- ligado aos três monitores acima, e somente a eles;
- ambiente: `production`;
- frequência de repetição: 30 minutos enquanto durar;
- gatilho de resolução ligado;
- ação de e-mail: `ti@boulangerie.com.br`;
- enabled: ligado.

O Sentry expõe uma frequência por workflow, não uma sequência crescente. O
contrato usa 30 minutos para não avisar uma vez e calar. A histerese do detector
evita abrir por uma falha isolada e o aviso de resolução fecha o ciclo.

Não apagar nem editar a regra de alta prioridade nesta sessão. Ela é independente;
a substituição só pode ser decidida depois que o fluxo de `ti@` tiver sido provado.

## 5. Prova no painel

Antes de criar credencial:

1. abrir cada monitor e conferir URL, ambiente, limiares e estado ativo;
2. abrir o workflow e conferir os três vínculos;
3. usar o teste de notificação do Sentry, se disponível, e confirmar recebimento em
   `ti@boulangerie.com.br`;
4. registrar UTC e capturas sem token.

## 6. Credencial de conferência

No painel, o dono cria uma credencial de organização limitada a leitura de alertas
(`alerts:read`; `org:read` também é aceito pela API) e a guarda no repositório como
secret `SENTRY_AUTH_TOKEN`. Não colar no App Platform: o token pertence ao job
externo de auditoria, não aos serviços web.

Depois, executar manualmente o workflow `Watchman Infrastructure`. O resultado
esperado é `external_monitoring: pass`. Qualquer `missing` ou `has drift` significa
que o painel não corresponde ao contrato; corrigir no painel e rodar novamente.

## Reversão

Se o novo workflow enviar para o destinatário errado ou repetir indevidamente, o
dono o desliga no painel. Não apagar os três monitores durante o diagnóstico: assim
o estado e o histórico ficam disponíveis. O Watchman acusará o workflow desabilitado
como drift até a correção.
