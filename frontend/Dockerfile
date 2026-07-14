# 前端 Dockerfile — 多阶段构建
# 1. 构建阶段
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2. 运行阶段 (nginx 静态服务)
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA 路由回退到 index.html
RUN echo 'server { listen 80; root /usr/share/nginx/html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
