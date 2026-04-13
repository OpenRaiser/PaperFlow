#!/usr/bin/env python3
"""
快速测试脚本 - 显示如何获取 chat_id

方法：
1. 在飞书开放平台查看 webhook 日志
2. 或者在飞书群中发送消息后，查看此脚本解析的事件
"""

import json
import os

# 示例：从飞书事件中提取 chat_id
sample_event = {
    "header": {
        "event_type": "im.message.receive_v1"
    },
    "event": {
        "message": {
            "chat_id": "oc_xxxxxxxxxx",  # ← 这就是你要找的 chat_id
            "msg_type": "text",
            "content": "{\"text\":\"测试消息\"}"
        },
        "sender": {
            "sender_type": "personal",
            "sender_id": {
                "open_id": "ou_xxxxxxxxxx",
                "user_id": "xxxxxxxxxx"
            }
        }
    }
}

print("="*60)
print("📋 获取 chat_id 的方法")
print("="*60)
print()
print("方法 1：从 webhook 日志中获取（推荐）")
print("-" * 60)
print("1. 确保 webhook 服务器正在运行")
print("2. 在飞书群里发送一条消息")
print("3. 查看终端输出的日志，会显示：")
print("   chat_id: oc_xxxxxxxxxx")
print()
print("方法 2：从飞书开放平台后台查看")
print("-" * 60)
print("1. 打开 https://open.feishu.cn/")
print("2. 进入你的应用 → 事件订阅")
print("3. 查看事件历史，找到最近的收信事件")
print("4. 从事件 JSON 中找到 event.message.chat_id")
print()
print("方法 3：使用飞书 API")
print("-" * 60)
print("发送 GET 请求：")
print("  https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}")
print()
print("="*60)
print()
print("获取到 chat_id 后，更新 data/roles.json：")
print()
print(json.dumps({
    "roles": {
        "rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_xxx_rolea_chat_id"},
        "roleb": {"user_id": "user_roleb", "feishu_chat_id": "oc_xxx_roleb_chat_id"},
        "rolec": {"user_id": "user_rolec", "feishu_chat_id": "oc_xxx_rolec_chat_id"},
        "roled": {"user_id": "user_roled", "feishu_chat_id": "oc_xxx_roled_chat_id"}
    },
    "current_role": "rolea"
}, indent=2, ensure_ascii=False))
