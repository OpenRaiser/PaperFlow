# SciTaste

SciTaste 是一个运行在飞书群聊里的科研论文助手。它通过 `Feishu webhook + ngrok` 接收消息，完成冷启动画像、每日推送、反馈学习、精读报告和周报生成，并且支持多角色、多群聊独立画像。

这份 README 的目标只有一个:

让别人第一次拿到仓库后，按照文档一步一步配置，就能把系统跑起来。

## 1. 项目能力

- 冷启动
  - 支持自然语言描述初始化画像
  - 支持 PDF 论文冷启动
  - 支持多角色预设方向
- 每日推送
  - 聚合 arXiv、OpenReview、期刊/会议源
  - 按相关度排序后推送到飞书群
- 反馈学习
  - 支持 `1 2 3`、`1-3`、`all red`、`none`
  - 根据用户选择持续更新画像
- 精读报告
  - 用户选中论文后自动生成飞书文档
  - 自动把文档链接发回原群聊
- 周报
  - 统计近期推荐、选择率、方向变化
- 多角色
  - 一个仓库可以绑定多个飞书群
  - 每个群维护独立画像和独立推荐逻辑

## 2. 运行方案

当前仓库只保留一套推荐方案:

`Feishu webhook + ngrok`

这是最适合公开仓库、最容易让别人复现的方案。

原因:

- 本地开发简单
- 不需要先上云服务器
- 飞书事件订阅链路清晰
- 出问题时排查最直接

## 3. 仓库结构

```text
scitaste/
├─ agents/                      # 各业务 Agent
├─ skills/                      # 抓取、嵌入、飞书发送、数据库等基础能力
├─ services/webhook-server/     # 飞书 webhook 服务与 ngrok 启动入口
├─ scripts/                     # 初始化、清库、调试辅助脚本
├─ config/                      # 角色模板、期刊会议配置、词典等
├─ docs/                        # 补充文档
├─ tests/                       # 自动化测试
├─ data/                        # 本地数据库与运行时文件（不提交）
├─ models/                      # 本地模型目录（不提交）
├─ .env.example                 # 环境变量模板
├─ start.bat                    # Windows 一步启动入口
└─ README.md
```

## 4. 给第一次使用者的快速路线

如果你只是想先跑通，请按下面顺序走:

1. 安装 Python、Node.js、ngrok
2. 克隆仓库
3. 运行初始化脚本
4. 填好 `.env`
5. 配置飞书应用和事件订阅
6. 运行 `start.bat` 或 `python services/webhook-server/start-with-ngrok.py`
7. 把 `data/feishu_request_url.txt` 里的地址填到飞书后台
8. 在飞书群里发送 `冷启动`、`推送`、`1 2` 做联调

下面是完整细化步骤。

## 5. 前置依赖

至少需要:

- Python 3.10 或更高
- Node.js 18 或更高
- `npm`
- `ngrok`
- 一个飞书开放平台应用
- 一个可用的 `lark-cli`

推荐但不是必须:

- 本地 embedding 模型
- 本地生成式模型
- OpenAI API Key
- Hugging Face Token
- OpenReview / IEEE API 凭证

## 6. 安装与初始化

### 6.1 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/scitaste.git
cd scitaste
```

如果对方不是通过 Git 获取，而是直接下载压缩包，也可以解压后进入项目根目录。

### 6.2 创建虚拟环境并安装依赖

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.3 安装 `lark-cli`

SciTaste 当前通过 `lark-cli` 发送飞书消息、创建飞书文档、查询文档链接。

安装:

```bash
npm install -g @larksuite/cli
lark-cli --version
```

登录:

```bash
lark-cli auth login --domain im,docs,drive --recommend
```

如果 `lark-cli` 没有进入系统 PATH，可以在 `.env` 里补:

```env
FEISHU_CLI_CMD=C:\path\to\lark-cli.cmd
```

### 6.4 运行初始化脚本

Windows:

```powershell
scripts\init.bat
```

macOS / Linux:

```bash
bash scripts/init_project.sh
```

这一步会做几件事:

- 从 `.env.example` 生成 `.env`
- 从 `config/roles.example.json` 生成 `data/roles.json`
- 安装 Python 依赖
- 初始化 `data/scitaste.db`
- 校验飞书相关环境变量

## 7. 配置 `.env`

先复制模板:

Windows:

```powershell
copy .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

