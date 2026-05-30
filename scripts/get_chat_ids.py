#!/usr/bin/env python3
"""
获取飞书对话框 chat_id 的辅助脚本

使用方法：
1. 在飞书上打开 PaperFlow Bot 对话框
2. 发送任意消息
3. 查看此脚本输出的 chat_id
"""

import sys
import os
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any
from urllib.parse import urlparse, parse_qs
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("chat_id_finder")


class ChatIdFinderHandler(BaseHTTPRequestHandler):
    """简单的 HTTP 处理器，用于捕获飞书事件的 chat_id"""

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            event = json.loads(body.decode('utf-8'))
            event_type = event.get("type", "")

            # 跳过 url_verification
            if event_type == "url_verification":
                challenge = event.get("challenge", "")
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"challenge": challenge}).encode('utf-8'))
                return

            # 解析事件
            header = event.get("header", {})
            event_type = header.get("event_type", "")

            if event_type == "im.message.receive_v1":
                event_data = event.get("event", {})
                message = event_data.get("message", {})
                sender = event_data.get("sender", {})

                chat_id = message.get("chat_id", "")
                msg_type = message.get("msg_type", "")
                content_raw = message.get("content", "{}")

                # 解析消息内容
                try:
                    content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
                except json.JSONDecodeError:
                    content = {"text": content_raw}

                text = content.get("text", "")
                sender_type = sender.get("sender_type", "")
                open_id = sender.get("sender_id", {}).get("open_id", "")
                user_id = sender.get("sender_id", {}).get("user_id", "")

                # 跳过 bot 消息
                if sender_type == "app_bot":
                    return

                # 打印 chat_id 信息
                print("\n" + "="*60)
                print(f"📱 收到消息！")
                print("="*60)
                print(f"  chat_id:    {chat_id}")
                print(f"  open_id:    {open_id}")
                print(f"  user_id:    {user_id or '(空)'}")
                print(f"  sender_type:{sender_type}")
                print(f"  msg_type:   {msg_type}")
                print(f"  消息内容：   {text[:50]}...")
                print("="*60)
                print("\n👉 请将上面的 chat_id 复制到 roles.json 中对应的角色下")
                print("   例如：\"rolea\": { \"feishu_chat_id\": \"" + chat_id + "\" }\n")

                # 发送响应
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            else:
                # 其他事件类型
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ignored", "event_type": event_type}).encode('utf-8'))

        except Exception as e:
            logger.error(f"Error processing event: {e}")
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        """健康检查"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "healthy", "service": "chat_id_finder"}).encode('utf-8'))

    def log_message(self, format, *args):
        logger.info("%s - %s" % (self.address_string(), format % args))


def main():
    port = 9999
    print("="*60)
    print("🔍 Chat ID Finder - 飞书对话框 ID 获取工具")
    print("="*60)
    print()
    print("使用步骤：")
    print("1. 保持此脚本运行")
    print("2. 在飞书开放平台将事件订阅 URL 临时改为：http://localhost:9999")
    print("   或者使用 ngrok：ngrok http 9999，然后将 ngrok URL 配置到飞书")
    print("3. 在飞书上给 PaperFlow Bot 发送任意消息")
    print("4. 此脚本会打印出 chat_id")
    print("5. 将 chat_id 复制到 data/roles.json 中对应角色的 feishu_chat_id 字段")
    print()
    print("按 Ctrl+C 停止")
    print("="*60)
    print()

    server = HTTPServer(('', port), ChatIdFinderHandler)
    logger.info(f"Starting chat_id finder server on port {port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
