import { readdir, rm } from 'node:fs/promises'

const outputDirectory = new URL('../public/pwa/', import.meta.url)
const generatedAsset = /^(?:pwa|maskable|apple-touch-icon|monochrome)-\d+x\d+\.png$|^(?:\.paper-)?apple-splash-.*\.png$|^favicon\.(?:ico|svg)$|^nelson-logo\.svg$/

for (const name of await readdir(outputDirectory)) {
  if (generatedAsset.test(name)) await rm(new URL(name, outputDirectory))
}
