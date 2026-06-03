# Feedback and Profile Learning

PaperFlow treats feedback as a shared learning signal. Whether the user replies
through the CLI, local GUI, or Feishu/Lark bot, the signal is stored in the same
local database and updates the same user profile for that `user_id`.

## Feedback Entry Points

| Surface | User action | Profile effect |
| --- | --- | --- |
| CLI | `paperflow feedback --user-id ... --push-id ... --reply "1 3"` | Updates selected/skipped paper signals and drift state |
| GUI | Select papers, mark "not interested", then submit | Updates selected/skipped paper signals and drift state |
| Feishu/Lark bot | Reply with numbers like `1 3`, ranges like `1-5`, or `none` | Routes to the same feedback agent and updates the same profile |
| Reading report | Run `paperflow read`, read an arXiv ID, or read a local PDF | Adds a conservative reading-side interest signal |
| Reading-report quality feedback | Send positive/negative report feedback in Feishu chat | Updates report-style preferences in the profile |

The important rule is that the `user_id` is the identity boundary. Feedback only
updates the profile for the matching user or role.

## What Gets Updated

Feedback can update:

- `topic_weights` and other profile interest weights
- selected/skipped behavior history
- short-term and long-term drift state
- reading signal state for papers that were deeply read
- local wiki nodes/edges when `PAPERFLOW_WIKI_INGEST=true`
- report-style preferences when the feedback is about reading-report quality

## CLI Flow

```bash
paperflow daily --user-id user_alice
paperflow feedback \
  --user-id user_alice \
  --push-id push_20260601_090000 \
  --reply "1 3"
```

This records papers `1` and `3` as selected. On the first feedback for a push,
the remaining unselected papers are treated as weak skipped signals. Later
amendments only add newly selected papers, so a second reply does not erase the
first selection.

Use:

```bash
paperflow feedback --user-id user_alice --push-id push_20260601_090000 --reply "none"
```

to explicitly say none of the pushed papers were useful.

## GUI Flow

In `paperflow gui`, the daily-push panel has two explicit actions:

- select papers to read
- mark papers as not interested

Submitting either action records behavior logs, updates the profile, and
refreshes local wiki metadata. If "提交并精读" is used, selected papers also
generate reading reports after the feedback update.

## Feishu/Lark Flow

In the webhook bot, chat messages such as `1 3`, `1-5`, `none`, `全部`, and
`没有` are parsed as feedback. The bot resolves the current role/user from the
chat context and then calls the same feedback agent used by the CLI.

That means a Feishu reply and this CLI command are equivalent learning signals
when they target the same `user_id` and push:

```bash
paperflow feedback --user-id user_alice --push-id <latest_push_id> --reply "1 3"
```

Feishu delivery requires webhook/ngrok only for receiving chat events. The
profile update itself is local and stored in `data/paperflow.db`.

## Reading Signals

Reading reports are also profile signals, but they are handled more
conservatively than explicit selection feedback. When a user runs `paperflow
read`, reads an arXiv paper in the GUI, or uploads/reads a local PDF, PaperFlow
can reinforce the detected paper topics through the reading-signal state.

This helps the system learn from "I actually read this" without treating every
deep read as a hard preference shift.

## Local Wiki

When `PAPERFLOW_WIKI_INGEST=true`, feedback and drift updates are mirrored into
the local wiki:

- paper nodes record selected/skipped/read behavior
- trajectory nodes record push and drift transitions
- topic nodes connect repeated themes

Run:

```bash
paperflow wiki backfill --user-id user_alice
paperflow wiki stats --user-id user_alice
```

to import older runtime history and inspect the stored signal counts.
