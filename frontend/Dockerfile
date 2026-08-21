FROM node:20-alpine AS build

# 使用国内镜像源加速依赖下载；构建时可通过 --build-arg NPM_REGISTRY=xxx 覆盖
# 依赖安装统一走 pnpm（与本地开发一致），--frozen-lockfile 保证与 pnpm-lock.yaml 严格对齐
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && pnpm config set registry ${NPM_REGISTRY} && pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# 非 root 运行：使用官方 unprivileged 镜像，默认以 uid 101 运行并监听 8080（容器内端口；对外发布端口由 docker-compose 的 ports 映射决定），
# pid/临时目录均已指向可写位置，无需额外提权。
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
