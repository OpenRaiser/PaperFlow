# Feishu Reporter Skill

## 职责

飞书交互：封装飞书 CLI，发送文本消息、卡片消息，创建飞书文档。

## 环境准备

### 安装飞书 CLI

```bash
# 安装 lark suite cli
pip install lark-cli

# 或者从源码安装
git clone https://github.com/larksuite/cli.git
cd cli && pip install -e .
```

### 配置认证

```bash
# 配置飞书应用凭证
lark config set app_id "cli_xxxxxxxxxxxxx"
lark config set app_secret "xxxxxxxxxxxxxxxxxxxxx"

# 验证配置
lark auth check
```

## API

### 发送消息

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `send_text(user_id, text)` | 接收者 ID, 文本内容 | message_id | 发送文本消息 |
| `send_card(user_id, card_json)` | 接收者 ID, 卡片内容 | message_id | 发送卡片消息 |
| `send_to_chat(chat_id, content, content_type)` | 群聊 ID, 内容，类型 | message_id | 发送到群聊 |

### 文档操作

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `create_doc(title, content)` | 标题，内容 | doc_url | 创建飞书文档 |
| `create_doc_in_folder(folder_id, title, content)` | 文件夹 ID, 标题，内容 | doc_url | 在指定文件夹创建文档 |
| `update_doc(doc_id, content)` | 文档 ID, 内容 | success | 更新文档内容 |
| `get_doc(doc_id)` | 文档 ID | doc_content | 获取文档内容 |

## 消息模板

### 每日推送卡片

```json
{
  "config": {
    "wide_screen_mode": true
  },
  "elements": [
    {
      "tag": "header",
      "text": {
        "content": "📰 今日论文 | 04-21 | 抓取 312 篇 → 筛后 47 篇",
        "tag": "plain_text"
      }
    },
    {
      "tag": "div",
      "text": {
        "content": "**━━━ 🔒 必读清单命中（5 篇）━━━**\n01 AlQuraishi — Geometric Pretraining for Protein Complexes\n02 Jian Tang — Scaling Molecular Generation with Flow Matching\n...",
        "tag": "lark_md"
      }
    },
    {
      "tag": "action",
      "actions": [
        {
          "tag": "button",
          "text": {
            "content": "查看完整清单",
            "tag": "plain_text"
          },
          "url": "https://example.feishu.cn/docx/xxxxx"
        }
      ]
    }
  ]
}
```

### 画像确认卡片

```json
{
  "config": {
    "wide_screen_mode": true
  },
  "elements": [
    {
      "tag": "header",
      "text": {
        "content": "📋 你的学术画像（v0.1 - 冷启动）",
        "tag": "plain_text"
      }
    },
    {
      "tag": "div",
      "text": {
        "content": "**━━━ 核心方向 ━━━**\nGUI Agent [权重：0.70]\nOptimizer/训练方法 [权重：0.60]\n...",
        "tag": "lark_md"
      }
    }
  ]
}
```

### 精读报告完成通知

```json
{
  "config": {
    "wide_screen_mode": true
  },
  "elements": [
    {
      "tag": "header",
      "text": {
        "content": "📄 精读报告已完成",
        "tag": "plain_text"
      }
    },
    {
      "tag": "div",
      "text": {
        "content": "**[论文标题]**\n\n链接：https://example.feishu.cn/docx/xxxxx\n\n预计阅读时间：5-8 分钟",
        "tag": "lark_md"
      }
    },
    {
      "tag": "action",
      "actions": [
        {
          "tag": "button",
          "text": {
            "content": "打开文档",
            "tag": "plain_text"
          },
          "url": "https://example.feishu.cn/docx/xxxxx",
          "type": "primary"
        }
      ]
    }
  ]
}
```

## 脚本实现 (scripts/feishu_cli_wrapper.sh)

```bash
#!/bin/bash
#
# Feishu CLI Wrapper for SciTaste
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../.env"

# Load environment variables
if [ -f "$CONFIG_FILE" ]; then
    export $(cat "$CONFIG_FILE" | grep -v '^#' | xargs)
fi

# Send text message
send_text() {
    local user_id="$1"
    local text="$2"
    
    lark im message send --user-id "$user_id" --text "$text"
}

# Send card message
send_card() {
    local user_id="$1"
    local card_file="$2"
    
    lark im message send --user-id "$user_id" --interactive "$(<"$card_file")"
}

# Create doc
create_doc() {
    local title="$1"
    local content="$2"
    local folder_id="${3:-}"
    
    if [ -n "$folder_id" ]; then
        lark docx create --title "$title" --folder "$folder_id" --content "$content"
    else
        lark docx create --title "$title" --content "$content"
    fi
}

# Get user info
get_user_info() {
    local user_id="$1"
    
    lark contact user get --user-id "$user_id"
}

# Parse command
case "$1" in
    send_text)
        send_text "$2" "$3"
        ;;
    send_card)
        send_card "$2" "$3"
        ;;
    create_doc)
        create_doc "$2" "$3" "$4"
        ;;
    get_user_info)
        get_user_info "$2"
        ;;
    *)
        echo "Usage: $0 {send_text|send_card|create_doc|get_user_info}"
        exit 1
        ;;
esac
```

## Python 封装 (可选)

```python
#!/usr/bin/env python3
"""
Feishu CLI Python Wrapper
"""

import subprocess
import json
from pathlib import Path

FEISHU_CLI = "lark"

def run_command(args):
    """运行飞书 CLI 命令"""
    result = subprocess.run(
        [FEISHU_CLI] + args,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"Feishu CLI error: {result.stderr}")
    return result.stdout

def send_text(user_id, text):
    """发送文本消息"""
    output = run_command([
        "im", "message", "send",
        "--user-id", user_id,
        "--text", text
    ])
    return json.loads(output)

def send_card(user_id, card_json):
    """发送卡片消息"""
    card_str = json.dumps(card_json) if isinstance(card_json, dict) else card_json
    output = run_command([
        "im", "message", "send",
        "--user-id", user_id,
        "--interactive", card_str
    ])
    return json.loads(output)

def create_doc(title, content, folder_id=None):
    """创建飞书文档"""
    args = ["docx", "create", "--title", title, "--content", content]
    if folder_id:
        args.extend(["--folder", folder_id])
    output = run_command(args)
    return json.loads(output)

# ... 其他函数
```

## 注意事项

1. **认证配置**：确保飞书 CLI 已正确配置凭证
2. **消息频率**：避免短时间内发送过多消息（限制：100 条/分钟）
3. **卡片大小**：卡片消息不超过 32KB
4. **文档权限**：创建的文档默认对应用可见，需要共享时显式设置
