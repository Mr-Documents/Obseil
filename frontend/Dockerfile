# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Obseil web client
# Built once with Vite, then served as static files by nginx. The API base URL
# is a build argument because Vite inlines it at build time.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# Run unprivileged: nginx:alpine ships an "nginx" user, and 8080 needs no root.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html
USER nginx

EXPOSE 8080

# Probe 127.0.0.1, not "localhost": nginx binds IPv4 only (see nginx.conf),
# while this image resolves localhost to ::1, so the check was refused on a
# container that was serving perfectly well. busybox wget does not fall back
# to IPv4 the way curl does, so the address has to be explicit.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
