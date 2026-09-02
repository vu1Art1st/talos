FROM node:22-alpine AS build

# 使用国内镜像源加速依赖下载；构建时可通过 --build-arg NPM_REGISTRY=xxx 覆盖
# 依赖安装统一走 pnpm（与本地开发一致），--frozen-lockfile 保证与 pnpm-lock.yaml 严格对齐
ARG NPM_REGISTRY=https://registry.npmmirror.com

# 构建上下文为仓库根（见 docker-compose.yml）。容器内复刻仓库布局 /app/frontend + /app/docs，
# 使源码里 ?raw 导入 ../../../docs/OPEN_API_GUIDE.md 的相对路径与本地开发完全一致。
WORKDIR /app/frontend
# 先只拷贝依赖清单以复用缓存层
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
# corepack 下载 pnpm 包管理器自身时默认固定走 registry.npmjs.org，与下面 pnpm 依赖源
# （pnpm config set registry）无关，海外源不可达会 ETIMEDOUT；需额外指定 COREPACK_NPM_REGISTRY，
# 让 corepack 也从国内镜像下载 pnpm 本体。
RUN corepack enable \
  && export COREPACK_NPM_REGISTRY=${NPM_REGISTRY} \
  && pnpm config set registry ${NPM_REGISTRY} \
  && pnpm install --frozen-lockfile
COPY frontend/ .
COPY docs/ ../docs/
RUN pnpm run build

# 非 root 运行：使用官方 unprivileged 镜像，默认以 uid 101 运行并监听 8080（容器内端口；对外发布端口由 docker-compose 的 ports 映射决定），
# pid/临时目录均已指向可写位置，无需额外提权。
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
