import withNuxt from "./.nuxt/eslint.config.mjs";
import operatorKit from "../operator-kit/eslint.config.base.mjs";
import prettier from "eslint-config-prettier";

export default withNuxt(...operatorKit, prettier);
