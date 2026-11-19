import { render, type RenderResult } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import messages from "../../messages/ru.json";

/** Renders a component with the real Russian message catalogue. */
export function renderWithIntl(ui: ReactElement): RenderResult {
  return render(
    <NextIntlClientProvider locale="ru" messages={messages} timeZone="Europe/Moscow">
      {ui}
    </NextIntlClientProvider>,
  );
}
