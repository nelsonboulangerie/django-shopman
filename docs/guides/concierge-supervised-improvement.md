# Melhoria supervisionada da Concierge por conversas reais

## Objetivo e limite

O ciclo é `observar → redigir → revisar → publicar → medir`. Não é treinamento
automático. A fala observada continua em `ConversationMessage`; não existe uma
segunda base de transcrições. Um caso frequente pode sugerir uma `FAQEntry`, que
nasce não publicada e só se torna conhecimento público depois de revisão humana.

Uma resposta da equipe é evidência de como a operação resolveu o caso, não fonte
automática de verdade. Horário, endereço, catálogo, preço, estoque, taxa e
cobertura de entrega continuam vindo das projeções canônicas da loja.

## Garantias do modo `observe`

O servidor opera em um único modo por release: `assist` ou `observe`. No modo
`observe`, atendimento fica bloqueado antes do intake mesmo se uma automação
antiga chamar o endpoint sem header e mesmo se o switch de atendimento e a chave
do modelo estiverem ativos. O External Request declara
`X-Concierge-Mode: observe`; campos de body com modo ou autor são ignorados. O
adapter fixa `author_type=customer` para a entrada ManyChat.

O modo global é um blackout deliberado desta fase: garante que nenhuma connection
ou canal responda enquanto a observação estiver ativa. Uma futura operação mista
exige outro desenho e outra prova; não é inferida destas flags.

Uma entrada observada:

- é gravada na transcrição canônica com `automation_eligible=false`;
- passa por redação local antes do `INSERT`; contato, documento, endereço,
  segredo e categorias sensíveis reconhecidas são substituídos;
- guarda o texto redigido uma vez, sem cópia em `content` e sem payload bruto;
- recebe `retention_until` obrigatório, entre 1 e 30 dias;
- não cria `Directive`, não acorda worker, não chama modelo e não envia mensagem;
- não altera handoff nem usa a allowlist de atendimento;
- não altera `last_inbound_at`, prioridade ou recuperação do atendimento;
- não entra no contexto do modelo, mesmo se o contato for autorizado depois;
- não pode ser reexecutada como atendimento após uma troca de modo;
- preserva at-least-once quando o provider não fornece ID oficial.

O modo exclusivo e quatro gates são cumulativos e fechados por padrão: `enabled`,
aprovação de privacidade, versão do aviso e retenção válida. Uma coorte explícita
é necessária; lista vazia não significa todos. Observar todos exige o gesto
adicional `allow_all_subjects=true`.

```env
CONCIERGE_OPERATION_MODE=observe
CONCIERGE_OBSERVATION_ENABLED=false
CONCIERGE_OBSERVATION_PRIVACY_APPROVED=false
CONCIERGE_OBSERVATION_NOTICE_VERSION=
CONCIERGE_OBSERVATION_RETENTION_DAYS=7
CONCIERGE_OBSERVATION_ALLOW_ALL_SUBJECTS=false
CONCIERGE_OBSERVATION_ALLOWED_SUBSCRIBERS=4605528796186498
```

`SHOPMAN_CONCIERGE_ENABLED` e a chave do modelo não são necessários para observar;
isso impede que ligar a coleta conceda autoridade de resposta por efeito colateral.
A connection e sua autenticação continuam obrigatórias.

A redação determinística reduz exposição, mas não prova que toda PII livre foi
reconhecida. Por isso ela não substitui G04 e não libera captura geral. Mensagem
inelegível sem prazo é recusada também por constraint do banco.

## ManyChat sem impacto no atendimento

A implementação técnica não modifica o flow. A conta foi inspecionada em
14/09/2026: o trigger `System field value changed` oferece E-mail e Celular, mas
não Last Text Input nem última interação. Portanto a captura usa uma **Rule por
tag**, independente do caminho operacional:

- tag técnica: `concierge_observe_ingress_v1`;
- no ramo de clientes do Default Reply, antes da condição atual de 24 horas, uma
  Action remove e reaplica essa tag, nessa ordem;
- trigger da Rule: tag `concierge_observe_ingress_v1` aplicada;
- frequência da ação: toda vez;
- única action: External Request para o portão canônico;
- header adicional: `X-Concierge-Mode: observe`;
- body mínimo: `subscriber_id`, `text` (Last Text Input) e
  `provider_timestamp` (última interação WhatsApp);
- sem Response Mapping, mensagem, tag, Inbox action, assignment ou handoff.

Rules executam ações globais fora das automações. O Default Reply faz somente a
operação interna de tag e segue imediatamente para o fluxo atual; o External
Request não está nessa cadeia. Uma falha da coleta não interrompe o aviso, a
espera nem a remoção da tag `aviso_atendimento_24h`. Remover antes de aplicar
rearma o evento mesmo quando uma execução anterior ficou dentro do throttle.

