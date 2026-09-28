import { proxyPublicContinuumCatalog } from '../../../../../utils/continuumSnapshot'

export default defineEventHandler(event => proxyPublicContinuumCatalog(event))
