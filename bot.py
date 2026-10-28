"""
Mimi Helper Bot - Discord Bot
Features:
1. Ping a role when Mimi bot drops cards (self-drop only).
2. Card stats evaluator: reply to Mimi card with `@bot calc` or `!calc` / `/calc`.
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
DROP_PATTERN = re.compile(
    rf"<@!?{MIMI_BOT_ID}>\s+dropped\s+\d+\s+cards?!",
    re.IGNORECASE,
)

# ─── Stat Constants ─────────────────────────────────────────
# I, Base stats at Lv 1 (Min: 4750/950/650/450, Max: 5250/1050/750/550)
BASE_STATS = {
    "HP": (4750, 5250),
    "ATK": (950, 1050),
    "DEF": (650, 750),
    "SPD": (450, 550),
}

# II, Stat gains per level (max level 150)
PER_LEVEL = {
    "HP": (40, 70),
    "ATK": (8, 15),
    "DEF": (5, 10),
    "SPD": (3, 8),
}

# III, Ascend milestones and bonus %
# Milestones: 20/50/80/100/120/150
# Bonus: 20%/25%/30%/35%/40%/50%
ASCEND_TIERS = [
    (20, 0.20),
    (50, 0.25),
    (80, 0.30),
    (100, 0.35),
    (120, 0.40),
    (150, 0.50),
]


# ─── Stat Calculator ────────────────────────────────────────
def calculate_stats_range(level: int, stats: dict[str, int] | None = None, num_ascends: int | None = None):
    """
    Calculate min and max range for each stat at a given level.
    Auto-detects ascend tier if num_ascends is not explicitly provided.
    """
    level = max(1, min(150, level))

    def _get_ranges_for(asc_count: int):
        res = {}
        for s in ["HP", "ATK", "DEF", "SPD"]:
            min_v, max_v = BASE_STATS[s]
            min_g, max_g = PER_LEVEL[s]
            curr = 1
            for i, (m, b) in enumerate(ASCEND_TIERS):
                if i < asc_count:
                    target = min(level, m)
                    min_v += (target - curr) * min_g
                    max_v += (target - curr) * max_g
                    curr = target
                    min_v *= (1 + b)
                    max_v *= (1 + b)
                else:
                    break
            if curr < level:
                min_v += (level - curr) * min_g
                max_v += (level - curr) * max_g
            res[s] = (round(min_v), round(max_v))
        return res

    if num_ascends is None:
        base_ascends = 0
        for milestone, _ in ASCEND_TIERS:
            if level > milestone:
                base_ascends += 1
            else:
                break

        # Check if exactly at an ascend milestone
        is_milestone = any(level == m for m, _ in ASCEND_TIERS)
        if is_milestone and stats:
            def score_candidate(cand_ascends):
                r = _get_ranges_for(cand_ascends)
                penalty = 0.0
                for s, (min_v, max_v) in r.items():
                    val = stats.get(s, (min_v + max_v) / 2)
                    pct = ((val - min_v) / (max_v - min_v)) * 100.0
                    if pct < 0:
                        penalty += abs(pct) * 2.0
                    elif pct > 100:
                        penalty += (pct - 100.0) * 2.0
                    else:
                        penalty += abs(pct - 50.0) * 0.1
                return penalty

            if score_candidate(base_ascends + 1) < score_candidate(base_ascends):
                base_ascends += 1

        num_ascends = base_ascends

    return _get_ranges_for(num_ascends), num_ascends


def evaluate_card(stats: dict[str, int], level: int = 1, num_ascends: int | None = None):
    """
    Evaluate current stats against min and max stat ranges.
    Returns percentage for each stat and overall average rating.
    """
    ranges, num_ascends = calculate_stats_range(level, stats=stats, num_ascends=num_ascends)

    details = {}
    total_pct = 0.0

    for stat in ["HP", "ATK", "DEF", "SPD"]:
        val = stats.get(stat, 0)
        min_v, max_v = ranges[stat]
        if max_v > min_v:
            pct = ((val - min_v) / (max_v - min_v)) * 100.0
        else:
            pct = 100.0
        pct = max(0.0, min(100.0, pct))  # clamp 0-100%
        details[stat] = {
            "val": val,
            "min": min_v,
            "max": max_v,
            "pct": pct,
        }
        total_pct += pct

    avg_pct = total_pct / 4.0

    # Color indicator based on percentage
    if avg_pct >= 85:
        color = 0xFFD700  # Gold
    elif avg_pct >= 75:
        color = 0xFFA500  # Orange
    elif avg_pct >= 65:
        color = 0x9B59B6  # Purple
    elif avg_pct >= 50:
        color = 0x3498DB  # Blue
    elif avg_pct >= 40:
        color = 0x2ECC71  # Green
    else:
        color = 0x95A5A6  # Gray

    return {
        "level": level,
        "ascends": num_ascends,
        "details": details,
        "avg_pct": avg_pct,
        "color": color,
    }


def make_progress_bar(pct: float, length: int = 10) -> str:
    filled = int(round((pct / 100.0) * length))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


# ─── Card Text / Embed Parser ──────────────────────────────
def clean_discord_text(text: str) -> str:
    # Remove custom emojis <:name:id> and <a:name:id>
    text = re.sub(r"<a?:[a-zA-Z0-9_]+:[0-9]+>", " ", text)
    # Remove user / role mentions <@123456>
    text = re.sub(r"<@!?[0-9]+>", " ", text)
    # Normalize special whitespace (ideographic space U+3000, non-breaking space U+00A0, braille space U+2800)
    text = text.replace("\u2800", " ").replace("\u3000", " ").replace("\u00a0", " ")
    # Remove markdown formatting: *, _, `, ~
    text = re.sub(r"[*_`~]", "", text)
    return text


def extract_stat(name: str, cleaned_text: str) -> int | None:
    # Match stat name followed by optional spaces, separator, spaces, and digits
    m = re.search(rf"\b{name}\b\s*[:：=]?\s*([\d,]+)", cleaned_text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_stats_from_line(text: str) -> dict[str, int] | None:
    """Extract HP, ATK, DEF, SPD from a line containing emojis or stat names."""
    # Clean markdown formatting (*, _, `, ~) and special spaces first
    clean = re.sub(r"[*_`~]", "", text)
    clean = clean.replace("\u2800", " ").replace("\u3000", " ").replace("\u00a0", " ")

    hp = re.search(r"(?:❤️|❤|:heart:|HP)\s*[:：=]?\s*([\d,]+)", clean, re.I)
    atk = re.search(r"(?:⚔️|⚔|:crossed_swords:|ATK)\s*[:：=]?\s*([\d,]+)", clean, re.I)
    defe = re.search(r"(?:🛡️|🛡|:shield:|DEF)\s*[:：=]?\s*([\d,]+)", clean, re.I)
    spd = re.search(r"(?:🏃‍♂️|🏃‍♀️|🏃|:runner:|SPD)\s*[:：=]?\s*([\d,]+)", clean, re.I)

    if hp and atk and defe and spd:
        try:
            return {
                "HP": int(hp.group(1).replace(",", "")),
                "ATK": int(atk.group(1).replace(",", "")),
                "DEF": int(defe.group(1).replace(",", "")),
                "SPD": int(spd.group(1).replace(",", "")),
            }
        except ValueError:
            return None
    return None


def parse_collection_from_text(full_text: str) -> list[dict]:
    """
    Parse a collection / inventory page containing multiple cards from Mimi.
    Returns list of card dicts with idx, code, name, level, ascend, stats.
    """
    chunks = re.split(r"(?:\n|^)\s*(?=`?\d+[\.\)]`?)", full_text.strip())
    cards = []
    for chunk in chunks:
        stats = extract_stats_from_line(chunk)
        if not stats:
            continue

        # Index (supports `1.` or 1. or `1)` or 1))
        m_idx = re.match(r"^\s*`?(\d+)[\.\)]`?", chunk)
        if not m_idx:
            continue
        idx = int(m_idx.group(1))

        # Code & Name from first line
        first_line = chunk.strip().split("\n")[0]
        # Clean custom discord emojis and text emojis
        clean_line = re.sub(r"<a?:[a-zA-Z0-9_]+:\d+>", " ", first_line)
        clean_line = re.sub(r":[a-zA-Z0-9_]+:", " ", clean_line)
        clean_line = clean_line.replace("\u2800", " ").replace("\u3000", " ").replace("\u00a0", " ")
        clean_line = re.sub(r"^\s*`?\d+[\.\)]`?\s*", "", clean_line)
        clean_line = re.sub(r"[*_`~]", "", clean_line)

        # Code: 4-7 uppercase alphanumeric after bullet or start
        m_code = re.search(r"(?:•|^|\s)([A-Z0-9]{4,7})\b", clean_line)
        code = m_code.group(1) if m_code else None

        name = None
        if code:
            m_name = re.search(rf"\b{code}\b\s*([^•\n]+?)(?:\s*•|\n|$)", clean_line)
            if m_name and m_name.group(1).strip():
                name = m_name.group(1).strip()

        if not name:
            m_name2 = re.search(r"(?:•|^)\s*([^•\n]+?)(?:\s*•|\n|$)", clean_line)
            if m_name2 and m_name2.group(1).strip():
                name = m_name2.group(1).strip()

        if not name:
            name = f"Card #{idx}"

        name = re.sub(r"^[•\-\s]+|[•\-\s]+$", "", name)

        # Clean whole chunk for Level & Ascend (in case Lv.**1** A0 has markdown)
        clean_chunk = re.sub(r"[*_`~]", "", chunk)
        m_lvl = re.search(r"Lv\.?\s*[:：]?\s*(\d+)", clean_chunk, re.I)
        level = int(m_lvl.group(1)) if m_lvl else 1

        m_asc = re.search(r"\bA(\d+)\b", clean_chunk, re.I)
        ascend = int(m_asc.group(1)) if m_asc else None

        cards.append({
            "idx": idx,
            "code": code,
            "name": name,
            "level": level,
            "ascend": ascend,
            "stats": stats,
        })
    return cards


def parse_card_from_text(full_text: str):
    """
    Extract card name, level, and 4 stats from text or embed content.
    """
    cleaned = clean_discord_text(full_text)

    # 1. Level (default: 1)
    level = 1
    m_lvl = re.search(r"(?:Level|Lv\.?)\s*[:：]?\s*(\d+)", cleaned, re.IGNORECASE)
    if m_lvl:
        try:
            level = int(m_lvl.group(1))
        except ValueError:
            level = 1

    # 2. Card Name
    name = "Card"
    m_name = re.search(r"^(.*?)\s*\|\s*(?:Level|Lv\.?)", cleaned, re.MULTILINE | re.IGNORECASE)
    if m_name and m_name.group(1).strip():
        name = m_name.group(1).strip()
    else:
        m_id = re.search(r"#(\d+)", cleaned)
        if m_id:
            name = f"Card #{m_id.group(1)}"

    # 3. 4 Stats
    # Ignore text before **STATS** to prevent false matches from abilities, descriptions, etc.
    stats_text = cleaned
    m_stats = re.search(r"(?:^|\n)\s*[#*_\s]*STATS[*_\s:]*(?:\n|$)", cleaned, re.IGNORECASE)
    if not m_stats:
        m_stats = re.search(r"\bSTATS\b", cleaned)
    if m_stats:
        stats_text = cleaned[m_stats.end():]

    stats = {}
    for s in ["HP", "ATK", "DEF", "SPD"]:
        val = extract_stat(s, stats_text)
        if val is None:
            return None, None, None
        stats[s] = val

    return name, level, stats


def extract_message_content(msg: discord.Message):
    """
    Extract full text, image URL, and page title from a Discord message (content + embeds).
    """
    text_parts = []
    if msg.content:
        text_parts.append(msg.content)

    image_url = None
    page_title = None

    for embed in msg.embeds:
        if embed.title:
            text_parts.append(embed.title)
            if not page_title:
                page_title = embed.title
        if embed.author and embed.author.name:
            text_parts.append(embed.author.name)
        if embed.description:
            text_parts.append(embed.description)
        for field in embed.fields:
            text_parts.append(f"{field.name}: {field.value}")
        if embed.footer and embed.footer.text:
            text_parts.append(embed.footer.text)
        if embed.image and embed.image.url:
            image_url = embed.image.url
        elif embed.thumbnail and embed.thumbnail.url:
            image_url = embed.thumbnail.url

    full_text = "\n".join(text_parts)
    return full_text, image_url, page_title


def extract_card_from_message(msg: discord.Message):
    """
    Extract single card information from a Discord message (content + embeds).
    """
    full_text, image_url, _ = extract_message_content(msg)
    name, level, stats = parse_card_from_text(full_text)
    return name, level, stats, image_url


def build_collection_evaluation_embed(cards: list[dict], page_title: str | None = None) -> discord.Embed:
    """
    Build a concise Discord Embed to display evaluations for multiple cards in a collection.
    """
    lines = []
    total_avg = 0.0

    for c in cards:
        eval_data = evaluate_card(c["stats"], level=c["level"], num_ascends=c.get("ascend"))
        avg = eval_data["avg_pct"]
        total_avg += avg
        d = eval_data["details"]

        code = c.get("code")
        code_str = f" (`{code}`)" if code else ""
        asc = eval_data["ascends"]
        asc_str = f" A{asc}" if asc is not None and asc > 0 else ""

        header = f"`{c['idx']}.` **{c['name']}**{code_str} • Lv.{c['level']}{asc_str} — ⭐ **{avg:.2f}%**"
        stat_str = (
            f"❤️ {d['HP']['pct']:.1f}% · "
            f"⚔️ {d['ATK']['pct']:.1f}% · "
            f"🛡️ {d['DEF']['pct']:.1f}% · "
            f"🏃 {d['SPD']['pct']:.1f}%"
        )
        lines.append(f"{header}\n{stat_str}")

    page_avg = total_avg / max(1, len(cards))

    # Color indicator based on page average percentage
    if page_avg >= 85:
        color = 0xFFD700  # Gold
    elif page_avg >= 75:
        color = 0xFFA500  # Orange
    elif page_avg >= 65:
        color = 0x9B59B6  # Purple
    elif page_avg >= 50:
        color = 0x3498DB  # Blue
    elif page_avg >= 40:
        color = 0x2ECC71  # Green
    else:
        color = 0x95A5A6  # Gray

    clean_title = None
    if page_title:
        clean_title = re.sub(r"(?:['’]s\s+)?(?:Full\s+)?Collection", "", page_title, flags=re.IGNORECASE).strip()
        if not re.search(r"\w", clean_title):
            clean_title = None

    title = clean_title if clean_title else f"📊 Card Stats Evaluation ({len(cards)} cards)"
    embed = discord.Embed(
        title=title,
        description="\n\n".join(lines),
        color=color,
    )
    embed.set_footer(
        text=f"{len(cards)} card(s) evaluated"
    )
    return embed


def build_evaluation_embed(name: str, eval_data: dict, image_url: str | None = None) -> discord.Embed:
    """
    Build a Discord Embed to display card evaluation results in English.
    """
    level = eval_data["level"]
    ascends = eval_data["ascends"]
    avg_pct = eval_data["avg_pct"]
    color = eval_data["color"]
    d = eval_data["details"]

    ascend_text = f" • Ascend A{ascends}" if ascends > 0 else ""

    embed = discord.Embed(
        title=f"📊 Card Stats Evaluation: {name}",
        description=f"**Level:** `{level}/150`{ascend_text}\n"
                    f"**Rating:** **{avg_pct:.2f}%**",
        color=color,
    )

    stat_icons = {
        "HP": "❤️",
        "ATK": "⚔️",
        "DEF": "🛡️",
        "SPD": "🏃",
    }

    lines = []
    for s in ["HP", "ATK", "DEF", "SPD"]:
        val = d[s]["val"]
        max_v = d[s]["max"]
        pct = d[s]["pct"]
        bar = make_progress_bar(pct, length=8)
        lines.append(
            f"{stat_icons[s]} **{s}:** `{val:,}` / `{max_v:,}` (**{pct:.2f}%**) `{bar}`"
        )

    embed.add_field(
        name="Stats Breakdown (Current / Max)",
        value="\n".join(lines),
        inline=False,
    )

    embed.add_field(
        name="📈 Overall Rating",
        value=f"⭐ **{avg_pct:.2f}%**",
        inline=True,
    )

    if image_url:
        embed.set_thumbnail(url=image_url)

    return embed


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
            name="Mimi drops & card stats 👀",
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

    # Debug log for messages mentioning calc
    if "calc" in message.content.lower():
        log.info(
            f"📨 Calc detected in msg #{message.id} from {message.author} in #{message.channel}: "
            f"content={message.content!r}, has_ref={bool(message.reference)}"
        )

    # Check card stats evaluation request
    handled = await handle_calc_request(message)
    if handled:
        return

    # Check if message is from Mimi bot (drop card ping)
    if message.author.id == MIMI_BOT_ID:
        await _handle_mimi_message(message)

    # Still process prefix commands
    await bot.process_commands(message)


async def handle_calc_request(message: discord.Message) -> bool:
    """
    Handle card calculation requests when replying to a Mimi card message or collection page with `!calc` or `calc`.
    Returns True if handled, False otherwise.
    """
    if message.author.bot:
        return False

    # Clean mentions to see actual command words
    clean_content = re.sub(r"<@!?[0-9]+>|<@&[0-9]+>", " ", message.content).strip().lower()
    words = [w.strip("!.,?:;`~") for w in clean_content.split()]

    # 1. Starts with command prefix: !calc, .calc, /calc, ?calc, $calc
    has_cmd_prefix = bool(re.search(r"(?:^|\s)[!\.\/\?\$]calc\b", clean_content))

    # 2. Contains word 'calc'
    has_calc_word = "calc" in words

    # 3. Bot is mentioned directly
    is_bot_mentioned = (
        (bot.user and bot.user in message.mentions)
        or (bot.user and f"<@{bot.user.id}>" in message.content)
        or (bot.user and f"<@!{bot.user.id}>" in message.content)
    )

    # 4. Message contains card stats keywords (pasted card text)
    has_stats_keywords = ("hp" in clean_content and "atk" in clean_content) or "stats" in clean_content

    should_trigger = False
    if has_cmd_prefix:
        should_trigger = True
    elif is_bot_mentioned and has_calc_word:
        should_trigger = True
    elif message.reference and has_calc_word:
        should_trigger = True
    elif has_calc_word and has_stats_keywords:
        should_trigger = True
    elif clean_content in ["calc", "calc!", "calc?", "calc.", "/calc", "!calc", ".calc"]:
        should_trigger = True

    if not should_trigger:
        return False

    log.info(f"🔍 Received calc request from {message.author} in #{message.channel}")

    try:
        target_msg = None
        # 1. Fetch referenced message
        if message.reference:
            try:
                if message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                    target_msg = message.reference.resolved
                if (not target_msg or (not target_msg.content and not target_msg.embeds)) and message.reference.message_id:
                    target_msg = await message.channel.fetch_message(message.reference.message_id)
            except Exception as e:
                log.warning(f"❌ Could not fetch referenced message: {e}")

        # 2. Extract card or collection data from target message or user message fallback
        cards, name, level, stats, image_url, page_title = None, None, None, None, None, None

        if target_msg:
            full_text, image_url, page_title = extract_message_content(target_msg)
            cards = parse_collection_from_text(full_text)
            if not cards:
                name, level, stats = parse_card_from_text(full_text)

        # Fallback: Check if user pasted card stats in their own message
        if not cards and stats is None:
            user_text, user_img, user_title = extract_message_content(message)
            cards = parse_collection_from_text(user_text)
            if not cards:
                name, level, stats = parse_card_from_text(user_text)
            if cards or stats is not None:
                image_url = user_img
                page_title = user_title

        # 3. If card stats still not found
        if not cards and stats is None:
            if not target_msg:
                help_text = (
                    "⚠️ **Please reply to a Mimi card message or collection page!**\n"
                    "👉 **How to use:** Click **Reply** on Mimi's card message or collection page and type `!calc` (or `calc`)."
                )
            else:
                help_text = (
                    "⚠️ **Card stats could not be found in the referenced message!**\n"
                    "👉 Please ensure you are replying directly to a Mimi card message or collection page."
                )
            await message.reply(help_text, mention_author=False)
            return True

        # 4. Evaluate card stats and send result
        if cards and len(cards) > 0:
            embed = build_collection_evaluation_embed(cards, page_title=page_title)
            await message.reply(embed=embed, mention_author=False)
            log.info(f"   ✅ Collection evaluation complete: {len(cards)} card(s)")
        else:
            eval_data = evaluate_card(stats, level=level)
            embed = build_evaluation_embed(name, eval_data, image_url=image_url)
            await message.reply(embed=embed, mention_author=False)
            log.info(f"   ✅ Evaluation complete: {name} (Lv.{level}) - Rating: {eval_data['avg_pct']:.2f}%")
        return True
    except Exception as e:
        log.error(f"❌ Error handling calc request: {e}", exc_info=True)
        await message.reply("⚠️ An unexpected error occurred while calculating card stats. Please try again.", mention_author=False)
        return True


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
            await channel.send(
                f"🎴 {role.mention} **Mimi is dropping cards!**\n"
                f"👉 Grab them in {message.channel.mention}!"
            )
        else:
            await channel.send(
                f"🎴 {role.mention} **Mimi is dropping cards!** Grab them! ⬆️"
            )
        log.info(f"   ✅ Pinged {role.name} in #{channel.name}")
    except discord.Forbidden:
        log.error(f"   ❌ Missing permissions to send messages in #{channel.name}")
    except Exception as e:
        log.error(f"   ❌ Error sending ping: {e}")


# ─── Slash Commands ───────────────────────────────────────

# --- /setup group ---
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

@bot.command(
    name="calc",
    help=(
        "Evaluate card stats from Mimi (Single card or Collection page).\n\n"
        "How to use:\n"
        "  • Reply to Mimi's card message or collection page with `!calc` (or `calc`).\n\n"
        "Evaluation Formula:\n"
        "  • Stat Rating = (Current Stat - Min) / (Max - Min) * 100%\n"
        "  • Overall Rating = Average percentage of all 4 stats (HP, ATK, DEF, SPD)."
    ),
    brief="Evaluate Mimi card stats: (Current - Min) / (Max - Min)",
)
async def cmd_calc(ctx: commands.Context):
    """Evaluate card stats from Mimi. Formula: (Current - Min) / (Max - Min)"""
    await handle_calc_request(ctx.message)


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


# ─── Health Check Web Server (keeps Render/cloud free tier alive) ─
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
    port = os.getenv("PORT")
    if port:
        await start_webserver()

    log.info("🔌 Connecting to Discord...")
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
