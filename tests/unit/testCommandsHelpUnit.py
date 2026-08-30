import unittest
import discord
from commands import *
import helper


class FakeGuild:
    def __init__(self, id):
        self.id = id
        self.name = f"Guild {id}"

    def get_member(self, member_id):
        return None  # simulate no cached members for this test
class FakeMember:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.name = display_name
        self.mention = f"<@{id}>"


class FakeGuildWithMember(FakeGuild):
    def __init__(self, id, member):
        super().__init__(id)
        self._member = member

    def get_member(self, member_id):
        return self._member if member_id == self._member.id else None

class TestCommandHelpMessages(unittest.TestCase):
    def assertInEmbed(self, check_for: str, embed: discord.Embed):
        """Custom assertion to check if check_for exists anywhere in an embed."""
        embed_dict_str = str(embed.to_dict())
        self.assertIn(check_for, embed_dict_str, f"'{check_for}' was not found anywhere in the Embed.")

    def assertNotInEmbed(self, check_for: str, embed: discord.Embed):
        """Custom assertion to check if check_for exists anywhere in an embed."""
        embed_dict_str = str(embed.to_dict())
        self.assertNotIn(check_for, embed_dict_str, f"'{check_for}' was not found anywhere in the Embed.")

    def test_build_commands_message_includes_slash_commands(self):
        message = helper._build_commands_message()

        self.assertInEmbed('/commands', message)
        self.assertInEmbed('/link', message)
        self.assertInEmbed('/update', message)

    def test_build_commands_message_excludes_default_help_command(self):
        message = helper._build_commands_message()
        self.assertNotInEmbed('!help', message)

    def test_build_linked_message_includes_linked_accounts(self):
        data = {
            '123': {
                '456': {'name': 'alice', 'platform': 'EA'}
            }
        }

        fake_guild = FakeGuild(id=123)
        message = helper._build_linked_message(fake_guild, data)

        self.assertInEmbed('alice', message)
        self.assertInEmbed('456', message)

    def test_build_linked_message_uses_member_mention_when_member_found(self):
        data = {'123': {'456': {'name': 'alice', 'platform': 'EA'}}}
        member = FakeMember(id=456, display_name='CoolPlayer')
        fake_guild = FakeGuildWithMember(id=123, member=member)

        message = helper._build_linked_message(fake_guild, data)

        self.assertInEmbed('alice', message)
        self.assertInEmbed('CoolPlayer', message)
        self.assertNotInEmbed('<left server>', message)

if __name__ == '__main__':
    unittest.main()