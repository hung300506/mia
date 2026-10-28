"""
Mimi Helper Test Bot - Card Stat Evaluator & Drop Helper
Test Bot Token: mia beta (ID: 1564671154382311454)
"""

import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import logging
import asyncio
from dotenv import load_dotenv

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("TestBot")

# ─── Load Environment / Token ──────────────────────────────
load_dotenv(".env.test")
TOKEN = os.getenv("TEST_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TEST_BOT_TOKEN not found in .env.test")

MIMI_BOT_ID = 1476927725775356037

# ─── Stat Constants ─────────────────────────────────────────
# I, Chỉ số gốc (Lv 1)
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


def evaluate_card(stats: dict[str, int], level: int = 1):
    """
    Evaluate current stats against min and max stat ranges.
    Returns percentage for each stat and overall average rating.
    """
    ranges, num_ascends = calculate_stats_range(level, stats=stats)

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
    # Xóa custom emojis <:name:id> và <a:name:id>
    text = re.sub(r"<a?:[a-zA-Z0-9_]+:[0-9]+>", " ", text)
    # Xóa mentions người dùng / role <@123456>
    text = re.sub(r"<@!?[0-9]+>", " ", text)
    # Chuẩn hóa khoảng trắng đặc biệt (ideographic space U+3000, non-breaking space U+00A0)
    text = text.replace("\u3000", " ").replace("\u00a0", " ")
    # Xóa markdown formatting: *, _, `, ~ để tránh làm đứt regex
    text = re.sub(r"[*_`~]", "", text)
    return text


def extract_stat(name: str, cleaned_text: str) -> int | None:
    # Match name followed by optional spaces, colon/separator, spaces, and digits
    m = re.search(rf"\b{name}\b\s*[:：=]?\s*([\d,]+)", cleaned_text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def parse_card_from_text(full_text: str):
    """
    Trích xuất tên card, level, và 4 stats từ chuỗi text / embed.
    """
    cleaned = clean_discord_text(full_text)

    # 1. Level (mặc định 1 nếu không tìm thấy)
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
        # Thử tìm tên card dạng #ID hoặc dòng đầu
        m_id = re.search(r"#(\d+)", cleaned)
        if m_id:
            name = f"Card #{m_id.group(1)}"

    # 3. 4 Stats
    stats = {}
    for s in ["HP", "ATK", "DEF", "SPD"]:
        val = extract_stat(s, cleaned)
        if val is None:
            return None, None, None
        stats[s] = val

    return name, level, stats


def extract_card_from_message(msg: discord.Message):
    """
    Trích xuất thông tin card từ Discord message (content + embeds).
    """
    text_parts = []
    if msg.content:
        text_parts.append(msg.content)

    image_url = None

    for embed in msg.embeds:
        if embed.title:
            text_parts.append(embed.title)
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
    name, level, stats = parse_card_from_text(full_text)
    return name, level, stats, image_url


def build_evaluation_embed(name: str, eval_data: dict, image_url: str | None = None) -> discord.Embed:
    """
    Build a Discord Embed to display card evaluation results.
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
        # Format: current stats / max stat (evaluation %)
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


# ─── Bot Setup ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
)


@bot.event
async def on_ready():
    log.info(f"✅ Test Bot Online: {bot.user} (ID: {bot.user.id})")
    log.info(f"   Connected to {len(bot.guilds)} server(s)")
    try:
        synced = await bot.tree.sync()
        log.info(f"   Synced {len(synced)} slash command(s)")
    except Exception as e:
        log.error(f"   Failed to sync slash commands: {e}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Mimi cards 📊 | @bot calc",
        )
    )


@bot.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author.id == bot.user.id:
        return

    # Check card stats evaluation request
    await handle_calc_request(message)

    # Process standard prefix commands
    await bot.process_commands(message)


async def handle_calc_request(message: discord.Message):
    """
    Handle card calculation requests when replying to a Mimi card message with `<@bot> calc` or `!calc` / `calc`.
    """
    content = message.content.strip().lower()
    is_mentioned = bot.user in message.mentions or f"<@{bot.user.id}>" in message.content or f"<@!{bot.user.id}>" in message.content
    has_calc_word = "calc" in content

    should_trigger = False
    if has_calc_word and is_mentioned:
        should_trigger = True
    elif content.startswith("!calc") or content.startswith(".calc"):
        should_trigger = True
    elif message.reference and content == "calc":
        should_trigger = True

    if not should_trigger:
        return

    log.info(f"🔍 Received calc request from {message.author} in #{message.channel}")

    target_msg = None
    # 1. If replying to another message
    if message.reference:
        try:
            if message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                target_msg = message.reference.resolved
            elif message.reference.message_id:
                target_msg = await message.channel.fetch_message(message.reference.message_id)
        except Exception as e:
            log.warning(f"❌ Could not fetch referenced message: {e}")

    # Log debug info of target message
    if target_msg:
        log.info(f"Target Msg ID: {target_msg.id} | Author: {target_msg.author} | Embeds count: {len(target_msg.embeds)}")
    else:
        log.info("No target_msg (not a reply or fetch failed)")

    # 2. Extract card data
    name, level, stats, image_url = None, None, None, None

    if target_msg:
        name, level, stats, image_url = extract_card_from_message(target_msg)
        log.info(f"Extract from target: Name={name}, Level={level}, Stats={stats}")

    # 3. If referenced message has no card, check if user pasted card text directly in their message
    if stats is None:
        name, level, stats = parse_card_from_text(message.content)
        if stats:
            log.info(f"Extract from user msg: Name={name}, Level={level}, Stats={stats}")

    # 4. If card stats still not found
    if stats is None:
        help_text = (
            "⚠️ **Card stats could not be found!**\n"
            "👉 **How to use:** **Reply** to Mimi's card message and type `@Mia calc` (or `!calc`).\n"
            "*You can also paste the card text directly into your message along with `calc`.*"
        )
        await message.reply(help_text, mention_author=False)
        return

    # 5. Evaluate card stats and send result
    eval_data = evaluate_card(stats, level=level)
    embed = build_evaluation_embed(name, eval_data, image_url=image_url)

    await message.reply(embed=embed, mention_author=False)
    log.info(f"   ✅ Evaluation complete: {name} (Lv.{level}) - Rating: {eval_data['avg_pct']:.2f}%")


# ─── Slash Command /calc (Manual) ─────────────────────────
@bot.tree.command(name="calc", description="Manually evaluate card stats")
@app_commands.describe(
    hp="HP stat",
    atk="ATK stat",
    def_="DEF stat",
    spd="SPD stat",
    level="Card level (1 - 150, default: 1)",
    name="Card name (optional)",
)
async def slash_calc(
    interaction: discord.Interaction,
    hp: int,
    atk: int,
    def_: int,
    spd: int,
    level: int = 1,
    name: str = "Custom Card",
):
    stats = {"HP": hp, "ATK": atk, "DEF": def_, "SPD": spd}
    eval_data = evaluate_card(stats, level=level)
    embed = build_evaluation_embed(name, eval_data)
    await interaction.response.send_message(embed=embed)


# ─── Main Entry Point ─────────────────────────────────────
async def main():
    log.info("🔌 Starting Test Bot...")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
