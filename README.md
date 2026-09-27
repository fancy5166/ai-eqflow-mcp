# AI-EqfLow MCP · 一键部署

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#)
[![MCP](https://img.shields.io/badge/Protocol-MCP%20stdio-orange)](https://modelcontextprotocol.io/)

把 [AI-EqfLow](https://aieqflow.com) 中转站的 **7 个 AI 能力**（余额查询 / 模型列表 / 对话 / 生图 / 生视频 / 视频任务查询 / 语音合成）一键装进你正在用的 AI 工具，无需 pip、无需 Node、无需手动改配置。

> **支持**：WorkBuddy · Codex CLI · Claude Desktop · Claude Code · Cursor

---

## ⚡ 30 秒安装

### 第 0 步：先拿到你的 API Key（唯一要准备的东西）

浏览器打开 https://aieqflow.com → 登录 → 个人中心 → 令牌 → **新建令牌** → 复制那串 `sk-` 开头的 Key。

> 下面教程里我都用 `sk-abc123xyz` 当作**假 Key** 举例——实际粘贴时请换成你自己复制的那串。
> 电脑没装 Python？先去 https://www.python.org/downloads/ 下载安装，安装时**务必勾选 "Add python.exe to PATH"**，装完重开命令行窗口再继续。

---

### 方式一：PowerShell 一行安装（推荐）

按 `Win` 键 → 输入 `powershell` → 回车打开蓝色窗口，复制下面任意一条：

**① 交互版（会提示你粘贴 Key，最简单）：**

```powershell
irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex
```

运行后会看到提示 `粘贴 AI-EqfLow API Key（输入不回显）:` ——直接 `Ctrl+V` 粘贴你的 Key 再回车即可（**不回显是正常的安全设计，不是没输进去**）。

**② 带 Key 版（一步到位，不想被提示就用这条）：**

```powershell
$env:AIEQFLOW_API_KEY="sk-abc123xyz"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex
```

**命令逐段拆解（哪里需要换、哪里原样照抄）：**

| 片段 | 是什么意思 | 需要改吗 |
| --- | --- | --- |
| `irm` | Invoke-RestMethod 的缩写，PowerShell 自带的「下载」命令，从网址拉取脚本内容 | ❌ 原样照抄 |
| `https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1` | 安装脚本的下载地址（GitHub 的原始文件服务）：`fancy5166` = 仓库作者账号，`ai-eqflow-mcp` = 仓库名，`main` = 主分支，`setup.ps1` = 安装脚本文件 | ❌ 原样照抄 |
| `\|` 竖线 | 管道符，把上一步下载到的内容「递给」下一步 | ❌ 原样照抄 |
| `iex` | Invoke-Expression 缩写，把递过来的脚本内容立即执行 | ❌ 原样照抄 |
| `$env:AIEQFLOW_API_KEY="sk-abc123xyz"` | 把你的 Key 存进一个叫 `AIEQFLOW_API_KEY` 的临时环境变量，安装脚本会自动读取它（只在当前窗口有效，不落盘） | ⚠️ **`sk-abc123xyz` 必须换成你的真实 Key**，其余原样 |
| `;` 分号 | 分隔两条命令：先设变量、再运行安装 | ❌ 原样照抄 |

> **✅ 默认就全装，不用每个工具跑一遍**：上面命令**跑一次**，会自动检测你电脑上装了哪些 AI 工具（WorkBuddy / Codex CLI / Claude Desktop / Claude Code / Cursor），**检测到几个装几个**，一次到位。

**进阶：只想装指定的几个工具？** 在带 Key 版前面多设一个 `AIEQFLOW_TARGETS` 变量即可（仍是一条命令）：

```powershell
$env:AIEQFLOW_TARGETS="workbuddy,codex"; $env:AIEQFLOW_API_KEY="sk-abc123xyz"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex
```

| 片段 | 是什么意思 | 需要改吗 |
| --- | --- | --- |
| `$env:AIEQFLOW_TARGETS="workbuddy,codex"` | 指定只装哪些工具，逗号分隔，可用值：`workbuddy` / `codex` / `claude-desktop` / `claude-code` / `cursor` | ⚠️ 按你想要的组合填；**不设这条就默认全装** |
| 其余部分 | 与方式一②完全相同 | ⚠️ Key 换成你的真实 Key |

**按工具速查：只装某一个？直接复制对应那条**（Key 记得换成你的）：

| 你想装到 | 复制这条命令（PowerShell） |
| --- | --- |
| 仅 WorkBuddy | `$env:AIEQFLOW_TARGETS="workbuddy"; $env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 \| iex` |
| 仅 Codex CLI | `$env:AIEQFLOW_TARGETS="codex"; $env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 \| iex` |
| 仅 Claude Desktop | `$env:AIEQFLOW_TARGETS="claude-desktop"; $env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 \| iex` |
| 仅 Claude Code | `$env:AIEQFLOW_TARGETS="claude-code"; $env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 \| iex` |
| 仅 Cursor | `$env:AIEQFLOW_TARGETS="cursor"; $env:AIEQFLOW_API_KEY="sk-你的Key"; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 \| iex` |
| 装多个（任选组合） | `TARGETS` 里用逗号连接，如 `"workbuddy,codex,cursor"` |
| 全装（不挑） | 直接用最上面的方式一②，不写 `TARGETS` 即可 |

> CMD（命令提示符）用户：把上表任意一条用 `powershell -c "..."` 包起来运行，例如
> `powershell -c "$env:AIEQFLOW_TARGETS='codex'; $env:AIEQFLOW_API_KEY='sk-你的Key'; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex"`（注意引号内 Key 用单引号）。

---

### 方式二：CMD（命令提示符）一行安装

按 `Win` 键 → 输入 `cmd` → 回车打开黑色窗口，复制下面任意一条：

**① 交互版（会提示你粘贴 Key）：**

```bat
powershell -c "irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex"
```

**② 带 Key 版：**

```bat
powershell -c "$env:AIEQFLOW_API_KEY='sk-abc123xyz'; irm https://raw.githubusercontent.com/fancy5166/ai-eqflow-mcp/main/setup.ps1 | iex"
```

**命令逐段拆解：**

| 片段 | 是什么意思 | 需要改吗 |
| --- | --- | --- |
| `powershell` | 在 CMD 里调用 PowerShell（CMD 本身没有下载命令，借用它来执行） | ❌ 原样照抄 |
| `-c` | `-Command` 的缩写，表示后面引号里是一段要执行的命令 | ❌ 原样照抄 |
| `"..."` 双引号 | 把整条 PowerShell 命令包起来整体传给它 | ❌ 原样照抄 |
| `$env:AIEQFLOW_API_KEY='sk-abc123xyz'` | 同方式一：存入你的 Key。⚠️ 注意 CMD 版 Key 外面用的是**单引号**（因为双引号已被外层占用），单双引号别抄混 | ⚠️ **换成你的真实 Key** |
| `irm ... \| iex` | 与方式一完全相同 | ❌ 原样照抄 |

---

### 方式三：手动下载安装（不用命令行）

1. 打开 [Releases 页面](../../releases/latest)，下载 `ai-eqflow-mcp-deploy.zip`
2. 解压到任意文件夹（比如桌面），**双击 `install.bat`** → 按提示粘贴 API Key（默认全装）
3. 看到 `✓ 自检通过：7 个工具在线` 就是装好了

想只装指定工具，可在解压目录的命令行里运行（`--targets` 按需组合）：

```bat
python install.py --key sk-abc123xyz --targets workbuddy,codex
```

---

### 装完之后：重启 + 验证

| AI 工具 | 装完做什么 |
| --- | --- |
| WorkBuddy | 完全退出重开（或连接器管理里对 ai-eqflow 点「信任/重载」） |
| Codex CLI / Claude Code | 重开终端 / 新会话 |
| Claude Desktop | 完全退出重开（托盘图标也要退） |
| Cursor | 重启 Cursor |

然后在 AI 对话里说一句：

> 查一下我的 AI-EqfLow 令牌余额

能返回「令牌名称 / total_used」等信息 = 部署成功 ✅

> **脚本都做了什么**：下载安装器到临时目录 → 把服务脚本固化到稳定目录（`~/.workbuddy/custom-connectors/ai-eqflow/server/`）→ 写入令牌 → 注册到检测到的 AI 工具（改配置前自动备份）→ 拉起服务自检。**可重复执行**（覆盖更新，不会弄坏原有配置；重跑一次即可更新到最新版）。

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

## ❓ 常见问题

| 现象 | 解决 |
| --- | --- |
| 提示找不到 python | 安装 Python 并勾选 Add to PATH，装完**重开命令行窗口**再重跑安装命令 |
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
git tag v1.0.1
git push origin v1.0.1   # GitHub Actions 自动打包并发布 Release
```

## ⚖️ 声明

本项目是 AI-EqfLow 中转站的第三方 MCP 客户端封装，与 aieqflow.com 官方无隶属关系；模型调用产生的费用由你自己的 API Key 承担。请遵守当地法律法规及站点服务条款。

## License

[MIT](LICENSE)
