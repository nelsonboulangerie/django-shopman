import { readdirSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import {
  baseParse,
  NodeTypes,
  type ElementNode,
  type RootNode,
  type TemplateChildNode,
} from "@vue/compiler-dom";
import { parse as parseSfc } from "@vue/compiler-sfc";
import { describe, expect, it } from "vitest";

const appRoot = new URL("../app/", import.meta.url);

function vueFiles(path = appRoot): URL[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(
      `${entry.name}${entry.isDirectory() ? "/" : ""}`,
      path,
    );
    if (entry.isDirectory()) return vueFiles(child);
    return extname(entry.name) === ".vue" ? [child] : [];
  });
}

const sources = vueFiles().map((url) => ({
  file: url.pathname.split("/app/")[1],
  source: readFileSync(url, "utf8"),
}));

// Segue o grafo real de componentes: uma lista manual já deixou escapar o Splitter
// e dois auxiliares transitivos. Se o Gestor passar a renderizar outra peça do kit,
// ela entra nesta auditoria automaticamente no mesmo commit.
const operatorComponentsRoot = new URL(
  "../../operator-kit/app/components/",
  import.meta.url,
);
const operatorComponents = new Map(
  vueFiles(operatorComponentsRoot).map((url) => [
    url.pathname
      .split("/")
      .at(-1)!
      .replace(/\.vue$/, ""),
    url,
  ]),
);
const reachableShared = new Map<string, URL>();
const componentQueue = sources.map(({ source }) => source);
while (componentQueue.length) {
  const source = componentQueue.shift()!;
  for (const match of source.matchAll(/<([A-Z][A-Za-z0-9]+)/g)) {
    const name = match[1]!;
    const url = operatorComponents.get(name);
    if (!url || reachableShared.has(name)) continue;
    reachableShared.set(name, url);
    componentQueue.push(readFileSync(url, "utf8"));
  }
}

const sharedSources = [...reachableShared.entries()].map(([name, url]) => ({
  file: `operator-kit/${name}.vue`,
  source: readFileSync(url, "utf8"),
}));

const runtimeSources = [...sources, ...sharedSources];

function offenders(pattern: RegExp): string[] {
  return sources
    .filter(({ source }) => pattern.test(source))
    .map(({ file }) => file);
}

function runtimeOffenders(pattern: RegExp): string[] {
  return runtimeSources
    .filter(({ source }) => pattern.test(source))
    .map(({ file }) => file);
}

// Captura a tag inteira sem parar no `>` de uma expressão Vue entre aspas. O
// guard anterior usava `[^>]*` e, por isso, uma prop como `:items="rows.map((row) =>
// row.value)"` podia esconder os atributos que vinham depois dela.
function componentTags(
  componentPattern: string,
  pool = runtimeSources,
): Array<{ file: string; tag: string }> {
  const tagPattern = new RegExp(
    `<Nuxt(?:${componentPattern})\\b(?:[^>"']|"[^"]*"|'[^']*')*>`,
    "gs",
  );
  return pool.flatMap(({ file, source }) =>
    [...source.matchAll(tagPattern)].map(([tag]) => ({ file, tag })),
  );
}

function elementProp(node: ElementNode, name: string) {
  return node.props.find(
    (prop) =>
      (prop.type === NodeTypes.ATTRIBUTE && prop.name === name) ||
      (prop.type === NodeTypes.DIRECTIVE &&
        prop.arg?.type === NodeTypes.SIMPLE_EXPRESSION &&
        prop.arg.content === name),
  );
}

function elementChildren(
  node: RootNode | TemplateChildNode,
): TemplateChildNode[] {
  return "children" in node ? node.children : [];
}

/**
 * Um botão dentro do slot de ações do Alert não é hierarquia independente:
 * ele repete a cor semântica do aviso e usa sempre a variante outline. A
 * auditoria usa o AST do template para não confundir botões vizinhos nem parar
 * em `>` dentro de expressões Vue.
 */