最少要填写这些字段:

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=your_app_secret_here
FEISHU_VERIFICATION_TOKEN=your_verification_token_here
FEISHU_BOT_NAME=SciTaste Bot
NGROK_AUTHTOKEN=your_ngrok_token_here
```

如果希望在缺少 `chat_id` 时还能回复到某个个人账号，可以额外填:

```env
FEISHU_USER_ID=ou_xxxxxxxxxxxxx
```

### 7.1 最省事的调试配置

如果你先只想把链路跑通，不想先处理模型问题:

```env
EMBEDDING_PROVIDER=hash
LLM_PARSER_PROVIDER=disabled
```

这种配置可以完成:

- webhook 联调
- 冷启动
- 推送
- 反馈
- 飞书文档生成

但是语义理解和推荐质量会弱很多。

### 7.2 推荐的本地模型配置

如果你已经把模型下载到了 `models/`:

```env
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL_PATH=./models/Qwen3-Embedding-8B
LOCAL_EMBEDDING_TRUST_REMOTE_CODE=true

LLM_PARSER_PROVIDER=local
LOCAL_LLM_MODEL_PATH=./models/Qwen3-4B-Instruct-2507
LOCAL_LLM_TRUST_REMOTE_CODE=true
LOCAL_LLM_DEVICE=auto
```

说明:

- `Qwen3-Embedding-8B` 只负责 embedding
- 画像理解、自由表达理解、精读润色需要生成式模型，比如 `Qwen3-4B-Instruct-2507`

### 7.3 API 配置

如果不想下载本地模型，可以用 API。

Embedding 走 Hugging Face:

```env
EMBEDDING_PROVIDER=hf_api
HF_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
HF_INFERENCE_PROVIDER=auto
```

LLM 走 OpenAI:

```env
LLM_PARSER_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_PARSER_OPENAI_MODEL=gpt-4o-mini
```

## 8. 配置角色

模板文件在:

`config/roles.example.json`

初始化后，实际运行文件在:

`data/roles.json`

默认结构示例:

```json
{
  "roles": {
    "rolea": {
      "user_id": "user_rolea",
      "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
      "feishu_chat_id": ""
    }
  },
  "current_role": "rolea"
}
```

建议每个角色先写 2 到 3 个研究方向到 `description`，这样冷启动更稳。

`feishu_chat_id` 的作用:

- 用于把不同飞书群绑定到不同角色
- 一个群对应一个角色
- 不填也能启动，但多群路由不会准确

如果你还没有拿到群 `chat_id`，可以使用:

```powershell
python scripts\how_to_get_chat_id.py
python scripts\get_chat_ids.py
```

## 9. 飞书开放平台配置

### 9.1 创建飞书应用

在飞书开放平台创建一个自建应用，并开启机器人能力。

你需要拿到:

- `App ID`
- `App Secret`
- `Verification Token`

然后填入 `.env`。

### 9.2 配置事件订阅

启动本地项目后，SciTaste 会自动生成:

- `data/ngrok_url.txt`
- `data/feishu_request_url.txt`

其中 `data/feishu_request_url.txt` 是你要填到飞书后台的地址。

配置路径:

`飞书开放平台 -> 你的应用 -> Event Subscription`

操作步骤:

1. 启动本地服务和 ngrok
2. 打开 `data/feishu_request_url.txt`
3. 把里面的完整 URL 粘贴到 `Request URL`
4. 把 `.env` 中的 `FEISHU_VERIFICATION_TOKEN` 填到飞书后台
5. 勾选事件 `im.message.receive_v1`
6. 保存并等待飞书校验通过

### 9.3 把机器人拉进群

如果要做多角色，建议准备多个飞书群:

- `rolea` 一个群
- `roleb` 一个群
- `rolec` 一个群
- `roled` 一个群

再把机器人加入这些群，最后把对应群的 `chat_id` 填回 `data/roles.json`。

## 10. 启动 webhook + ngrok

### 10.1 Windows 一步启动

```powershell
start.bat
```

### 10.2 通用启动命令

```bash
python services/webhook-server/start-with-ngrok.py
```

### 10.3 只启动本地 webhook

```bash
python services/webhook-server/start.py
```

### 10.4 只检查配置是否完整

```bash
python services/webhook-server/start.py --verify
```

### 10.5 启动成功后会发生什么

脚本会自动:

- 启动本地 webhook 服务，默认端口 `8080`
- 检测并复用本机 ngrok agent，或者拉起新的隧道
- 生成公网 URL
- 写入 `data/ngrok_url.txt`
- 写入 `data/feishu_request_url.txt`

## 11. 标准验证流程

建议按下面顺序验证。

### 11.1 基础健康检查

```bash
curl http://127.0.0.1:8080/health
```

期望返回:

```json
{"status":"healthy"}
```

### 11.2 检查 ngrok 隧道

```bash
curl http://127.0.0.1:4040/api/tunnels
```

确认返回里有指向 `localhost:8080` 的 tunnel。

### 11.3 检查飞书后台地址

确认:

- `data/feishu_request_url.txt` 是最新地址
- 飞书后台 `Request URL` 也同步成这个最新地址

### 11.4 飞书群实测

在飞书群里依次测试:

1. `冷启动`
2. `推送`
3. `1 2`
4. `精读`
5. `周报`

也可以测试这些常用命令:

- `all red`
- `none`
- `加个必读作者：XXX`
- `加个机构：MIT`
- `添加关键词：GUI Agent`
- `我对Cold Start不感兴趣`

## 12. 常用维护命令

初始化数据库:

```powershell
python scripts\init_db.py
```

清理数据库但保留角色冷启动画像:

```powershell
python scripts\clear_database.py --action full_reset --yes
```

查看数据库:

```powershell
python scripts\view_db.py
```

查看某个角色画像:

```powershell
python scripts\show_profile.py --user-id user_rolea
```

## 13. 常见问题

### 13.1 `Webhook server did not become healthy in time`

优先检查:

- `8080` 端口是否被占用
- `.env` 是否漏填飞书必填项
- `python services\webhook-server\start.py --verify` 是否通过

### 13.2 飞书群里发 `推送` 没反应

优先检查:

- 本地 `http://127.0.0.1:8080/health` 是否健康
- `http://127.0.0.1:4040/api/tunnels` 是否有 tunnel
- 飞书后台 `Request URL` 是否还是旧 ngrok 地址

