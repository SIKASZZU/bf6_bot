from discord.ext import commands
from discord import app_commands

from globals import *
from helper import load_data, save_data, update_all_players, update_player
from ranks import create_roles

# TODO: helper!
async def send_interaction_message(interaction: discord.Interaction, content: str, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)

# TODO: delete or move to helper
def _check_and_warn_no_channel(ctx):
    """Checks if a report channel is set and warns if not. Returns True if channel exists, False otherwise."""
    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    channel_id = guild_config.get('channel_id')

    if not channel_id:
        return False
    return True

def _get_tree_commands():
    tree_commands = getattr(bot.tree, 'get_commands', None)
    if callable(tree_commands):
        try:
            return list(tree_commands())
        except TypeError:
            return []
    return list(getattr(bot.tree, 'commands', []))

def _build_commands_help_message():
    lines = ["**All commands:**"]
    admin_lines = ["**Administrator only:**"]
    seen_names = set()

    for cmd in list(bot.commands) + _get_tree_commands():
        if getattr(cmd, 'hidden', False):
            continue

        name = getattr(cmd, 'name', None)
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        is_admin = any(
            getattr(check, '__qualname__', '').startswith('has_permissions')
            for check in getattr(cmd, 'checks', [])
        )

        prefix = COMMAND_PREFIX if isinstance(cmd, commands.Command) else '/'
        line = f"{prefix}{name}"

        help_text = getattr(cmd, 'help', None) or getattr(cmd, 'description', None)
        if help_text:
            line += f" — {help_text}"

        if is_admin:
            admin_lines.append(line)
        else:
            lines.append(line)

    message = "\n".join(lines)
    if admin_lines:
        message += "\n\n" + "\n".join(admin_lines)
    return message

def _build_links_message(guild_id, data: dict) -> str:
    server_data = data.get(str(guild_id), {})

    if not server_data:
        return "No linked accounts found for this server in the database."

    lines = [f"Linked accounts for this server:"]
    for discord_id, entry in server_data.items():
        if isinstance(entry, dict):
            name = entry.get('name', 'unknown')
            platform = entry.get('platform', DEFAULT_PLATFORM)

        lines.append(f"- {discord_id}: {name} ({platform})")

    return "\n".join(lines)

def _build_unlinked_message(guild_id, data):

    server_data = data.get(str(guild_id), {})

    if not server_data:
        return "No linked accounts found for this server in the database."

    lines = [f"Linked accounts for this server:"]

    for guild_data in bot.get_guild(guild_id):
        for member in guild_data.members:
            if member not in server_data.keys():
                lines.append(f"- {member}")

    return "\n".join(lines)

