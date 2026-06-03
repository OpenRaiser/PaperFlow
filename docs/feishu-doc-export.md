# Feishu/Lark Reading Report Export

This document covers only one capability: creating a Feishu/Lark document from
a PaperFlow reading report.

It is separate from the webhook/ngrok bot deployment. You do not need ngrok for
document export because PaperFlow calls Feishu APIs directly from the local
machine.

## What This Does

```text
paperflow read
  -> generate a local Markdown reading report
  -> optionally create a Feishu/Lark doc with the same content
  -> record doc_url / doc_token in PaperFlow history and wiki metadata
```

If Feishu doc creation fails, the local Markdown report is still saved.

## Minimum Configuration

Set these values in `.env`:

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_CLI_CMD=C:/Users/you/npm-global/lark-cli.cmd
FEISHU_IM_IDENTITY=bot
```

Optional GUI default:

```env
PAPERFLOW_WRITE_FEISHU=true
```

`PAPERFLOW_WRITE_FEISHU` only controls whether the GUI checkbox is enabled by
default. The CLI is controlled by `--no-feishu`.

## Feishu App Requirements

In the Feishu/Lark developer console:

1. Create or select a Feishu/Lark app.
2. Copy its `App ID` into `FEISHU_APP_ID`.
3. Copy its `App Secret` into `FEISHU_APP_SECRET`.
4. Enable permissions needed for creating cloud documents.
5. If you also want PaperFlow to send the document link to a chat, enable bot
   messaging permissions and add the bot to the target chat.

If `lark-cli` reports `permission_violations`, open the `console_url` from the
error and enable the listed scopes. That error is the most reliable source of
the exact missing permission for your app.

## lark-cli Smoke Test

Dry run, no real document is created:

```bash
lark-cli docs +create --as bot --title "PaperFlow Feishu smoke test" --markdown "hello" --dry-run
```

Create a real tiny test document:

```bash
lark-cli docs +create --as bot --title "PaperFlow Feishu smoke test" --markdown "hello"
```

## CLI Usage

Create local Markdown and a Feishu document:

```bash
paperflow read 1 --user-id user_role1
```

Only create local Markdown:

```bash
paperflow read 1 --user-id user_role1 --no-feishu
```

Create the Feishu document in a specific folder:

```bash
paperflow read 1 --user-id user_role1 --folder-id <feishu_folder_token>
```

The folder token comes from a URL like:

```text
https://.../drive/folder/<feishu_folder_token>
```

Optionally send the created document link to a Feishu user:

```bash
paperflow read 1 --user-id user_role1 --feishu-user-id ou_xxxxxxxxx
```

For this notification step, the bot must be able to message that user or chat.
If using private messages, the user should first send any message to the bot so
Feishu has an existing one-on-one conversation.

## GUI Usage

Start the GUI:

```bash
paperflow gui
```

In the daily-push or direct-reading panels, tick:

```text
同时尝试写入飞书文档
```

Checked means: generate local Markdown, then attempt Feishu doc creation.

Unchecked means: generate local Markdown only.

## Not Covered Here

This document does not cover:

- Feishu users sending messages to the PaperFlow bot
- Feishu event callbacks
- daily scheduled bot delivery
- ngrok webhook exposure

Those belong to [feishu-webhook-setup.md](feishu-webhook-setup.md).
