"""
Mimi Helper Bot - Discord Bot
Main function: Ping a role when Mimi bot drops cards (self-drop only).
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import logging
import asyncio
from aiohttp import web
from dotenv import load_dotenv
from pathlib import Path

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("MimiHelper")

# ─── Load environment ─────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

# ─── Constants ─────────────────────────────────────────────
MIMI_BOT_ID = 1476927725775356037  # Mimi bot ID
DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "config.json"

# Pattern to detect Mimi's self-drop message
# Example: "<@1476927725775356037> dropped 3 cards! ..."
# Only matches when Mimi mentions itself (self-drop)
DROP_PATTERN = re.compile(
    rf"<@!?{MIMI_BOT_ID}>\s+dropped\s+\d+\s+cards?!",
    re.IGNORECASE,
)


# ─── Config Manager ───────────────────────────────────────
class ConfigManager:
    """Per-server (guild) config manager, saved to JSON file."""

    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = self._load()

    # --- persistence ---
    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # --- public API ---
    def get_guild(self, guild_id: int) -> dict:
        return self._data.setdefault(str(guild_id), {})

    def set_ping_role(self, guild_id: int, role_id: int):
        self.get_guild(guild_id)["ping_role_id"] = role_id
        self._save()

    def get_ping_role(self, guild_id: int) -> int | None:
        return self.get_guild(guild_id).get("ping_role_id")

    def remove_ping_role(self, guild_id: int):
        guild = self.get_guild(guild_id)
        guild.pop("ping_role_id", None)
        self._save()

    def set_ping_channel(self, guild_id: int, channel_id: int):
        self.get_guild(guild_id)["ping_channel_id"] = channel_id
        self._save()

    def get_ping_channel(self, guild_id: int) -> int | None:
        return self.get_guild(guild_id).get("ping_channel_id")

    def remove_ping_channel(self, guild_id: int):
        guild = self.get_guild(guild_id)
        guild.pop("ping_channel_id", None)
        self._save()

    def set_enabled(self, guild_id: int, enabled: bool):
        self.get_guild(guild_id)["enabled"] = enabled
        self._save()

    def is_enabled(self, guild_id: int) -> bool:
        return self.get_guild(guild_id).get("enabled", True)


# ─── Bot Setup ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=commands.DefaultHelpCommand(no_category="Commands"),
)
config = ConfigManager()


# ─── Events ───────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info(f"✅ Bot is online: {bot.user} (ID: {bot.user.id})")
    log.info(f"   Connected to {len(bot.guilds)} server(s)")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Mimi drops 👀",
        )
    )


@bot.command(name="sync", help="Sync slash commands (owner only)")
@commands.is_owner()
async def cmd_sync(ctx: commands.Context):
    """Manually sync slash commands. Run once: !sync"""
    synced = await bot.tree.sync()
    await ctx.send(f"✅ Synced {len(synced)} slash command(s).")


@bot.event
async def on_message(message: discord.Message):
    # Ignore DMs
    if not message.guild:
        return

    # Check if message is from Mimi bot
    if message.author.id == MIMI_BOT_ID:
        await _handle_mimi_message(message)

    # Still process prefix commands
    await bot.process_commands(message)


async def _handle_mimi_message(message: discord.Message):
    """Handle Mimi bot messages — ping role only on Mimi self-drops."""
    guild_id = message.guild.id

    # Check if bot is enabled in this server
    if not config.is_enabled(guild_id):
        return

    # Check message content + embeds
    content = message.content or ""

    embed_texts = []
    for embed in message.embeds:
        if embed.description:
            embed_texts.append(embed.description)
        if embed.title:
            embed_texts.append(embed.title)

    full_text = content + " " + " ".join(embed_texts)

    # Only trigger on Mimi SELF-drops (Mimi mentions itself)
    if not DROP_PATTERN.search(full_text):
        return

    log.info(f"🎴 Mimi self-drop detected in #{message.channel.name} ({message.guild.name})")

    # Get ping role
    role_id = config.get_ping_role(guild_id)
    if not role_id:
        log.warning(f"   No ping role set for server {message.guild.name}")
        return

    role = message.guild.get_role(role_id)
    if not role:
        log.warning(f"   Role ID {role_id} not found in server {message.guild.name}")
        return

    # Determine which channel to send ping in
    ping_channel_id = config.get_ping_channel(guild_id)
    if ping_channel_id:
        channel = message.guild.get_channel(ping_channel_id)
        if not channel:
            channel = message.channel  # fallback
    else:
        channel = message.channel  # default: same channel as drop

    # Send ping
    try:
        if channel.id != message.channel.id:
            ping_msg = await channel.send(
                f"🎴 {role.mention} **Mimi is dropping cards!**\n"
                f"👉 Grab them in {message.channel.mention}!"
            )
        else:
            ping_msg = await channel.send(
                f"🎴 {role.mention} **Mimi is dropping cards!** Grab them! ⬆️"
            )
        log.info(f"   ✅ Pinged {role.name} in #{channel.name}")

        # Auto-delete ping after 30 seconds to reduce spam
        await ping_msg.delete(delay=30)
    except discord.Forbidden:
        log.error(f"   ❌ Missing permissions to send messages in #{channel.name}")
    except Exception as e:
        log.error(f"   ❌ Error sending ping: {e}")


# ─── Slash Commands ───────────────────────────────────────

setup_group = app_commands.Group(
    name="setup",
    description="Configure Mimi Helper Bot",
    default_permissions=discord.Permissions(manage_guild=True),
)


@setup_group.command(name="role", description="Set the role to ping when Mimi drops cards")
@app_commands.describe(role="The role to ping on card drops")
async def setup_role(interaction: discord.Interaction, role: discord.Role):
    config.set_ping_role(interaction.guild_id, role.id)
    embed = discord.Embed(
        title="✅ Ping role set",
        description=f"{role.mention} will be pinged whenever Mimi drops cards.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="Tip: Use /setup channel to set a separate notification channel")
    await interaction.response.send_message(embed=embed)
    log.info(f"⚙️ Server {interaction.guild.name}: ping role set → {role.name}")


@setup_group.command(name="channel", description="Set a separate channel for ping notifications (optional)")
@app_commands.describe(channel="Notification channel (leave empty = same channel as drop)")
async def setup_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if channel:
        config.set_ping_channel(interaction.guild_id, channel.id)
        embed = discord.Embed(
            title="✅ Ping channel set",
            description=f"Notifications will be sent in {channel.mention}.",
            color=discord.Color.green(),
        )
    else:
        config.remove_ping_channel(interaction.guild_id)
        embed = discord.Embed(
            title="✅ Ping channel reset",
            description="Notifications will be sent in the same channel as the drop.",
            color=discord.Color.green(),
        )
    await interaction.response.send_message(embed=embed)


@setup_group.command(name="toggle", description="Enable or disable the bot in this server")
@app_commands.describe(enabled="Enable (True) or disable (False) the bot")
async def setup_toggle(interaction: discord.Interaction, enabled: bool):
    config.set_enabled(interaction.guild_id, enabled)
    status = "🟢 **ENABLED**" if enabled else "🔴 **DISABLED**"
    embed = discord.Embed(
        title="⚙️ Bot Status",
        description=f"Bot has been {status}",
        color=discord.Color.green() if enabled else discord.Color.red(),
    )
    await interaction.response.send_message(embed=embed)


@setup_group.command(name="status", description="View current bot configuration")
async def setup_status(interaction: discord.Interaction):
    guild_id = interaction.guild_id

    # Role
    role_id = config.get_ping_role(guild_id)
    if role_id:
        role = interaction.guild.get_role(role_id)
        role_text = role.mention if role else f"⚠️ Role deleted (ID: {role_id})"
    else:
        role_text = "❌ Not set — use `/setup role`"

    # Channel
    ch_id = config.get_ping_channel(guild_id)
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        ch_text = ch.mention if ch else f"⚠️ Channel deleted (ID: {ch_id})"
    else:
        ch_text = "📌 Same channel as Mimi drop"

    # Enabled
    enabled = config.is_enabled(guild_id)
    status_text = "🟢 Enabled" if enabled else "🔴 Disabled"

    embed = discord.Embed(
        title="📋 Mimi Helper Bot Configuration",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Status", value=status_text, inline=True)
    embed.add_field(name="Ping Role", value=role_text, inline=True)
    embed.add_field(name="Notification Channel", value=ch_text, inline=False)
    embed.add_field(
        name="Watching Bot",
        value=f"<@{MIMI_BOT_ID}> (`{MIMI_BOT_ID}`)",
        inline=False,
    )
    embed.set_footer(text="Use /setup role, /setup channel, /setup toggle to change settings")
    await interaction.response.send_message(embed=embed)


bot.tree.add_command(setup_group)


# ─── Prefix Commands (backup) ─────────────────────────────

@bot.command(name="setrole", help="Set the ping role (mention the role). Example: !setrole @CardPing")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def cmd_setrole(ctx: commands.Context, role: discord.Role):
    config.set_ping_role(ctx.guild.id, role.id)
    await ctx.send(f"✅ Ping role set: {role.mention}")


@bot.command(name="removerole", help="Remove the configured ping role")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def cmd_removerole(ctx: commands.Context):
    config.remove_ping_role(ctx.guild.id)
    await ctx.send("✅ Ping role removed.")


@bot.command(name="botstatus", help="View current bot configuration")
@commands.guild_only()
async def cmd_status(ctx: commands.Context):
    role_id = config.get_ping_role(ctx.guild.id)
    enabled = config.is_enabled(ctx.guild.id)
    role_text = f"<@&{role_id}>" if role_id else "Not set"
    await ctx.send(
        f"**Bot Status:** {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        f"**Ping Role:** {role_text}"
    )


# ─── Error handlers ──────────────────────────────────────
@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need **Manage Server** permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `!help {ctx.command}` for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument. Please check and try again.")
    else:
        log.error(f"Command error: {error}")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need **Manage Server** permission to use this command.", ephemeral=True
        )
    else:
        log.error(f"App command error: {error}")
        await interaction.response.send_message(
            "❌ An error occurred. Please try again.", ephemeral=True
        )


# ─── Health Check Web Server (keeps Render free tier alive) ─
async def health_handler(request):
    return web.Response(text="OK")


async def start_webserver():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"   Health check server running on port {port}")


# ─── Run ──────────────────────────────────────────────────
async def main():
    await start_webserver()

    max_retries = 10
    delay = 30  # start with 30 seconds

    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"🔌 Connecting to Discord... (attempt {attempt}/{max_retries})")
            async with bot:
                await bot.start(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                log.warning(f"⏳ Rate limited! Waiting {delay}s before retry...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 600)  # double wait, max 10 min
            else:
                log.error(f"❌ HTTP error: {e}")
                await asyncio.sleep(30)
        except Exception as e:
            log.error(f"❌ Unexpected error: {e}")
            await asyncio.sleep(30)

    log.error("❌ Max retries reached. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
