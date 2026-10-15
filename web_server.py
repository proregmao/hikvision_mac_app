"""
海康威视管理应用本地服务端与嵌入式前端
使用 Python 标准库 http.server，内置 QRCode 生成与海康微信小程序扫码重置功能
提供 RESTful API 与精美 macOS 原生质感桌面 UI
"""

import sys
import os
import json
import time
import socket
import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import webbrowser
import subprocess

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    from hikvision_mac_app.core.scanner import DeviceScanner
    from hikvision_mac_app.core.sadp_protocol import calculate_classic_recovery_code
except ImportError:
    from core.scanner import DeviceScanner
    from core.sadp_protocol import calculate_classic_recovery_code

scanner = DeviceScanner()
cached_devices = {}
is_searching = False
search_status_text = "就绪"

# 读取本地离线 qrcode.js 内容
QRCODE_JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static_qrcode.js")
QRCODE_JS_CONTENT = ""
if os.path.exists(QRCODE_JS_PATH):
    try:
        with open(QRCODE_JS_PATH, "r", encoding="utf-8") as f:
            QRCODE_JS_CONTENT = f.read()
    except Exception:
        pass

HTML_CONTENT = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>海康威视设备管理工具 (Hikvision Manager for macOS)</title>
  <script>
    {QRCODE_JS_CONTENT}
  </script>
  <style>
    :root {{
      --bg: #F5F6F8;
      --card-bg: #FFFFFF;
      --text-main: #1C1C1E;
      --text-sub: #8E8E93;
      --primary: #007AFF;
      --primary-hover: #0062CC;
      --success: #34C759;
      --warning: #FF9500;
      --danger: #FF3B30;
      --border: #E5E5EA;
      --radius: 10px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", sans-serif; }}
    body {{ background: var(--bg); color: var(--text-main); font-size: 13px; line-height: 1.5; padding: 20px; overflow-x: hidden; }}

    /* 顶部导航与工具栏 */
    .header-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
    .header-title {{ font-size: 18px; font-weight: 700; display: flex; align-items: center; gap: 8px; }}
    .header-tag {{ font-size: 11px; background: rgba(0,122,255,0.1); color: var(--primary); padding: 3px 8px; border-radius: 6px; font-weight: 600; }}

    .card {{ background: var(--card-bg); border-radius: var(--radius); border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(0,0,0,0.02); padding: 16px; margin-bottom: 16px; }}
    
    /* 工具栏布局 */
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }}
    .toolbar-left, .toolbar-right {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}

    .input-group {{ display: flex; align-items: center; background: #EFEFF4; border-radius: 8px; padding: 4px 10px; }}
    .input-group input, .input-group select {{ background: transparent; border: none; outline: none; font-size: 13px; padding: 4px; }}
    
    .btn {{ display: inline-flex; align-items: center; gap: 6px; background: #E5E5EA; color: var(--text-main); border: none; padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }}
    .btn:hover {{ background: #D1D1D6; }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-primary:hover {{ background: var(--primary-hover); }}
    .btn-warning {{ background: var(--warning); color: #fff; }}
    .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}

    /* 表格区域 */
    .table-container {{ overflow-x: auto; max-height: calc(100vh - 240px); border-radius: 8px; border: 1px solid var(--border); }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{ background: #FAFBFD; position: sticky; top: 0; padding: 12px 14px; font-size: 12px; font-weight: 600; color: var(--text-sub); border-bottom: 1px solid var(--border); z-index: 10; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); background: #FFF; font-size: 13px; white-space: nowrap; }}
    tr:hover td {{ background: #F8F9FB; }}
    tr.selected td {{ background: rgba(0, 122, 255, 0.08); }}

    .badge {{ display: inline-block; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }}
    .badge-dhcp {{ background: #E1F8E8; color: #1DBB53; }}
    .badge-static {{ background: #EFEFF4; color: #666; }}
    .badge-type {{ background: #EBF5FF; color: var(--primary); }}

    /* 弹窗抽屉模态框 */
    .modal-overlay {{ position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.35); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 100; }}
    .modal {{ background: #FFF; width: 560px; max-width: 92vw; border-radius: 12px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); animation: pop 0.2s ease-out; max-height: 90vh; overflow-y: auto; }}
    @keyframes pop {{ from {{ opacity: 0; transform: scale(0.96); }} to {{ opacity: 1; transform: scale(1); }} }}
    .modal-title {{ font-size: 16px; font-weight: 700; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
    .close-btn {{ background: none; border: none; font-size: 18px; cursor: pointer; color: var(--text-sub); }}

    .form-group {{ margin-bottom: 12px; }}
    .form-group label {{ display: block; font-size: 12px; font-weight: 600; color: var(--text-sub); margin-bottom: 5px; }}
    .form-group input, .form-group textarea {{ width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 13px; outline: none; }}
    .form-group input:focus, .form-group textarea:focus {{ border-color: var(--primary); box-shadow: 0 0 0 2px rgba(0,122,255,0.15); }}
    .form-row {{ display: flex; gap: 10px; }}
    .form-row .form-group {{ flex: 1; }}

    /* Tab 样式 */
    .tab-bar {{ display: flex; border-bottom: 1px solid var(--border); margin-bottom: 16px; }}
    .tab-item {{ padding: 8px 14px; cursor: pointer; font-weight: 600; color: var(--text-sub); border-bottom: 2px solid transparent; font-size: 13px; }}
    .tab-item.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
    
    .status-badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-sub); }}
    .status-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--success); }}
    .status-dot.pulsing {{ animation: pulse 1.2s infinite; background: var(--primary); }}
    @keyframes pulse {{ 0% {{ opacity: 0.4; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.4; }} }}

    /* 二维码展示卡片 */
    .qr-card {{ background: #FAFAFC; border: 1px dashed var(--border); border-radius: 10px; padding: 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 16px; }}
    .qr-box {{ background: #FFFFFF; padding: 12px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; justify-content: center; align-items: center; }}
    .qr-box img, .qr-box canvas {{ display: block; }}
  </style>
</head>
<body>

  <!-- 头部信息 -->
  <div class="header-bar">
    <div class="header-title">
      <span>📹 海康威视设备管理工具 (Hikvision SADP)</span>
      <span class="header-tag">macOS 本地桌面版</span>
    </div>
    <div class="status-badge">
      <span id="statusDot" class="status-dot"></span>
      <span id="statusText">就绪</span>
    </div>
  </div>

  <!-- 工具栏卡片 -->
  <div class="card">
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="input-group">
          <label style="font-weight:600; margin-right:6px;">搜索模式:</label>
          <select id="searchMode" onchange="onModeChange()">
            <option value="broadcast">全网广播 / 组播 (自动发现)</option>
            <option value="subnet">指定特定网段 (CIDR 深度穿透)</option>
          </select>
        </div>
        <div class="input-group" id="subnetGroup" style="display:none;">
          <input type="text" id="subnetInput" placeholder="例如 192.168.1.0/24" value="192.168.110.0/24" style="width:140px;">
        </div>
        <button class="btn btn-primary" id="searchBtn" onclick="triggerSearch()">🔍 开始搜索设备</button>
      </div>

      <div class="toolbar-right">
        <button class="btn" onclick="toggleSelectAll()">全选 / 取消</button>
        <button class="btn" onclick="openModifyModal()">⚙️ 修改网络参数</button>
        <button class="btn btn-warning" onclick="openRecoveryModal()">🔑 找回密码 (扫码向导)</button>
        <button class="btn" onclick="openWebAdmin()">🌐 访问 Web 登录页</button>
      </div>
    </div>
  </div>

  <!-- 设备列表表格 -->
  <div class="card" style="padding:0;">
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th style="width:36px; text-align:center;"><input type="checkbox" id="selectAllCheckbox" onchange="toggleSelectAll()"></th>
            <th style="width:40px;">#</th>
            <th>设备型号</th>
            <th>IPv4 地址</th>
            <th>子网掩码</th>
            <th>默认网关</th>
            <th>HTTP端口</th>
            <th>SDK端口</th>
            <th>网络模式</th>
            <th style="text-align:center; width:80px;">激活状态</th>
            <th>物理 MAC 地址</th>
            <th>设备序列号</th>
            <th>固件版本</th>
            <th style="text-align:center; width:130px;">操作</th>
          </tr>
        </thead>
        <tbody id="deviceTableBody">
          <tr><td colspan="14" style="text-align:center; padding:40px; color:#999;">正在检测局域网海康威视设备...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 底部统计 -->
  <div style="display:flex; justify-content:space-between; color:var(--text-sub); font-size:12px; padding:0 4px;">
    <span id="localIpHint">正在检测本机 IP...</span>
    <span id="selectedCountHint">共发现 0 台设备 | 已选中 0 台</span>
  </div>

  <!-- 新设备激活模态框 -->
  <div id="activateModal" class="modal-overlay">
    <div class="modal">
      <div class="modal-title">
        <span>🚀 激活海康威视新设备</span>
        <button class="close-btn" onclick="closeModal('activateModal')">&times;</button>
      </div>
      <div style="background:#E8F5E9; color:#2E7D32; padding:10px 12px; border-radius:6px; font-size:12px; margin-bottom:14px; line-height:1.5;">
        检测到该摄像头为全新出厂/未激活状态。请设置初始管理员 (admin) 密码完成设备激活。
      </div>
      <div class="form-group">
        <label>设备信息:</label>
        <div id="activateDevInfo" style="font-weight:600; color:#333; font-family:Menlo; font-size:13px; padding:4px 0;">-</div>
      </div>
      <div class="form-group">
        <label>设置管理员密码 (admin):</label>
        <input type="password" id="activatePassword" placeholder="8~16位，包含大写、小写字母或数字">
      </div>
      <div class="form-group">
        <label>确认新密码:</label>
        <input type="password" id="activatePasswordConfirm" placeholder="请再次输入确认密码">
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="btn" onclick="closeModal('activateModal')">取消</button>
        <button class="btn btn-primary" style="background:#34C759;" onclick="submitActivate()">确认并立即激活</button>
      </div>
    </div>
  </div>

  <!-- 单机/批量参数修改模态框 -->
  <div id="modifyModal" class="modal-overlay">
    <div class="modal">
      <div class="modal-title">
        <span id="modifyModalTitle">修改网络参数</span>
        <button class="close-btn" onclick="closeModal('modifyModal')">&times;</button>
      </div>
      <div id="batchModeHint" style="display:none; background:#FFF9E6; color:#996600; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px;">
        已勾选多台设备：将以“起始 IP”为基准，依次为选中的设备递增自动分配连续 IP 地址。
      </div>
      <div class="form-group">
        <label id="ipLabel">IPv4 地址:</label>
        <input type="text" id="formIp" placeholder="例如 192.168.110.187">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>子网掩码:</label>
          <input type="text" id="formMask" value="255.255.255.0">
        </div>
        <div class="form-group">
          <label>默认网关:</label>
          <input type="text" id="formGateway" placeholder="例如 192.168.110.254">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>DNS 服务器:</label>
          <input type="text" id="formDns" value="114.114.114.114">
        </div>
        <div class="form-group">
          <label>HTTP Web 端口:</label>
          <input type="number" id="formHttpPort" value="80">
        </div>
        <div class="form-group">
          <label>SDK 端口 (私有):</label>
          <input type="number" id="formCmdPort" value="8000">
        </div>
      </div>
      <div class="form-group">
        <label>设备当前管理密码* (用于权限校验):</label>
        <input type="password" id="formPassword" placeholder="输入设备管理员密码">
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="btn" onclick="closeModal('modifyModal')">取消</button>
        <button class="btn btn-primary" onclick="submitModify()">确认下发修改</button>
      </div>
    </div>
  </div>

  <!-- 找回密码向导模态框（支持小程序扫码） -->
  <div id="recoveryModal" class="modal-overlay">
    <div class="modal" style="width:620px;">
      <div class="modal-title">
        <span>🔑 找回设备密码向导</span>
        <button class="close-btn" onclick="closeModal('recoveryModal')">&times;</button>
      </div>

      <div class="tab-bar">
        <div class="tab-item active" onclick="switchRecoveryTab(0)">📱 微信扫码重置 (官方400)</div>
        <div class="tab-item" onclick="switchRecoveryTab(1)">📁 官方 DeviceKey 文件</div>
        <div class="tab-item" onclick="switchRecoveryTab(2)">🛠️ 机身物理 RESET 按键</div>
        <div class="tab-item" onclick="switchRecoveryTab(3)">⚡ 老设备日安全码</div>
      </div>

      <!-- Tab 0: 微信小程序 / 400密码重置助手扫码 -->
      <div id="tabQrCode">
        <div id="deviceDiagBanner" style="background:#EBF5FF; color:#0055B3; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px;">
          <span id="diagDeviceName">正在读取设备...</span>
        </div>

        <div class="qr-card">
          <div style="display:flex; justify-content:space-between; width:100%; align-items:center; margin-bottom:8px;">
            <span style="font-weight:600; font-size:13px; color:#333;">📷 海康设备重置专属二维码</span>
            <div style="font-size:12px; display:flex; gap:10px;">
              <label><input type="radio" name="qrFormat" value="raw" checked onchange="onQrFormatChange()"> 400助手专用密文</label>
              <label><input type="radio" name="qrFormat" value="xml" onchange="onQrFormatChange()"> 官方XML格式</label>
            </div>
          </div>

          <div id="qrLoading" style="color:var(--text-sub); padding:30px;">正在向设备请求重置特征码...</div>
          <div class="qr-box" id="qrBox" style="display:none;"></div>
          
          <div style="font-size:11px; color:#555; margin-top:10px; text-align:left; background:#FFF; padding:10px; border-radius:6px; border:1px solid var(--border); width:100%;">
            <strong>扫码指引（两者均可）：</strong><br>
            1. 微信小程序：搜索<strong>【海康威视400密码重置助手】</strong> -> 点击【密码重置】 -> 勾选设备类型 -> 点击底部<strong>【开始扫码】</strong>扫描上方二维码；<br>
            2. 微信服务号：关注<strong>【海康威视客户服务】</strong> -> 点击【贴心服务】 -> 【密码重置】 -> 【开始扫码】。<br>
            <div style="background:#FFF1F0; border-left:3px solid #FF3B30; padding:6px 8px; margin-top:6px; color:#CF1322; font-weight:600;">
              ⚠️ 极重要规则：海康设备采用单次会话机制，扫出验证码后请直接在下方输入提交！切勿在扫码期间点击“刷新二维码”或关闭窗口，否则设备内部会话重置，前一个验证码将立即失效报 emptyEncryptString。
            </div>
          </div>

          <div style="margin-top:10px; display:flex; gap:8px;">
            <button class="btn" style="padding:4px 10px; font-size:12px;" onclick="fetchQrCodeData()">🔄 刷新二维码</button>
            <button class="btn" style="padding:4px 10px; font-size:12px;" onclick="copyQrRawData()">📋 复制密文串</button>
          </div>
        </div>

        <div style="background:#F9F9FB; padding:14px; border-radius:8px; border:1px solid var(--border);">
          <div class="form-group">
            <label style="color:#007AFF; font-size:13px; font-weight:700;">① 输入手机端返回的安全验证码 (Security Code):</label>
            <input type="text" id="qrSecurityCode" placeholder="例如微信返回的 6 或 8 位字母数字验证码" style="font-family:Menlo,monospace; font-size:15px; font-weight:700; text-transform:uppercase;">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>② 设置新管理员密码:</label>
              <input type="password" id="qrNewPassword" placeholder="8~16位，含大小写字母与数字">
            </div>
            <div class="form-group">
              <label>③ 确认新密码:</label>
              <input type="password" id="qrConfirmPassword" placeholder="再次输入新密码">
            </div>
          </div>
          <button class="btn btn-primary" style="width:100%; justify-content:center; padding:10px; font-size:14px; font-weight:600;" onclick="submitQrResetPassword()">✅ 立即下发重置密码</button>
        </div>
      </div>

      <!-- Tab 1: 官方 DeviceKey.xml 文件导入 -->
      <div id="tabModern" style="display:none;">
        <p style="color:#666; font-size:12px; margin-bottom:12px;">
          海康官方 SADP SDK 规范的离线密钥恢复流程。导出特征文件发送给官方微信公众号或 400 客服，客服秒级回传解密文件。
        </p>
        <div style="margin-bottom:14px; padding:12px; background:#F8F9FA; border-radius:8px; border:1px solid var(--border);">
          <div style="font-weight:600; margin-bottom:6px;">步骤 1: 导出官方 DeviceKey.xml 特征文件</div>
          <div style="font-size:12px; color:#666; margin-bottom:8px;">包含设备芯片 RSA 签名硬件指纹，完全符合官方 SADP 工具标准。</div>
          <button class="btn btn-primary" onclick="exportDeviceKey()">📥 下载 DeviceKey_{{MAC}}.xml 文件</button>
        </div>
        <div style="padding:12px; background:#F8F9FA; border-radius:8px; border:1px solid var(--border);">
          <div style="font-weight:600; margin-bottom:6px;">步骤 2: 导入官方发回的 Encrypt_xxx.xml 文件并重置</div>
          <div class="form-group">
            <label>选择或粘贴客服回传的文件内容:</label>
            <input type="file" id="encryptKeyFile" onchange="onKeyFileSelect(this)" style="margin-bottom:6px;">
            <textarea id="encryptKeyText" rows="2" placeholder="或将 Encrypt_xxx.xml 内的 Code 串或 XML 粘贴在此..."></textarea>
          </div>
          <div class="form-group">
            <label>设置设备新管理员密码:</label>
            <input type="password" id="fileNewPassword" placeholder="8~16位，含大小写字母与数字">
          </div>
          <button class="btn btn-primary" onclick="submitFileResetPassword()">确认提交重置</button>
        </div>
      </div>

      <!-- Tab 2: 硬件物理 RESET 按键说明 -->
      <div id="tabPhysical" style="display:none;">
        <div style="background:#FFF9E6; border:1px solid #FFE58F; padding:12px; border-radius:8px; margin-bottom:14px;">
          <div style="font-weight:700; color:#B78103; font-size:13px; margin-bottom:4px;">💡 100% 成功、免扫码、免客服的最快方案：机身物理 RESET</div>
          <div style="font-size:12px; color:#666;">海康威视网络摄像机（包括当前这台半球摄像机 DS-2CD2125FD-IWS）出厂均配有硬件物理复位键。</div>
        </div>

        <div style="background:#FAFBFD; padding:14px; border-radius:8px; border:1px solid var(--border); font-size:13px; line-height:1.7;">
          <div style="font-weight:700; margin-bottom:6px; color:#1C1C1E;">复位操作步骤：</div>
          <ol style="padding-left:18px; color:#333;">
            <li><strong>取下透明球罩</strong>：拧下半球摄像机底座的 3 颗内六角螺丝，取下防护外罩；</li>
            <li><strong>找到 RESET 按键</strong>：在镜头模块旁边、MicroSD(TF) 卡槽侧面，有一个小微动按键，旁边标有清晰的字母 <strong>【RESET】</strong>；</li>
            <li><strong>通电长按 10 秒</strong>：保持摄像机插着网线/PoE 或电源通电，用笔尖或回形针按住 <strong>【RESET】 按键持续 10 秒</strong> 不松开；</li>
            <li><strong>设备重启</strong>：观察红外灯/状态灯闪烁后松开按键，摄像机将自动重启并<strong>完全恢复为出厂【未激活】状态</strong>；</li>
            <li><strong>重新激活</strong>：在当前软件工具中点击【🔍 开始搜索设备】，直接输入新密码即可秒级激活！</li>
          </ol>
        </div>
      </div>

      <!-- Tab 3: 经典日安全码算号器 -->
      <div id="tabClassic" style="display:none;">
        <div id="classicWarning" style="background:#FFF1F0; border:1px solid #FFA39E; color:#CF1322; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px; display:none;">
          ⚠️ 警告：当前设备固件（V5.5.0）已彻底关闭老日安全码后门（ResetAbility=false）。在 Web 登录页直接输入日安全码会提示密码错误。请使用 Tab 0 微信扫码或 Tab 2 物理 RESET。
        </div>
        <p style="color:#666; font-size:12px; margin-bottom:12px;">
          仅适用于 2017 年之前出厂的早期老固件设备（V5.3.0 以下）。根据设备序列号与当前日期计算每日出厂恢复安全码。
        </p>
        <div class="form-group">
          <label>设备序列号:</label>
          <input type="text" id="classicSn" readonly>
        </div>
        <div class="form-group">
          <button class="btn btn-primary" onclick="calcClassicCode()">⚡ 计算今日临时安全码</button>
        </div>
        <div id="classicResultBox" style="display:none; padding:12px; background:#EBF5FF; border-radius:8px; margin-top:12px;">
          <div style="font-size:12px; color:var(--text-sub);">今日出厂临时恢复码:</div>
          <div id="classicCodeVal" style="font-size:20px; font-weight:700; color:var(--primary); font-family:Menlo; margin:6px 0;">------</div>
          <div style="font-size:11px; color:#666;">注：仅对支持老版出厂恢复的旧设备有效。</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let devices = [];
    let selectedMacs = new Set();
    let currentTargetDevice = null;
    let currentQrText = "";
    let qrcodeInstance = null;

    function onModeChange() {{
      const mode = document.getElementById('searchMode').value;
      document.getElementById('subnetGroup').style.display = (mode === 'subnet') ? 'flex' : 'none';
    }}

    async function triggerSearch() {{
      const btn = document.getElementById('searchBtn');
      btn.disabled = true;
      document.getElementById('statusDot').className = 'status-dot pulsing';
      document.getElementById('statusText').innerText = '正在搜索设备...';

      const mode = document.getElementById('searchMode').value;
      const subnet = (mode === 'subnet') ? document.getElementById('subnetInput').value : '';

      try {{
        await fetch('/api/search', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{ subnet: subnet }})
        }});
      }} catch(e) {{}}

      let timer = setInterval(fetchDevices, 800);
      setTimeout(() => {{
        clearInterval(timer);
        fetchDevices();
        btn.disabled = false;
        document.getElementById('statusDot').className = 'status-dot';
        document.getElementById('statusText').innerText = '搜索完成';
      }}, 3500);
    }}

    async function fetchDevices() {{
      try {{
        const res = await fetch('/api/devices');
        const data = await res.json();
        devices = data.devices || [];
        document.getElementById('localIpHint').innerText = '本机探测 IP: ' + (data.local_ip || '未知');
        renderTable();
      }} catch(e) {{}}
    }}

    function renderTable() {{
      const tbody = document.getElementById('deviceTableBody');
      if (devices.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="13" style="text-align:center; padding:30px; color:#888;">未发现设备。请尝试点击“开始搜索设备”或指定网段探测。</td></tr>';
        updateStats();
        return;
      }}

      tbody.innerHTML = devices.map((d, idx) => {{
        const isSel = selectedMacs.has(d.mac);
        const crossBadge = d.cross_subnet ? `<span class="badge" style="background:#E3F2FD; color:#0D47A1; margin-left:4px; font-size:10px;">跨三层</span>` : '';
        const actBadge = d.activated 
          ? `<span class="badge" style="background:#E8F5E9; color:#2E7D32; font-weight:600;">已激活</span>`
          : `<span class="badge" style="background:#FFF3E0; color:#E65100; font-weight:700;">未激活</span>`;
        const webUrl = `http://${{d.ip}}:${{d.http_port || 80}}`;
        let actionBtns = `<a href="${{webUrl}}" target="_blank" class="btn btn-sm" style="text-decoration:none; display:inline-block; padding:3px 8px; font-size:11px; background:#007AFF; color:#fff; border-radius:4px;">打开Web</a>`;
        if (!d.activated) {{
          actionBtns = `<button class="btn btn-sm" style="padding:3px 8px; font-size:11px; background:#34C759; color:#fff; border-radius:4px; margin-right:4px;" onclick="openActivateModal('${{d.mac}}', event)">立即激活</button>` + actionBtns;
        }}
        return `
          <tr class="${{isSel ? 'selected' : ''}}" onclick="toggleRowSelect('${{d.mac}}', event)">
            <td style="text-align:center;" onclick="event.stopPropagation();">
              <input type="checkbox" ${{isSel ? 'checked' : ''}} onchange="onCheckboxChange('${{d.mac}}', this.checked)">
            </td>
            <td>${{idx + 1}}</td>
            <td style="font-weight:600;"><span class="badge badge-type">${{d.model}}</span>${{crossBadge}}</td>
            <td style="font-weight:600; color:#007AFF;">${{d.ip}}</td>
            <td>${{d.mask}}</td>
            <td>${{d.gateway || '-'}}</td>
            <td>${{d.http_port}}</td>
            <td>${{d.cmd_port}}</td>
            <td><span class="badge ${{d.dhcp ? 'badge-dhcp' : 'badge-static'}}">${{d.dhcp ? 'DHCP' : '静态'}}</span></td>
            <td style="text-align:center;">${{actBadge}}</td>
            <td style="font-family:Menlo; font-size:12px;">${{d.mac}}</td>
            <td style="font-family:Menlo; font-size:11px; color:#666;">${{d.sn || '-'}}</td>
            <td style="font-size:12px; color:#888;">${{d.version || '-'}}</td>
            <td style="text-align:center;" onclick="event.stopPropagation();">
              ${{actionBtns}}
            </td>
          </tr>
        `;
      }}).join('');

      updateStats();
    }}

    function onCheckboxChange(mac, checked) {{
      if (checked) selectedMacs.add(mac);
      else selectedMacs.delete(mac);
      renderTable();
    }}

    function toggleRowSelect(mac, event) {{
      if (selectedMacs.has(mac)) selectedMacs.delete(mac);
      else selectedMacs.add(mac);
      renderTable();
    }}

    function toggleSelectAll() {{
      if (selectedMacs.size === devices.length) {{
        selectedMacs.clear();
      }} else {{
        selectedMacs = new Set(devices.map(d => d.mac));
      }}
      renderTable();
    }}

    function updateStats() {{
      document.getElementById('selectedCountHint').innerText = `共发现 ${{devices.length}} 台设备 | 已选中 ${{selectedMacs.size}} 台`;
      document.getElementById('selectAllCheckbox').checked = (devices.length > 0 && selectedMacs.size === devices.length);
    }}

    function openModifyModal() {{
      if (selectedMacs.size === 0) {{
        alert('请先在列表中勾选需要修改参数的设备！');
        return;
      }}
      const isBatch = selectedMacs.size > 1;
      document.getElementById('modifyModalTitle').innerText = isBatch ? `批量修改网络参数 (已选 ${{selectedMacs.size}} 台)` : '修改设备网络参数';
      document.getElementById('batchModeHint').style.display = isBatch ? 'block' : 'none';
      document.getElementById('ipLabel').innerText = isBatch ? '起始 IPv4 地址 (递增分配):' : 'IPv4 地址:';

      const firstDev = devices.find(d => selectedMacs.has(d.mac));
      currentTargetDevice = firstDev;
      document.getElementById('formIp').value = firstDev.ip;
      document.getElementById('formMask').value = firstDev.mask;
      document.getElementById('formGateway').value = firstDev.gateway;
      document.getElementById('formDns').value = firstDev.dns || '114.114.114.114';
      document.getElementById('formHttpPort').value = firstDev.http_port || 80;
      document.getElementById('formCmdPort').value = firstDev.cmd_port || 8000;
      document.getElementById('formPassword').value = '';

      openModal('modifyModal');
    }}

    async function submitModify() {{
      const pwd = document.getElementById('formPassword').value.trim();
      if (!pwd) {{
        alert('请输入设备管理员密码进行校验！');
        return;
      }}

      const payload = {{
        macs: Array.from(selectedMacs),
        ip: document.getElementById('formIp').value.trim(),
        mask: document.getElementById('formMask').value.trim(),
        gateway: document.getElementById('formGateway').value.trim(),
        dns: document.getElementById('formDns').value.trim(),
        http_port: parseInt(document.getElementById('formHttpPort').value) || 80,
        cmd_port: parseInt(document.getElementById('formCmdPort').value) || 8000,
        password: pwd
      }};

      try {{
        const res = await fetch('/api/modify', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        const result = await res.json();
        alert(result.message);
        if (result.success) {{
          closeModal('modifyModal');
          setTimeout(triggerSearch, 1000);
        }}
      }} catch(e) {{
        alert('网络请求失败: ' + e);
      }}
    }}

    function openActivateModal(mac, event) {{
      if (event) event.stopPropagation();
      const dev = devices.find(d => d.mac === mac);
      if (!dev) return;
      currentTargetDevice = dev;
      document.getElementById('activateDevInfo').innerText = `${{dev.ip}} (${{dev.mac}}) - ${{dev.model}}`;
      document.getElementById('activatePassword').value = '';
      document.getElementById('activatePasswordConfirm').value = '';
      openModal('activateModal');
    }}

    async function submitActivate() {{
      const p1 = document.getElementById('activatePassword').value.trim();
      const p2 = document.getElementById('activatePasswordConfirm').value.trim();
      if (!p1 || p1.length < 8) {{
        alert('密码长度不能少于 8 位！');
        return;
      }}
      if (p1 !== p2) {{
        alert('两次输入的密码不一致！');
        return;
      }}
      try {{
        const res = await fetch('/api/activate', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{ mac: currentTargetDevice.mac, password: p1 }})
        }});
        const data = await res.json();
        alert(data.message);
        if (data.success) {{
          closeModal('activateModal');
          setTimeout(fetchDevices, 1000);
        }}
      }} catch(e) {{
        alert('请求失败: ' + e);
      }}
    }}

    function openRecoveryModal() {{
      if (selectedMacs.size === 0) {{
        alert('请先在列表中勾选需要找回密码的设备！');
        return;
      }}
      const firstDev = devices.find(d => selectedMacs.has(d.mac));
      currentTargetDevice = firstDev;
      document.getElementById('classicSn').value = firstDev.sn || '';
      document.getElementById('classicResultBox').style.display = 'none';
      switchRecoveryTab(0);
      openModal('recoveryModal');
      fetchQrCodeData();
    }}

    let currentRawEncrypt = "";
    let currentOfficialXml = "";

    function switchRecoveryTab(index) {{
      const tabs = document.querySelectorAll('#recoveryModal .tab-item');
      tabs.forEach((t, i) => t.className = 'tab-item ' + (i === index ? 'active' : ''));
      document.getElementById('tabQrCode').style.display = (index === 0) ? 'block' : 'none';
      document.getElementById('tabModern').style.display = (index === 1) ? 'block' : 'none';
      document.getElementById('tabPhysical').style.display = (index === 2) ? 'block' : 'none';
      document.getElementById('tabClassic').style.display = (index === 3) ? 'block' : 'none';

      if (index === 3 && currentTargetDevice) {{
        const isModern = (currentTargetDevice.version && !currentTargetDevice.version.startsWith('V4') && currentTargetDevice.reset_ability === false);
        document.getElementById('classicWarning').style.display = isModern ? 'block' : 'none';
      }}
    }}

    function onQrFormatChange() {{
      const radios = document.getElementsByName('qrFormat');
      let mode = 'raw';
      for (const r of radios) {{
        if (r.checked) mode = r.value;
      }}
      const textToRender = (mode === 'xml' && currentOfficialXml) ? currentOfficialXml : currentRawEncrypt;
      if (textToRender) {{
        currentQrText = textToRender;
        renderQrCode(textToRender);
      }}
    }}

    async function fetchQrCodeData() {{
      if (!currentTargetDevice) return;
      document.getElementById('qrLoading').style.display = 'block';
      document.getElementById('qrBox').style.display = 'none';

      // 显示诊断标签
      document.getElementById('diagDeviceName').innerHTML = 
        `当前目标: <strong>${{currentTargetDevice.model}}</strong> (${{currentTargetDevice.ip}}) | MAC: <code>${{currentTargetDevice.mac}}</code> | 序列号: <code>${{currentTargetDevice.sn || '未知'}}</code>` +
        (currentTargetDevice.boot_time ? ` | 设备开机时间: ${{currentTargetDevice.boot_time}}` : '');

      try {{
        const res = await fetch(`/api/get_qr_data?mac=${{currentTargetDevice.mac}}`);
        const data = await res.json();
        if (data.success && data.raw_encrypt_string) {{
          currentRawEncrypt = data.raw_encrypt_string;
          currentOfficialXml = data.official_xml || "";
          
          const radios = document.getElementsByName('qrFormat');
          let mode = 'raw';
          for (const r of radios) {{ if (r.checked) mode = r.value; }}
          currentQrText = (mode === 'xml' && currentOfficialXml) ? currentOfficialXml : currentRawEncrypt;

          renderQrCode(currentQrText);
        }} else {{
          document.getElementById('qrLoading').innerText = data.message || '获取设备二维码特征失败，请尝试刷新重试。';
        }}
      }} catch(e) {{
        document.getElementById('qrLoading').innerText = '网络异常: ' + e;
      }}
    }}

    function renderQrCode(text) {{
      document.getElementById('qrLoading').style.display = 'none';
      const box = document.getElementById('qrBox');
      box.style.display = 'flex';
      box.innerHTML = '';
      if (typeof QRCode !== 'undefined') {{
        qrcodeInstance = new QRCode(box, {{
          text: text,
          width: 200,
          height: 200,
          colorDark: '#000000',
          colorLight: '#FFFFFF',
          correctLevel: QRCode.CorrectLevel.M
        }});
      }} else {{
        box.innerHTML = '<div style="color:red;">未加载二维码生成组件</div>';
      }}
    }}

    function copyQrRawData() {{
      if (!currentQrText) return;
      navigator.clipboard.writeText(currentQrText).then(() => {{
        alert('特征密文已复制到剪贴板！');
      }}).catch(() => {{
        prompt('请复制以下特征密文:', currentQrText);
      }});
    }}

    async function submitQrResetPassword() {{
      const secCode = document.getElementById('qrSecurityCode').value.trim();
      const newPwd = document.getElementById('qrNewPassword').value.trim();
      const confirmPwd = document.getElementById('qrConfirmPassword').value.trim();

      if (!secCode) {{
        alert('请输入手机小程序中生成的安全验证码！');
        return;
      }}
      if (!newPwd || newPwd.length < 8) {{
        alert('新密码长度不能少于 8 位！');
        return;
      }}
      if (newPwd !== confirmPwd) {{
        alert('两次输入的新密码不一致，请重新输入！');
        return;
      }}

      try {{
        const res = await fetch('/api/reset_password', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{
            mac: currentTargetDevice.mac,
            security_code: secCode,
            new_password: newPwd
          }})
        }});
        const data = await res.json();
        alert(data.message);
        if (data.success) {{
          closeModal('recoveryModal');
          setTimeout(triggerSearch, 1000);
        }}
      }} catch(e) {{
        alert('请求失败: ' + e);
      }}
    }}

    function exportDeviceKey() {{
      if (!currentTargetDevice) return;
      window.location.href = `/api/export_key?mac=${{currentTargetDevice.mac}}`;
    }}

    function onKeyFileSelect(input) {{
      if (input.files && input.files[0]) {{
        const reader = new FileReader();
        reader.onload = e => document.getElementById('encryptKeyText').value = e.target.result;
        reader.readAsText(input.files[0]);
      }}
    }}

    async function submitFileResetPassword() {{
      const encryptKey = document.getElementById('encryptKeyText').value.trim();
      const newPwd = document.getElementById('fileNewPassword').value.trim();
      if (!encryptKey) {{
        alert('请导入或粘贴官方秘钥文件内容！');
        return;
      }}
      if (!newPwd || newPwd.length < 8) {{
        alert('新密码建议不少于 8 位！');
        return;
      }}

      const res = await fetch('/api/reset_password', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          mac: currentTargetDevice.mac,
          new_password: newPwd,
          encrypt_key: encryptKey
        }})
      }});
      const data = await res.json();
      alert(data.message);
      if (data.success) closeModal('recoveryModal');
    }}

    async function calcClassicCode() {{
      const sn = document.getElementById('classicSn').value.trim();
      const res = await fetch('/api/calc_recovery_code', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{ sn: sn }})
      }});
      const data = await res.json();
      document.getElementById('classicCodeVal').innerText = data.code;
      document.getElementById('classicResultBox').style.display = 'block';
    }}

    function openWebAdmin() {{
      if (selectedMacs.size === 0) {{
        alert('请先在列表中勾选需要访问的设备！');
        return;
      }}
      const firstDev = devices.find(d => selectedMacs.has(d.mac));
      const url = (firstDev.http_port == 80) ? `http://${{firstDev.ip}}` : `http://${{firstDev.ip}}:${{firstDev.http_port}}`;
      window.open(url, '_blank');
    }}

    function openModal(id) {{ document.getElementById(id).style.display = 'flex'; }}
    function closeModal(id) {{ document.getElementById(id).style.display = 'none'; }}

    // 初始化加载
    triggerSearch();
  </script>
