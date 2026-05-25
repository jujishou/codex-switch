"""沙箱测试 v3：验证自定义提供商机制（添加/删除/路由/写入翻译官配置）。"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core

REAL_CONFIG = Path.home() / ".codex" / "config.toml"

tmp = Path(tempfile.mkdtemp(prefix="cdss-custom-test-"))
print(f"沙箱: {tmp}")

sandbox_codex = tmp / ".codex"
sandbox_cc = tmp / ".cc-switch"
sandbox_codex.mkdir()
sandbox_cc.mkdir()
sandbox_config = sandbox_codex / "config.toml"
shutil.copy2(REAL_CONFIG, sandbox_config)

core.CODEX_DIR = sandbox_codex
core.CC_SWITCH_DIR = sandbox_cc
core.CONFIG_TOML = sandbox_config
core.BACKUP_TOML = sandbox_codex / "config.toml.openai-backup"
core.ADAPTER_JSON = sandbox_cc / "stepfun-codex-adapter-config.json"
core.KEYS_JSON = sandbox_cc / "switcher-keys.json"
core.CUSTOM_JSON = sandbox_cc / "switcher-custom-providers.json"

results = []
def check(name, ok):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


print("\n=== 1. 添加自定义条目 ===")
check("初始 load_custom 为空", core.load_custom() == [])
core.add_custom("智谱", "glm-4-plus",
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "https://open.bigmodel.cn", "sk-zhipu-FAKE")
core.add_custom("通义", "qwen-max",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                "", "sk-qwen-FAKE")
items = core.load_custom()
check("添加 2 条", len(items) == 2)
check("第 0 条 label 正确", items[0]["label"] == "智谱")
check("第 1 条 upstream 正确", items[1]["upstream"].startswith("https://dashscope"))


print("\n=== 2. flat_models 合并内置 + 自定义 ===")
flat = core.flat_models()
builtin_count = sum(len(p["models"]) for p in core.PROVIDERS.values())
check(f"总数 = 内置 {builtin_count} + 自定义 2", len(flat) == builtin_count + 2)
custom_labels = [lab for lab, _, rt in flat if rt.startswith("custom:")]
check("自定义有特殊标记 ✦", all("✦" in lab for lab in custom_labels))
check("自定义 route_type 是 custom:0 和 custom:1",
      [rt for _, _, rt in flat if rt.startswith("custom:")] == ["custom:0", "custom:1"])


print("\n=== 3. resolve_route 内置 vs 自定义 ===")
core.save_key("deepseek", "sk-deepseek-XX")
r1 = core.resolve_route("deepseek", "deepseek-v4-pro")
check("内置 deepseek upstream 正确",
      r1["upstream"] == "https://api.deepseek.com/chat/completions")
check("内置 deepseek api_key 来自 keys.json", r1["api_key"] == "sk-deepseek-XX")
r2 = core.resolve_route("custom:0", "glm-4-plus")
check("自定义 0 upstream 正确",
      r2["upstream"].startswith("https://open.bigmodel.cn"))
check("自定义 0 api_key 自带", r2["api_key"] == "sk-zhipu-FAKE")
r3 = core.resolve_route("custom:1", "qwen-max")
check("自定义 1 api_key 自带", r3["api_key"] == "sk-qwen-FAKE")


print("\n=== 4. write_adapter_json 走自定义路由 ===")
core.write_adapter_json("glm-4-plus", "custom:0")
ad = json.loads(core.ADAPTER_JSON.read_text("utf-8"))
check("adapter.json model = glm-4-plus", ad["model"] == "glm-4-plus")
check("adapter.json upstream = 智谱 URL",
      ad["upstream"] == "https://open.bigmodel.cn/api/paas/v4/chat/completions")
check("adapter.json api_key = 智谱 key", ad["api_key"] == "sk-zhipu-FAKE")

core.write_adapter_json("qwen-max", "custom:1")
ad = json.loads(core.ADAPTER_JSON.read_text("utf-8"))
check("切到通义后 api_key 隔离", ad["api_key"] == "sk-qwen-FAKE")
check("切到通义后 upstream 隔离", ad["upstream"].startswith("https://dashscope"))


print("\n=== 5. update_custom_key 局部更新 ===")
core.update_custom_key(0, "sk-zhipu-NEW")
check("智谱 key 已更新", core.load_custom()[0]["api_key"] == "sk-zhipu-NEW")
check("通义 key 不受影响", core.load_custom()[1]["api_key"] == "sk-qwen-FAKE")


print("\n=== 6. remove_custom + 索引重排 ===")
core.remove_custom(0)
items = core.load_custom()
check("删后只剩 1 条", len(items) == 1)
check("剩下的是通义（前移）", items[0]["label"] == "通义")
# 注意：旧的 custom:1 现在变成了 custom:0
r = core.resolve_route("custom:0", "qwen-max")
check("custom:0 现在指向通义", r["api_key"] == "sk-qwen-FAKE")


print("\n=== 7. 缺字段防御 ===")
core.add_custom("不完整", "some-model", "", "", "sk-x")  # upstream 空
try:
    core.write_adapter_json("some-model", "custom:1")
    check("空 upstream 应抛错（结果未抛）", False)
except ValueError:
    check("空 upstream 正确抛错", True)


print("\n" + "=" * 40)
total = len(results)
passed = sum(1 for _, ok in results if ok)
print(f"{passed}/{total} 通过")
if passed != total:
    print("FAILED:")
    for n, ok in results:
        if not ok:
            print(f"  - {n}")
else:
    print("ALL PASS")

shutil.rmtree(tmp, ignore_errors=True)
