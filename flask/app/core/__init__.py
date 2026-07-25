import logging
import random
import requests
from datetime import datetime, timedelta

import pygeohash as pgh
from apscheduler.schedulers.background import BackgroundScheduler
from flask_socketio import SocketIO

from ..game_config import ADMINS, CARD_COUNT, COLLAPSE, COLLAPSE_DAMAGE_INTERVAL, COLLAPSE_DAMAGE, COLLAPSE_LIST, END_STATION, DISTANCE, IMPRISONED_TIME, BACKUP_INTERVAL
from ..config import UNKNOWN_PLAYER_LIMIT, UNKNOWN_PLAYER_TTL_SECONDS
from ..data import load_data
from ..models import db
from ..models.teams import Teams
from ..modules.pending_players import PendingPlayers
from ..modules.team_membership import (
    assign_player as assign_team_member,
    remove_player as remove_team_member,
)
from .metro import MetroSystem
from .team import Team
from .collapse import Collapse


log = logging.getLogger(__name__)


class Core:
    def __init__(self) -> None:
        self.is_running = False
        # self.metro = MetroSystem() 改到start_game，讓隱藏站和占領狀態可被重置
        self.socketio = None
        self.teams: dict[str, Team] = {}
        self.visited = []
        self.choice: dict[int, list[str]] = {i: [] for i in range(1, 7)}
        self.collapse = Collapse()
        self.collapse_list = COLLAPSE_LIST.copy()
        self.collapse_scheduler = BackgroundScheduler()
        self.prison_scheduler = BackgroundScheduler()

        self.backup_scheduler = BackgroundScheduler()
        self.auto_backup_secret = str(random.random())

        self.unknown_players = PendingPlayers(
            ttl_seconds=UNKNOWN_PLAYER_TTL_SECONDS,
            max_size=UNKNOWN_PLAYER_LIMIT,
        )
        
        # 預先建立管理員隊伍
        # self.create_team("admins", admins=ADMINS.copy())

        # 建立預設隊伍
        teams_presets = load_data("team_presets")
        for team in teams_presets["teams"]:
            self.create_team(**team)
        
        self.start_game()
        
        
    def init_socketio(self, socketio: SocketIO) -> None:
        self.socketio = socketio
        
        log.info("SocketIO initialized.")
        
        self.init_collapse()
        self.init_prison()
        
        
    def init_collapse(self) -> None:
        
        if self.socketio is None:
            log.error("SocketIO is not initialized.")
            return None
        
        if self.collapse_scheduler.running:
            self.collapse_scheduler.shutdown()
        
        for collapse in COLLAPSE:
            hour, minute = map(int, collapse["time"].split(":"))
            collapse_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if collapse_time < datetime.now():
                self._collapse()
                
            elif collapse_time - datetime.now() < timedelta(minutes=5):
                self._collapse_warning()
                
                self.collapse_scheduler.add_job(self._collapse, "date", run_date=collapse_time)
                log.info(f"Add collapse job at {collapse_time}.")
            
            else:
                self.collapse_scheduler.add_job(self._collapse_warning, "date", run_date=collapse_time - timedelta(minutes=5))
                log.info(f"Add collapse warning job at {collapse_time - timedelta(minutes=5)}.")
                
                self.collapse_scheduler.add_job(self._collapse, "date", run_date=collapse_time)
                log.info(f"Add collapse job at {collapse_time}.")
            
        self.collapse_scheduler.add_job(self._collapse_damage, "interval", minutes=COLLAPSE_DAMAGE_INTERVAL)
        self.collapse_scheduler.start()
        
        log.info("Collapse scheduler started.")
        
        
    def init_prison(self) -> None:
        
        if self.prison_scheduler.running:
            return None
            
        self.prison_scheduler.add_job(self._release, "interval", minutes=1)
        self.prison_scheduler.start()
        
        log.info("Prison scheduler started.")
    
    
    def _collapse(self) -> None:
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        self.collapse.warning = False
        
        collapse = COLLAPSE[self.collapse.status]
                
        if collapse["final"]:
            for station in self.metro.graph.keys():
                if station == END_STATION: continue
                self.collapse_list.append(station)
                
            self.collapse.status += 1
                
            log.debug("All stations collapsed.")
            
            return None
        
        for station in collapse["stations"]:
            self.collapse_list.append(station)
            
        if self.collapse.status + 1 < len(COLLAPSE):
            self.collapse.next_time = COLLAPSE[self.collapse.status + 1]["time"]
        else:
            self.collapse.next_time = None
        
        self.collapse.status += 1
        self.socketio.emit("collapse", collapse["stations"])
        
        log.info(f"Station collapsed. Current status: {self.collapse.status}.")
                
                
    def _collapse_damage(self) -> None:
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        for team in self.teams.values():
            if team.location in self.collapse_list:
                log.debug(f"Team {team.name} is in collapsed station {team.location}.")
                team.point -= COLLAPSE_DAMAGE
                team.add_point_log(-COLLAPSE_DAMAGE, "Station collapsed")
                self.socketio.emit("collapse_damage", team.name)
                log.debug(f"Team {team.name} took collapse damage -{COLLAPSE_DAMAGE}. Current point: {team.point}.")
                
                
    def _collapse_warning(self) -> None:
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        self.collapse.warning = True
        
        self.socketio.emit("collapse_warning")
        log.info(f"Station will collapse in 5 minutes.")
        
        
    def _release(self) -> None:
        for team in self.teams.values():
            
            if not team.is_imprisoned:
                continue
            
            team.imprisoned_time -= 1
            if team.imprisoned_time <= 0:
                
                team.is_imprisoned = False
                team.imprisoned_time = 0
                
                log.debug(f"Team {team.name} released.")
                core.teams[team.name].add_event_log(f"Released from prison")
                self.socketio.emit("release", team.name)
                
    def init_backup(self) -> None:
        """Initialize the backup scheduler."""
        
        if self.backup_scheduler.running:
            return None
        
        self.backup_scheduler.add_job(lambda: requests.get(f"http://localhost:8080/api/admin/save_game_auto?secret={self.auto_backup_secret}"), "interval", minutes=BACKUP_INTERVAL)
        self.backup_scheduler.start()
        
        log.info("Backup scheduler started.")

                
    def start_game(self) -> None:
        """Start the game."""
        
        if self.is_running:
            log.warning("Game already started.")
            return None
        
        self.metro = MetroSystem()
        
        self.init_collapse()
        self.init_prison()
        self.init_backup()
        
        self.collapse = Collapse()
        self.collapse_list = COLLAPSE_LIST.copy()
        
        for team in self.teams.values():
            self.reset_team(team.name)
            
        # if "admins" not in self.teams.keys():
        #     self.create_team("admins", admins=ADMINS.copy())
            
        self.is_running = True
        
        log.info("Game started.")
                
            
    def end_game(self) -> None:
        """End the game."""
        
        if not self.is_running:
            log.warning("Game already ended.")
            return None
        
        self.is_running = False
        
        log.info("Game ended.")
        
    
    def load_team(self) -> None:
        """Load the data from the database."""
        
        for team in Teams.query.all():

            team: Teams

            if team.name in self.teams:
                self.teams[team.name].replace_data(team)
                log.info(f"Loaded team {team.name} from database.")
            else:
                self.create_team(team.name, team.players, team.admins, team.location)
                self.teams[team.name].replace_data(team)

                log.info(f"Created team {team.name} from database.")

            
        log.debug("Load data from the database.")
            
        
    def save_team(self, names: set[str] | None=None) -> None:
        """Save the data to the database."""

        teams = self.teams.values() if names is None else (
            self.teams[name] for name in names if name in self.teams
        )
        for team in teams:
            if team.name == "admins":
                continue
            if Teams.query.filter_by(name=team.name).first() is None:
                db.session.add(Teams(team))
            else:
                Teams.query.filter_by(name=team.name).update({**team.__dict__})
                
        db.session.commit()
        
        log.debug("Save data to the database.")

    
    def create_team(self, name: str, players: list[str]=None, admins: list[str]=None, station: str=None) -> None:
        """
        Create a new team.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
            
        station: :type:`str`
            The name of the station.
            
        players: :type:`list[str]`
            The list of player discord usernames.
            
        Returns
        -------
        team: :class:`Team`
            The team object.
        """
        
        if name in self.teams.keys():
            log.warning(f"Team {name} already exists.")
            return None
        
        if station == "":
            station = None

        self.teams[name] = Team(name, players if players is not None else [], admins if admins is not None else [], station)
        
        log.debug(f"Team {name} created.")
        
        
    def check_player(self, player: str, remember_unknown: bool=True) -> tuple[Team | None, bool]:
        """
        Check if the player is in the team.
        
        Parameters
        ----------
        player: :type:`str`
            The discord username of the player.
            
        Returns
        -------
        team: :class:`Team`
            The team object.
            
        is_admin: :type:`bool`
            If the player is an admin.
        """
        
        for team in self.teams:
            
            if player in self.teams[team].admins:
                self.unknown_players.discard(player)
                return self.teams[team], True
            
            if player in self.teams[team].players:
                self.unknown_players.discard(player)
                return self.teams[team], player in ADMINS

        if remember_unknown and player not in ADMINS:
            self.unknown_players.add(player)
            
        return None, player in ADMINS


    def assign_player(self, team_name: str, player: str, as_admin: bool=False) -> bool:
        """Assign a Discord user to one team and persist affected teams."""
        affected_teams = assign_team_member(
            self.teams,
            self.unknown_players,
            team_name,
            player,
            as_admin=as_admin,
        )
        if affected_teams is None:
            return False
        self.save_team(affected_teams)
        return True


    def remove_player(self, player: str) -> bool:
        """Remove a Discord user from all teams and persist affected teams."""
        affected_teams = remove_team_member(self.teams, player)
        if not affected_teams:
            return False

        self.save_team(affected_teams)
        return True
    
    
    def check_combo(self, name: str) -> None:
        """
        Check if the team achieved the combo and add the point.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
        """
        
        for combo in load_data("combo"):
            if combo["name"] in self.teams[name].combos:
                continue
            
            if set(combo["stations"]) == set(combo["stations"]).intersection(set(self.teams[name].stations)):
                self.teams[name].point += combo["point"]
                self.teams[name].combos.append(combo["name"])
                self.teams[name].add_point_log(combo["point"], f"Achieved combo {combo['name']}")
                core.teams[name].add_event_log(f"Achieved combo {combo['name']}")
                
                self.socketio.emit("combo", combo["name"])
                
                log.debug(f"Team {name} achieved combo {combo['name']}.")
    
    
    # DFS🔥🔥🔥
    def _move(self, current_station: str, target_deep: int, deep: int=1) -> list[str]:
        choice = []
        
        if deep > target_deep or current_station in self.visited:
            return choice
        
        self.visited.append(current_station)
        
        for station in self.metro.move(current_station):
            if station not in self.visited: choice.append(station)
            choice.extend(self._move(station, target_deep, deep + 1))
            
        log.debug(f"Deep: {deep}, Station: {current_station}, Choice: {choice}")
        
        for s in choice:
            if s not in self.choice[deep]:
                self.choice[deep].append(s)
                
        return choice
    
    
    def move(self, name: str, step: int) -> list[str] | None:
        """
        Calculate the possible stations to move.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
            
        step: :type:`int`
            The number of steps to move.
            
        Returns
        -------
        choice: :type:`list[str]`
            The list of possible station ids to move.
        """
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None

        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        self.choice = {i: [] for i in range(1, 7)}
        self.visited = []
        current_station = self.teams[name].location
        self._move(current_station, step)
                    
        self.teams[name].choice = self.choice[step]
        
        log.debug(f"Team {name} can move to {self.choice[step]}.")
        
        return self.choice[step]
    
    
    def move_to_location(self, name: str, location: str) -> None:
        """
        Set the target location of the team to move.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.

        location: :type:`str`
            The name of the station to move to.
        """
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        station = self.metro.find_station(location)
        self.teams[name].target_location = station.name

        # self.teams[name].current_mission_finished = 2 # Another secret status for frontend # No no no Don't do this
        
        ############
        # # 達成組合
        # self.check_combo(name)
        
        # # 過路費
        # if station.team is not None and station.team != name:
        #     self.teams[name].point -= station.point
        #     self.teams[name].add_point_log(-station.point, f"To team {station.team}")
            
        #     self.teams[station.team].point += station.point
        #     self.teams[station.team].add_point_log(station.point, f"From team {name}")
            
        # # 監獄
        # if station.is_prison:
        #     self.teams[name].is_imprisoned = True
        #     self.teams[name].imprisoned_time = random.randint(IMPRISONED_TIME["min"], IMPRISONED_TIME["max"])
        #     self.teams[name].current_mission_finished = True
        #     self.teams[name].stations.append(station.name)
            
        #     log.debug(f"Team {name} is imprisoned.")
            
        # else:
        #     self.teams[name].current_mission_finished = False
        ############
            
        self.teams[name].current_card = None
        self.metro.find_station(location).hidden = False

        
        log.debug(f"The target location of team {name} is {location}.")
        self.teams[name].add_event_log(f"Going to {self.teams[name].target_location}")
        
        return None

    def arrive_target(self, name: str) -> None:
        """
        Confirm if the team arrive.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
        """
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        if self.teams[name].location == self.teams[name].target_location:
            log.warning(f"Team {name} hasn't moved.")
            return None
        
        
        self.teams[name].location = self.teams[name].target_location
        station = self.metro.find_station(self.teams[name].location)
        

        # 達成組合
        self.check_combo(name)
        
        # 過路費
        if station.team is not None and station.team != name:
            self.teams[name].point -= station.point
            self.teams[name].add_point_log(-station.point, f"To team {station.team}")
            
            self.teams[station.team].point += station.point
            self.teams[station.team].add_point_log(station.point, f"From team {name}")
            
        # 監獄
        if station.is_prison:
            self.teams[name].is_imprisoned = True
            self.teams[name].imprisoned_time = random.randint(IMPRISONED_TIME["min"], IMPRISONED_TIME["max"])
            self.teams[name].current_mission_finished = True
            self.teams[name].stations.append(station.name)

            core.teams[name].add_event_log(f"Imprisoned at {station.name}")
            log.debug(f"Team {name} is imprisoned.") 

        elif station.name in self.teams[name].owned_stations:
            self.teams[name].current_mission_finished = True
            log.debug(f"team {name} arrived at {self.teams[name].location} again.")
            self.teams[name].add_event_log(f"Arrived at {self.teams[name].location} again")
            return None

        else:
            self.teams[name].current_mission_finished = False
            
        # self.teams[name].current_card = None
        # self.metro.find_station(location).hidden = False
        
        log.debug(f"team {name} arrived at {self.teams[name].location}.")
        self.teams[name].add_event_log(f"Arrived at {self.teams[name].location}")
        
        return None 
        
    def finish_mission(self, name: str) -> str | None:
        """
        Finish the mission.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
                        
        Returns
        -------
        card: :type:`str`
            The card to draw.
        """
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        if self.teams[name].current_mission_finished:
            log.warning(f"Team {name} has finished the mission.")
            return None
        
        # if self.teams[name].target_location != self.teams[name].location:
        #     log.warning(f"Team {name} hasn't arrived.")
        #     return None

        # 廢案 由於GPS在捷運站精確度不達預期標準 因此取消此功能
        # if self.teams[name].location != self.teams[name].target_location:
        #     log.warning(f"Team {name} is not in the target location.")
        #     return None
        
        station = self.metro.find_station(self.teams[name].target_location)
        
        if station is None:
            log.warning(f"Station {self.teams[name].target_location} does not exist.")
            return None
        
        # 完成任務加分
        self.teams[name].point += station.point
        self.teams[name].add_point_log(station.point, f"Finish mission at {station.name}")
        core.teams[name].add_event_log(f"Finished the mission")
        
        # 佔領
        if station.team is None:
            self.metro.find_station(station.name).team = name
            if station.name not in self.teams[name].owned_stations:
                self.teams[name].owned_stations.append(station.name)
                self.teams[name].add_event_log(f"Owned station {station.name}")
            
        # 紀錄經過站點
        if station.name not in self.teams[name].stations:
            self.teams[name].stations.append(station.name)

        # 達成組合
        self.check_combo(name)

        # 初始化
        self.teams[name].current_mission_finished = True
        self.teams[name].location = self.teams[name].target_location
        
        log.debug(f"Team {name} finished the mission.")
        
        # 抽卡
        if station.is_special:
            if self.teams[name].current_card is None:
                card = f"card{self.dice(CARD_COUNT)}"
                self.teams[name].current_card = card
            
            core.teams[name].add_event_log(f"Drew card \'{self.teams[name].current_card}\'")
            log.debug(f"Team {name} draw card {self.teams[name].current_card}.")    
            
            return self.teams[name].current_card
        
        
    def skip_mission(self, name: str) -> None:
        """
        Skip the mission.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
        """
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        if self.teams[name].current_mission_finished:
            log.warning(f"Team {name} has finished the mission.")
            return None
        
        # 需先按下抵達才可跳過
        if self.teams[name].target_location != self.teams[name].location:
            log.warning(f"Team {name} hasn't arrived.")
            return None
        
        # 廢案 由於GPS在捷運站精確度不達預期標準 因此取消此功能
        # if self.teams[name].location != self.teams[name].target_location:
        #     log.warning(f"Team {name} is not in the target location.")
        #     return None
        
        # 初始化
        self.teams[name].current_mission_finished = True
        self.teams[name].location = self.teams[name].target_location
        
        log.debug(f"Team {name} skipped the mission.")
        core.teams[name].add_event_log(f"Skipped the mission")
            
        
    def dice(self, faces: int=6) -> int:
        """
        Just a dice.
        
        Parameters
        ----------
        faces: :type:`int`
            The number of faces of the dice.
            
        Returns
        -------
        result: :type:`int`
            The result of the dice.
        """
        
        return random.randint(1, faces)
    
    
    def check_pos(self, name: str, geohash: str) -> dict | None:
        """
        Check the position of the team.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
            
        geohash: :type:`str`
            The geohash of the position.
            
        Returns
        -------
        data: :type:`dict[str, str]`
            The data of the position.
            
            - location: :type:`str`
                The current station of the team.
                
            - distance: :type:`str`
                The distance between the station and the position.
        """
        
        if self.is_running is False:
            log.warning("Game ended.")
            return None
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        if self.teams[name].is_imprisoned:
            return None
        
        data = {
            "location": None,
            "distance": None,
        }
        
        for station_name, station_geohash in self.metro.station_location.items():
            dis = pgh.geohash_approximate_distance(geohash, station_geohash)
            if dis <= DISTANCE:
                
                if data["location"] is None or dis < data["distance"]:
                    data["location"] = station_name
                    self.teams[name].location = station_name
                    
                    log.info(f"Team {name} moved to {station_name}.")
                    
            if station_name == self.teams[name].target_location:
                data["distance"] = dis
                
        log.debug(data)
        
        return data
    
    
    def reset_team(self, name: str) -> None:
        """
        Reset the team.
        
        Parameters
        ----------
        name: :type:`str`
            The name of the team.
        """
        
        if name not in self.teams.keys():
            log.warning(f"Team {name} does not exist.")
            return None
        
        self.teams[name].point = 10
        self.teams[name].step = 0
        self.teams[name].target_location = self.teams[name].location
        self.teams[name].current_mission_finished = True
        self.teams[name].current_card = None
        self.teams[name].imprisoned_time = 0
        self.teams[name].is_imprisoned = False
        self.teams[name].stations = []
        self.teams[name].combos = []
        self.teams[name].choice = []
        self.teams[name].point_log = []
        
        log.info(f"Team {name} reset.")


    def backup(self) -> None:
        """Backup the data to the database."""
        
        self.save_team()
        self.metro.save_stations()        
        
        log.info("Backup data to the database.")

    def restore(self) -> None:
        """Restore the data from the database."""
        
        self.load_team()
        self.metro.load_stations()
        
        log.info("Restore data from the database.")

    
core = Core()
