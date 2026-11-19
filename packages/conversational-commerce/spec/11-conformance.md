# Conformidade: como um adaptador roda a suíte, e a matriz

> **Estado:** vigente
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
se faltar algum K.

Desde o F11 os 40 estão marcados no núcleo, e o `--check` roda dentro da suíte
(`tests/test_d1_exit.py`).

## 5. O critério de saída do D1 (F11)

`tests/test_d1_exit.py` é o critério, como teste:

| Prova | Como |
|---|---|
| A matriz fecha | `report` sem problema nem K faltando, e `matrix --check` devolve 0 |
| A checagem reprova o que deve | o teste do teste: K sem escopo, K desconhecido, escopo diferente do exigido e K faltando (a suíte sem o arquivo do K39) |
| As seis jornadas juntas | J1 a J6 no mesmo núcleo e sobre os mesmos falsos, cada uma no seu episódio |
| A especificação vigente | os doze arquivos de `spec/` com `Estado: vigente` |

A rede bloqueada é a fixture `autouse` do `conftest.py`, e vale para toda a suíte; o K38 é
`test_k38_no_infrastructure.py`; o wheel limpo é `python scripts/wheel_suite.py
conversational-commerce`, na raiz do monorepo.

[DECIDIDO] As jornadas J3 e J5 conferem o texto da promessa sem o instante do prazo, porque
o prazo é o da fila a partir do relógio, e o relógio depende de quantas jornadas rodaram
antes. O instante exato fica provado nos testes do F9 (`tests/commitments/`).

## 6. O que fica para o adaptador

Os K de escopo `adapter` (K01, K02, K03, K06 a K10, K15 a K18, K20, K22, K23, K24, K27,
K33, K35, K36, K39) e `real_mechanism` (K11 a K14) passam no núcleo sobre os falsos, mas só
valem para uma implementação quando o adaptador roda o teste correspondente no mecanismo
dele e a matriz fecha com `--path <testes do adaptador>`. Até lá, a matriz do núcleo fechada
é o D1, não a prova do adaptador.
