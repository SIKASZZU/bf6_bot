
import discord
from discord.ext import commands

from src.globals import bot, COMMAND_PREFIX
from src.globals import load_config, log

def _build_no_channel_warning_embed() -> discord.Embed:
    warning_embed = discord.Embed(
        title="⚠️ Report Channel Not Configured",
        description="No report channel has been set!",
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
        await interaction.followup.send(embed=_build_no_channel_warning_embed(), ephemeral=True)
    except Exception as e:
        log(interaction.guild, f"[WARNING] Failed to DM `{interaction.user.name}` about missing channel config: {e}")

async def send_interaction_message(interaction: discord.Interaction, content: str | discord.Embed | None, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if isinstance(content, discord.Embed):
        kwargs['embed'] = content
        content = None

    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)

    await _warn_user_if_no_channel(interaction)


async def _send_chunked(channel, text: str, limit: int = 1900):
    lines = [l for l in text.split('\n') if l.strip()]
    for chunk in _chunk_items(lines, max_len=limit, sep='\n'):
        for i in range(0, len(chunk), limit):
            await channel.send(chunk[i:i + limit])


def _chunk_items(items: list, *, max_len: int, sep: str) -> list[str]:
    chunks, current = [], ''
    for item in items:
        piece = item if not current else f'{sep}{item}'
        if current and len(current) + len(piece) > max_len:
            chunks.append(current)
            current = item
        else:
            current += piece
    if current:
        chunks.append(current)
    return chunks


def _get_tree_commands():
    tree_commands = getattr(bot.tree, 'get_commands', None)
    if callable(tree_commands):
        try:
            return list(tree_commands())
        except TypeError:
            return []
    return list(getattr(bot.tree, 'commands', []))


def _paginate_lines(title: str, lines: list[str], color: discord.Color, *, sep: str = "\n", code_block: bool = True) -> list[discord.Embed]:
    bounded_lines = [
        line[i:i + 4000]
        for line in lines
        for i in range(0, len(line), 4000)
    ]
    pages = _chunk_items(bounded_lines, max_len=4000, sep=sep)
    embeds = []
    for i, page in enumerate(pages, 1):
        description = f"```\n{page}\n```" if code_block else page
        e = discord.Embed(title=title, description=description, color=color)
        if len(pages) > 1:
            e.set_footer(text=f"Page {i}/{len(pages)} • {len(lines)} total")
        embeds.append(e)
    return embeds


def _build_commands_message() -> list[discord.Embed]:
    command_lines = []

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

        command_lines.append(field_value)

    if not command_lines:
        command_lines.append("No commands available.")

    return _paginate_lines(
        "📋 All commands",
        command_lines,
        discord.Color.blue(),
        code_block=False
    )


async def _build_linked_message(guild: discord.Guild, data: dict, member: discord.Member = None) -> list[discord.Embed]:
    resolved = await guild.fetch_member(int(member.id)) if member else None

    member_name = (resolved.name if resolved else (f"<left server> ({member.id})" if member else None))
    embed = discord.Embed(title="👥 Linked members" if not member else f"**`{member_name}`** linked account", color=discord.Color.blue())
    embed.title += f' (EA id, level, role)' if member else f' (discord, EA id, level, role)'

    # There are no links in data
    if not (server_data := data.get(str(guild.id))) or (member and str(member.id) not in server_data.keys()):
        embed.description = ("No linked accounts found." if not member else "No link")
        return [embed]

    rows = []
    if member and str(member.id) in server_data.keys():
        entry = server_data.get(str(member.id))
        rows.append((entry.get("name", "<Unknown>"), str(entry.get("career_rank", "<Missing>")), entry.get("rank_name", "<Missing>")))
    else:
        for discord_id, entry in server_data.items():
            try:
                label = (await guild.fetch_member(int(discord_id))).name
            except Exception:
                label = f"<left> ({discord_id})"
            rows.append((label, entry.get("name", "<Unknown>"), str(entry.get("career_rank", "<Missing>")), entry.get("rank_name", "<Missing>")))

    # TODO: make this code nicer.
    COL_WIDTHS = (12, 0, 0, 0)
    def _format_table(rows: list[tuple]) -> list[str]:
        # single-member mode has 3 columns, so use the trailing widths
        widths = COL_WIDTHS[-len(rows[0]):]
        out = []
        for r in rows:
            cells = []
            for i, (cell, w) in enumerate(zip(r, widths)):
                cells.append(cell.ljust(w))

            out.append(" | ".join(cells))
        return out

    lines = _format_table(rows)

    if not lines:
        embed.description = ("No linked accounts found" if not member else "No link")
        return [embed]

    return _paginate_lines(embed.title, lines, embed.color)


async def _build_unlinked_message(guild: discord.Guild, data: dict) -> list[discord.Embed]:
    embed = discord.Embed(title="👥 Unlinked members", color=discord.Color.orange())

    server_data = data.get(str(guild.id))

    lines = []
    guild_members = [m async for m in guild.fetch_members()]
    for member in guild_members:
        if member.bot:
            continue

        elif not server_data:
            lines.append(f"{member}")

        elif str(member.id) not in server_data:
            lines.append(f"{member}")

    if not lines:
        embed.description = "No unlinked accounts found."
        return [embed]

    return _paginate_lines(embed.title, lines, embed.color)
