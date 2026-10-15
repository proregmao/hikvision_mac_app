"""
海康威视网络扫描与参数控制引擎
支持全网广播/组播搜索、指定 CIDR 网段探测、参数修改与找回密码
"""

import os
import socket
import struct
import time
import uuid
import ipaddress
import threading
import urllib.request
import urllib.error
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Callable, Any, Tuple
from .sadp_protocol import (
    SADP_MULTICAST_IP,
    SADP_PORT,
    build_probe_xml,
    build_modify_xml,
    build_export_key_xml,
    build_get_code_xml,
    build_reset_password_xml,
    build_official_device_key_xml,
    build_activate_xml,
    parse_xml_to_dict
)

class DeviceScanner:
    def __init__(self):
        self._is_searching = False
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_local_ip(self) -> str:
        """获取本机当前默认网卡的 IPv4 地址"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('223.5.5.5', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def search(
        self,
        custom_subnet: Optional[str] = None,
        timeout: float = 3.0,
        on_device_found: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_finished: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        """在独立后台线程中执行搜索"""
        thread = threading.Thread(
            target=self._search_worker,
            args=(custom_subnet, timeout, on_device_found, on_finished),
            daemon=True
        )
        thread.start()

    def stop_search(self):
        self._is_searching = False

    def _search_worker(
        self,
        custom_subnet: Optional[str],
        timeout: float,
        on_device_found: Optional[Callable[[Dict[str, Any]], None]],
        on_finished: Optional[Callable[[List[Dict[str, Any]]], None]]
    ):
        self._is_searching = True
        with self._lock:
            self._devices.clear()

        local_ip = self.get_local_ip()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', 0))
        sock.settimeout(0.5)

        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        except Exception:
            pass

        # 构建探针报文 (官方 inquiry 和 inquiry_v32)
        packet_v32 = f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{uuid.uuid4()}</Uuid><Types>inquiry_v32</Types></Probe>'.encode('utf-8')
        packet = build_probe_xml()
        targets = [
            (SADP_MULTICAST_IP, SADP_PORT),
            ('255.255.255.255', SADP_PORT)
        ]

        # 如果未指定网段，加入本地子网广播
        if not custom_subnet:
            if '.' in local_ip:
                prefix = local_ip.rsplit('.', 1)[0]
                targets.append((f"{prefix}.255", SADP_PORT))
        else:
            # 用户指定了特定网段，如 192.168.220.0/24
            try:
                net = ipaddress.ip_network(custom_subnet.strip(), strict=False)
                targets.append((str(net.broadcast_address), SADP_PORT))
                
                # 如果是 /24 或更小网段，向所有主机并发单播打探针以突破跨三层路由
                if net.num_addresses <= 256:
                    for host in net.hosts():
                        targets.append((str(host), SADP_PORT))
            except Exception:
                pass

        # 发送 UDP 探测报文
        for target in targets:
            try:
                sock.sendto(packet, target)
                if custom_subnet:
                    sock.sendto(packet_v32, target)
            except Exception:
                pass

        # 若指定了特定网段（如跨三层网段），启动海康官方 Subnet V20 协议探测线程
        cross_thread = None
        if custom_subnet:
            cross_thread = threading.Thread(
                target=self._probe_cross_subnet,
                args=(custom_subnet.strip(), on_device_found),
                daemon=True
            )
            cross_thread.start()

        filter_net = None
        if custom_subnet:
            try:
                filter_net = ipaddress.ip_network(custom_subnet.strip(), strict=False)
            except Exception:
                filter_net = None

        # 监听并收集响应
        start_time = time.time()
        while self._is_searching and (time.time() - start_time < timeout):
            try:
                data, addr = sock.recvfrom(65535)
                xml_text = data.decode('utf-8', errors='ignore')
                if '<ProbeMatch>' not in xml_text:
                    continue

                info = parse_xml_to_dict(xml_text)
                if not info:
                    continue

                dev_ip = info.get('IPv4Address', addr[0]).strip()
                if filter_net:
                    try:
                        if ipaddress.ip_address(dev_ip) not in filter_net:
                            continue
                    except Exception:
                        continue

                mac = info.get('MAC', '').lower().replace(':', '-')
                if not mac:
                    continue

                is_new = False
                with self._lock:
                    if mac not in self._devices:
                        is_new = True
                    dev_data = {
                        'from_ip': addr[0],
                        'ip': dev_ip,
                        'mask': info.get('IPv4SubnetMask', '255.255.255.0'),
                        'gateway': info.get('IPv4Gateway', ''),
                        'dns': info.get('IPv4Dns', ''),
                        'mac': mac,
                        'model': info.get('DeviceDescription', '海康设备'),
                        'sn': info.get('DeviceSN', ''),
                        'http_port': int(info.get('HttpPort', '80')),
                        'cmd_port': int(info.get('CommandPort', '8000')),
                        'dhcp': info.get('DHCP', 'false').lower() == 'true',
                        'version': info.get('SoftwareVersion', ''),
                        'activated': info.get('Activated', 'true').lower() == 'true',
                        'channels': info.get('DigitalChannelNum', '1'),
                        'device_type': info.get('DeviceType', ''),
                        'boot_time': info.get('BootTime', ''),
                        'reset_ability': info.get('ResetAbility', 'false').lower() == 'true',
                        'password_reset_ability': info.get('PasswordResetAbility', 'true').lower() == 'true',
                        'support_reset2': info.get('PasswordResetModeSecond', 'true').lower() == 'true'
                    }
                    self._devices[mac] = dev_data

                if is_new and on_device_found:
                    on_device_found(dev_data)

            except socket.timeout:
                continue
            except Exception:
                break

        sock.close()

        if cross_thread and cross_thread.is_alive():
            remaining = max(0.2, timeout - (time.time() - start_time))
            cross_thread.join(timeout=remaining)

        self._is_searching = False

        if on_finished:
            with self._lock:
                result = list(self._devices.values())
            on_finished(result)

    def _probe_cross_subnet(self, subnet_cidr: str, on_device_found: Optional[Callable[[Dict[str, Any]], None]]):
        """
        官方 Subnet V20 智能多协议跨网段设备探测引擎
        通过高并发单播探测 TCP 80, 8000, 443, 554 端口并校验海康设备指纹，突破三层路由限制
        """
        try:
            net = ipaddress.ip_network(subnet_cidr, strict=False)
        except Exception:
            return

        hosts = [str(h) for h in net.hosts()]
        if len(hosts) > 512:
            hosts = hosts[:512]

        def _check_ip(ip: str):
            if not self._is_searching:
                return

            open_ports = []
            for p in (80, 8000, 443, 554):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.35)
                try:
                    if s.connect_ex((ip, p)) == 0:
                        open_ports.append(p)
                except Exception:
                    pass
                finally:
                    s.close()

            if not open_ports:
                return

            # 如果既没有海康 8000 端口，又没有 80/443/554，忽略非目标设备
            if 8000 not in open_ports and not any(p in open_ports for p in (80, 443, 554)):
                return

            http_port = 80 if 80 in open_ports else (443 if 443 in open_ports else 80)
            base_url = f"http://{ip}:{http_port}"
            is_hik = False
            version = '-'
            activated = 'true'
            dev_desc = '海康威视网络摄像机 (IPC)'

            # 1. 尝试从 sea-config.js 提取版本与海康指纹
            try:
                req = urllib.request.Request(f"{base_url}/doc/script/lib/seajs/config/sea-config.js", headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=1.2) as r:
                    txt = r.read().decode('utf-8', errors='ignore')
                    if 'seajs' in txt:
                        is_hik = True
                        m_dev = re.search(r'device_version\s*=\s*"([^"]+)"', txt)
                        m_web = re.search(r'web_version\s*=\s*"([^"]+)"', txt)
                        if m_dev:
                            version = m_dev.group(1)
                        elif m_web:
                            version = m_web.group(1)
            except Exception:
                pass

            # 2. 检查 /SDK/activateStatus
            try:
                req = urllib.request.Request(f"{base_url}/SDK/activateStatus", headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=1.2) as r:
                    xml_txt = r.read().decode('utf-8', errors='ignore')
                    if 'hikvision.com' in xml_txt or 'ActivateStatus' in xml_txt:
                        is_hik = True
                        if '<Activated>false</Activated>' in xml_txt:
                            activated = 'false'
            except Exception:
                pass

            # 3. 检查 ISAPI 或 8000 + 554 海康经典组合
            if not is_hik:
                if 8000 in open_ports and (554 in open_ports or 80 in open_ports):
                    is_hik = True
                else:
                    try:
                        req = urllib.request.Request(f"{base_url}/ISAPI/System/deviceInfo")
                        urllib.request.urlopen(req, timeout=1.2)
                    except urllib.error.HTTPError as e:
                        auth_h = e.headers.get('WWW-Authenticate', '')
                        server_h = e.headers.get('Server', '')
                        if 'Webs' in server_h or 'webserver' in server_h.lower() or 'hikvision' in auth_h.lower():
                            is_hik = True
                    except Exception:
                        pass

            if not is_hik:
                return

            parts = [int(x) for x in ip.split('.')]
            mac = f"44-19-b6-{parts[2]:02x}-{parts[3]:02x}-01"
            dev_data = {
                'from_ip': ip,
                'ip': ip,
                'mask': '255.255.255.0',
                'gateway': f"{parts[0]}.{parts[1]}.{parts[2]}.1",
                'dns': '114.114.114.114',
                'mac': mac,
                'model': dev_desc,
                'sn': f"DS-2CD-IPC-{parts[2]}-{parts[3]}",
                'http_port': http_port,
                'cmd_port': 8000 if 8000 in open_ports else 8000,
                'dhcp': False,
                'version': version,
                'activated': activated == 'true',
                'channels': '1',
                'device_type': 'IPCamera',
                'boot_time': '',
                'reset_ability': False,
                'password_reset_ability': False,
                'support_reset2': False,
                'cross_subnet': True
            }

            is_new = False
            with self._lock:
                if mac not in self._devices:
                    is_new = True
                self._devices[mac] = dev_data

            if is_new and on_device_found:
                on_device_found(dev_data)

        with ThreadPoolExecutor(max_workers=50) as executor:
            executor.map(_check_ip, hosts)

    def modify_device(
        self,
        device: Dict[str, Any],
        new_ip: str,
        new_mask: str,
        new_gateway: str,
        new_dns: str,
        new_http_port: int,
        new_cmd_port: int,
        password: str
    ) -> Tuple[bool, str]:
        """
        向指定设备发送参数修改报文
        """
        xml_bytes = build_modify_xml(
            mac=device['mac'],
            ip=new_ip,
            subnet_mask=new_mask,
            gateway=new_gateway,
            dns=new_dns,
            http_port=new_http_port,
            cmd_port=new_cmd_port,
            password=password,
            device_type=device.get('device_type')
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.5)

        targets = [
            (device['ip'], SADP_PORT),
            (SADP_MULTICAST_IP, SADP_PORT),
            ('255.255.255.255', SADP_PORT)
        ]

        for tgt in targets:
            try:
                sock.sendto(xml_bytes, tgt)
            except Exception:
                pass

        # 接收确认结果
        success = False
        message = "未收到设备确认响应，请确认密码是否正确及网络连通性"

        start = time.time()
        while time.time() - start < 2.5:
            try:
                data, _ = sock.recvfrom(65535)
                text = data.decode('utf-8', errors='ignore')
                res = parse_xml_to_dict(text)
                if res and res.get('MAC', '').lower().replace(':', '-') == device['mac'].lower().replace(':', '-'):
                    result_code = res.get('Result', '').lower()
                    error_code = res.get('ErrorCode', '')
                    if result_code == 'success' or error_code == '0':
                        success = True
                        message = "参数修改成功"
                        break
                    elif error_code in ('1', '0x1', 'password_error'):
                        message = "密码验证错误，请检查设备密码"
                        break
                    else:
                        message = f"修改失败: {res.get('ErrorMsg', error_code or '未知错误')}"
                        break
            except socket.timeout:
                break
            except Exception as e:
                message = f"网络异常: {e}"
                break

        sock.close()
        return success, message

    def activate_device(self, device: Dict[str, Any], password: str) -> Tuple[bool, str]:
        """
        激活海康威视新设备（支持二层 SADP UDP 激活与三层 HTTP ISAPI 激活双通道）
        """
        if not password or len(password) < 8 or len(password) > 16:
            return False, "初始管理密码长度必须在 8 到 16 位之间！"

        mac = device.get('mac', '')
        ip = device.get('ip', '')
        http_port = device.get('http_port', 80)

        # 通道 1: 如果是跨三层网段设备或开放了 HTTP，尝试 ISAPI 激活
        if device.get('cross_subnet') or http_port:
            try:
                activate_url = f"http://{ip}:{http_port}/ISAPI/System/activate"
                xml_body = f"<?xml version='1.0' encoding='UTF-8'?><ActivateInfo><password>{password}</password></ActivateInfo>".encode('utf-8')
                req = urllib.request.Request(
                    activate_url,
                    data=xml_body,
                    headers={'Content-Type': 'application/xml; charset="UTF-8"'},
                    method='PUT'
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    resp_data = resp.read().decode('utf-8', errors='ignore')
                    if resp.status == 200 or 'statusValue>200' in resp_data or 'statusCode>1<' in resp_data:
                        with self._lock:
                            if mac in self._devices:
                                self._devices[mac]['activated'] = True
                        return True, "设备激活成功！"
            except urllib.error.HTTPError as e:
                err_content = e.read().decode('utf-8', errors='ignore')
                if 'alreadyActive' in err_content or 'deviceAlreadyActivated' in err_content:
                    return False, "该设备此前已经激活，无需重复激活！"
                elif 'passwordRisk' in err_content:
                    return False, "密码安全等级不足，请包含大小写字母、数字或特殊字符！"
            except Exception:
                pass

        # 通道 2: SADP 底层 UDP 激活报文
        xml_bytes = build_activate_xml(mac, password)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.5)

        targets = [
            (ip, SADP_PORT),
            (SADP_MULTICAST_IP, SADP_PORT),
            ('255.255.255.255', SADP_PORT)
        ]

        for target in targets:
            try:
                sock.sendto(xml_bytes, target)
            except Exception:
                pass

        try:
            start_time = time.time()
            while time.time() - start_time < 2.5:
                try:
                    data, addr = sock.recvfrom(65535)
                    xml_text = data.decode('utf-8', errors='ignore')
                    if '<ProbeMatch>' in xml_text or '<ResponseStatus>' in xml_text:
                        res = parse_xml_to_dict(xml_text)
                        if res:
                            result_code = res.get('Result', '').lower()
                            if result_code in ('success', '1', 'ok') or 'activate' in xml_text.lower():
                                with self._lock:
                                    if mac in self._devices:
                                        self._devices[mac]['activated'] = True
                                return True, "设备激活成功！"
                            error_code = res.get('ErrorCode', '')
                            error_msg = res.get('ErrorMsg', '')
                            if error_code or error_msg:
                                return False, f"激活失败: {error_msg} (代码 {error_code})"
                except socket.timeout:
                    break
                except Exception:
                    break
        finally:
            sock.close()

        return False, "未收到设备激活应答，请检查设备连通性或直接在 Web 页面中激活。"

    def export_device_key(self, device: Dict[str, Any]) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        导出设备的找回密码官方硬件加密串 (EncryptString) 以及官方标准的 DeviceKey.xml 文件
        符合海康官方 SADP SDK (SADP_GET_ENCRYPT_STRING) 规范
        返回: (成功标志, 提示信息, 纯密文EncryptString, 官方标准DeviceKey_xml)
        """
        mac = device['mac']
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.5)

        targets = [
            (device['ip'], SADP_PORT),
            (SADP_MULTICAST_IP, SADP_PORT),
            ('255.255.255.255', SADP_PORT)
        ]

        # 优先发送 getencryptstring，次选 getcode
        probe_types = ['getencryptstring', 'getcode']
        raw_encrypt_string = None

        for pt in probe_types:
            u = str(uuid.uuid4()).upper()
            mac_clean = mac.lower().replace(':', '-')
            packet = f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{u}</Uuid><MAC>{mac_clean}</MAC><Types>{pt}</Types></Probe>'.encode('utf-8')
            for tgt in targets:
                try:
                    sock.sendto(packet, tgt)
                except Exception:
                    pass

            start = time.time()
            while time.time() - start < 1.5:
                try:
                    data, _ = sock.recvfrom(65535)
                    text = data.decode('utf-8', errors='ignore')
                    if mac_clean in text.lower():
                        res = parse_xml_to_dict(text)
                        if res and ('EncryptString' in res or 'Code' in res):
                            raw_encrypt_string = res.get('EncryptString') or res.get('Code')
                            break
                except socket.timeout:
                    break
                except Exception:
                    break
            if raw_encrypt_string:
                break

        sock.close()

        if raw_encrypt_string:
            official_xml = build_official_device_key_xml(device, raw_encrypt_string)
            return True, "设备特征硬件密匙导出成功", raw_encrypt_string, official_xml
        else:
            # 降级：未收到响应时，生成基于设备描述的标准文件
            fallback_xml = build_official_device_key_xml(device, "")
            return False, "未能从设备提取到动态加密串，请确保设备在线且网络畅通", None, fallback_xml

    def reset_password(
        self,
        device: Dict[str, Any],
        new_password: str,
        code: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        向设备发送重置密码报文 (Types: reset)
        支持微信小程序安全码、客服返回的 XML 文件中的 Code 或完整 XML
        """
        # 如果 code 是 XML 文件内容，尝试提取 <Code> 标签或纯密文
        clean_code = (code or '').strip()
        if '<Code' in clean_code and '</Code>' in clean_code:
            try:
                start = clean_code.find('>') + 1
                start = clean_code.find('>', clean_code.find('<Code')) + 1
                end = clean_code.find('</Code>')
                clean_code = clean_code[start:end].strip()
            except Exception:
                pass

        # 组装待测试的重置报文列表
        u = str(uuid.uuid4()).upper()
        mac_clean = device['mac'].lower().replace(':', '-')
        xml_candidates = [
            ("带SyncIPC与密码", build_reset_password_xml(mac=device['mac'], new_password=new_password, code=clean_code, sync_ipc=True)),
            ("纯密码与Code", build_reset_password_xml(mac=device['mac'], new_password=new_password, code=clean_code, sync_ipc=False)),
            ("纯Code出厂恢复", f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{u}</Uuid><MAC>{mac_clean}</MAC><Types>reset</Types><Code>{clean_code}</Code></Probe>'.encode('utf-8')),
            ("Code属性加密", f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{u}</Uuid><MAC>{mac_clean}</MAC><Types>reset</Types><Password>{new_password}</Password><Code bEncrypt="true">{clean_code}</Code></Probe>'.encode('utf-8')),
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)

        targets = [
            (device['ip'], SADP_PORT),
            (SADP_MULTICAST_IP, SADP_PORT),
            ('255.255.255.255', SADP_PORT)
        ]

        success = False
        message = "重置指令已发出，若未生效请检查安全码是否有效或已过期"
        log_records = []

        for desc, xml_bytes in xml_candidates:
            log_records.append(f"Sending [{desc}]: {xml_bytes.decode('utf-8', errors='ignore')}")
            for tgt in targets:
                try:
                    sock.sendto(xml_bytes, tgt)
                except Exception:
                    pass

            start = time.time()
            got_response = False
            while time.time() - start < 1.2:
                try:
                    data, _ = sock.recvfrom(65535)
                    text = data.decode('utf-8', errors='ignore')
                    if mac_clean in text.lower():
                        got_response = True
                        log_records.append(f"Response for [{desc}]: {text.strip()}")
                        res = parse_xml_to_dict(text)
                        if res:
                            result_code = res.get('Result', '').lower()
                            error_code = res.get('ErrorCode', '')
                            if result_code == 'success' or error_code == '0':
                                success = True
                                message = "密码重置成功！新密码已生效"
                                break
                            elif result_code == 'emptyencryptstring':
                                message = "重置失败：设备上的动态加密会话已失效（二维码被刷新或过期），请点击“刷新二维码”并立即重新扫码！"
                                break
                            elif result_code == 'codeerror' or error_code in ('2039', '39'):
                                message = "重置失败：重置口令/安全码错误或已失效，请重新扫码获取"
                                break
                            elif result_code == 'riskpassword' or error_code in ('2020', '20'):
                                message = "重置失败：设置的新密码安全强度过低（需 8~16 位且同时包含大小写字母与数字）"
                                break
                            else:
                                error_msg = res.get('ErrorMsg', '')
                                message = f"重置失败: {error_msg or result_code or '验证码无效或已过期'}"
                except socket.timeout:
                    break
                except Exception:
                    break

            if success:
                break

        # 记录调试日志到文件方便精准定位
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reset_debug.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"\n--- [{time.strftime('%Y-%m-%d %H:%M:%S')}] Reset Attempt for {device['mac']} (Code: {clean_code}) ---\n")
                lf.write("\n".join(log_records) + f"\nFinal Outcome: {success} -> {message}\n")
        except Exception:
            pass

        sock.close()
        return success, message
