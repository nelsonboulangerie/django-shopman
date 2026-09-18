// Flat config do operator-kit — o layer se linta a si mesmo.
//
// Por que NÃO começa em `./.nuxt/eslint.config.mjs` como os apps irmãos: o kit é
// um LAYER, não um app. `nuxt prepare` até roda aqui (gera tipos), mas não produz
// `.nuxt/eslint.config.mjs`: esse arquivo é obra do módulo `@nuxt/eslint`, e o
// `nuxt.config.ts` do layer não registra módulo nenhum de propósito — módulo
// declarado no layer vaza por `extends` para as nove superfícies hospedeiras.
// Então montamos o preset à mão: js + typescript-eslint + eslint-plugin-vue,
// mais a MESMA base compartilhada que os apps aplicam, e Prettier por último.
import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";
import vueParser from "vue-eslint-parser";

import operatorKitBase from "./eslint.config.base.mjs";

export default [
  {
    ignores: [
      "**/.nuxt/**",
      "**/.output/**",
      "**/dist/**",
      "**/node_modules/**",
      "**/public/**",
      "package-lock.json",
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],

  {
    // O layer é isomórfico: `app/` roda no browser, `server/` e `runtime/server/`
    // no Nitro, `scripts/` no Node. Declarar os três evita `no-undef` falso em
    // `window`, `process` e afins sem desligar a regra para o repositório todo.
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.serviceworker },
    },
    rules: {
      // Nuxt auto-importa (`ref`, `computed`, `defineNuxtPlugin`, `useRuntimeConfig`,
      // `defineEventHandler`, `createError`, …). Sem o módulo `@nuxt/eslint` para
      // declarar esses globais, `no-undef` acusaria cada um deles. É exatamente o
      // que o preset do Nuxt faz nos apps: desliga a regra e deixa o TypeScript
      // (que conhece os tipos gerados em `.nuxt/`) responder por símbolo inexistente.
      "no-undef": "off",
    },
  },

  {
    // `.vue` precisa do parser de SFC por fora e do parser TS dentro do `<script>`.
    // Nos apps isso vem pronto do preset gerado; aqui é explícito.
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        ecmaVersion: "latest",
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
    },
  },

  ...operatorKitBase,

  {
    // O bloco `app/components/Ui/**` da base afrouxa `any`/`v-html` para as primitivas
    // VENDADAS do ui-thing/reka-ui, que nos apps moram nesse diretório. No kit os
    // `Ui*.vue` são planos (`app/components/UiNativeSelect.vue`) — o glob da base nem
    // os alcança — e, o que decide a questão, são ESCRITOS AQUI: não são superfície
    // pública de lib de terceiro a re-tipar. A permissão NÃO se estende a eles.
    //
    // Vem DEPOIS da base de propósito e cobre as duas formas (plana e aninhada): se
    // um dia alguém criar `app/components/Ui/` no kit, o afrouxamento da base não
    // pega carona — o componente do kit continua respondendo pelas três regras.
    files: ["app/components/Ui*.vue", "app/components/Ui/**/*.vue"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-empty-object-type": "error",
      "vue/no-v-html": "error",
    },
  },

  prettier,
];
