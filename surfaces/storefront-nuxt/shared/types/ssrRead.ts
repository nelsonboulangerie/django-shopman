export interface SsrReadTiming {
  kind: 'site' | 'shell' | 'primary' | 'fallback'
  startedAt: number
  finishedAt?: number
  statuses: number[]
  errorCode?: string
  networkCodes?: string[]
}

export interface StorefrontSsrRead {
  id: string
  route: 'catalog' | 'product'
  startedAt: number
  primaryPath: string
  primary?: Promise<unknown>
  primaryRaw?: Promise<unknown>
  fallbackPath?: string
  ownerRequest?: object
  reads: SsrReadTiming[]
  reported?: boolean
}
