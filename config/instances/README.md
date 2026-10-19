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
alterar pacote ou código. Ela declara também `SHOPMAN_POS_CHANNEL_REF` como
configuração de deploy: o descritor materializa o canal `counter`, e o ambiente
seleciona essa mesma ref para o POS sem esconder uma dependência da Nelson.

## Contratos de fechamento

`make test-instance-contracts` mantém três provas separadas:

- **soberania:** stockman, offerman e doorman constroem wheels próprios, são
  instalados sem dependências num venv vazio e importam sem o orquestrador;
- **composição:** a Instância mínima materializa somente seu canal e persona,
  e o runtime lê do DB exatamente a política declarada;
- **evolução:** uma nova versão declarativa atualiza a configuração possuída
  sem apagar canal, usuário ou vínculo criados pelo tenant; conflito tardio
  reverte a transação inteira.

## A loja é uma só

A `Shop` é singleton. O apply cria a loja quando não há nenhuma e recusa, dizendo
quantas há e quais `pk`, quando encontra mais de uma; o dump e o `seed` também.
O `seed` atualiza a loja que o apply criou, nunca uma `pk` fixa: depois de um
`seed --flush` a sequência não volta a 1.

## Configuração declarada × estado operacional

O descritor manda na **configuração**. O operador manda no **estado
operacional**, e o apply não o toca, o dump não o exporta e o diff não o enxerga
(`OPERATIONAL_STATE` em `config/instance_descriptors.py`):

- `enabled` do canal: vale só para o canal que nasce; depois, ligar e desligar é
  gesto do operador;
- `overrides.activation`: o registro do último gesto no liga/desliga;
- `overrides.display.paused_skus`: a pausa local de SKU num canal de exibição.

O descritor não pode declarar `activation` nem `paused_skus` (o checker e o apply
recusam).

## Leitura e drift

`python manage.py instance_descriptor dump --descriptor <arquivo>` projeta o
estado configurável comprovado no DB para stdout. `diff` compara essa projeção
com o arquivo e retorna código 1 quando há drift. Nenhum dos comandos escreve
arquivo ou banco.

O dump é **allowlist**: sai só chave que um contrato tipado declara. No canal,
os campos do dataclass `ChannelConfig` (os mapas livres `lifecycle`,
`fulfillment.stage_goal_minutes` e `notifications.routing` só aceitam
identificadores); na regra, os parâmetros que a classe aceita; na tarefa, as
chaves de `TASK_CONFIG_KEYS`. Chave desconhecida recusa o dump inteiro, dizendo o
caminho e nunca o valor. A denylist de nomes e de padrões de valor (chave Pix,
HMAC, JWT, `whsec_`, certificado, URL com senha) continua como segunda camada.

A projeção cobre somente modelos comprovados: identidade da `Shop`, canais,
`RuleConfig`, grupos/permissões e templates operacionais. Seções sem modelo DB
canônico permanecem vazias; o dump não inventa que unidades ou perfis fiscais
são editáveis.

## Apply

`python manage.py instance_descriptor apply --descriptor <arquivo>` é **ensaio**:
imprime o diff (o que seria criado, acrescentado, atualizado, removido e o que
diverge) e não escreve nada. Grava com `--commit --confirm-instance <ref>`; a
confirmação precisa coincidir exatamente com `instance.ref`.

A comparação é de três vias: o declarado agora, o banco e a última versão
aplicada (a trilha `InstanceApplyRecord`). Valor que o banco tem igual à última
versão aplicada é do descritor e acompanha a versão nova. Valor diferente foi
mudado por fora (pelo operador, no Admin) e o apply **recusa** sem ordem
explícita: `--keep-drift` preserva o banco, `--overwrite-drift` grava o
declarado. Banco sem trilha (aplicado antes dela existir) trata toda diferença
como divergência.

Cada apply que muda o banco grava uma linha em `InstanceApplyRecord`: quem
(`--actor`, padrão `cli:<usuário>`), quando, o hash e o descritor declarado, e a
lista de mudanças. Apply sem mudança e com o mesmo descritor não grava nada.

Tudo numa transação: falha tardia reverte todas as mudanças. O apply não remove
registros ausentes do arquivo e recusa seção sem dono DB comprovado.

O `seed` da Nelson materializa `nelson.json` antes dos dados de demonstração,
com `--keep-drift` implícito (preserva o que divergiu e avisa quantos).
Canais, regras, personas RBAC e templates operacionais não têm uma segunda
lista no comando: o seed apenas cria fatos operacionais sobre a configuração já
aplicada. Outra Instância usa `instance_descriptor apply`; o catálogo e o
histórico sintético do comando `seed` continuam deliberadamente Nelson.
