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
alterar pacote ou código. Projeção do DB, diff e apply pertencem aos próximos
passos do WP-6; nenhum consumidor de runtime é introduzido aqui.
