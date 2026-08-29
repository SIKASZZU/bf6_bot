import discord
from globals import log
from english_ranks import EN_RANK_TIERS
from estonian_ranks import EN_TO_ET


def _build_r_dict() -> dict:

    r_dict = {}
    for base_name, tiers in EN_RANK_TIERS.items():
        et_base = EN_TO_ET[base_name]
        for suffix, bounds in tiers:
            role_name = f"{et_base} {suffix}".strip() if suffix else et_base
            r_dict[role_name] = bounds
    return r_dict


r_dict = _build_r_dict()


def get_role_dict():
    return r_dict


def getRankNameFromCareerRank(userCareerRank: int) -> str:
    for rank_name, (min_val, max_val) in r_dict.items():
        if min_val <= userCareerRank <= max_val:
            return rank_name
    return None

async def create_roles(guild: discord.Guild):
    existing_role_names = {role.name for role in guild.roles}

    created = []
    skipped = []
    failed = []

    for rank_name in r_dict.keys():
        if rank_name in existing_role_names:
            skipped.append(rank_name)
            continue

        try:
            await guild.create_role(
                name=rank_name,
                mentionable=True,
                reason="Auto-created by bot for rank system"
            )
            created.append(rank_name)

        except Exception as e:
            log(guild, fail_msg := f'Failed to create role. Error {e}')
            failed.append(rank_name)

    return created, skipped, failed