import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


APP_TITLE = "潜在客户邮箱自动化工具"
REQUIRED_IMPORTS = {
    "requests": "requests",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "openai": "openai",
    "openpyxl": "openpyxl",
}


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def check_dependencies() -> list[str]:
    missing = []
    for import_name, package_name in REQUIRED_IMPORTS.items():
        try:
            __import__(import_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    return missing


def read_env_file() -> dict:
    env_path = get_app_dir() / ".env"
    values = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_env_values(updates: dict) -> None:
    env_path = get_app_dir() / ".env"
    current = read_env_file()
    current.update({key: value for key, value in updates.items() if value is not None})

    ordered_keys = [
        "SERPAPI_KEY",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
    ]

    lines = []
    written = set()
    for key in ordered_keys:
        if key in current:
            lines.append(f"{key}={current[key]}")
            written.add(key)
            if key == "SERPAPI_KEY":
                lines.append("")
            if key == "LLM_MODEL":
                lines.append("")

    for key in sorted(set(current) - written):
        lines.append(f"{key}={current[key]}")

    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    for key, value in updates.items():
        if value is not None:
            os.environ[key] = value


class LeadGenerationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(980, 680)

        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.is_running = False

        self.configure(bg="#f5f7fb")
        self._build_style()
        self._build_layout()
        self._load_initial_values()
        self._refresh_table()
        self.after(150, self._drain_log_queue)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#f5f7fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f5f7fb", foreground="#172033", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background="#ffffff", foreground="#172033", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background="#f5f7fb", foreground="#172033", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Muted.TLabel", background="#f5f7fb", foreground="#667085", font=("Microsoft YaHei UI", 9))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#172033", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 7))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8))
        style.configure("TEntry", fieldbackground="#ffffff", padding=6)
        style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=28)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Horizontal.TProgressbar", troughcolor="#e8edf5", background="#2864d9")

    def _build_layout(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="输入 API Key 和采集条件，程序会搜索候选官网、抓取页面、交给 LLM 判断，并导出高质量 Excel。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        body = ttk.Frame(root)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=0, minsize=380)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_settings(left)
        self._build_results(right)

    def _build_settings(self, parent):
        ttk.Label(parent, text="配置", style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(parent, text="API Key 会保存到本地 .env 文件。", style="Card.TLabel").pack(anchor=tk.W, pady=(2, 12))

        self.serpapi_key = self._entry(parent, "SerpAPI Key", show="*")
        self.llm_api_key = self._entry(parent, "LLM API Key", show="*")
        self.llm_base_url = self._entry(parent, "LLM Base URL")
        self.llm_model = self._entry(parent, "LLM 模型")

        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="采集任务", style="CardTitle.TLabel").pack(anchor=tk.W)

        self.keyword = self._entry(parent, "产品/行业关键词", placeholder="例如：medical device")
        self.country = self._entry(parent, "国家/地区，仅用于记录和导出", placeholder="例如：Korea，可留空")
        self.limit = self._entry(parent, "目标有效邮箱数量", placeholder="例如：5")

        self.progress = ttk.Progressbar(parent, orient=tk.HORIZONTAL, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(14, 8))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(parent, textvariable=self.status_var, style="Card.TLabel").pack(anchor=tk.W)

        actions = ttk.Frame(parent, style="Card.TFrame")
        actions.pack(fill=tk.X, pady=(16, 0))
        self.start_button = ttk.Button(actions, text="开始采集", style="Primary.TButton", command=self.start_collect)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(actions, text="导出 Excel", command=self.export_excel).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Button(parent, text="刷新结果表", command=self._refresh_table).pack(fill=tk.X, pady=(10, 0))

    def _build_results(self, parent):
        top = ttk.Frame(parent, style="Card.TFrame", padding=12)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="运行日志", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="清空日志", command=self._clear_logs).grid(row=0, column=1, sticky="e")

        self.log_text = tk.Text(
            top,
            height=10,
            wrap=tk.WORD,
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            padx=12,
            pady=10,
            font=("Consolas", 10),
        )
        self.log_text.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        table_card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        table_card.grid(row=1, column=0, sticky="nsew")
        table_card.rowconfigure(1, weight=1)
        table_card.columnconfigure(0, weight=1)
        ttk.Label(table_card, text="数据库中的潜在客户", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")

        columns = ("id", "name", "website", "country", "industry", "status", "confidence", "email")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", height=12)
        headings = {
            "id": "ID",
            "name": "公司名称",
            "website": "官网",
            "country": "国家/地区",
            "industry": "行业",
            "status": "状态",
            "confidence": "置信度",
            "email": "邮箱",
        }
        widths = {
            "id": 50,
            "name": 180,
            "website": 220,
            "country": 90,
            "industry": 120,
            "status": 110,
            "confidence": 80,
            "email": 180,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor=tk.W)

        yscroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_card, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        yscroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))
        xscroll.grid(row=2, column=0, sticky="ew")

    def _entry(self, parent, label, show=None, placeholder=""):
        ttk.Label(parent, text=label, style="Card.TLabel").pack(anchor=tk.W, pady=(10, 4))
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, show=show)
        entry.pack(fill=tk.X)
        if placeholder:
            entry.insert(0, placeholder)
            entry.configure(foreground="#98a2b3")

            def on_focus_in(_event):
                if entry.get() == placeholder:
                    entry.delete(0, tk.END)
                    entry.configure(foreground="#172033")

            def on_focus_out(_event):
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.configure(foreground="#98a2b3")

            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)
        return entry

    def _load_initial_values(self):
        values = read_env_file()
        self._set_entry(self.serpapi_key, values.get("SERPAPI_KEY", ""))
        self._set_entry(self.llm_api_key, values.get("LLM_API_KEY", ""))
        self._set_entry(self.llm_base_url, values.get("LLM_BASE_URL", "https://api.deepseek.com"))
        self._set_entry(self.llm_model, values.get("LLM_MODEL", "deepseek-chat"))
        self._set_entry(self.limit, "5")

    def _set_entry(self, entry, value):
        entry.delete(0, tk.END)
        entry.configure(foreground="#172033")
        entry.insert(0, value)

    def _entry_value(self, entry, placeholders=()):
        value = entry.get().strip()
        return "" if value in placeholders else value

    def _save_api_settings(self):
        from config import load_config

        serpapi_key = self._entry_value(self.serpapi_key)
        llm_api_key = self._entry_value(self.llm_api_key)
        llm_base_url = self._entry_value(self.llm_base_url) or "https://api.deepseek.com"
        llm_model = self._entry_value(self.llm_model) or "deepseek-chat"

        if not serpapi_key or serpapi_key == "xxx":
            raise ValueError("请先输入 SerpAPI Key。")
        if not llm_api_key or llm_api_key == "xxx":
            raise ValueError("请先输入 LLM API Key。")

        save_env_values(
            {
                "SERPAPI_KEY": serpapi_key,
                "LLM_API_KEY": llm_api_key,
                "LLM_BASE_URL": llm_base_url,
                "LLM_MODEL": llm_model,
            }
        )
        load_config()

    def start_collect(self):
        if self.is_running:
            messagebox.showinfo(APP_TITLE, "采集任务正在运行中。")
            return

        keyword = self._entry_value(self.keyword, ("例如：medical device",))
        country = self._entry_value(self.country, ("例如：Korea，可留空",))
        limit_text = self._entry_value(self.limit, ("例如：5",))

        if not keyword:
            messagebox.showwarning(APP_TITLE, "请输入产品/行业关键词。")
            return
        try:
            limit = int(limit_text or "5")
        except ValueError:
            messagebox.showwarning(APP_TITLE, "目标有效邮箱数量必须是数字。")
            return
        if limit <= 0:
            messagebox.showwarning(APP_TITLE, "目标有效邮箱数量必须大于 0。")
            return

        try:
            self._save_api_settings()
        except Exception as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return

        self.is_running = True
        self.start_button.configure(state=tk.DISABLED)
        self.progress.configure(value=0, maximum=100)
        self.status_var.set("正在运行")
        self._log("已保存 API 配置，开始采集任务。")

        self.worker_thread = threading.Thread(
            target=self._collect_worker,
            args=(keyword, country, limit),
            daemon=True,
        )
        self.worker_thread.start()

    def _collect_worker(self, keyword, country, limit):
        from crawler import crawl_candidate
        from database import init_database, insert_company, insert_contact, insert_rejected_result
        from exporter import export_to_excel
        from llm_analyzer import analyze_candidate_with_llm
        from search import search_candidates

        counters = {"skipped": 0, "rejected": 0, "contact_found": 0, "no_contact": 0}
        try:
            init_database()
            self._log(f"[1/4] 正在搜索候选网站：{keyword}")
            candidates = search_candidates(keyword, limit * 3)
            total = len(candidates)
            self._log(f"找到 {total} 个候选网址。")

            for index, candidate in enumerate(candidates, start=1):
                if counters["contact_found"] >= limit:
                    break

                self._set_progress(index, max(total, 1), f"正在处理 {index}/{total}")
                self._log(f"[{index}/{total}] 正在抓取：{candidate['url']}")

                try:
                    crawl_result = crawl_candidate(candidate["url"])
                except Exception as exc:
                    counters["skipped"] += 1
                    self._log(f"  已跳过：抓取失败：{exc}")
                    continue

                self._log("  正在交给 LLM 判断官网真实性和邮箱质量...")
                try:
                    analysis = analyze_candidate_with_llm(keyword, candidate, crawl_result)
                except Exception as exc:
                    counters["skipped"] += 1
                    self._log(f"  已跳过：LLM 分析失败：{exc}")
                    continue

                if not analysis.get("is_target_company"):
                    counters["rejected"] += 1
                    reason = analysis.get("reason", "LLM 判断不是目标公司官网")
                    insert_rejected_result(
                        candidate.get("title", ""),
                        candidate.get("url", ""),
                        candidate.get("domain", ""),
                        reason,
                    )
                    self._log(f"  已拒绝：{reason}")
                    continue

                best_email = analysis.get("best_email", "")
                status = "contact_found" if best_email else "no_contact"
                company_id = insert_company(
                    analysis.get("company_name") or candidate.get("domain", "Unknown"),
                    analysis.get("website") or crawl_result.get("final_url") or candidate.get("url"),
                    country,
                    analysis.get("industry") or keyword,
                    status,
                    analysis.get("confidence", 0.0),
                    analysis.get("reason", ""),
                )

                if best_email:
                    insert_contact(
                        company_id,
                        best_email,
                        analysis.get("email_type", "unknown"),
                        crawl_result.get("final_url") or candidate.get("url"),
                    )
                    counters["contact_found"] += 1
                    self._log(f"  已保存有效联系人：{analysis.get('company_name')} | {best_email}")
                else:
                    counters["no_contact"] += 1
                    self._log(f"  已保存公司，但没有合适邮箱：{analysis.get('company_name')}")

            output_path = export_to_excel()
            self._log(
                "处理完成。"
                f" 找到邮箱={counters['contact_found']}，"
                f"无合适邮箱={counters['no_contact']}，"
                f"已拒绝={counters['rejected']}，"
                f"已跳过={counters['skipped']}"
            )
            self._log(f"Excel 已导出：{output_path}")
            self.log_queue.put(("done", output_path))
        except Exception as exc:
            self._log(f"任务失败：{exc}")
            self.log_queue.put(("failed", str(exc)))

    def export_excel(self):
        from database import init_database
        from exporter import export_to_excel

        try:
            init_database()
            output_path = export_to_excel()
            self._refresh_table()
            messagebox.showinfo(APP_TITLE, f"Excel 已导出：\n{output_path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：{exc}")

    def _refresh_table(self):
        from database import get_all_companies, get_contacts_by_company, init_database

        try:
            init_database()
            for item in self.tree.get_children():
                self.tree.delete(item)

            for company in get_all_companies():
                contacts = get_contacts_by_company(company["id"])
                email = contacts[0]["email"] if contacts else ""
                confidence = company["confidence"]
                if confidence is None:
                    confidence_text = ""
                else:
                    confidence_text = f"{float(confidence):.2f}"
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        company["id"],
                        company["company_name"],
                        company["website"],
                        company["country"],
                        company["industry"],
                        company["status"],
                        confidence_text,
                        email,
                    ),
                )
        except Exception as exc:
            self._log(f"刷新结果表失败：{exc}")

    def _log(self, text):
        self.log_queue.put(("log", text))

    def _set_progress(self, current, total, status):
        percent = 0 if total <= 0 else int(current / total * 100)
        self.log_queue.put(("progress", percent, status))

    def _drain_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log_text.insert(tk.END, item[1] + "\n")
                    self.log_text.see(tk.END)
                elif kind == "progress":
                    self.progress.configure(value=item[1])
                    self.status_var.set(item[2])
                elif kind == "done":
                    self.progress.configure(value=100)
                    self.status_var.set("完成")
                    self.is_running = False
                    self.start_button.configure(state=tk.NORMAL)
                    self._refresh_table()
                    messagebox.showinfo(APP_TITLE, f"采集完成，Excel 已导出：\n{item[1]}")
                elif kind == "failed":
                    self.status_var.set("失败")
                    self.is_running = False
                    self.start_button.configure(state=tk.NORMAL)
                    messagebox.showerror(APP_TITLE, f"任务失败：{item[1]}")
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

    def _clear_logs(self):
        self.log_text.delete("1.0", tk.END)


def main():
    missing = check_dependencies()
    if missing:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_TITLE,
            "当前 Python 环境缺少依赖：\n\n"
            + "\n".join(f"- {name}" for name in missing)
            + "\n\n请在项目目录运行：\n"
            + "pip install -r requirements.txt\n\n"
            + "如果使用 PyCharm，请确认安装到正在运行 gui.py 的同一个解释器里。",
        )
        root.destroy()
        return

    app = LeadGenerationGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
