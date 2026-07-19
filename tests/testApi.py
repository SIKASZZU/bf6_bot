import unittest
import aiohttp

from globals import build_api_url

class TestApiFunctionality(unittest.IsolatedAsyncioTestCase):

    async def test_api_success(self):
        API_URL = build_api_url('sikzu', 'EA')

        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as response:
                self.assertEqual(200, response.status, 'Response status OK')

    def test_builds_correct_url(self):
        url = build_api_url('sikzu', 'EA')
        self.assertIn('name=sikzu', url)
        self.assertIn('platform=EA', url)

if __name__ == '__main__':
    unittest.main()
