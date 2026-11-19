# Conformidade: como um adaptador roda a suíte, e a matriz

> **Estado:** rascunho
> **Dono:** F3 cria, F11 fecha

Responde: como um adaptador prova que implementa as portas, como cada teste K declara o que
prova, e como a matriz teste × invariante é mantida. A fonte é o código:
`conversational_commerce/testing/conformance/`.

Derivado de: v2 Apêndice A e plano do framework, decisões 8 e 9 e seção 3.10.

## 1. Duas camadas de prova

1. **Forma da porta** (`harness.py`). Tipos, capacidades e as garantias mínimas observáveis
   de cada porta (seção 2 do `03-ports.md`). Roda igual contra os falsos e contra o adaptador.
2. **Testes K** (K01 a K40, v2 A.2). O comportamento do núcleo sobre as portas. Cada WP
   escreve os seus (plano 3.10) e marca cada um com `@conformance`.

## 2. Como um adaptador roda a forma

O adaptador monta um `HarnessEnv`: o contexto confiável, a `ClockPort` dele e entradas que
existem no sistema dele (mensagem bruta do canal, item, carrinho, outro sujeito para a
checagem de autorização por objeto, e `fresh_terms`, que cota o carrinho). Depois chama,
porta por porta:

```python
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks

failures = run_checks("commerce_execute", my_executor, env)
assert failures == []
```

`run_checks` não depende de pytest. Ele devolve a lista de `CheckFailure(port, check,
message)`, e vazio é verde. O arnês usa duas guardas de teste: `AllowGuard`, que confere que
o executor a chamou, e `RefuseGuard`, que confere que a recusa não deixa efeito.

## 3. `@conformance`

```python
from conversational_commerce.testing.conformance import conformance

@conformance("K13", invariants=("N13",), scope="real_mechanism")
def test_two_workers_same_episode_version(...): ...
```

- `scope` é obrigatório: `core` (provado com os falsos), `adapter` (o adaptador real precisa
  repetir) ou `real_mechanism` (só vale no mecanismo do adaptador; no núcleo é simulação).
- O decorador confere K, escopo e invariantes na importação e não depende de pytest.
- Argumentos sempre literais: a matriz lê pelo AST, sem importar os testes.

O escopo **exigido** de cada K, e o WP dono, estão em `conformance/catalog.py`, transcritos
do plano 3.10. Um teste que declara escopo diferente do exigido é problema na matriz.

## 4. A matriz

```bash
python -m conversational_commerce.testing.matrix                 # marcados e faltantes
python -m conversational_commerce.testing.matrix --path <testes>  # inclui os do adaptador
python -m conversational_commerce.testing.matrix --check          # falha se faltar K
```

Gerada dos decoradores, nunca escrita à mão (decisão 9): nenhuma lista central para os WPs
editarem. Sem `--check`, ela lista e só falha em problema de forma: K desconhecido, escopo
inválido, argumento não literal ou escopo diferente do exigido. Com `--check`, falha também
se faltar algum K. O `--check` passa a ser exigido pelo F11; até lá a listagem diz o que
falta.

Estado ao fim do F3: K38 marcado (F0, `core`). O K39 está provado no F2
(`tests/catalog/test_k39_profile_lines.py`, PR do F2) e ganha o decorador quando os dois PRs
estiverem no `main`. Os demais são dos WPs F4 a F10.

## 5. A fechar no F11

- `--check` dentro da suíte, com os 40 marcados.
- Um K de escopo `adapter` ou `real_mechanism` precisa do teste correspondente no adaptador
  (`--path`) para a matriz fechar no adaptador.
- Rede bloqueada e as seis jornadas juntas.
