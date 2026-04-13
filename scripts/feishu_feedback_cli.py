#!/usr/bin/env python3
"""
飞书反馈处理器 - 半自动模式

使用方式：
1. 从飞书复制用户的回复（如 "1 2 4 6"）
2. 运行此脚本，粘贴回复
3. 脚本自动调用 feedback-agent 处理
"""

import sys
import os

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用 importlib 导入带连字符的模块
import importlib
import json
from datetime import datetime

# 导入 feedback-agent
feedback_agent = importlib.import_module("agents.feedback-agent.main")
parse_user_reply = feedback_agent.parse_user_reply
process_feedback = feedback_agent.process_feedback

# 导入数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile


def load_today_push() -> list:
    """从今日推送文件加载论文列表"""
    import glob

    # 查找今天的推送文件
    today = datetime.now().strftime("%Y-%m-%d")
    push_files = glob.glob("test_push*.txt")

    if not push_files:
        print("未找到推送文件，请先运行 daily-push")
        return []

    # 读取最新的推送文件
    latest_file = max(push_files, key=os.path.getmtime)
    print(f"读取推送文件：{latest_file}")

    papers = []
    with open(latest_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 匹配格式：01. 2604.07258v1: 标题
            import re
            match = re.match(r'^\s*(\d+)\.\s*([\w\.]+):\s*(.+)$', line)
            if match:
                num = int(match.group(1))
                arxiv_id = match.group(2)
                title = match.group(3)
                papers.append({
                    "id": num,
                    "arxiv_id": arxiv_id,
                    "title": title
                })

    return papers


def main():
    print("=" * 60)
    print("飞书反馈处理器 - 半自动模式")
    print("=" * 60)
    print()

    # 1. 获取用户 ID
    user_id = input("用户 ID [默认：user_001]: ").strip() or "user_001"

    # 2. 加载今日推送
    print("\n加载今日推送...")
    papers = load_today_push()

    if not papers:
        print("未找到论文数据，退出")
        return

    print(f"加载了 {len(papers)} 篇论文")

    # 3. 循环处理反馈
    print("\n" + "-" * 60)
    print("请从飞书复制用户回复，粘贴到下方（输入 q 退出）：")
    print("支持格式：1 2 4 6 | 1-5 6 9 | 1,2,4,6")
    print("-" * 60)

    while True:
        print()
        reply = input("回复：").strip()

        if reply.lower() in ('q', 'quit', 'exit'):
            print("退出")
            break

        if not reply:
            continue

        # 解析回复
        selected = parse_user_reply(reply)

        if not selected:
            print("未识别到有效编号，请重新输入")
            continue

        print(f"选中论文编号：{sorted(selected)}")

        # 处理反馈
        push_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        result = process_feedback(
            user_id=user_id,
            push_id=push_id,
            reply=reply,
            papers=papers,
            feishu_user_id=None  # 不发送飞书确认
        )

        print(f"\n处理结果:")
        print(f"  选中：{result.get('selected_count', 0)} 篇")
        print(f"  跳过：{result.get('skipped_count', 0)} 篇")
        print(f"  选择率：{result.get('selection_rate', 0):.1%}")

        # 显示画像更新摘要
        profile = get_profile(user_id)
        if profile:
            history = profile.get('reading_history', [])
            print(f"  阅读历史：{len(history)} 条")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断退出")
    except Exception as e:
        print(f"\n错误：{e}")
        import traceback
        traceback.print_exc()
