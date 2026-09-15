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
    transparent: {
      ...minimal2023Preset.transparent,
      padding: 0,
      favicons: [[48, `${output}favicon.ico`]]
    },
    maskable: {
      ...minimal2023Preset.maskable,
      padding: 0.2,
      resizeOptions: { fit: 'contain', background: '#FFD25C' }
    },
    apple: {
      ...minimal2023Preset.apple,
      padding: 0.02,
      resizeOptions: { fit: 'contain', background: '#FFD25C' }
    },
    assetName: (type, size) => {
      if (type === 'maskable') return `${output}maskable-${size.width}x${size.height}.png`
      if (type === 'apple') return `${output}apple-touch-icon-${size.width}x${size.height}.png`
      return `${output}pwa-${size.width}x${size.height}.png`
    }
  }
})
