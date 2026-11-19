// Shared ESLint flat config for every TypeScript package in the monorepo.
import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";

export const ignores = {
  ignores: [
    "**/node_modules/**",
    "**/.next/**",
    "**/.turbo/**",
    "**/dist/**",
    "**/coverage/**",
    "**/src/generated/**",
    "**/next-env.d.ts",
    "**/test-results/**",
    "**/playwright-report/**",
  ],
};

export const base = tseslint.config(
  ignores,
  js.configs.recommended,
  ...tseslint.configs.strict,
  ...tseslint.configs.stylistic,
  {
    languageOptions: {
      globals: { ...globals.node },
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": "error",
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  prettier,
);

export default base;
