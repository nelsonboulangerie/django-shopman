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
workflows ou destinatários. Para a conferência, o token precisa ler alertas **e
membros**: `alerts:read` mais `member:read` (ou os escopos administrativos
equivalentes aceitos pelos dois endpoints), nunca `alerts:write`.

## Antes de salvar qualquer coisa

Abra `ops/watchman/sentry.json` ao lado do painel. Os nomes e números abaixo vêm
desse arquivo. Se o painel não oferecer um campo descrito aqui, pare e registre
a diferença; não escolha um valor “parecido”.

O modelo novo do Sentry **não grava um endereço de e-mail livre no workflow**.
A ação de e-mail aponta para uma identidade Sentry por
`config.targetType` (`user` ou `team`) e `config.targetIdentifier` (ID). As ações
ficam em `actionFilters[].actions`; `triggers.actions` é vazio. Por isso o
Watchman nunca procura o texto `ti@boulangerie.com.br` no JSON: texto em nome,
descrição ou display não prova entrega.

Organização: `nelson-boulangerie`. Projeto: `shopman`. Ambiente: `production`.

## 1. Monitor composto de disponibilidade

Em **Alerts → Create Monitor → Uptime**:

- nome: `Watchman — composite readiness`;
- URL: `https://status.boulangerie.com.br/api/watchman-readiness`;
- método: GET;
- intervalo: 1 minuto;
- timeout: 10 segundos;
- abrir depois de 3 falhas;
- resolver depois de 2 sucessos;
- captura de resposta: desligada;
- ambiente: `production`.

Salvar sem associar ainda à regra antiga de prioridade.

Essa URL roda na borda independente do Cloudflare e sonda em paralelo as duas
readiness, que continuam servidas por processos diferentes. Ela responde 503 se
qualquer perna falhar e o corpo sanitizado identifica `web_operator` ou
`web_storefront`. Assim o único Uptime incluído sem custo no plano cobre os dois
serviços; um segundo Uptime criaria cobrança. O verificador acusa qualquer outro
Uptime ativo no projeto como drift. Se os dois monitores legados tiverem sido
criados antes desta revisão, desative-os antes de criar o composto.

## 2. Monitor de volume de erros

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

## 3. Workflow de aviso

### 3.1 Identidade que recebe o e-mail

Primeiro confirme no plano atual que adicionar um membro não cria assento pago.
Se não houver custo, criar ou confirmar um **membro Sentry dedicado**, autenticado
pelo endereço `ti@boulangerie.com.br`. Não usar `issue owners`, `recent active
members` nem a conta pessoal do dono: esses alvos mudam sem alterar o nome do
workflow.

Depois que o convite estiver aceito, o Watchman lê paginadamente `GET
/api/0/organizations/nelson-boulangerie/members/`, exige exatamente um membro
ativo e aceito com o endereço declarado no contrato, obtém seu `user.id` e o
compara ao `targetIdentifier` da ação. O ID não fica versionado: ele é uma
identidade externa mutável e deve ser resolvido na fonte em toda auditoria. Não
confundir `user.id` com o ID da associação `member.id`.

Se o membro dedicado implicar custo, não criar um assento pago. Um usuário ou time
existente com encaminhamento de e-mail pode ser provado manualmente, mas o Sentry
não expõe pela API a rota final até a caixa operacional. Portanto
`evidenced_email_routing` **não satisfaz o aceite automático atual**: o Watchman
falha fechado até existir um adaptador que consulte uma evidência externa
verificável. A opção automatizável neste contrato é o membro dedicado quando
gratuito.

### 3.2 Gatilhos e ação

Criar um workflow com:

- nome: `Watchman: operações ti@`;
- ligado aos dois detectores acima (um Uptime e um de volume), e somente a eles;
- ambiente: `production`;
- frequência de repetição: 30 minutos enquanto durar;
- gatilhos de abertura `first_seen_event`, `regression_event` e
  `reappeared_event`, além do gatilho de resolução `issue_resolved_trigger`;
- uma ação de e-mail ativa, dentro de um filtro de ação, apontando para o membro
  dedicado acima (`targetType=user`, `targetIdentifier=<user.id real>`);
- enabled: ligado.

O Sentry expõe uma frequência por workflow, não uma sequência crescente. O
contrato usa 30 minutos para não avisar uma vez e calar. A histerese do detector
evita abrir por uma falha isolada e o aviso de resolução fecha o ciclo.

Não apagar nem editar a regra de alta prioridade nesta sessão. Ela é independente;
a substituição só pode ser decidida depois que o fluxo de `ti@` tiver sido provado.

## 4. Prova no painel

Antes de criar credencial:

1. abrir cada monitor e conferir URL, ambiente, limiares e estado ativo;
2. abrir o workflow e conferir os três vínculos;
3. conferir na resposta de leitura que a ação ativa está em
   `actionFilters[].actions`, com `targetType=user` e o `targetIdentifier` do
   membro dedicado resolvido pelo Watchman;
4. usar o teste de notificação do Sentry, se disponível, e confirmar recebimento em
   `ti@boulangerie.com.br`;
5. registrar UTC e capturas sem token no registro operacional da execução.

O membro e o ID tornam a identidade de destino verificável por máquina; ainda é
prudente provar que a caixa é acompanhada. Repetir a prova de recebimento a cada
**90 dias** e depois de qualquer mudança no membro, no grupo de e-mail ou no
workflow. O contrato registra essa periodicidade em
`delivery_assurance.evidence_review_days`.

## 5. Credencial de conferência

No painel, o dono cria uma credencial de organização limitada a leitura de alertas
e membros (`alerts:read` + `member:read`, ou equivalentes mínimos aceitos) e a
guarda no repositório como secret `SENTRY_AUTH_TOKEN`. Não colar no App Platform:
o token pertence ao job externo de auditoria, não aos serviços web. Sem permissão
para listar membros, a conferência falha fechada; ela não rebaixa a prova para uma
busca textual no workflow.

Depois, executar manualmente o workflow `Watchman Infrastructure`. O resultado
esperado é `external_monitoring: pass`. Qualquer `missing` ou `has drift` significa
que o painel não corresponde ao contrato; corrigir no painel e rodar novamente.

A conferência percorre todas as páginas de monitores, membros e workflows e falha
fechada se a paginação estiver incompleta ou ambígua. Nomes esperados duplicados
também são drift: não basta uma das cópias estar correta.

## Reversão

Se o novo workflow enviar para o destinatário errado ou repetir indevidamente, o
dono o desliga no painel. Não apagar os dois detectores durante o diagnóstico: assim
o estado e o histórico ficam disponíveis. O Watchman acusará o workflow desabilitado
como drift até a correção.
