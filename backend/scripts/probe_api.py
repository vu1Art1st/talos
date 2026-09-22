"""关键接口探针：把 AGENTS.md「验收口径」里的接口巡检固化为可重复执行的命令。

背景：此前每次验证都临时写一份探针脚本、跑完即删（AGENTS.md 原文「脚本用完即删」），
既费时又无法保证覆盖一致。本脚本把「form 表单登录 + 22 个关键接口全 200」固化下来，
本地开发、容器、CI 与发布前检查共用同一份口径。

用法（可在宿主机 venv，也可在容器内；不依赖 app 配置，只需 httpx）：

    # 本地开发后端（dev.ps1 / dev.sh 起的 27015）
    backend/.venv/Scripts/python -m scripts.probe_api --base-url http://127.0.0.1:27015

    # 容器部署（前端 Nginx 反代 /api，仅 27012 对外）
    python -m scripts.probe_api --base-url http://127.0.0.1:27012

    # 容器内直连 api 进程
    docker compose exec -T api python -m scripts.probe_api --base-url http://127.0.0.1:8000

退出码：0 = 全部 200；1 = 有接口未通过或登录失败（明细打印到 stdout）。
"""
import argparse
import sys

import httpx

# AGENTS.md 验收口径固化的 22 个关键接口（相对 /api/v1）
ENDPOINTS: tuple[str, ...] = (
    "/meta",
    "/vulns",
    "/vulns/stats",
    "/reports",
    "/testing-plans",
    "/testing-plans/stats",
    "/testing-plans/conclusion",
    "/nonpen-plans",
    "/nonpen-plans/stats",
    "/remote-testings",
    "/spring-actions",
    "/knowledge",
    "/knowledge/search?q=注入",
    "/search?q=a",
    "/assets",
    "/users",
    "/roles",
    "/groups",
    "/pats",
    "/notify-channels",
    "/audit/logs",
    "/imports",
)


def _login(client: httpx.Client, username: str, password: str) -> str | None:
    """form 表单登录（必须用 data=，JSON 会 422），返回 access_token。"""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    if resp.status_code != 200:
        print(f"[probe] 登录失败：HTTP {resp.status_code} {resp.text[:200]}")
        return None
    token = resp.json().get("access_token")
    if not token:
        print("[probe] 登录响应缺少 access_token")
        return None
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="关键接口探针（全部 200 视为通过）")
    parser.add_argument("--base-url", default="http://127.0.0.1:27015", help="后端或前端反代地址")
    parser.add_argument("--username", default="admin1", help="登录账号（容器数据为 admin1）")
    parser.add_argument("--password", default="123456", help="登录口令")
    parser.add_argument("--timeout", type=float, default=30.0, help="单请求超时（秒）")
    parser.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    failures: list[str] = []
    with httpx.Client(base_url=base, timeout=args.timeout) as client:
        token = _login(client, args.username, args.password)
        if token is None:
            return 1
        headers = {"Authorization": f"Bearer {token}"}
        for path in ENDPOINTS:
            try:
                resp = client.get(f"/api/v1{path}", headers=headers)
            except httpx.HTTPError as exc:  # 连接失败/超时也计入失败，不中断其余巡检
                failures.append(f"{path} → {exc.__class__.__name__}: {exc}")
                print(f"[probe] FAIL {path} {exc.__class__.__name__}")
                continue
            ok = resp.status_code == 200
            if not ok:
                failures.append(f"{path} → HTTP {resp.status_code} {resp.text[:120]}")
            if not args.quiet or not ok:
                # 用 ASCII 标记而非 ✓/✗：Windows 控制台默认 GBK，非 GBK 字形会抛 UnicodeEncodeError
                mark = "OK  " if ok else "FAIL"
                print(f"[probe] {mark} {path} {resp.status_code}")

    total = len(ENDPOINTS)
    if failures:
        print(f"\n[probe] 失败 {len(failures)}/{total}（base_url={base}）：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"\n[probe] 通过 {total}/{total}（base_url={base}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
