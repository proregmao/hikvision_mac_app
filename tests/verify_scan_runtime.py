"""
真实网络环境扫描验证
"""

import sys
import os
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from hikvision_mac_app.core.scanner import DeviceScanner

def test_live_scan():
    print("[*] 正在启动实时网络扫描验证...")
    scanner = DeviceScanner()
    found = []

    def on_device(dev):
        print(f"[+] 发现设备: {dev['model']} | IP: {dev['ip']} | MAC: {dev['mac']}")
        found.append(dev)

    finished = [False]
    def on_done(results):
        finished[0] = True

    scanner.search(timeout=3.0, on_device_found=on_device, on_finished=on_done)

    # 等待完成
    start = time.time()
    while not finished[0] and time.time() - start < 4.0:
        time.sleep(0.2)

    print(f"[*] 扫描结束，共抓取到 {len(found)} 台设备。")
    assert len(found) >= 1, "未能在局域网内探测到海康设备！"
    print("[*] 实时网络扫描验证成功！")

if __name__ == '__main__':
    test_live_scan()
