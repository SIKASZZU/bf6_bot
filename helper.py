import json
import aiohttp
import time
import math
from discord.ext import tasks
from discord import app_commands
import asyncio
import datetime

import messages
from globals import *
from ranks import getRankNameFromCareerRank, get_role_dict

_last_command_time = 0


class EmbedPager(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=120)
        self.embeds, self.i = embeds, 0

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.i = (self.i - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.i], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.i = (self.i + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.i], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if getattr(self, "message", None):
            await self.message.edit(view=self)

class WrongChannelError(app_commands.CheckFailure):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"Command must be used in <#{channel_id}>")


def load_data() -> dict:
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_DATA_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}


def save_data(data: dict):
    if not isinstance(data, dict):
        print('Returning! No data provided for save_data.')
        return

    conn = get_conn()
    for key, value in data.items():
        conn.execute(
            f'INSERT OR REPLACE INTO {DB_DATA_FILE} (key, value) VALUES (?, ?)',
            (key, json.dumps(value))
        )
    conn.commit()
    conn.close()


def _embed_pager_kwargs(embeds: list[discord.Embed]) -> dict:
    return {"view": EmbedPager(embeds)} if len(embeds) > 1 else {}


def _get_guild_role_status(guild: discord.Guild) -> list:
    missing_roles: bool = False
    position_below: bool = False

    bot_top_position = guild.me.top_role.position
    for rank_name in get_role_dict().keys():
        role = discord.utils.get(guild.roles, name=rank_name)
        if role is None:
            missing_roles = True
            continue

        if role.position >= bot_top_position:
            position_below = True

        if missing_roles and position_below:
            # all boxes are checked
            break

    return_v: list = []
    if missing_roles:
        return_v.append(f'Missing role(s), run /create-roles.')
    if position_below:
        return_v.append(f"Bot's role is positioned below some role(s) - move the bot's role higher.")
    return return_v


def check_guild_requirements(guild: discord.Guild) -> dict:
    """Checks everything the bot needs to run an update in this guild.

    Returns {"ok": bool, "issues": [str, ...]} - issues is empty when ok is True.
    Call this before _run_guild_update so a whole run fails fast with a clear
    reason instead of dying partway through with a raw Discord exception.
    """
    issues = []

    # 1. Base permission - can the bot manage roles here at all?
    if not guild.me.guild_permissions.manage_roles:
        issues.append("Bot is missing the 'Manage Roles' permission in this server.")

    # 2. Hierarchy - bot's top role must sit above every rank role it assigns/removes.
    #    Checked per-role rather than just "highest rank role" so you get the exact
    #    offending role name instead of a vague pass/fail.
    issues.extend(_get_guild_role_status(guild))

    # 3. Report channel - configured and still resolvable (not deleted).
    channel_id = load_config().get(str(guild.id), {}).get('channel_id')
    if not channel_id:
        issues.append("No report channel configured - run /set-channel.")
    elif not bot.get_channel(channel_id):
        issues.append(f"Configured report channel ({channel_id}) no longer exists or bot can't see it.")

    return {"ok": not issues, "issues": issues}


def _get_time_to_next_update(guild: discord.Guild):
    try:
        loop = running_loops.get(guild.id)
        if loop and loop.next_iteration:
            now = datetime.datetime.now(datetime.timezone.utc)
            time_left = loop.next_iteration - now

            total_seconds = int(time_left.total_seconds())
            if total_seconds < 0:
                return "Starting soon..."

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"

    except Exception as e:
        print(f"Error calculating next update time: {e}")
        return "❌ Needs /set-channel"


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


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    async def send_error(description: str):
        embeds = messages._paginate_lines(
            "❌ Command failed",
            [description],
            discord.Color.red(),
            code_block=False
        )
        kwargs = {"view": EmbedPager(embeds)} if len(embeds) > 1 else {}
        await messages.send_interaction_message(
            interaction,
            embeds[0],
            ephemeral=True,
            **kwargs
        )

    if isinstance(error, WrongChannelError):
        await send_error(f"This command can only be used in <#{error.channel_id}>.")
        return

    if isinstance(error, app_commands.CheckFailure):
        await send_error("You don't have permission to use this command. Requires **Administrator** or the `/show-authorised-role` role.")
        return

    log(interaction.guild, f"Unhandled error in command '{interaction.command.name if interaction.command else '?'}': {error}")
    await send_error(f"An unexpected error occurred: {error}")