function alertActionViolations(): string[] {
  const failures: string[] = [];

  for (const { file, source } of runtimeSources) {
    const template = parseSfc(source).descriptor.template?.content;
    if (!template) continue;
    const root = baseParse(template);

    const inspectAlert = (alert: ElementNode) => {
      const colorProp = elementProp(alert, "color");
      const alertColor =
        colorProp?.type === NodeTypes.ATTRIBUTE
          ? colorProp.value?.content
          : colorProp?.type === NodeTypes.DIRECTIVE
            ? colorProp.exp?.loc.source.replaceAll(/\s+/g, " ").trim()
            : undefined;
      const actionsProp = elementProp(alert, "actions");

      if (actionsProp?.type === NodeTypes.DIRECTIVE) {
        const raw = actionsProp.exp?.loc.source ?? "";
        const labels = [...raw.matchAll(/\blabel\s*:/g)].length;
        const variants = [
          ...raw.matchAll(/\bvariant\s*:\s*["']([^"']+)["']/g),
        ].map((match) => match[1]);
        const colors = [...raw.matchAll(/\bcolor\s*:\s*["']([^"']+)["']/g)].map(
          (match) => match[1],
        );

        if (labels && variants.length !== labels) {
          failures.push(`${file}:${alert.loc.start.line}: ação sem variant`);
        }
        for (const variant of variants) {
          if (variant !== "outline") {
            failures.push(
              `${file}:${alert.loc.start.line}: variant ${variant}`,
            );
          }
        }
        if (
          colorProp?.type === NodeTypes.ATTRIBUTE &&
          labels &&
          colors.length !== labels
        ) {
          failures.push(`${file}:${alert.loc.start.line}: ação sem color`);
        }
        if (colorProp?.type === NodeTypes.ATTRIBUTE) {
          for (const color of colors) {
            if (color !== alertColor) {
              failures.push(
                `${file}:${alert.loc.start.line}: ${color} em Alert ${alertColor}`,
              );
            }
          }
        }
      }

      const inspectSlot = (node: TemplateChildNode) => {
        if (node.type !== NodeTypes.ELEMENT) return;
        if (node.tag === "NuxtButton") {
          const variant = elementProp(node, "variant");
          const color = elementProp(node, "color");
          if (
            variant?.type !== NodeTypes.ATTRIBUTE ||
            variant.value?.content !== "outline"
          ) {
            failures.push(
              `${file}:${node.loc.start.line}: botão de Alert não outline`,
            );
          }
          if (!color) {
            failures.push(
              `${file}:${node.loc.start.line}: botão de Alert sem color`,
            );
          } else if (
            colorProp?.type === NodeTypes.ATTRIBUTE &&
            color.type === NodeTypes.ATTRIBUTE &&
            color.value?.content !== alertColor
          ) {
            failures.push(
              `${file}:${node.loc.start.line}: ${color.value?.content} em Alert ${alertColor}`,
            );
          } else if (
            colorProp?.type === NodeTypes.DIRECTIVE &&
            color.type === NodeTypes.DIRECTIVE &&
            color.exp?.loc.source.replaceAll(/\s+/g, " ").trim() !== alertColor
          ) {
            failures.push(
              `${file}:${node.loc.start.line}: expressão de cor diverge do Alert`,
            );
          }
        }
        for (const child of node.children) inspectSlot(child);
      };

      for (const child of alert.children) {
        if (
          child.type === NodeTypes.ELEMENT &&
          child.tag === "template" &&
          elementProp(child, "actions")
        ) {
          for (const nested of child.children) inspectSlot(nested);
        }
      }
    };

    const visit = (node: RootNode | TemplateChildNode) => {
      if (node.type === NodeTypes.ELEMENT && node.tag === "NuxtAlert") {
        inspectAlert(node);
      }
      for (const child of elementChildren(node)) visit(child);
    };
    visit(root);
  }

  return failures;
}

