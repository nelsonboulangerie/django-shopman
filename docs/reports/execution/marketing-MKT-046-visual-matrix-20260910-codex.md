# MKT-046 — Matriz visual e de estados do Marketing

Data: 2026-09-10

Branch isolada: `codex/marketing-irrepressible-excellence-20260908`

Ambiente: worktree local, fixtures sintéticas, zero provider/deploy/produção

## Resultado técnico

A matriz automatizada mantém **69 screenshots determinísticas** e passou integralmente
sem atualização de baseline. Ela cobre os mínimos nominais da seção 15, os modos
transversais e os estados operacionais que precisam ser distinguíveis. Estados sem
screenshot próprio permanecem cobertos pelos testes unitários/de componente e pelos
contratos backend; uma imagem semelhante não é usada como substituto de teste de
estado.

O comando manual de campanha, que estava corretamente bloqueado por
`fire_command_upgrade_required`, foi fechado antes de fotografar o fluxo:

- a Action é a autoridade e carrega `campaign:<pk>:v<version>`, método, URL,
  idempotência e confirmação;
- o request aceita somente `base_version` e regras públicas de audiência; `body`,
  telefone e chaves privadas são recusados;
- versão/CAS, lock do ator, quota/throttle, recent-auth, senha/frase e idempotência
  são validados no servidor;
- zero ou degradação de audiência falham fechados e ainda devolvem comprovante seguro;
- o aceite cria somente um anúncio pendente de revisão, com snapshot, audit event e
  comprovante. Não cria outbox, directive, target ou attempt e não chama provider;
- retry exato devolve o mesmo resultado e chave com payload diferente gera conflito;
- a UI mantém conflito, limite, comprovante e atalho de revisão no mesmo painel.

## Ledger da matriz

| Célula da seção 15 | Baselines | Evidência principal |
|---|---:|---|
| Gate/login global | 7 | anônimo, credencial inválida, rate limit, sessão expirada com draft, forbidden, offline e foco |
| Painel | 8 | pending, degraded, empty, normal, SSE down, dark, forced colors e text spacing |
| Cartão de anúncio | 4 | edição extrema 320, confirmação, conflito de draft e preview fiel |
| Detalhe do anúncio | 5 | 403, expirado, partial, pending e unknown/reconcile |
| Campanhas | 4 | menor mobile, filtros persistidos, densidade/paginação e vazio real |
| Criar/editar campanha | 5 | teclado, regras longas, validação, schema completo e diff de conflito |
| Disparo manual | 9 | zero, loading, degraded, grande, confirmação, throttle, conflito e comprovante |
| Modelos | 6 | outage, dependência, edição mobile, ajuda de variável, variante e vazio |
| Plataformas | 6 | outage, blocked, sandbox receipt, ready, conflito e zoom 200% |
| Histórico | 5 | filtros, partial, cursor/paginação, normal e unknown |
| Alertas pessoais | 5 | sheet, Action, dedupe, popover e Action obsoleta |
| Erros globais | 5 | offline, 404, 500 com referência, manutenção e contrato incompatível |
| **Total** | **69** | `tests/visual/baselines/` |

Geometrias efetivamente exercitadas: 320×568, 375×812, 390×844, 768×1024,
1024×768, 1280×800, 1440×900 e reflow equivalente a zoom 200%. A configuração
fixa locale `pt-BR`, timezone `America/Sao_Paulo`, clock, reduced motion, navegador,
fixtures e ordem de execução. Não há mascaramento nem PII. O limite de diff é
0,1% dos pixels, com threshold de 0,2.

## Conteúdo extremo

- counts 0, 1, 999, 1.000, 99.999 e 1.000.000 têm teste de apresentação pt-BR;
- o blast de 1.999 é assertado na árvore acessível e fotografado em desktop;
- a edição em 320 px combina URL sem quebra, dez hashtags, acentos, texto RTL e emoji
  composto/ZWJ, sem overflow horizontal e sem perder a ação primária;
- mídia ausente, nomes/regras longos, horários com timezone, paginação densa, erros e
  estados sem dados também aparecem na matriz;
- todos os screenshots verificam `scrollWidth <= clientWidth + 1`.

## Pré-medição dos budgets de omotenashi

Esta é uma medição de engenharia com fixtures locais, não a discovery humana do
MKT-047.

