# Marketing — formatos públicos e canário unitário

**Estado:** primeiro canário público executado e confirmado pela Meta

**Branch:** `codex/marketing-stories-social-publishing-20260911`

**Worktree:** `django-shopman-marketing-stories-social-20260911`

**Efeito externo nesta execução:** uma publicação pública no Stories da conta
`@nelsonboulangerie`; nenhuma mensagem direta, DM ou entrega para clientes

**Atualização do gate:** push e PR foram autorizados pelo proprietário em 2026-09-11.
O proprietário autorizou explicitamente o Story do anúncio 25, com a foto sanitizada
do hibisco e o texto editorial “Lá vem a primavera...”, sem mensagens/DMs.

## Resultado do primeiro canário público

- conta verificada por consulta read-only à Meta: `nelsonboulangerie`;
- anúncio: `25`, versão aprovada `2`;
- consequência exata: `c70ff9f7-038b-4981-acdc-510d50e39449`;
- formato: Instagram Stories;
- alcance: uma publicação pública e zero destinatários diretos;
- tentativa aceita às 12:17 (America/Sao_Paulo);
- comprovante sanitizado: `ig:17930588622397363`;
- consulta posterior read-only: `instagram_publication_confirmed` às 12:19;
- consumers gerais de outbox e entrega permaneceram desligados.

O adapter não enviou `caption` para o endpoint de Stories da Meta. O texto visível
“Lá vem a primavera...” foi incorporado pelo Codex, antes da publicação, à arte derivada
`hibisco-primavera-20260911.jpg`; não estava na fotografia original fornecida pelo
proprietário e não foi sobreposto pela Meta. O payload externo conteve somente a URL
dessa imagem derivada e `media_type=STORIES`.

A fotografia sanitizada original `hibisco-20260911.jpg` permaneceu intacta. A derivada
1080×1920 foi criada às 09:10 (America/Sao_Paulo) por edição de imagem, adicionada no
commit `7f89983af` e escolhida como mídia do anúncio 25. O registro anterior que dizia
que a frase não apareceu na imagem estava incorreto; confundia a ausência de um campo
nativo de legenda no payload com o conteúdo já rasterizado na mídia selecionada.

### Falhas encontradas antes da fronteira externa

1. O primeiro staging do destino falhou fechado com
   `target_hmac_key_unavailable`. A configuração viva não possuía
   `SHOPMAN_MARKETING_TARGET_HMAC_KEY`; uma chave exclusiva de 64 caracteres foi criada
   como segredo de runtime, versão 1. Antes da recuperação foram conferidos zero
   destinos e zero tentativas externas.
2. O primeiro claim do destino expôs uma incompatibilidade PostgreSQL:
   `FOR UPDATE` abrangia o `OUTER JOIN` opcional de `member__customer`. A consulta foi
   validada no destino exato com `FOR UPDATE OF self`, sem efeito externo. A correção
   permanente trava apenas `DeliveryTarget` e ganhou um teste dedicado no gate real de
   PostgreSQL.

A diretiva 20874 foi recuperada apenas depois de validar estado, erro, outbox exata e
ausência de destino/tentativa. A execução subsequente alcançou uma única vez a Meta.

## Resultado

O produto passou a distinguir a consequência real de cada canal:

| Canal | Consequência contratada | Estado desta entrega |
|---|---|---|
| WhatsApp | mensagem direta por contato elegível | preservada; fora do canário público |
| Instagram | **Stories por padrão**; Feed somente por escolha explícita | adapter e fluxo unitário implementados |
| Facebook | publicação pública na Página | adapter e fluxo unitário implementados |
| Perfil da Empresa no Google | atualização pública padrão do local | adapter e fluxo unitário implementados |

Mensagem direta no Instagram continua fora do contrato. Stories nunca cai
silenciosamente para Feed. O artifact aprovado sela formato, texto, mídia e hash antes
da fila; a aprovação usa o conteúdo efetivamente apresentado, não uma releitura futura
do modelo.

