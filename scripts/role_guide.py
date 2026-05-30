#!/usr/bin/env python3
"""
多角色系统使用指南

============================================================
角色 = 独立的飞书对话框/群聊
============================================================

每个角色有：
- 独立的用户画像 (user_rolea, user_roleb...)
- 独立的飞书群 ID (chat_id)
- 独立的推送流

============================================================
使用流程
============================================================

1. 创建角色
   python agents/role-manager/main.py --command "创建角色 roleA，研究方向：GUI Agent"

2. 在飞书中创建一个群聊（手动）
   - 打开飞书
   - 创建新群聊
   - 添加机器人到群聊
   - 获取群聊 ID（chat_id）

3. 绑定角色到飞书群
   python agents/role-manager/main.py --command "绑定 roleA chat_xxx"

4. 测试推送
   python deployments/feishu/daily-push-agent/main.py --user-id user_rolea --send-feishu

============================================================
当前角色列表
============================================================
运行：
   python agents/role-manager/main.py --command "查看角色列表"

============================================================
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
role_manager = importlib.import_module("agents.role-manager.main")

# 显示当前角色
meta = role_manager.load_roles_meta()
print("当前角色系统状态：")
print(json.dumps(meta, indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("操作示例：")
print("=" * 60)
print("""
# 创建新角色
python agents/role-manager/main.py --command "创建角色 roleC, 研究方向：deep learning"

# 绑定飞书群（需要先获取群 chat_id）
python agents/role-manager/main.py --command "绑定 roleA chat_xxxxx"

# 切换角色
python agents/role-manager/main.py --command "切换到 roleA"

# 查看角色列表
python agents/role-manager/main.py --command "查看角色列表"

# 给指定角色推送
python deployments/feishu/daily-push-agent/main.py --user-id user_rolea --send-feishu
""")
