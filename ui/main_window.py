"""
海康威视 macOS 桌面管理工具主窗口
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import Dict, List, Any, Optional

from .theme import (
    apply_theme, COLOR_BG, COLOR_CARD, COLOR_PRIMARY,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_BORDER, FONT_MAIN, FONT_BOLD, FONT_TITLE
)
from .dialogs import SingleModifyDialog, BatchModifyDialog, PasswordRecoveryDialog
from ..core.scanner import DeviceScanner

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hikvision Device Manager (海康威视设备管理工具 for macOS)")
        self.geometry("1100x680")
        self.minsize(960, 560)

        self.scanner = DeviceScanner()
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.selected_macs = set()

        apply_theme(self)
        self._build_ui()
        self._center_window()

        # 启动时自动触发一次全网搜索
        self.after(300, self._start_search)

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # 1. 顶部控制面板
        top_card = ttk.Frame(self, padding=12)
        top_card.pack(fill="x", padx=16, pady=(16, 8))

        # 第一行: 搜索模式与输入
        search_row = ttk.Frame(top_card)
        search_row.pack(fill="x", pady=4)

        ttk.Label(search_row, text="搜索模式:", font=FONT_BOLD).pack(side="left", padx=(0, 8))

        self.search_mode_var = tk.StringVar(value="broadcast")
        rb_all = ttk.Radiobutton(
            search_row,
            text="全网搜索 (组播/广播)",
            variable=self.search_mode_var,
            value="broadcast",
            command=self._on_search_mode_changed
        )
        rb_all.pack(side="left", padx=(0, 12))

        rb_subnet = ttk.Radiobutton(
            search_row,
            text="指定特定网段 (CIDR):",
            variable=self.search_mode_var,
            value="subnet",
            command=self._on_search_mode_changed
        )
        rb_subnet.pack(side="left", padx=(0, 6))

        # 预推网段
        local_ip = self.scanner.get_local_ip()
        default_subnet = f"{local_ip.rsplit('.', 1)[0]}.0/24" if '.' in local_ip else "192.168.1.0/24"
        self.subnet_var = tk.StringVar(value=default_subnet)
        self.subnet_entry = ttk.Entry(search_row, textvariable=self.subnet_var, width=18, state="disabled")
        self.subnet_entry.pack(side="left", padx=(0, 16))

        self.search_btn = ttk.Button(search_row, text="🔍 开始搜索设备", command=self._start_search)
        self.search_btn.pack(side="left", padx=(0, 8))

        self.loading_lbl = ttk.Label(search_row, text="", foreground="#007AFF", font=FONT_MAIN)
        self.loading_lbl.pack(side="left", padx=8)

        # 第二行: 操作快捷按钮
        action_row = ttk.Frame(top_card)
        action_row.pack(fill="x", pady=(10, 0))

        self.select_all_btn = ttk.Button(action_row, text="全选 / 取消全选", command=self._toggle_select_all)
        self.select_all_btn.pack(side="left", padx=(0, 8))

        self.modify_btn = ttk.Button(action_row, text="⚙️ 修改网络参数", command=self._on_click_modify)
        self.modify_btn.pack(side="left", padx=(0, 8))

        self.recover_btn = ttk.Button(action_row, text="🔑 找回密码向导", command=self._on_click_recover)
        self.recover_btn.pack(side="left", padx=(0, 8))

        self.browser_btn = ttk.Button(action_row, text="🌐 打开 Web 登录页", command=self._open_in_browser)
        self.browser_btn.pack(side="left", padx=(0, 8))

        # 2. 中间表格展示区域
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=16, pady=4)

        columns = (
            "sel", "idx", "model", "ip", "mask", "gateway",
            "http_port", "cmd_port", "dhcp", "mac", "sn", "version"
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")

        # 定义列标题与宽度
        col_defs = [
            ("sel", "选择", 45, "center"),
            ("idx", "#", 40, "center"),
            ("model", "设备型号", 150, "w"),
            ("ip", "IPv4 地址", 130, "center"),
            ("mask", "子网掩码", 120, "center"),
            ("gateway", "默认网关", 120, "center"),
            ("http_port", "Web端口", 70, "center"),
            ("cmd_port", "SDK端口", 70, "center"),
            ("dhcp", "DHCP", 65, "center"),
            ("mac", "MAC 物理地址", 140, "center"),
            ("sn", "设备序列号", 220, "w"),
            ("version", "固件版本", 140, "w"),
        ]

        for cid, text, width, anchor in col_defs:
            self.tree.heading(cid, text=text, command=lambda c=cid: self._sort_tree(c, False))
            self.tree.column(cid, width=width, anchor=anchor)

        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 绑定事件
        self.tree.bind("<Double-1>", self._on_double_click_row)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._build_context_menu()

        # 3. 底部状态栏
        bottom_bar = ttk.Frame(self, padding=(16, 6))
        bottom_bar.pack(fill="x", side="bottom")

        self.status_local_lbl = ttk.Label(bottom_bar, text=f"本机 IP: {local_ip}", font=FONT_MAIN)
        self.status_local_lbl.pack(side="left")

        self.status_count_lbl = ttk.Label(bottom_bar, text="共发现 0 台设备 | 已选中 0 台", font=FONT_BOLD)
        self.status_count_lbl.pack(side="right")

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="修改此设备参数...", command=self._on_click_modify)
        self.context_menu.add_command(label="找回密码向导...", command=self._on_click_recover)
        self.context_menu.add_command(label="在浏览器中打开 Web 界面", command=self._open_in_browser)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制 IPv4 地址", command=self._copy_ip)
        self.context_menu.add_command(label="复制 MAC 地址", command=self._copy_mac)

        self.tree.bind("<Button-2>", self._show_context_menu)
        self.tree.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _on_search_mode_changed(self):
        if self.search_mode_var.get() == "subnet":
            self.subnet_entry.config(state="normal")
            self.subnet_entry.focus()
        else:
            self.subnet_entry.config(state="disabled")

    def _start_search(self):
        self.search_btn.config(state="disabled")
        self.loading_lbl.config(text="正在搜索局域网海康设备...")
        self.tree.delete(*self.tree.get_children())
        self.devices.clear()
        self.selected_macs.clear()
        self._update_status_counts()

        custom_subnet = None
        if self.search_mode_var.get() == "subnet":
            custom_subnet = self.subnet_var.get().strip()

        def on_found(dev):
            self.after(0, lambda d=dev: self._add_device_to_tree(d))

        def on_done(results):
            self.after(0, self._on_search_finished)

        self.scanner.search(
            custom_subnet=custom_subnet,
            timeout=3.5,
            on_device_found=on_found,
            on_finished=on_done
        )

    def _add_device_to_tree(self, dev: Dict[str, Any]):
        mac = dev['mac']
        if mac in self.devices:
            return
        self.devices[mac] = dev
        idx = len(self.devices)

        # 默认显示未勾选状态标记
        item_id = self.tree.insert("", "end", iid=mac, values=(
            "☐",
            idx,
            dev.get('model', '未知'),
            dev.get('ip', ''),
            dev.get('mask', ''),
            dev.get('gateway', ''),
            dev.get('http_port', 80),
            dev.get('cmd_port', 8000),
            "开" if dev.get('dhcp') else "关",
            mac,
            dev.get('sn', ''),
            dev.get('version', '')
        ))
        self._update_status_counts()

    def _on_search_finished(self):
        self.search_btn.config(state="normal")
        self.loading_lbl.config(text=f"搜索完成，发现 {len(self.devices)} 台设备")
        self._update_status_counts()

    def _on_tree_select(self, event):
        selected_iids = self.tree.selection()
        self.selected_macs = set(selected_iids)
        # 更新复选框文字
        for item in self.tree.get_children():
            current_vals = list(self.tree.item(item, "values"))
            current_vals[0] = "☑" if item in self.selected_macs else "☐"
            self.tree.item(item, values=current_vals)
        self._update_status_counts()

    def _toggle_select_all(self):
        all_items = self.tree.get_children()
        if len(self.selected_macs) == len(all_items):
            self.selected_macs.clear()
            self.tree.selection_set([])
        else:
            self.selected_macs = set(all_items)
            self.tree.selection_set(all_items)
        self._on_tree_select(None)

    def _update_status_counts(self):
        total = len(self.devices)
        sel = len(self.selected_macs)
        self.status_count_lbl.config(text=f"共发现 {total} 台设备 | 已选中 {sel} 台")

    def _on_double_click_row(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.devices:
            SingleModifyDialog(self, self.devices[item_id], self.scanner, self._start_search)

    def _on_click_modify(self):
        if not self.selected_macs:
            messagebox.showwarning("提示", "请先在列表中选中需要修改参数的设备！", parent=self)
            return

        if len(self.selected_macs) == 1:
            mac = next(iter(self.selected_macs))
            SingleModifyDialog(self, self.devices[mac], self.scanner, self._start_search)
        else:
            dev_list = [self.devices[m] for m in self.selected_macs]
            BatchModifyDialog(self, dev_list, self.scanner, self._start_search)

    def _on_click_recover(self):
        if not self.selected_macs:
            messagebox.showwarning("提示", "请先选中需要找回密码的设备！", parent=self)
            return
        mac = next(iter(self.selected_macs))
        PasswordRecoveryDialog(self, self.devices[mac], self.scanner)

    def _open_in_browser(self):
        if not self.selected_macs:
            messagebox.showwarning("提示", "请先选中设备！", parent=self)
            return
        mac = next(iter(self.selected_macs))
        dev = self.devices[mac]
        ip = dev.get('ip')
        port = dev.get('http_port', 80)
        url = f"http://{ip}" if port == 80 else f"http://{ip}:{port}"
        webbrowser.open(url)

    def _copy_ip(self):
        if self.selected_macs:
            mac = next(iter(self.selected_macs))
            ip = self.devices[mac].get('ip', '')
            self.clipboard_clear()
            self.clipboard_append(ip)

    def _copy_mac(self):
        if self.selected_macs:
            mac = next(iter(self.selected_macs))
            self.clipboard_clear()
            self.clipboard_append(mac)

    def _sort_tree(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        # 尝试数值转换排序
        try:
            l.sort(key=lambda t: int(t[0]), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))