## Omotenashi comprovável

- Stories já vem selecionado e explicado como recomendado; Feed exige uma decisão
  consciente.
- Uma imagem fixa é informada uma vez e reutilizada nos quatro canais, sem redigitação.
- Se Stories usará foto do produto, o formulário explica no próprio campo que ausência
  de foto bloqueará a aprovação; “Sem imagem” mostra a consequência imediatamente.
- A prévia 9:16 deixa explícito que a imagem é o conteúdo publicado no Story e que o
  texto permanece como prova editorial, sem prometer sobreposição automática.
- O preflight aceita o mesmo número visível em `/announcements/ID`, resolve a referência
  exata e entrega o comando final pronto para copiar; o operador não consulta banco nem
  transcreve UUID.
- O canário toca no máximo uma outbox e um destino. Consumers amplos precisam permanecer
  desligados, portanto backlog histórico não é drenado por acidente.
- Estados apresentados ao operador pelo canário estão em português e distinguem aceito,
  confirmado, falha repetível e resultado incerto.

No caso comum do canário, o operador faz zero mudança de tela para encontrar a
referência, zero consulta ao banco e zero redigitação de identificador. Permanecem duas
decisões humanas porque reduzi-las violaria segurança: conferir conta/peça e autorizar a
consequência pública exata.

## Segurança e semântica externa

Os adapters HTTP usam Bearer/JSON ou form conforme o fornecedor, limite de resposta,
erros sanitizados e bloqueio de redirects para não encaminhar credenciais a outro host.
Resposta perdida após efeito vira `unknown`; não existe retry cego. Replay de destino
encerrado não chama o fornecedor novamente.

O comando `run_marketing_publication_canary` exige simultaneamente:

1. `SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED=true`;
2. os dois consumers globais de Marketing desligados;
3. integração exata pronta e apenas a flag da plataforma necessária;
4. outbox UUID exata, plataforma correspondente, `--execute` e frase de confirmação
   vinculada ao UUID.

O runbook operacional é
[`docs/operations/marketing-publication-canary.md`](../../operations/marketing-publication-canary.md).

## Pré-requisitos externos ainda intencionalmente ausentes

- **Instagram/Facebook:** Page ID, Instagram Business Account ID, token correto, escopos
  Meta e confirmação visual da conta/página de destino.
- **Instagram Stories:** arte final JPEG pública por HTTPS, preferencialmente vertical
  9:16, que possa de fato permanecer pública durante o teste.
- **Perfil da Empresa no Google:** acesso à Business Profile API, OAuth com
  `business.manage`, account ID, location ID e confirmação do estabelecimento.
- O token Google está modelado para um canário controlado. Ativação contínua exige uma
  decisão e implementação separada do ciclo de renovação OAuth; não se deve operar
  indefinidamente com token estático.

Os contratos externos foram revalidados em 2026-09-11 nas referências de
[publicação do Instagram mantidas pela Meta](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api),
[criação de Local Post](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts/create)
e [consulta de Local Post](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts/get).

## Capacidade real de Stories na API pública da Meta

A referência `IG User /media`, atualizada pela Meta em 12/08/2026, distingue a
publicação automática do compartilhamento móvel para o compositor do Instagram.

| Recurso | Publicação automática (`/media`) | Observação operacional |
|---|---|---|
| Imagem ou vídeo | sim | imagem JPEG; vídeo MOV/MP4; 9:16 recomendado |
| Menção de usuário | sim, via `user_tags` | nome público e posição `x/y` opcional; não é figurinha |
| Texto desenhado, fonte, cor e posição | não há campo nativo documentado | precisa ser incorporado à mídia e aprovado visualmente |
| Legenda como no Feed | não há contrato de exibição em Story | não deve ser prometida como texto visível |
| Link clicável | não | a Meta cita explicitamente figurinha de link como incompatível |
| Enquete e localização | não | citadas explicitamente como figurinhas incompatíveis |
| Pergunta, quiz, contagem regressiva, emoji e `Add Yours` | não | a API não publica figurinhas |
| Música da biblioteca do Instagram | não | vídeo pode conter áudio próprio/licenciado já embutido |
| Filtro, efeito ou AR | não | filtros não são compatíveis; efeito deve ser pré-renderizado |
| Fundo sólido/gradiente como camada | não | na API automática, a própria mídia ocupa o canvas |

