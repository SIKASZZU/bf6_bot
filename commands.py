from discord.ext import commands

from globals import *
from helper import load_data, save_data, update_all_players


@bot.command(name='link')
async def link(ctx, platform: str = DEFAULT_PLATFORM, *, name: str):
    """
    Links your Discord account to a game account.
    Usage: !link [platform] <name> 
    Example for a Steam player: !link steam Sikzu
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(ctx.author.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"✅ Successfully linked your Discord account to `{name}` on platform `{platform}`!")

@bot.command(name="link-user")
@commands.has_permissions(administrator=True)
async def link_user(ctx, member: discord.Member, platform: str = DEFAULT_PLATFORM, *, name: str, ):
    """
    Admin-only: link someone else's Discord account to a game account.
    Usage: !link-user <@member> [platform] <name>
    Example: !link-user @Oljake Oljake
    Example for Steam: !link-user @Oljake steam Oljake
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(member.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"✅ Linked {member.mention} to `{name}` on platform `{platform}`!")

@bot.command(name="set-channel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""
    global UPDATE_CHANNEL_ID
    UPDATE_CHANNEL_ID = ctx.channel.id
    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the 24h stats updates.")


@bot.command(name="update-all")
@commands.has_permissions(administrator=True)
async def force_update_all(ctx):
    """Manually forces the background update logic to run immediately via chat."""
    await ctx.send("🔄 Manually initiating a global player stats update...")

    try:
        await update_all_players()
        await ctx.send("✅ Global player stats update completed successfully!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred during the update: {e}")
        print(f"Manual update error: {e}")


@bot.command(name="commands")
async def display_commands(ctx):
    """
    Update this method manually.
    Sends a message to channel containing all the commands
    """

    await ctx.send(f"\
        All the commands:                       \n\
        !link [platform] <name> (platform optional)                 \n\
        !link-user <@member> [platform] <name> (platform optional)  \n\
        !update-all                              \n\
        !set-channel                             \n\
        !info                                   \n\
        !supported-platforms                    \n\
    ")

@bot.command(name='info')
async def display_info(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Bot assigns roles based on Bf6 career rank! Firstly administrator has to link member to member's {DEFAULT_PLATFORM.upper()} account using !commands. Updating automatically every {AUTO_UPDATE_TIMER}.")

@bot.command(name='supported-platforms')
async def display_info(ctx):
    """ Sends a message to channel containing information about and use cases of bot."""
    await ctx.send(f"Default platform: {DEFAULT_PLATFORM} \n All supported: {', '.join(sorted(VALID_PLATFORMS))}")


