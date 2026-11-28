# ADR-042 — Multi-loja: um schema do Postgres por loja, e a configuração da loja não cresce por env

**Data:** 2026-10-23
**Status:** Aceito
**Escopo:** Orquestrador (`shopman/shop`), `config/settings.py`, `config/instances/`, Core (intacto)
**Origem:** laudo adversarial de go-live de 23/10/2026 (tese "tenant = config + dados + marca, zero código"); decisão do dono na mesma data

## Contexto

O Shopman roda uma loja só (a Nelson). A tese de produto é que outra empresa adote o
sistema com configuração, dados e marca, sem código. O laudo de 23/10/2026 mediu que
isso vale no backend do orquestrador e não vale nas credenciais: a configuração de uma
loja entra hoje, em boa parte, por variável de ambiente lida no `settings`.

Medido no `main` em 23/10/2026:

- cerca de 30 dos 40 segredos do spec de deploy são **de uma loja** (Efí, Focus, Stripe,
  ManyChat, iFood, Comtele, Machine/TaOn), não do ambiente;
- `config/settings.py` lê 176 variáveis de ambiente com nome de loja (`SHOPMAN_*`,
  `EFI*`, `FOCUS*`, `STRIPE*`, `MANYCHAT*`, `IFOOD*`, `COMTELE*`, `MACHINE*`, `TAON*`);
- o runtime faz 312 leituras dessas chaves via `settings` (171 arquivos, fora testes e
  migrações) e 22 leituras diretas de `os.environ`/`os.getenv`;
- a `Shop` é singleton, lida por `Shop.objects.first()` em 7 pontos de runtime.

Cada leitura dessas é um ponto que, com duas lojas no mesmo processo, devolveria a
credencial da loja errada.

## Decisão

1. **O alvo é um schema do Postgres por loja.** A `Shop` continua singleton, agora
   singleton **por schema**; o Core (`packages/*`) não muda, porque nenhum modelo dele
   ganha chave de loja. A seleção do schema por requisição (host, sessão ou fila) é
   trabalho futuro e terá ADR própria.
2. **Agora, só a trava.** Nenhuma configuração ou credencial **nova** de uma loja entra
   por variável de ambiente ou por `settings`. Ela mora:
   - na `Shop` (campo ou JSON), quando é dado da loja;
   - no descritor de instância (`config/instances/*.json`), quando é contrato de
     bootstrap; segredo aparece ali só pelo **nome**, em `ownership.secret`;
   - num cofre de credenciais por loja, quando ele existir.
3. **O que já existe fica congelado, não migrado.** A dívida medida acima vira baseline
   versionada e só pode diminuir. Mover as leituras atuais para a `Shop` ou para o cofre
   é trabalho das frentes que já tocam esses arquivos, uma por vez.

Configuração de **ambiente** (banco, Redis, hosts, CSP, telemetria) não é da loja e
continua no `settings`.

## A trava

`scripts/check_tenant_config.py`, stdlib-only, roda no job "Quality + deploy contract" do
`runtime-gate.yml`. Conta por arquivo, por AST:

- `settings`: `settings.<PREFIXO…>` e `getattr/hasattr(settings, "<PREFIXO…>")`, com o
  alias do import de `django.conf` respeitado, mais todo `getattr(settings, <nome montado>)`;
- `env`: toda leitura de `os.environ`/`os.getenv` em runtime, de qualquer nome;
- `settings_env`: em `config/settings*.py`, as variáveis de ambiente lidas com nome de loja.

Fora da contagem: `tests/`, `test_*.py`, `conftest.py`, `migrations/`, `scripts/`,
`surfaces/`, e as leituras de infraestrutura dentro do `settings`.

Comparada com `scripts/tenant-config-baseline.json`, a contagem que **cresce** reprova, com
a lista de arquivos e onde a configuração deve morar. A que **diminui** passa e pede
`--update`, para que a folga não seja reaproveitada. Crescimento legítimo (configuração de
ambiente com prefixo de loja, por exemplo) se faz com `--update` e o motivo escrito no PR.

## Consequências

- Integração nova (outro provedor de pagamento, de fiscal, de entrega) nasce lendo a
  credencial da `Shop` ou do descritor, e não acrescenta linha ao `settings`.
- A trava é barata e grossa: conta leituras, não entende intenção. Ela não impede que uma
  leitura existente mude de chave; impede que o total de um arquivo cresça sem decisão.
- Os 7 `Shop.objects.first()` não entram na trava: no alvo eles continuam corretos (um
  singleton por schema). A troca por um acessor único fica para quando a seleção de
  schema existir.
