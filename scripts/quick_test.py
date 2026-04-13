#!/usr/bin/env python3
"""
SciTaste 快速测试脚本

测试完整流程：
1. 创建角色
2. 每日推送
3. 反馈处理
4. 查看周报
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib

# 导入模块
role_manager = importlib.import_module("agents.role-manager.main")
daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
feedback_agent = importlib.import_module("agents.feedback-agent.main")
profile_report_agent = importlib.import_module("agents.profile-report-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def main():
    print_header("SciTaste 完整流程测试")

    # 1. 查看现有角色
    print_header("步骤 1: 查看现有角色")
    result = role_manager.process_role_command("查看角色列表", feishu_user_id=None, send_to_feishu=False)
    print(f"角色列表：{result}")

    # 2. 每日推送（使用 role2）
    print_header("步骤 2: 每日推送 (user_role2)")
    daily_push_agent.daily_push(
        user_id="user_role2",
        days=1,
        limit_per_source=5,
        send_to_feishu=False,  # 输出到控制台
        output_file=None
    )

    # 3. 反馈处理
    print_header("步骤 3: 反馈处理")
    push_info = db_ops.get_latest_push("user_role2")

    if push_info and push_info.get("papers"):
        papers = push_info["papers"]
        print(f"获取到 {len(papers)} 篇论文")
        print("\n论文列表:")
        for i, p in enumerate(papers[:10]):
            title = p.get("title", "Unknown")[:50]
            print(f"  {i+1}. {title}")

        # 模拟反馈
        reply = input("\n请输入选择的论文编号 (如 '1 2 3'，直接回车跳过): ").strip()
        if reply:
            result = feedback_agent.process_feedback(
                user_id="user_role2",
                push_id=push_info["push_id"],
                reply=reply,
                papers=papers,
                feishu_user_id=None,
                send_to_feishu=False
            )
            print(f"反馈处理结果：{result}")
        else:
            print("跳过反馈测试")
    else:
        print("没有推送记录，跳过反馈测试")

    # 4. 查看周报
    print_header("步骤 4: 查看周报")
    try:
        result = profile_report_agent.send_weekly_report(
            user_id="user_role2",
            send_to_feishu=False,
            feishu_user_id=None
        )
        print(f"周报结果：{result}")
    except Exception as e:
        print(f"周报：{e}")

    print_header("测试完成")

if __name__ == "__main__":
    main()
