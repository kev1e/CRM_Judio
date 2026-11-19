// Russian is the default and, for now, the only locale. Adding a locale means
// adding it here and providing messages/<locale>.json — components do not change.
export const locales = ["ru"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "ru";
export const timeZone = "Europe/Moscow";
