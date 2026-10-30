export interface SsrReadTiming {
  kind: 'site' | 'shell' | 'primary'
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
  reads: SsrReadTiming[]
  reported?: boolean
}
