#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
token_path="$root/private/widget/access-token"

if [ ! -s "$token_path" ]; then
  echo "没有找到小组件令牌，请先运行 scripts/generate-widget-token.py" >&2
  exit 1
fi
if ! command -v xsel >/dev/null 2>&1; then
  echo "系统未安装 xsel，无法安全复制到剪贴板" >&2
  exit 1
fi

tr -d '\r\n' < "$token_path" | xsel --clipboard --input
echo "小组件令牌已复制到本机剪贴板；程序未打印令牌内容。"
