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
são editáveis. Apply pertence ao passo seguinte do WP-6.
