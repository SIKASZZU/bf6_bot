from discord import app_commands
import aiohttp
import time

from globals import *
import helper
from ranks import create_roles


@bot.tree.command(name='link', description='Link Discord account to game account.')
@app_commands.describe(
    name=f'The {DEFAULT_PLATFORM} account name',
    member='Discord member'
)
async def link(interaction: discord.Interaction, name: str, member: discord.Member = None):

    await interaction.response.defer()

    target = member or interaction.user

    if target.bot:
        await helper.send_interaction_message(interaction, f"❌ Dude. Why assign to bot someone's account? I hereby refuse.")
        return

    platform = DEFAULT_PLATFORM
    # if platform not in VALID_PLATFORMS:
    #     await helper.send_interaction_message(interaction, f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
    #     return

    data = helper.load_data()
    data.setdefault(str(interaction.guild.id))[str(target.id)] = {"name": name, "platform": platform}
    helper.save_data(data)

    if target.id == interaction.user.id:
        await helper.send_interaction_message(interaction, msg := f"✅ Successfully linked You to `{name}` on platform `{platform}`!")
    else:
        await helper.send_interaction_message(interaction, msg := f"✅ Linked `{target}` to `{name}` on platform `{platform}`!")

    log(interaction.guild, msg)

@bot.tree.command(name='update', description='Gather latest statistics and update roles accordingly.')
@app_commands.describe(
    member='Discord member',
)
async def force_update(interaction: discord.Interaction, member: discord.Member = None):
    """Manually forces update on member. """

    await helper.send_interaction_message(interaction, update_msg:=f'(Updating... `{member if member else ''}`)')
    log(interaction.guild, update_msg)

    target = member or interaction.user

    try:
        # update only the requested target by checking if member was given.
        if member:
            async with aiohttp.ClientSession() as session:
                return_value: dict = await helper._update_member(interaction.guild, target, session)

                if not return_value['success']:
                    raise Exception(f'Update fail for `{target.name}`. {return_value['value']}')

                await interaction.edit_original_response(content = helper._build_update_summary(return_value))
            return

        # update everybody
        last_edit = 0.0
        async def report_progress(done: int, total: int, is_last: bool):
            nonlocal last_edit
            now = time.monotonic()
            if not is_last and (now - last_edit) < 2:
                return
            last_edit = now
            await interaction.edit_original_response(content=f"🔄 Updating... ({done}/{total} links updated)")

        return_value = await helper._run_guild_update(interaction.guild, on_progress=report_progress)
        log(interaction.guild, member_success := f'{return_value['value']}')
        await interaction.edit_original_response(content=member_success)

    except Exception as e:
        log(interaction.guild, fail_msg := f'❌ {e}')
        await interaction.edit_original_response(content=fail_msg)

@bot.tree.command(name='create-roles', description='Creates all possible career rank roles for bot to assign.')
async def setup_roles(interaction: discord.Interaction):
    await interaction.response.defer()

    created, skipped, failed, cap_reached = await create_roles(interaction.guild)

    message = discord.Embed(
        title="⚙️ Role Creation",
        color=discord.Color.green()
    )

    if not created and not skipped and not failed:
        message.description = "❌ Something went wrong trying to create roles."
        message.color = discord.Color.red()
    else:
        helper._add_chunked_field(message, "✅ Created roles", created)
        helper._add_chunked_field(message, "✅ Already existed", skipped)
        if failed:
            if cap_reached:
                field_name = "❌ Role limit reached"
                suffix = f"\n_This server has hit Discord's 250-role limit ({len(interaction.guild.roles)} roles). Remove unused roles to free up space, then run `{COMMAND_PREFIX}create-roles` again._"
            else:
                field_name = "❌ Missing permissions"
                suffix = f"\n_Move the bot's role above these ranks (or grant Manage Roles), then run `{COMMAND_PREFIX}create-roles` again._"

            helper._add_chunked_field(message, field_name, failed, suffix=suffix)
            message.color = discord.Color.orange()

    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='set-channel', description='Bot will be set to talk in that channel.')
@app_commands.describe(
    channel='Channel to use (defaults to the channel you run this in)'
)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    target_channel = channel or interaction.channel

    perms = target_channel.permissions_for(interaction.guild.me)
    if not (perms.view_channel and perms.send_messages):
        await helper.send_interaction_message(
            interaction,
            f"❌ I don't have permission to send messages in {target_channel.mention}. ",
            ephemeral=True
        )
        return

    config = load_config()
    config.setdefault(str(interaction.guild.id), {})["channel_id"] = target_channel.id
    save_config(config)

    message = discord.Embed(
        title="✅ Channel Configured",
        description=f"Channel ({target_channel.mention}) will be used for communication with and for this bot.",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='set-update-interval', description='Set how often automatic updates should happen. Set time in hours (minimum 1 hour).')
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
    config.setdefault(str(interaction.guild.id))['update_interval'] = hours
    save_config(config)

    helper.restart_guild_update_loop(interaction.guild)

    success_message = discord.Embed(
        title="✅ Done!",
        description=f"The update interval is now {hours} hours.",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=success_message)

@bot.tree.command(name='commands', description='Display all the commands possible.')
async def display_commands(interaction: discord.Interaction):
    await helper.send_interaction_message(interaction, content=helper._build_commands_message())

@bot.tree.command(name='linked', description=f'Display established links.')
@app_commands.describe(
    member='Discord member',
)
async def display_links(interaction: discord.Interaction, member: discord.Member = None):
    await helper.send_interaction_message(interaction, content=helper._build_linked_message(interaction.guild, helper.load_data(), member))

