import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

import helper
from helper import update_all_players


class FakeGuild:
    def __init__(self, guild_id, members=None):
        self.id = guild_id
        self.name = f"Guild {guild_id}"
        self.members = members or []


class FakeMember:
    def __init__(self, name):
        self.display_name = name
        self.bot = False


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestGuildSelection(unittest.IsolatedAsyncioTestCase):
    async def test_update_all_players_uses_the_requested_guild(self):
        guild_a = FakeGuild(111, [FakeMember("Alice")])
        guild_b = FakeGuild(222, [FakeMember("Bob")])

        with patch("helper.bot.wait_until_ready", new=AsyncMock()), \
             patch("helper.load_config", return_value={}), \
             patch.object(type(helper.bot), "guilds", new_callable=PropertyMock, return_value=[guild_a, guild_b]), \
             patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
             patch("helper._update_member", new=AsyncMock(return_value=True)) as update_member:
            await update_all_players(guild=guild_b)

        self.assertEqual(update_member.await_count, 1)
        self.assertEqual(update_member.await_args_list[0].args[0], guild_b)


if __name__ == "__main__":
    unittest.main()
