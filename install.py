#!/usr/bin/env python3
"""AI-EqfLow MCP 一键部署脚本（保姆式，幂等可重复执行）。

用法：
    python install.py                          # 交互式：提示粘贴 API Key，部署到检测到的全部 AI 工具
    python install.py --key sk-xxxx            # 带免输 Key
    python install.py --targets workbuddy,codex  # 只部署到指定工具
    python install.py --targets workbuddy --key sk-xxx --base-url https://aieqflow.com/v1

支持目标：workbuddy / codex / claude-desktop / claude-code / cursor
依赖：仅 Python 3.10+ 标准库，无需 pip install。
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

SERVER_FILES = ["aieqflow_mcp.py", "aieqflow_client.py"]
SERVER_ID = "ai-eqflow"
DEFAULT_BASE = "https://aieqflow.com/v1"
ALL_TARGETS = ["workbuddy", "codex", "claude-desktop", "claude-code", "cursor"]

G, Y, R, C, N = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"


def ok(msg: str) -> None:
    print(f"{G}✓{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}!{N} {msg}")


def fail(msg: str) -> None:
    print(f"{R}✗{N} {msg}")


def backup(p: Path) -> Path | None:
    if p.exists():
        b = p.with_name(p.name + ".bak-" + datetime.now().strftime("%Y%m%d%H%M%S"))
        shutil.copy2(p, b)
        return b
    return None


def mask(secret: str) -> str:
    return secret[:6] + "..." + secret[-4:] if len(secret) > 12 else "***"


# ---------------------------------------------------------------- paths
def workbuddy_home() -> Path:
    return Path(os.environ.get("WORKBUDDY_HOME") or (Path.home() / ".workbuddy"))


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def claude_desktop_config() -> Path | None:
    appdata = os.environ.get("APPDATA")
    return (Path(appdata) / "Claude" / "claude_desktop_config.json") if appdata else None


def cursor_mcp() -> Path:
    return Path(os.environ.get("CURSOR_HOME") or (Path.home() / ".cursor")) / "mcp.json"


def claude_code_config() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    p = Path(base)
    return (p / ".claude.json") if p.is_dir() else (Path.home() / ".claude.json")


def mcp_entry(python_exe: str, script: Path, key: str, base_url: str) -> dict:
    return {
        "type": "stdio",
        "command": python_exe,
        "args": [str(script)],
        "env": {"AIEQFLOW_API_KEY": key, "API_BASE": base_url, "MIN_QUOTA_USD": "1.0"},
        "disabled": False,
    }


def merge_json_config(path: Path, key_name: str, entry: dict) -> bool:
    """把 entry 合并进 json 顶层/嵌套 mcpServers。存在同名则覆盖。返回是否写入。"""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            warn(f"{path} 解析失败（{e}），跳过该目标")
            return False
    backup(path)
    servers = data.setdefault("mcpServers", {})
    servers[key_name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------- targets
def deploy_workbuddy(python_exe: str, script: Path, key: str, base_url: str) -> bool:
    home = workbuddy_home()
    stable = home / "custom-connectors" / SERVER_ID / "server"
    stable.mkdir(parents=True, exist_ok=True)
    for f in SERVER_FILES:
        shutil.copy2(Path(__file__).resolve().parent / "server" / f, stable / f)
    # 单一令牌源：<id>.env（WorkBuddy 表单未填时的回退）
    env_file = home / f"{SERVER_ID}.env"
    env_file.write_text(f"AIEQFLOW_API_KEY={key}\nAPI_BASE={base_url}\n", encoding="utf-8")
    # WorkBuddy 表单占位符模式：mcp.json 里放 ${VAR}，脚本自动回退 .env
    entry = {
        "type": "stdio",
        "command": python_exe,
        "args": [str(stable / "aieqflow_mcp.py")],
        "env": {
            "AIEQFLOW_API_KEY": "${AIEQFLOW_API_KEY}",
            "API_BASE": base_url,
            "MIN_QUOTA_USD": "1.0",
        },
        "disabled": False,
    }
    mcp_json = home / "mcp.json"
    b = backup(mcp_json)
    data = {}
    if mcp_json.exists():
        try:
            data = json.loads(mcp_json.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            fail(f"{mcp_json} 解析失败：{e}")
            return False
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_ID] = entry
    mcp_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"WorkBuddy：mcp.json 已注册（脚本 → {stable}），令牌 → {env_file}" + (f"，备份 {b.name}" if b else ""))
    return True


def deploy_codex(python_exe: str, script: Path, key: str, base_url: str) -> bool:
    cfg = codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    backup(cfg)
    section_header = f"[mcp_servers.{SERVER_ID}]"
    # TOML 双引号字符串会把 \\ 当转义符，Windows 路径必须用单引号字面量
    lines = [
        section_header,
        f"command = '{python_exe}'",
        f"args = ['{script}']",
        "env = { AIEQFLOW_API_KEY = \"" + key + "\", API_BASE = \"" + base_url + "\", MIN_QUOTA_USD = \"1.0\" }",
    ]
    block = "\n".join(lines) + "\n\n"
    # 移除旧 section（从 [mcp_servers.ai-eqflow] 到下一个 [ 或 EOF）
    if section_header in text:
        out, skip = [], False
        for line in text.splitlines():
            if line.strip() == section_header:
                skip = True
                continue
            if skip and line.strip().startswith("["):
                skip = False
            if not skip:
                out.append(line)
        text = "\n".join(out).rstrip() + "\n\n"
    cfg.write_text(text + block, encoding="utf-8")
    ok(f"Codex：{cfg} 已注册（重启 Codex 后生效）")
    return True


def deploy_claude_desktop(python_exe: str, script: Path, key: str, base_url: str) -> bool:
    cfg = claude_desktop_config()
    if cfg is None:
        warn("Claude Desktop：未检测到 %APPDATA%，跳过")
        return False
    return merge_json_config(cfg, SERVER_ID, mcp_entry(python_exe, script, key, base_url))


def deploy_claude_code(python_exe: str, script: Path, key: str, base_url: str) -> bool:
    cfg = claude_code_config()
    return merge_json_config(cfg, SERVER_ID, mcp_entry(python_exe, script, key, base_url))


def deploy_cursor(python_exe: str, script: Path, key: str, base_url: str) -> bool:
    return merge_json_config(cursor_mcp(), SERVER_ID, mcp_entry(python_exe, script, key, base_url))


TARGET_FN = {
    "workbuddy": deploy_workbuddy,
    "codex": deploy_codex,
    "claude-desktop": deploy_claude_desktop,
    "claude-code": deploy_claude_code,
    "cursor": deploy_cursor,
}


# ---------------------------------------------------------------- self check
def self_check(python_exe: str, script: Path) -> bool:
    """拉起 stdio server，验证 initialize + tools/list。"""
    try:
        proc = subprocess.Popen(
            [python_exe, str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
    except Exception as e:  # noqa: BLE001
        fail(f"无法启动 server：{e}")
        return False
    try:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                "clientInfo": {"name": "installer", "version": "1.0"}}}) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        proc.stdin.flush()
        deadline = time.time() + 20
        tools = None
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2:
                tools = [t.get("name") for t in (msg.get("result") or {}).get("tools") or []]
                break
        if tools is None:
            fail("server 无响应（tools/list 超时）")
            return False
        if len(tools) < 7:
            fail(f"工具数量异常：{len(tools)}（预期 7）：{tools}")
            return False
        ok(f"自检通过：7 个工具在线（{', '.join(tools)}）")
        return True
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="AI-EqfLow MCP 一键部署")
    ap.add_argument("--key", help="API Key（sk- 开头）；不传则交互输入")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=f"API 地址（默认 {DEFAULT_BASE}）")
    ap.add_argument("--targets", default="all",
                    help="逗号分隔：workbuddy,codex,claude-desktop,claude-code,cursor 或 all")
    ap.add_argument("--skip-check", action="store_true", help="跳过部署后自检")
    args = ap.parse_args()

    pkg = Path(__file__).resolve().parent
    server_src = pkg / "server"
    for f in SERVER_FILES:
        if not (server_src / f).exists():
            fail(f"缺少 {server_src / f}（请完整解压部署包后再运行）")
            return 2

    key = (args.key or "").strip()
    if not key:
        key = getpass.getpass("粘贴 AI-EqfLow API Key（输入不回显）: ").strip()
    if not key.startswith("sk-"):
        fail("API Key 应以 sk- 开头（获取：https://aieqflow.com → 个人中心 → 令牌）")
        return 2

    python_exe = sys.executable or "python"

    # 统一先把服务脚本固化到稳定目录（三原则：所有工具都指向这里，删包不断链）
    stable = workbuddy_home() / "custom-connectors" / SERVER_ID / "server"
    stable.mkdir(parents=True, exist_ok=True)
    for f in SERVER_FILES:
        shutil.copy2(server_src / f, stable / f)
    ok(f"服务脚本已固化：{stable}")
    script = stable / "aieqflow_mcp.py"

    if args.targets.strip().lower() == "all":
        targets = list(ALL_TARGETS)
    else:
        targets = [t.strip().lower() for t in args.targets.split(",") if t.strip()]
        bad = [t for t in targets if t not in ALL_TARGETS]
        if bad:
            fail(f"未知目标：{bad}（可选：{', '.join(ALL_TARGETS)}）")
            return 2

    print(f"{C}AI-EqfLow MCP 一键部署{N}  key={mask(key)}  base={args.base_url}")
    print("=" * 72)
    print(f"目标：{', '.join(targets)}\n")

    results = {}
    for t in targets:
        try:
            results[t] = TARGET_FN[t](python_exe, script, key, args.base_url)
        except Exception as e:  # noqa: BLE001
            fail(f"{t} 部署异常：{type(e).__name__}: {e}")
            results[t] = False

    if not args.skip_check:
        print()
        self_check(python_exe, script)

    print("\n" + "=" * 72)
    done = [t for t, r in results.items() if r]
    skipped = [t for t, r in results.items() if not r]
    if done:
        ok(f"已部署：{', '.join(done)}")
    if skipped:
        warn(f"跳过/失败：{', '.join(skipped)}（对应工具未安装或配置异常）")
    print(f"""
{C}下一步（人工确认）：{N}
1. 重启对应 AI 工具（WorkBuddy 需完全退出重开，或在其连接器界面点「信任/重载」）
2. 在 AI 对话里说：{Y}查一下我的 AI-EqfLow 令牌余额{N} —— 能返回点数即部署成功
3. 常用指令示例：出视频 / 合成语音 / 生成海报（详见 README.md 第 4 节）

Key 存放位置（勿外传）：{workbuddy_home() / f'{SERVER_ID}.env'} 及各工具配置文件
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
