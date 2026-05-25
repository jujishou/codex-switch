# codex-switch

> 给 OpenAI **Codex App** 接入 DeepSeek / Kimi / 智谱 / 通义 等任意 OpenAI 兼容大模型的桌面切换器。**一键切换、一键回滚。** Windows GUI。

<table align="center">
  <tr>
    <td align="center" width="280">
      <img src="docs/xiaohongshu-qr.jpg" width="200" alt="小红书 - 跟着阿亮学AI" /><br/>
      <b>📕 小红书</b><br/>
      <code>migeai</code> · 跟着阿亮学AI<br/>
      🔗 <a href="https://www.xiaohongshu.com/user/profile/5f84695f0000000001008c8d?xsec_token=ABwF5Byv3YIJkaQ6Nowz_YKz9AG3qztgK-tGv6mxjYg8U%3D&xsec_source=pc_search">点击打开小红书主页</a>
    </td>
    <td align="center" width="280">
      <img src="docs/douyin-qr.jpg" width="200" alt="抖音 - 跟着阿亮学AI" /><br/>
      <b>🎵 抖音</b><br/>
      <code>migeaiketang</code> · @跟着阿亮学AI<br/>
      🔗 <a href="https://v.douyin.com/Wjw2ZK53MEM">点击打开抖音主页</a>
    </td>
  </tr>
</table>

![status](https://img.shields.io/badge/status-beta-orange)
![platform](https://img.shields.io/badge/platform-Windows-blue)
![license](https://img.shields.io/badge/license-MIT-green)

<!-- 截图占位：发布时贴一张主界面图
![screenshot](docs/screenshot.png)
-->

---

## 它解决什么

OpenAI Codex App 默认只能用官方 GPT 模型。但你可能希望：

- **省钱**：换成 DeepSeek、Kimi、智谱、通义、Groq 等便宜很多倍的模型
- **国内速度**：直连国内厂商 API，不走代理
- **多家随手切**：今天用 DeepSeek，明天用 Kimi，再后天试自己加的 GLM

codex-switch 在你本机起一个翻译官（Codex `Responses` API ↔ OpenAI `chat/completions`），帮你把 Codex 的请求转给你选的任何 OpenAI 兼容上游。

---

## 特性

- 🪄 **一键切换**：选模型 → 输 Key → 点按钮，完事
- ↩️ **一键回滚**：随时切回 OpenAI 原版，零残留
- 🧱 **多家内置**：DeepSeek × 2、Kimi × 4，开箱即用
- ➕ **自定义提供商**：内置 9 个常见平台模板（智谱/通义/零一/豆包/Groq/Mistral/OpenRouter 等），选模板自动填 Base URL，只补 Key 就能用；模板没收录的可全手填
- 🔐 **Key 分家存**：每家 Key 单独保存，互不覆盖，下次自动加载
- 🛡️ **不破坏原配置**：字段级合并 Codex `config.toml`，保留你所有原有的 `[projects]` / `[plugins]` / `[marketplaces]` 配置
- 💾 **自动备份**：第一次切之前自动把原 `config.toml` 备份到 `.openai-backup`
- 🌗 **浅色/深色**：CustomTkinter 现代 UI，跟随系统主题
- 📦 **单文件 .exe**：无需装 Python，双击即用

---

## 谁能用

- **OS**：Windows 10 / 11（其它平台未测试）
- **前置**：装好 OpenAI Codex App（任意版本）
- **依赖**：无（.exe 自带运行时；自己跑源码需 Python 3.10+）

---

## 用法（用 .exe）

1. 从 [Releases](../../releases) 下载 `codex-switch.exe`
2. 双击启动（第一次可能慢 5-10 秒，正常）
3. 在窗口里：
   - 模型下拉选一个（DeepSeek/Kimi/...）
   - 粘贴对应平台的 API Key
   - 点蓝色按钮 **▶ 启动翻译官 + 切到所选模型**
4. 打开 Codex App，开始用
5. 不用了：点红色按钮 **⏸ 停止翻译官 + 切回 OpenAI**

详细图文说明见 [`release/使用说明.txt`](release/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.txt)。

---

## 加新模型

GUI 里点 **「+ 自定义」**：
- 选预设模板（含 9 个常见平台），自动填 Base URL；只输 Key
- 或者模板选「自定义」，全手填 4 个字段：显示名 / 模型 ID / Base URL / API Key

「管理」按钮可列出所有自定义条目，逐条删除。

---

## 自己跑源码 / 自己打包

```powershell
# 1. 克隆
git clone https://github.com/<your-user>/codex-switch.git
cd codex-switch

# 2. 装依赖
pip install -r requirements.txt

# 3. 跑 GUI
python src/gui_ctk.py

# 4. 跑测试（不碰你真实配置，全沙箱）
python src/tests/test_core.py

# 5. 一键打包成单 .exe
.\build.ps1
# 产物：release\codex-switch.exe
```

---

## 项目结构

```
codex-switch/
├─ src/
│   ├─ adapter.py       # 翻译官：Codex Responses ↔ OpenAI chat/completions
│   │                   # 源自 LearnPrompt/stepfun-codex-adapter (MIT)，见 NOTICE
│   ├─ core.py          # 配置管理、provider 路由、Key 分家存、子线程 server
│   ├─ gui_ctk.py       # CustomTkinter 现代 GUI
│   └─ tests/           # 沙箱测试（toml 合并 / 多 provider / 自定义路由 23 项）
├─ release/             # 分发产物（.exe + 使用说明.txt）
├─ build.ps1            # 一键打包
├─ requirements.txt
├─ LICENSE              # MIT
├─ NOTICE               # 第三方代码归属
└─ README.md
```

---

## 数据存哪

| 文件 | 内容 |
|---|---|
| `~/.cc-switch/switcher-keys.json` | 内置 provider 的 API Key（按厂商分字段） |
| `~/.cc-switch/switcher-custom-providers.json` | 自定义 provider 条目（含 Key/URL/模型 ID） |
| `~/.cc-switch/stepfun-codex-adapter-config.json` | 翻译官当前激活配置 |
| `~/.codex/config.toml` | Codex 主配置（被字段级修改） |
| `~/.codex/config.toml.openai-backup` | 切到任意非 OpenAI 模式之前的完整备份，用于回滚 |

---

## 已知限制 / 边界

- Kimi 内置的 4 个模型尚未在所有真实环境穷举测试，如果遇到 401/404 请优先检查 Base URL 在 [platform.kimi.com](https://platform.kimi.com) 文档里的最新值
- 自定义提供商功能假设上游是 **OpenAI Chat Completions 兼容**协议（绝大多数国产/海外模型都是）
- 翻译官只在 `127.0.0.1:18667` 监听，外网访问不到
- 同一时刻只能挂一家上游（这是 Codex 的限制，不是我们的）

---

## 致谢

本项目的核心翻译模块 [`src/adapter.py`](src/adapter.py) 提取自 [LearnPrompt/stepfun-codex-adapter](https://github.com/LearnPrompt/stepfun-codex-adapter)（MIT 协议），向原作者致谢。详见 [NOTICE](NOTICE)。

---

## License

[MIT](LICENSE) © 2026 zhiliang
