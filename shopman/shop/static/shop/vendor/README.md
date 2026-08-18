# Bibliotecas de terceiros servidas por nós

Superfície de kiosk não pode depender de CDN público para desenhar. A TV da loja
e a prévia do DANFE ficavam em branco quando o `unpkg.com` não respondia — a rede
da loja, o DNS ou o próprio CDN bastavam para apagar o cardápio, com o Shopman
100% saudável do outro lado.

| Arquivo | Versão | Origem | SHA-256 |
|---|---|---|---|
| `alpine-3.14.1.min.js` | 3.14.1 | `https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js` | `358d9afbb1ab5befa2f48061a30776e5bcd7707f410a606ba985f98bc3b1c034` |

**Ao atualizar:** baixe a versão nova, confira o SHA-256, troque o arquivo E a
linha da tabela. O nome do arquivo carrega a versão de propósito — o cache do
navegador de um kiosk é longo, e nome novo é o jeito honesto de invalidá-lo.
