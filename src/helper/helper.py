import json
import aiohttp
import time
import sys
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
from urllib.parse import urlencode
from src.globals import *
from src.ranks.ranks import get_rank_name, r_dict
from src.data.config import load_config, save_config


async def send_interaction_message(interaction: discord.Interaction, content: str, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if isinstance(content, discord.Embed):
        kwargs['embed'] = content
        content = None

    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)

    await _warn_user_if_no_channel(interaction)

def log(guild: discord.Guild, message: str):
    def get_caller() -> str:
        try: return sys._getframe(2).f_code.co_name
        except ValueError: return "Unknown"
    print(f'[server:{guild.name if guild else 'Unknown'}] (func:{get_caller()}) msg: {message}')

def build_api_url(name: str) -> str:
    params = urlencode({'name': name, 'platform': DEFAULT_PLATFORM})
    return f"{API_BASE_URL}?{params}"


class WrongChannelError(app_commands.CheckFailure):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"Command must be used in <#{channel_id}>")

def _get_tree_commands():
    tree_commands = getattr(bot.tree, 'get_commands', None)
    if callable(tree_commands):
        try:
            return list(tree_commands())
        except TypeError:
            return []
    return list(getattr(bot.tree, 'commands', []))

def _get_guild_role_status(guild: discord.Guild) -> list:
    missing_roles: bool = False
    position_below: bool = False

    bot_top_position = guild.me.top_role.position
    for rank_name in r_dict.keys():
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

def _build_no_channel_warning_embed() -> discord.Embed:
    warning_embed = discord.Embed(
        title="⚠️ Report Channel Not Configured",
        description="No report channel has been set for this server!",
        color=discord.Color.red()
    )
    warning_embed.add_field(
        name="How to fix:",
        value=f"1. Go to your desired report channel\n2. Run: `{COMMAND_PREFIX}set-channel`",
        inline=False
    )
    return warning_embed

async def _warn_user_if_no_channel(interaction: discord.Interaction):
    """DMs the invoking user
    if this guild has no report channel configured yet. Called from send_interaction_message
    so it fires after every slash command without needing to touch each command."""
    if not interaction.guild:
        return

    if load_config().get(str(interaction.guild.id), {}).get('channel_id'):
        return

    try:
        # await interaction.user.send(embed=_build_no_channel_warning_embed())
        await interaction.followup.send(embed=_build_no_channel_warning_embed(), ephemeral=True)
    except Exception as e:
        log(interaction.guild, f"[WARNING] Failed to DM `{interaction.user.name}` about missing channel config: {e}")

