import unittest

from helper import remove_rank_role


class FakeRole:
    def __init__(self, name):
        self.name = name
        self.mention = f"@{name}"

class FakeMember:
    def __init__(self, roles):
        self.roles = roles
        self.removed = []
        self.name = "TestUser"

    async def remove_roles(self, role, reason):
        self.removed.append((role.name, reason))

class FakeGuild:
    def __init__(self, id, roles=None):
        self.roles = roles or []
        self.name = f"Guild {id}"

class TestRoleRemoval(unittest.IsolatedAsyncioTestCase):
    async def test_remove_rank_role_removes_old_rank_roles_by_name(self):
        current_role = FakeRole("Major")
        old_role = FakeRole("Kapral")
        member = FakeMember([current_role, old_role])
        guild = FakeGuild(id=123)

        result = await remove_rank_role(guild, member, "Major")

        self.assertEqual(member.removed, [("Kapral", "Rank sync - removing obsolete roles")])
        self.assertEqual(result, {
            "success": True,
            "value": "Removed roles: @Kapral",
            "rank_removed": "@Kapral",
        })

    async def test_remove_rank_role_resolves_string_role_names(self):
        current_role = FakeRole("Major")
        old_role = FakeRole("Kapral")
        member = FakeMember([current_role, old_role])
        guild = FakeGuild(id=123, roles=[old_role])

        result = await remove_rank_role(guild, member, "Major")

        self.assertEqual(member.removed, [("Kapral", "Rank sync - removing obsolete roles")])
        self.assertTrue(result["success"])

if __name__ == "__main__":
    unittest.main()
