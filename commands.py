from discord import app_commands
import aiohttp

from globals import *
import helper
from ranks import create_roles


@bot.tree.command(name='link', description='Link Discord account to game account.')
@helper.is_admin_or_has_role()
@app_commands.describe(
    name=f'The {DEFAULT_PLATFORM} account name',
    member='Discord member'
)
async def link(interaction: discord.Interaction, name: str, member: discord.Member = None):

    await interaction.response.defer()

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
    #         f"⚠️ **Note:** No report channel is configured! Updates will not be announced. Admin: use `{COMMAND_PREFIX}set-channel` in your desired channel."
    #     )

    await force_update.callback(interaction, member=target, update_everybody=False)

@bot.tree.command(name='update', description='Gather latest statistics and update roles accordingly.')
@helper.is_admin_or_has_role()
@app_commands.describe(
    member='Discord member',
    update_everybody='Update all members that have been linked.'
)
async def force_update(interaction: discord.Interaction, member: discord.Member = None, update_everybody: bool = False):
    """Manually forces update on member. """

    is_admin = interaction.user.guild_permissions.administrator
    if not is_admin and (member is not None or update_everybody):
        await helper.send_interaction_message(
            interaction,
            "❌ Only administrators can update accounts for other members or for everybody."
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

@bot.tree.command(name="setup-roles", description='Creates all possible career rank roles for bot to assign.')
@helper.is_admin_or_has_role()
async def setup_roles(interaction: discord.Interaction):
    created, skipped = await create_roles(interaction.guild)

    message = discord.Embed(
        title="⚙️ Role Setup",
        color=discord.Color.green()
    )

    if not created and not skipped:
        message.description = "❌ Something went wrong trying to create roles."
        message.color = discord.Color.red()
    else:
        if created:
            message.add_field(name="✅ Created roles", value=", ".join(created), inline=False)
        if skipped:
            message.add_field(name="✅ Already existed", value=", ".join(skipped), inline=False)

    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name="set-channel", description='Bot will default to talking to this the set channel.')
@helper.is_admin_or_has_role()
async def set_channel(interaction: discord.Interaction):
    config = load_config()
    config.setdefault(str(interaction.guild.id), {})["channel_id"] = interaction.channel.id
    save_config(config)

    message = discord.Embed(
        title="✅ Channel Configured",
        description=f"This channel ({interaction.channel.mention}) will now receive the {load_config().get(str(interaction.guild.id), {}).get('update_interval')}h automatic stats updates.",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name="set-update-interval", description='Set how often automatic updates should happen. Set time in hours (minimum 1 hour).')
@helper.is_admin_or_has_role()
@app_commands.describe(
    hours='Updates in set hour interval (minimum 1 hour)'
)
async def set_update_interval(interaction: discord.Interaction, hours: int):
    if (hours < 1):
        log(interaction.guild, f'Somebody tried to set hours: {hours}')
        error_message = discord.Embed(
            title="❌ Error",
            description="Try again! Only natural numbers including from 1 and above can be set as interval.",
            color=discord.Color.red()
        )
        await helper.send_interaction_message(interaction, content=error_message)
        return

    config = load_config()
    config.setdefault(str(interaction.guild.id), {})['update_interval'] = hours
    save_config(config)

    helper.restart_guild_update_loop(interaction.guild)

    success_message = discord.Embed(
        title="✅ Done!",
        description=f"The update interval is now {hours} hours.",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=success_message)

@bot.tree.command(name="commands", description='Display all the commands possible.')
@helper.is_admin_or_has_role()
async def display_commands(interaction: discord.Interaction):
    await helper.send_interaction_message(interaction, content=helper._build_commands_message())

@bot.tree.command(name="links", description=f'Have all the links be displayed.')
@helper.is_admin_or_has_role()
async def display_links(interaction: discord.Interaction):
    await helper.send_interaction_message(interaction, content=helper._build_links_message(interaction.guild, helper.load_data()))

@bot.tree.command(name='unlinks', description=f'Have all the unlinked members be displayed.')
@helper.is_admin_or_has_role()
async def display_unlinks(interaction: discord.Interaction):
    await helper.send_interaction_message(interaction, content=helper._build_unlinked_message(interaction.guild, helper.load_data()))

