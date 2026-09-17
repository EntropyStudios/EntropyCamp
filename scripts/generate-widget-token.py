#!/usr/bin/env python3
"""Idempotently create the private iPhone widget access token."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from widget_service import ensure_widget_token  # noqa: E402


token_path = ROOT / "private" / "widget" / "access-token"
existed = token_path.exists()
ensure_widget_token(token_path)
print(f"小组件令牌{'已存在' if existed else '已生成'}：{token_path}")