| Tarefa | Resultado local | Budget da seção 16 |
|---|---|---|
| Abrir e disparar regra escolhida | 3 decisões significativas incluindo confirmação | ≤4 |
| Mudança de tela até o comprovante | 0; sheet e confirmação sobre a lista | 0 |
| Consultas externas | 0 | 0 |
| Contagem | feedback imediato; fixture normal estabiliza em ~300–450 ms | ≤2 s |
| Aceite | comprovante no mesmo painel; mock responde abaixo de 1 s | ≤1 s |
| Recuperação | idem no duplo toque; conflito atualiza versão; throttle mantém contexto | receipt/retry seguro |
| Certeza | público, versão, receipt, “nenhuma publicação enviada” e próximo passo | consequência + tracking |

O fluxo exige senha de recent-auth e frase exata no disparo. Isso excede o budget
proposto de digitação zero, mas preserva G-H04. A exceção não está aprovada por
inferência: Produto e 5–8 gestores devem validá-la no G-H05/MKT-047. O password manager
reduz redigitação, mas não elimina a confirmação deliberada.

## Provas reproduzíveis

- frontend: **33 arquivos / 221 testes**;
- visual: **69/69**, execução integral sem `--update-snapshots`;
- backend relacionado: **197 testes**;
- Nuxt: typecheck, lint e build de produção verdes;
- Python: Ruff verde, `makemigrations --check --dry-run` sem mudanças;
- `git diff --check` verde.

Comandos centrais:

```bash
cd surfaces/marketing-nuxt
npm run test
npm run typecheck
npm run lint
npm run build
npm run test:visual
```

O procedimento local foi atualizado em
`docs/operations/marketing-local-simulator.md`; não é mais necessário criar anúncio
por shell para testar o disparo seguro.

O ensaio manual no navegador encontrou uma divergência que a suíte anterior não via:
a projeção da campanha estava em versão 1, mas a lista montava a Action na versão 0. O
frontend recusou o comando antes do POST. A montagem foi corrigida para usar a mesma
versão e ganhou teste de regressão. A campanha sintética também apontava para um modelo
que exigia produto sem possuir SKU; a tentativa terminou sem anúncio e a configuração
local foi corrigida pela própria UI para o modelo manual sem produto.

Na repetição, o navegador criou o anúncio local 37, ainda `pending_review`, e mostrou o
comprovante `9844a84d-bd38-4abf-ba0d-5f8b326535f4` com atalho direto à revisão. A
conferência read-only confirmou campanha na versão 3, receipt `completed`, 1 snapshot,
evento `campaign_fired`, **0 outboxes, 0 directives e 0 targets**. A execução parou antes
de publicar.

## Gate humano e limites

Em 2026-09-10, o proprietário confirmou explicitamente os três pontos abaixo:

1. nenhuma ação primária, estado, consequência ou diferença por plataforma ficou
   cortada/ambígua nos viewports e modos obrigatórios;
2. o comprovante do disparo deixa inequívoco que somente um anúncio para revisão foi
   criado e que nenhuma publicação/mensagem saiu;
3. a fricção de senha + frase no disparo é aceitável como exceção de segurança a ser
   levada ao G-H05.

Com isso, o gate humano de MKT-046 está **aprovado**. A confirmação e a observação de
que haverá verificação online não autorizam deploy, staging, produção ou provider
externo, nem autorizam MKT-047 por procuração. O próximo pacote exige Product
Owner e sessões com 5–8 gestores para medir task success, budgets, defaults,
thresholds de confirmação, janela de cancel/edit e prioridade de alertas. Não houve
deploy, staging, produção, provider externo, push, merge ou PR.

## Correção posterior encontrada no E2E

Ao tentar publicar o anúncio local 37 depois da revisão, os fatos já haviam ultrapassado
a janela de cinco minutos. O serviço recusava antes da releitura canônica e tornava o
retry impossível. A correção mantém a janela e todas as guardas: fatos vencidos são
relidos; somente hash idêntico prossegue, preservando os bytes revisados e a vinculação
da confirmação; drift continua recusado e o worker revalida antes do adapter.

O navegador atravessou novamente senha + frase e concluiu o pipeline simulado: receipt
`8b0f402a-6a3d-4556-b9fe-e1dafea361b1`, Instagram 1/1, WhatsApp 12/12,
`provider_calls=0`, `pii=false`. A regressão focada de fatos/aprovação/IA fechou 244
testes antes do ensaio; testes explícitos cobrem snapshot vencido igual e vencido com
drift.
