from discord.ext import commands
from discord import app_commands

from globals import *
from helper import load_data, save_data, update_all_players, update_player


@bot.command(name='link')
async def link(ctx, *, name: str):
    """
    Links your Discord account to a game account.
    Usage: !link <name>
    """

    platform = DEFAULT_PLATFORM
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(ctx.guild.id)][str(ctx.author.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"✅ Successfully linked your Discord account to `{name}` on platform `{platform}`!")

@bot.command(name="update")
async def force_update(ctx):
    """Manually forces update on member. """
    await ctx.send("🔄 Updating...")

    try:
        await update_player(ctx.author, report_channel=ctx.channel)
        await ctx.send("✅ Player stats update completed successfully!")

    except Exception as e:
        await ctx.send(f"❌ An error occurred during the update: {e}")
        print(f"Manual update error: {e}")


@bot.command(name="link-user")
@commands.has_permissions(administrator=True)
async def link_user(ctx, member: discord.Member, *, name: str, ):
    """
    Admin-only: link someone else's Discord account to a game account.
    Usage: !link-user <@member> <name>
    """

    platform = DEFAULT_PLATFORM
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(ctx.guild.id)][str(member.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"✅ Linked {member.mention} to `{name}` on platform `{platform}`!")

@bot.command(name="set-channel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""

    config = load_config()
    config[str(ctx.guild.id)]["channel_id"] = ctx.channel.id
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
    config[str(ctx.guild.id)]["update_interval"] = hours
    save_config(config)

    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h stats updates.")

@bot.command(name="update-user")
@commands.has_permissions(administrator=True)
async def force_update_member(ctx, member: discord.Member):
    """Manually forces update on member. """
    await ctx.send("🔄 Looking for update on player...")

    try:
        await update_player(member, report_channel=ctx.channel)
        # await update_all_players(report_channel=ctx.channel)
        await ctx.send("✅ Player stats update completed successfully!")

    except Exception as e:
        await ctx.send(f"❌ An error occurred during the update: {e}")
        print(f"Manual update error: {e}")

@bot.command(name="update-all")
@commands.has_permissions(administrator=True)
async def force_update_all(ctx):
    """Manually forces the background update logic to run immediately via chat."""
    await ctx.send("🔄 Automatic update in progress... ")

    try:
        await update_all_players(report_channel=ctx.channel)
        await ctx.send("✅ Automatic update complete!")

    except Exception as e:
        await ctx.send(f"❌ An error occurred during the update: {e}")
        print(f"Manual update error: {e}")

@bot.command(name="commands")
async def display_commands(ctx):
    await ctx.send(f"\
        All the commands:                       \n\
        !info                                   \n\
        !link <name>                            \n\
        !update                                 \n\
        --- Administrator only commands! ---    \n\
        !link-user <@member> <name>             \n\
        !set-channel                            \n\
        !set-update-interval <hours>            \n\
        !update-user <@member>                  \n\
        !update-all                             \n\
        "
        # !supported-platforms                    \n\
    )

@bot.command(name='info')
async def display_info(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Bot assigns roles based on Bf6 career rank! Use !set-channel to assign for bot spam. Firstly administrator has to link member to their {DEFAULT_PLATFORM} account using !commands. Updating automatically every {load_config().get(str(ctx.guild.id), {}).get('update_interval')}h.")

@bot.command(name='supported-platforms')
async def display_supported_playforms(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")


