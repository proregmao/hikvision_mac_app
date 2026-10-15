"""
海康威视 SADP (Search Active Devices Protocol) 协议封装模块
提供报文构建、响应解析、参数修改报文、秘钥导出及经典安全码算法。
"""

import uuid
import hashlib
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple, Any

SADP_MULTICAST_IP = "239.255.255.250"
SADP_PORT = 37020

def generate_uuid() -> str:
    """生成大写的标准 UUID"""
    return str(uuid.uuid4()).upper()

def build_probe_xml() -> bytes:
    """构建设备搜索探针报文"""
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Probe><Uuid>{generate_uuid()}</Uuid><Types>inquiry</Types></Probe>'
    )
    return xml.encode('utf-8')

def parse_xml_to_dict(xml_str: str) -> Optional[Dict[str, str]]:
    """将 XML 字符串解析为扁平字典"""
    try:
        root = ET.fromstring(xml_str.strip())
        res = {}
        for elem in root.iter():
            if elem.text and elem.text.strip():
                res[elem.tag] = elem.text.strip()
        return res
    except Exception:
        return None

def build_modify_xml(
    mac: str,
    ip: str,
    subnet_mask: str,
    gateway: str,
    dns: str,
    http_port: int,
    cmd_port: int,
    password: str,
    device_type: Optional[str] = None
) -> bytes:
    """
    构建修改网络参数的 XML 报文
    """
    # 格式化 MAC 地址为标准小写带短划线或原样
    mac_clean = mac.lower().replace(':', '-')
    
    xml_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Probe>',
        f'<Uuid>{generate_uuid()}</Uuid>',
        '<Types>inquiry</Types>',
        f'<MAC>{mac_clean}</MAC>',
        f'<IPv4Address>{ip}</IPv4Address>',
        f'<IPv4SubnetMask>{subnet_mask}</IPv4SubnetMask>',
        f'<IPv4Gateway>{gateway}</IPv4Gateway>',
        f'<IPv4Dns>{dns}</IPv4Dns>',
        f'<HttpPort>{http_port}</HttpPort>',
        f'<CommandPort>{cmd_port}</CommandPort>',
        f'<Password>{password}</Password>'
    ]
    if device_type:
        xml_parts.append(f'<DeviceType>{device_type}</DeviceType>')
    xml_parts.append('</Probe>')
    
    return "".join(xml_parts).encode('utf-8')

def build_export_key_xml(mac: str) -> bytes:
    """构建官方 SADP 获取加密串（getencryptstring）的报文"""
    mac_clean = mac.lower().replace(':', '-')
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Probe><Uuid>{generate_uuid()}</Uuid>'
        f'<MAC>{mac_clean}</MAC>'
        f'<Types>getencryptstring</Types>'
        '</Probe>'
    )
    return xml.encode('utf-8')

def build_get_code_xml(mac: str) -> bytes:
    """构建官方 SADP 获取设备码（getcode）的报文"""
    mac_clean = mac.lower().replace(':', '-')
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Probe><Uuid>{generate_uuid()}</Uuid>'
        f'<MAC>{mac_clean}</MAC>'
        f'<Types>getcode</Types>'
        '</Probe>'
    )
    return xml.encode('utf-8')

def build_reset_password_xml(
    mac: str,
    new_password: str,
    code: Optional[str] = None,
    sync_ipc: bool = True
) -> bytes:
    """
    构建符合海康官方 SADP SDK 规范的重置密码报文 (Types: reset)
    严格对齐 libsadp.so:
    <Probe><Uuid>%s</Uuid><MAC>%s</MAC><Types>reset</Types><Password>%s</Password><SyncIPCPassword>true</SyncIPCPassword><Code>%s</Code></Probe>
    """
    mac_clean = mac.lower().replace(':', '-')
    code_val = (code or '').strip()
    sync_node = '<SyncIPCPassword>true</SyncIPCPassword>' if sync_ipc else ''
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Probe>'
        f'<Uuid>{generate_uuid()}</Uuid>'
        f'<MAC>{mac_clean}</MAC>'
        '<Types>reset</Types>'
        f'<Password>{new_password}</Password>'
        f'{sync_node}'
        f'<Code>{code_val}</Code>'
        '</Probe>'
    )
    return xml.encode('utf-8')

def build_official_device_key_xml(device: dict, encrypt_string: str) -> str:
    """
    生成符合海康官方 SADP 规范的 DeviceKey.xml 文件
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<DeviceKey>\n'
        f'  <DeviceDescription>{device.get("model", "")}</DeviceDescription>\n'
        f'  <DeviceSN>{device.get("sn", "")}</DeviceSN>\n'
        f'  <MAC>{device.get("mac", "").lower()}</MAC>\n'
        f'  <IPv4Address>{device.get("ip", "")}</IPv4Address>\n'
        f'  <SoftwareVersion>{device.get("version", "")}</SoftwareVersion>\n'
        f'  <BootTime>{device.get("boot_time", "")}</BootTime>\n'
        f'  <EncryptString>{encrypt_string}</EncryptString>\n'
        '</DeviceKey>\n'
    )

def _rshift(val: int, n: int) -> int:
    return (val % 0x100000000) >> n

def _char_shift(char: str) -> str:
    c = ord(char)
    shifts = {
        range(0, 51): 33,
        range(51, 53): 62,
        range(53, 55): 47,
        range(55, 57): 66
    }
    for r, value in shifts.items():
        if c in r:
            return chr(c + value)
    return char

def calculate_classic_recovery_code(serial: str, year: int, month: int, day: int) -> str:
    """
    海康威视官方经典设备出厂临时超级恢复码算法 (Magic Code Generator)
    基于设备真实序列号（自动剔除型号前缀）与当前日期精确计算。
    """
    clean_serial = serial.strip()
    # 如果包含型号前缀（如 DS-2CD... 或 iDS-6704...），尝试剥离型号前缀提取后段数字与字母串
    if clean_serial.startswith("DS-") or clean_serial.startswith("iDS-"):
        # 寻找紧接在型号后面的有效数字串（通常从 20xx 年份开始）
        for year_prefix in ("201", "202", "200"):
            pos = clean_serial.find(year_prefix)
            if pos != -1:
                clean_serial = clean_serial[pos:]
                break

    date_str = f"{year}{month:02d}{day:02d}"
    seed = clean_serial + date_str

    magic_number = sum(ord(ch) * idx ^ idx for idx, ch in enumerate(seed, 1))
    magic_number *= 1751873395
    magic_number = _rshift(magic_number, 0)
    recovery_code = ''.join(_char_shift(digit) for digit in str(magic_number))
    return recovery_code

def build_activate_xml(mac: str, password: str) -> bytes:
    """
    构建海康威视设备激活报文 (SADP Activate)
    """
    mac_clean = mac.lower().replace(':', '-')
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Probe>'
        f'<Uuid>{generate_uuid()}</Uuid>'
        '<Types>activate</Types>'
        f'<MAC>{mac_clean}</MAC>'
        f'<Password>{password}</Password>'
        '</Probe>'
    )
    return xml.encode('utf-8')


