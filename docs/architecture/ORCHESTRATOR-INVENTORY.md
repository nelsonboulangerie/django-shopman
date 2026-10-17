# Inventário do orquestrador

Este é o artefato de entrada do WP-7; não é o piloto de extração.

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
