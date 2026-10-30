import { writeFile } from 'node:fs/promises'
import { startBackend, startNuxt } from '../../../surfaces/storefront-nuxt/tests/ssr/harness.mjs'
const [build,output]=process.argv.slice(2)
const backend=await startBackend();let server
const modules=logs=>[...new Set([...logs.matchAll(/file:\/\/\/[^\s)'"\]]+/g)].map(x=>x[0]).filter(x=>x.includes('/node_modules/reka-ui/')))]
try {
 process.env.NODE_DEBUG='esm'
 server=await startNuxt(backend.url,build,{continuumEnabled:true})
 const before=modules(server.logs())
 const r=await fetch(server.url+'/produto/FENDU');await r.text()
 const after=modules(server.logs())
 const report={method:'NODE_DEBUG=esm separate diagnostic run; timings not used as latency evidence',status:r.status,external_reka_modules_at_health:before.length,external_reka_modules_after_first_ssr:after.length,sample:after.slice(0,8).map(x=>x.slice(x.indexOf('/node_modules/reka-ui/'))),server_timing:r.headers.get('server-timing')}
 await writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report))
} finally {await server?.close();await backend.close()}
