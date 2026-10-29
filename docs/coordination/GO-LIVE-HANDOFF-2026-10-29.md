# Handoff de decisões e pendências de go-live, 29/10/2026

Este registro reconcilia o inventário das sessões Claude com o `main`, os PRs e
as sessões Codex observados em 29/10/2026. Não substitui a
[matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md) e não autoriza efeitos
externos. O estado de PR é uma fotografia; a decisão do dono é o que permanece.

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
| Rescues e briefing UX | #2047 aberto | Coordenação global acompanha |
| Retirada grátis no Google | #2050 aberto | Sessão Google acompanha; depois do deploy ainda depende de configurar a loja e concluir Listagens locais no Merchant Center |
| Retirada grátis no produto | #2052 aberto | Sessão Google acompanha |
| CI/E2E da fila | #2054, #2056 e #2057 abertos com auto-merge | Coordenação global acompanha; não reimplementar |
| Navegação Gestor/Compras | #2048 draft, docs e prévias locais | Espera avaliação do dono; não enfileirar |

## Triagem das pendências transferidas

| Pendência | Estado no `main` de 29/10 | Próximo dono / PR |
|---|---|---|
| Código da loja e Listagens locais gratuitas | Ação externa ainda posterior aos #2050/#2052 | Sessão Google + Pablo no Merchant Center; não inferir autorização para concluir telas externas |
| Remover fonte XML legada | Desenho aprovado, fonte em tempo real já existe; rota/feed legado ainda existe | Nova frente de código e remoção da fonte externa, sem misturar com retirada |
| Catálogo do Gestor lento | Defeito relatado, sem PR específico confirmado; #2053 trata catálogo/PDP do Storefront | Atribuir depois da medição, sem confundir os dois catálogos |
| Escada do Doorman | Passkey e device trust existem, mas a decisão completa de 180 dias renováveis, entrada por passkey, retorno à loja e SMS ligado à origem não está entregue | WP próprio antes do go-live |
| WP-RELEASE-01 R0/R1 | Nenhuma entrega correspondente confirmada | WP próprio antes do go-live |
| Onda 2 T13 a T15 | Escopo não foi recuperado com evidência suficiente | Coordenação global recupera o laudo antes de abrir trabalho |
| Mensagens distintas de rejeição de cupom | O código atual unifica a resposta por segurança contra enumeração e tem testes explícitos | Reabrir só com decisão que concilie clareza e segurança; não tratar a nota antiga como aprovação |
| Webhook legado `/ifood/` | A rota ainda existe ao lado de `/ifood/events/` | WP próprio, depois de provar que nenhum produtor usa a rota antiga |
| Seis runbooks com `make` local | Escopo exato não foi preservado | Localizar evidência antes de editar; não fazer substituição mecânica |
| CAS de Directive e `customer_orders` | Há locks `select_for_update`, mas a leitura não prova que todas as transições finais usam CAS | Auditoria concorrente própria com teste PostgreSQL |
| `data-schemas`, campo `e2e_id` | Escritores/leitores já estão documentados em vários contratos | Confirmar o ponto exato “Lido por” antes de abrir PR; a nota genérica está parcialmente obsoleta |
| Marcador expand-contract e ADR-015 | Implementado em `scripts/check_migrations.py`, documentado e testado | Encerrado; não reimplementar |
| EventSource do Marketing | Marketing ainda instancia `EventSource` cru apesar do wrapper resiliente do operator-kit | Frente própria |
| Cache/timeout de instalação dos browsers | A instalação ainda aparece em vários jobs e scripts | Frente de CI própria; não regenerar baselines |
| Prova do código 99 via iFood | Efeito externo não autorizado nesta transferência | Depende de decisão contextual do dono |
| `tpIntegra=1` para cartão online e Pix | Decisão explicitamente pós-go-live | Não executar agora |
| `evidence/glr-2026-10-23/` | A nota antiga manda apagar, mas a redundância e retenção ainda não foram provadas nesta rodada | Não apagar sem auditoria de referências |
| Alerta `fiscal_cancel_failed` da N09 | A causa histórica foi corrigida no #2029 e a prova posterior está no #2051 | Conferir estado vivo em leitura; não apagar alerta sem reconciliação |

## Limites preservados

- Não executar corrida real TaOn, pagamento, emissão fiscal, credencial, reseed ou
  ação de terceiro sem autorização específica.
- A autorização da fornada vale apenas para a TRADI no alpha.
- Nenhum produto além da TRADI deve ser exposto no Google antes do go-live.
- Trabalho novo usa uma frente, uma branch e um PR; trabalho já em voo fica com
  o owner identificado acima.
