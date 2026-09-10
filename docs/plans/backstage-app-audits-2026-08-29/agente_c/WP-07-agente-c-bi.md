# WP-07-agente-c — B.I.

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `shopman/backstage/bi/`, `projections/bi_*`, telas de B.I. no Admin
**Objetivo:** o número que o gestor lê é o número que ele acha que está lendo — e quem vê dinheiro é quem audita.

## Diferenças vs. WP-07 (Agente G) e WP-07-agente-d

**O achado mais grave alegado pelo Agente D — "egress de financeiro para provedor de IA" — é um falso
positivo.** Verifiquei campo a campo, porque era a acusação mais pesada dos nove WPs. O que sai são
**agregados de venda**: totais e período anterior, série por dia, faturamento por canal, top 10 SKUs com nome,
pedidos por hora e por dia da semana. **Não sai nenhum pedido, nome de cliente, telefone, CPF, apuração de
caixa nem nome de operador.** A fronteira está documentada **três vezes** — docstring do módulo, docstring da
função, e o plano de fundação de dados — e o código a respeita. Só roda com a chave de IA configurada, e o
desligamento já é construído: sem chave, o botão nem aparece.

É **decisão de negócio para o dono**, não bug — e a proposta do Agente D (tirar nomes de SKU, agregar dia para
semana) degradaria o recurso para resolver um problema que ninguém decidiu que existe. Vira pergunta 1.

**O achado realmente grave nenhum dos dois viu, e está vivo no main.** Ver P0-1.

**Refutadas duas hipóteses do briefing original:** a agregação **não** soma pedidos cancelados (são excluídos
das vendas e das linhas, contados à parte, com teste); e **não há PII de cliente** nas projections de B.I. —
elas devolvem só contagens, e não existe export CSV no B.I.

**Recalibrados:** o exemplo/cenário de métrica proibida vira P1 (a API **fecha** com 403 — o dano é confiança,
não vazamento); janela inválida fica P2, e a proposta do Agente D (motivo de normalização no contrato) é a
certa contra a do Agente G (400 seco, que reverte decisão documentada).

**Agravado:** o bloco de Clientes é pior que o descrito — **cinco** dos seis blocos são globais, não quatro.

**Novos:** o 500 vivo no explorador; a série longa somando o que não se soma; o alarme que converte ausência
em zero; a corrida de autorização no Admin de alertas; a janela em UTC pulando um dia à noite.

## Pré-requisitos

Nenhum. **Nenhuma permissão nova** — `setup_groups` não muda.
⚠️ A colisão a vigiar é `_normalize_window`, importado por cinco projections.

## Achados priorizados

### P0-1 — Quebra de caixa por operador derruba o explorador, e a tela fica em branco

**Regressão viva no main, e nenhum dos dois agentes a viu.**

**Mecanismo.** O commit `d76a66c70` (21/08, "a custódia é da GAVETA") removeu `CanonicalShift.operator_key` e
o substituiu por `operator_keys` mais `sole_operator_key`. A docstring da dataclass diz isso em voz alta:
*"Não há `operator_key`"*. O commit atualizou os alertas e a projection de caixa, mas **não** atualizou
`bi_explore.py:859`, que ainda acessa o atributo removido. A dataclass é `frozen` com `slots` — provado em
runtime: `AttributeError`.

Do clique ao efeito: o gestor-auditor abre **Explorar** e escolhe o chip de exemplo **"Quebra de caixa por
operador"**. A view valida a gramática, o laço roda no primeiro turno fechado da janela e levanta
`AttributeError`. Isso não é o erro de domínio que o `except` da view captura; o handler de erro da casa
devolve `None` para exceção não-DRF; sai **500 sem `detail`**. Na tela, o painel só renderiza o `detail` — e
como não há, e o relatório é nulo, **a tela fica em branco, sem mensagem nenhuma**. Pior que stacktrace:
silêncio.

**Por que passou.** O único corte que funciona é por tempo — que é justamente o que o dropdown escolhe
sozinho. E **o único teste que toca o caminho assere 200 num banco sem nenhum turno fechado**: o laço não
executa. Smoke de banco vazio escondendo bug de linha, que é uma armadilha já catalogada nesta casa.

