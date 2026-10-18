# Descritores de Instância

O banco de dados é a única verdade de runtime. Estes arquivos não são lidos pelo
servidor para decidir comportamento: são contratos versionados para bootstrap,
dump e diff.

O vocabulário de ownership é fechado:

- `instance_db`: configuração materializada no banco;
- `deploy`: configuração pública do ambiente de execução;
- `secret`: somente o **nome** da configuração secreta; nunca seu valor;
- `structural`: composição invariável do produto, não customização de tenant.

`bootstrap` aceita apenas configuração declarativa. Pedidos, pagamentos,
saldo, ledger, sessões, auditoria e outros estados operacionais são proibidos.
O checker também recusa chaves e padrões de valores que pareçam credenciais.

`counter-minimal.json` prova que uma segunda instalação pode ser descrita sem
alterar pacote ou código.

## Leitura e drift

`python manage.py instance_descriptor dump --descriptor <arquivo>` projeta o
estado configurável comprovado no DB para stdout. `diff` compara essa projeção
com o arquivo e retorna código 1 quando há drift. Nenhum dos comandos escreve
arquivo ou banco.

A projeção cobre somente modelos comprovados: identidade da `Shop`, canais,
`RuleConfig`, grupos/permissões e templates operacionais. Seções sem modelo DB
canônico permanecem vazias; o dump não inventa que unidades ou perfis fiscais
são editáveis.

## Apply

`python manage.py instance_descriptor apply --descriptor <arquivo>
--confirm-instance <ref>` faz upsert apenas dos modelos comprovados, dentro de
uma única transação. A confirmação precisa coincidir exatamente com
`instance.ref`. Falha tardia reverte todas as mudanças; segunda execução com
o mesmo descritor não altera o estado. O apply não remove registros ausentes do
arquivo e recusa seção sem dono DB comprovado.

O `seed` da Nelson materializa `nelson.json` antes dos dados de demonstração.
Canais, regras, personas RBAC e templates operacionais não têm uma segunda
lista no comando: o seed apenas cria fatos operacionais sobre a configuração já
aplicada. Outra Instância usa `instance_descriptor apply`; o catálogo e o
histórico sintético do comando `seed` continuam deliberadamente Nelson.
