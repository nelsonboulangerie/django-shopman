# WP — Cutover comercial e canário de Go-live

- **Status:** execução autônoma permitida somente até cada gate humano declarado
- **Data-base da auditoria:** 2026-09-28
- **Objetivo:** virar de pré-go-live técnico para operação comercial com dinheiro e nota reais, preservando reversibilidade e exigindo autorização humana em todo efeito externo.

## 1. Dependências

- WP de segurança/CI integrado.
- WP de verdade documental integrado.
- Checkout canônico de `main` limpo; checkout raiz sem operação Git interrompida ou conflitos, com todo remanescente classificado; trabalho crítico preservado.
- SHA de release congelado.
- Zero P0 aberto.
- Escopo v1 aprovado pelo owner.
- Restore ensaiado e rollback conhecido.

## 2. Regra de autonomia

O executor pode autonomamente:

- inspecionar estado;
- testar local e staging;
- preparar configuração sanitizada;
- executar gates não mutantes;
- produzir evidência;
- esperar deployment;
- observar um canário conduzido pelo humano;
- recomendar `GO`, `NO-GO` ou `UNKNOWN`.

O executor deve parar antes de:

- inserir ou rotacionar credencial;
- gerar cobrança;
- pagar;
- emitir ou cancelar NFC-e;
- estornar;
- enviar SMS, WhatsApp ou email real;
- abrir ou cancelar corrida;
- publicar ou alterar iFood;
- ativar 2FA global;
- mudar DNS, ingress ou branch protection;
- criar tag ou fazer deploy de produção;
- restaurar banco ou executar rollback.

Cada ação acima exige autorização explícita com alvo, impacto e rollback declarados. Secrets nunca são colados no chat ou nos artifacts.

## 3. C0 — Trigger e comando

Antes de qualquer mudança, registrar:

- data e janela;
- incident commander humano;
- escopo v1 fechado;
- canais incluídos e excluídos;
- teto financeiro dos canários;
- telefones e emails de teste;
- critérios de abortar;
- janela de rollback;
- comunicação interna;
- política de escrita no iFood.

A proibição vigente de escrita no iFood permanece. Leitura e comparação são permitidas; publicação exige aprovação específica do diff remoto.

## 4. C1 — Auditoria somente leitura

Registrar, sem modificar o ambiente:

1. SHA e tag candidata.
2. CI e merge queue.
3. Imagens e digests.
4. Deployment ativo.
5. Spec vivo sanitizado.
6. Componentes, release job e workers.
7. Postgres, Redis/Valkey e migrations.
8. Backup/PITR e último restore testado.
9. Filas e backlog.
10. Flags mock/debug/autopilot.
11. Adapters configurados.
12. Estado de webhooks.
13. Operadores ativos e prontidão 2FA.
14. Observabilidade.
15. Domínios, TLS, cookies, CSRF e proxy depth.
16. Catálogo, estoque, preço e cupom kill-switch.
17. Presença ou ausência de `go-live-v1`.

Saída obrigatória: matriz `GO`, `NO-GO` ou `UNKNOWN`, com evidência. “Provavelmente” não é um estado.

## 5. C2 — Ensaio em staging

Automação segura:

- full CI;
- Production Contract hermético;
- migrations desde banco vazio;
- migration safety;
- restore rehearsal em cluster temporário;
- rollback de código ensaiado;
- webhook duplicado e fora de ordem com fixtures;
- reconciliação em dry-run;
- teste de carga proporcional;
- smoke de checkout sem cobrança;
- QA de indisponibilidade e fallback.

O cutover fica bloqueado se restore nunca foi exercido ou se o alvo usado for pool PgBouncer em vez da conexão direta exigida para `pg_dump`/`pg_restore`.

## 6. C3 — Configuração de produção

Após o owner inserir credenciais no console seguro, verificar:

- `SHOPMAN_ENVIRONMENT=production`;
- `DJANGO_DEBUG=false`;
- ausência de:
  - `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`;
  - `SHOPMAN_EXPOSE_MOCK_CAPTURE`;
  - `SHOPMAN_MOCK_PIX_AUTO_CONFIRM`;
  - `SHOPMAN_EXPOSE_DEBUG_OTP`;
  - `SHOPMAN_STAGING_AUTOPILOT`;
- Efi em produção;
- Stripe live;
- Focus NFe em produção;
- Postgres e Redis reais;
- domains, cookies e CSRF corretos;
- Doorman, SMTP e ManyChat conforme escopo;
- Sentry e alerta do gestor;
- Maps keys restritas;
- `DOORMAN_TRUSTED_PROXY_DEPTH` correto;
- Machine somente se logística estiver no v1.

