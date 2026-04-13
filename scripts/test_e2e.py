#!/usr/bin/env python3
"""
SciTaste 端到端测试脚本

测试完整的推荐流程：
1. 创建角色
2. 冷启动（设置研究方向）
3. 每日推送（获取论文列表）
4. 反馈处理（选择论文）
5. 生成精读报告
6. 查看周报

用法:
    python scripts/test_e2e.py --role test_user
"""

import sys
import os
import json
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib

# 导入模块
role_manager = importlib.import_module("agents.role-manager.main")
coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
feedback_agent = importlib.import_module("agents.feedback-agent.main")
reading_agent = importlib.import_module("agents.reading-agent.main")
profile_report_agent = importlib.import_module("agents.profile-report-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def run_create_role(role_name: str, description: str) -> str:
    """测试创建角色"""
    print_section(f"步骤 1: 创建角色 '{role_name}'")

    result = role_manager.create_role(
        role_name=role_name,
        description=description,
        natural_language=description
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("success"):
        print(f"[OK] 角色 '{role_name}' 创建成功")
        return result.get("user_id")
    else:
        print(f"[WARNING] 角色创建可能已存在：{result.get('message')}")
        # 返回已存在的 user_id
        return f"user_{role_name}"


def run_cold_start(user_id: str, natural_language: str):
    """测试冷启动"""
    print_section("步骤 2: 冷启动 - 设置研究方向")

    # 使用测试模式，不发送飞书
    result = coldstart_agent.cold_start(
        user_id=user_id,
        natural_language=natural_language,
        send_to_feishu=False  # 测试模式
    )

    print(f"冷启动结果：{result}")
    print("[OK] 冷启动完成")


def run_daily_push(user_id: str, limit: int = 10):
    """测试每日推送"""
    print_section("步骤 3: 每日推送")

    # 执行每日推送，输出到控制台
    daily_push_agent.daily_push(
        user_id=user_id,
        days=1,
        limit_per_source=limit,
        send_to_feishu=False,  # 测试模式
        output_file=None  # 输出到控制台
    )

    print("[OK] 每日推送完成")


def run_feedback(user_id: str, reply: str = "1 2 3"):
    """测试反馈处理"""
    print_section("步骤 4: 反馈处理")

    # 获取最近的推送
    push_info = db_ops.get_latest_push(user_id)

    if not push_info:
        print("[SKIP] 没有推送记录，跳过反馈测试")
        return

    papers = push_info.get("papers", [])
    if not papers:
        print("[SKIP] 没有论文数据，跳过反馈测试")
        return

    print(f"从推送 {push_info['push_id']} 获取了 {len(papers)} 篇论文")

    # 处理反馈
    result = feedback_agent.process_feedback(
        user_id=user_id,
        push_id=push_info['push_id'],
        reply=reply,
        papers=papers,
        feishu_user_id=None,
        send_to_feishu=False  # 测试模式
    )

    print(f"反馈处理结果：{result}")
    print("[OK] 反馈处理完成")


def run_reading_report(user_id: str, paper_ids: list = None):
    """测试精读报告"""
    print_section("步骤 5: 生成精读报告")

    # 获取最近的推送
    push_info = db_ops.get_latest_push(user_id)

    if not push_info:
        print("[SKIP] 没有推送记录，跳过精读测试")
        return

    papers = push_info.get("papers", [])
    if not papers:
        print("[SKIP] 没有论文数据，跳过精读测试")
        return

    # 默认使用前 2 篇论文
    if paper_ids is None:
        paper_ids = [p['id'] for p in papers[:2]]

    print(f"为论文 {paper_ids} 生成精读报告...")

    # 生成精读报告（不发送到飞书）
    try:
        created_docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=paper_ids,
            papers=papers,
            send_to_feishu=False  # 测试模式
        )
        print(f"[OK] 生成了 {len(created_docs)} 个精读报告")
    except Exception as e:
        print(f"[INFO] 精读报告生成（飞书 API 可能需要配置）: {e}")


def run_weekly_report(user_id: str):
    """测试周报生成"""
    print_section("步骤 6: 生成周报")

    try:
        result = profile_report_agent.send_weekly_report(
            user_id=user_id,
            send_to_feishu=False,  # 测试模式
            feishu_user_id=None
        )
        print(f"周报结果：{result}")
        print("[OK] 周报生成完成")
    except Exception as e:
        print(f"[INFO] 周报生成：{e}")


def run_show_profile(user_id: str):
    """查看用户画像"""
    print_section("当前用户画像")

    profile = db_ops.get_profile(user_id)

    if profile:
        print(f"用户 ID: {profile.get('user_id', 'N/A')}")
        print(f"版本：{profile.get('version', 'N/A')}")

        core_directions = profile.get("core_directions", {})
        if core_directions:
            print("\n核心研究方向:")
            for direction, weight in sorted(core_directions.items(), key=lambda x: -x[1]):
                print(f"  - {direction}: {weight:.2f}")

        must_read = profile.get("must_read", {})
        if must_read:
            print("\n必读清单:")
            for key, items in must_read.items():
                if items:
                    print(f"  {key}: {items[:3]}")  # 只显示前 3 个
    else:
        print("未找到用户画像")


def main():
    parser = argparse.ArgumentParser(description="SciTaste E2E Test")
    parser.add_argument("--role", type=str, default="test_user", help="角色名称")
    parser.add_argument("--description", type=str,
                        default="machine learning, deep learning, neural networks, NLP, computer vision",
                        help="研究方向描述")
    parser.add_argument("--skip-coldstart", action="store_true", help="跳过冷启动")
    parser.add_argument("--skip-push", action="store_true", help="跳过每日推送")
    parser.add_argument("--feedback", type=str, default="1 2 3", help="反馈选择")
    parser.add_argument("--limit", type=int, default=10, help="每数据源论文数量限制")

    args = parser.parse_args()

    role_name = args.role
    user_id = f"user_{role_name}"

    print("=" * 60)
    print("  SciTaste 端到端测试")
    print("=" * 60)
    print(f"角色：{role_name}")
    print(f"用户 ID: {user_id}")
    print("=" * 60)

    # 1. 创建角色
    run_create_role(role_name, args.description)

    # 2. 冷启动
    if not args.skip_coldstart:
        run_cold_start(user_id, args.description)

    # 3. 查看画像
    run_show_profile(user_id)

    # 4. 每日推送
    if not args.skip_push:
        run_daily_push(user_id, args.limit)

    # 5. 反馈处理
    run_feedback(user_id, args.feedback)

    # 6. 精读报告
    run_reading_report(user_id)

    # 7. 周报
    run_weekly_report(user_id)

    # 最后查看画像
    print_section("测试完成后的用户画像")
    run_show_profile(user_id)

    print("\n" + "=" * 60)
    print("  端到端测试完成!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