**Fix — duas opções, e a segunda é a certa:**
- (a) uma linha, restaura o comportamento usando `sole_operator_key` com fallback para "compartilhado";
- (b) **preferível**, e coerente com o commit que causou a regressão: a dimensão de quebra de caixa vira
  **gaveta**, não operador. Hoje o explorador atribui quebra a **pessoa** exatamente onde o resto do sistema
  decidiu, por escrito, que não se pode.

### P1-1 — O alerta de faturamento entrega reais ao balconista

O alarme monta *"14/08 (sexta) faturou R$ 3.412,00, 48% do esperado (R$ 7.100,00 na média de 4 sextas)"*. A
redação só é filtrada para métricas do conjunto "somente auditoria", e esse conjunto tem **um** item. A
mensagem íntegra vira alerta de operador, servido sob um predicado que é um **OR de todas as personas
operacionais** — e o grupo Caixa satisfaz dois deles.

Isso contraria uma decisão escrita no próprio `setup_groups.py`: *"Dinheiro fica de fora, e não é
esquecimento… quem vê dinheiro é quem audita."* E a regra **está ligada** — nasce ativa no seed e é avaliada
todo ciclo do worker de manutenção.

**Fix.** Não basta mover a métrica para "somente auditoria" — aí o gerente perde o aviso. O correto é uma
**mensagem pública própria** ("o faturamento de tal dia ficou em X% do esperado; detalhe no B.I."), mantendo a
leitura íntegra no evento de alerta, que já é gateado. Mais um guardrail de teste: nenhum alerta de operador
vindo de regra de B.I. contém `"R$"`.

### P1-2 — A série longa soma o que não se soma

Nenhum dos dois viu, e é exatamente o objetivo declarado do WP ("confiança dos números").

Acima de 120 pontos a série é agrupada por semana; acima de 740, por mês. A docstring do agrupador é honesta:
*"devolve os dias de cada balde para a página somar **do jeito da métrica dela**"*. **A página não faz isso** —
ela soma incondicionalmente.

Seis métricas com dimensão de tempo **não são aditivas**: ticket médio, rendimento percentual, share de
indisponibilidade, pico de grupos no salão, receita por lugar-hora e giro de mesas. O gestor escolhe **1 ano**
mais **Ticket médio** mais **Tempo**, e a barra da semana mostra ~7× o ticket real — formatada como reais,
"R$ 178,50", perfeitamente convincente. Rendimento passa de 100%.

**Fix.** O contrato já tem `unit`. A versão barata são duas linhas na página, com uma lista explícita de
métricas de média e pico. A versão limpa, que prefiro: **o servidor declara `aggregation: "sum" | "mean" |
"max"` no spec da métrica e a UI obedece.** Hoje a regra mora em duas cabeças e nenhuma no contrato.

### P1-3 — Exemplo e cenário salvo de métrica proibida

Mantido dos dois, recalibrado para P1: a API **fecha** com 403, então o dano é confiança, não vazamento. Com o
P0-1 no ar, o dano é pior — o chip nem 403 dá, dá tela branca.

**Fix — três pontos pequenos:** filtrar os exemplos também pelas métricas permitidas; validar a família
audit-only contra o `request` ao salvar cenário; e a listagem de cenários filtrar contra a permissão
**corrente**, para que quem perdeu `audit_shift` pare de ver as próprias views de caixa.

### P1-4 — "Clientes" mostra base global sob rótulo de período

Agravado: **cinco** dos seis blocos são globais — segmentos, total, com insight, em risco e ticket médio. Só
"novos por semana" usa a janela, que é calculada e devolvida no contrato como se governasse tudo. O gestor
troca de 28 dias para 1 ano, vê as datas mudarem no cabeçalho e os quatro KPIs **não** mudarem — e conclui que
a base está estagnada.

