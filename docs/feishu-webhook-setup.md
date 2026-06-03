# 飞书 Webhook 配置指南

这份文档对应 PaperFlow 当前唯一保留的本地联调方案：

`webhook + ngrok`

如果只是把精读报告创建成飞书文档，不需要 webhook 或 ngrok；请看
[feishu-doc-export.md](feishu-doc-export.md)。

## 1. 填好 `.env`

最少需要：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
FEISHU_BOT_NAME=PaperFlow Bot
FEISHU_USER_ID=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`FEISHU_APP_ID` / `FEISHU_APP_SECRET` 在飞书开放平台应用详情页 → **凭证与基础信息** 看（详见 §4.1）。

`FEISHU_VERIFICATION_TOKEN` 在 **开发配置 → 事件与回调 → 事件配置** 顶部那一栏看（详见 §4.3）。

`FEISHU_USER_ID` 是**你自己的飞书 open_id**（私聊 bot 没绑 chat_id 时，bot 会私聊回到这个 open_id）。三种取法挑一种就行：

1. **最快**：bot 启动后，自己私聊 bot 随便发一句话，本地 webhook 终端会打印一行类似 `sender open_id=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`，复制 `ou_...` 整段粘到 `.env`。
2. **从 API**：在浏览器打开 <https://open.feishu.cn/api-explorer> → 搜 `获取用户信息 / Get User Info` → 用应用身份调一次，返回里 `open_id` 就是。
3. **从飞书客户端**：打开飞书设置 → 个人信息页右上角 ⋯，部分版本会显示 `User ID`，但**那个不是 open_id**（是 `user_id`）。除非你把 [feishu_reporter.py](../deployments/feishu/feishu-reporter/scripts/feishu_reporter.py) 改成走 `user_id` 模式，否则别用这种方式。

> 注意：bot 通过 `FEISHU_USER_ID` 私聊你之前，你必须**先和 bot 互发过至少一条消息**（飞书要求"已建立单聊会话"），否则 bot 主动发消息会报 `99991672 NotFound`。

可选（强烈推荐 — URL 永远不变）：

```bash
NGROK_AUTHTOKEN=xxxxxxxxxxxxxxxx
NGROK_DOMAIN=gap-suffrage-caddie.ngrok-free.dev
```

`NGROK_DOMAIN` 来自 <https://dashboard.ngrok.com/domains> 点 **+ New Domain**，免费账号送一个永久域名。配置之后下面"配置飞书开放平台"那一步只需做一次。

## 2. 确认 ngrok 已可用

```bash
ngrok version
ngrok config add-authtoken <your-token>
```

token 来自 <https://dashboard.ngrok.com/get-started/your-authtoken>，每台机器跑一次即可。

## 3. 启动 PaperFlow 的联调入口

```bash
python deployments/feishu/webhook-server/start-with-ngrok.py
```

成功后会看到：

- 本地 webhook 地址
- 当前 ngrok 公网地址
- 可直接填写到飞书后台的 `Request URL`

同时脚本会把地址写到：

```text
data/ngrok_url.txt
data/feishu_request_url.txt
```

## 4. 配置飞书开放平台

入口：<https://open.feishu.cn/app> → 在 **企业自建应用 / Custom Apps** 列表里点中你的 PaperFlow App，进入应用详情页。

> 后面所有"左侧菜单"指的都是**应用详情页**左边那一栏，分组依次是：**应用信息 / 凭证与基础信息 / 应用能力 / 开发配置 / 应用发布**。

### 4.1 取 App ID / App Secret 填到 `.env`

左侧菜单 → **凭证与基础信息 / Credentials & Basic Info**

| 页面字段 | 复制到 `.env` 的哪一项 |
|----------|----------------------|
| App ID | `FEISHU_APP_ID` |
| App Secret（点"显示"才能看到） | `FEISHU_APP_SECRET` |

### 4.2 启用机器人能力（仅首次）

左侧菜单 → **应用能力 / Add features**（不是顶部，是左栏中间的分组）→ 找到 **机器人 / Bot** 这一行卡片 → 点 **添加 / 启用**。

启用后这一行右侧会出现"已添加"。**没有这一步飞书不会把消息推过来。**

### 4.3 配置事件订阅 Request URL（最容易卡的一步）

