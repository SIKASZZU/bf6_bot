from discord.ext import commands
from discord import app_commands

from globals import *
from helper import load_data, save_data, update_all_players, update_player
from ranks import create_roles


async def send_interaction_message(interaction: discord.Interaction, content: str, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)


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
        f'🔄 Updating... (arguments: member: {member_name}, update_everybody: {update_everybody})',
    )

    target = member or interaction.user

    try:
        if update_everybody:
            await update_all_players()
            await send_interaction_message(interaction, "✅ All players stats update completed successfully!")

        else:
            await update_player(interaction.guild, target, report_channel=interaction.channel)
            await send_interaction_message(interaction, f"✅ Player stats update completed successfully for {target.display_name}!")

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
        msg += f"✅ Already existed: {', '.join(skipped)}"

    await ctx.send(msg or "❌ Something went wrong trying to create roles.")

@bot.command(name="set-channel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""

    config = load_config()
    config.setdefault(str(ctx.guild.id), {})["channel_id"] = ctx.channel.id
    save_config(config)

    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h stats updates.")

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

    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h stats updates.")

@bot.command(name="commands")
async def display_commands(ctx):
    lines = ["**All commands:**"]
    admin_lines = ["**Administrator only:**"]

    for cmd in bot.commands:
        if cmd.hidden:
            continue

        # figure out if it's admin-only by checking its checks
        is_admin = any(
            getattr(check, '__qualname__', '').startswith('has_permissions')
            for check in cmd.checks
        )

        line = f"!{cmd.name}"
        if cmd.help:
            line += f" — {cmd.help}"

        if is_admin:
            admin_lines.append(line)
        else:
            lines.append(line)

    message = "\n".join(lines) + "\n\n" + "\n".join(admin_lines)
    await ctx.send(message)

@bot.command(name='info')
async def display_info(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Bot assigns roles based on Bf6 career rank! Use !set-channel to assign for bot spam. Firstly administrator has to link member to their {DEFAULT_PLATFORM} account using !commands. Updating automatically every {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h.")

@bot.command(name='supported-platforms')
async def display_supported_playforms(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")


