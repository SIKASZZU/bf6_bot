import unittest

from src.globals import build_api_url


class TestApiFunctionality(unittest.IsolatedAsyncioTestCase):

    def test_builds_correct_url(self):
        url = build_api_url('sikzu', 'EA', nucleus_id='1', player_id='2')

        self.assertIn('platform=EA', url)
        self.assertNotIn('name=sikzu', url)

    def test_fills_url_with_name(self):
        url = build_api_url('sikzu', 'EA', nucleus_id=None, player_id='2')

        self.assertIn('name=sikzu', url)
        self.assertIn('playerid=2', url)
        self.assertIn('platform=EA', url)

    def test_build_url_with_name_if_ids_missing(self):
        url = build_api_url('sikzu', 'EA', nucleus_id=None, player_id=None)

        self.assertIn('name=sikzu', url)
        self.assertIn('platform=EA', url)

        self.assertNotIn('nucleus_id', url)
        self.assertNotIn('playerid', url)


if __name__ == '__main__':
    unittest.main()
