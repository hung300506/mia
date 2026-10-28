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
    # Remove markdown formatting: *, _, `, ~ to avoid regex breaking
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
        parts = first_line.split("•")

        code = None
        name = None

        if len(parts) >= 2:
            # Mimi bullet structure:
            # parts[0]: Index + optional custom tags/emojis (e.g. "2. 👜💰" or "4. :heaven:")
            # parts[1]: Code + Element Emoji + Character Name (e.g. "73L :tide: Chisa")
            # parts[2]: Series Name (e.g. "Wuthering Waves")
            part1 = parts[1]
            clean1 = re.sub(r"<a?:[a-zA-Z0-9_]+:\d+>", " ", part1)
            clean1 = re.sub(r":[a-zA-Z0-9_]+:", " ", clean1)
            clean1 = clean1.replace("\u2800", " ").replace("\u3000", " ").replace("\u00a0", " ")
            clean1 = re.sub(r"[*_`~]", "", clean1).strip()

            # Match code (2 to 7 alphanumeric uppercase) followed by character name
            m = re.match(r"^([A-Z0-9]{2,7})\s+(.+)$", clean1)
            if m:
                code = m.group(1)
                name = m.group(2).strip()
            else:
                name = clean1

        # Fallback if structure didn't have bullets or didn't yield name
        if not name:
            clean_line = re.sub(r"<a?:[a-zA-Z0-9_]+:\d+>", " ", first_line)
            clean_line = re.sub(r":[a-zA-Z0-9_]+:", " ", clean_line)
            clean_line = clean_line.replace("\u2800", " ").replace("\u3000", " ").replace("\u00a0", " ")
            clean_line = re.sub(r"^\s*`?\d+[\.\)]`?\s*", "", clean_line)
            clean_line = re.sub(r"[*_`~]", "", clean_line)

            m_code = re.search(r"(?:•|^|\s)([A-Z0-9]{2,7})\b", clean_line)
            code = m_code.group(1) if m_code else None

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
        # Try finding card name as #ID
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

    # Process standard prefix commands
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


# ─── Prefix Command !calc (Help & Backup) ─────────────────
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


# ─── Main Entry Point ─────────────────────────────────────
async def main():
    log.info("🔌 Starting Test Bot...")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
