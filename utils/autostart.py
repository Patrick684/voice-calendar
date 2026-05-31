"""开机自启管理模块 - 通过 Windows 注册表管理自动启动"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 注册表路径
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "VoiceCalendar"


def get_app_start_command() -> str:
    """获取应用的启动命令

    Returns:
        可用于注册表的启动命令字符串
    """
    # 如果是打包后的 .exe
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    # 开发模式：python + 脚本路径
    main_script = Path(__file__).parent.parent / "main.py"
    return f'"{sys.executable}" "{main_script}"'


def is_autostart_enabled() -> bool:
    """检查是否已设置开机自启

    Returns:
        是否已启用自启
    """
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REG_PATH,
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enable: bool) -> bool:
    """设置或取消开机自启

    Args:
        enable: True 启用，False 禁用

    Returns:
        操作是否成功
    """
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REG_PATH,
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enable:
                cmd = get_app_start_command()
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
                logger.info(f"已启用开机自启: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                    logger.info("已禁用开机自启")
                except FileNotFoundError:
                    pass  # 本来就没设置
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"设置开机自启失败: {e}")
        return False
