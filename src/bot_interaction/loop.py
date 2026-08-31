# loop
import discord
import aiohttp
from discord.ext import tasks
from src.globals import bot, running_loops
from src.data.config import load_config
from src.data.data import load_data
from src.helper.helper import check_guild_requirements, log
from src.helper.updates import _update_member
from src.helper.message_builder import _build_update_summary
from src.ranks.ranks import _has_rank_change


async def _run_guild_update(guild: discord.Guild, on_progress=None, only_report_changes: bool = False) -> dict:
    """Runs one full update pass over every member of a guild, assigning/removing rank roles.
    Resolves the guild's configured report channel itself, so callers just pass a guild.

    on_progress, if given, is an async callable(updated_count, total_linked) invoked after
    each successful member update - used for live progress reporting (e.g. editing a message).

    only_report_changes, when True, drops successful-but-unchanged members from the returned
    summary so callers only see members whose rank role was actually assigned/removed. Failed
    updates are always included regardless of this flag. Used by the automatic loop.
    """
    check = check_guild_requirements(guild)
    if not check["ok"]:
        fail_msg = "❌ [ERROR STARTING AUTOMATIC UPDATE]: " + " | ".join(check["issues"])
        log(guild, fail_msg)
        return {'success': False, 'value': fail_msg}

    player_update_summary_list: list = []
    failed_player_updates_summary_list: list = []
    linked_member_ids = list(load_data().get(str(guild.id)).keys())

    log(guild, f"[START AUTOMATIC UPDATE] Total linked: {len(linked_member_ids)} member{'' if len(linked_member_ids)==1 else 's'}.")
    async with aiohttp.ClientSession() as session:
        for idx, member_id in enumerate(linked_member_ids):
            member = guild.get_member(int(member_id))

            try:
                return_value: dict = await _update_member(guild, member, session)
                member_update_msg = _build_update_summary(return_value)

                if on_progress:
                    await on_progress(len(player_update_summary_list), len(linked_member_ids), idx == (len(linked_member_ids) - 1))

                if not return_value['success']:
                    raise Exception(f'❌ Update failed for `{member}`: {return_value['value']}')

                if not only_report_changes or _has_rank_change(return_value):
                    player_update_summary_list.append(f'\n{member_update_msg}')

            except Exception as e:
                log(guild, summary := f'{e}')
                failed_player_updates_summary_list.append(f'\n{summary}')

    log(guild, f"[FINISHED AUTOMATIC UPDATE] Updated {len(player_update_summary_list)} member{'' if len(player_update_summary_list) == 1 else 's'}.")
    return {'success': True, 'value': ', '.join(player_update_summary_list), 'failed_player_updates_summary_list': ', '.join(failed_player_updates_summary_list)}

def _make_guild_update_loop(guild_id: int, interval_hours: float) -> tasks.Loop:
    if not interval_hours:
        log(bot.get_guild(guild_id), f'{interval_hours} is not valid. Returning.')
        return

    if not guild_id:
        log(bot.get_guild(guild_id), f'{guild_id} is not valid. Returning.')
        return

    @tasks.loop(hours=interval_hours)
    async def _loop():
        await bot.wait_until_ready()

        guild = bot.get_guild(guild_id)
        if guild is None:
            log(guild, f"[ERROR] Guild {guild_id} no longer accessible, stopping its update loop.")
            _loop.cancel()
            return

        if not (channel := bot.get_channel(load_config().get(str(guild.id), {}).get('channel_id'))):
            log(guild, 'Channel is not set.')
            return _loop

        return_value = await _run_guild_update(guild, only_report_changes=True)

        success_msg = return_value.get('value')
        failed_msg = return_value.get('failed_player_updates_summary_list')

        if not success_msg and not failed_msg:
            log(guild, 'No updated members.')
            return _loop

        try:
            # try because channel.send might raise error if channel not set or some permission missing. both cases should already be covered.
            if failed_msg:
                await channel.send(failed_msg)

            if success_msg:
                log(guild, channel_msg := f"{success_msg}")
                await channel.send(channel_msg)

        except Exception as e:
            log(guild, f'Error at automatic loop sending channel msg: {e}')

    return _loop

def start_guild_update_loop(guild: discord.Guild):
    """Starts (or restarts) the automatic update loop for one guild, using its configured interval."""
    loop = _make_guild_update_loop(guild.id, load_config().get(str(guild.id)).get('update_interval'))
    running_loops[guild.id] = loop
    loop.start()

def restart_guild_update_loop(guild: discord.Guild):
    """Call this after update_interval changes in config, so the new interval takes effect."""
    existing = running_loops.get(guild.id)
    if existing:
        existing.cancel()
    start_guild_update_loop(guild)
