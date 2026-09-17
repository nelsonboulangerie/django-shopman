import { defineEventHandler } from 'h3'
import { applyIndexingPolicy } from '../utils/indexingPolicy'

export default defineEventHandler((event) => {
  applyIndexingPolicy(event)
})
