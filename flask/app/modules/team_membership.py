from collections.abc import Mapping
from typing import Any, Optional

from .pending_players import PendingPlayers


def assign_player(
    teams: Mapping[str, Any],
    pending_players: PendingPlayers,
    team_name: str,
    player: str,
    *,
    as_admin: bool = False,
) -> Optional[set[str]]:
    """Move a player to one team and return the names of affected teams."""
    target_team = teams.get(team_name)
    if target_team is None:
        return None

    affected_teams = set()
    for current_team in teams.values():
        removed = False
        while player in current_team.players:
            current_team.players.remove(player)
            removed = True
        while player in current_team.admins:
            current_team.admins.remove(player)
            removed = True
        if removed:
            affected_teams.add(current_team.name)

    members = target_team.admins if as_admin else target_team.players
    members.append(player)
    affected_teams.add(target_team.name)
    pending_players.discard(player)
    return affected_teams


def remove_player(teams: Mapping[str, Any], player: str) -> set[str]:
    """Remove a player from every team and return affected team names."""
    affected_teams = set()
    for team in teams.values():
        removed = False
        while player in team.players:
            team.players.remove(player)
            removed = True
        while player in team.admins:
            team.admins.remove(player)
            removed = True
        if removed:
            affected_teams.add(team.name)
    return affected_teams
