import sys
import discord
sys.stdout.reconfigure(encoding="utf-8")
from test_bot import evaluate_card, parse_card_from_text

sample_mimi_text = """
Zhuang Fangyi | Level : 1/150

Element: Verdant 🟢
Ability: Regenerate — Restore 2% max HP at the start of each of the next 4 turns.
In team battles, remaining regen ticks carry to the next card.

Arknights: Endfield • 30W26 • #752 • @P H

STATS
❤️ HP : 5,081  ⚔️ ATK : 982
🛡️ DEF : 705  🏃 SPD : 457

XP: 0 / 60
"""

name, level, stats = parse_card_from_text(sample_mimi_text)
print(f"Parsed: Name={name}, Level={level}, Stats={stats}")

eval_data = evaluate_card(stats, level=level)
print("\n=== EVALUATION RESULT ===")
for stat in ["HP", "ATK", "DEF", "SPD"]:
    d = eval_data["details"][stat]
    val, max_v, pct, min_v = d["val"], d["max"], d["pct"], d["min"]
    print(f"{stat}: {val:,} / {max_v:,} ({pct:.2f}%) [Min: {min_v:,}]")

print(f"\nAverage %: {eval_data['avg_pct']:.2f}%")
print(f"Ascends: {eval_data['ascends']}")

# Test case with tricky ability containing HP, ATK, DEF, SPD before **STATS**
tricky_mimi_text = """
Kafka | Level : 80/150

Element: Lightning ⚡
Ability: Overload — Deals ATK: 50 bonus damage and restores HP: 10. Lowers enemy DEF: 20 and SPD: 5.

Honkai: Star Rail • #1249 • @Player

**STATS**
❤️ HP : 10,240  ⚔️ ATK : 2,150
🛡️ DEF : 1,480  🏃 SPD : 720

XP: 120 / 300
"""

name2, level2, stats2 = parse_card_from_text(tricky_mimi_text)
print(f"\nTricky Card Parsed: Name={name2}, Level={level2}, Stats={stats2}")
assert stats2 == {"HP": 10240, "ATK": 2150, "DEF": 1480, "SPD": 720}, f"Stats mismatch! Got {stats2}"
print("✅ Test 1 passed! False stats in ability were ignored, correct stats extracted from after **STATS**.")

# Test case with multi-card collection page view
from bot import parse_collection_from_text, build_collection_evaluation_embed, bot as main_bot

collection_text = """
1. ⠀ • PS99V :verdant: Chrollo Lucilfer • Hunter x Hunter • Halloween 2026
P48 • Lv.1 A0 • Verdant • ⚡ Fortify
❤️ 4,956 · ⚔️ 1,000 · 🛡️ 731 · 🏃 547
2. ⠀ • K0Q4Y :ember: Nicole • Genshin Impact
P1235 • Lv.1 A0 • Ember • ⚡ Rage
❤️ 5,217 · ⚔️ 1,041 · 🛡️ 677 · 🏃 462
3. ⠀ • GIQ59 :umbra: Wiz • KonoSuba
P1248 • Lv.1 A0 • Umbra • ⚡ Corrupt
❤️ 5,080 · ⚔️ 966 · 🛡️ 691 · 🏃 528
4. ⠀ • NPCGJ :tide: Oguri Cap • Umamusume: Pretty Derby
P1272 • Lv.1 A0 • Tide • ⚡ Freeze
❤️ 5,220 · ⚔️ 1,038 · 🛡️ 690 · 🏃 548
5. ⠀ • 6ZLQ1 :lumen: Seele Vollerei • Honkai Impact
P1225 • Lv.1 A0 • Lumen • ⚡ Bless
❤️ 5,114 · ⚔️ 1,029 · 🛡️ 740 · 🏃 506
6. ⠀ • WLXA0 :verdant: Uruha Rushia • Hololive
P1202 • Lv.1 A0 • Verdant • ⚡ Fortify
❤️ 4,962 · ⚔️ 1,034 · 🛡️ 666 · 🏃 507
7. ⠀ • XPKT6 :verdant: Tamaki Kotatsu • Fire Force
P1265 • Lv.1 A0 • Verdant • ⚡ Shield
❤️ 5,087 · ⚔️ 1,031 · 🛡️ 724 · 🏃 505
"""

cards = parse_collection_from_text(collection_text)
print(f"\nCollection Parsed: {len(cards)} cards")
assert len(cards) == 7, f"Expected 7 cards, got {len(cards)}"
assert cards[0]["name"] == "Chrollo Lucilfer" and cards[0]["code"] == "PS99V"
assert cards[0]["stats"] == {"HP": 4956, "ATK": 1000, "DEF": 731, "SPD": 547}
assert cards[3]["name"] == "Oguri Cap" and cards[3]["code"] == "NPCGJ"
assert cards[6]["name"] == "Tamaki Kotatsu" and cards[6]["code"] == "XPKT6"

