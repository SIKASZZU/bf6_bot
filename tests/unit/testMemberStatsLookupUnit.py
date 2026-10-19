import unittest
from unittest.mock import AsyncMock, patch

import src.helper as helper


class FakeGuild:
    id = 123


class FakeMember:
    id = 456
    name = "Player"
    bot = False


class FakeSession:
    def get(self, url):
        raise OSError(f"stats API unavailable: {url}")


class TestMemberStatsLookup(unittest.IsolatedAsyncioTestCase):
    async def test_query_returns_empty_ids_after_retries_fail(self):
        with patch("src.helper.API_MAX_RETRIES", 1):
            result = await helper._query_member_stats("Player", "EA", FakeSession())

        self.assertEqual(result, (None, None))

    async def test_update_uses_saved_player_id_when_nucleus_id_exists(self):
        guild = FakeGuild()
        member = FakeMember()
        data = {"123": {"456": {"name": "Player", "nucleus_id": 789, "player_id": 987}}}
        session = object()

        with patch("src.helper.bot.wait_until_ready", new=AsyncMock()), \
            patch("src.helper.get_player_entry", return_value=data["123"]["456"]), \
            patch("src.helper.load_data", return_value=data), \
            patch("src.helper._query_member_stats", new=AsyncMock()) as query_stats, \
            patch("src.helper.fetch_player_stats", new=AsyncMock(return_value={"profile": True})) as fetch_stats, \
            patch("src.helper.get_rank_value_from_data", return_value=1), \
            patch("src.helper.getRankNameFromCareerRank", return_value="Major"), \
            patch("src.helper.assign_rank_role", new=AsyncMock(return_value={"success": True, "value": ""})), \
            patch("src.helper.remove_rank_role", new=AsyncMock(return_value={"success": True, "value": ""})), \
            patch("src.helper.save_data"):
            result = await helper._update_member(guild, member, session)

        query_stats.assert_not_awaited()
        fetch_stats.assert_awaited_once_with(guild, session, "Player", "EA", 789, 987)
        self.assertTrue(result["success"])

    async def test_update_continues_by_name_when_stats_lookup_fails(self):
        guild = FakeGuild()
        member = FakeMember()
        session = object()

        with patch("src.helper.bot.wait_until_ready", new=AsyncMock()), \
            patch("src.helper.load_data", return_value={"123": {"456": {"name": "Player"}}}), \
            patch("src.helper.get_player_entry", return_value={"name": "Player"}), \
            patch("src.helper._query_member_stats", new=AsyncMock(return_value=(None, None))), \
            patch("src.helper.fetch_player_stats", new=AsyncMock(return_value=None)) as fetch_stats:
            result = await helper._update_member(guild, member, session)

        fetch_stats.assert_awaited_once_with(guild, session, "Player", "EA", None, None)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
