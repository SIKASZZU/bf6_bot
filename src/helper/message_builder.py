import discord
import datetime
from discord.ext import commands
from src.globals import bot, COMMAND_PREFIX, running_loops
from src.data.config import load_config
from src.helper.helper import log, _get_tree_commands


def _build_commands_message():
    embed = discord.Embed(
        title="📋 All commands",
        color=discord.Color.blue()
    )

    exempt_fields = []
    restricted_fields = []

    seen_names = set()
    all_commands = list(bot.commands) + list(_get_tree_commands())
    for cmd in sorted(all_commands, key=lambda c: c.name):
        if getattr(cmd, 'hidden', False):
            continue

        name = getattr(cmd, 'name', None)
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        prefix = COMMAND_PREFIX if isinstance(cmd, commands.Command) else '/'

        help_text = getattr(cmd, 'help', None) or getattr(cmd, 'description', None) or "No description."
        field_value = f"`{prefix}{name}` — {help_text}"

        # if name in CHANNEL_CHECK_EXEMPT:
        #     exempt_fields.append(field_value)
        # else:
        restricted_fields.append(field_value)

    # if exempt_fields:
    #     embed.add_field(name="Available in every channel", value="\n".join(exempt_fields), inline=False)

    if restricted_fields:
        #Available in only set channel
        embed.add_field(name="", value="\n".join(restricted_fields), inline=False)

    return embed

def _build_linked_message(guild: discord.Guild, data: dict, member: discord.Member = None) -> discord.Embed:
    server_data = data.get(str(guild.id))

    resolved = guild.get_member(int(member.id)) if member else None
    member_name = resolved.name if resolved else (f"<left server> ({member.id})" if member else None)

    embed = discord.Embed(
        title="📊 Linked accounts" if not member else f"{member_name}'s linked account",
        color=discord.Color.blue()
    )

    lines = []

    for discord_id, entry in server_data.items():
        if member and discord_id == str(member.id):
            lines.append(
                f"`{member.name}`: {entry.get('name', 'unknown')}, level {entry.get('career_rank', 'Missing level')}, {entry.get('rank_name', 'Missing rank')}"
            )
            break

        elif not member:
            member_guild = guild.get_member(int(discord_id))
            member_label = member_guild.name if member_guild else f"<left server> ({discord_id})"
            lines.append(
                f"`{member_label}`: {entry.get('name', 'unknown')}, level {entry.get('career_rank', 'Missing level')}, {entry.get('rank_name', 'Missing rank')}"
            )

    if not server_data or not lines:
        embed.description = "No linked accounts found for this server in the database." if not member else f"No link"
        return embed

    embed.description = "\n".join(lines)
    return embed

def _build_unlinked_message(guild: discord.Guild, data: dict) -> discord.Embed:
    server_data = data.get(str(guild.id))

    embed = discord.Embed(
        title="👥 Unlinked members",
        color=discord.Color.orange()
    )

    lines = []

    for member in guild.members:
        if member.bot:
            continue
        if str(member.id) not in server_data.keys():
            lines.append(f"{member}")

    if not lines:
        embed.description = "All members are linked!"
    else:
        embed.description = "\n".join(lines)
    return embed

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

def _build_update_summary(return_value: dict) -> str:
    parts = [return_value['value']]

    assign = return_value.get('assign_rank_role') or {}
    if assign.get('rank_added'):
        parts.append(assign['value'])

    remove = return_value.get('remove_rank_role') or {}
    if remove.get('rank_removed'):
        parts.append(remove['value'])

    return ', '.join(parts)

def _add_chunked_field(embed: discord.Embed, name: str, items: list, *, max_len: int = 1024, suffix: str = ''):
    """Adds `items` (joined with ', ') to embed as one or more fields, splitting
    across multiple fields so no single field value exceeds Discord's 1024-char
    limit. `suffix` (e.g. a note appended after the last chunk) is appended to
    the final chunk only, and still respects the limit."""
    if not items:
        return

    chunks = []
    current = ''
    for item in items:
        piece = item if not current else f', {item}'
        if len(current) + len(piece) > max_len:
            chunks.append(current)
            current = item
        else:
            current += piece
    if current:
        chunks.append(current)

    if suffix:
        if len(chunks[-1]) + len(suffix) <= max_len:
            chunks[-1] += suffix
        else:
            chunks.append(suffix.lstrip('\n'))

    for i, chunk in enumerate(chunks):
        field_name = name if i == 0 else f'\u200b'
        embed.add_field(name=field_name, value=chunk, inline=False)




