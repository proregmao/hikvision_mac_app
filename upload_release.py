#!/usr/bin/env python3
"""
GitHub Release 一键创建与资产上传辅助脚本
"""
import sys
import os
import json
import urllib.request
import urllib.error

REPO = "proregmao/hikvision_mac_app"
TAG = "v1.0.0"
TITLE = "海康威视 macOS 桌面管理工具 v1.0.0 正式版"
BODY = """## 📷 海康威视 macOS 桌面管理工具 v1.0.0 正式版发布

专为 macOS 用户深度定制的海康威视 (Hikvision) 设备局域网管理与密码重置工具。开箱即用，双击运行！

### ✨ 核心亮点
- 🍏 **原生体验**：现代 macOS 质感 UI，视网膜高分屏支持，内存占用极低。
- ⚡ **毫秒级发现**：二层 UDP 广播/组播，极速扫描局域网 IPC/NVR 等设备。
- 🌐 **独创 Subnet V20 跨三层探测**：跨路由穿透扫描（如跨 `192.168.220.0/24` 子网），突破广播域隔离。
- 🚀 **新设备探测与一键激活**：自动标注未激活设备，支持直接下发激活指令。
- 📱 **真机对齐微信小程序扫码**：176 字符芯片加密串扫码 100% 成功，获取口令一键重置。
- 💻 **全环境自包含**：内置完整运行时，无需安装 Python 环境，任何 Mac 电脑双击即开。

### 📦 下载安装
下载下方的 `.dmg` 安装镜像文件，双击打开后将「海康威视管理工具」拖入「Applications (应用程序)」文件夹即可使用。
"""

def upload_release(token, file_path):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ReleaseUploader"
    }

    # 1. 查找或创建 Release
    create_url = f"https://api.github.com/repos/{REPO}/releases"
    data = json.dumps({
        "tag_name": TAG,
        "name": TITLE,
        "body": BODY,
        "draft": False,
        "prerelease": False
    }).encode("utf-8")

    req = urllib.request.Request(create_url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            release_info = json.loads(resp.read().decode("utf-8"))
            print(f"[+] Release 创建成功: {release_info.get('html_url')}")
            upload_url = release_info["upload_url"].split("{")[0]
            release_id = release_info["id"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        if "already_exists" in err_body:
            # 获取已存在的 release
            get_req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=headers)
            with urllib.request.urlopen(get_req) as resp:
                release_info = json.loads(resp.read().decode("utf-8"))
                upload_url = release_info["upload_url"].split("{")[0]
                print(f"[*] Release 已存在: {release_info.get('html_url')}")
        else:
            print(f"[-] 创建 Release 失败: {e.code} {err_body}")
            return False

    # 2. 上传 DMG 资产
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    upload_asset_url = f"{upload_url}?name={urllib.parse.quote(file_name)}"
    print(f"[*] 正在上传资产 {file_name} ({file_size / (1024*1024):.2f} MB)...")

    with open(file_path, "rb") as f:
        file_data = f.read()

    asset_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-apple-diskimage",
        "Content-Length": str(file_size),
        "Accept": "application/vnd.github+json",
        "User-Agent": "ReleaseUploader"
    }

    asset_req = urllib.request.Request(upload_asset_url, data=file_data, headers=asset_headers)
    try:
        with urllib.request.urlopen(asset_req) as resp:
            asset_info = json.loads(resp.read().decode("utf-8"))
            print(f"[+] 资产上传成功: {asset_info.get('browser_download_url')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[-] 资产上传失败: {e.code} {e.read().decode('utf-8')}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 upload_release.py <GITHUB_TOKEN> <FILE_PATH>")
        sys.exit(1)
    upload_release(sys.argv[1], sys.argv[2])