async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # 1. DM Guard
    if not interaction.guild:
        return True

    # 2. Rate-limiter / Cooldown check
    global _last_command_time
    now = time.monotonic()
    if now - _last_command_time < COMMAND_REQUEST_COOLDOWN:
        raise app_commands.CheckFailure(f"{COMMAND_REQUEST_COOLDOWN} cooldown after every command!")
    _last_command_time = now

    # Load full configuration safely
    full_config = load_config()
    guild_id_str = str(interaction.guild.id)
    guild_config = full_config.get(guild_id_str, {})

    # 3. Admin-or-role check
    if not interaction.user.guild_permissions.administrator:
        role_id = guild_config.get('permissioned_role_id')
        if not (role_id and discord.utils.get(interaction.user.roles, id=role_id)):
            role = interaction.guild.get_role(role_id) if role_id else None
            role_str = role.mention if role else "a required role"
            raise app_commands.CheckFailure(f"Missing {role_str} or Administrator permissions.")

    # 4. Report-channel restriction
    if (channel_id := guild_config.get('channel_id')):
        if interaction.guild.get_channel(channel_id) is None:
            # Channel deleted - reset setting safely across full config
            guild_config['channel_id'] = None
            full_config[guild_id_str] = guild_config
            save_config(full_config)
            return True

        if interaction.channel.id != channel_id:
            raise WrongChannelError(channel_id)

    return True

bot.tree.interaction_check = global_interaction_check


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}!")

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log(guild, f"Synced {len(synced)} commands to {guild.name} ({guild.id})")

        start_guild_update_loop(guild)


