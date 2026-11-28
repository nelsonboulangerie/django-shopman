# Handoff de decisões e pendências de go-live, 29/10/2026

Este registro reconcilia o inventário das sessões Claude com o `main`, os PRs e
as sessões Codex observados em 29/10/2026. Não substitui a
[matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md) e não autoriza efeitos
externos. O estado de PR é uma fotografia; a decisão do dono é o que permanece.
As linhas reconciliadas em 02/11/2026 citam os PRs efetivamente mergeados;
linhas sem nova evidência conservam a pendência, sem inferir conclusão.

## Decisões atuais

As linhas abaixo substituem as perguntas antigas com o mesmo assunto.

| Assunto | Decisão do dono | Execução |
|---|---|---|
| Baguette no Google | Manter só a TRADI visível antes do go-live. Fazer uma fornada diária no alpha para o Google ler disponibilidade real | A rotina deve usar `WorkOrder`, eventos e ledger canônicos, uma vez por dia, sem reseed, ajuste direto de quant ou disponibilidade simulada |
| Troco depois da coleta | Se o pedido for cancelado e o entregador voltar, o troco levado deve voltar ao caixa | Frente própria, com idempotência, permissão e invariantes do ledger; contexto #2031 a #2033 |
| Cor do tempo | Gestor, Cozinha e Produção usam vermelho atrasado, âmbar perto do prazo, neutro no prazo e verde somente em Pronto | `timeTone()` no operator-kit; não alterar chips de contagem, início do PDV pela comanda nem barra lateral do Gestor |
| Envio ao fornecedor | Revisão humana é o padrão. Um fornecedor confiável pode optar por envio direto | Configuração no fornecedor, nunca em env/settings (ADR-042) |
| Corrida TaOn com várias paradas | O teste real fica com o dono | Nenhum agente chama o provedor automaticamente |
| Admin de produção | `admin/admin` pode ficar durante o alpha | Troca por credencial forte é bloqueador obrigatório antes do go-live; não trocar agora |

O #2048 continua draft de análise e protótipos de navegação, sem autorização de
merge ou implementação. As frentes de cor do tempo e Compras não autorizam
alterar navegação, barra lateral, tema ou baselines.

## Estado reconciliado das entregas em voo

| Frente | Estado medido | Owner / ação |
|---|---|---|
| Correções do PDV que estavam no #2022 | #2041 mergeado em 29/10 às 19:02:51 UTC, incluindo a encomenda do PDV nascer aceita | Encerrada; não reimplementar |
| Resíduos Grid/Merchant | Documentados nos #2040 e #2042, ambos mergeados | Encerrados; não publicar versões obsoletas |
| Rescues e briefing UX | #2047 mergeado em 29/10 | Encerrados; fontes preservadas |
| Retirada grátis no Google | #2050 mergeado em 29/10 | Configuração externa da loja e Listagens locais continuam com a sessão Google |
| Retirada grátis no produto | #2052 mergeado em 29/10 | Código entregue; não reimplementar |
| CI/E2E da fila | #2054, #2056 e #2057 mergeados em 29/10 | Encerrados; não reimplementar |
| Navegação Gestor/Compras | #2048 draft, docs e prévias locais | Espera avaliação do dono; não enfileirar |

## Triagem das pendências transferidas

| Pendência | Estado no `main` de 29/10 | Próximo dono / PR |
|---|---|---|
| Código da loja e Listagens locais gratuitas | Ação externa ainda posterior aos #2050/#2052 | Sessão Google + Pablo no Merchant Center; não inferir autorização para concluir telas externas |
| Remover fonte XML legada | Código do feed removido pela #2065, mergeada em 02/11 | Sessão Google confirma remoção da fonte externa; não reimplementar código |
| Catálogo do Gestor lento | Defeito relatado, sem PR específico confirmado; #2053 trata catálogo/PDP do Storefront | Atribuir depois da medição, sem confundir os dois catálogos |
| Escada do Doorman | #2082 e #2084 mergeadas em 02/11: 180 dias renováveis, passkey, retorno à loja e SMS pela origem | Código entregue; confirmação em dispositivos reais permanece no ensaio operacional |
| WP-RELEASE-01 R0/R1 | #2076 e #2080 mergeadas em 02/11: identidade nas imagens, contrato, inventário e identidade observável | R0/R1 entregues; não confundir com as fases posteriores do WP |
| Onda 2 T13 a T15 | Escopo não foi recuperado com evidência suficiente | Coordenação global recupera o laudo antes de abrir trabalho |
| Mensagens distintas de rejeição de cupom | O código atual unifica a resposta por segurança contra enumeração e tem testes explícitos | Reabrir só com decisão que concilie clareza e segurança; não tratar a nota antiga como aprovação |
| Webhook legado `/ifood/` | Removido pela #2067; spec reconciliado na #2068; eventos sem barra corrigidos #2089 e portal validado #2090 | Entregue; webhook canônico de eventos preservado |
| Seis runbooks com `make` local | Escopo exato não foi preservado | Localizar evidência antes de editar; não fazer substituição mecânica |
| CAS de Directive e `customer_orders` | #2003 cobre apenas parte do perímetro; auditoria PostgreSQL retomada em 02/11 | #2091 em execução; não declarar concluída antes da prova e integração |
| `data-schemas`, campo `e2e_id` | Escritores/leitores já estão documentados em vários contratos | Confirmar o ponto exato “Lido por” antes de abrir PR; a nota genérica está parcialmente obsoleta |
| Marcador expand-contract e ADR-015 | Implementado em `scripts/check_migrations.py`, documentado e testado | Encerrado; não reimplementar |
| EventSource do Marketing | Retomada em 02/11: reconector canônico com backoff, recuperação por visibilidade/rede e fetch após reabertura | #2092; confirmar integração antes de declarar entregue |
| Cache/timeout de instalação dos browsers | A instalação ainda aparece em vários jobs e scripts | Frente de CI própria; não regenerar baselines |
| Prova do código 99 via iFood | Efeito externo não autorizado nesta transferência | Depende de decisão contextual do dono |
| `tpIntegra=1` para cartão online e Pix | Decisão explicitamente pós-go-live | Não executar agora |
| `evidence/glr-2026-10-23/` | Apagado em 02/11/2026: 10 de 11 provas falhavam no `main` (defeito sumiu); a 11ª era sanidade | Encerrado |
| Alerta `fiscal_cancel_failed` da N09 | A causa histórica foi corrigida no #2029 e a prova posterior está no #2051 | Conferir estado vivo em leitura; não apagar alerta sem reconciliação |

## Limites preservados

- Não executar corrida real TaOn, pagamento, emissão fiscal, credencial, reseed ou
  ação de terceiro sem autorização específica.
- A autorização da fornada vale apenas para a TRADI no alpha.
- Nenhum produto além da TRADI deve ser exposto no Google antes do go-live.
- Trabalho novo usa uma frente, uma branch e um PR; trabalho já em voo fica com
  o owner identificado acima.
