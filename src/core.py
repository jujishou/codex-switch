"""核心逻辑：配置管理 + 翻译官启停 + 多 provider 路由。GUI 调用本模块。

加新 provider 只需要在 PROVIDERS 字典里加一行；其它代码不用动。
"""
import json
import os
import shutil
import socket
import threading
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import tomlkit

import adapter

HOME = Path(os.path.expanduser("~"))
CC_SWITCH_DIR = HOME / ".cc-switch"
CODEX_DIR = HOME / ".codex"
CONFIG_TOML = CODEX_DIR / "config.toml"
BACKUP_TOML = CODEX_DIR / "config.toml.openai-backup"
ADAPTER_JSON = CC_SWITCH_DIR / "stepfun-codex-adapter-config.json"
KEYS_JSON = CC_SWITCH_DIR / "switcher-keys.json"
CUSTOM_JSON = CC_SWITCH_DIR / "switcher-custom-providers.json"

ADAPTER_HOST = "127.0.0.1"
ADAPTER_PORT = 18667
HEALTH_URL = f"http://{ADAPTER_HOST}:{ADAPTER_PORT}/health"

# ---------- Provider 注册表（未来加新家在这里加一行） ----------

PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "upstream": "https://api.deepseek.com/chat/completions",
        "key_url": "https://platform.deepseek.com",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
    },
    "kimi": {
        "label": "Kimi",
        "upstream": "https://api.moonshot.cn/v1/chat/completions",
        "key_url": "https://platform.kimi.com",
        "models": [
            "kimi-k2-0711-preview",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
    },
}

# ---------- 自定义提供商预设模板（GUI 弹窗里给用户挑） ----------
# 不直接出现在主下拉里；用户点"添加自定义"选模板后，base_url 自动填充。
PRESETS = [
    {"label": "智谱", "model": "glm-4-plus",
     "upstream": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
     "key_url": "https://open.bigmodel.cn"},
    {"label": "智谱", "model": "glm-4-air",
     "upstream": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
     "key_url": "https://open.bigmodel.cn"},
    {"label": "通义", "model": "qwen-max",
     "upstream": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
     "key_url": "https://dashscope.console.aliyun.com"},
    {"label": "通义", "model": "qwen-plus",
     "upstream": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
     "key_url": "https://dashscope.console.aliyun.com"},
    {"label": "零一", "model": "yi-large",
     "upstream": "https://api.lingyiwanwu.com/v1/chat/completions",
     "key_url": "https://platform.lingyiwanwu.com"},
    {"label": "豆包", "model": "doubao-1-5-pro-32k",
     "upstream": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
     "key_url": "https://console.volcengine.com"},
    {"label": "Groq", "model": "llama-3.3-70b-versatile",
     "upstream": "https://api.groq.com/openai/v1/chat/completions",
     "key_url": "https://console.groq.com"},
    {"label": "Mistral", "model": "mistral-large-latest",
     "upstream": "https://api.mistral.ai/v1/chat/completions",
     "key_url": "https://console.mistral.ai"},
    {"label": "OpenRouter", "model": "anthropic/claude-3.5-sonnet",
     "upstream": "https://openrouter.ai/api/v1/chat/completions",
     "key_url": "https://openrouter.ai"},
    {"label": "自定义", "model": "",
     "upstream": "", "key_url": ""},
]


# ---------- 自定义提供商持久化 ----------

