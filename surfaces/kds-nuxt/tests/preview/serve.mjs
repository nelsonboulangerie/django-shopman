// Prévia local dos cards do KDS, sem Django: sobe o mock com os quadros de
// previewFixtures.mjs (`KDS_MOCK_FIXTURE=preview`, :8799) e o `nuxt dev` apontado
// para ele (:3013). Abrir http://127.0.0.1:3013/bancada (preparo) ou
// http://127.0.0.1:3013/expedicao. Os botões funcionam: iniciar, finalizar (com a
// janela de Desfazer) e despachar mudam o quadro; reiniciar volta ao começo.
//
//   npm run preview:cards
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const mockPort = process.env.MOCK_PORT || "8799";
const port = process.env.PORT || "3013";

const children = [
  spawn(process.execPath, [join(root, "tests/e2e/mockBackend.mjs")], {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, KDS_MOCK_FIXTURE: "preview", MOCK_PORT: mockPort },
  }),
  spawn(
    process.execPath,
    [join(root, "node_modules/nuxt/bin/nuxt.mjs"), "dev", "--host", "127.0.0.1", "--port", port],
    {
      cwd: root,
      stdio: "inherit",
      env: { ...process.env, NUXT_DJANGO_BASE_URL: `http://127.0.0.1:${mockPort}` },
    },
  ),
];

function stop() {
  for (const child of children) child.kill("SIGTERM");
  process.exit(0);
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const child of children) child.on("exit", stop);
