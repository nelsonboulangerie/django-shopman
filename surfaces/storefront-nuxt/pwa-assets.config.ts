import {
  defineConfig,
  minimal2023Preset
} from '@vite-pwa/assets-generator/config'

const output = '../public/pwa/'

export default defineConfig({
  images: ['brand/nelson-mark.svg'],
  overrideAssets: true,
  manifestIconsEntry: false,
  preset: {
    ...minimal2023Preset,
    // O selo redondo, com fundo transparente fora do círculo: é o que o desktop
    // mostra sem máscara no `any` e o que a aba mostra no favicon.
    transparent: {
      ...minimal2023Preset.transparent,
      padding: 0,
      favicons: [[48, `${output}favicon.ico`]]
    },
    // `maskable` e `apple-touch-icon` precisam de fundo OPACO, e o fundo oficial é
    // outra arte — o quadrado amarelo em degradê de `brand/nelson-mark-bg.svg`. O
    // gerador lê uma imagem só, então quem os escreve é
    // `scripts/finalize-pwa-assets.mjs`. `sizes: []` = o gerador não emite nada
    // aqui; antes ele gerava dois PNGs que o finalize sobrescrevia em seguida.
    maskable: { sizes: [] },
    apple: { sizes: [] },
    assetName: (type, size) => {
      if (type === 'maskable') return `${output}maskable-${size.width}x${size.height}.png`
      if (type === 'apple') return `${output}apple-touch-icon-${size.width}x${size.height}.png`
      return `${output}pwa-${size.width}x${size.height}.png`
    }
  }
})
