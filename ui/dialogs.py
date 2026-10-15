"""
海康威视管理应用模态交互对话框
包含单机修改、批量修改、找回密码向导
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ipaddress
import datetime
from typing import Dict, List, Any, Callable
from ..core.scanner import DeviceScanner
from ..core.sadp_protocol import calculate_classic_recovery_code

class SingleModifyDialog(tk.Toplevel):
    """修改单台设备参数的对话框"""
    def __init__(self, parent, device: Dict[str, Any], scanner: DeviceScanner, on_success: Callable):
        super().__init__(parent)
        self.device = device
        self.scanner = scanner
        self.on_success = on_success
        self.title(f"修改网络参数 - {device.get('model', '设备')} ({device.get('ip')})")
        self.geometry("460x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build_ui(self):
        pad = {'padx': 16, 'pady': 6}

        # 头部提示
        header = ttk.Label(
            self,
            text=f"设备: {self.device.get('model')}  |  MAC: {self.device.get('mac')}",
            font=("-apple-system", 11, "bold")
        )
        header.pack(fill="x", padx=16, pady=(16, 8))

        form_frame = ttk.Frame(self)
        form_frame.pack(fill="both", expand=True, padx=16, pady=4)

        # 字段列表
        self.entries = {}
        fields = [
            ("IPv4 地址:", "ip", self.device.get('ip', '')),
            ("子网掩码:", "mask", self.device.get('mask', '255.255.255.0')),
            ("默认网关:", "gateway", self.device.get('gateway', '')),
            ("DNS 服务器:", "dns", self.device.get('dns', '114.114.114.114')),
            ("HTTP 端口:", "http_port", str(self.device.get('http_port', 80))),
            ("SDK 端口 (私有):", "cmd_port", str(self.device.get('cmd_port', 8000))),
            ("设备管理员密码*:", "password", "")
        ]

        for idx, (label_text, key, default_val) in enumerate(fields):
            lbl = ttk.Label(form_frame, text=label_text, width=16, anchor="w")
            lbl.grid(row=idx, column=0, sticky="w", pady=4)

            is_pwd = (key == "password")
            ent = ttk.Entry(form_frame, width=28, show="*" if is_pwd else "")
            ent.grid(row=idx, column=1, sticky="ew", pady=4)
            if default_val:
                ent.insert(0, default_val)
            self.entries[key] = ent

        pwd_hint = ttk.Label(form_frame, text="* 修改海康威视参数需输入设备当前的管理密码进行校验", foreground="#8E8E93", font=("-apple-system", 10))
        pwd_hint.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(4, 12))

        # 按钮栏
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=16, pady=16)

        cancel_btn = ttk.Button(btn_frame, text="取消", command=self.destroy)
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ttk.Button(btn_frame, text="确认保存修改", command=self._do_save)
        save_btn.pack(side="right")

    def _do_save(self):
        new_ip = self.entries['ip'].get().strip()
        new_mask = self.entries['mask'].get().strip()
        new_gw = self.entries['gateway'].get().strip()
        new_dns = self.entries['dns'].get().strip()
        pwd = self.entries['password'].get().strip()

        # 校验
        try:
            ipaddress.IPv4Address(new_ip)
            ipaddress.IPv4Address(new_mask)
            if new_gw:
                ipaddress.IPv4Address(new_gw)
        except ValueError:
            messagebox.showerror("格式错误", "请输入有效的 IPv4 地址、子网掩码或网关！", parent=self)
            return

        try:
            http_port = int(self.entries['http_port'].get().strip())
            cmd_port = int(self.entries['cmd_port'].get().strip())
            if not (1 <= http_port <= 65535 and 1 <= cmd_port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("格式错误", "端口号必须在 1-65535 范围内！", parent=self)
            return

        if not pwd:
            messagebox.showwarning("提示", "请输入设备管理密码！", parent=self)
            return

        # 执行下发
        ok, msg = self.scanner.modify_device(
            device=self.device,
            new_ip=new_ip,
            new_mask=new_mask,
            new_gateway=new_gw,
            new_dns=new_dns,
            new_http_port=http_port,
            new_cmd_port=cmd_port,
            password=pwd
        )

        if ok:
            messagebox.showinfo("成功", f"设备参数修改成功！\n新 IP: {new_ip}\n请稍后刷新列表。", parent=self)
            self.on_success()
            self.destroy()
        else:
            messagebox.showerror("失败", f"修改失败: {msg}", parent=self)


class BatchModifyDialog(tk.Toplevel):
    """批量修改设备参数对话框"""
    def __init__(self, parent, devices: List[Dict[str, Any]], scanner: DeviceScanner, on_finish: Callable):
        super().__init__(parent)
        self.devices = devices
        self.scanner = scanner
        self.on_finish = on_finish
        self.title(f"批量修改网络参数 (已选中 {len(devices)} 台设备)")
        self.geometry("520x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build_ui(self):
        info_lbl = ttk.Label(
            self,
            text=f"将对选中的 {len(self.devices)} 台设备批量分配 IP 地址及网络参数：",
            font=("-apple-system", 12, "bold")
        )
        info_lbl.pack(fill="x", padx=16, pady=(16, 8))

        form = ttk.Frame(self)
        form.pack(fill="both", expand=True, padx=16, pady=4)

        # 预设首个设备的参数
        first_dev = self.devices[0]
        self.entries = {}
        fields = [
            ("起始 IPv4 地址*:", "start_ip", first_dev.get('ip', '192.168.110.100')),
            ("统一子网掩码:", "mask", first_dev.get('mask', '255.255.255.0')),
            ("统一默认网关:", "gateway", first_dev.get('gateway', '192.168.110.1')),
            ("统一 DNS 服务器:", "dns", "114.114.114.114"),
            ("统一 HTTP 端口:", "http_port", "80"),
            ("统一 SDK 端口:", "cmd_port", "8000"),
            ("设备统一管理密码*:", "password", "")
        ]

        for idx, (label_text, key, default_val) in enumerate(fields):
            lbl = ttk.Label(form, text=label_text, width=18, anchor="w")
            lbl.grid(row=idx, column=0, sticky="w", pady=4)

            is_pwd = (key == "password")
            ent = ttk.Entry(form, width=30, show="*" if is_pwd else "")
            ent.grid(row=idx, column=1, sticky="ew", pady=4)
            if default_val:
                ent.insert(0, default_val)
            self.entries[key] = ent

        hint = ttk.Label(
            form,
            text="注：系统将以“起始 IP”为基准，依次递增为选中的设备分配连续 IP 地址。\n修改要求所有设备的管理密码一致。",
            foreground="#8E8E93",
            font=("-apple-system", 10)
        )
        hint.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 12))

        # 进度条
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=len(self.devices))
        self.progress.pack(fill="x", padx=16, pady=4)

        self.status_lbl = ttk.Label(self, text="准备就绪", foreground="#007AFF")
        self.status_lbl.pack(fill="x", padx=16, pady=2)

        # 按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=16, pady=16)

        cancel_btn = ttk.Button(btn_frame, text="取消", command=self.destroy)
        cancel_btn.pack(side="right", padx=(8, 0))

        self.submit_btn = ttk.Button(btn_frame, text="开始批量修改", command=self._do_batch_modify)
        self.submit_btn.pack(side="right")

    def _do_batch_modify(self):
        start_ip_str = self.entries['start_ip'].get().strip()
        mask = self.entries['mask'].get().strip()
        gateway = self.entries['gateway'].get().strip()
        dns = self.entries['dns'].get().strip()
        pwd = self.entries['password'].get().strip()

        try:
            curr_ip_int = int(ipaddress.IPv4Address(start_ip_str))
            ipaddress.IPv4Address(mask)
            if gateway:
                ipaddress.IPv4Address(gateway)
            http_port = int(self.entries['http_port'].get().strip())
            cmd_port = int(self.entries['cmd_port'].get().strip())
        except Exception:
            messagebox.showerror("格式错误", "请输入有效的 IP、掩码、网关与端口号！", parent=self)
            return

        if not pwd:
            messagebox.showwarning("提示", "请输入设备管理密码！", parent=self)
            return

        self.submit_btn.config(state="disabled")
        success_count = 0
        fail_list = []

        for idx, dev in enumerate(self.devices):
            allocated_ip = str(ipaddress.IPv4Address(curr_ip_int + idx))
            self.status_lbl.config(text=f"正在修改 [{idx+1}/{len(self.devices)}] {dev.get('model')} -> {allocated_ip} ...")
            self.progress['value'] = idx + 1
            self.update_idletasks()

            ok, msg = self.scanner.modify_device(
                device=dev,
                new_ip=allocated_ip,
                new_mask=mask,
                new_gateway=gateway,
                new_dns=dns,
                new_http_port=http_port,
                new_cmd_port=cmd_port,
                password=pwd
            )
            if ok:
                success_count += 1
            else:
                fail_list.append((dev.get('ip'), dev.get('mac'), msg))

        # 完成通知
        summary = f"批量修改完成！\n成功: {success_count} 台\n失败: {len(fail_list)} 台"
        if fail_list:
            summary += "\n\n失败详情:\n" + "\n".join([f"{ip} ({mac}): {err}" for ip, mac, err in fail_list[:5]])
        messagebox.showinfo("批量结果", summary, parent=self)
        self.on_finish()
        self.destroy()


class PasswordRecoveryDialog(tk.Toplevel):
    """找回密码向导对话框（支持现代特征文件重置与老设备安全码）"""
    def __init__(self, parent, device: Dict[str, Any], scanner: DeviceScanner):
        super().__init__(parent)
        self.device = device
        self.scanner = scanner
        self.title(f"找回设备密码 - {device.get('model')} ({device.get('mac')})")
        self.geometry("540x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        # Tab 1: 官方秘钥文件向导 (现代设备)
        tab_modern = ttk.Frame(notebook)
        notebook.add(tab_modern, text="现代固件（特征文件重置）")
        self._build_modern_tab(tab_modern)

        # Tab 2: 经典日安全码算号器 (老固件)
        tab_classic = ttk.Frame(notebook)
        notebook.add(tab_classic, text="老固件（日安全码快速算号）")
        self._build_classic_tab(tab_classic)

    def _build_modern_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill="both", expand=True)

        step1_lbl = ttk.Label(frame, text="步骤 1: 导出设备特征秘钥文件", font=("-apple-system", 11, "bold"))
        step1_lbl.pack(anchor="w", pady=(4, 2))

        step1_desc = ttk.Label(
            frame,
            text="点击下方按钮将该设备的 DeviceKey.xml 特征文件保存到本地，并将其发送至海康客服/官方微信助手获取解密文件。",
            wraplength=480,
            foreground="#555"
        )
        step1_desc.pack(anchor="w", pady=(0, 6))

        export_btn = ttk.Button(frame, text="导出 DeviceKey.xml 秘钥文件...", command=self._do_export_key)
        export_btn.pack(anchor="w", pady=(0, 14))

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=6)

        step2_lbl = ttk.Label(frame, text="步骤 2: 导入官方秘钥文件并设置新密码", font=("-apple-system", 11, "bold"))
        step2_lbl.pack(anchor="w", pady=(8, 4))

        file_frame = ttk.Frame(frame)
        file_frame.pack(fill="x", pady=4)

        self.key_path_var = tk.StringVar()
        key_entry = ttk.Entry(file_frame, textvariable=self.key_path_var, width=36)
        key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ttk.Button(file_frame, text="选择秘钥文件...", command=self._browse_key_file)
        browse_btn.pack(side="left")

        pwd_frame = ttk.Frame(frame)
        pwd_frame.pack(fill="x", pady=6)

        ttk.Label(pwd_frame, text="设置新密码:").pack(side="left", padx=(0, 8))
        self.new_pwd_entry = ttk.Entry(pwd_frame, show="*", width=24)
        self.new_pwd_entry.pack(side="left")

        submit_btn = ttk.Button(frame, text="提交重置密码", command=self._do_reset_modern)
        submit_btn.pack(anchor="w", pady=(12, 0))

    def _build_classic_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill="both", expand=True)

        desc = ttk.Label(
            frame,
            text="本算号器基于海康早期出厂设备的日临时恢复密钥算法，适用于 2017 年之前的老版本 IPC/NVR 固件。\n输入设备序列号及今日日期，自动生成临时安全码。",
            wraplength=480,
            foreground="#555"
        )
        desc.pack(anchor="w", pady=(4, 12))

        grid_f = ttk.Frame(frame)
        grid_f.pack(fill="x", pady=4)

        ttk.Label(grid_f, text="设备序列号:").grid(row=0, column=0, sticky="w", pady=4)
        self.sn_entry = ttk.Entry(grid_f, width=32)
        self.sn_entry.grid(row=0, column=1, sticky="w", pady=4)
        self.sn_entry.insert(0, self.device.get('sn', ''))

        now = datetime.date.today()
        ttk.Label(grid_f, text="当前日期:").grid(row=1, column=0, sticky="w", pady=4)
        self.date_lbl = ttk.Label(grid_f, text=f"{now.year}年{now.month}月{now.day}日", font=("-apple-system", 11, "bold"))
        self.date_lbl.grid(row=1, column=1, sticky="w", pady=4)

        calc_btn = ttk.Button(frame, text="计算今日临时安全码", command=self._calc_classic_code)
        calc_btn.pack(anchor="w", pady=(12, 8))

        res_frame = ttk.Frame(frame)
        res_frame.pack(fill="x", pady=8)

        ttk.Label(res_frame, text="今日临时恢复密码:", font=("-apple-system", 11, "bold")).pack(side="left", padx=(0, 8))
        self.code_val_lbl = ttk.Label(res_frame, text="------", foreground="#007AFF", font=("Menlo", 14, "bold"))
        self.code_val_lbl.pack(side="left", padx=(0, 8))

        copy_btn = ttk.Button(res_frame, text="复制安全码", command=self._copy_code)
        copy_btn.pack(side="left")

    def _do_export_key(self):
        ok, msg, content = self.scanner.export_device_key(self.device)
        if not ok or not content:
            messagebox.showerror("错误", f"导出失败: {msg}", parent=self)
            return

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="保存设备特征文件",
            defaultextension=".xml",
            initialfile=f"DeviceKey_{self.device.get('mac', 'dev')}.xml",
            filetypes=[("XML 秘钥文件", "*.xml"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("成功", f"特征文件已成功导出至:\n{file_path}\n请发送该文件至海康官方获取解密激活 Key。", parent=self)
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {e}", parent=self)

    def _browse_key_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="选择官方解密秘钥文件",
            filetypes=[("XML 秘钥文件", "*.xml"), ("所有文件", "*.*")]
        )
        if path:
            self.key_path_var.set(path)

    def _do_reset_modern(self):
        key_path = self.key_path_var.get().strip()
        new_pwd = self.new_pwd_entry.get().strip()

        if not key_path:
            messagebox.showwarning("提示", "请选择官方发回的秘钥文件！", parent=self)
            return
        if not new_pwd or len(new_pwd) < 8:
            messagebox.showwarning("提示", "新密码长度建议不少于 8 位！", parent=self)
            return

        try:
            with open(key_path, "r", encoding="utf-8") as f:
                encrypt_content = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取秘钥文件失败: {e}", parent=self)
            return

        ok, msg = self.scanner.reset_password(
            device=self.device,
            new_password=new_pwd,
            encrypt_key=encrypt_content
        )
        if ok:
            messagebox.showinfo("成功", "密码重置成功！请使用新密码登录设备。", parent=self)
            self.destroy()
        else:
            messagebox.showerror("重置结果", msg, parent=self)

    def _calc_classic_code(self):
        sn = self.sn_entry.get().strip()
        if not sn:
            messagebox.showwarning("提示", "请输入设备序列号！", parent=self)
            return
        now = datetime.date.today()
        code = calculate_classic_recovery_code(sn, now.year, now.month, now.day)
        self.code_val_lbl.config(text=code)

    def _copy_code(self):
        code = self.code_val_lbl.cget("text")
        if code and code != "------":
            self.clipboard_clear()
            self.clipboard_append(code)
            messagebox.showinfo("提示", f"已复制安全码: {code}\n可直接作为老设备恢复密码输入。", parent=self)
