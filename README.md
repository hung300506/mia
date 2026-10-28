# 🎴 Mimi Helper Bot

A Discord Bot that assists with **Mimi bot** (`<@1476927725775356037>`) card drops and card stats evaluation.

## ✨ Features

- 🔔 **Auto-ping Role**: Alerts your configured role when Mimi self-drops cards.
- 📊 **Card Stats Evaluator**: Reply to Mimi's card message or collection page with `!calc` or `calc`.
- 📚 **Collection Page Support**: Evaluates multiple cards in collection views and outputs a clean, concise breakdown.
- ⚙️ **Slash Commands** (`/setup`): Easy configuration per server.
- 🏠 **Per-server Config**: Customizable settings saved per guild.
- 📌 **Custom Channel**: Send pings to the drop channel or a designated alert channel.
- 🔄 **Toggle Switch**: Enable or disable the bot on demand.

## 🚀 Installation & Setup

### 1. Create a Bot on the Discord Developer Portal

1. Visit https://discord.com/developers/applications
2. Create a new Application → go to the **Bot** tab.
3. Copy the **Bot Token**.
4. Enable **Privileged Gateway Intents**:
   - ✅ Message Content Intent
   - ✅ Server Members Intent
5. Generate an invite link (**OAuth2 → URL Generator**):
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Read Messages/View Channels`, `Manage Messages`

### 2. Install Dependencies

```bash
cd quick-franklin

pip install -r requirements.txt

# Create .env from template
copy .env.example .env

# Edit .env and paste your DISCORD_BOT_TOKEN
```

### 3. Run the Bot

```bash
python bot.py
```

## 📖 Usage Guide

### Slash Commands (Recommended)

| Command | Description |
|---|---|
| `/setup role @Role` | Set the role to ping on card drops |
| `/setup channel #channel` | Set a notification channel (optional) |
| `/setup toggle True/False` | Enable or disable the bot |
| `/setup status` | View current server configuration |

### Prefix Commands

| Command | Description |
|---|---|
| `!calc` | Evaluate card stats (reply to a Mimi card or collection page) |
| `!help calc` | View detailed instructions and evaluation formula |
| `!setrole @Role` | Set ping role |
| `!removerole` | Remove ping role |
| `!botstatus` | View bot status |

> **Note:** Setup commands require **Manage Server** permissions.

## 🔄 How It Works

1. The bot monitors messages in configured server channels.
2. When Mimi drops cards (`dropped X cards!`), the bot pings the configured role.
3. When users reply to Mimi's card message or collection page with `!calc` or `calc`:
   - **Single Card View**: Displays detailed progress bars for each stat (HP, ATK, DEF, SPD), max stats, and overall rating.
   - **Collection View (Multi-Card)**: Displays a concise summary list evaluating each card with its code, level, stat percentages, and overall rating, plus page average.
4. **Evaluation Formula**:
   $$\text{Stat Rating} = \frac{\text{Current} - \text{Min}}{\text{Max} - \text{Min}} \times 100\%$$
   $$\text{Overall Rating} = \frac{\text{Rating}_{\text{HP}} + \text{Rating}_{\text{ATK}} + \text{Rating}_{\text{DEF}} + \text{Rating}_{\text{SPD}}}{4}$$

## 📁 Project Structure

```
quick-franklin/
├── bot.py              # Main bot implementation
├── test_bot.py         # Test bot script
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
├── .env                # Private configuration & token
├── discloud.config     # Discloud hosting config
├── Procfile            # Cloud Procfile
└── data/
    └── config.json     # Per-server persistent configuration
```
