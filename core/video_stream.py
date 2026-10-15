"""
海康威视实时视频流与抓拍控制引擎
支持 RTSP 规范流生成、外部播放器调用 (VLC/IINA/系统默认)、
ISAPI 实时抓拍 (Digest/Basic 鉴权) 以及 PTZ 云台控制
"""

import os
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Tuple, Any

def generate_rtsp_url(
    ip: str,
    port: int = 554,
    username: str = "admin",
    password: str = "",
    channel: int = 1,
    stream_type: int = 1
) -> str:
    """
    根据海康威视协议生成标准 RTSP 实时视频流地址
    :param ip: 设备 IP
    :param port: RTSP 端口（默认 554）
    :param username: 用户名（默认 admin）
    :param password: 设备密码
    :param channel: 通道号（默认 1）
    :param stream_type: 码流类型（1 为主码流高清，2 为子码流标清/流畅）
    :return: 规范的 RTSP 链接
    """
    channel_id = channel * 100 + stream_type
    encoded_user = urllib.parse.quote(username, safe="")
    encoded_pwd = urllib.parse.quote(password, safe="")
    
    if encoded_pwd:
        auth_part = f"{encoded_user}:{encoded_pwd}@"
    elif encoded_user:
        auth_part = f"{encoded_user}@"
    else:
        auth_part = ""
        
    port_str = f":{port}" if port and port != 554 else ""
    return f"rtsp://{auth_part}{ip}{port_str}/Streaming/Channels/{channel_id}"

def detect_installed_players() -> List[Dict[str, str]]:
    """
    检测 macOS 系统中安装的可用视频流播放器
    """
    players = []
    
    candidates = [
        {"name": "IINA", "path": "/Applications/IINA.app", "desc": "现代原生 macOS 播放器 (推荐)"},
        {"name": "VLC", "path": "/Applications/VLC.app", "desc": "强大兼容的开源流媒体播放器"},
        {"name": "QuickTime Player", "path": "/Applications/QuickTime Player.app", "desc": "macOS 系统内置播放器"}
    ]
    
    for item in candidates:
        if os.path.exists(item["path"]):
            players.append(item)
            
    return players

def launch_rtsp_player(rtsp_url: str, preferred_player: Optional[str] = None) -> Tuple[bool, str]:
    """
    调用 macOS 系统命令拉起播放器播放 RTSP 实时视频流
    """
    if not rtsp_url:
        return False, "RTSP 地址为空"

    installed = detect_installed_players()
    chosen_path = None
    player_name = "默认播放器"

    if preferred_player:
        for p in installed:
            if p["name"].lower() == preferred_player.lower():
                chosen_path = p["path"]
                player_name = p["name"]
                break

    if not chosen_path and installed:
        # 默认优先 VLC 或 IINA
        for p in installed:
            if p["name"] in ["IINA", "VLC"]:
                chosen_path = p["path"]
                player_name = p["name"]
                break
        if not chosen_path:
            chosen_path = installed[0]["path"]
            player_name = installed[0]["name"]

    try:
        if chosen_path:
            subprocess.Popen(["open", "-a", chosen_path, rtsp_url])
            return True, f"已在 {player_name} 中调起实时视频播放"
        else:
            subprocess.Popen(["open", rtsp_url])
            return True, "已通过系统默认关联应用调起 RTSP 流"
    except Exception as e:
        return False, f"调起播放器失败: {str(e)}"

