# Marketing — formatos públicos e canário unitário

**Estado:** implementação técnica concluída localmente; efeito externo bloqueado

**Branch:** `codex/marketing-stories-social-publishing-20260911`

**Worktree:** `django-shopman-marketing-stories-social-20260911`

**Efeito externo nesta execução:** nenhum; sem push, PR, deploy, configuração viva,
mensagem ou publicação

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
