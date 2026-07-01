# ── 构建阶段 ──
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Docker 内 API 走 nginx 代理，不需要绝对地址
ENV VITE_API_BASE_URL=""
RUN npm run build

# ── 运行阶段 ──
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