@bot.tree.command(name='info', description='Sends comprehensive information about the bot and how to use it.')
@helper.is_admin_or_has_role()
async def display_info(interaction: discord.Interaction):
    config = load_config()
    guild_config = config.get(str(interaction.guild.id), {})
    data = helper.load_data()
    linked_count = len(data.get(str(interaction.guild.id), {}))
    update_interval = guild_config.get('update_interval', 1)
    channel_id = guild_config.get('channel_id')

    message = discord.Embed(
        title="🤖 Battlefield 6 Rank Bot - Info",
        description="This bot automatically assigns Discord roles based on your Battlefield 6 career rank!",
        color=discord.Color.blue()
    )

    # Linked Accounts
    message.add_field(
        name="📊 Linked Accounts",
        value=f"**{linked_count}** account(s) linked on this server",
        inline=False
    )

    # Update Timer
    time_to_update = helper._get_time_to_next_update(interaction.guild)
    message.add_field(
        name="⏱️ Update Status",
        value=f"Updates every **{update_interval}h**\nNext update: {time_to_update}",
        inline=False
    )

    # Setup Status
    channel_status = f"<#{channel_id}>" if channel_id else "❌ Not configured"
    message.add_field(
        name="⚙️ Configuration",
        value=f"Report channel: {channel_status}",
        inline=False
    )

    # Quick Setup Guide
    message.add_field(
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
    # message.add_field(
    #     name="🎮 Supported Platforms",
    #     value=f"Default: **{DEFAULT_PLATFORM}**\nAll: {', '.join(sorted(VALID_PLATFORMS))}",
    #     inline=False
    # )

    # All Commands
    message.add_field(
        name="📋 All Commands",
        value=f"Use `{COMMAND_PREFIX}commands` to see all available commands",
        inline=False
    )

    message.set_footer(text="For detailed instructions, use !setup or !instructions")

    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='setup', description='Display setup steps for the bot.', extras={'aliases': ['instructions']})
@helper.is_admin_or_has_role()
async def display_setup(interaction: discord.Interaction):
    """Sends detailed setup instructions."""
    message = discord.Embed(
        title="📖 Setup Instructions",
        description="Step-by-step guide to get the bot running on your server",
        color=discord.Color.green()
    )

    message.add_field(
        name="Step 1️⃣: Create Rank Roles",
        value=f"Administrator runs: `{COMMAND_PREFIX}setup-roles`\nThis creates roles for each BF6 rank.",
        inline=False
    )

    message.add_field(
        name="Step 2️⃣: Set Report Channel",
        value=f"Administrator goes to desired channel and runs: `{COMMAND_PREFIX}set-channel`\nThe bot will use this channel to post updates.",
        inline=False
    )

    message.add_field(
        name="Step 3️⃣: Link Accounts",
        value=f"Members link their BF6 account: `{COMMAND_PREFIX}link <your_bf6_username>`\nOr admins can link for members: `{COMMAND_PREFIX}link <name> @member`",
        inline=False
    )

    message.add_field(
        name="Step 4️⃣: Set Update Interval",
        value=f"(Optional) Administrator can set update frequency: `{COMMAND_PREFIX}set-update-interval <hours>`\nDefault is 1 hour.",
        inline=False
    )

    message.add_field(
        name="✅ That's it!",
        value="The bot will now automatically update member ranks every interval.",
        inline=False
    )

    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='unlink', description="Unlink a member's Discord account from their game account.")
@helper.is_admin_or_has_role()
@app_commands.describe(
    member='Discord member'
    )
async def unlink_member(interaction: discord.Interaction, member: discord.Member):
    data = helper.load_data()
    guild_key = str(interaction.guild.id)
    member_key = str(member.id)

    if guild_key not in data or member_key not in data[guild_key]:
        message = discord.Embed(
            title="❌ Error",
            description=f"{member.mention} is not linked to any account.",
            color=discord.Color.red()
        )
        await helper.send_interaction_message(interaction, content=message)
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

    message = discord.Embed(
        title="✅ Account unlinked",
        description=f"Unlinked {member.mention} from account `{account_name}`",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='time-until-update', description='Shows the time until the next automatic update.')
@helper.is_admin_or_has_role()
async def show_time_to_update(interaction: discord.Interaction):
    guild_config = load_config().get(str(interaction.guild.id))
    time_left = helper._get_time_to_next_update(interaction.guild)

    message = discord.Embed(
        title="⏰ Next Update",
        description=f"Time remaining: **{time_left}**",
        color=discord.Color.gold()
    )
    message.add_field(name="Update Interval", value=f"{guild_config.get('update_interval')} hour(s)", inline=False)
    await helper.send_interaction_message(interaction, content=message)

# @bot.command(name='supported-platforms')
# async def display_supported_playforms(ctx):
#     """ Sends a message to channel containing information about and use cases of bot."""
#     await helper.send_interaction_message(interaction, f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")
