import unittest

from commands import _build_commands_help_message, _build_links_message


class FakeGuild:
    def __init__(self, id):
        self.id = id

    def get_member(self, member_id):
        return None  # simulate no cached members for this test
class FakeMember:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeGuildWithMember(FakeGuild):
    def __init__(self, id, member):
        super().__init__(id)
        self._member = member

    def get_member(self, member_id):
        return self._member if member_id == self._member.id else None

class TestCommandHelpMessages(unittest.TestCase):
    def test_build_commands_help_message_includes_slash_commands(self):
        message = _build_commands_help_message()

        self.assertIn('!commands', message)
        self.assertIn('/link', message)
        self.assertIn('/update', message)

    def test_build_links_message_includes_linked_accounts(self):
        data = {
            '123': {
                '456': {'name': 'alice', 'platform': 'EA'}
            }
        }

        fake_guild = FakeGuild(id=123)
        message = _build_links_message(fake_guild, data)

        self.assertIn('alice', message)
        self.assertIn('EA', message)
        self.assertIn('456', message)

    def test_build_links_message_uses_display_name_when_member_found(self):
        data = {'123': {'456': {'name': 'alice', 'platform': 'EA'}}}
        member = FakeMember(id=456, display_name='CoolPlayer')
        fake_guild = FakeGuildWithMember(id=123, member=member)

        message = _build_links_message(fake_guild, data)

        self.assertIn('CoolPlayer', message)
        self.assertNotIn('<left server>', message)

if __name__ == '__main__':
    unittest.main()