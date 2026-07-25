import unittest

from app.modules.pending_players import PendingPlayers


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class PendingPlayersTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.players = PendingPlayers(
            ttl_seconds=300,
            max_size=2,
            clock=self.clock,
        )

    def test_players_are_unique_and_keep_insertion_order(self):
        self.players.add("alice")
        self.players.add("bob")
        self.players.add("alice")

        self.assertEqual(self.players.to_list(), ["bob", "alice"])

    def test_oldest_player_is_evicted_at_capacity(self):
        self.players.add("alice")
        self.players.add("bob")
        self.players.add("charlie")

        self.assertEqual(self.players.to_list(), ["bob", "charlie"])

    def test_expired_players_are_removed(self):
        self.players.add("alice")
        self.clock.value = 301

        self.assertEqual(self.players.to_list(), [])
        self.assertNotIn("alice", self.players)

    def test_discard_removes_player(self):
        self.players.add("alice")

        self.players.discard("alice")

        self.assertEqual(self.players.to_list(), [])


if __name__ == "__main__":
    unittest.main()
