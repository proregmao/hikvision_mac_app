"""
实时视频流与 PTZ 控制模块单元测试
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
    from hikvision_mac_app.core.video_stream import (
        generate_rtsp_url,
        detect_installed_players,
        control_ptz
    )
except ImportError:
    from core.video_stream import (
        generate_rtsp_url,
        detect_installed_players,
        control_ptz
    )

class TestVideoStream(unittest.TestCase):
    def test_rtsp_url_standard(self):
        url = generate_rtsp_url(
            ip="192.168.1.64",
            port=554,
            username="admin",
            password="password123",
            channel=1,
            stream_type=1
        )
        self.assertEqual(url, "rtsp://admin:password123@192.168.1.64/Streaming/Channels/101")

    def test_rtsp_url_substream(self):
        url = generate_rtsp_url(
            ip="192.168.220.50",
            port=554,
            username="admin",
            password="pwd",
            channel=2,
            stream_type=2
        )
        self.assertEqual(url, "rtsp://admin:pwd@192.168.220.50/Streaming/Channels/202")

    def test_rtsp_url_special_characters(self):
        url = generate_rtsp_url(
            ip="10.0.0.10",
            port=10554,
            username="admin@hk",
            password="pass#word:123@",
            channel=1,
            stream_type=1
        )
        self.assertTrue("pass%23word%3A123%40" in url)
        self.assertTrue(":10554" in url)

    def test_detect_players(self):
        players = detect_installed_players()
        self.assertIsInstance(players, list)

    def test_ptz_invalid_action(self):
        ok, msg = control_ptz(ip="127.0.0.1", action="INVALID_ACTION")
        self.assertFalse(ok)
        self.assertTrue("不支持" in msg)

if __name__ == '__main__':
    unittest.main()
