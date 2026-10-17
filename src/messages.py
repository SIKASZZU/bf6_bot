
import discord
from discord.ext import commands

import src.helper as helper
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


async def _send_embed_to_channel(channel: discord.TextChannel, embeds: list[discord.Embed]):
    if not embeds:
        return

    kwargs = {"view": helper.EmbedPager(embeds)} if len(embeds) > 1 else {}
    await channel.send(embed=embeds[0], **kwargs)


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

    FIRST_COL_MIN = 12
    def _format_table(rows: list[tuple]) -> list[str]:
        cells = [[str(c) for c in r] for r in rows]
        first_w = max(FIRST_COL_MIN, max(len(r[0]) for r in cells))
        return [" | ".join([r[0].ljust(first_w), *r[1:]]) for r in cells]

    lines = _format_table(rows)

    if not lines:
        embed.description = ("No linked accounts found" if not member else "No link")
        return [embed]

    return _paginate_lines(embed.title, lines, embed.color)


async def _build_unlinked_message(guild: discord.Guild, data: dict) -> list[discord.Embed]:
    embed = discord.Embed(title="👥 Unlinked members (discord)", color=discord.Color.blue())

    server_data = data.get(str(guild.id))

    lines = []
    guild_members = [m async for m in guild.fetch_members()]
    for member in guild_members:
        if member.bot:
            continue

        elif not server_data:
            lines.append(f"`{member}`")

        elif str(member.id) not in server_data:
            lines.append(f"`{member}`")

    if not lines:
        embed.description = "No unlinked accounts found."
        return [embed]

    return _paginate_lines(embed.title, lines, embed.color, code_block=False)


async def _build_and_send_force_update_message(interaction: discord.Interaction, return_value):
    summary_parts = []
    if return_value.get('value'):
        summary_parts.append(return_value['value'])
    if return_value.get('failed_player_updates_summary_list'):
        summary_parts.append(return_value['failed_player_updates_summary_list'])

    combined = ' '.join(summary_parts) if summary_parts else 'No linked members to update.'
    log(interaction.guild, combined)

    has_update_failures = bool(return_value.get('failed_player_updates_summary_list'))

    result_title = (
        "❌ Update completed" if not return_value.get('success')
        else "⚠️ Update completed" if has_update_failures
        else "✅ Update completed"
    )
    result_color = (
        discord.Color.red() if not return_value.get('success')
        else discord.Color.orange() if has_update_failures
        else discord.Color.green()
    )
    result_embeds = _paginate_lines(
        result_title,
        combined.splitlines() or [combined],
        result_color,
        code_block=False
    )
    await interaction.edit_original_response(
        embed=result_embeds[0],
        **helper._embed_pager_kwargs(result_embeds)
    )