A documentação informa que uma Rule para o mesmo contato dispara no máximo uma
vez a cada 30 segundos. Mensagens adicionais nessa janela não chegam ao servidor.
O corpus serve para descobrir padrões, mas não fornece contagem exata nem
cobertura integral. Não substituir por trigger amplo que ocupe a conversa,
polling, Inbox scraping ou External Request inline antes do atendimento atual.

Antes de ativar uma captura geral, o ensaio de homologação precisa provar no
próprio ManyChat:

1. usar somente o contato de Pablo e deixar a conversa inicialmente não lida;
2. remover/reaplicar a tag técnica e executar pela Rule um External Request com
   `X-Concierge-Mode: observe`, sem Response Mapping, mensagem, ação de Inbox,
   assignment ou handoff;
3. confirmar HTTP 200 com `status=observed` e `queued=false`;
4. confirmar que o cliente não recebeu conteúdo da Concierge;
5. confirmar que a conversa continua Open/Unassigned e não lida para o operador;
6. provocar timeout/500 e confirmar que o aviso e o caminho atuais continuam;
7. somente depois habilitar a Rule para a coorte aprovada e repetir o ensaio.

A documentação do ManyChat trata External Request, Open/Closed e Unread como
mecanismos distintos. Ela não oferece uma garantia expressa de que qualquer
automação preserve Unread. Esse item permanece gate de homologação e não pode ser
inferido de teste local. Se o ensaio falhar, o bloco não entra no Default Reply.

O External Request é síncrono. A documentação informa que uma falha pode
interromper o restante de uma automação. Por isso ele não entra na cadeia do
Default Reply. A latência do ACK ainda deve ser medida; budget proposto para
homologação: p95 abaixo de 500 ms.

## O que o ManyChat permite aprender hoje

O campo Last Text Input pode enviar ao servidor perguntas que alcançam o trigger
configurado. A API pública do ManyChat não expõe evento de resposta manual do
Inbox nem exportação incremental da conversa. Portanto:

- perguntas observadas pelo trigger podem alimentar a triagem;
- respostas da própria Concierge já ficam na mesma transcrição;
- respostas manuais da equipe não são capturadas automaticamente por esta fase;
- polling, scraping do Inbox e inferência por timestamp ficam proibidos;
- respostas da equipe entram somente quando houver evento oficial autenticável,
  API privada contratada ou um provider direto em que nossa gateway veja a saída.

“Todas as conversas” significa apenas a cobertura comprovada do trigger. Mensagens
consumidas por outro flow ou recebidas durante pausa humana podem não passar pelo
Default Reply. A medição deve declarar essa cobertura, sem tratar frequência como
contagem exata enquanto não houver ID oficial da mensagem.

## Curadoria e avaliação

Cada agrupamento de casos deve registrar intenção, variantes de linguagem,
resultado esperado, fonte canônica dos fatos e próxima ação. A avaliação usa:

- intenção atendida;
- fatos consistentes com a projeção canônica;
- ausência de invenção e de dado pedido novamente sem necessidade;
- clareza, tom e preservação de contexto;
- resultado ou próxima ação inequívocos;
- handoff correto e evidência de entrega disponível.

Estados de revisão: `aprovado`, `precisa_edicao`, `inseguro` e
`conhecimento_ausente`. Uma FAQ sugerida começa com `is_published=false`; respostas
operacionais reservadas não podem sombrear as projeções. Frequência prioriza a
revisão, mas não publica, altera prompt ou modifica regra comercial sozinha.

## Retenção, descarte e rollback

`cleanup_concierge_observations` integra o `maintenance_worker` periódico e remove
observações vencidas, além de bindings e conversas que ficaram vazios. Para uma
solicitação pontual do titular:

```bash
python manage.py cleanup_concierge_observations \
  --connection-key manychat-whatsapp-primary \
  --subject '<id confirmado no canal>'
```

O comando retorna apenas contagens; não exporta texto nem PII. Observações ficam
fora do Admin para o papel comum de atendimento; somente a permissão dedicada
`shop.review_conversation_observations` libera conversa ou linha observada. Aviso
ao cliente, base legal, responsáveis por conceder esse acesso e procedimento de
acesso/exclusão precisam de aprovação G04 antes de dados reais. Rollback começa
com `CONCIERGE_OPERATION_MODE=assist` e
`CONCIERGE_OBSERVATION_ENABLED=false`; a limpeza permanece até o prazo ou executa
descarte autorizado. Nunca se reprocessa a transcrição para “recuperar”
aprendizagem.

A permissão dedicada não é concedida automaticamente por `setup_operators`:
continua sem grupo por desenho até G04 nomear curadores. Backups/restores, auditoria
de cada consulta e prevenção de reingestão após exclusão também permanecem gates
antes de uma coorte de clientes reais.
