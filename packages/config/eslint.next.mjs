// ESLint flat config for the Next.js application.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier";

import { ignores } from "./eslint.base.mjs";

/** The browser application talks to the backend over HTTP only (ARCHITECTURE.md). */
const noDirectDataAccess = {
  rules: {
    "no-restricted-imports": [
      "error",
      {
        paths: ["pg", "postgres", "redis", "ioredis"].map((name) => ({
          name,
          message: "apps/web must not connect to PostgreSQL or Redis; call the API.",
        })),
      },
    ],
    "@typescript-eslint/consistent-type-imports": "error",
    "no-console": ["error", { allow: ["warn", "error"] }],
  },
};

export const next = [
  ignores,
  ...nextCoreWebVitals,
  ...nextTypescript,
  noDirectDataAccess,
  prettier,
];

export default next;