def load_custom() -> list[dict]:
    if not CUSTOM_JSON.exists():
        return []
    try:
        data = json.loads(CUSTOM_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_custom_list(items: list[dict]):
    ensure_dirs()
    CUSTOM_JSON.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_custom(label: str, model: str, upstream: str, key_url: str, api_key: str):
    items = load_custom()
    items.append({
        "label": label.strip(),
        "model": model.strip(),
        "upstream": upstream.strip(),
        "key_url": key_url.strip(),
        "api_key": api_key.strip(),
    })
    save_custom_list(items)


def remove_custom(index: int):
    items = load_custom()
    if 0 <= index < len(items):
        items.pop(index)
        save_custom_list(items)


# ---------- 统一路由 ----------

def resolve_route(route_type: str, model: str) -> dict:
    """返回 {label, upstream, key_url, api_key}。
    route_type:
      - 内置 provider id（'deepseek' / 'kimi' / ...）
      - 'custom:<index>' 指向 load_custom()[index]
    """
    if route_type.startswith("custom:"):
        idx = int(route_type[7:])
        items = load_custom()
        if idx >= len(items):
            raise ValueError(f"自定义条目 {idx} 不存在（可能被删了）")
        it = items[idx]
        return {
            "label": it["label"], "upstream": it["upstream"],
            "key_url": it.get("key_url", ""), "api_key": it.get("api_key", ""),
        }
    if route_type not in PROVIDERS:
        raise ValueError(f"未知 provider: {route_type}")
    info = PROVIDERS[route_type]
    return {
        "label": info["label"], "upstream": info["upstream"],
        "key_url": info["key_url"], "api_key": load_key(route_type),
    }


def update_custom_key(index: int, api_key: str):
    """单独更新自定义条目的 api_key（GUI 编辑用）。"""
    items = load_custom()
    if 0 <= index < len(items):
        items[index]["api_key"] = api_key.strip()
        save_custom_list(items)


def flat_models() -> list[tuple[str, str, str]]:
    """返回 (display_label, model_id, route_type) 列表，给下拉框用。
    route_type 是 'deepseek'/'kimi'/.../'custom:<idx>'。
    """
    out = []
    for pid, info in PROVIDERS.items():
        for m in info["models"]:
            out.append((f"{info['label']} · {m}", m, pid))
    for idx, it in enumerate(load_custom()):
        label = f"{it['label']} · {it['model']} ✦"
        out.append((label, it["model"], f"custom:{idx}"))
    return out


def model_to_provider(model: str) -> str | None:
    for pid, info in PROVIDERS.items():
        if model in info["models"]:
            return pid
    return None


def provider_info(pid: str) -> dict:
    return PROVIDERS[pid]


# ---------- TOML 字段（与 provider 无关） ----------

CODEX_TOML_FIELDS = {
    "model_provider": "stepfun_codex_adapter",
    "model_reasoning_effort": "high",
    "disable_response_storage": True,
}
PROVIDER_BLOCK = {
    "name": "StepFun Codex Adapter",
    "base_url": f"http://{ADAPTER_HOST}:{ADAPTER_PORT}/v1",
    "wire_api": "responses",
    "requires_openai_auth": False,
    "request_max_retries": 2,
    "stream_max_retries": 2,
    "stream_idle_timeout_ms": 300000,
}


# ---------- 状态检测 ----------

def adapter_running() -> bool:
    try:
        with socket.create_connection((ADAPTER_HOST, ADAPTER_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def adapter_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def codex_in_adapter_mode() -> bool:
    """是否已切到翻译官（任何 provider 都算）。"""
    if not CONFIG_TOML.exists():
        return False
    try:
        doc = tomlkit.parse(CONFIG_TOML.read_text(encoding="utf-8"))
    except Exception:
        return False
    return doc.get("model_provider") == "stepfun_codex_adapter"


def current_model() -> str | None:
    if not CONFIG_TOML.exists():
        return None
    try:
        doc = tomlkit.parse(CONFIG_TOML.read_text(encoding="utf-8"))
    except Exception:
        return None
    m = doc.get("model")
    return str(m) if m else None


# ---------- Key 多 provider 存取 ----------

def ensure_dirs():
    CC_SWITCH_DIR.mkdir(parents=True, exist_ok=True)
    CODEX_DIR.mkdir(parents=True, exist_ok=True)


def _load_keys_dict() -> dict:
    if KEYS_JSON.exists():
        try:
            return json.loads(KEYS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 兼容旧版：从 adapter.json 迁移一次 DeepSeek key
    if ADAPTER_JSON.exists():
        try:
            old = json.loads(ADAPTER_JSON.read_text(encoding="utf-8"))
            k = old.get("api_key")
            if k:
                return {"deepseek": k}
        except Exception:
            pass
    return {}


def load_key(provider: str) -> str:
    return _load_keys_dict().get(provider, "")


def save_key(provider: str, key: str):
    ensure_dirs()
    d = _load_keys_dict()
    d[provider] = key
    KEYS_JSON.write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- 翻译官 + Codex 配置写入 ----------

def write_adapter_json(model: str, route_type: str):
    """根据 route_type 写翻译官配置。支持内置和 custom:<idx>。"""
    ensure_dirs()
    route = resolve_route(route_type, model)
    if not route["api_key"]:
        raise ValueError(f"{route['label']} 的 API Key 未设置")
    if not route["upstream"]:
        raise ValueError(f"{route['label']} 的 Base URL 未设置")
    payload = {
        "subscription": "normal",
        "model": model,
        "upstream": route["upstream"],
        "api_key": route["api_key"],
    }
    ADAPTER_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def backup_config_toml_if_needed() -> bool:
    if not CONFIG_TOML.exists():
        return False
    if BACKUP_TOML.exists():
        return False
    shutil.copy2(CONFIG_TOML, BACKUP_TOML)
    return True


def apply_codex_config(model: str):
    """字段级合并，不冲掉用户其他配置。"""
    ensure_dirs()
    if CONFIG_TOML.exists():
        doc = tomlkit.parse(CONFIG_TOML.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    doc["model"] = model
    for k, v in CODEX_TOML_FIELDS.items():
        doc[k] = v

    if "model_providers" not in doc:
        doc["model_providers"] = tomlkit.table()
    providers = doc["model_providers"]
    if "stepfun_codex_adapter" not in providers:
        providers["stepfun_codex_adapter"] = tomlkit.table()
    block = providers["stepfun_codex_adapter"]
    for k, v in PROVIDER_BLOCK.items():
        block[k] = v
    # 动态 name：让 Codex 输入框右下角显示当前选中的模型
    block["name"] = model

    CONFIG_TOML.write_text(tomlkit.dumps(doc), encoding="utf-8")


def restore_openai_config() -> str:
    if not BACKUP_TOML.exists():
        return "未发现备份文件，跳过还原（你的 Codex 配置本来就没被改过）。"
    shutil.copy2(BACKUP_TOML, CONFIG_TOML)
    return f"已从 {BACKUP_TOML.name} 还原 config.toml。"


# ---------- 翻译官启停（同进程子线程） ----------

class AdapterRunner:
    def __init__(self, log_fn=None):
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.log = log_fn or (lambda msg: None)

    def start(self) -> bool:
        if self.thread and self.thread.is_alive():
            self.log("翻译官已经在跑了。")
            return True
        try:
            self.httpd = ThreadingHTTPServer(
                (adapter.HOST, adapter.PORT), adapter.Handler
            )
        except OSError as e:
            self.log(f"端口 {adapter.PORT} 占用或权限不足：{e}")
            return False
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="adapter-server",
            daemon=True,
        )
        self.thread.start()
        for _ in range(20):
            if adapter_running():
                self.log(f"翻译官已启动：http://{adapter.HOST}:{adapter.PORT}")
                return True
            time.sleep(0.05)
        self.log("翻译官启动超时。")
        return False

    def stop(self):
        if not self.httpd:
            return
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception as e:
            self.log(f"停翻译官出错（忽略）：{e}")
        self.httpd = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        self.log("翻译官已停止。")