embed = build_collection_evaluation_embed(cards)
print("Collection Embed Title:", embed.title)
print("Collection Embed Description preview:\n" + embed.description[:300] + "...")
print("Collection Embed Footer:", embed.footer.text)
print("✅ Test 2 passed! Collection cards parsed and concise embed built.")

# Test case 2B: Real Mimi collection format with backticks around numbers (`8.`, `9.`, etc.)
real_mimi_collection_text = """📋 .hwng.'s Full Collection
`8.` ⠀ • `YURKR` <:tide:1489915367425052783> **Furina** • *Genshin Impact*
     P**1221** • Lv.**1** A0 • Tide • ⚡ Heal
     ❤️ **5,110** · ⚔️ **958** · 🛡️ **734** · 🏃 **459**
`9.` ⠀ • `PS99V` <:verdant:1489915484987064350> **Chrollo Lucilfer** • *Hunter x Hunter* • Halloween 2026
     P**48** • Lv.**1** A0 • Verdant • ⚡ Fortify
     ❤️ **4,956** · ⚔️ **1,000** · 🛡️ **731** · 🏃 **547**
`10.` ⠀ • `K0Q4Y` <:ember:1489915403978408026> **Nicole** • *Genshin Impact*
     P**1235** • Lv.**1** A0 • Ember • ⚡ Rage
     ❤️ **5,217** · ⚔️ **1,041** · 🛡️ **677** · 🏃 **462**
`11.` ⠀ • `GIQ59` <:umbra:1489915281945137162> **Wiz** • *KonoSuba*
     P**1248** • Lv.**1** A0 • Umbra • ⚡ Corrupt
     ❤️ **5,080** · ⚔️ **966** · 🛡️ **691** · 🏃 **528**
`12.` ⠀ • `NPCGJ` <:tide:1489915367425052783> **Oguri Cap** • *Umamusume: Pretty Derby*
     P**1272** • Lv.**1** A0 • Tide • ⚡ Freeze
     ❤️ **5,220** · ⚔️ **1,038** · 🛡️ **690** · 🏃 **548**
`13.` ⠀ • `6ZLQ1` <:lumen:1489915233601323139> **Seele Vollerei** • *Honkai Impact*
     P**1225** • Lv.**1** A0 • Lumen • ⚡ Bless
     ❤️ **5,114** · ⚔️ **1,029** · 🛡️ **740** · 🏃 **506**
`14.` ⠀ • `WLXA0` <:verdant:1489915484987064350> **Uruha Rushia** • *Hololive*
     P**1202** • Lv.**1** A0 • Verdant • ⚡ Fortify
     ❤️ **4,962** · ⚔️ **1,034** · 🛡️ **666** · 🏃 **507**
Page 2/150 • 1047 cards"""

cards_real = parse_collection_from_text(real_mimi_collection_text)
assert len(cards_real) == 7, f"Expected 7 cards, got {len(cards_real)}"
assert cards_real[0]["name"] == "Furina" and cards_real[0]["code"] == "YURKR"
assert cards_real[0]["idx"] == 8 and cards_real[0]["level"] == 1
assert cards_real[0]["stats"] == {"HP": 5110, "ATK": 958, "DEF": 734, "SPD": 459}
print("✅ Test 2B passed! Real Mimi collection with backticks `8.` parsed perfectly.")

# Test case: !help calc command registration & removal of paste / slash command
cmd = main_bot.get_command("calc")
assert cmd is not None, "calc command not registered in bot!"
assert "(Current - Min)" in cmd.brief
assert "(Current Stat - Min)" in cmd.help
assert "paste" not in cmd.help.lower(), "calc help still mentions pasting text!"
assert "/calc" not in cmd.help, "calc help still mentions /calc slash command!"
assert main_bot.tree.get_command("calc") is None, "/calc slash command should be removed!"
print("✅ Test 3 passed! `!help calc` command registered with clean usage (no paste, no /calc) and formula.")

# Test case 5: Async test of handle_calc_request
import asyncio
from unittest.mock import AsyncMock, MagicMock

