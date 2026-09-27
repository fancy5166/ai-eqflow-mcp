# AI-EqfLow MCP · 一键部署

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#)
[![MCP](https://img.shields.io/badge/Protocol-MCP%20stdio-orange)](https://modelcontextprotocol.io/)

把 [AI-EqfLow](https://aieqflow.com) 中转站的 **7 个 AI 能力**（余额查询 / 模型列表 / 对话 / 生图 / 生视频 / 视频任务查询 / 语音合成）一键装进你正在用的 AI 工具，无需 pip、无需 Node、无需手动改配置。

> **支持**：WorkBuddy · Codex CLI · Claude Desktop · Claude Code · Cursor

---

## ⚡ 30 秒安装（PowerShell 一行命令）

不用下载 zip，直接复制运行（会自动拉取脚本并进入交互安装，粘贴你的 API Key 即可）：

```powershell
irm https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/ai-eqflow-mcp/main/setup.ps1 | iex
```

带 Key 免交互版：

```powershell
$env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/ai-eqflow-mcp/main/setup.ps1 | iex
```

> 脚本做了什么：下载安装器到临时目录 → 固化服务脚本到稳定目录 → 写入令牌 → 注册到检测到的 AI 工具（改前自动备份）→ 拉起服务自检。**可重复执行**（覆盖更新，不会弄坏原有配置）。

不想用一行命令？也可以传统三步：

1. 在 [Releases](../../releases/latest) 下载 `ai-eqflow-mcp-deploy.zip` 并解压
2. 双击 `install.bat`（或命令行 `python install.py --key sk-你的Key`）
3. 看到 `✓ 自检通过：7 个工具在线` 即成功，重启 AI 工具后说一句「**查一下我的 AI-EqfLow 令牌余额**」验证

## 🔑 准备一个 API Key

浏览器打开 https://aieqflow.com → 登录 → 个人中心 → 令牌 → 新建令牌，复制 `sk-` 开头的 Key。
（电脑没有 Python？先去 https://www.python.org/downloads/ 安装，**勾选 Add python.exe to PATH**。）

## 🧰 安装后能干什么（直接说人话）

| 你对 AI 说 | 背后调用的工具 |
| --- | --- |
| 用 Seedance 出一段 5 秒 16:9 的产品视频，存到 E:/out/clip.mp4 | `aieqflow_generate_video` |
| 视频好了吗？task_id 是 151862971，下载到 E:/out/ | `aieqflow_video_status` |
| 把这段台词合成语音，存到 E:/out/voice.mp3 | `aieqflow_tts` |
| 用 AI-EqfLow 生成一张中文促销海报，存到 E:/out/poster.png | `aieqflow_generate_image` |
| AI-EqfLow 上有哪些模型？/ 查一下我的余额 | `aieqflow_list_models` / `aieqflow_quota` |
| 用 Deepseek/Kimi/GPT 帮我写…… | `aieqflow_chat` |

⚠️ 生视频 / 生图 / 语音按量计费，余额在 aieqflow.com 个人中心查看；批量出片前先跟 AI 确认数量。

## 🖥️ 安装后需要重启的工具

| 工具 | 安装后动作 |
| --- | --- |
| WorkBuddy | 完全退出重开；或在连接器管理里对 ai-eqflow 点「信任 / 重载」 |
| Codex CLI | 重开终端（新会话生效） |
| Claude Desktop | 完全退出重开（托盘图标也要退） |
| Claude Code | 重开会话 |
| Cursor | 重启 Cursor |

## ❓ 常见问题

| 现象 | 解决 |
| --- | --- |
| 提示找不到 python | 安装 Python 并勾选 Add to PATH，或用 `py setup` 方式重试 |
| 提示 Missing API key | 重跑安装命令，或手动编辑 `~/.workbuddy/ai-eqflow.env` |
| WorkBuddy 里看不到工具 | 确认 `~/.workbuddy/mcp.json` 里有 `ai-eqflow`；重启 WorkBuddy；连接器界面点「信任」 |
| Codex 里连不上 | 检查 `~/.codex/config.toml` 的 `[mcp_servers.ai-eqflow]`；命令行跑 `codex mcp list` |
| 401 Invalid token | Key 错了 / 被删了，去 aieqflow.com 重新生成后重跑安装命令 |
| 视频出片要多久 | 通常 1–5 分钟；AI 先返回 task_id，稍后让它查状态即可 |

## 🔒 Key 存放在哪（安全须知）

- WorkBuddy：`~/.workbuddy/ai-eqflow.env`（mcp.json 里只放 `${VAR}` 占位符，不落明文）
- Codex / Claude / Cursor：各自配置文件内（本机明文，勿外传配置文件）
- 本仓库**不含也不收集**任何 Key；换 Key 重跑安装命令即可全局更新

## 📦 仓库结构

```
ai-eqflow-mcp/
├── setup.ps1                 # PowerShell 一行安装入口（irm | iex）
├── install.py                # 跨工具一键部署器（仅标准库，幂等）
├── install.bat               # Windows 双击入口
├── server/
│   ├── aieqflow_mcp.py       # MCP stdio server（7 工具）
│   └── aieqflow_client.py    # OpenAI 兼容 + New-API 扩展客户端
├── .github/workflows/release.yml   # push tag 自动打包 Release
└── LICENSE                   # MIT
```

## 🚀 更新 / 发布新版本

```bash
git tag v1.0.1 && git push origin v1.0.1   # GitHub Actions 自动打包并发布 Release
```

## ⚖️ 声明

本项目是 AI-EqfLow 中转站的第三方 MCP 客户端封装，与 aieqflow.com 官方无隶属关系；模型调用产生的费用由你自己的 API Key 承担。请遵守当地法律法规及站点服务条款。

## License

[MIT](LICENSE)
