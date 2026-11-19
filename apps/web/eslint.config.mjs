import next from "@crm/config/eslint/next";

const config = [...next, { settings: { next: { rootDir: import.meta.dirname } } }];

export default config;
