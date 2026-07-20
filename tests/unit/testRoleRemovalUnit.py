import unittest
from unittest.mock import AsyncMock, patch

from helper import remove_rank_role


class FakeRole:
    def __init__(self, name):
        self.name = name


class FakeMember:
    def __init__(self, roles):
        self.roles = roles
        self.removed = []
        self.display_name = "TestUser"

    async def remove_roles(self, role, reason):
        self.removed.append((role.name, reason))


class FakeGuild:
    def __init__(self, roles=None):
        self.roles = roles or []


class TestRoleRemoval(unittest.IsolatedAsyncioTestCase):
    async def test_remove_rank_role_removes_old_rank_roles_by_name(self):
        current_role = FakeRole("Major")
        old_role = FakeRole("Kapral")
        member = FakeMember([current_role, old_role])
        guild = FakeGuild()

        with patch("helper.get_role", new=AsyncMock(return_value=old_role)):
            await remove_rank_role(guild, member, "Major")

        self.assertEqual(member.removed, [("Kapral", "Rank sync - removing role")])

    async def test_remove_rank_role_resolves_string_role_names(self):
        current_role = FakeRole("Major")
        old_role = FakeRole("Kapral")
        member = FakeMember([current_role, old_role])
        guild = FakeGuild([old_role])

        with patch("helper.get_role", new=AsyncMock(return_value="Kapral")):
            await remove_rank_role(guild, member, "Major")

        self.assertEqual(member.removed, [("Kapral", "Rank sync - removing role")])


if __name__ == "__main__":
    unittest.main()
