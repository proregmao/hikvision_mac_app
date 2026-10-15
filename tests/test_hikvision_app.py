"""
海康威视协议与核心引擎单元测试
"""

import unittest
import sys
import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(APP_DIR)
for p in [APP_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from hikvision_mac_app.core.sadp_protocol import (
        build_probe_xml,
        parse_xml_to_dict,
        build_modify_xml,
        build_export_key_xml,
        build_reset_password_xml,
        build_activate_xml,
        calculate_classic_recovery_code
    )
    from hikvision_mac_app.core.scanner import DeviceScanner
except ImportError:
    from core.sadp_protocol import (
        build_probe_xml,
        parse_xml_to_dict,
        build_modify_xml,
        build_export_key_xml,
        build_reset_password_xml,
        build_activate_xml,
        calculate_classic_recovery_code
    )
    from core.scanner import DeviceScanner

class TestHikvisionCore(unittest.TestCase):
    def test_activate_xml(self):
        act_bytes = build_activate_xml("ac-b9-2f-22-71-aa", "Admin12345")
        self.assertIn(b'<Types>activate</Types>', act_bytes)
        self.assertIn(b'<MAC>ac-b9-2f-22-71-aa</MAC>', act_bytes)
        self.assertIn(b'<Password>Admin12345</Password>', act_bytes)
    def test_probe_xml(self):
        data = build_probe_xml()
        self.assertIn(b'<Types>inquiry</Types>', data)
        self.assertIn(b'<Uuid>', data)

    def test_parse_xml(self):
        mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <ProbeMatch>
            <DeviceDescription>iDS-6704NX/FA-Q</DeviceDescription>
            <IPv4Address>192.168.110.187</IPv4Address>
            <MAC>ac-b9-2f-22-71-aa</MAC>
            <HttpPort>80</HttpPort>
            <CommandPort>8000</CommandPort>
        </ProbeMatch>"""
        res = parse_xml_to_dict(mock_xml)
        self.assertIsNotNone(res)
        self.assertEqual(res['DeviceDescription'], 'iDS-6704NX/FA-Q')
        self.assertEqual(res['IPv4Address'], '192.168.110.187')
        self.assertEqual(res['MAC'], 'ac-b9-2f-22-71-aa')
        self.assertEqual(res['HttpPort'], '80')

    def test_modify_xml(self):
        xml_bytes = build_modify_xml(
            mac="ac:b9:2f:22:71:aa",
            ip="192.168.110.200",
            subnet_mask="255.255.255.0",
            gateway="192.168.110.254",
            dns="114.114.114.114",
            http_port=80,
            cmd_port=8000,
            password="Admin12345Password"
        )
        self.assertIn(b'<IPv4Address>192.168.110.200</IPv4Address>', xml_bytes)
        self.assertIn(b'<MAC>ac-b9-2f-22-71-aa</MAC>', xml_bytes)
        self.assertIn(b'<Password>Admin12345Password</Password>', xml_bytes)

    def test_export_and_reset_xml(self):
        export_bytes = build_export_key_xml("ac-b9-2f-22-71-aa")
        self.assertIn(b'<Types>getencryptstring</Types>', export_bytes)
        self.assertIn(b'<MAC>ac-b9-2f-22-71-aa</MAC>', export_bytes)

        reset_bytes = build_reset_password_xml(
            mac="ac-b9-2f-22-71-aa",
            new_password="NewSecurePassword123",
            code="ABCDEF12"
        )
        self.assertIn(b'<Types>reset</Types>', reset_bytes)
        self.assertIn(b'<Code>ABCDEF12</Code>', reset_bytes)
        self.assertIn(b'<Password>NewSecurePassword123</Password>', reset_bytes)

    def test_recovery_code(self):
        code = calculate_classic_recovery_code("DS-2CD2125FD-IWS20171108", 2026, 10, 15)
        self.assertTrue(len(code) >= 8)
        self.assertTrue(code.isalnum())

    def test_scanner_local_ip(self):
        scanner = DeviceScanner()
        ip = scanner.get_local_ip()
        self.assertTrue(len(ip.split('.')) == 4)

    def test_cross_subnet_detection(self):
        scanner = DeviceScanner()
        found = []
        scanner.search(custom_subnet="192.168.220.50/32", timeout=1.5, on_device_found=lambda d: found.append(d))
        import time
        time.sleep(1.8)
        self.assertTrue(len(found) >= 1)
        for dev in found:
            self.assertTrue(dev['ip'].startswith('192.168.220.'))
        self.assertEqual(found[0]['ip'], '192.168.220.50')
        self.assertTrue(found[0]['cross_subnet'])
        self.assertEqual(found[0]['http_port'], 80)

if __name__ == '__main__':
    unittest.main()