describe("Gestor canônico em Nuxt UI", () => {
  it("não mantém controles HTML ou wrappers visuais paralelos", () => {
    expect(
      runtimeOffenders(/<(?:button|input|select|textarea|form|table)\b/i),
    ).toEqual([]);
    // Os cinco campos de data e hora da suíte são o cânone por decisão do dono (brief
    // do WP-OPERADOR-NUXTUI-ONDAS, #1529): camadas finas sobre InputDate, InputTime e
    // Calendar, com o locale, o passo e os limites da casa. Admitidos PELO NOME, sem
    // curinga: qualquer outro <Ui…> continua reprovando.
    expect(
      runtimeOffenders(
        /<Ui(?!(?:DateField|DateRangeField|TimeField|TimeRangeField|DateTimeField)\b)[A-Z]|\b:ui=|\bui="/,
      ),
    ).toEqual([]);
    // Import de TIPO do reka-ui não desenha nada (os campos de data tipam o range com
    // ele); o que a trava proíbe é montar primitiva do reka por fora do Nuxt UI.
    expect(
      runtimeOffenders(/^import\s+(?!type\b)[^;]*from ["']reka-ui["']/m),
    ).toEqual([]);
    expect(offenders(/role="button"/)).toEqual([]);
    expect(
      offenders(/<(?:div|span|img|p|li)\b[^>]*@(?:click|keydown)=/s),
    ).toEqual([]);
    expect(
      componentTags("Card")
        .filter(({ tag }) =>
          /\bclass="[^"]*\b(?:bg-|border(?:-|\b)|ring-|rounded|shadow|p[xy]?)-/.test(
            tag,
          ),
        )
        .map(({ file }) => file),
    ).toEqual([]);
  });

  it("não recria overlays, menus, tabs ou alerts por ARIA manual", () => {
    expect(
      runtimeOffenders(
        /role="(?:alert|dialog|menu|menuitem|menuitemcheckbox|option|tab|tablist)"/,
      ),
    ).toEqual([]);
  });

  it("não aplica skin local aos controles Nuxt UI", () => {
    const controls =
      "Button|Input|Textarea|Switch|Checkbox|Select|Badge|Alert|Tabs|Progress|RadioGroup|CheckboxGroup|Kbd|Chip|NavigationMenu|InputNumber";
    const tags = componentTags(controls);
    const skin =
      /(?:^|[\s'"`])(?:bg-|border(?:-|\b)|ring-|rounded|shadow|text-(?:primary|secondary|success|info|warning|error|neutral|foreground|muted|accent|rail|popover|white|black))/;
    expect(
      tags
        .filter(({ tag }) => {
          const classValues = [
            ...tag.matchAll(/\b:?class\s*=\s*"([^"]*)"/g),
          ].map((match) => match[1]!);
          return classValues.some((value) => skin.test(value));
        })
        .map(({ file }) => file),
    ).toEqual([]);
    expect(
      tags
        .filter(({ tag }) => /\b:?style\s*=/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
    const buttons = componentTags("Button", sources);
    expect(
      buttons
        .filter(
          ({ tag }) =>
            /\b:size=/.test(tag) || /\bsize="(?!xs")[^"]+"/.test(tag),
        )
        .map(({ file }) => file),
    ).toEqual([]);
    expect(
      componentTags("Badge|Tabs|Switch", sources)
        .filter(({ tag }) => /\bsize=/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
    expect(
      componentTags("Badge")
        .filter(({ tag }) => !/\bvariant="(?:soft|subtle)"/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
    expect(offenders(/<kbd\b/i)).toEqual([]);
  });

  it("dimensiona USkeleton sem substituir sua aparência canônica", () => {
    const tags = sources.flatMap(({ file, source }) =>
      [...source.matchAll(/<NuxtSkeleton\b[^>]*\/?\s*>/gs)].map(([tag]) => ({
        file,
        tag,
      })),
    );
    expect(tags.length).toBeGreaterThan(0);
    expect(
      tags
        .filter(({ tag }) => !/\bclass="[^"]*(?:\bh-|\bw-|\bsize-)/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
    expect(
      tags
        .filter(({ tag }) =>
          /\bclass="[^"]*\b(?:bg|border|rounded|shadow|ring|animate)-/.test(
            tag,
          ),
        )
        .map(({ file }) => file),
    ).toEqual([]);
  });

  it("usa somente as cores semânticas do tema Shopman", () => {
    expect(
      runtimeOffenders(
        /\b(?:bg|text|border|ring|divide)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d/,
      ),
    ).toEqual([]);
    expect(runtimeOffenders(/\b(?:bg|text|border|ring)-destructive\b/)).toEqual(
      [],
    );
  });

  it("não reativa a pele visual legada da suíte", () => {
    expect(runtimeOffenders(/\b:?class="[^"]*\bsuite:/s)).toEqual([]);
    expect(runtimeOffenders(/data-suite=["']v3["']/)).toEqual([]);
  });

  it("escolhe variantes de Alert por uso e mantém o subtle opaco no tema", () => {
    const appConfig = readFileSync(
      new URL("../../operator-kit/app/app.config.ts", import.meta.url),
      "utf8",
    );
    expect(appConfig).toMatch(/\balert:\s*\{/);
    for (const color of [
      "primary",
      "secondary",
      "success",
      "info",
      "warning",
      "error",
      "neutral",
    ]) {
      expect(appConfig).toMatch(
        new RegExp(
          `color: ["']${color}["'][\\s\\S]{0,100}variant: ["']subtle["']`,
        ),
      );
    }
    expect(appConfig).toContain("color-mix(in_srgb");
    expect(appConfig).toContain('"4xl": "h-4 min-w-4 px-1 text-[12px]/none"');
    expect(appConfig).not.toContain('"5xl"');
    expect(appConfig).not.toContain('"6xl"');
    const inbox = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorInbox.vue",
        import.meta.url,
      ),
      "utf8",
    );
    expect(inbox).toContain('size="4xl"');
    const chips = componentTags("Chip");
    expect(chips.length).toBeGreaterThan(0);
    expect(
      chips.filter(({ tag }) => !/\binset\b/.test(tag)).map(({ file }) => file),
    ).toEqual([]);
    // A regra aprovada: Chip com número é o numérico (4xl, texto de 12 px); sem
    // número é o indicativo (2xl); o On/Off é xl. A única expressão aceita é o
    // tamanho amarrado ao próprio texto: `:size="X ? '4xl' : '2xl'"` com `:text="X"`.
    const chipSizeOk = ({ file, tag }: { file: string; tag: string }) => {
      if (file.endsWith("OperatorLiveStatus.vue"))
        return /\bsize="xl"/.test(tag);
      const bound = tag.match(/:size="([\w.]+) \? '4xl' : '2xl'"/);
      if (bound) return tag.includes(`:text="${bound[1]}"`);
      const hasText = /(?:^|\s):?text=/.test(tag);
      return hasText ? /\bsize="4xl"/.test(tag) : /\bsize="2xl"/.test(tag);
    };
    expect(
      chips.filter((chip) => !chipSizeOk(chip)).map(({ file }) => file),
    ).toEqual([]);
    expect(appConfig).toMatch(
      /kbd:\s*\{[\s\S]*?defaultVariants:\s*\{\s*variant:\s*["']soft["']\s*\}/,
    );
    expect(
      componentTags("Kbd")
        .filter(
          ({ tag }) => /\bvariant=/.test(tag) && !/\bvariant="soft"/.test(tag),
        )
        .map(({ file }) => file),
    ).toEqual([]);
    for (const component of [
      "OperatorPwaUpdatePrompt.vue",
      "OperatorPushInvite.vue",
    ]) {
      const notice = readFileSync(
        new URL(
          `../../operator-kit/app/components/${component}`,
          import.meta.url,
        ),
        "utf8",
      );
      expect(notice).toContain('color: "info" as const');
      expect(notice).toContain('variant: "outline" as const');
    }
    const alerts = runtimeSources.flatMap(({ file, source }) =>
      [...source.matchAll(/<NuxtAlert\b[^>]*>/gs)].map(([tag]) => ({
        file,
        tag,
      })),
    );
    expect(
      alerts
        .filter(({ tag }) => !/\bvariant=/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
    const infoActionSources = [
      readFileSync(new URL("../app/pages/[ref].vue", import.meta.url), "utf8"),
      readFileSync(
        new URL("../app/components/CatalogBindingReview.vue", import.meta.url),
        "utf8",
      ),
    ];
    for (const source of infoActionSources) {
      expect(source).toMatch(
        /color: ['"]info['"][\s\S]{0,80}variant: ['"]outline['"]/,
      );
    }
  });

  it("faz toda ação de Alert repetir sua cor semântica em outline", () => {
    expect(alertActionViolations()).toEqual([]);
  });

  it("usa o shell, o cabeçalho e as tabs canônicas no piloto", () => {
    const app = readFileSync(
      new URL("../app/app.vue", import.meta.url),
      "utf8",
    );
    const board = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );
    const boardColumn = readFileSync(
      new URL("../app/components/OrderBoardColumn.vue", import.meta.url),
      "utf8",
    );
    const boardHeading = readFileSync(
      new URL("../app/components/OrderBoardHeading.vue", import.meta.url),
      "utf8",
    );
    expect(app).toContain("<OperatorAppRoot>");
    expect(app).toContain("<OperatorSuiteShell");
    expect(app).toContain("operatorSurfaceGate({");
    expect(app).toContain('v-if="surface.showPage"');
    expect(app).toContain('v-else-if="surface.showForbidden"');
    expect(app).toContain('v-else-if="surface.showChecking"');
    expect(app).toContain('v-if="surface.showUnavailable"');
    expect(app).toContain('v-if="surface.showLogin"');
    expect(app).toContain('v-else-if="surface.showLock"');
    expect(app).not.toContain('v-show="canIdentify');
    expect(app).toContain('empty-to="/workstations"');
    expect(app).not.toContain("<GestorNav");
    expect(board).toContain("<OperatorPageHeader");
    expect(
      (board.match(/<NuxtTabs\b/g)?.length ?? 0) +
        (boardColumn.match(/<NuxtTabs\b/g)?.length ?? 0) +
        (boardHeading.match(/<NuxtTabs\b/g)?.length ?? 0),
      // Escopo da Fila, recorte do fluxo (o mesmo na Saída), abas das colunas no
      // celular e no tablet em pé, e a visão Grade | Lista.
    ).toBeGreaterThanOrEqual(4);
    expect(board).toContain("<OperatorSplitter");
    expect(board).not.toContain("<QueueColumnResizeHandle");
    expect(board).not.toContain("<QueueColumnStrip");
    expect(board).toContain('v-if="hasChannelQueueSignal" #feedback');
    expect(boardColumn).toContain('v-if="!phone && heading" as="header"');
    expect(boardColumn).toContain("<OrderBoardHeading");
    // O posto Saída usa a mesma faixa de recortes; não há cabeçalho de coluna na toolbar.
    expect(board).toContain(':items="fulfillmentFilterTabs"');
    expect(board).not.toContain('v-if="exitPostView && desktopZones[0]"');
    expect(board).toContain(':heading="!exitPostView"');
    expect(board).toMatch(
      /<OperatorToolbar[\s\S]*?v-if="boardAsTabs && view === 'board' && zones\.length"[\s\S]*?class="py-2"/,
    );
    const header = board.slice(
      board.indexOf("<OperatorPageHeader"),
      board.indexOf("</OperatorPageHeader>"),
    );
    expect(header).not.toContain('size="lg"');
    expect(header).toMatch(/<NuxtTabs[\s\S]*?data-view-switch/);
    expect(header).not.toMatch(
      /<NuxtTabs\b(?=[^>]*data-view-switch)[^>]*color="neutral"/s,
    );
    expect(runtimeOffenders(/#below\b/)).toEqual([]);
    expect(
      componentTags("Tabs", sources)
        .filter(({ tag }) => !/:content="false"/.test(tag))
        .map(({ file }) => file),
    ).toEqual([]);
  });

  it("mantém metadados dentro da anatomia canônica dos menus", () => {
    const boardMenu = readFileSync(
      new URL("../app/components/BoardMenu.vue", import.meta.url),
      "utf8",
    );
    const catalog = readFileSync(
      new URL("../app/pages/catalog.vue", import.meta.url),
      "utf8",
    );
    for (const source of [boardMenu, catalog]) {
      expect(source).not.toContain("#content-top");
      expect(source).toContain('slot: "freshness"');
      expect(source).toContain("<template #freshness>");
    }
    const freshness = readFileSync(
      new URL("../app/components/ReadFreshness.vue", import.meta.url),
      "utf8",
    );
    expect(freshness).toContain("font-normal");
    expect(freshness).toContain("whitespace-normal");
    expect(freshness).not.toContain("whitespace-nowrap");
  });

  it("mantém login e filtros em formulários Nuxt UI", () => {
    const login = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorLogin.vue",
        import.meta.url,
      ),
      "utf8",
    );
    const loginForm = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorLoginForm.vue",
        import.meta.url,
      ),
      "utf8",
    );
    const filters = readFileSync(
      new URL(
        "../../operator-kit/app/components/FilterBar.vue",
        import.meta.url,
      ),
      "utf8",
    );
    expect(login).toContain("<NuxtModal");
    expect(login).not.toContain('role="dialog"');
    expect(loginForm).toContain("<NuxtForm");
    expect(login).not.toContain('as="form"');
    expect(filters).toContain("<NuxtForm");
  });

  it("não empilha cards dentro do modal de atalhos", () => {
    const shortcuts = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorShortcutsHelp.vue",
        import.meta.url,
      ),
      "utf8",
    );
    expect(shortcuts).toContain("<NuxtModal");
    expect(shortcuts).toContain("<NuxtKbd");
    expect(shortcuts).toContain("<NuxtSeparator");
    expect(shortcuts).not.toContain("<NuxtCard");
  });

  it("mantém as ações dos avisos outline e na cor semântica do Alert", () => {
    const inbox = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorInbox.vue",
        import.meta.url,
      ),
      "utf8",
    );
    const actionSlots = [
      ...inbox.matchAll(/<template #actions\b[^>]*>([\s\S]*?)<\/template>/g),
    ].map((match) => match[1]!);
    expect(actionSlots.length).toBeGreaterThanOrEqual(4);
    for (const slot of actionSlots) {
      expect(slot).toContain('variant="outline"');
      expect(slot).not.toMatch(/variant="(?:link|ghost)"/);
    }
    expect(inbox).toContain(':color="alertColor(alert.tone)"');
    expect(inbox).toContain('class="min-w-0 basis-0 flex-[2]"');
    expect(inbox).toContain('class="min-w-0 basis-0 flex-1"');
    expect(inbox).toContain(
      ":color=\"isHighlighted(item) ? 'warning' : 'neutral'\"",
    );
    expect(inbox.match(/variant="outline"/g)?.length).toBeGreaterThanOrEqual(5);
  });

  it("padroniza os metadados dos cards de consciência da fila", () => {
    const queue = readFileSync(
      new URL("../app/components/QueueView.vue", import.meta.url),
      "utf8",
    );
    expect(queue).toMatch(
      /data-queue-progress[\s\S]*?color="neutral"[\s\S]*?variant="subtle"[\s\S]*?:label="`\$\{workingCount\} /,
    );
    expect(queue).toMatch(
      /data-queue-system[\s\S]*?color="neutral"[\s\S]*?variant="subtle"[\s\S]*?:label="`\$\{awareness\?\.system_window_minutes \?\? 15\} min`"/,
    );
    expect(queue).toContain("'grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'");
    // O item da vez: destaque semântico oficial (PageCard highlight), dono 07/10.
    expect(queue).toContain(':highlight="item.card.ref === focusRef"');
    expect(queue).toContain('highlight-color="primary"');
  });

  it("não usa cards como simples divisores dentro de outros cards", () => {
    const negotiations = readFileSync(
      new URL("../app/components/OrderIFoodNegotiations.vue", import.meta.url),
      "utf8",
    );
    const feeds = readFileSync(
      new URL("../app/pages/feeds.vue", import.meta.url),
      "utf8",
    );
    const unavailable = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorSessionUnavailable.vue",
        import.meta.url,
      ),
      "utf8",
    );
    const channelHealth = readFileSync(
      new URL("../app/components/ChannelHealthChecklist.vue", import.meta.url),
      "utf8",
    );
    expect(negotiations).not.toContain("<NuxtCard");
    expect(negotiations).toContain("<NuxtSeparator");
    expect(feeds).toMatch(/<NuxtAlert[\s\S]*?data-automatic-row/);
    expect(feeds).not.toMatch(/<NuxtCard[^>]*data-automatic-row/);
    expect(unavailable).toContain("<NuxtEmpty");
    expect(unavailable).not.toContain("<NuxtCard");
    expect(channelHealth).toContain("<NuxtAlert");
    expect(channelHealth).toContain("<NuxtSeparator");
    expect(channelHealth).not.toContain("<NuxtCard");
  });

  it("entrega cards e estados de feedback aos componentes Nuxt UI", () => {
    const appConfig = readFileSync(
      new URL("../../operator-kit/app/app.config.ts", import.meta.url),
      "utf8",
    );
    const card = readFileSync(
      new URL("../app/components/OrderCard.vue", import.meta.url),
      "utf8",
    );
    const feeds = readFileSync(
      new URL("../app/pages/feeds.vue", import.meta.url),
      "utf8",
    );
    const courier = readFileSync(
      new URL("../app/components/OrderCourierPanel.vue", import.meta.url),
      "utf8",
    );
    const catalog = readFileSync(
      new URL("../app/pages/catalog.vue", import.meta.url),
      "utf8",
    );
    const customers = readFileSync(
      new URL("../app/pages/customers/[ref].vue", import.meta.url),
      "utf8",
    );
    const bindings = readFileSync(
      new URL("../app/components/CatalogBindingReview.vue", import.meta.url),
      "utf8",
    );
    expect(appConfig).toMatch(
      /card:\s*\{[\s\S]*?header:\s*["']p-4 sm:p-4["'][\s\S]*?body:\s*["']p-4 sm:p-4 has-\[>\[data-slot=root\]:only-child>table\]:p-0 has-\[>\[data-slot=root\]:only-child>\[data-slot=item\]\]:py-0["'][\s\S]*?footer:\s*["']p-4 sm:p-4["']/,
    );
    expect(appConfig).toMatch(
      /pageCard:\s*\{[\s\S]*?container:\s*["']p-4 sm:p-4["']/,
    );
    expect(card).toMatch(/<NuxtCard\s+as="article"/);
    expect(card).toContain(
      // 1fr, não minmax(0,1fr): numa grade que rola, o corpo não pode encolher
      // abaixo do conteúdo (o rodapé subia por cima dele na Saída).
      'class="grid h-full grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr_auto]"',
    );
    expect(card).toContain(":variant=\"selected ? 'subtle' : 'outline'\"");
    expect(card).toContain("<template #header>");
    expect(card).toContain("<template #footer>");
    // 1/3 + 2/3 quando o rodapé tem largura para isso; abaixo, empilha legível.
    expect(card).toContain(
      "'@[22rem]:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'",
    );
    expect(card).toContain('class="@container flex items-end gap-2"');
    expect(feeds.match(/<template #header>/g)?.length).toBeGreaterThanOrEqual(
      2,
    );
    expect(feeds.match(/<template #footer>/g)?.length).toBeGreaterThanOrEqual(
      2,
    );
    expect(courier).toContain("<template #header>");
    expect(courier).toContain("#footer");
    expect(catalog).not.toContain('<NuxtCard v-if="loading"');
    expect(catalog).toContain(':loading="loading"');
    expect(catalog).toContain("<template #loading>");
    expect(
      customers.match(/<template #header>/g)?.length,
    ).toBeGreaterThanOrEqual(3);
    expect(bindings).toContain("<template #header>");
    expect(card).not.toContain("data-card-pack-declare");
    expect(offenders(/<article\b/)).toEqual([]);
    expect(offenders(/<style\b/)).toEqual([]);
  });

  it("mantém chrome fora da rolagem e filas responsivas no celular", () => {
    const shell = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorSuiteShell.vue",
        import.meta.url,
      ),
      "utf8",
    );
    const queue = readFileSync(
      new URL("../app/components/QueueView.vue", import.meta.url),
      "utf8",
    );
    const board = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );
    const pageHeader = readFileSync(
      new URL(
        "../../operator-kit/app/components/OperatorPageHeader.vue",
        import.meta.url,
      ),
      "utf8",
    );
    expect(shell).not.toContain('class="min-h-0 flex-1 overflow-y-auto"');
    expect(shell).toContain("border-t border-default border-b-0");
    expect(shell).toContain("data-suite-rail-footer");
    expect(shell).toContain("flex-col items-center");
    expect(shell).toContain("data-suite-rail-navigation");
    // Seções e pé do rail: a mesma peça do sino (Chip inset + Button quadrado) e o
    // mesmo espaçamento, em vez de um NavigationMenu recolhido com outra geometria.
    expect(shell).toContain(
      'class="flex w-full min-w-0 flex-col items-center gap-1.5"\n        :aria-label="label"\n        data-suite-rail-navigation',
    );
    expect(shell).not.toMatch(/<NuxtNavigationMenu[^>]*\bcollapsed\b/);
    expect(shell).not.toContain('class="w-fit self-center"');
    expect(shell).toContain('<OperatorInbox placement="rail" />');
    expect(queue).toContain("sm:grid-cols-[80px_minmax(0,1fr)]");
    // Três colunas só a partir do xl, com 240 px para total e gesto; abaixo disso
    // o gesto desce para baixo do conteúdo (184 px cortavam "Recusar | Aceitar").
    expect(queue).toContain("xl:grid-cols-[92px_minmax(0,1fr)_240px]");
    expect(queue).toContain('<template v-if="printedKey(item)" #trailing>');
    expect(queue).toMatch(
      /<NuxtKbd\s+value="enter"\s+size="sm"\s+variant="soft"\s+data-queue-key/,
    );
    expect(queue).not.toContain('size="xl"');
    expect(pageHeader).toContain("flex-nowrap overflow-x-auto no-scrollbar");
    expect(
      [
        board,
        readFileSync(
          new URL("../app/components/OrderCard.vue", import.meta.url),
          "utf8",
        ),
      ]
        .join("\n")
        .replaceAll(/\s+/g, " "),
    ).not.toMatch(/tone[^?]{0,80}=== ['"]late['"][^?]{0,80}\? ['"]error['"]/);
  });

  it("não mistura o estado da visão com a fileira de botões do cabeçalho", () => {
    const board = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );
    expect(board).not.toContain("data-board-view-label");
    // A visão do posto é o título da página; não há selo repetindo-a.
    expect(board).toContain(`:title="exitPostView ? 'Saída' : 'Pedidos'"`);
    expect(board).not.toContain("viewLabel");
  });

  it("tabela no card é branca de ponta a ponta, e a do Catálogo cabe no card", () => {
    const appConfig = readFileSync(
      new URL("../../operator-kit/app/app.config.ts", import.meta.url),
      "utf8",
    ).replaceAll(/\s+/g, " ");
    // O oficial pinta cabeçalho fixo e coluna fixada com `bg-default/75` (o bege da
    // página): a tabela ficava creme dentro do card branco (dono, 07/10/2026).
    expect(appConfig).toContain(
      'pinned: { true: { th: "sticky bg-card z-1", td: "sticky bg-card z-1" }',
    );
    expect(appConfig).toContain(
      'header: { thead: "sticky top-0 inset-x-0 bg-card z-1" }',
    );
    const catalog = readFileSync(
      new URL("../app/pages/catalog.vue", import.meta.url),
      "utf8",
    );
    // Grade sem coluna declarada deixa a tabela crescer até o conteúdo e o card
    // corta a ponta direita, onde mora o ⋯ fixado.
    expect(catalog).toContain(
      "grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)]",
    );
    expect(catalog).toContain('right: ["actions"]');
    expect(catalog).toContain("#actions-cell");
    // Sem grade de planilha: só a divisa entre canais e feeds.
    expect(catalog).not.toContain("border-l border-l-border");
    // O selo "Oculto" já diz; riscar o nome repetia, e o Switch neutral pintava escuro.
    expect(catalog).not.toContain("line-through decoration-1");
    expect(catalog).not.toContain(
      "rowStatuses[row.sku]?.off ? 'neutral' : 'success'",
    );
  });

  it("Em andamento agrupa cada grupo numa lista emoldurada", () => {
    const queue = readFileSync(
      new URL("../app/components/QueueView.vue", import.meta.url),
      "utf8",
    );
    expect(queue).toContain(':data-queue-working-list="group.key"');
    const appConfig = readFileSync(
      new URL("../../operator-kit/app/app.config.ts", import.meta.url),
      "utf8",
    );
    expect(appConfig).toContain(
      "has-[>[data-slot=root]:only-child>[data-slot=item]]:py-0",
    );
  });

  it("menu de ação é DropdownMenu ou ActionList; NavigationMenu é do kit (ledger)", () => {
    const offenders = readdirSync(new URL("../app", import.meta.url), {
      recursive: true,
    })
      .map(String)
      .filter((path) => path.endsWith(".vue"))
      .filter((path) =>
        readFileSync(
          new URL(`../app/${path}`, import.meta.url),
          "utf8",
        ).includes("<NuxtNavigationMenu"),
      );
    expect(offenders).toEqual([]);
    const cardMenu = readFileSync(
      new URL("../app/components/OrderCardMenu.vue", import.meta.url),
      "utf8",
    );
    expect(cardMenu).toContain("<NuxtDropdownMenu");
    expect(cardMenu).toContain("<NuxtModal");
  });
});