### 13.3 为什么每次都要更新 `Request URL`

免费 ngrok 的公网域名通常会变化，这是正常现象。

如果只是本地调试:

- 每次重启后，把新的 `data/feishu_request_url.txt` 地址重新贴到飞书后台即可

如果后续要长期稳定运行:

- 升级到 ngrok 保留域名
- 或把服务部署到固定公网地址

### 13.4 为什么自然语言理解有时会慢

如果启用了本地生成式模型，第一次解析用户自然语言时可能会先加载模型，所以会明显变慢。

如果只是联调链路，建议先用:

```env
LLM_PARSER_PROVIDER=disabled
```

等 webhook、推送和反馈全部稳定后，再切回本地模型或 API。

## 14. 上传到 GitHub 前的注意事项

这个仓库默认不会提交:

- `.env`
- `data/`
- `models/`
- `__pycache__/`
- `.pytest_cache/`
- 本地日志和调试输出

上传前请务必确认:

- 不要提交真实的 `.env`
- 不要提交 `data/roles.json` 里的真实群 `chat_id`
- 不要提交 `data/scitaste.db`
- 不要提交 `models/` 下的大模型

如果你要新建自己的 GitHub 仓库:

```bash
git init -b main
git add .
git commit -m "Initial public release"
git remote add origin https://github.com/YOUR_USERNAME/scitaste.git
git push -u origin main
```

## 15. 推荐发布方式

如果你的目标是“先让别人能跑起来”，最推荐的是:

- 仓库里保留这份 README
- 保留 `.env.example`
- 保留 `config/roles.example.json`
- 保留 `start.bat`
- 不提交任何真实密钥、真实数据库、真实模型

这样别人只需要准备自己的飞书应用、自己的 ngrok token 和自己的角色配置，就能跑起来。

## 16. License

MIT
