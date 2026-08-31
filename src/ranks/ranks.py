import discord
from src.ranks.base_ranks import EN_RANK_TIERS
from src.ranks.estonian_ranks import EN_TO_ET

# Import log locally to avoid circular imports
def _get_log():
    from src.helper.helper import log
    return log

def _build_r_dict() -> dict:
    r_dict = {}
    for base_name, tiers in EN_RANK_TIERS.items():
        et_base = EN_TO_ET[base_name]
        for suffix, bounds in tiers:
            role_name = f"{et_base} {suffix}".strip() if suffix else et_base
            r_dict[role_name] = bounds
    return r_dict

r_dict = _build_r_dict()

def get_rank_name(userCareerRank: int) -> str:
    for rank_name, (min_val, max_val) in r_dict.items():

        if min_val == max_val and max_val <= userCareerRank:
            return rank_name

        if min_val <= userCareerRank <= max_val:
            return rank_name
    return None

async def create_roles(guild: discord.Guild):
    existing_role_names = {role.name for role in guild.roles}

    created = []
    skipped = []
    failed = []
    cap_reached = False

    for rank_name in r_dict.keys():
        if rank_name in existing_role_names:
            skipped.append(rank_name)
            continue

        if cap_reached:
            # Already know every further create_role call will fail identically -
            # don't burn API calls/rate limit budget confirming that repeatedly.
            failed.append(rank_name)
            continue

        try:
            await guild.create_role(
                name=rank_name,
                mentionable=True,
                reason="Auto-created by bot for rank system"
            )
            created.append(rank_name)

        except discord.HTTPException as e:
            if e.code == 30005:
                cap_reached = True
                _get_log()(guild, f'Server hit the 250-role cap ({len(guild.roles)} roles) - stopping role creation.')
            else:
                _get_log()(guild, fail_msg := f'Failed to create role. Error {e}')
            failed.append(rank_name)

        except Exception as e:
            _get_log()(guild, fail_msg := f'Failed to create role. Error {e}')
            failed.append(rank_name)

    return created, skipped, failed, cap_reached

async def remove_rank_role(guild: discord.Guild, member: discord.Member, current_rank_name: str) -> dict:
    """
    Removes all obsolete rank roles from a member, keeping only their current rank role.

    return_value = {
        "success": bool,
        "value": string
        "rank_removed": string|None
    }
    """
    all_rank_names = r_dict.keys()

    # Identify obsolete roles the member currently holds
    roles_to_remove = [
        role for role in member.roles
        if role.name in all_rank_names and role.name != current_rank_name
    ]

    if not roles_to_remove:
        # log(guild, msg := f"No obsolete rank roles to remove.")
        return {"success": True, "value": f"No obsolete rank roles to remove.", "rank_removed": None}

    try:
        await member.remove_roles(*roles_to_remove, reason="Rank sync - removing obsolete roles")
        removed_names = ", ".join(role.mention for role in roles_to_remove)
        # log(guild, msg := f"Removed roles: {removed_names}.")
        return {"success": True, "value": f"Removed roles: {removed_names}", "rank_removed": removed_names}

    except Exception as e:
        # log(guild, return_msg := f"Remove rank error: {e}")
        return {"success": False, "value": f"Remove rank error: {e}"}

async def assign_rank_role(guild: discord.Guild, member: discord.Member, rank_name: str) -> dict:
    """
    Ensures the role for rank_name exists, then gives it to member, removing other rank roles.

    return_value = {
        "success": bool,
        "value": string|None
        "rank_added": string|None
    }
    """
    if not rank_name:
        _get_log()(guild, return_msg := 'Returning! rank_name is None.')
        return {"success": False, "value": return_msg}

    if not (role := discord.utils.get(guild.roles, name=rank_name)):
        _get_log()(guild, return_msg := 'Returning! Role is None.')
        return {"success": False, "value": return_msg}

    if role.position >= guild.me.top_role.position:
        _get_log()(guild, return_msg := f"Bot's role is too low to assign {role.mention} - move the bot's role higher.")
        return {"success": False, "value": return_msg}

    try:
        return_msg = None
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            _get_log()(guild, return_msg := f"Assigned rank: {role.mention}")

        return {"success": True, "value": return_msg or f'Already has rank: {role.mention}', "rank_added": rank_name if return_msg else None }

    except Exception as e:
        _get_log()(guild, return_msg := f"Assign role error: {e}")
        return {"success": False, "value": return_msg}

def get_rank_value_from_data(stats: dict) -> int:
    """
    Extracts rank from the bf6 profile response.

    Public profile:
    {
      "playerProfiles": [
        {
          "playerCard": {"rank": 254, ...},
          "rankName": "Major",
          ...
        }
      ]
    }
    Private profile:
    {
    "other": [
        {
        "playerProfiles": [
            {
            "rank": 134,
            "badges": 81,
            "rankName": "Second Lieutenant IV",
            ...
            }
        ]
        }
    ]
    }
    """

    if not isinstance(stats, dict):
        return None

    profiles = stats.get("playerProfiles")
    if not profiles and isinstance(stats.get("other"), list) and stats["other"]:
        profiles = stats["other"][0].get("playerProfiles")

    if not isinstance(profiles, list) or not profiles:
        return None

    profile = profiles[0]

    player_card = profile.get("playerCard")
    if isinstance(player_card, dict) and "rank" in player_card:
        return player_card.get("rank")

    if "rank" in profile:
        return profile.get("rank")

    return None

def _has_rank_change(return_value: dict) -> bool:
    """True only if this member's update actually assigned or removed a rank
    role. Used to filter out no-op successes from the automatic update report."""
    assign = return_value.get('assign_rank_role') or {}
    remove = return_value.get('remove_rank_role') or {}
    return bool(assign.get('rank_added')) or bool(remove.get('rank_removed'))