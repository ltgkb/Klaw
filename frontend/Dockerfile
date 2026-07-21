# 前端 Dockerfile — 多阶段构建
# 1. 构建阶段
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2. 运行阶段 (nginx 静态服务 + API 反向代理)
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA 路由回退 + /api 反向代理到后端
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
\n\
    # API 反向代理到后端\n\
    location /api/ {\n\
        proxy_pass http://backend:8000;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_http_version 1.1;\n\
        proxy_buffering off;\n\
        proxy_cache off;\n\
        proxy_read_timeout 3600s;\n\
    }\n\
\n\
    # SPA 路由回退\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