def get_device_snapshot(
    ip: str,
    http_port: int = 80,
    username: str = "admin",
    password: str = "",
    channel: int = 1,
    timeout: float = 3.5
) -> Tuple[bool, Any, str]:
    """
    从海康威视设备抓取即时单帧监控画面 (ISAPI Picture)
    支持 Digest 摘要认证与 Basic 基础认证双重重试机制
    :return: (成功状态, 图片二进制数据或错误原因, Content-Type)
    """
    channel_id = channel * 100 + 1
    target_urls = [
        f"http://{ip}:{http_port}/ISAPI/Streaming/channels/{channel_id}/picture",
        f"http://{ip}:{http_port}/ISAPI/Streaming/channels/{channel}/picture",
        f"http://{ip}:{http_port}/onvif-http/snapshot?channel={channel}"
    ]

    # 构建支持 Digest 与 Basic 认证的 Opener
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    for u in target_urls:
        password_mgr.add_password(None, u, username, password)

    auth_handler = urllib.request.HTTPDigestAuthHandler(password_mgr)
    basic_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    opener = urllib.request.build_opener(auth_handler, basic_handler)

    last_err = "未知错误"
    for url in target_urls:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "HikvisionMacTool/1.0",
                    "Accept": "image/jpeg,image/png,*/*"
                }
            )
            with opener.open(req, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "image/jpeg")
                data = response.read()
                if len(data) > 100:  # 有效图像
                    return True, data, content_type
        except urllib.error.HTTPError as e:
            if e.code in [401, 403]:
                return False, "设备访问认证失败：请检查输入的管理员密码是否正确", "text/plain"
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = str(e)

    return False, f"抓取实时画面失败: {last_err}", "text/plain"

def control_ptz(
    ip: str,
    http_port: int = 80,
    username: str = "admin",
    password: str = "",
    channel: int = 1,
    action: str = "STOP",
    speed: int = 4,
    timeout: float = 2.5
) -> Tuple[bool, str]:
    """
    发送海康 ISAPI PTZ 云台与镜头控制指令
    :param action: 方向/控制动作：UP, DOWN, LEFT, RIGHT, UP_LEFT, UP_RIGHT,
                   DOWN_LEFT, DOWN_RIGHT, ZOOM_IN, ZOOM_OUT, FOCUS_IN, FOCUS_OUT, STOP
    :param speed: 速度 1~7
    """
    speed_val = max(1, min(7, speed)) * 10
    
    pan = 0
    tilt = 0
    zoom = 0
    
    action_upper = action.upper()
    if action_upper == "UP":
        tilt = speed_val
    elif action_upper == "DOWN":
        tilt = -speed_val
    elif action_upper == "LEFT":
        pan = -speed_val
    elif action_upper == "RIGHT":
        pan = speed_val
    elif action_upper == "UP_LEFT":
        pan = -int(speed_val * 0.7)
        tilt = int(speed_val * 0.7)
    elif action_upper == "UP_RIGHT":
        pan = int(speed_val * 0.7)
        tilt = int(speed_val * 0.7)
    elif action_upper == "DOWN_LEFT":
        pan = -int(speed_val * 0.7)
        tilt = -int(speed_val * 0.7)
    elif action_upper == "DOWN_RIGHT":
        pan = int(speed_val * 0.7)
        tilt = -int(speed_val * 0.7)
    elif action_upper == "ZOOM_IN":
        zoom = speed_val
    elif action_upper == "ZOOM_OUT":
        zoom = -speed_val
    elif action_upper == "STOP":
        pan = 0
        tilt = 0
        zoom = 0
    else:
        return False, f"不支持的 PTZ 操作指令: {action}"

    xml_body = (
        f"<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<PTZData version='2.0' xmlns='http://www.isapi.org/ver20/XMLSchema'>\n"
        f"  <pan>{pan}</pan>\n"
        f"  <tilt>{tilt}</tilt>\n"
        f"  <zoom>{zoom}</zoom>\n"
        f"</PTZData>\n"
    ).encode("utf-8")

    url = f"http://{ip}:{http_port}/ISAPI/PTZCtrl/channels/{channel}/continuous"
    
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, url, username, password)
    opener = urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(password_mgr),
        urllib.request.HTTPBasicAuthHandler(password_mgr)
    )

    try:
        req = urllib.request.Request(
            url,
            data=xml_body,
            headers={"Content-Type": "application/xml; charset=\"UTF-8\""},
            method="PUT"
        )
        with opener.open(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            if resp.status == 200 or "statusValue>200" in content or "statusCode>1<" in content:
                return True, "PTZ 指令下发成功"
            return True, "PTZ 指令已送达"
    except urllib.error.HTTPError as e:
        if e.code in [401, 403]:
            return False, "PTZ 控制认证失败：请核对设备密码"
        elif e.code == 404 or e.code == 501:
            return False, "该设备不支持 PTZ 云台控制（可能为定焦枪机）"
        return False, f"PTZ 指令返回错误 HTTP {e.code}"
    except Exception as e:
        return False, f"PTZ 控制请求异常: {str(e)}"
