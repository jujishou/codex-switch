"""Codex 模型切换器 — 现代化 GUI（CustomTkinter）"""
import platform
import queue
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

import core

APP_TITLE = "codex-switch"

# 跨平台等宽字体:mac → Menlo, Windows → Consolas, Linux → Monospace
_SYSTEM = platform.system()
MONO_FONT = "Menlo" if _SYSTEM == "Darwin" else ("Consolas" if _SYSTEM == "Windows" else "Monospace")

ctk.set_appearance_mode("System")  # System / Light / Dark
ctk.set_default_color_theme("blue")

# 颜色常量
ACCENT = "#2c7be5"
ACCENT_HOVER = "#1a5dc9"
DANGER = "#e55353"
DANGER_HOVER = "#c43838"
MUTED = ("#666666", "#aaaaaa")  # (light_mode_color, dark_mode_color)
LINK = ("#2c7be5", "#5a9eff")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x720")  # 默认展开日志
        self.minsize(560, 520)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.runner = core.AdapterRunner(log_fn=self._enqueue_log)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.show_key_var = ctk.BooleanVar(value=False)
        self.log_expanded = True  # 默认日志展开
        self._busy = False  # 切换中,锁主按钮防重入

        self.flat: list[tuple[str, str, str]] = []
        self.label_to_meta: dict[str, tuple[str, str]] = {}
        self.labels: list[str] = []

        self.model_label_var = ctk.StringVar()
        self.key_var = ctk.StringVar()
        self._current_route: str = ""

        self._build_ui()
        self._reload_models(initial=True)
        self._pump_log()
        self._refresh_status()

    # ---------- UI ----------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        # row 6 = log_card 才有 weight,而且只在展开时设

        # ===== row 0: 顶部标题 + 主题切换 =====
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="codex-switch",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.theme_seg = ctk.CTkSegmentedButton(
            top, values=["浅色", "深色"], width=120,
            command=self._on_theme_change,
        )
        self.theme_seg.set("浅色" if ctk.get_appearance_mode() == "Light" else "深色")
        self.theme_seg.grid(row=0, column=1, sticky="e")

        # ===== row 1: 状态卡(紧凑一行) =====
        status = ctk.CTkFrame(self, corner_radius=10)
        status.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        status.grid_columnconfigure(2, weight=1)
        self.adapter_dot = ctk.CTkLabel(
            status, text="●", font=ctk.CTkFont(size=20),
            text_color="#999999", width=24,
        )
        self.adapter_dot.grid(row=0, column=0, padx=(14, 4), pady=12)
        self.adapter_status_label = ctk.CTkLabel(
            status, text="未启动",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.adapter_status_label.grid(row=0, column=1, sticky="w", pady=12)
        self.codex_status_label = ctk.CTkLabel(
            status, text="Codex: ?",
            font=ctk.CTkFont(size=12), text_color=MUTED,
        )
        self.codex_status_label.grid(row=0, column=2, sticky="e", padx=(0, 14), pady=12)

        # ===== row 2: 配置卡(模型 + Key) =====
        cfg = ctk.CTkFrame(self, corner_radius=10)
        cfg.grid(row=2, column=0, sticky="ew", padx=20, pady=4)
        cfg.grid_columnconfigure(0, weight=1)

        # 模型选择行
        row_model = ctk.CTkFrame(cfg, fg_color="transparent")
        row_model.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(row_model, text="模型", width=56, anchor="w").pack(side="left")
        self.model_menu = ctk.CTkOptionMenu(
            row_model, variable=self.model_label_var, values=[],
            command=self._on_model_change, dynamic_resizing=False,
        )
        self.model_menu.pack(side="left", padx=(0, 6), fill="x", expand=True)
        ctk.CTkButton(
            row_model, text="+ 自定义", width=72, height=28,
            command=self._open_custom_dialog,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            row_model, text="管理", width=52, height=28,
            command=self._open_manage_dialog,
            fg_color="transparent", border_width=1,
            text_color=("#333", "#ccc"), hover_color=("#eee", "#333"),
        ).pack(side="left", padx=2)

        # 拿 Key 链接 (紧凑)
        self.key_url_link = ctk.CTkLabel(
            cfg, text="", text_color=LINK,
            font=ctk.CTkFont(size=11, underline=True), cursor="hand2",
        )
        self.key_url_link.pack(anchor="w", padx=(78, 14), pady=(0, 2))
        self.key_url_link.bind("<Button-1>", self._open_key_url)

        # API Key 输入行
        row_key = ctk.CTkFrame(cfg, fg_color="transparent")
        row_key.pack(fill="x", padx=14, pady=(4, 14))
        ctk.CTkLabel(row_key, text="API Key", width=56, anchor="w").pack(side="left")
        self.key_entry = ctk.CTkEntry(
            row_key, textvariable=self.key_var, show="●",
            placeholder_text="粘贴 sk-... 字符串",
        )
        self.key_entry.pack(side="left", padx=(0, 8), fill="x", expand=True)
        ctk.CTkCheckBox(
            row_key, text="显示", variable=self.show_key_var,
            command=self._toggle_key, width=20,
        ).pack(side="left")

        # ===== row 3: 主操作按钮(单按钮智能切换) =====
        self.main_btn = ctk.CTkButton(
            self, text="▶  启动",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=48, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._on_main_button,
        )
        self.main_btn.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 2))

        # (row 4 留空 — 停止按钮已经包含"切回 OpenAI"的动作,不再需要单独链接)

        # ===== row 5: 日志折叠头 =====
        self.log_header = ctk.CTkButton(
            self, text="▼  日志", anchor="w",
            font=ctk.CTkFont(size=12),
            fg_color="transparent", text_color=MUTED,
            hover_color=("#eee", "#2a2a2a"), height=28,
            command=self._toggle_log,
        )
        self.log_header.grid(row=5, column=0, sticky="ew", padx=20, pady=(2, 0))

        # ===== row 6: 日志卡 (默认展开) =====
        self.log_card = ctk.CTkFrame(self, corner_radius=10)
        self.log_card.grid_columnconfigure(0, weight=1)
        self.log_card.grid_rowconfigure(0, weight=1)
        self.log_card.grid(row=6, column=0, sticky="nsew", padx=20, pady=(4, 14))
        self.grid_rowconfigure(6, weight=1)
        self.log = ctk.CTkTextbox(
            self.log_card, wrap="word",
            font=ctk.CTkFont(family=MONO_FONT, size=11),
            state="disabled", corner_radius=6,
        )
        self.log.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self._log("准备就绪。选模型 → 输入 API Key → 点蓝色按钮。")

    def _on_theme_change(self, value: str):
        ctk.set_appearance_mode("Light" if value == "浅色" else "Dark")

    def _toggle_key(self):
        self.key_entry.configure(show="" if self.show_key_var.get() else "●")

    def _toggle_log(self):
        if self.log_expanded:
            self.log_card.grid_remove()
            self.log_header.configure(text="▶  日志")
            self.grid_rowconfigure(6, weight=0)
            self.log_expanded = False
            # 收起后窗口高度回缩
            w = self.winfo_width()
            self.geometry(f"{w}x500")
        else:
            self.log_card.grid(row=6, column=0, sticky="nsew", padx=20, pady=(4, 14))
            self.log_header.configure(text="▼  日志")
            self.grid_rowconfigure(6, weight=1)
            self.log_expanded = True
            w = self.winfo_width()
            self.geometry(f"{w}x720")

    # ---------- 模型数据 ----------

    def _reload_models(self, initial: bool = False, prefer_route: str | None = None):
        self.flat = core.flat_models()
        self.label_to_meta = {lab: (m, rt) for lab, m, rt in self.flat}
        self.labels = [lab for lab, _, _ in self.flat]
        self.model_menu.configure(values=self.labels)

        if prefer_route:
            target = next((lab for lab, _, rt in self.flat if rt == prefer_route), None)
        else:
            cur = core.current_model()
            target = next((lab for lab, m, _ in self.flat if m == cur), None)
        if not target and self.labels:
            target = self.labels[0]
        if target:
            self.model_label_var.set(target)
            self._refresh_provider_ui(initial=initial)

    def _route_of_label(self, label: str) -> str:
        return self.label_to_meta[label][1]

    def _model_of_label(self, label: str) -> str:
        return self.label_to_meta[label][0]

    def _on_model_change(self, _selected: str | None = None):
        old_key = self.key_var.get().strip()
        if old_key and self._current_route:
            self._save_current_key(old_key)
        self._refresh_provider_ui()

    def _save_current_key(self, key: str):
        if self._current_route.startswith("custom:"):
            idx = int(self._current_route[7:])
            core.update_custom_key(idx, key)
        else:
            core.save_key(self._current_route, key)

    def _refresh_provider_ui(self, initial: bool = False):
        label = self.model_label_var.get()
        if not label:
            return
        route = self._route_of_label(label)
        self._current_route = route
        try:
            info = core.resolve_route(route, self._model_of_label(label))
        except Exception as e:
            self._log(f"路由错误: {e}")
            return
        url = info["key_url"] or ""
        self.key_url_link.configure(text=f"拿 Key: {url}" if url else "")
        self.key_var.set(info["api_key"])
        if not initial:
            self._log(f"已切到 {label}。Key 已从本地加载。")
        # 主按钮文字也跟着变(显示当前选中模型)
        if hasattr(self, "main_btn"):
            self._refresh_main_button()

    def _open_key_url(self, _evt=None):
        url = self.key_url_link.cget("text")
        if url and url.startswith("http"):
            webbrowser.open(url)

    # ---------- 弹窗 ----------

    def _open_custom_dialog(self):
        CustomDialog(self, on_saved=self._on_custom_saved)

    def _on_custom_saved(self):
        n = len(core.load_custom())
        self._log(f"自定义条目已保存。下拉新增一项（共 {n} 个自定义）。")
        self._reload_models(prefer_route=f"custom:{n - 1}")

    def _open_manage_dialog(self):
        ManageDialog(self, on_changed=self._on_custom_saved)

    # ---------- 主按钮 + 切回 OpenAI 链接 ----------

    def _on_main_button(self):
        """主按钮:翻译官没跑就启动,跑了就停止。"""
        if self._busy:
            return
        if core.adapter_running():
            self._stop_adapter()
        else:
            self._start_adapter()

    def _set_busy(self, text: str):
        self._busy = True
        self.main_btn.configure(text=text, state="disabled")

    def _start_adapter(self):
        label = self.model_label_var.get()
        if not label:
            return
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning(APP_TITLE, "请先输入 API Key。")
            return
        self._save_current_key(key)
        self._set_busy("⏳  启动中…")
        # 让 UI 先刷新出 loading 状态再做真实操作
        model = self._model_of_label(label)
        route = self._route_of_label(label)
        self.after(50, lambda: self._do_start(model, route, label))

    def _do_start(self, model: str, route: str, label: str):
        try:
            core.write_adapter_json(model, route)
            self._log(f"已写入翻译官配置（{label}）。")
            if core.backup_config_toml_if_needed():
                self._log(f"已备份原 Codex 配置 → {core.BACKUP_TOML.name}")
            core.apply_codex_config(model)
            self._log("已合并配置到 config.toml。")
        except Exception as e:
            self._log(f"配置写入失败：{e}")
            messagebox.showerror(APP_TITLE, f"配置写入失败：\n{e}")
            self._busy = False
            self._refresh_status()
            return
        if not self.runner.start():
            messagebox.showerror(APP_TITLE, "翻译官启动失败，看日志。")
            self._busy = False
            self._refresh_status()
            return
        self._log("✅ 全部就绪。打开 Codex App 即可使用。")
        self._busy = False
        self._refresh_status()

    def _stop_adapter(self):
        """停止 = 停翻译官 + 从备份还原 Codex 配置(切回 OpenAI 原版)。"""
        self._set_busy("⏳  停止并切回中…")
        self.after(50, self._do_stop)

    def _do_stop(self):
        self.runner.stop()
        try:
            msg = core.restore_openai_config()
            self._log(msg)
        except Exception as e:
            self._log(f"还原 Codex 配置失败：{e}")
            messagebox.showerror(APP_TITLE, f"还原 Codex 配置失败：\n{e}")
            self._busy = False
            self._refresh_status()
            return
        self._log("✅ 已停翻译官 + 切回 OpenAI 原版。重启 Codex App 生效。")
        self._busy = False
        self._refresh_status()

    def _refresh_main_button(self):
        """根据当前 adapter / 选中的模型,刷新主按钮文字+颜色。"""
        if self._busy:
            return
        running = core.adapter_running()
        label = self.model_label_var.get()
        target = self._model_of_label(label) if label else "?"
        if running:
            # 运行中显示当前模型 + 停止动作(会切回 OpenAI)
            self.main_btn.configure(
                text=f"⏹  停止并切回 OpenAI  (当前 {target})",
                fg_color="transparent",
                border_width=2,
                border_color="#2ecc71",
                text_color="#2ecc71",
                hover_color=("#e8f5e9", "#1a3320"),
                state="normal",
            )
        else:
            self.main_btn.configure(
                text=f"▶  启动 + 切到 {target}",
                fg_color=ACCENT,
                border_width=0,
                text_color="white",
                hover_color=ACCENT_HOVER,
                state="normal",
            )

    # ---------- 状态轮询 ----------

    def _refresh_status(self):
        if self._busy:
            self.after(800, self._refresh_status)  # busy 期间快速复查 loading 是否结束
            return
        running = core.adapter_running()
        cur_model = core.current_model()
        codex_in_adapter = core.codex_in_adapter_mode()

        # 状态卡:圆点 + 翻译官状态 + Codex 模式
        if running:
            self.adapter_dot.configure(text_color="#2ecc71")
            self.adapter_status_label.configure(text="运行中")
        else:
            self.adapter_dot.configure(text_color="#999999")
            self.adapter_status_label.configure(text="未启动")
        if codex_in_adapter and cur_model:
            self.codex_status_label.configure(text=f"Codex: {cur_model}")
        elif cur_model:
            self.codex_status_label.configure(text=f"Codex: OpenAI 原版")
        else:
            self.codex_status_label.configure(text="Codex: 未初始化")

        # 主按钮
        self._refresh_main_button()

        self.after(2000, self._refresh_status)

    # ---------- 日志 ----------

    def _enqueue_log(self, msg: str):
        self.log_queue.put(msg)

    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _pump_log(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(150, self._pump_log)

    # ---------- 关闭 ----------

    def on_close(self):
        try:
            k = self.key_var.get().strip()
            if k and self._current_route:
                self._save_current_key(k)
        except Exception:
            pass
        try:
            self.runner.stop()
        except Exception:
            pass
        self.destroy()


# ====================================================================

class CustomDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_saved):
        super().__init__(parent)
        self.parent = parent
        self.on_saved = on_saved
        self.title("添加自定义模型")
        self.geometry("560x540")
        self.resizable(False, False)
        self.transient(parent)
        self.after(50, self.grab_set)  # CTkToplevel 需延迟 grab，否则报错

        self.preset_labels = [f"{p['label']} · {p['model']}" if p['model'] else p['label']
                              for p in core.PRESETS]
        self.template_var = ctk.StringVar(value=self.preset_labels[0])
        self.name_var = ctk.StringVar()
        self.model_var = ctk.StringVar()
        self.upstream_var = ctk.StringVar()
        self.key_url_var = ctk.StringVar()
        self.api_key_var = ctk.StringVar()

        self._build()
        self._on_template_change(self.preset_labels[0])

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="添加自定义模型",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            self, text="选个模板自动填字段，或选\"自定义\"全手填。",
            text_color=MUTED, font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        # 模板行
        trow = ctk.CTkFrame(self, fg_color="transparent")
        trow.grid(row=2, column=0, sticky="ew", padx=20, pady=4)
        trow.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(trow, text="模板", width=80, anchor="w").grid(row=0, column=0)
        ctk.CTkOptionMenu(
            trow, variable=self.template_var, values=self.preset_labels,
            command=self._on_template_change, dynamic_resizing=False,
        ).grid(row=0, column=1, sticky="ew")

        self._field("显示名", self.name_var, 3, "例：智谱 / 通义 / 我的代理")
        self._field("模型 ID", self.model_var, 4, "例：glm-4-plus（向 API 提交的字符串）")
        self._field("Base URL", self.upstream_var, 5, "完整端点，必须含 /chat/completions")
        self._field("Key 入口", self.key_url_var, 6, "可选，去哪个网址注册拿 Key")
        self._field("API Key", self.api_key_var, 7, "sk-... 类型", show="●")

        # 按钮
        btnf = ctk.CTkFrame(self, fg_color="transparent")
        btnf.grid(row=8, column=0, sticky="ew", padx=20, pady=(16, 16))
        btnf.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            btnf, text="取消", command=self.destroy,
            fg_color="transparent", border_width=1,
            text_color=("#333", "#ccc"), hover_color=("#eee", "#333"),
            width=100,
        ).grid(row=0, column=1, padx=4)
        ctk.CTkButton(
            btnf, text="保存", command=self._save,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, width=100,
        ).grid(row=0, column=2, padx=4)

    def _field(self, label, var, row, hint, show=None):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=20, pady=2)
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label, width=80, anchor="w").grid(row=0, column=0)
        entry = ctk.CTkEntry(f, textvariable=var, placeholder_text=hint)
        if show:
            entry.configure(show=show)
        entry.grid(row=0, column=1, sticky="ew")

    def _on_template_change(self, label: str):
        for p in core.PRESETS:
            disp = f"{p['label']} · {p['model']}" if p['model'] else p['label']
            if disp == label:
                self.name_var.set(p["label"] if p["label"] != "自定义" else "")
                self.model_var.set(p["model"])
                self.upstream_var.set(p["upstream"])
                self.key_url_var.set(p["key_url"])
                return

    def _save(self):
        name = self.name_var.get().strip()
        model = self.model_var.get().strip()
        upstream = self.upstream_var.get().strip()
        key_url = self.key_url_var.get().strip()
        api_key = self.api_key_var.get().strip()
        missing = [n for n, v in (("显示名", name), ("模型 ID", model),
                                  ("Base URL", upstream), ("API Key", api_key))
                   if not v]
        if missing:
            messagebox.showwarning("缺字段", "以下字段必填：\n  " + "\n  ".join(missing))
            return
        if not upstream.startswith(("http://", "https://")):
            messagebox.showwarning("Base URL 格式", "Base URL 必须以 http:// 或 https:// 开头")
            return
        try:
            core.add_custom(name, model, upstream, key_url, api_key)
            self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


class ManageDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_changed):
        super().__init__(parent)
        self.parent = parent
        self.on_changed = on_changed
        self.title("管理自定义模型")
        self.geometry("600x420")
        self.transient(parent)
        self.after(50, self.grab_set)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="已添加的自定义模型",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=4)
        self.list_frame.grid_columnconfigure(0, weight=1)

        btnf = ctk.CTkFrame(self, fg_color="transparent")
        btnf.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 16))
        btnf.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            btnf, text="关闭", command=self.destroy,
            fg_color="transparent", border_width=1,
            text_color=("#333", "#ccc"), hover_color=("#eee", "#333"),
            width=100,
        ).grid(row=0, column=1)

        self._reload()

    def _reload(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        items = core.load_custom()
        if not items:
            ctk.CTkLabel(
                self.list_frame, text="（还没有自定义条目）",
                text_color=MUTED,
            ).grid(row=0, column=0, pady=20)
            return
        for i, it in enumerate(items):
            row = ctk.CTkFrame(self.list_frame, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=4, padx=4)
            row.grid_columnconfigure(0, weight=1)
            txt = f"{it['label']} · {it['model']}"
            sub = it["upstream"][:60] + ("…" if len(it["upstream"]) > 60 else "")
            ctk.CTkLabel(
                row, text=txt, anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                row, text=sub, anchor="w",
                text_color=MUTED, font=ctk.CTkFont(size=11),
            ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
            ctk.CTkButton(
                row, text="删除", width=60, height=28,
                fg_color=DANGER, hover_color=DANGER_HOVER,
                command=lambda idx=i: self._delete(idx),
            ).grid(row=0, column=1, rowspan=2, padx=10, pady=8)

    def _delete(self, idx: int):
        items = core.load_custom()
        if idx >= len(items):
            return
        if not messagebox.askyesno("确认", f"删除 {items[idx]['label']} · {items[idx]['model']}？"):
            return
        core.remove_custom(idx)
        self._reload()
        self.on_changed()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
