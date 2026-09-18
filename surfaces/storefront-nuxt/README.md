# Storefront Nuxt

Look at the [Nuxt documentation](https://nuxt.com/docs/getting-started/introduction) to learn more.

## Setup

Make sure to install dependencies:

```bash
# npm
npm install

# pnpm
pnpm install

# yarn
yarn install

# bun
bun install
```

## Development Server

Start the development server on `http://localhost:3000`:

```bash
# npm
npm run dev

# pnpm
pnpm dev

# yarn
yarn dev

# bun
bun run dev
```

## Production

Build the application for production:

```bash
# npm
npm run build

# pnpm
pnpm build

# yarn
yarn build

# bun
bun run build
```

Locally preview production build:

```bash
# npm
npm run preview

# pnpm
pnpm preview

# yarn
yarn preview

# bun
bun run preview
```

Check out the [deployment documentation](https://nuxt.com/docs/getting-started/deployment) for more information.

## PWA

Use Node 22. O manifesto é servido por `/manifest.webmanifest` a partir da
projeção pública de Loja; nome, nome curto, descrição e cores não devem ser
duplicados em componentes. Se o Django estiver indisponível, o builder usa o
fallback da Nelson gravado em `server/utils/pwaManifest.ts`.

O ícone instalável é o selo da marca: monograma marrom `#aa6a2b` sobre o disco
amarelo `#ffcd40`. Ele tem duas versões oficiais em `brand/`, e o formato do
ícone decide qual entra — `nelson-mark.svg`, com fundo transparente fora do
círculo, onde há alfa (`purpose: any`, favicon, `monochrome`); e
`nelson-mark-bg.svg`, quadrado amarelo em degradê de ponta a ponta, onde o
formato exige opacidade (`maskable` e `apple-touch-icon`). Os mesmos SVGs são a
fonte do favicon, do logotipo e dos splash screens. Para regenerar favicon,
ícones, maskable, monochrome, apple-touch-icon e todos os splash screens iOS:

```bash
npm run pwa:assets
```

Revise visualmente `public/pwa/maskable-512x512.png` depois de qualquer troca da
arte. A saída é versionada; o comando deve ser executado e o diff conferido antes
do commit. O anel externo do selo chega a 0,452 do lado no `maskable`, fora do
círculo de 40% que um launcher Android pode recortar — é propriedade da arte de
fundo, e o que fica sob risco de corte é a borda fina do anel, nunca o monograma.
Encolher isso é decisão de arte, não do gerador.

Os ícones `any` são o selo solto, com canto transparente: desktop (Windows, macOS,
Linux) mostra o `any` sem máscara, e a marca da loja é redonda por desenho — não o
retângulo arredondado da família de operador. O manifesto é o mesmo para todo
navegador e sempre publica o `maskable`: o Chrome no macOS monta o ícone do Dock a
partir dele, recortado na grade do macOS; sem ele, usava o `any` de ponta a ponta e
o app ficava ~24% maior que os vizinhos (ver `operator-kit/PWA_ICONS.md`). Por isso
`maskable` e `apple-touch-icon` seguem quadrados opacos, com a mesma forma da
família de operador. A resposta usa `private, no-store`, porque nome e cores vêm da
loja. O link versionado do manifesto evita reutilizar a resposta anterior; `id`,
`scope` e `start_url` não mudam. Ícones já instalados precisam receber a
atualização do navegador; validar também uma instalação nova.

O gate completo da fase parte da raiz do repositório:

```bash
make pwa app=storefront
```

Ele faz o build, valida manifesto, arquivos e dimensões, inspeciona o precache e
o cache de runtime, sobe o Nitro localmente e roda o fluxo Playwright. O contrato
é deliberadamente estreito: navegação usa rede com fallback apenas para
`offline.html`; cache de runtime existe somente para `/img/products/**` e
`/fonts/**`. API, SSE, Admin e HTML nunca entram nesse cache.

### Instalação no iPhone

1. Publique o build em HTTPS e abra a loja no Safari de um iPhone com iOS 16.4+.
2. Toque em **Compartilhar → Adicionar à Tela de Início**.
3. Abra pelo ícone e confira nome, ícone, splash e modo standalone.
4. Com a home já aberta uma vez, corte a rede e navegue: a página deve mostrar o
   casco offline honesto, sem simular catálogo ou pedido disponível.

Se os splash screens mudarem, remova a instalação anterior e adicione-a de novo;
o iOS conserva assets da instalação antiga.

### Forçar e validar uma atualização

1. Rode `npm run build` e `npm run preview`.
2. Abra o app e espere `navigator.serviceWorker.ready` no console do navegador.
3. Faça outro build com uma alteração visível e recarregue a página.
4. Quando aparecer “Nova versão disponível”, toque em **Atualizar**.

O worker em espera só recebe `skipWaiting` por esse toque. Não habilite
`autoUpdate` nem chame `skipWaiting()` no carregamento.