@bot.event
async def on_guild_join(guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    config = load_config()
    server_key = str(guild.id)

    msg = f'[JOINED] bot into {guild.name} id: {guild.id}\n'

    if server_key not in config:
        config[server_key] = {
            "channel_id": None,
            "update_interval": AUTO_UPDATE_TIMER_HOURS
        }
        save_config(config)
        msg += f"Initialized default config configuration for server.\n"

    data = load_data()
    if server_key not in data:
        data[server_key] = {}
        save_data(data)
        msg += f"Initialized default data configuration for server."

    log(guild, msg)
    start_guild_update_loop(guild)


@bot.event
async def on_guild_remove(guild):
    config = load_config()
    server_key = str(guild.id)

    msg = f'[REMOVED] bot from {guild.name} id: {guild.id}\n'

    if server_key in config:
        delete_config_key(server_key)
        msg += f"Removed configuration for server.\n"

    data = load_data()
    if server_key in data:
        delete_data_key(server_key)
        msg += f"Removed saved data for server."

    log(guild, msg)

    existing = running_loops.pop(guild.id, None)
    if existing:
        existing.cancel()


@bot.event
async def on_member_remove(member: discord.Member):
    data = load_data()

    if str(member.guild.id) in data and str(member.id) in data[str(member.guild.id)]:
        del data[str(member.guild.id)][str(member.id)]
        save_data(data)
        log(member.guild, f"[LEFT] `{member.name}` left the guild - removed their link from data.")


async def fetch_player_stats(guild: discord.Guild, session: aiohttp.ClientSession, name: str, platform: str, nucleus_id: str):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries transient failures up to API_MAX_RETRIES times. "Player not found" is treated as
    permanent (bad name/platform) and fails immediately without retrying."""

    last_error = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url(name, platform, nucleus_id)
            async with session.get(API_URL) as response:
                body = await response.text()

                if response.status != 200:
                    raise Exception(
                        f"HTTP {response.status} | "
                        f"URL: {response.url} | "
                        f"Body: {body}"
                    )

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")

                return stats

        except Exception as e:
            last_error = e

            if attempt < API_MAX_RETRIES:
                # max time is 126sec with 6 attempts. S = 2(2**6-1)/(2-1)
                await asyncio.sleep(2 ** attempt)

            continue

    log(guild, f"ERROR! [Attempt {attempt}/{API_MAX_RETRIES}] {name}: {last_error}")
    return None


def get_rank_value_from_data(stats: dict) -> int:
    """
    Extracts rank from the bf6 profile response.

    Public profile:
    {
      "playerProfiles": [
        {
          "playerCard": {"rank": 254, ...},
          "rankName": "Major",
          ...
        }
      ]
    }
    Private profile:
    {
    "other": [
        {
        "playerProfiles": [
            {
            "rank": 134,
            "badges": 81,
            "rankName": "Second Lieutenant IV",
            ...
            }
        ]
        }
    ]
    }
    """

    if not isinstance(stats, dict):
        return None

    profiles = stats.get("playerProfiles")
    if not profiles and isinstance(stats.get("other"), list) and stats["other"]:
        profiles = stats["other"][0].get("playerProfiles")

    if not isinstance(profiles, list) or not profiles:
        return None

    profile = profiles[0]

    player_card = profile.get("playerCard")
    if isinstance(player_card, dict) and "rank" in player_card:
        return player_card.get("rank")

    if "rank" in profile:
        return profile.get("rank")

    return None


async def remove_rank_role(guild: discord.Guild, member: discord.Member, current_rank_name: str) -> dict:
    """
    Removes all obsolete rank roles from a member, keeping only their current rank role.

    return_value = {
        "success": bool,
        "value": string
        "rank_removed": string|None
    }
    """
    all_rank_names = get_role_dict().keys()

    # Identify obsolete roles the member currently holds
    roles_to_remove = [
        role for role in member.roles
        if role.name in all_rank_names and role.name != current_rank_name
    ]

    if not roles_to_remove:
        # log(guild, msg := f"No obsolete rank roles to remove.")
        return {"success": True, "value": f"No obsolete rank roles to remove.", "rank_removed": None}

    try:
        await member.remove_roles(*roles_to_remove, reason="Rank sync - removing obsolete roles")
        removed_names = ", ".join(role.name for role in roles_to_remove)
        # log(guild, msg := f"Removed roles: {removed_names}.")
        return {"success": True, "value": f"Removed roles: {removed_names}", "rank_removed": removed_names}

    except Exception as e:
        # log(guild, return_msg := f"Remove rank error: {e}")
        return {"success": False, "value": f"Remove rank error: {e}"}


async def assign_rank_role(guild: discord.Guild, member: discord.Member, rank_name: str) -> dict:
    """
    Ensures the role for rank_name exists, then gives it to member, removing other rank roles.

    return_value = {
        "success": bool,
        "value": string|None
        "rank_added": string|None
    }
    """
    if not rank_name:
        log(guild, return_msg := 'Returning! rank_name is None.')
        return {"success": False, "value": return_msg}

    if not (role := discord.utils.get(guild.roles, name=rank_name)):
        log(guild, return_msg := 'Returning! Role is None.')
        return {"success": False, "value": return_msg}

    if role.position >= guild.me.top_role.position:
        log(guild, return_msg := f"Bot's role is too low to assign {role.name} - move the bot's role higher.")
        return {"success": False, "value": return_msg}

    try:
        return_msg = None
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            log(guild, return_msg := f"Assigned rank: {role.name}")

        return {"success": True, "value": return_msg or f'Already has rank: {role.name}', "rank_added": rank_name if return_msg else None }

    except Exception as e:
        log(guild, return_msg := f"Assign role error: {e}")
        return {"success": False, "value": return_msg}

async def _query_member_stats(name: str, platform: str, session: aiohttp.ClientSession) -> int | None:
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url_stats(name, platform)
            async with session.get(API_URL) as response:
                body = await response.text()

                if response.status != 200:
                    raise Exception(
                        f"HTTP {response.status} | "
                        f"URL: {response.url} | "
                        f"Body: {body}"
                    )

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")

                return stats.get('userId')

        except Exception:
            if attempt < API_MAX_RETRIES:
                # max time is 126sec with 6 attempts. S = 2(2**6-1)/(2-1)
                await asyncio.sleep(1)
            continue
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

    if not member:
        return {'success': False, 'value': f"❌ Not a member: `{member}`"}

    if member.bot:
        # log(guild, fail_msg := f"❌ Trying to update a bot. What the helly.")
        return return_msg | {'success': False, 'value': f"❌ Trying to update a bot. What the helly."}

    if not (entry := get_player_entry(load_data(), guild.id, member.id)):
        # log(guild, fail_msg := f"❌ Not linked. Skipping.")
        return return_msg | {'success': False, 'value': f"❌ Not linked. Skipping."}

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)
    
    if not (nucleus_id := entry.get('nucleus_id')):
        nucleus_id = await _query_member_stats(name, platform, session)
        log(guild, message=f"nucleus_id query done for: {name}, {platform}, {nucleus_id}")

    if not (stats := await fetch_player_stats(guild, session, name, platform, nucleus_id)):
        # log(guild, fail_msg := f"⚠️ Data fetch failed. If link is correct, do not stress, API failure.")
        return return_msg | {'success': False, 'value': f"⚠️ Data fetch failed. If link is correct, do not stress, API failure."}

    rankValue = get_rank_value_from_data(stats)
    if rankValue is None:
        # log(guild, fail_msg := f"[WARNING] Could not extract rank.")
        return return_msg | {'success': False, 'value': f"[WARNING] Could not extract rank."}

    concise_rank_name = getRankNameFromCareerRank(rankValue)

    data = load_data()
    data[str(guild.id)][str(member.id)].update({
        'rank_name': concise_rank_name,
        'career_rank': rankValue
    })
    if not (data.get('nucleus_id')):
        data[str(guild.id)][str(member.id)].update({'nucleus_id': nucleus_id})
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


def _build_update_summary(return_value: dict) -> str:
    parts = [return_value['value']]

    assign = return_value.get('assign_rank_role') or {}
    if assign.get('rank_added'):
        parts.append(assign['value'])

    remove = return_value.get('remove_rank_role') or {}
    if remove.get('rank_removed'):
        parts.append(remove['value'])

    return ', '.join(parts)


def _has_rank_change(return_value: dict) -> bool:
    """True only if this member's update actually assigned or removed a rank
    role. Used to filter out no-op successes from the automatic update report."""
    assign = return_value.get('assign_rank_role') or {}
    remove = return_value.get('remove_rank_role') or {}
    return bool(assign.get('rank_added')) or bool(remove.get('rank_removed'))


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
    linked_member_ids = list(load_data().get(str(guild.id), {}).keys())

    log(guild, f"[START AUTOMATIC UPDATE] Total linked: {len(linked_member_ids)} member{'' if len(linked_member_ids)==1 else 's'}.")
    async with aiohttp.ClientSession() as session:
        for idx, member_id in enumerate(linked_member_ids):
            member = await guild.fetch_member(int(member_id))

            try:
                return_value: dict = await _update_member(guild, member, session)
                member_update_msg = _build_update_summary(return_value)

                if on_progress:
                    await on_progress(len(player_update_summary_list), len(linked_member_ids), idx == (len(linked_member_ids) - 1))

                if not return_value['success']:
                    raise Exception(f'❌ Update failed for `{member if member else member_id}`: {return_value['value']}')

                if not only_report_changes or _has_rank_change(return_value):
                    player_update_summary_list.append(f'\n{member_update_msg}')

            except Exception as e:
                log(guild, summary := f'{e}')
                failed_player_updates_summary_list.append(f'\n{summary}')

    log(guild, f"[FINISHED AUTOMATIC UPDATE] Updated {len(player_update_summary_list)} member{'' if len(player_update_summary_list) == 1 else 's'}.")
    return {'success': True, 'value': ', '.join(player_update_summary_list), 'failed_player_updates_summary_list': ', '.join(failed_player_updates_summary_list)}

# TODO: make this embed aswell like linked and shit is.
def _make_guild_update_loop(guild_id: int, interval_hours: float) -> tasks.Loop | None:
    if not guild_id:
        log(bot.get_guild(guild_id), f'{guild_id} is not valid. Returning.')
        return

    if (
        not isinstance(interval_hours, (int, float))
        or not math.isfinite(interval_hours)
        or interval_hours <= 0
    ):
        log(bot.get_guild(guild_id), f'{interval_hours} is not a valid update interval. Returning.')
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
                log(guild, failed_msg)
                await messages._send_chunked(channel, failed_msg)

            if success_msg:
                log(guild, channel_msg := f"{success_msg}")
                await messages._send_chunked(channel, channel_msg)

        except Exception as e:
            log(guild, f'Error at automatic loop sending channel msg: {e}')

    return _loop


def start_guild_update_loop(guild: discord.Guild):
    """Starts (or restarts) the automatic update loop for one guild, using its configured interval."""
    existing = running_loops.get(guild.id)
    if existing and existing.is_running():
        return

    guild_config = load_config().get(str(guild.id), {})
    interval_hours = guild_config.get('update_interval', AUTO_UPDATE_TIMER_HOURS)
    loop = _make_guild_update_loop(guild.id, interval_hours)
    if loop is None:
        running_loops.pop(guild.id, None)
        return

    running_loops[guild.id] = loop
    loop.start()

def restart_guild_update_loop(guild: discord.Guild):
    """Call this after update_interval changes in config, so the new interval takes effect."""
    existing = running_loops.pop(guild.id, None)
    if existing:
        existing.cancel()
    start_guild_update_loop(guild)