async def test_calc_handlers():
    # Mock referenced Mimi collection message
    target_msg = MagicMock(spec=discord.Message)
    target_msg.content = collection_text
    target_msg.embeds = []
    target_msg.reference = None

    # Case A: User replies to Mimi with Discord auto-mention of Mimi: "<@1476927725775356037> calc"
    user_msg_reply = MagicMock(spec=discord.Message)
    user_msg_reply.author.bot = False
    user_msg_reply.author.name = "Tester"
    user_msg_reply.channel.name = "bot-commands"
    user_msg_reply.channel.fetch_message = AsyncMock(return_value=target_msg)
    user_msg_reply.content = "<@1476927725775356037> calc"
    user_msg_reply.mentions = []
    user_msg_reply.reference = MagicMock()
    user_msg_reply.reference.resolved = target_msg
    user_msg_reply.reference.message_id = 999999
    user_msg_reply.reply = AsyncMock()

    from bot import handle_calc_request
    await handle_calc_request(user_msg_reply)
    assert user_msg_reply.reply.called, "Reply was not called for '<@1476927725775356037> calc'!"
    embed_sent = user_msg_reply.reply.call_args.kwargs.get("embed")
    assert embed_sent is not None and "Collection Card Stats Evaluation" in embed_sent.title
    print("✅ Test 5A passed! Reply with Mimi mention '<@1476927725775356037> calc' properly handled.")

    # Case B: User replies with "<@1476927725775356037> !calc"
    user_msg_reply_2 = MagicMock(spec=discord.Message)
    user_msg_reply_2.author.bot = False
    user_msg_reply_2.author.name = "Tester"
    user_msg_reply_2.channel.name = "bot-commands"
    user_msg_reply_2.channel.fetch_message = AsyncMock(return_value=target_msg)
    user_msg_reply_2.content = "<@1476927725775356037> !calc"
    user_msg_reply_2.mentions = []
    user_msg_reply_2.reference = MagicMock()
    user_msg_reply_2.reference.resolved = target_msg
    user_msg_reply_2.reference.message_id = 999999
    user_msg_reply_2.reply = AsyncMock()

    await handle_calc_request(user_msg_reply_2)
    assert user_msg_reply_2.reply.called
    print("✅ Test 5B passed! Reply with Mimi mention '<@1476927725775356037> !calc' properly handled.")

    # Case C: User types "!calc" without replying
    user_msg_no_reply = MagicMock(spec=discord.Message)
    user_msg_no_reply.author.bot = False
    user_msg_no_reply.author.name = "Tester"
    user_msg_no_reply.channel.name = "bot-commands"
    user_msg_no_reply.content = "!calc"
    user_msg_no_reply.mentions = []
    user_msg_no_reply.reference = None
    user_msg_no_reply.reply = AsyncMock()

    await handle_calc_request(user_msg_no_reply)
    assert user_msg_no_reply.reply.called
    reply_text = user_msg_no_reply.reply.call_args.args[0]
    assert "Please reply to a Mimi card message" in reply_text
    print("✅ Test 5C passed! '!calc' without reply prompts user to reply to Mimi.")

    # Case D: User sends bare 'calc' or 'calc!' without reply
    user_msg_bare = MagicMock(spec=discord.Message)
    user_msg_bare.author.bot = False
    user_msg_bare.author.name = "Tester"
    user_msg_bare.channel.name = "bot-commands"
    user_msg_bare.content = "calc!"
    user_msg_bare.mentions = []
    user_msg_bare.reference = None
    user_msg_bare.reply = AsyncMock()

    await handle_calc_request(user_msg_bare)
    assert user_msg_bare.reply.called
    assert "Please reply to a Mimi card message" in user_msg_bare.reply.call_args.args[0]
    print("✅ Test 5D passed! Bare 'calc!' without reply prompts user to reply to Mimi.")

    # Case E: User pastes card text directly
    user_msg_paste = MagicMock(spec=discord.Message)
    user_msg_paste.author.bot = False
    user_msg_paste.author.name = "Tester"
    user_msg_paste.channel.name = "bot-commands"
    user_msg_paste.content = "Zhuang Fangyi | Level: 1/150\n**STATS**\n❤️ HP : 5,081 ⚔️ ATK : 982\n🛡️ DEF : 705 🏃 SPD : 457\ncalc"
    user_msg_paste.mentions = []
    user_msg_paste.reference = None
    user_msg_paste.reply = AsyncMock()

    await handle_calc_request(user_msg_paste)
    assert user_msg_paste.reply.called
    embed_sent = user_msg_paste.reply.call_args.kwargs.get("embed")
    assert embed_sent is not None and "Zhuang Fangyi" in embed_sent.title
    print("✅ Test 5E passed! Direct card paste with 'calc' evaluated successfully.")

asyncio.run(test_calc_handlers())