左侧菜单 → **开发配置 / Development Config** → **事件与回调 / Events & Callbacks** → 顶部 Tab 选 **事件配置 / Event Configuration**。

页面顶部 **配置订阅方式 / Subscription Method** 那一块：

- **推送方式 / Push Method**：选 **将事件发送至开发者服务器（HTTP）/ Send to developer server (HTTP)**（不是"长连接 WebSocket"）

下方出现三个输入框，按下表填：

| 字段（页面原文） | 值 | 说明 |
|------------------|-----|------|
| **请求地址 / Request URL** | `https://gap-suffrage-caddie.ngrok-free.dev/`（直接复制 `data/feishu_request_url.txt` 整行） | **结尾的 `/` 不能少** |
| **Encrypt Key / 加密 Key** | **完全留空，不要点"重置"** | PaperFlow webhook 不解密 payload；填了校验必失败 |
| **Verification Token / 校验 Token** | 一串 16+ 位字符 | 复制这串到 `.env` 里的 `FEISHU_VERIFICATION_TOKEN`，两边必须**完全一致**（含大小写） |

点页面右下角 **保存 / Save**。飞书会立刻调用一次 Request URL 做校验：

- 成功 → 弹出 "URL 校验通过 / Verification succeeded" 绿条
- 失败 → 红条提示，按下面"常见问题"排查

### 4.4 订阅消息事件

**同一页面**继续往下翻，找到 **事件 / Events** 区块（在 Request URL 下方，有一个表格 + **添加事件 / Add Events** 按钮）。

点 **添加事件 / Add Events**，弹窗里搜索并勾选：

| 事件名（搜索关键词） | 事件 Key | 必需？ |
|----------------------|----------|--------|
| 接收消息 / Receive Messages | `im.message.receive_v1` | **必需**，没它 bot 收不到任何消息 |
| 消息已读 / Message Read | `im.message.message_read_v1` | 可选 |
| 消息表情回复 / Message Reaction Created | `im.message.reaction.created_v1` | 想用点赞/点踩当 feedback 时勾 |

每勾一个，弹窗会提示"该事件需要以下权限"，**直接点确认/添加，权限会自动加进权限申请单**。

弹窗关掉后，点表格右下角的 **保存 / Save** 让订阅生效。

### 4.5 申请并发布权限（首次必需，否则 bot 不能发消息）

左侧菜单 → **开发配置 / Development Config** → **权限管理 / Permissions & Scopes**。

页面有一个搜索框，按表格依次搜索 + 点 **申请 / Add**：

| Scope（搜索这个名字） | 用途 |
|-----------------------|------|
| `im:message` | 收发消息 |
| `im:message:send_as_bot` | 以 bot 身份发消息 |
| `im:resource` | 下载用户上传的 PDF |
| `docx:document` | 创建精读报告 docx |
| `docx:document:readonly` | 读取自己创建的报告 |
| `contact:user.id:readonly` | 把 open_id 解析成用户 |

> 4.4 弹窗自动加进来的权限，这里会显示"待发布"。

申请完**必须发版本，否则权限不会真正生效**：

