import { defineEventHandler } from 'h3'
import { applyStorefrontSecurityHeaders } from '../utils/storefrontSecurity'

export default defineEventHandler((event) => {
  applyStorefrontSecurityHeaders(event)
})
