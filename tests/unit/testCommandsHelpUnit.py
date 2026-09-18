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
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.mention = f"<@{id}>"


class FakeGuildWithMember(FakeGuild):
    def __init__(self, id, member):
        super().__init__(id)
        self._member = member

    def get_member(self, member_id):
        return self._member if member_id == self._member.id else None

def _embed_text(embeds) -> str:
    """Flattens one Embed or a list of Embeds into searchable plain text."""
    if isinstance(embeds, discord.Embed):
        embeds = [embeds]

    parts = []
    for e in embeds:
        parts += [e.title or "", e.description or ""]
        for f in e.fields:
            parts += [f.name or "", f.value or ""]
        if e.footer.text:
            parts.append(e.footer.text)
    return "\n".join(parts)

class TestCommandHelpMessages(unittest.TestCase):
    def assertInEmbed(self, check_for: str, embeds):
        """Asserts check_for appears anywhere in an Embed or list of Embeds."""
        self.assertIn(check_for, _embed_text(embeds), f"'{check_for}' was not found in the embed(s).")

    def assertNotInEmbed(self, check_for: str, embeds):
        self.assertNotIn(check_for, _embed_text(embeds), f"'{check_for}' was unexpectedly found in the embed(s).")

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
        member = FakeMember(id=456, name='CoolPlayer')
        fake_guild = FakeGuildWithMember(id=123, member=member)

        message = helper._build_linked_message(fake_guild, data)

        self.assertInEmbed('alice', message)
        self.assertInEmbed('CoolPlayer', message)
        self.assertNotInEmbed('<left server>', message)

if __name__ == '__main__':
    unittest.main()