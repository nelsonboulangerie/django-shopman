# ADR-049 — Comércio conversacional: pacote puro no monorepo, contratos em dataclass, conformidade como segunda implementação

**Status:** Aceito
**Data:** 2026-11-17
**Escopo:** `packages/conversational-commerce/`, o adaptador da Concierge no orquestrador, `scripts/wheel_suite.py`
**Origem:** compromisso DEV-2026-041; pesquisa `docs/research/INTELIGENCIA-COMERCIO-CONVERSACIONAL-v2.md` (11.4 e 15.4); plano `docs/plans/COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md` (seção 2, decisões 1a a 10; WP F0)

---

## Contexto

O dono quer um framework **genérico** de comércio conversacional: qualquer canal, qualquer
modelo, qualquer sistema de comércio por trás. A Concierge (a Nice) é o primeiro caso de uso,
não o desenho. A pesquisa v2 fixou a regra de corte: o que não puder ser dito sem nomear uma
empresa, um canal, um framework web ou um ramo de negócio pertence ao adaptador ou ao perfil,
nunca ao núcleo.

Três perguntas de arquitetura precisavam de resposta antes do primeiro contrato:

1. Onde o núcleo nasce, e quando sai.
2. Como os contratos são definidos sem trazer dependência.
3. Como conciliar a porta de comércio, que no começo tem um único sistema real por trás (o
   Shopman), com a regra do [ADR-001](adr-001-protocol-adapter.md) de só criar Protocol com
   duas implementações reais.

## Decisão

1. **Pacote Python puro, dentro do monorepo.** Distribuição `conversational-commerce`, import
   `conversational_commerce`, em `packages/conversational-commerce/`, com layout plano como os
   irmãos e testes dentro do pacote. `requires-python >= 3.12`, licença FSL-1.1-ALv2, **zero
   dependências**; o único extra é `[testing]` = `pytest`, para a suíte de conformidade. O
   nome não leva Nice, Concierge, Shopman nem o sufixo `-man`, que é a família da suíte: o
   pacote não pode dizer nada do Shopman.

2. **O núcleo não importa infraestrutura, e isso é prova, não disciplina.** Três travas:
   - **K38** (`conversational_commerce/tests/test_k38_no_infrastructure.py`): varre o pacote
     por AST e reprova import fora da biblioteca padrão e do próprio pacote (inclusive
     `importlib.import_module` e `__import__`, e import dinâmico de nome não literal), e
     importa todo módulo num processo novo conferindo que nada de fora entrou em
     `sys.modules`. Só `tests` e `testing` podem importar `pytest`. O teste do teste planta
     um módulo que importa `django` e exige a reprovação.
   - **Sem rede:** fixture `autouse` no `conftest.py` do pacote bloqueia `socket.socket` e
     `socket.getaddrinfo`; o pytest roda com `-p no:django`.
   - **Wheel limpo:** `scripts/wheel_suite.py` instala o wheel num venv vazio, roda a suíte
     importada do site-packages e exige que o Django **não** esteja instalado ali.

3. **Contratos em `dataclass(frozen=True, slots=True)` da biblioteca padrão; o JSON Schema é
   gerado** a partir deles, versionado no repositório, com teste de deriva. Python é a fonte
   única. Pydantic fica recusado (dependência e acoplamento de versão com os pinos do
   Shopman); esquema primeiro fica recusado enquanto só houver consumidor Python (dois donos
   para um contrato e uma cadeia de geração). Quem consumir de outra linguagem lê o esquema
   exportado.

4. **A porta de comércio nasce com uma implementação real e o backend falso de referência
   como a segunda, e isso cumpre o ADR-001.** A leitura é a que o
   [ADR-044](adr-044-substituibilidade-na-borda.md) (item 3) já fixou: substituível é quem
   implementa o **mesmo contrato semântico**, e a prova de que implementa é passar a suíte de
   conformidade. O backend falso não é mock de teste nem implementação "para o futuro": é o
   sistema de comércio mínimo que cumpre o contrato inteiro (reserva, recibo, idempotência,
   falhas injetáveis), distribuído no wheel em `conversational_commerce.testing`, e é ele
   que prova a independência de plataforma. As portas de canal e de modelo já têm mais de
   uma implementação real.

5. **O Shopman instala o pacote**, como instala os irmãos: dependência no `pyproject.toml` da
   raiz, linha no `Dockerfile` e no `scripts/check_constraints.py`, `pip install -e` no
   `make install`, e o alvo `make test-conversational-commerce` dentro de `test-cores` e
   `test`. O alvo fixa `PYTHONPATH` no próprio pacote, para não testar uma instalação
   editável de outro checkout.

6. **O adaptador mora no orquestrador.** Portas de comércio sobre Orderman, Offerman,
   Stockman, Guestman, Craftsman e Payman, canal, modelo e equipe são implementadas em
   `shopman/`, como hoje. O núcleo guarda referência e evidência; `Session`, `Order`,
   pagamento e estoque continuam sendo a verdade do negócio. Não nasce um segundo livro de
   pedidos.

7. **Critério de extração (degrau D7 da v2):** o pacote sai para repositório próprio quando
   existir o **segundo adaptador real**, sobre outro sistema de comércio que não o Shopman.
   Antes disso, extrair só cria dois lugares para mudar um contrato. A especificação
   (`packages/conversational-commerce/spec/`) e os vetores de teste já moram com o pacote,
   para viajarem com ele.

## Consequências

- Os WPs F1 a F11 escrevem só dentro de `packages/conversational-commerce/`; qualquer import
  de Django, SDK de modelo ou de canal ali reprova o K38 antes de chegar à revisão.
- O `wheel_suite.py` passa a aceitar pacote fora do namespace `shopman.` e sem `pytest-django`,
  lendo o tipo do `pyproject` de cada um. Os 13 apps Django da suíte seguem com o contrato
  de sempre (`shopman.<pacote>`, extra `[dev]`, `pytest-django`), e um `pyproject` que não
  caiba em nenhum dos dois tipos reprova, em vez de cair no caminho mais frouxo.
- A regra "Protocol só com duas implementações reais" do ADR-001 não muda: a segunda
  implementação da porta de comércio é real no sentido que conta (cumpre o contrato e passa
  a suíte). Um backend falso que não passe a suíte não conta como implementação.
- Mudar um contrato pede, no mesmo PR, a dataclass, o esquema gerado e os vetores; o teste
  de deriva reprova o que vier separado.
- Repositório próprio, nome de produto e publicação no PyPI ficam para o D7. O nome
  `conversational-commerce` estava livre no PyPI em 17/11/2026.
