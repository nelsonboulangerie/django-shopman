# Guard de tema obrigatório na fila

## Causa comprovada

A #2094 integrou pelo commit `6886e6d7ab95747eac2ee7ab798dbb629c73f3d2`. O run `41562747556` é de `merge_group` e testou exatamente esse SHA. O job `125676918306`, "Versões das superfícies", falhou porque o tema tinha fingerprint `9262f57f…` e o aceite registrava `1ac497e6…`. O job executou; não foi pulado por escopo.

Todos os 27 contextos então obrigatórios tiveram SUCCESS no SHA integrado. O contexto vermelho não estava na branch protection nem no seu espelho versionado; o ruleset `20999744` tinha somente a regra de merge queue. A fila aplicou o conjunto incompleto que estava configurado. Não há evidência de bypass.

## Correção restrita

"Versões das superfícies" passa a ser obrigatório, com app ID 15368. A atualização preserva strict e todos os pares contexto/app ID anteriores, registrados em `protection-before.json`. O espelho recebe o mesmo contexto. O job já roda incondicionalmente em `pull_request` e `merge_group`, sem modificar seu nome.

O gate canônico também passa a reprovar a remoção desse contexto do espelho, mesmo que o job continue existindo. Antes ele só verificava o sentido inverso: cada contexto listado precisava de um produtor. A regressão tem dois cenários, com e sem o contexto obrigatório, mantendo o produtor nos dois.

Não basta ligar `needs` nos apps: isso pode produzir consumidores skipped sem tornar obrigatório o guard que falhou. Exigir diretamente o contexto preserva a consequência do resultado FAILURE.

## Validação

- Ruff dos dois arquivos Python: `All checks passed!`.
- `python3 scripts/check_canonical_docs.py`: passou, 28 checks produzidos em PR e merge group.
- `pytest shopman/shop/tests/test_required_status_checks_gate.py --no-cov -q`: 9 passaram.
- Os mesmos testes com o script original: 1 falhou e 8 passaram, confirmando que a regressão detecta o guard produzido mas opcional.

## Regularização visual integrada

A #2095 integrou em 03/11/2026 às 11:46:49 UTC pelo commit `433c27c026b0c83f692be164004cb4165c96a6e5`. O aceite publicado pelo autor registra Pablo Valentini, a data e o escopo das abas, moldura dourada e X do aviso no celular. O fingerprint recomputado corresponde exatamente ao contrato (`sha256:e4413006a65766677ed42b1669faf0de31fcaaa2cd7784ec3b992ffe08092290`). O guard de tema passou no head e no merge group.

Esta PR incorporou esse main sem editar UI, baseline ou aceite. Após a atualização, o guard de tema e o gate canônico com comparação viva passaram; os nove testes isolados do leitor de checks também passaram. O espelho mantém os 28 pares contexto/app ID exigidos na proteção remota, com strict preservado. A pendência que exigia draft foi resolvida pela frente autora.

## Conferência dos demais gates

Security Gate, Production Contract, Operator Groups Contract e Coverage Gate já estão entre os obrigatórios. O job agora exigido também abriga os guards de versões, registro de superfícies, componentes, atalhos e layouts/tokens do operador.

Também foram observados contextos não obrigatórios como "Contrato canônico das superfícies", supply chain, PWA, status e preview interno. Eles não foram acrescentados por suposição. O contrato canônico gera as matrizes que vários consumidores usam; sua garantia de falha fechada merece verificação específica, mas não foi demonstrada outra integração indevida nesta auditoria.
