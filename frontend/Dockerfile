# The envless command centre.
#
#   docker build -t envless-centre \
#     --build-arg NEXT_PUBLIC_ENVLESS_API=http://127.0.0.1:8000 ./frontend
#   docker run --rm -p 3000:3000 envless-centre
#
# NEXT_PUBLIC_ENVLESS_API is read by the browser, not by this container, so it
# is baked into the client bundle at BUILD time. It must therefore be an
# address the browser can reach - the published host port, not a compose
# service name - and changing it means rebuilding, not restarting.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci


FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

ARG NEXT_PUBLIC_ENVLESS_API=http://127.0.0.1:8000
ENV NEXT_PUBLIC_ENVLESS_API=$NEXT_PUBLIC_ENVLESS_API

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 10001 nodejs \
    && adduser --system --uid 10001 nextjs

# Standalone carries its own trimmed node_modules and server.js; static assets
# and public/ are not included in it and have to come across separately.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
