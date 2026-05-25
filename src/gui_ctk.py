"""Codex 模型切换器 — 现代化 GUI（CustomTkinter）"""
import queue
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

import core

APP_TITLE = "codex-switch"

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
        self.geometry("660x780")
        self.minsize(600, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.runner = core.AdapterRunner(log_fn=self._enqueue_log)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.show_key_var = ctk.BooleanVar(value=False)

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
        self.grid_rowconfigure(4, weight=1)  # 日志区可伸缩

        # ===== Top: title + theme toggle =====
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="codex-switch",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.theme_seg = ctk.CTkSegmentedButton(
            top, values=["浅色", "深色"], width=140,
            command=self._on_theme_change,
        )
        self.theme_seg.set("浅色" if ctk.get_appearance_mode() == "Light" else "深色")
        self.theme_seg.grid(row=0, column=1, sticky="e")

        # ===== 状态卡 =====
        status_card = self._card(row=1)
        ctk.CTkLabel(
            status_card, text="当前状态",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(12, 6))
        self.adapter_dot = ctk.CTkLabel(
            status_card, text="●", font=ctk.CTkFont(size=18),
            text_color="#999999",
        )
        self.adapter_dot.pack(side="left", padx=(16, 4), pady=(0, 14))
        self.adapter_status_label = ctk.CTkLabel(
            status_card, text="翻译官：检测中…",
            font=ctk.CTkFont(size=13),
        )
        self.adapter_status_label.pack(side="left", pady=(0, 14))
        self.codex_status_label = ctk.CTkLabel(
            status_card, text="Codex 模式：检测中…",
            font=ctk.CTkFont(size=13),
            text_color=MUTED,
        )
        self.codex_status_label.pack(side="right", padx=(0, 16), pady=(0, 14))

        # ===== 模型 + Key 卡 =====
        cfg = self._card(row=2)
        ctk.CTkLabel(
            cfg, text="模型 & API Key",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(12, 6))

        # 模型行
        row_model = ctk.CTkFrame(cfg, fg_color="transparent")
        row_model.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(row_model, text="模型", width=70, anchor="w").pack(side="left")
        self.model_menu = ctk.CTkOptionMenu(
            row_model, variable=self.model_label_var, values=[],
            command=self._on_model_change,
            width=300, dynamic_resizing=False,
        )
        self.model_menu.pack(side="left", padx=(0, 8), fill="x", expand=True)
        ctk.CTkButton(
            row_model, text="+ 自定义", width=80, height=28,
            command=self._open_custom_dialog,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            row_model, text="管理", width=60, height=28,
            command=self._open_manage_dialog,
            fg_color="transparent", border_width=1,
            text_color=("#333", "#ccc"), hover_color=("#eee", "#333"),
        ).pack(side="left", padx=2)

        # provider 提示行
        self.provider_hint = ctk.CTkLabel(
            cfg, text="", text_color=MUTED, font=ctk.CTkFont(size=12),
        )
        self.provider_hint.pack(anchor="w", padx=16, pady=(8, 0))
        self.key_url_link = ctk.CTkLabel(
            cfg, text="", text_color=LINK, font=ctk.CTkFont(size=12, underline=True),
            cursor="hand2",
        )
        self.key_url_link.pack(anchor="w", padx=16, pady=(0, 6))
        self.key_url_link.bind("<Button-1>", self._open_key_url)

        # Key 行
        row_key = ctk.CTkFrame(cfg, fg_color="transparent")
        row_key.pack(fill="x", padx=16, pady=(2, 14))
        ctk.CTkLabel(row_key, text="API Key", width=70, anchor="w").pack(side="left")
        self.key_entry = ctk.CTkEntry(
            row_key, textvariable=self.key_var, show="●",
            placeholder_text="粘贴该平台的 sk-... 字符串",
        )
        self.key_entry.pack(side="left", padx=(0, 8), fill="x", expand=True)
        ctk.CTkCheckBox(
            row_key, text="显示", variable=self.show_key_var,
            command=self._toggle_key, width=20,
        ).pack(side="left")

        # ===== 按钮卡 =====
        btn_card = ctk.CTkFrame(self, fg_color="transparent")
        btn_card.grid(row=3, column=0, sticky="ew", padx=20, pady=8)
        btn_card.grid_columnconfigure(0, weight=1)
        self.start_btn = ctk.CTkButton(
            btn_card, text="▶  启动翻译官 + 切到所选模型",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self.on_start,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.stop_btn = ctk.CTkButton(
            btn_card, text="⏸  停止翻译官 + 切回 OpenAI",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, corner_radius=10,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            command=self.on_stop,
        )
        self.stop_btn.grid(row=1, column=0, sticky="ew")

        # ===== 日志卡 =====
        log_card = self._card(row=4, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            log_card, text="日志",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))
        self.log = ctk.CTkTextbox(
            log_card, wrap="word", font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled", corner_radius=6,
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self._log("准备就绪。选模型 → 输入 API Key → 点蓝色按钮。")
        self._log("加新模型：点【+ 自定义】，选模板或手填 Base URL。")

    def _card(self, row: int, sticky: str = "ew"):
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=row, column=0, sticky=sticky, padx=20, pady=6)
        return card

    def _on_theme_change(self, value: str):
        ctk.set_appearance_mode("Light" if value == "浅色" else "Dark")

    def _toggle_key(self):
        self.key_entry.configure(show="" if self.show_key_var.get() else "●")

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
        prefix = "自定义提供商" if route.startswith("custom:") else info["label"]
        self.provider_hint.configure(text=f"当前选中 {prefix} 的模型，去这里拿 Key:")
        self.key_url_link.configure(text=info["key_url"] or "（无官网链接）")
        self.key_var.set(info["api_key"])
        if not initial:
            self._log(f"已切到 {label}。Key 已从本地加载。")

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

    # ---------- 按钮 ----------

    def on_start(self):
        label = self.model_label_var.get()
        if not label:
            return
        model = self._model_of_label(label)
        route = self._route_of_label(label)
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning(APP_TITLE, "请先输入 API Key。")
            return
        self._save_current_key(key)
        try:
            core.write_adapter_json(model, route)
            self._log(f"已写入翻译官配置（{label}）。")
            if core.backup_config_toml_if_needed():
                self._log(f"已备份原 Codex 配置 → {core.BACKUP_TOML.name}")
            core.apply_codex_config(model)
            self._log("已合并配置到 config.toml（保留你原有的项目/插件配置）。")
        except Exception as e:
            self._log(f"配置写入失败：{e}")
            messagebox.showerror(APP_TITLE, f"配置写入失败：\n{e}")
            return
        if not self.runner.start():
            messagebox.showerror(APP_TITLE, "翻译官启动失败，看日志。")
            return
        self._log("✅ 全部就绪。打开 Codex App 即可使用。")
        self._refresh_status()

    def on_stop(self):
        self.runner.stop()
        try:
            msg = core.restore_openai_config()
            self._log(msg)
        except Exception as e:
            self._log(f"还原失败：{e}")
            messagebox.showerror(APP_TITLE, f"还原失败：\n{e}")
            return
        self._log("✅ 已切回 OpenAI 原版。重启 Codex App 生效。")
        self._refresh_status()

    # ---------- 状态轮询 ----------

    def _refresh_status(self):
        running = core.adapter_running()
        cur_model = core.current_model()
        if core.codex_in_adapter_mode() and cur_model:
            mode = cur_model
        else:
            mode = f"OpenAI 原版 ({cur_model})" if cur_model else "未知"

        if running:
            self.adapter_dot.configure(text_color="#2ecc71")  # 绿
            self.adapter_status_label.configure(text="翻译官：运行中")
        else:
            self.adapter_dot.configure(text_color="#999999")
            self.adapter_status_label.configure(text="翻译官：未启动")
        self.codex_status_label.configure(text=f"Codex 模式: {mode}")
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
