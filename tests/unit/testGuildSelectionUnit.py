import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

import helper


class FakeGuild:
    def __init__(self, guild_id, members=None):
        self.id = guild_id
        self.name = f"Guild {guild_id}"
        self.members = members or []

    def get_member(self, member_id):
        for member in self.members:
            if getattr(member, "id", None) == int(member_id):
                return member
        return None

class FakeMember:
    def __init__(self, member_id, name=None):
        self.id = int(member_id)
        self.display_name = name or str(member_id)
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
    async def test_run_guild_update_updates_every_member_of_the_given_guild(self):
        guild_a = FakeGuild(111, [FakeMember(1, "Alice")])
        guild_b = FakeGuild(222, [FakeMember(1, "Bob"), FakeMember(2, "Carol")])

        with patch("helper.load_config", return_value={"222": {"channel_id": 999}, "111": {"channel_id": 999}}), \
            patch("helper.load_data", return_value={"222": {"1": {}, "2": {}}}), \
            patch("helper.bot.get_channel", return_value=FakeChannel(999)), \
            patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
            patch("helper._update_member", new=AsyncMock(return_value=True)) as update_member:
            await helper._run_guild_update(guild_b)

        self.assertEqual(update_member.await_count, 2)
        self.assertTrue(all(call.args[0] is guild_b for call in update_member.await_args_list))

    async def test_run_guild_update_resolves_configured_channel(self):
        guild = FakeGuild(111, [FakeMember(1, "Alice")])
        fake_channel = object()

        with patch("helper.load_config", return_value={"111": {"channel_id": 999}}), \
            patch("helper.load_data", return_value={"111": {"1": {}}}), \
            patch("helper.bot.get_channel", return_value=fake_channel) as get_channel, \
            patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
            patch("helper._update_member", new=AsyncMock(return_value=True)) as update_member:
            await helper._run_guild_update(guild)

        get_channel.assert_called_once_with(999)
        self.assertEqual(update_member.await_args_list[0].args[3], fake_channel)

    async def test_run_guild_update_continues_after_a_member_raises(self):
        guild = FakeGuild(111, [FakeMember(1, "Alice"), FakeMember(2, "Bob")])

        with patch("helper.load_config", return_value={"111": {"channel_id": 999}}), \
            patch("helper.load_data", return_value={"111": {"1": {}, "2": {}}}), \
            patch("helper.bot.get_channel", return_value=FakeChannel(999)), \
            patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
            patch("helper._update_member", new=AsyncMock(side_effect=[Exception("boom"), True])) as update_member:
            failed_to_update: list = await helper._run_guild_update(guild)

        self.assertEqual(update_member.await_count, 2)
        self.assertEqual(len(failed_to_update), 1)

    # async def test_run_guild_update_calls_on_progress_after_each_successful_update(self):
    #     guild = FakeGuild(111, [FakeMember("Alice"), FakeMember("Bob")])
    #     progress_calls = []

    #     async def on_progress(done, total):
    #         progress_calls.append((done, total))

    #     with patch("helper.load_config", return_value={}), \
    #         patch("helper.load_data", return_value={"111": {"1": {}, "2": {}}}), \
    #         patch("helper.aiohttp.ClientSession", return_value=DummySession()), \
    #         patch("helper._update_member", new=AsyncMock(return_value=True)):
    #         await helper._run_guild_update(guild, on_progress=on_progress)

    #     self.assertEqual(progress_calls, [(1, 2), (2, 2)])

if __name__ == "__main__":
    unittest.main()
