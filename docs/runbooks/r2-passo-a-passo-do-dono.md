# Guardar os arquivos no Cloudflare R2: o que o dono faz

**Para quê.** Hoje, a foto que alguém manda pelo sistema (por exemplo, a foto da receita no
`/recipes/new`) fica guardada no próprio servidor, e o servidor é refeito a cada atualização: a
foto some. Você decidiu (01/10/2026, D-010) guardar esses arquivos no **Cloudflare R2**, um
"armário de arquivos" da Cloudflare. O sistema já está pronto para usar o R2, mas está
**desligado** até você entregar a chave do armário.

**Tempo:** uns 10 minutos. **Custo:** o R2 tem uma faixa grátis mensal; o volume de fotos da
casa deve ficar dentro dela, mas confira a página de preços da Cloudflare antes.

> Os nomes de botões e menus abaixo vêm da documentação oficial da Cloudflare (links no fim).
> O painel muda de vez em quando; se um rótulo estiver um pouco diferente, procure o mais
> parecido.

---

## Passo 1. Criar o "armário" (bucket)

1. Entre no painel da Cloudflare (dash.cloudflare.com) com a conta da casa.
2. No menu da esquerda, abra **Storage & databases** e depois **R2**, em **Overview**.
3. Crie um bucket novo.
   - **Nome:** `nelson-arquivos` (só letras minúsculas, números e hífen; de 3 a 63 letras).
   - **Location (local):** deixe na escolha automática (não marque região nem "Specify
     jurisdiction"). A jurisdição não pode ser trocada depois.
   - **Storage class:** deixe **Standard**.
4. **Não ligue acesso público.** O bucket nasce fechado, e é assim que ele deve ficar: o sistema
   gera, para cada foto, um link temporário que vence em uma hora. Quem não tem o link não vê
   nada.

## Passo 2. Criar a chave que só abre esse armário (token de API)

1. Ainda na página do **R2**, em **Account Details**, clique em **Manage**, ao lado de
   **API Tokens**.
2. Escolha **Create Account API token** (a chave fica ligada à conta da casa, não a uma pessoa;
   se alguém sair, a chave continua valendo).
3. Dê um nome que diga para que serve, por exemplo `shopman-arquivos`.
4. Em **Permissions**, escolha **Object Read & Write** (ler e gravar arquivos; nada de
   "Admin").
5. Restrinja a chave **só ao bucket `nelson-arquivos`** (a opção de aplicar a buckets
   específicos). Assim, se a chave vazar, ela não abre mais nada da conta.
6. Crie o token.

Na tela seguinte aparecem dois valores:

- **Access Key ID** (chave de acesso);
- **Secret Access Key** (chave secreta).

⚠️ **A chave secreta só aparece uma vez.** A própria Cloudflare avisa: depois de sair dessa
tela, não dá para ver de novo. Copie os dois valores **direto para o lugar do Passo 4** (ou para
o seu gerenciador de senhas) antes de fechar. Se perder, apague o token e crie outro.

## Passo 3. Achar o identificador da conta (Account ID)

Não é segredo, mas precisa ser exato. Dois jeitos:

- no painel, aperte `Cmd + K` (no Mac) e digite **Copy account ID**; ou
- em **Workers & Pages**, na seção **Account Details**, use o botão de copiar ao lado de
  **Account ID**.

Ele também aparece dentro do endereço do R2 (`https://<Account ID>.r2.cloudflarestorage.com`).

## Passo 4. Colar os valores no painel da DigitalOcean (você mesmo)

**Os segredos não vão por chat**, nem para mim, nem para ninguém, nem por e-mail. O caminho
seguro é você mesmo colar no painel da DO:

1. Entre no painel da DigitalOcean e abra o app da loja.
2. Vá em **Settings** e, lá, em **App-Level Environment Variables** (variáveis que valem para o
   app inteiro). Clique para editar.
3. Acrescente estas quatro, **com os nomes exatamente assim**:

   | Nome (exato) | Valor | Marcar **Encrypt**? |
   |---|---|---|
   | `R2_ACCOUNT_ID` | o Account ID do Passo 3 | não precisa (pode marcar) |
   | `R2_BUCKET` | `nelson-arquivos` | não precisa |
   | `R2_ACCESS_KEY_ID` | o Access Key ID do Passo 2 | **sim** |
   | `R2_SECRET_ACCESS_KEY` | o Secret Access Key do Passo 2 | **sim** |

4. **Não crie** a variável `SHOPMAN_MEDIA_STORAGE` ainda. Ela é o interruptor; sem ela, nada
   muda no ar.
5. Salve. A DO refaz o app (alguns minutos). Como o interruptor está desligado, o sistema segue
   igual.

Se preferir não mexer no painel, entregue os quatro valores por um **gerenciador de senhas**
compartilhado (item com acesso só para quem vai colar), nunca por mensagem.

Depois, mande no chat só isto: **"colei as quatro do R2"**. Nenhum valor.

## Passo 5. Ligar (com a sua palavra)

Com as quatro coladas, alguém da equipe (ou o agente, se você mandar) acrescenta a variável
`SHOPMAN_MEDIA_STORAGE` com o valor `r2`, no mesmo lugar. Isso só acontece quando você disser
"pode ligar o R2".

Se alguma das quatro estiver faltando ou com o nome errado, o sistema **não sobe** e diz qual
falta. É de propósito: melhor não subir do que fingir que guardou a foto e perdê-la no deploy
seguinte. Para voltar atrás, basta apagar `SHOPMAN_MEDIA_STORAGE` (ou pôr `local`).

## Passo 6. Conferir que funcionou

1. Abra o `/recipes/new` (ou outra tela que mande foto) e envie uma foto qualquer.
2. No painel da Cloudflare, em **R2**, abra o bucket `nelson-arquivos`: a foto tem de aparecer
   na lista de objetos.
3. Volte ao sistema e abra a foto: ela abre por um link longo, com `r2.cloudflarestorage.com` e
   uma assinatura no fim. Esse link vence em uma hora; abrir a tela de novo gera outro.
4. A prova final: depois da próxima atualização do sistema, a foto continua lá.

---

## Resumo do que o código lê

| Variável | O que é | Segredo? |
|---|---|---|
| `SHOPMAN_MEDIA_STORAGE` | interruptor: vazio ou `local` = como hoje; `r2` = R2 | não |
| `R2_ACCOUNT_ID` | identificador da conta Cloudflare | não |
| `R2_BUCKET` | nome do bucket (`nelson-arquivos`) | não |
| `R2_ACCESS_KEY_ID` | chave de acesso do token | **sim** |
| `R2_SECRET_ACCESS_KEY` | chave secreta do token | **sim** |
| `R2_URL_EXPIRE_SECONDS` | opcional: validade do link de cada foto, em segundos (padrão 3600) | não |

Código: `config/media_storage.py`. Decisão: `docs/coordination/DECISIONS.md`, D-010.

## Fontes (documentação oficial da Cloudflare)

- Token de API do R2 (Manage → API Tokens, permissões, aviso da chave secreta):
  https://developers.cloudflare.com/r2/api/tokens/
- Onde fica o Account ID: https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/
- Local do bucket (Location automática, jurisdição que não muda depois):
  https://developers.cloudflare.com/r2/reference/data-location/
- Nome do bucket e bucket fechado por padrão: https://developers.cloudflare.com/r2/buckets/create-buckets/
- Classe de armazenamento (Standard): https://developers.cloudflare.com/r2/buckets/storage-classes/
- Endereço do R2 e região `auto`: https://developers.cloudflare.com/r2/examples/aws/boto3/
