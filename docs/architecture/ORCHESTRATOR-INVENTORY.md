# Inventário do orquestrador

Este foi o artefato de entrada do WP-7. O piloto de extração executado, com cenário
congelado, métrica antes/depois e regra de aborto, está em
[`PROMOTION-PILOT.md`](PROMOTION-PILOT.md).

Há dois eixos independentes:

- `orchestrator-inventory.json` classifica toda fonte Python de produção em
  touchpoints e claims de símbolos. `support_claims` só aceita leitura, contrato,
  configuração e infraestrutura; decisão e composição sempre apontam para uma
  unidade semântica. As responsabilidades da fonte são derivadas desses dois
  conjuntos, portanto uma fonte multifuncional não precisa mentir com `mixed`.
- `orchestrator-units.json` registra decisões e composições reais por pergunta,
  dono/entrypoint, símbolos congelados, autoridades normativas, fronteiras
  observadas no AST e testes.
  Arquivo não é sinônimo de unidade: uma fonte pode responder várias perguntas.

O checker é stdlib-only e não importa Django. Ele compara o inventário com o
filesystem, aplica integralmente o schema JSON usado pelo repositório, resolve
entrypoints e testes, exige cobertura disjunta de todo símbolo top-level relevante
e recalcula domains, ports, events, directives, configuração e touchpoints. Cada
`authoritative_symbol` precisa pertencer à unidade e ser alcançável pelo entrypoint
público no grafo AST qualificado. O fechamento das fronteiras atravessa helpers de
suporte qualificados mesmo em outro módulo, mas para antes de entrar em outra unidade
semântica; helper privado não pode fingir ser API. Não existe
comando de geração: classificação, perguntas e titularidade são decisões
versionadas.

## Evidência obrigatória

O manifesto mergeável não admite `tests: []`, teste aproximado, entrypoint privado
ou autoridade inalcançável. A referência deve seguir a coleta do pytest e não pode
estar estaticamente pulada na função, classe ou no módulo. A relação do teste exige
import/binding qualificado e uso da unidade; coincidências lexicais como `send`,
`connect` e `sync` não contam.

`out_of_extraction` também não é uma dispensa discricionária. O gate exige que ele
seja verdadeiro se, e somente se, a responsabilidade for exclusivamente `leitura`,
tanto na fonte física quanto na unidade semântica. Unidades de decisão, composição,
contrato, configuração ou infraestrutura não podem usar o campo para escapar do
programa. Por isso, um teto percentual ou um prazo por WP mediria a quantidade de
read models legítimos, não dívida: a proteção relevante é a equivalência semântica
já executável, combinada com a proibição absoluta de lacunas de teste.

## Snapshot auditável após o piloto de promoção

O snapshot posterior ao piloto do WP-7, integrado pela PR #1860, contém:

- 442 unidades semânticas; 14 com `out_of_extraction`, todas e somente de `leitura`;
- zero `test_gap_reason` não nulo e 442 unidades com evidência direta em `tests`;
- 487 fontes físicas; 32 com `out_of_extraction`, todas e somente de `leitura`.

Em cada execução, o gate publica `unit_owner_prefixes`: a distribuição pelo primeiro
segmento do capability owner (o trecho anterior ao primeiro ponto). Isso permite
acompanhar a concentração do inventário sem transformar leitura legítima em dívida.
Neste snapshot, a distribuição completa é:

```text
account=10, accounting=1, auth=2, availability=5, calendar=10, cart=6,
catalog=28, channel=9, checkout=5, delivery=15, deployment=1, directive=3,
external-egress=1, fiscal=27, fulfillment=12, identity=12, ifood=25,
loyalty=7, marketing=53, menuboard=1, notification=14, offer=2,
operations=7, operator-notification=1, operator-passkey=2, order=50,
payment=26, pos=22, preorder=2, pricing=11, production=33, promotion=11,
purchasing=4, receiving=1, remote-mutation=1, returns=2, runtime=1,
shop=1, staging=2, stock=4, suggestion=2, surface=1, waitlist=9
```

Na recuração foi encontrada e removida uma violação de titularidade: Meta, Google e
TikTok repetiam `_external_allowed`, enquanto a decisão canônica de segurança de
egress é `shopman.shop.adapters._external:inert`. O PR #1857 eliminou as três cópias
sem shim nem flag e fez os adapters chamarem a autoridade canônica. O inventário não
legitima as antigas cópias como policies nem as esconde em suporte.

## Defaults de instância

`orchestrator-instance-debt.json` registra defaults de runtime ainda presos à
instância e defaults estruturais em zonas sensíveis (paleta, regras de sugestão e
bootstrap comercial). O detector ignora comentários e docstrings; ele não afirma
descobrir nomes próprios arbitrários. Sua fronteira falseável é: nomes conhecidos
em literais executáveis e as categorias estruturais declaradas devem ter finding
pendente até WP-6/WP-11 removê-los. O gate reprova finding órfão, evidência stale
ou ocorrência conhecida sem triagem.

## Execução

```bash
make orchestrator-governance
```

O alvo roda o gate canônico e todas as fixtures negativas sem carregar o plugin
Django do pytest.