Executar um `production-readiness` estritamente read-only: `make production-readiness read_only=1` (`--read-only`). O modo recusa por mecanismo todo SQL que não é leitura (guard `execute_wrapper` e, no PostgreSQL, `SET TRANSACTION READ ONLY`) e reporta o smoke local de gateways, que grava fixtures, como `SKIP`; esse smoke se prova no CI ou em clone descartável. Contrato em [commands.md](../reference/commands.md#release-readiness).

### Gate humano C3

Credenciais são inseridas pelo owner. Alterar env/spec, reiniciar componentes ou disparar deployment exige autorização explícita. Nunca aplicar spec local que possa apagar valores `EV[...]` existentes.

## 7. C4 — Hardening humano

1. Bootstrap admin com senha forte.
2. Enroll TOTP de todos os staff ativos.
3. Guardar recuperação fora do app.
4. Testar recuperação com operador designado.
5. Rodar `check_admin_2fa_ready`.
6. Somente então autorizar `SHOPMAN_ADMIN_REQUIRE_2FA=true`.
7. Configurar allowlist ou Cloudflare Access apenas no `admin.`.
8. Provar login e rate-limit atrás dos proxies reais.

Ativação global de 2FA e mudanças de ingress são gates humanos obrigatórios.

## 8. C5 — QA físico e mobile

### Cliente, em aparelho real

- iOS Safari e Android Chrome;
- login WhatsApp e SMS;
- endereço, GPS/mapa, teclado, autofill e botão Voltar;
- carrinho e checkout;
- troca para o banco no Pix e retorno;
- cartão;
- tracking, SSE e fallback de polling;
- push/deep link, se aplicável;
- acessibilidade básica;
- rede lenta, offline e retomada.

### Operação física

- PDV;
- Gestor;
- KDS;
- Produção;
- impressora;
- som;
- gaveta e agente local;
- fechamento;
- cancelamento/reembolso;
- estoque, hold e release.

A evidência vem do humano e do aparelho. O executor organiza e valida completude; não inventa aprovação por ausência de relato.

## 9. C6 — Observabilidade e logística

- Confirmar Sentry por alerta sintético autorizado.
- Confirmar email, SMS e WhatsApp somente em destinatários de teste autorizados.
- Validar workers, filas, CPU, memória e reinícios.
- Definir dashboard, limiares e responsáveis.
- Para Machine:
  - probe de autenticação;
  - cotação;
  - dispatch e cancelamento apenas após autorização e confirmação de eventual custo;
  - fallback manual documentado.
- iFood permanece read-only sem autorização específica.

## 10. C7 — Freeze, backup e tag

1. Congelar merges e deploys.
2. Anotar SHA, digests e deployment verde anterior.
3. Confirmar PITR e ponto de restauração.
4. Validar classe das migrations e rollback.
5. Declarar `SHOPMAN_MIGRATION_BACKUP_REF`.
6. Com todos os gates pré-cutover verdes, solicitar autorização para criar a tag anotada `go-live-v1` no SHA congelado.
7. Nunca mover ou recriar a tag.
8. Solicitar autorização para ligar `SHOPMAN_GO_LIVE=true`.
9. Solicitar autorização para disparar deployment de produção.

A tag arma a política pós-Go-live da ADR-015; por isso é irreversível como marco histórico, embora o código possa sofrer rollback.

## 11. C8 — Canário financeiro e fiscal

Ordem recomendada:

1. Pedido Pix de baixo valor.
2. Pagamento realizado pelo humano.
3. Confirmar webhook, ledger, pedido, estoque e NFC-e.
4. Pedido de cartão de baixo valor.
5. Confirmar captura, webhook, ledger e NFC-e.
6. Autorizar estorno Pix.
7. Autorizar refund Stripe.
8. Confirmar estados finais, devolução de estoque quando aplicável e reconciliação sem divergência.
9. Confirmar NFC-e sobre o valor com desconto, se houver cupom.
10. Confirmar que o incentivo é Coupon desligável, não alteração do preço-base.

Nenhum clique de pagamento, emissão, cancelamento ou estorno é autônomo.

## 12. C9 — Decisão e expansão

### Critério `GO`

- health e ready verdes;
- checkout funcional;
- Pix e cartão reconciliados;
- NFC-e emitida;
- ambos os estornos comprovados;
- observabilidade entrega alertas;
- workers sem backlog;
- 2FA operacional;
- QA físico e mobile aprovado;
- rollback e restore comprovados;
- zero P0;
- sign-off humano.

Começar com “canário de um”. Convidados limitados só entram depois da primeira janela estável. Beta e soft launch exigem reconciliação do primeiro dia e nova decisão humana.

## 13. Rollback imediato

Disparadores:

- 5xx crítico;
- pagamento sem pedido;
- pedido sem pagamento reconciliável;
- NFC-e falhando;
- divergência financeira;
- migration ou release job falho;
- worker parado;
- auth indisponível;
- estoque corrompido.

Sequência:

1. pausar aquisição, cupom ou canal afetado;
2. congelar deploys;
3. preservar evidência;
4. classificar migration;
5. solicitar autorização para rollback de imagem/código quando seguro;
6. solicitar autorização para restore em cluster novo quando necessário;
7. reconciliar pagamentos antes de reabrir;
8. executar smoke completo;
9. obter autorização humana para retomada.

## 14. Evidência mínima

Pacote sanitizado com:

- SHA e tag;
- IDs de runs e deployment;
- digests;
- timestamp e referência do backup;
- saída dos gates;
- checklist mobile/físico assinado;
- recibos dos canários com IDs mascarados;
- NFC-e mascarada;
- confirmação dos estornos;
- reconciliação;
- alerta sintético;
- decisão `GO` assinada;
- alvo de rollback.

## 15. Condição de parada

O WP termina em `BLOCKED — HUMAN GATE` sempre que faltar credencial, pagamento, emissão, estorno, aparelho, operador, decisão de escopo ou autorização. Ausência de evidência nunca vira verde.
