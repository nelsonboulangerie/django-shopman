# Runner visual das superfícies de operador

Esta pasta é a única infraestrutura de matriz visual dos oito apps de operador. Ela
centraliza viewports, Chromium aceito, scanner geométrico, captura, manifestos e contact
sheets. Storefront e Admin/Unfold não consomem este runner.

Cada spec declara `app`, `surface`, `route`, `scenario`, `state` e usa
`captureOperatorEvidence`. O helper grava a imagem, executa o scanner e anexa metadados.
O reporter organiza tudo em `test-results/operator-evidence`, gera `manifest.json`, uma
folha HTML e folhas PNG por app.

Execução incremental:

```bash
make operator-visual app=marketing route=/campaigns scenario=empty
make operator-visual app=operator-kit scenario=office-shell viewports=desktop-common,mobile-standard
```

Baseline oficial só pode ser atualizada com Playwright e revisão de Chromium idênticos a
`browser-lock.json`. O global setup recusa outra versão antes de abrir a primeira tela.

As exceções do scanner são locais ao cenário, enumeram apenas categorias observadas e
precisam aparecer no ledger com motivo, responsável e teste. Não se desliga o scanner para
fazer um retrato passar.
