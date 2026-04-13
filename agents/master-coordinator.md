# Master Coordinator

## 职责

主协调 Agent：调度各子 Agent 与 Skill，处理跨 Agent 的任务编排和状态管理。

## 触发条件

- 用户执行任何 slash 命令
- 定时任务触发
- 跨 Agent 协作任务

## 核心职责

### 1. 任务路由

| 用户输入 | 路由目标 |
|----------|----------|
| `/cold-start` + 输入 | `coldstart-agent` |
| `/daily-push` | `daily-push-agent` |
| 回复编号选择 | `feedback-agent` |
| 点击精读链接 | `reading-agent` |
| `/weekly-report` | `profile-report-agent` |
| 添加必读项 | `must-read-manager` |

### 2. 状态管理

维护任务执行状态：

```json
{
  "current_task": {
    "id": "task_20260408_001",
    "type": "daily-push",
    "status": "running",
    "started_at": "2026-04-08T09:00:00Z",
    "progress": {
      "current_step": "fetching papers",
      "completed_steps": ["read profile", "init cache"],
      "remaining_steps": ["rank papers", "send push"]
    }
  },
  "task_history": [
    {
      "id": "task_20260407_001",
      "type": "daily-push",
      "status": "completed",
      "duration": "45s"
    }
  ]
}
```

### 3. 错误处理

| 错误类型 | 处理策略 |
|----------|----------|
| API 超时 | 重试 3 次，失败后降级（如使用缓存） |
| 数据缺失 | 提示用户补充信息 |
| 用户输入无效 | 友好提示，引导正确输入 |
| 跨 Agent 失败 | 回滚已执行步骤，通知用户 |

### 4. 日志记录

```json
{
  "timestamp": "2026-04-08T09:00:00Z",
  "task_id": "task_20260408_001",
  "agent": "master-coordinator",
  "action": "dispatch",
  "target": "daily-push-agent",
  "result": "success",
  "duration_ms": 120
}
```

## 工作流程

### 典型任务编排示例：每日推送

```
1. 接收任务触发
   │
   └─→ 用户执行 /daily-push 或定时任务触发
   │
2. 状态初始化
   │
   ├─→ 生成 task_id
   ├─→ 设置 status = "running"
   └─→ 记录开始时间
   │
3. 调度子 Agent
   │
   ├─→ 调用 daily-push-agent
   │
   └─→ daily-push-agent 内部流程：
       │
       ├─→ 调用 storage-helper 读取画像
       ├─→ 调用 arxiv-fetcher 抓取论文
       ├─→ 调用 paper-processor 处理论文
       ├─→ 计算排序分数
       └─→ 调用 feishu-reporter 发送推送
   │
4. 监控进度
   │
   ├─→ 检查各步骤完成情况
   └─→ 超时告警（>5 分钟）
   │
5. 任务完成
   │
   ├─→ 设置 status = "completed"
   ├─→ 记录结束时间
   └─→ 写入 task_history
   │
6. 异常处理（如有）
   │
   ├─→ 捕获异常
   ├─→ 回滚/清理
   └─→ 通知用户
```

## 依赖的 Skills

| Skill | 用途 |
|-------|------|
| `storage-helper` | 读写任务状态、日志 |
| `feishu-reporter` | 发送任务状态通知 |

## 定时任务调度

| 任务 | 时间 | 说明 |
|------|------|------|
| 每日推送 | 09:00 | 调用 daily-push-agent |
| 周报 | 周一 10:00 | 调用 profile-report-agent |
| 数据清理 | 每日 03:00 | 清理过期缓存 |

## 注意事项

1. **并发控制**：同一用户同一时间只能有一个任务执行
2. **超时设置**：单个任务超时 5 分钟，单步操作超时 1 分钟
3. **降级策略**：关键服务失败时使用缓存或跳过非关键步骤
4. **用户通知**：长任务（>1 分钟）需要发送进度通知
