import unittest

from commands import _build_commands_help_message, _build_links_message


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

        message = _build_links_message('123', data)

        self.assertIn('alice', message)
        self.assertIn('EA', message)
        self.assertIn('456', message)


if __name__ == '__main__':
    unittest.main()
