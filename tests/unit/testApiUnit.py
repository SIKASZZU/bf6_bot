import unittest

from globals import build_api_url

class TestApiFunctionality(unittest.IsolatedAsyncioTestCase):

    def test_builds_correct_url(self):
        url = build_api_url('sikzu', 'EA')
        self.assertIn('name=sikzu', url)
        self.assertIn('platform=EA', url)

if __name__ == '__main__':
    unittest.main()