**Fix:** `scope: "global" | "window"` por campo no contrato, e dois títulos na página ("Base atual" × "No
período"). **Não** recalcular RFM por janela — o insight é agregado do guestman e o B.I. declara que só lê. O
Agente D está certo nesse limite.

### P2-1 — Janela inválida e clamp silenciosos

Data inválida é engolida; janela invertida é corrigida; acima do máximo é clampada — tudo sem dizer. A
proposta do Agente G (400 seco) reverte a decisão documentada de que janela inválida cai no default; a do
Agente D (motivo de normalização no contrato) é a certa. Acrescento: **o clamp não tem comentário nenhum**, então
documentá-lo faz parte do fix.

**Fix:** a normalização devolve o motivo; os relatórios publicam; a UI diz "período ajustado para o máximo de
5 anos". Sem 400 em endpoint de leitura.

### P2-2 — O alarme trata ausência como zero e grita

A série de vendas **não devolve o dia quando não há venda registrada**, e diz isso em letra grande: *"ausência
não é zero… não pode entrar numa média como um dia de faturamento zero"*. O alarme viola o contrato do módulo
que ele consome: converte ausência em `0.0`, o share vira zero, e **dispara** *"ontem faturou R$ 0,00, 0% do
esperado"*.

Quando acontece na prática: dia sem contexto carimbado em que o calendário diz "aberto" e a casa não abriu
(feriado não cadastrado); ou dia cuja fonte é o histórico e o lote ainda não entrou. Todas as outras ausências
do módulo se abstêm corretamente — esta é a única que inventa um número.

**Fix — uma linha**, no dialeto que o resto do arquivo já fala: sem dado, leitura sem valor e sem disparo.

### P2-3 — Corrida de autorização no Admin de alertas

O admin guarda o usuário do request num **atributo de classe**, e `ModelAdmin` é singleton no registro do
Django. O deploy roda **daphne** — ASGI, requisições concorrentes no mesmo processo, views síncronas num
threadpool. Duas aberturas simultâneas da lista — uma do Dono, outra da Gerente — podem render a coluna
"última leitura" da Gerente usando a identidade do Dono, e aí a mensagem completa da quebra de caixa aparece
para quem não deve vê-la. O `get_fieldsets` do mesmo arquivo faz certo, com o `request`.

**Fix:** mover a redação para `get_queryset`, que recebe o `request` — como o admin de eventos ao lado já faz.
Apagar o atributo de classe e o override inteiros.

### P2-4 — A janela pula um dia à noite

A resolução de intervalo usa `toISOString()`, que é **UTC**. Em horário de Brasília, a partir das 21h a data
UTC já é a de amanhã. Consequências, todas silenciosas: o preset "Dia" manda amanhã e devolve "Nada no
período"; os presets móveis deslocam a janela inteira um dia à frente, incluindo um dia que não existe e
descartando o dia mais antigo real. E o servidor **não clampa a data final a hoje**, então nada corrige.

Colide com a convenção da casa de usar data local, não UTC. **Fix — uma linha** (e a mesma função aparece
duas vezes, com o mesmo defeito).

### P2-5 — Sem célula mínima em famílias financeiras

Mantido dos dois, com o custo que o Agente D declarou e eu confirmo: a linha do explorador não carrega a
contagem. Escopar às famílias de vendas, pagamento e caixa, e só nas dimensões finas.

P2 porque a padaria é uma só e o público do B.I. é o gestor: o risco de reidentificação é baixo e o custo é
médio. **É o candidato natural a sair se o escopo apertar.**

### P3-1 — Resíduo de rename no seed, e sobrescrita silenciosa de cenário

O rótulo da métrica de quebra de caixa no seed ainda fala em "por operador", depois do rename e da migração —
e é o texto que o gestor lê no Admin. Uma linha. E salvar um cenário com nome já usado **apaga o corte
anterior em silêncio**, enquanto a tela diz "Cenário salvo." Devolver `created` e a UI dizer "Cenário
atualizado."

## Verificado sem achado

Cancelados são corretamente excluídos das vendas e das linhas, e contados à parte, com teste. As projections
de cliente devolvem **só contagens** — nenhum nome, telefone, documento ou id. Não existe export CSV no B.I.

## RBAC / `setup_groups`

**Nenhuma mudança.**

## Testes

1. Turno fechado com contagem na janela + explorar quebra de caixa por operador → 200. **Hoje é 500.**
2. Nenhum alerta de operador vindo de regra de B.I. contém `"R$"`.
3. Métrica não aditiva em janela longa: o valor do balde é a média (ou o máximo), não a soma.
4. Exemplo de métrica proibida não é oferecido a quem não pode; salvar cenário de família audit-only sem
   permissão devolve 403; a listagem some quando a permissão some.
5. Cada campo do bloco Clientes declara seu escopo; trocar a janela muda só o que é de janela.
6. Janela invertida e clampada publicam o motivo no contrato.
7. Dia sem venda registrada **não** dispara alerta de faturamento zero.
8. O admin de alertas não guarda usuário em atributo de classe (assert estrutural + teste concorrente, se
   viável).
9. Às 22h de Brasília, o preset "Dia" resolve para hoje, não para amanhã.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Observação |
|---|---|---|
| `shopman/backstage/api/bi.py` (`_normalize_window`) | **MÉDIO-ALTO** | importado por **cinco** projections — mudar a assinatura toca todas |
| `shopman/backstage/projections/bi_explore.py` | BAIXO | P0-1 |
| `shopman/backstage/bi/alerts.py` | BAIXO | P1-1, P2-2 |
| `shopman/backstage/projections/bi_customers.py` | BAIXO | P1-4 |
| `shopman/backstage/admin/bi_alerts.py` | BAIXO | P2-3 |
| `surfaces/*/presentation/bi.ts`, `explore.vue` | BAIXO | P1-2, P2-4 |
| `config/management/commands/seed.py` | **ALTO** | arquivo grande e disputado; **uma linha** de rótulo — agrupe com outras mudanças de seed se houver |

## Fora de escopo

Recalcular RFM por janela (é do guestman). Desligar ou degradar o assistente de IA sem decisão do dono.
Qualquer export novo.

## Perguntas para o dono do produto

1. **Agregados de venda podem sair para a API da Anthropic?** É o que acontece hoje quando o gerador de
   cenários é usado: totais, série por dia, faturamento por canal e os dez SKUs mais vendidos, com nome.
   Nenhum dado de cliente, caixa ou operador. Está documentado em três lugares e o código respeita a
   fronteira, e o recurso desliga sozinho sem a chave configurada. **Não é um bug — é uma decisão sua**, e
   nenhum dos agentes anteriores tinha como tomá-la. (Verificar também se a chave está de fato configurada no
   alpha: ela é secret no spec e não consegui ler o valor.)
2. **A quebra de caixa se atribui à gaveta ou à pessoa?** O resto do sistema decidiu, por escrito, que é da
   gaveta. O explorador ainda oferece "por operador" — e é o que quebra hoje. Consertar a linha ou mudar a
   dimensão são respostas diferentes para a mesma pergunta.
3. **O alerta de faturamento deve chegar ao balconista?** Hoje chega, com o valor em reais. Proponho mensagem
   pública sem valor e detalhe no B.I. para quem tem a permissão — mas quem decide quem vê faturamento é você.

## Prompt para agente executor

~~~text
Execute WP-07-agente-c (B.I.).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-07-agente-c-bi.md
- shopman/backstage/bi/canonical.py:216 (a docstring que diz "nao ha operator_key")
- shopman/backstage/projections/bi_explore.py:73, 859
- shopman/backstage/bi/alerts.py:126-130, 209, 216-218
- shopman/backstage/projections/sales_series.py:40-44 (o contrato "ausencia nao e zero")
- shopman/backstage/projections/bi_customers.py:48, 69-93
- shopman/backstage/api/bi.py:45-52, 254-309  ⚠️ _normalize_window e importado por 5 projections
- surfaces/*/app/presentation/bi.ts:246, 303-304, 354-377 + explore.vue:96-103
- shopman/backstage/admin/bi_alerts.py:48-61

Fases:
1. P0-1: escreva o teste 1 ANTES (turno fechado COM Entry na janela — banco vazio nao
   reproduz). Depois decida entre consertar a linha ou mudar a dimensao (pergunta 2).
2. P1-1 + P2-2: mensagem publica sem R$ e ausencia que nao vira zero. Guardrail: nenhum
   OperatorAlert de regra de B.I. contem "R$".
3. P1-2: prefira declarar aggregation no MetricSpec e a UI obedecer, em vez da lista no
   cliente. A regra deve morar no contrato.
4. P1-4, P1-3, P2-1 (motivo de normalizacao — NAO 400 seco), P2-3, P2-4, P3-1.
5. P2-5 so se o escopo permitir; e o primeiro a sair.

NAO degrade o gerador de cenarios sem a resposta 1 — o egress e agregado, documentado
tres vezes, e o codigo respeita a fronteira. Nao e bug.
NAO recalcule RFM por janela (e do guestman).
~~~