</body>
</html>
"""

class HikvisionRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/' or url.path == '/index.html':
            body = HTML_CONTENT.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == '/api/devices':
            local_ip = scanner.get_local_ip()
            dev_list = list(cached_devices.values())
            self._send_json({'devices': dev_list, 'local_ip': local_ip})
        elif url.path == '/api/get_qr_data':
            params = parse_qs(url.query)
            mac = params.get('mac', [''])[0]
            dev = cached_devices.get(mac)
            if not dev:
                self._send_json({'success': False, 'message': '未找到设备'}, status=404)
                return
            ok, msg, raw_encrypt_string, official_xml = scanner.export_device_key(dev)
            
            if not ok or not raw_encrypt_string:
                self._send_json({'success': False, 'message': msg or '未能提取到设备加密串'}, status=500)
                return

            self._send_json({
                'success': True,
                'raw_encrypt_string': raw_encrypt_string,
                'official_xml': official_xml,
                'mac': mac,
                'sn': dev.get('sn', ''),
                'model': dev.get('model', ''),
                'boot_time': dev.get('boot_time', ''),
                'version': dev.get('version', '')
            })
        elif url.path == '/api/export_key':
            params = parse_qs(url.query)
            mac = params.get('mac', [''])[0]
            dev = cached_devices.get(mac)
            if not dev:
                self._send_json({'error': '设备不存在'}, status=404)
                return
            ok, msg, raw_encrypt_string, official_xml = scanner.export_device_key(dev)
            body = (official_xml or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/xml; charset=utf-8')
            self.send_header('Content-Disposition', f'attachment; filename="DeviceKey_{mac}.xml"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else '{}'
        try:
            params = json.loads(post_data)
        except Exception:
            params = {}

        if url.path == '/api/search':
            custom_subnet = params.get('subnet')
            cached_devices.clear()
            def on_found(dev):
                cached_devices[dev['mac']] = dev
            scanner.search(custom_subnet=custom_subnet, timeout=3.2, on_device_found=on_found)
            self._send_json({'status': 'searching'})

        elif url.path == '/api/activate':
            mac = params.get('mac')
            password = params.get('password')
            if not mac or not password:
                self._send_json({'success': False, 'message': '缺少必要参数'}, status=400)
                return
            dev = cached_devices.get(mac)
            if not dev:
                self._send_json({'success': False, 'message': '未在当前搜索列表中找到该设备'}, status=404)
                return
            ok, msg = scanner.activate_device(dev, password)
            self._send_json({'success': ok, 'message': msg})

        elif url.path == '/api/modify':
            macs = params.get('macs', [])
            start_ip = params.get('ip')
            mask = params.get('mask')
            gw = params.get('gateway')
            dns = params.get('dns')
            http_port = params.get('http_port', 80)
            cmd_port = params.get('cmd_port', 8000)
            pwd = params.get('password')

            if not macs or not start_ip or not pwd:
                self._send_json({'success': False, 'message': '参数不完整'}, status=400)
                return

            import ipaddress
            try:
                base_ip_int = int(ipaddress.IPv4Address(start_ip))
            except Exception:
                self._send_json({'success': False, 'message': '无效的 IPv4 地址'}, status=400)
                return

            success_count = 0
            fail_list = []
            for idx, mac in enumerate(macs):
                dev = cached_devices.get(mac)
                if not dev:
                    continue
                allocated_ip = str(ipaddress.IPv4Address(base_ip_int + idx))
                ok, msg = scanner.modify_device(
                    device=dev,
                    new_ip=allocated_ip,
                    new_mask=mask,
                    new_gateway=gw,
                    new_dns=dns,
                    new_http_port=http_port,
                    new_cmd_port=cmd_port,
                    password=pwd
                )
                if ok:
                    success_count += 1
                else:
                    fail_list.append(f"{dev.get('ip')}: {msg}")

            if len(macs) == 1:
                if success_count == 1:
                    self._send_json({'success': True, 'message': '网络参数修改成功！'})
                else:
                    err_msg = fail_list[0] if fail_list else '修改失败'
                    self._send_json({'success': False, 'message': err_msg})
            else:
                msg = f"批量修改完成：成功 {success_count} 台，失败 {len(fail_list)} 台"
                if fail_list:
                    msg += "\\n" + "\\n".join(fail_list[:3])
                self._send_json({'success': success_count > 0, 'message': msg})

        elif url.path == '/api/reset_password':
            mac = params.get('mac')
            new_pwd = params.get('new_password')
            code = params.get('security_code') or params.get('encrypt_key') or params.get('code')
            dev = cached_devices.get(mac)
            if not dev or not new_pwd:
                self._send_json({'success': False, 'message': '参数不完整'}, status=400)
                return
            ok, msg = scanner.reset_password(
                dev,
                new_password=new_pwd,
                code=code
            )
            self._send_json({'success': ok, 'message': msg})

        elif url.path == '/api/calc_recovery_code':
            sn = params.get('sn', '')
            now = datetime.date.today()
            code = calculate_classic_recovery_code(sn, now.year, now.month, now.day)
            self._send_json({'code': code})

        else:
            self.send_error(404, "Not Found")

def is_server_running(port=23702):
    """检测指定端口是否已经有运行中的海康服务实例"""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/devices", headers={'User-Agent': 'HikvisionCheck'})
        with urllib.request.urlopen(req, timeout=1.0) as res:
            if res.status == 200:
                data = json.loads(res.read().decode('utf-8'))
                return 'devices' in data
    except Exception:
        pass
    return False

def open_desktop_window(url):
    """唤起独立 Chrome App 窗口或默认浏览器"""
    chrome_app_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    launched = False
    if os.path.exists(chrome_app_path):
        try:
            subprocess.Popen([chrome_app_path, f"--app={url}"])
            launched = True
            print(f"[*] 已唤起 Google Chrome 独立 App 窗口: {url}")
        except Exception:
            pass

    if not launched:
        webbrowser.open(url)
        print(f"[*] 已在系统默认浏览器中打开桌面面板: {url}")

def start_server(port=23702, max_retries=10):
    """启动本地 HTTP 服务，支持端口复用与自动递增"""
    ThreadingHTTPServer.allow_reuse_address = True
    for p in range(port, port + max_retries):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', p), HikvisionRequestHandler)
            print(f"[*] 海康威视管理服务已在本地运行: http://127.0.0.1:{p}")
            return server, p
        except OSError as e:
            if e.errno == 48:  # Address already in use
                continue
            raise e
    raise OSError(f"无法在端口 {port}~{port+max_retries} 范围内启动服务")

def run_app():
    port = 23702
    url = f"http://127.0.0.1:{port}"

    # 1. 检测是否已有服务在运行
    if is_server_running(port):
        print(f"[*] 检测到海康威视管理服务已在后台运行 (http://127.0.0.1:{port})")
        open_desktop_window(url)
        return

    # 2. 若未运行或端口被非本应用占用，启动新服务（自动寻找可用端口）
    server, actual_port = start_server(port)
    actual_url = f"http://127.0.0.1:{actual_port}"

    open_desktop_window(actual_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] 服务已停止。")
        server.server_close()


if __name__ == '__main__':
    run_app()
