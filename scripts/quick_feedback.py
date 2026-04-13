#!/usr/bin/env python3
"""
飞书反馈处理器 - 快速模式

使用方式：
python scripts/quick_feedback.py "1 2 4 6"
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

import importlib
from datetime import datetime

# 导入 feedback-agent
feedback_agent = importlib.import_module("agents.feedback-agent.main")
process_feedback = feedback_agent.process_feedback
parse_user_reply = feedback_agent.parse_user_reply

# 导入数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile


def main():
    if len(sys.argv) < 2:
        print("用法：python quick_feedback.py \"1 2 4 6\"")
        print("     或：python quick_feedback.py \"1-5 8 10\"")
        sys.exit(1)

    # 拼接所有参数作为回复
    reply = " ".join(sys.argv[1:])

    print("=" * 60)
    print(f"处理回复：{reply!r}")
    print("=" * 60)

    # 解析
    selected = parse_user_reply(reply)
    print(f"选中编号：{sorted(selected)}")

    # 加载论文
    import glob
    push_files = glob.glob("test_push*.txt")
    if not push_files:
        print("错误：未找到推送文件，请先运行 daily-push")
        sys.exit(1)

    latest_file = max(push_files, key=os.path.getmtime)
    papers = []
    with open(latest_file, 'r', encoding='utf-8') as f:
        for line in f:
            import re
            match = re.match(r'^\s*(\d+)\.\s*([\w\.]+):\s*(.+)$', line)
            if match:
                papers.append({
                    "id": int(match.group(1)),
                    "arxiv_id": match.group(2),
                    "title": match.group(3)
                })

    print(f"论文数：{len(papers)}")

    # 处理反馈
    user_id = "user_001"
    push_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    result = process_feedback(
        user_id=user_id,
        push_id=push_id,
        reply=reply,
        papers=papers,
        feishu_user_id=None
    )

    print()
    print("处理完成:")
    print(f"  选中：{result.get('selected_count', 0)} 篇")
    print(f"  选择率：{result.get('selection_rate', 0):.1%}")

    # 显示画像状态
    profile = get_profile(user_id)
    if profile:
        history = profile.get('reading_history', [])
        print(f"  阅读历史：{len(history)} 条")


if __name__ == "__main__":
    main()
