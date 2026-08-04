import unittest
from types import SimpleNamespace

from app.modules.pending_players import PendingPlayers
from app.modules.team_membership import assign_player, remove_player


class TeamAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.teams = {
            "alpha": SimpleNamespace(name="alpha", players=["alice"], admins=[]),
            "beta": SimpleNamespace(name="beta", players=[], admins=[]),
        }
        self.pending_players = PendingPlayers(ttl_seconds=300, max_size=10)

    def test_assigns_pending_player_without_restart(self):
        self.pending_players.add("bob")

        affected = assign_player(self.teams, self.pending_players, "beta", "bob")

        self.assertEqual(affected, {"beta"})
        self.assertIn("bob", self.teams["beta"].players)
        self.assertNotIn("bob", self.pending_players)

    def test_moves_existing_player_and_persists_both_teams(self):
        affected = assign_player(self.teams, self.pending_players, "beta", "alice")

        self.assertEqual(affected, {"alpha", "beta"})
        self.assertNotIn("alice", self.teams["alpha"].players)
        self.assertIn("alice", self.teams["beta"].players)

    def test_assigns_team_admin_without_duplicate_membership(self):
        affected = assign_player(
            self.teams,
            self.pending_players,
            "beta",
            "alice",
            as_admin=True,
        )

        self.assertEqual(affected, {"alpha", "beta"})
        self.assertNotIn("alice", self.teams["alpha"].players)
        self.assertIn("alice", self.teams["beta"].admins)

    def test_unknown_team_does_not_change_membership(self):
        affected = assign_player(self.teams, self.pending_players, "missing", "alice")

        self.assertIsNone(affected)
        self.assertIn("alice", self.teams["alpha"].players)

    def test_remove_player_persists_affected_team(self):
        affected = remove_player(self.teams, "alice")

        self.assertEqual(affected, {"alpha"})
        self.assertNotIn("alice", self.teams["alpha"].players)


if __name__ == "__main__":
    unittest.main()
