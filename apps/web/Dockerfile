# Build context: repo root (.)
# Dockerfile path: apps/web/Dockerfile

# Stage 1: install dependencies
FROM node:22-alpine AS deps
RUN apk add --no-cache libc6-compat
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate
WORKDIR /workspace

# Copy workspace manifests so pnpm can resolve inter-package deps
COPY pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY packages/ts-shared/package.json ./packages/ts-shared/
COPY apps/web/package.json ./apps/web/

RUN pnpm install --frozen-lockfile

# Stage 2: build
FROM node:22-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate
WORKDIR /workspace

COPY --from=deps /workspace/node_modules ./node_modules
COPY pnpm-workspace.yaml ./
COPY packages/ts-shared ./packages/ts-shared
COPY apps/web ./apps/web

# If wasm-core is imported by apps/web, pre-build it with:
#   wasm-pack build --target web packages/wasm-core
# then uncomment:
# COPY packages/wasm-core/pkg ./packages/wasm-core/pkg

ARG NEXT_PUBLIC_API_URL=http://localhost
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm --filter @project/ts-shared build
RUN pnpm --filter web build

# Stage 3: production runner
FROM node:22-alpine AS runner
WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /workspace/apps/web/public ./public
COPY --from=builder --chown=nextjs:nodejs /workspace/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /workspace/apps/web/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

CMD ["node", "server.js"]