1. 左侧菜单 → **应用发布 / App Release** → **版本管理与发布 / Versions & Releases**
2. 右上角点 **创建版本 / Create Version**
3. 版本号随便填（如 `0.1.0`）→ 更新说明随便写 → **提交申请 / Submit**
4. 企业自建应用一般会显示"无需审核，已发布"；如果显示"待管理员审核"，去飞书管理后台 (<https://www.feishu.cn/admin>) 自己批准就行

### 4.6 让 bot 进群（如果你用群聊）

在飞书桌面端：
1. 建一个群（或用现有的群）
2. 群右上角 ⋯ → **群设置 / Group Settings** → **群机器人 / Group Bots** → **添加机器人 / Add Bot**
3. 搜你的 PaperFlow Bot → 添加

bot 进群后，在群里 @它 随便发一句话，本地 webhook 终端会打印一行带 `chat_id` 的日志（形如 `oc_xxxxxxxx`）。复制 `oc_...`，回命令行：

```bash
python agents/role-manager/main.py --command "绑定 role1 oc_xxxxxxxx"
```

把 `chat_id` 写回 `data/roles.json`。**只私聊用 bot 的话这一步可以跳过**。


## 5. 角色与群的对应（多用户必看）

PaperFlow 是多角色系统：每个**飞书群**对应一个**角色（role）**，bot 收到消息后查 [data/roles.json](../data/roles.json) 反查"这个 chat_id 是哪个 role"，然后用那个 role 的画像生成推荐 / 报告。

### 5.1 唯一对应表

只有一个文件：[data/roles.json](../data/roles.json)。结构是：

```json
{
  "roles": {
    "role1": {
      "user_id": "user_role1",
      "feishu_chat_id": "oc_aae06b...",
      "description": "direction: gui agent, web automation, ..."
    },
    "role2": { ... }
  }
}
```

每条 role 有一个 `feishu_chat_id` 字段决定它绑哪个群。webhook 每次收消息都会重读这个文件，**不用重启**。

### 5.2 查看当前对应表

```bash
python -c "import json; r=json.load(open('data/roles.json',encoding='utf-8'))['roles']; [print(f'{n} -> {v[\"feishu_chat_id\"] or \"(empty)\"} | {v.get(\"description\",\"\")[:50]}') for n,v in r.items()]"
```

### 5.3 三种修改方式（任选其一）

**方式 A：群里 @bot 直接绑**（最方便）

在目标群里 @PaperFlow Bot 发：

```
绑定 role1
```

bot 会把当前群的 `chat_id` 写到 `role1` 的 `feishu_chat_id`。

**方式 B：命令行**

```bash
python agents/role-manager/main.py --command "绑定 role1 oc_xxxxxxxx"
```

**方式 C：直接编辑 JSON**

打开 [data/roles.json](../data/roles.json)，改对应 role 的 `feishu_chat_id` 字段保存即可。

### 5.4 新人接入的两种典型路径

**路径 1：复用现成 24 个 role**

适合：跟实验对齐 / 跑 demo / 想体验不同方向。

操作：在飞书里建若干个群 → 把 bot 拉进每个群 → 在每个群里 `@bot 绑定 roleN` 即可（每个群只能绑一个 role）。

**路径 2：建自己的 role**

适合：自己研究方向、不在 24 个预设方向里。

```bash
# 建一个新角色
python agents/role-manager/main.py --command "创建角色 alice，研究方向：扩散模型 视频生成"

# 跑一次 profile cold start 给它写初始画像
paperflow profile \
  --user-id user_alice \
  --natural-language "扩散模型 视频生成"

# 把它绑到飞书群
python agents/role-manager/main.py --command "绑定 alice oc_xxxxxxxx"
```

[role-manager/main.py](../agents/role-manager/main.py) 支持的命令：

| 命令 | 用途 |
|------|------|
| `创建角色 <name>，研究方向：<keywords>` | 新建一个 role |
| `切换到 <name>` | CLI 模式下切换默认 role（webhook 模式下不影响群） |
| `删除角色 <name>` | 删 role |
| `绑定 <name> <chat_id>` | 把 chat_id 写到 role 上 |
| `角色列表` | 列出所有 role |

### 5.5 飞书反馈和 CLI 反馈的关系

飞书群里回复 `1 3`、`1-5`、`none`、`全部`、`没有` 时，webhook 会先根据
`chat_id` 找到绑定的 role / `user_id`，然后调用和 CLI 一样的
`feedback-agent`。因此下面两种方式对同一个 `user_id` 来说是等价的画像学习信号：

```text
飞书群里回复：1 3
```

```bash
paperflow feedback --user-id user_alice --push-id <latest_push_id> --reply "1 3"
```

二者都会写入 `data/paperflow.db`，更新用户画像、selected/skipped 行为日志、
drift 状态，并在开启 `PAPERFLOW_WIKI_INGEST=true` 时同步到本地 wiki。完整闭环见
[feedback-loop.md](feedback-loop.md)。

### 5.6 怎么知道某个群的 chat_id

飞书界面里看不到 chat_id。最快的办法：bot 进群后，群里 @bot 发任意一句话，本地 webhook 终端会打印：

```
[INFO] received text from chat_id=oc_aae06b0c... role=role1 ...
```

`oc_...` 那串就是这个群的 chat_id。如果 `role=` 后面是 `None`，就说明这个群还没绑任何 role，按 §5.3 绑一下就行。


## 6. 本地自检

### webhook 是否活着

```bash
curl http://127.0.0.1:8080/health
```

### ngrok 是否真的转到本地 8080

```bash
curl http://127.0.0.1:4040/api/tunnels
```

看返回内容里是否有：

```text
localhost:8080
```

## 7. 在飞书里做真实测试

给 bot 私聊或群里 @它 发任意一条文本消息，例如：

```text
推送
```

如果飞书里能看到你发出的消息，但本地 webhook 没有收到 `POST /`，通常就是飞书后台还挂着旧的 ngrok 地址（用 `NGROK_DOMAIN` 静态域名后这个问题不会再出现）。

## 8. 常见问题

### Request URL 验证失败

按这个顺序查：

1. webhook 是否已经启动（`curl http://127.0.0.1:8080/health` 回 `{"status":"healthy"}`）
2. ngrok 隧道是否真的指向 8080（`curl http://127.0.0.1:4040/api/tunnels` 看到 `localhost:8080`）
3. 飞书后台 **Encrypt Key** 是否留空
4. 飞书后台 **Verification Token** 是否和 `.env` 里的 `FEISHU_VERIFICATION_TOKEN` 完全一致（含大小写）
5. URL 末尾有没有漏 `/`

### 每次都要改 URL

免费 ngrok 不带静态域名时 URL 每次重启都会变。在 `.env` 里加一行 `NGROK_DOMAIN=xxx-yyy-zzz.ngrok-free.dev`（去 <https://dashboard.ngrok.com/domains> 领一个免费的）就能锁定 URL。

### 终端有日志，但飞书里 bot 不回消息

最常见的几种原因，按出现频率排：

**1. 缺权限（最常见）：申请了但没"创建版本 → 发布"**

scope 申请完只是"待发布"，必须发版本权限才生效，否则 bot 调发消息接口会返回 `99991663 / 99991668 / NoAccess` 之类。

去 **应用发布 → 版本管理与发布** → **创建版本** → 提交 → 发布。看终端是否还有 `Send message failed: code=99991xxx` 这种报错。

**2. bot 没启用机器人能力**

scope 全了，但没在 **应用能力 → 机器人** 里启用。终端调 IM 接口返回 `230002` 或 `99991671`。回 §4.2 启用一次。

**3. 群里 bot 默认只听 @它 的消息**

终端日志里能看到 `chat_id=oc_xxx` 但**没有** `intent=...` / `routing to coordinator` 这种行 — 说明消息没进 coordinator。原因：群里 bot 的"接收消息范围"默认只接 @它 的消息，你直接发"推送"它收不到。

解决：要么每次 @ 它（`@PaperFlow Bot 推送`），要么去 **事件订阅 / Event Subscriptions** 把 **接收消息范围 / Message Receive Range** 改成"所有消息"。

**4. chat_id 没绑到任何 role**

终端打 `_find_role_by_chat_id ... role=None`，coordinator 拿不到 user_id 就早早 return 不回消息。按 §5.3 绑一下：群里 @bot 发 `绑定 role1`。

**5. 私聊场景下 bot 主动发消息要求"已建立单聊会话"**

如果你刚建好 bot 没和它互发过任何消息，bot 主动给你 push 会报 `99991672 NotFound`。先在私聊里随便发一句"hi"建好会话再试。

**6. coordinator 内部抛异常但被吞了**

终端有 `Traceback` 就是这种。最常见是 `OPENAI_API_KEY` 没配 / 配错（默认 LLM provider 是 openai），bot 生成不了内容自然没法回。看终端 traceback 第一行是哪个错对症下药；如果只是想跑通流程不在意推荐质量，临时设：

```bash
PAPERFLOW_LLM_PROVIDER=mock PAPERFLOW_EMBED_PROVIDER=hash python deployments/feishu/webhook-server/start-with-ngrok.py
```

mock provider 不调任何外部 API，能快速验证消息回路。

### 调试小技巧

webhook 终端里搜这几个关键词，定位卡在哪一层：

| 关键词 | 含义 |
|--------|------|
| `POST /` | 飞书 → webhook 这一段通了 |
| `chat_id=oc_xxx role=roleN` | role 反查成功 |
| `intent=daily_push` 等 | coordinator 识别意图成功 |
| `Send message failed` | bot 调发消息接口失败（通常是权限） |
| `Traceback` | coordinator 内部炸了，看下一行错误 |
