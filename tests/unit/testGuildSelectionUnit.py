import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

import helper


class FakeGuild:
    def __init__(self, guild_id, members=None):
        self.id = guild_id
        self.name = f"Guild {guild_id}"
        self.members = members or []


class FakeMember:
    def __init__(self, name):
        self.display_name = name
        self.bot = False


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.name = f"channel-{channel_id}"

class FakeResponse:
    def __init__(self, is_done=False):
        self._is_done = is_done
        self.messages = []

    def is_done(self):
        return self._is_done

    async def send_message(self, message, **kwargs):
        self.messages.append((message, kwargs))


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):
        self.messages.append((message, kwargs))


class FakeInteraction:
    def __init__(self, is_done=False):
        self.response = FakeResponse(is_done=is_done)
        self.followup = FakeFollowup()

class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestGuildSelection(unittest.IsolatedAsyncioTestCase):
    async def test_update_all_players_uses_the_requested_guild(self):
        guild_a = FakeGuild(111, [FakeMember("Alice")])
        guild_b = FakeGuild(222, [FakeMember("Bob")])
        interaction = FakeInteraction()

        with patch("helper.bot.wait_until_ready", new=AsyncMock()), \
             patch("helper.load_config", return_value={}), \
             patch.object(type(helper.bot), "guilds", new_callable=PropertyMock, return_value=[guild_a, guild_b]), \
             patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
             patch("helper._update_member", new=AsyncMock(return_value=True)) as update_member:
            await helper.update_all_players(interaction, guild=guild_b)

        self.assertEqual(update_member.await_count, 1)
        self.assertEqual(update_member.await_args_list[0].args[0], guild_b)

    async def test_update_all_players_uses_all_available_guilds_when_no_guild_is_provided(self):
        guild_a = FakeGuild(111, [FakeMember("Alice")])
        guild_b = FakeGuild(222, [FakeMember("Bob")])
        interaction = FakeInteraction()

        with patch("helper.bot.wait_until_ready", new=AsyncMock()), \
             patch("helper.load_config", return_value={}), \
             patch.object(type(helper.bot), "guilds", new_callable=PropertyMock, return_value=[guild_a, guild_b]), \
             patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
             patch("helper._update_member", new=AsyncMock(return_value=True)) as update_member:
            await helper.update_all_players(interaction)

        self.assertEqual(update_member.await_count, 2)
        self.assertEqual({call.args[0].id for call in update_member.await_args_list}, {111, 222})

if __name__ == "__main__":
    unittest.main()
