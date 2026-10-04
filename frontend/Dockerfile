FROM node:22-slim

WORKDIR /srv/frontend
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN npm ci

COPY . .

EXPOSE 5173
# Vite dev server; /api is proxied to API_PROXY_TARGET (see vite.config.ts).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
