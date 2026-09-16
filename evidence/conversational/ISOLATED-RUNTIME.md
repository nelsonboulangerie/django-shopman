# Runtime sintético e reprodução

Validado nesta sessão: Python 3.12.5, PostgreSQL 16.14 (Homebrew), Redis 7.2.5. O runner reposiciona os imports dos packages para o worktree e usa `config.settings_test`. Nenhum `.env` foi copiado. Os testes substituem os adapters/modelos externos; concorrência usa PostgreSQL real.

Instância exclusiva da sessão: `/tmp/conversational-implementation-20260911/pg`, PostgreSQL em `127.0.0.1:56419`, usuário sintético `concierge_test`; Redis em `127.0.0.1:56420`. O banco principal dos ensaios integrados é `concierge_final` e o banco criado pelo pytest é `test_concierge_final`; Redis DB12. Agentes usaram bancos separados. Não há conexão com instância de terceiros.

Para reproduzir, provisione um **novo** cluster PostgreSQL local e Redis exclusivos, com portas livres, e crie banco sintético vazio. Não reaproveite produção ou uma instância compartilhada. Instale as dependências do projeto em ambiente Python adequado e adapte somente o caminho do executável e as URLs privadas. A seleção integral está em `final-selection.json`:

```python
import json, os, subprocess
from pathlib import Path

root = Path.cwd()  # checkout do SHA candidato
selected = json.loads((root / "evidence/conversational/final-selection.json").read_text())
env = dict(os.environ,
    DATABASE_URL="postgres://concierge_test@127.0.0.1:56419/concierge_final",
    REDIS_URL="redis://127.0.0.1:56420/12",
    PYTHONDONTWRITEBYTECODE="1",
)
subprocess.run([
    "/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python",
    "evidence/conversational/run.py", *selected, "-rs", "--reuse-db",
], env=env, check=True)
```

O caminho absoluto foi o runtime efetivamente utilizado aqui; não é dependência de produto. O core `packages/orderman/shopman/orderman/tests/test_commit_branches.py` roda em processo separado: seu `conftest.py` limpa o registry global e a combinação no mesmo processo com testes transacionais de framework invalida o harness. `integration-mixed-registry-fixture.txt` preserva essa falha intermediária. Não alterar o registry de produto para esconder a colisão.

`make admin` integral, navegador e schema check têm logs próprios. `runtime-load-final.txt` inclui conexões, SQL, deadlocks, locks esperando ao término, RSS do processo e tamanho UTF-8 das saídas sintéticas. SQL elapsed inclui espera e execução, não é medida separada de lock wait; RSS é pico do processo de teste, não footprint exclusivo do concierge. Não há latência/custo real de modelo/fornecedor nem prova humana.

O ensaio de backup usa `backup_rehearsal.py`, bancos sintéticos e `pg_dump`/`pg_restore`. Seu dump temporário foi removido após verificar Order, receipt e saída unknown; o hash e o resultado estão em `backup-restore.txt`. Manter o schema expandido no rollback de aplicação: não apagar campos, mensagens, Orders ou receipts e não reproduzir transcrições legadas como intenção.
