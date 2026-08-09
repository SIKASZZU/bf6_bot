from discord.ext import commands
from discord import app_commands
import aiohttp

from globals import *
import helper
from ranks import create_roles
import datetime


@bot.tree.command(name='link', description='Link Discord account to game account.')
@app_commands.describe(
    name=f'The {DEFAULT_PLATFORM} account name',
    member='Admin only: link discord member\'s account to name'
)
async def link(interaction: discord.Interaction, name: str, member: discord.Member = None):

    await interaction.response.defer(ephemeral=False)

    platform = DEFAULT_PLATFORM
    if platform not in VALID_PLATFORMS:
        await helper.send_interaction_message(interaction, f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    target = member or interaction.user
    # only allow linking someone else if the invoker is an admin
    if member is not None and not interaction.user.guild_permissions.administrator:
        await helper.send_interaction_message(
            interaction,
            "❌ Only administrators can link accounts for other members.",
            ephemeral=True,
        )
        return

    data = helper.load_data()
    data.setdefault(str(interaction.guild.id), {})[str(target.id)] = {"name": name, "platform": platform}
    helper.save_data(data)

    if target.id == interaction.user.id:
        await helper.send_interaction_message(interaction, f"✅ Successfully linked your Discord account to `{name}` on platform `{platform}`!")
    else:
        await helper.send_interaction_message(interaction, f"✅ Linked {target.mention} to `{name}` on platform `{platform}`!")

    # Check if report channel is configured
    # config = load_config()
    # if not config.get(str(interaction.guild.id), {}).get('channel_id'):
    #     await helper.send_interaction_message(
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
        await helper.send_interaction_message(
            interaction,
            "❌ Only administrators can update accounts for other members or for everybody.",
            ephemeral=True,
        )
        return

    member_name = member.display_name if member else "None"

    await helper.send_interaction_message(
        interaction,
        f'🔄 Updating...',
    )
    log(interaction.guild, f'(Updating... arguments: member: {member_name}, update_everybody: {update_everybody})')

    target = member or interaction.user

    try:
        if update_everybody:
            await helper.update_all_players(guild=interaction.guild)
            await helper.send_interaction_message(interaction, "✅ All players stats update completed successfully!")

        else:
            async with aiohttp.ClientSession() as session:
                if await helper._update_member(interaction.guild, target, session, channel=interaction.channel):
                    log(interaction.guild, f"✅ Player stats update completed successfully for {target.display_name}!")
                    await helper.send_interaction_message(interaction, f"✅ Player stats update completed successfully for {target.display_name}!")

    except Exception as e:
        log(interaction.guild, f"Manual update error: {e}")
        await helper.send_interaction_message(interaction, f"❌ An error occurred during the update: {e}")

@bot.command(name="setup-roles")
@commands.has_permissions(administrator=True)
async def setup_roles(ctx):
    created, skipped = await create_roles(ctx.guild)

    embed = discord.Embed(
        title="⚙️ Role Setup",
        color=discord.Color.green()
    )

    if not created and not skipped:
        embed.description = "❌ Something went wrong trying to create roles."
        embed.color = discord.Color.red()
    else:
        if created:
            embed.add_field(name="✅ Created roles", value=", ".join(created), inline=False)
        if skipped:
            embed.add_field(name="✅ Already existed", value=", ".join(skipped), inline=False)

    await ctx.send(embed=embed)

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
        log(ctx.guild, f'Somebody tried to set hours: {hours}')
        embed = discord.Embed(
            title="❌ Error",
            description="Try again! Only natural numbers including from 1 and above can be set as interval.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    config = load_config()
    config.setdefault(str(ctx.guild.id), {})['update_interval'] = hours
    save_config(config)

    helper.restart_guild_update_loop(ctx.guild)

    embed = discord.Embed(
        title="✅ Done!",
        description=f"The update interval is now {hours} hours.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="commands")
async def display_commands(ctx):
    await ctx.send(embed=helper._build_commands_message())

@bot.command(name="links", description=f'Have all the links be displayed.')
async def display_links(ctx):
    await ctx.send(embed=helper._build_links_message(ctx.guild, helper.load_data()))

@bot.command('unlinks', description=f'Have all the unlinked members be displayed.')
async def display_unlinks(ctx):
    embed = helper._build_unlinked_message(ctx.guild, helper.load_data())
    log(ctx.guild, embed.description)
    await ctx.send(embed=embed)

def _get_time_to_next_update(guild: discord.Guild):
    try:
        loop = helper.running_loops.get(guild.id)
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
    return "Unknown"

@bot.command(name='info')
async def display_info(ctx):
    """Sends comprehensive information about the bot and how to use it."""
    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    data = helper.load_data()
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
    time_to_update = _get_time_to_next_update(ctx.guild)
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

    # # Platforms
    # embed.add_field(
    #     name="🎮 Supported Platforms",
    #     value=f"Default: **{DEFAULT_PLATFORM}**\nAll: {', '.join(sorted(VALID_PLATFORMS))}",
    #     inline=False
    # )

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
    data = helper.load_data()
    guild_key = str(ctx.guild.id)
    member_key = str(member.id)

    if guild_key not in data or member_key not in data[guild_key]:
        embed = discord.Embed(
            title="❌ Error",
            description=f"{member.mention} is not linked to any account.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    # Store the removed entry for confirmation
    removed_entry = data[guild_key][member_key]
    del data[guild_key][member_key]
    helper.save_data(data)

    # Get the account name for the message
    if isinstance(removed_entry, dict):
        account_name = removed_entry.get('name', 'unknown')
    else:
        account_name = removed_entry

    embed = discord.Embed(
        title="✅ Account unlinked",
        description=f"Unlinked {member.mention} from account `{account_name}`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='time-to-update')
async def show_time_to_update(ctx):
    """Shows the time until the next automatic update."""
    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    update_interval = guild_config.get('update_interval', 1)
    time_left = _get_time_to_next_update(ctx.guild)

    embed = discord.Embed(
        title="⏰ Next Update",
        description=f"Time remaining: **{time_left}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="Update Interval", value=f"{update_interval} hour(s)", inline=False)

    await ctx.send(embed=embed)

# @bot.command(name='supported-platforms')
# async def display_supported_playforms(ctx):
#     """ Sends a message to channel containing information about and use cases of bot."""
#     await ctx.send(f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")

@bot.command(name='test-role')
@commands.has_permissions(administrator=True)
async def test_role_assignment(ctx, rank_name: str, member: discord.Member = None):
    """Test role assignment on a member. Useful for troubleshooting."""
    target = member or ctx.author

    if not rank_name:
        embed = discord.Embed(title="❌ Error", description="Please provide a rank name to test (e.g., 'Private', 'Corporal', 'Sergeant').", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    # Get rank roles available
    from ranks import get_role_dict
    available_ranks = list(get_role_dict().keys())

    if rank_name not in available_ranks:
        embed = discord.Embed(title="❌ Invalid rank", description=f"Available ranks: {', '.join(available_ranks)}", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    # Get the role
    role = discord.utils.get(ctx.guild.roles, name=rank_name)
    if not role:
        embed = discord.Embed(title="❌ Role not found", description=f"Role `{rank_name}` not found. Did you run `{COMMAND_PREFIX}setup-roles`?", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    # Test assignment
    try:
        if ctx.guild.me.top_role.position <= role.position:
            embed = discord.Embed(title="❌ Bot permission error", description=f"Bot's top role is too low to assign `{rank_name}`. Please move the bot's role higher in the role hierarchy.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        if role in target.roles:
            embed = discord.Embed(title="ℹ️ Already assigned", description=f"{target.mention} already has the `{rank_name}` role.", color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await target.add_roles(role)
            embed = discord.Embed(title="✅ Role assigned", description=f"Successfully assigned `{rank_name}` role to {target.mention}. Role assignment is working!", color=discord.Color.green())
            await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = discord.Embed(title="❌ Missing permissions", description=f"Missing permissions to assign role `{rank_name}`.", color=discord.Color.red())
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=f"Error during role assignment: {e}", color=discord.Color.red())
        await ctx.send(embed=embed)
