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

O SVG mestre dos ícones é `brand/nelson-mark.svg`. Para regenerar favicon,
ícones, maskable, monochrome, apple-touch-icon e todos os splash screens iOS:

```bash
npm run pwa:assets
```

Revise visualmente `public/pwa/maskable-512x512.png` depois de qualquer troca do
SVG: todo o símbolo precisa continuar dentro da zona segura central de 80%. A
saída é versionada; o comando deve ser executado e o diff conferido antes do
commit.

Os ícones `any` usam o selo circular sem margem adicional e com transparência.
No Mac, o manifesto omite `maskable` para o Chrome selecionar esse selo; a
resposta varia por `User-Agent`. O ícone Apple é opaco, amarelo `#FFD25C`, com
98% de ocupação. O adaptativo Android usa o mesmo amarelo com 80% de ocupação,
preservando a zona segura contra recortes do launcher. Ícones já instalados
precisam receber a atualização do navegador; validar também uma instalação nova.

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
