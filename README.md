# 🧠 Second Brain — Capture & Recall MVP

A Slack-native cognitive system that captures messages, classifies them with AI, and provides dual search (vector + keyword) through a local web dashboard.

## Prerequisites

- **Python 3.11+**
- **Slack App** — Bot token with `channels:history`, `im:history`, `users:read`, `chat:write` scopes
- **Hugging Face Account** — Free API token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
- **Qdrant Cloud Account** — Free tier at [cloud.qdrant.io](https://cloud.qdrant.io)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd second_brain

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# Install in editable mode
pip install -e ".[dev]"
```

## Configuration

```bash
# Copy the example env file
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

Edit `.env` and fill in your tokens:

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack bot token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | Channel ID to monitor (`C0123456789`) |
| `SLACK_COLLECT_DMS` | Also collect bot DMs (`true`/`false`) |
| `HF_API_TOKEN` | Hugging Face API token (`hf_...`) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app (or select your existing one)
2. Navigate to **OAuth & Permissions** → **Bot Token Scopes** and add:
   - `channels:history` — read messages in public channels
   - `groups:history` — read messages in private channels
   - `mpim:history` — read messages in group DMs
   - `im:history` — read bot direct messages
   - `users:read` — resolve user display names
   - `chat:write` — (optional, for future features)
3. Click **Install to Workspace** (or **Reinstall** if you added new scopes)
4. Copy the **Bot User OAuth Token** (`xoxb-...`) into your `.env` as `SLACK_BOT_TOKEN`
5. To find your channel ID: right-click the channel in Slack → **View channel details** → scroll to the bottom to find the Channel ID (`C0123456789`)
6. **Invite the bot** to your channel: in the channel, type `/invite @YourBotName`

## Running

```bash
# Activate the virtual environment first
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# Using the entry point
second-brain

# Or directly
python -m src.main
```

The dashboard opens at **http://localhost:8000**.

On startup, the app:
1. Initializes the SQLite database (creates tables if needed)
2. Connects to Qdrant Cloud (creates the vector collection if needed)
3. Runs a Slack catch-up — fetches new messages since the last run
4. Starts the web server on `127.0.0.1:8000`

If the Slack catch-up fails (e.g., missing scopes), the dashboard still starts — you can use manual capture and fix Slack later.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `missing_scope` from Slack | Bot token lacks required OAuth scopes | Add scopes in Slack app settings → reinstall → copy new token |
| `403 Forbidden` from Qdrant | Invalid API key | Copy the API key from Qdrant Cloud dashboard → paste into `.env` |
| `Port 8000 already in use` | Previous instance still running | Kill Python processes or use a different port |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -e ".[dev]"` |
| `No module named 'src'` | Not running from project root | `cd` to the project directory first |
| Slack catch-up returns 0 messages | Bot not invited to channel | Type `/invite @YourBotName` in the Slack channel |

## Usage

- **Dashboard** — Left panel shows the capture feed (newest first). Right panel has search + today's digest.
- **Search** — Type in the search box for live dual search (vector similarity + keyword matching). Results show source badges: 🧲 vector, 🔤 keyword, 🧲🔤 both.
- **Refresh** — Click 🔄 Refresh to pull new messages from Slack.
- **Manual Capture** — Type a thought in the capture input and click 💾 Capture.
- **Copy** — Click 📋 Copy on any search result to copy title + summary to clipboard.
- **Slack Link** — Click 🔗 on any entry to open the original Slack message.

## Architecture

See the [tech spec](_bmad-output/implementation-artifacts/tech-spec-second-brain-mvp-capture-recall.md) for full details.

```
Slack ──poll──▶ Collector ──▶ Pipeline ──▶ Classifier (HF API)
                                  │              │
                                  ▼              ▼
                              SQLite          Qdrant Cloud
                             (FTS5)          (vectors)
                                  │              │
                                  └──────┬───────┘
                                         ▼
                                Dashboard (FastAPI + htmx)
```

## Development

```bash
# Run tests
pytest

# Run with debug logging
LOG_LEVEL=DEBUG second-brain
```

## Entry Types

| Type | Emoji | Description |
|------|-------|-------------|
| Idea | 💡 | New ideas and concepts |
| Task | ✅ | Actionable tasks |
| Decision | ⚖️ | Decisions made |
| Risk | ⚠️ | Identified risks |
| Arch Note | 🏗️ | Architecture notes |
| Strategy | 🎯 | Strategic thinking |
| Note | 📝 | General notes |
| Unclassified | ❓ | Classification failed (error state) |
