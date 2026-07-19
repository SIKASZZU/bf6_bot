import unittest

from commands import send_interaction_message


class FakeResponse:
    def __init__(self, is_done=False):
        self._is_done = is_done
        self.messages = []

    def is_done(self):
        return self._is_done

    async def send_message(self, message, **kwargs):
        self.messages.append((message, kwargs))


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):
        self.messages.append((message, kwargs))


class FakeInteraction:
    def __init__(self, is_done=False):
        self.response = FakeResponse(is_done=is_done)
        self.followup = FakeFollowup()


class TestInteractionResponse(unittest.IsolatedAsyncioTestCase):
    async def test_uses_followup_when_interaction_already_responded(self):
        interaction = FakeInteraction(is_done=True)

        await send_interaction_message(interaction, "hello")

        self.assertEqual(interaction.followup.messages[0][0], "hello")
        self.assertEqual(interaction.response.messages, [])

    async def test_uses_response_when_interaction_not_yet_responded(self):
        interaction = FakeInteraction(is_done=False)

        await send_interaction_message(interaction, "hello")

        self.assertEqual(interaction.response.messages[0][0], "hello")
        self.assertEqual(interaction.followup.messages, [])


if __name__ == '__main__':
    unittest.main()