@bot.tree.command(name='unlinked', description=f'Have all the unlinked members be displayed.')
async def display_unlinks(interaction: discord.Interaction):
    await helper.send_interaction_message(interaction, content=helper._build_unlinked_message(interaction.guild, helper.load_data()))

@bot.tree.command(name='info', description='Sends comprehensive information about the bot and how to use it.')
async def display_info(interaction: discord.Interaction):
    config = load_config()
    guild_config = config.get(str(interaction.guild.id))
    linked_count = len(helper.load_data().get(str(interaction.guild.id)))
    update_interval = guild_config.get('update_interval')
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
    channel_status = f"<#{channel_id}>" if (channel_id and bot.get_guild(interaction.guild.id).get_channel(channel_id)) else "❌ Not configured. Use /set-channel."
    role_id = guild_config.get('permissioned_role_id')
    authorised_role_display = f"<@&{role_id}>" if role_id else "Administrator only"

    message.add_field(
        name="⚙️ Configuration",
        value=f"Report channel: {channel_status}\nAuthorised role: {authorised_role_display}",
        inline=False
    )

    # Quick Setup Guide
    message.add_field(
        name="🚀 Quick Setup",
        value=(
            f"`/setup` - Detailed information (2 minutes)\n"
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

    await helper.send_interaction_message(interaction, content=message)

    check = helper.check_guild_requirements(interaction.guild)
    if not check["ok"]:
        fail_msg = "[ERROR STARTING AUTOMATIC UPDATE]: " + " | ".join(check["issues"])
        log(interaction.guild, fail_msg)
        return {'success': False, 'value': fail_msg}


@bot.tree.command(name='setup', description='Display setup steps for the bot.', extras={'aliases': ['instructions']})
async def display_setup(interaction: discord.Interaction):
    """Sends detailed setup instructions."""
    message = discord.Embed(
        title="📖 Setup Instructions",
        description="Step-by-step guide to get the bot running on your server",
        color=discord.Color.green()
    )

    message.add_field(
        name="Step 1️⃣: Create Rank Roles",
        value=f"Administrator runs: `{COMMAND_PREFIX}create-roles`\nThis creates roles for each BF6 rank.",
        inline=False
    )

    message.add_field(
        name="Step 2️⃣: Set Report Channel",
        value=f"Administrator goes to desired channel and runs: `{COMMAND_PREFIX}set-channel`\nThe bot will use set channel to post updates if any.",
        inline=False
    )

    message.add_field(
        name="Step 3️⃣: Link Accounts",
        value=f"Admins can link for members: `{COMMAND_PREFIX}link <member_{DEFAULT_PLATFORM}_name> @member`",
        inline=False
    )

    message.add_field(
        name="Step 4️⃣: Set Update Interval",
        value=f"(Optional) Administrator can set update frequency: `{COMMAND_PREFIX}set-update-interval <hours>`\nDefault is {AUTO_UPDATE_TIMER_HOURS} hour.",
        inline=False
    )

    message.add_field(
        name="✅ That's it!",
        value="The bot will now automatically update member ranks every interval.",
        inline=False
    )

    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='unlink', description="Unlink a member's Discord account from their game account.")
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
            description=f"`{member}` is not linked to any account.",
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
        description=f"Unlinked `{member}` from account `{account_name}`",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='set-authorised-role', description="(Administrator*) Allow a role to use bot's commands. (max 1 role)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    role='Role that should be allowed to use bot commands.'
    )
async def assign_management_role(interaction: discord.Interaction, role: discord.Role):
    config = load_config()
    config.setdefault(str(interaction.guild.id))['permissioned_role_id'] = role.id
    save_config(config)

    log(interaction.guild, f"Management role set to '{role.name}' ({role.id}) by {interaction.user.name}")

    message = discord.Embed(
        title="✅ Management Role Set",
        description=f"{role.mention} can now use the bot's commands (in addition to server Administrators).",
        color=discord.Color.green()
    )
    await helper.send_interaction_message(interaction, content=message)

@bot.tree.command(name='show-authorised-role', description="Display management role.")
async def display_management_role(interaction: discord.Interaction):

    message = discord.Embed(
        title="🔑 Management Role",
        color=discord.Color.blue()
    )

    if role_id := load_config().get(str(interaction.guild.id), {}).get('permissioned_role_id'):
        role = interaction.guild.get_role(role_id)
        if role:
            message.description = f"{role.mention} can use the bot's commands."
        else:
            message.description = f"⚠️ The configured role (ID `{role_id}`) no longer exists on this server. Run `/assign-management-role` to set a new one."
            message.color = discord.Color.orange()
    else:
        message.description = f"No management role has been set yet. Run `/assign-management-role` to set one explicitly."

    await helper.send_interaction_message(interaction, content=message)

# @bot.tree.command(name='time-until-update', description='Shows the time until the next automatic update.')
# async def show_time_to_update(interaction: discord.Interaction):
#     guild_config = load_config().get(str(interaction.guild.id))
#     time_left = helper._get_time_to_next_update(interaction.guild)

#     message = discord.Embed(
#         title="⏰ Next Update",
#         description=f"Time remaining: **{time_left}**",
#         color=discord.Color.gold()
#     )
#     message.add_field(name="Update Interval", value=f"{guild_config.get('update_interval')} hour(s)", inline=False)
#     await helper.send_interaction_message(interaction, content=message)

# @bot.command(name='supported-platforms')
# async def display_supported_playforms(ctx):
#     """ Sends a message to channel containing information about and use cases of bot."""
#     await helper.send_interaction_message(interaction, f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")
