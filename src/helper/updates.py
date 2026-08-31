

import discord
import aiohttp
import asyncio
from src.globals import bot, DEFAULT_PLATFORM, API_MAX_RETRIES
from src.helper.helper import log, build_api_url
from src.ranks.ranks import get_rank_name, get_rank_value_from_data, assign_rank_role, remove_rank_role
from src.data.data import load_data, save_data


def get_player_entry(data: dict, guild_id: int, discord_id: int):
    """
    Returns {"name": ..., "platform": ...} for a linked discord id, or None.
    Old entries were plain strings (just the EA name) - normalize those to
    the new dict shape so both formats keep working.
    """
    entry = data.get(str(guild_id)).get(str(discord_id))
    if entry is None:
        return None
    if isinstance(entry, str):
        return {"name": entry, "platform": DEFAULT_PLATFORM}
    return entry

async def fetch_player_stats(guild: discord.Guild, session: aiohttp.ClientSession, name: str):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries transient failures up to API_MAX_RETRIES times. "Player not found" is treated as
    permanent (bad name/platform) and fails immediately without retrying."""

    last_error = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url(name)
            async with session.get(API_URL) as response:
                if response.status != 200:
                    raise Exception(f'{response}')

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")

                return stats

        except Exception as e:
            last_error = e
            if attempt <= API_MAX_RETRIES:
                # max time is 126sec with 6 attempts. S = 2(2**6-1)/(2-1)
                await asyncio.sleep(2 ** attempt)
            continue

    log(guild, f"ERROR! [Attempt {attempt}/{API_MAX_RETRIES}] {name}: {last_error}")
    return None


async def _update_member(guild: discord.Guild, member: discord.Member, session: aiohttp.ClientSession):
    """
    Updates a single member's Discord rank roles based on their linked external game stats.

    Steps:
    1. Validates member eligibility (skips bots and unlinked accounts).
    2. Fetches external player stats and resolves their career rank name.
    3. Assigns the new rank role and strips obsolete rank roles in the guild.

    Returns:
        dict: A status map containing {'success': bool} along with 'value' (details),
              plus role update results on success.

    return_value = {
        "success": bool,
        "value": string,
        "assign_rank_role": dict,
        "remove_rank_role": dict,
    }

    """
    await bot.wait_until_ready()

    return_msg = {'success': True}

    if member.bot:
        # log(guild, fail_msg := f"❌ Trying to update a bot. What the helly.")
        return return_msg | {'success': False, 'value': f"❌ Trying to update a bot. What the helly."}

    if not (entry := get_player_entry(load_data(), guild.id, member.id)):
        # log(guild, fail_msg := f"❌ Not linked. Skipping.")
        return return_msg | {'success': False, 'value': f"❌ Not linked. Skipping."}

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)

    if not (stats := await fetch_player_stats(guild, session, name)):
        # log(guild, fail_msg := f"⚠️ Data fetch failed. If link is correct, do not stress, API failure.")
        return return_msg | {'success': False, 'value': f"⚠️ Data fetch failed. If link is correct, do not stress, API failure."}

    rankValue = get_rank_value_from_data(stats)
    if rankValue is None:
        # log(guild, fail_msg := f"[WARNING] Could not extract rank.")
        return return_msg | {'success': False, 'value': f"[WARNING] Could not extract rank."}

    concise_rank_name = get_rank_name(rankValue)

    # lol
    data = load_data()
    data[str(guild.id)][str(member.id)].update({
        'rank_name': concise_rank_name,
        'career_rank': rankValue
    })
    save_data(data)

    return_msg['assign_rank_role'] = await assign_rank_role(guild, member, concise_rank_name)
    if not return_msg['assign_rank_role']['success']:
        # log(guild, msg := return_msg['assign_rank_role']['value'])
        return return_msg | {'success': False, 'value': f'{return_msg['assign_rank_role']['value']}'}

    return_msg['remove_rank_role'] = await remove_rank_role(guild, member, concise_rank_name)
    if not return_msg['remove_rank_role']['success']:
        # log(guild, msg := return_msg['remove_rank_role']['value'])
        return return_msg | {'success': False, 'value': f'{return_msg['remove_rank_role']['value']}'}

    # log(guild, success_msg := )
    return return_msg | {'value': f'✅ Update successful for `{member.name}`'}





