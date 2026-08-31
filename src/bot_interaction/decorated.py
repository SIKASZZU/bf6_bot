import time
import discord
from discord import app_commands
from src.globals import REQUEST_INTERVAL_SECONDS, bot, AUTO_UPDATE_TIMER_HOURS, running_loops
from src.data.config import load_config, save_config, delete_config_key
from src.data.data import load_data, save_data, delete_data_key
from src.helper.helper import log, send_interaction_message, WrongChannelError
from src.bot_interaction.loop import start_guild_update_loop

_last_command_time = 0

async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # 1. DM Guard
    if not interaction.guild:
        return True

    # 2. Rate-limiter / Cooldown check
    global _last_command_time
    now = time.monotonic()
    if now - _last_command_time < REQUEST_INTERVAL_SECONDS:
        raise app_commands.CheckFailure(f"{REQUEST_INTERVAL_SECONDS} cooldown after every command!")
    _last_command_time = now

    # Load full configuration safely
    full_config = load_config()
    guild_id_str = str(interaction.guild.id)
    guild_config = full_config.get(guild_id_str, {})

    # 3. Admin-or-role check
    if not interaction.user.guild_permissions.administrator:
        role_id = guild_config.get('permissioned_role_id')
        if not (role_id and discord.utils.get(interaction.user.roles, id=role_id)):
            role = interaction.guild.get_role(role_id) if role_id else None
            role_str = role.mention if role else "a required role"
            raise app_commands.CheckFailure(f"Missing {role_str} or Administrator permissions.")

    # 4. Report-channel restriction
    if (channel_id := guild_config.get('channel_id')):
        if interaction.guild.get_channel(channel_id) is None:
            # Channel deleted - reset setting safely across full config
            guild_config['channel_id'] = None
            full_config[guild_id_str] = guild_config
            save_config(full_config)
            return True

        if interaction.channel.id != channel_id:
            raise WrongChannelError(channel_id)

    return True

bot.tree.interaction_check = global_interaction_check

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, WrongChannelError):
        await send_interaction_message(interaction, f"❌ This command can only be used in <#{error.channel_id}>.", ephemeral=True)
        return

    if isinstance(error, app_commands.CheckFailure):
        await send_interaction_message(interaction, f"❌ You don't have permission to use this command. Requires **Administrator** or the `/show-authorised-role` role.", ephemeral=True)
        return

    log(interaction.guild, f"Unhandled error in command '{interaction.command.name if interaction.command else '?'}': {error}")
    await send_interaction_message(interaction, f"❌ An unexpected error occurred: {error}", ephemeral=True)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}!")

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log(guild, f"Synced {len(synced)} commands to {guild.name} ({guild.id})")

        start_guild_update_loop(guild)

    # if not update_all_players.is_running():
    #     update_all_players.start()

@bot.event
async def on_guild_join(guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    config = load_config()
    server_key = str(guild.id)

    msg = f'[JOINED] bot into {guild.name} id: {guild.id}\n'

    if server_key not in config:
        config[server_key] = {
            "channel_id": None,
            "update_interval": AUTO_UPDATE_TIMER_HOURS
        }
        save_config(config)
        msg += f"Initialized default config configuration for server.\n"

    data = load_data()
    if server_key not in data:
        data[server_key] = {}
        save_data(data)
        msg += f"Initialized default data configuration for server."

    log(guild, msg)
    start_guild_update_loop(guild)

@bot.event
async def on_guild_remove(guild):
    config = load_config()
    server_key = str(guild.id)

    msg = f'[REMOVED] bot from {guild.name} id: {guild.id}\n'

    if server_key in config:
        delete_config_key(server_key)
        msg += f"Removed configuration for server.\n"

    data = load_data()
    if server_key in data:
        delete_data_key(server_key)
        msg += f"Removed saved data for server."

    log(guild, msg)

    existing = running_loops.pop(guild.id, None)
    if existing:
        existing.cancel()

@bot.event
async def on_member_remove(member: discord.Member):
    data = load_data()

    if str(member.guild.id) in data and str(member.id) in data[str(member.guild.id)]:
        del data[str(member.guild.id)][str(member.id)]
        save_data(data)
        log(member.guild, f"[LEFT] `{member.name}` ({str(member.id)}) left the guild - removed their link from data.")