O fluxo móvel **Compartilhar no Stories**, atualizado pela Meta em 30/06/2026, é
outro contrato: um app Android/iOS entrega ao compositor uma mídia de fundo, uma
imagem de figurinha e/ou duas cores de fundo. O Instagram então abre o compositor e
o usuário ainda edita e publica. Esse handoff não é uma publicação servidor-a-servidor,
não oferece na documentação atual um parâmetro de link e não elimina o gate humano;
ele pode, porém, tornar fácil adicionar manualmente link, música ou figurinha nativa.

Fontes oficiais:
[referência de criação de mídia](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)
e [compartilhamento móvel para Stories](https://developers.facebook.com/docs/instagram-platform/sharing-to-stories/).

### Arte preparada para o primeiro Story

O proprietário forneceu `IMG_2588.JPG`. A cópia de canário ficou em
`surfaces/marketing-nuxt/public/canary/hibisco-20260911.jpg` e será servida, depois do
deploy, em `https://mkt.boulangerie.com.br/canary/hibisco-20260911.jpg`.

- JPEG, RGB, 2268×4032: proporção exata 9:16;
- transformação lossless: pixels idênticos ao original e perfil Display P3 preservado;
- EXIF removido porque o original continha coordenadas GPS, aparelho e data;
- SHA-256 sanitizado: `85018a1e379bc702fcb0a0756abfce74eef4af059101fdb8849f4e278efa3655`.

A conta oficial informada é `@nelsonboulangerie`. Para não expor o ensaio aos clientes,
a preferência operacional é `@pabvalentini`, mas ela só pode ser usada se for uma conta
Instagram profissional elegível e ligada ao app/token Meta. A escolha permanece no gate
humano anterior ao preflight; nenhuma conta foi alterada nesta preparação.

## Evidências locais

| Gate | Evidência |
|---|---|
| Backend Marketing amplo | 877 passaram, 2 ignorados |
| Canário/readiness/adapters finais | 50 passaram |
| Frontend unitário/componentes | 34 arquivos; 249 testes após o aviso inline |
| Segurança frontend | 2 arquivos; 4 testes |
| E2E gerenciado | 1 passou |
| Acessibilidade gerenciada | 2 passaram |
| Matriz visual | 69 passaram; 3 baselines afetadas revalidadas após a última copy |
| Lint/typecheck/build | verdes |
| Auditoria npm | 0 vulnerabilidades |
| Contrato documental | 6 rotas Nuxt, 31 rotas Django e 2 specs de deploy |
| Django | system check verde; nenhuma migration nova |

Os testes dos adapters cobrem Story, Feed explícito, Facebook, Google, timeout depois de
possível efeito, resposta excessiva, erro sanitizado e recusa de redirect autenticado.
A simulação local prova que duas consequências elegíveis coexistem e o canário executa
somente a referência escolhida; a outra permanece pendente e sem destino materializado.

## Gates humanos restantes

Esta entrega não conclui MKT-052 nem autoriza MKT-053. O máximo factual é
**implementação técnica concluída localmente**. Para um teste público real faltam apenas:

1. o proprietário fornecer a arte final e escolher a conta/plataforma exata;
2. Release Manager autorizar push/PR/deploy e a configuração limitada daquela lane;
3. com o preflight já disponível, o proprietário conferir a prévia e autorizar a frase
   da consequência pública exata;
4. após publicação, conferir o resultado e decidir separadamente qualquer remoção.

Os consumers globais permanecem `false`. Não há autorização implícita para lote,
clientes reais, rollout progressivo, remoção de publicação ou escrita em produção.
