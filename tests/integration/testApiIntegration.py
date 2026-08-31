import unittest
import aiohttp

from src.helper.helper import build_api_url

class TestApiFunctionality(unittest.IsolatedAsyncioTestCase):

    async def test_api_success(self):
        API_URL = build_api_url('sikzu')

        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as response:
                self.assertEqual(200, response.status, 'Response status OK')

if __name__ == '__main__':
    unittest.main()