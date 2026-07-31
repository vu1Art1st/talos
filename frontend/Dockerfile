FROM node:20-alpine AS build

WORKDIR /app
COPY package.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

# 非 root 运行：使用官方 unprivileged 镜像，默认以 uid 101 运行并监听 8080，
# pid/临时目录均已指向可写位置，无需额外提权。
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
