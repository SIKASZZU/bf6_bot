from discord.ext import commands

from globals import *
from helper import load_data, save_data, update_all_players


@bot.command(name='link')
async def link(ctx, name: str, platform: str = DEFAULT_PLATFORM):
    """
    Links your Discord account to a game account.
    Usage: !link <name> [platform]
    platform defaults to 'ea'. Valid values: ea, xbox, psn, steam, epic, pc, xboxone, ps4, xboxseries, ps5
    Example for a Steam player: !link Sikzu steam
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(ctx.author.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"Successfully linked your Discord account to **{name}** on platform `{platform}`! I will track your stats automatically.")

@bot.command(name="linkuser")
@commands.has_permissions(administrator=True)
async def link_user(ctx, member: discord.Member, name: str, platform: str = DEFAULT_PLATFORM):
    """
    Admin-only: link someone else's Discord account to a game account.
    Usage: !linkuser <@member> <name> [platform]
    Example: !linkuser @Oljake Oljake
    Example for Steam: !linkuser @Oljake Oljake steam
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(member.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"Linked {member.mention} to **{name}** on platform `{platform}`!")

@bot.command(name="setchannel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""
    global UPDATE_CHANNEL_ID
    UPDATE_CHANNEL_ID = ctx.channel.id
    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the 24h stats updates.")


@bot.command(name="updateall")
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
        !link <name> [platform]                 \n\
        !linkuser <@member> <name> [platform]   \n\
        !updateall                              \n\
        !setchannel                             \n\
    ")

