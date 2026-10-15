"""
macOS 现代化 UI 主题与色彩样式配置
"""

import tkinter as tk
from tkinter import ttk

# 色彩规范
COLOR_BG = "#F5F6F8"
COLOR_CARD = "#FFFFFF"
COLOR_PRIMARY = "#007AFF"       # 苹果蓝
COLOR_PRIMARY_HOVER = "#0062CC"
COLOR_SUCCESS = "#34C759"       # 翡翠绿
COLOR_WARNING = "#FF9500"       # 琥珀橙
COLOR_DANGER = "#FF3B30"        # 珊瑚红
COLOR_TEXT_PRIMARY = "#1C1C1E"
COLOR_TEXT_SECONDARY = "#8E8E93"
COLOR_BORDER = "#D1D1D6"
COLOR_ROW_ALT = "#F9F9FB"

FONT_MAIN = ("-apple-system", 12)
FONT_BOLD = ("-apple-system", 12, "bold")
FONT_TITLE = ("-apple-system", 14, "bold")
FONT_CODE = ("Menlo", 11)

def apply_theme(root: tk.Tk):
    """应用 macOS 原生与 ttk 现代美化样式"""
    root.configure(bg=COLOR_BG)
    style = ttk.Style()
    
    # 尝试使用 macOS 系统的 'aqua' 主题
    available_themes = style.theme_names()
    if 'aqua' in available_themes:
        style.theme_use('aqua')
    elif 'clam' in available_themes:
        style.theme_use('clam')

    # 配置 Treeview 样式
    style.configure(
        "Treeview",
        background=COLOR_CARD,
        foreground=COLOR_TEXT_PRIMARY,
        fieldbackground=COLOR_CARD,
        rowheight=28,
        font=FONT_MAIN
    )
    style.configure(
        "Treeview.Heading",
        font=FONT_BOLD,
        background=COLOR_BG,
        foreground=COLOR_TEXT_PRIMARY
    )
    style.map(
        "Treeview",
        background=[('selected', COLOR_PRIMARY)],
        foreground=[('selected', '#FFFFFF')]
    )

    # 按钮与标签
    style.configure("TLabel", background=COLOR_BG, font=FONT_MAIN, foreground=COLOR_TEXT_PRIMARY)
    style.configure("Card.TFrame", background=COLOR_CARD)
    style.configure("Toolbar.TFrame", background=COLOR_BG)
