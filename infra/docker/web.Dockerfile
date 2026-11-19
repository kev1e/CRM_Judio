# Next.js application as a self-contained server bundle.
# Build context: repository root.
ARG NODE_VERSION=26.13.1

FROM node:${NODE_VERSION}-trixie-slim AS builder

ENV NEXT_TELEMETRY_DISABLED=1 \
    CI=true

RUN npm install --global --no-fund --no-audit pnpm@12.20.0

WORKDIR /repo

# Dependencies first: this layer is rebuilt only when a manifest or the lockfile changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/config/package.json packages/config/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN pnpm install --frozen-lockfile --filter "@crm/web..."

COPY packages/config packages/config
COPY packages/contracts packages/contracts
COPY apps/web apps/web
RUN pnpm --filter @crm/web run build


FROM node:${NODE_VERSION}-trixie-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app
COPY --from=builder --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static

USER node
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