@bot.tree.command(name='link', description='Link Discord account to game account.')
@app_commands.describe(
    name=f'The {DEFAULT_PLATFORM} account name',
    member='Admin only: link discord member\'s account to name'
)
async def link(interaction: discord.Interaction, name: str, member: discord.Member = None):

    await interaction.response.defer(ephemeral=False)

    platform = DEFAULT_PLATFORM
    if platform not in VALID_PLATFORMS:
        await send_interaction_message(interaction, f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    target = member or interaction.user
    # only allow linking someone else if the invoker is an admin
    if member is not None and not interaction.user.guild_permissions.administrator:
        await send_interaction_message(
            interaction,
            "❌ Only administrators can link accounts for other members.",
            ephemeral=True,
        )
        return

    data = load_data()
    data.setdefault(str(interaction.guild.id), {})[str(target.id)] = {"name": name, "platform": platform}
    save_data(data)

    if target.id == interaction.user.id:
        await send_interaction_message(interaction, f"✅ Successfully linked your Discord account to `{name}` on platform `{platform}`!")
    else:
        await send_interaction_message(interaction, f"✅ Linked {target.mention} to `{name}` on platform `{platform}`!")

    # Check if report channel is configured
    # config = load_config()
    # if not config.get(str(interaction.guild.id), {}).get('channel_id'):
    #     await send_interaction_message(
    #         interaction,
    #         f"⚠️ **Note:** No report channel is configured! Updates will not be announced. Admin: use `{COMMAND_PREFIX}set-channel` in your desired channel.",
    #         ephemeral=True
    #     )

    await force_update.callback(interaction, member=target, update_everybody=False)

@bot.tree.command(name='update', description='Gather latest statistics and update roles accordingly.')
@app_commands.describe(
    member='Admin only: link discord member\'s account to name',
    update_everybody='Admin only: update all members that have been linked.'
)
async def force_update(interaction: discord.Interaction, member: discord.Member = None, update_everybody: bool = False):
    """Manually forces update on member. """

    is_admin = interaction.user.guild_permissions.administrator
    if not is_admin and (member is not None or update_everybody):
        await send_interaction_message(
            interaction,
            "❌ Only administrators can update accounts for other members or for everybody.",
            ephemeral=True,
        )
        return

    member_name = member.display_name if member else "None"

    await send_interaction_message(
        interaction,
        f'🔄 Updating...',
    )
    print(f'(Updating... arguments: member: {member_name}, update_everybody: {update_everybody})')

    target = member or interaction.user

    try:
        if update_everybody:
            await update_all_players(guild=interaction.guild)
            await send_interaction_message(interaction, "✅ All players stats update completed successfully!")

        else:
            await update_player(interaction.guild, target, report_channel=interaction.channel)
            await send_interaction_message(interaction, f"✅ Player stats update completed successfully for {target.display_name}!")

        # # Check if report channel is configured
        # config = load_config()
        # if not config.get(str(interaction.guild.id), {}).get('channel_id') and update_everybody:
        #     await send_interaction_message(
        #         interaction,
        #         f"⚠️ **Note:** No report channel is configured! Update results were not announced to a specific channel. Admin: use `{COMMAND_PREFIX}set-channel` in your desired channel.",
        #         ephemeral=True
        #     )

    except Exception as e:
        print(f"Manual update error: {e}")
        await send_interaction_message(interaction, f"❌ An error occurred during the update: {e}")

@bot.command(name="setup-roles")
@commands.has_permissions(administrator=True)
async def setup_roles(ctx):
    created, skipped = await create_roles(ctx.guild)

    msg = ""
    if created:
        msg += f"✅ Created roles: {', '.join(created)}\n"

    if skipped:
        msg += f"✅ Already existed: {', '.join(skipped)}\n"

    msg += f"\n**Next steps:**\n1. Run `{COMMAND_PREFIX}set-channel` in your desired report channel\n2. Members use `{COMMAND_PREFIX}link <username>` to link their accounts"

    await ctx.send(msg or "❌ Something went wrong trying to create roles.")

@bot.command(name="set-channel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""

    config = load_config()
    config.setdefault(str(ctx.guild.id), {})["channel_id"] = ctx.channel.id
    save_config(config)

    success_embed = discord.Embed(
        title="✅ Channel Configured",
        description=f"This channel ({ctx.channel.mention}) will now receive the {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h automatic stats updates.",
        color=discord.Color.green()
    )
    await ctx.send(embed=success_embed)

@bot.command(name="set-update-interval")
@commands.has_permissions(administrator=True)
async def set_update_interval(ctx, hours: int):
    """Sets the current channel as the target for the 24h stats report."""

    if (hours < 1):
        print(f'Somebody tried to set hours: {hours}')
        ctx.send(f"Try again! Only natural numbers including from 1 and above can be set as interval.")
        return

    config = load_config()
    config.setdefault(str(ctx.guild.id), {})['update_interval'] = hours
    save_config(config)

    update_all_players.change_interval(hours=hours)
    await ctx.send(f"✅ Done! The update interval is now {hours} hours.")

@bot.command(name="commands")
async def display_commands(ctx):
    await ctx.send(_build_commands_help_message())

@bot.command(name="links", description=f'Have all the links be displayed.')
async def display_links(ctx):
    await ctx.send(_build_links_message(ctx.guild.id, load_data()))

@bot.command('unlinks', description=f'Have all the unlinked members be displayed.')
async def display_unlinks(ctx):
    await ctx.send(_build_unlinked_message(ctx.guild.id, load_data()))

def _get_time_to_next_update():
    """Returns the time until the next automatic update in HH:MM:SS format."""
    try:
        if hasattr(update_all_players, 'next_iteration') and update_all_players.next_iteration:
            import datetime
            now = datetime.datetime.utcnow()
            time_left = update_all_players.next_iteration - now

            total_seconds = int(time_left.total_seconds())
            if total_seconds < 0:
                return "Starting soon..."

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"
    except Exception as e:
        print(f"Error calculating next update time: {e}")
    return "Unknown"

@bot.command(name='info')
async def display_info(ctx):
    """Sends comprehensive information about the bot and how to use it."""
    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    data = load_data()
    linked_count = len(data.get(str(ctx.guild.id), {}))
    update_interval = guild_config.get('update_interval', 1)
    channel_id = guild_config.get('channel_id')

    embed = discord.Embed(
        title="🤖 Battlefield 6 Rank Bot - Info",
        description="This bot automatically assigns Discord roles based on your Battlefield 6 career rank!",
        color=discord.Color.blue()
    )

    # Linked Accounts
    embed.add_field(
        name="📊 Linked Accounts",
        value=f"**{linked_count}** account(s) linked on this server",
        inline=False
    )

    # Update Timer
    time_to_update = _get_time_to_next_update()
    embed.add_field(
        name="⏱️ Update Status",
        value=f"Updates every **{update_interval}h**\nNext update: {time_to_update}",
        inline=False
    )

    # Setup Status
    channel_status = f"<#{channel_id}>" if channel_id else "❌ Not configured"
    embed.add_field(
        name="⚙️ Configuration",
        value=f"Report channel: {channel_status}",
        inline=False
    )

    # Quick Setup Guide
    embed.add_field(
        name="🚀 Quick Setup (Admin Only)",
        value=(
            f"`{COMMAND_PREFIX}set-channel` - Set report channel\n"
            f"`{COMMAND_PREFIX}setup-roles` - Create rank roles\n"
            f"`{COMMAND_PREFIX}link <name>` - Link your account\n"
            f"`{COMMAND_PREFIX}update` - Manual update"
        ),
        inline=False
    )

    # Platforms
    embed.add_field(
        name="🎮 Supported Platforms",
        value=f"Default: **{DEFAULT_PLATFORM}**\nAll: {', '.join(sorted(VALID_PLATFORMS))}",
        inline=False
    )

    # All Commands
    embed.add_field(
        name="📋 All Commands",
        value=f"Use `{COMMAND_PREFIX}commands` to see all available commands",
        inline=False
    )

    embed.set_footer(text="For detailed instructions, use !setup or !instructions")

    await ctx.send(embed=embed)

@bot.command(name='setup', aliases=['instructions'])
async def display_setup(ctx):
    """Sends detailed setup instructions."""
    embed = discord.Embed(
        title="📖 Setup Instructions",
        description="Step-by-step guide to get the bot running on your server",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Step 1️⃣: Create Rank Roles",
        value=f"Administrator runs: `{COMMAND_PREFIX}setup-roles`\nThis creates roles for each BF6 rank.",
        inline=False
    )

    embed.add_field(
        name="Step 2️⃣: Set Report Channel",
        value=f"Administrator goes to desired channel and runs: `{COMMAND_PREFIX}set-channel`\nThe bot will use this channel to post updates.",
        inline=False
    )

    embed.add_field(
        name="Step 3️⃣: Link Accounts",
        value=f"Members link their BF6 account: `{COMMAND_PREFIX}link <your_bf6_username>`\nOr admins can link for members: `{COMMAND_PREFIX}link <name> @member`",
        inline=False
    )

    embed.add_field(
        name="Step 4️⃣: Set Update Interval",
        value=f"(Optional) Administrator can set update frequency: `{COMMAND_PREFIX}set-update-interval <hours>`\nDefault is 1 hour.",
        inline=False
    )

    embed.add_field(
        name="✅ That's it!",
        value="The bot will now automatically update member ranks every interval.",
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command(name='unlink')
@commands.has_permissions(administrator=True)
async def unlink_member(ctx, member: discord.Member):
    """Unlink a member's Discord account from their game account."""
    data = load_data()
    guild_key = str(ctx.guild.id)
    member_key = str(member.id)

    if guild_key not in data or member_key not in data[guild_key]:
        await ctx.send(f"❌ {member.mention} is not linked to any account.")
        return

    # Store the removed entry for confirmation
    removed_entry = data[guild_key][member_key]
    del data[guild_key][member_key]
    save_data(data)

    # Get the account name for the message
    if isinstance(removed_entry, dict):
        account_name = removed_entry.get('name', 'unknown')
    else:
        account_name = removed_entry

    await ctx.send(f"✅ Unlinked {member.mention} from account `{account_name}`")

@bot.command(name='time-to-update')
async def show_time_to_update(ctx):
    """Shows the time until the next automatic update."""
    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    update_interval = guild_config.get('update_interval', 1)
    time_left = _get_time_to_next_update()

    embed = discord.Embed(
        title="⏰ Next Update",
        description=f"Time remaining: **{time_left}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="Update Interval", value=f"{update_interval} hour(s)", inline=False)

    await ctx.send(embed=embed)

@bot.command(name='supported-platforms')
async def display_supported_playforms(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")

@bot.command(name='test-role')
@commands.has_permissions(administrator=True)
async def test_role_assignment(ctx, rank_name: str, member: discord.Member = None):
    """Test role assignment on a member. Useful for troubleshooting."""
    target = member or ctx.author

    if not rank_name:
        await ctx.send("❌ Please provide a rank name to test (e.g., 'Private', 'Corporal', 'Sergeant').")
        return

    # Get rank roles available
    from ranks import get_role_dict
    available_ranks = list(get_role_dict().keys())

    if rank_name not in available_ranks:
        await ctx.send(f"❌ Invalid rank: `{rank_name}`. Available ranks: {', '.join(available_ranks)}")
        return

    # Get the role
    role = discord.utils.get(ctx.guild.roles, name=rank_name)
    if not role:
        await ctx.send(f"❌ Role `{rank_name}` not found. Did you run `{COMMAND_PREFIX}setup-roles`?")
        return

    # Test assignment
    try:
        if ctx.guild.me.top_role.position <= role.position:
            await ctx.send(f"❌ Bot's top role is too low to assign `{rank_name}`. Please move the bot's role higher in the role hierarchy.")
            return

        if role in target.roles:
            await ctx.send(f"ℹ️ {target.mention} already has the `{rank_name}` role.")
        else:
            await target.add_roles(role)
            await ctx.send(f"✅ Successfully assigned `{rank_name}` role to {target.mention}. Role assignment is working!")
    except discord.Forbidden:
        await ctx.send(f"❌ Missing permissions to assign role `{rank_name}`.")
    except Exception as e:
        await ctx.send(f"❌ Error during role assignment: {e}")
