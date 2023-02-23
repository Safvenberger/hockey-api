import requests
import pandas as pd
import numpy as np
from pandera.typing import DataFrame


class GameJSON:
    """
    Extract information from the JSON report of an NHL game.
    
    Arguments:
        game_id: int, the id of the game, given as e.g. 2021020001.
        pbp: bool, if play by play data should be downloaded.
        shifts: bool, if shift data should be downloaded. 
        requests_session: optional, the session to use for scraping.
    
    Attributes:
        game_id: int, the id of the game.
        url: str, the url of the JSON report. One for play-by-play, and one for shifts.
        pbp: the play by play data.
        dressed_for_game: all players listed in the play by play data.
        shifts: all shifts reported for the game.
    
    Methods:
        get_event_data: retrieves the event data from the game.
        get_players_dressed_for_game: retrieves all players dressed for the game.
        get_shifts: retrieves all shifts from the home and away team.
    
    """
    def __init__(self, game_id: int, pbp: bool=True, shifts: bool=True,
                 requests_session: requests.sessions.Session=None):
        """ Initialize a new game object. """
        
        # Create a new session if none is provided
        if requests_session is None:
            requests_session = requests.Session()
        
        # Save the game id as attribute
        self.game_id = game_id

        # Save the urls
        if pbp:
            self.pbp_url = self.__get_url(game_id, report_type="PL")
        if shifts:
            self.shifts_url = self.__get_url(game_id, report_type="SH")

        # Run the methods to save the results
        if pbp:
            self.pbp = self.__get_event_data(requests_session)
            self.dressed_for_game = self.__get_players_dressed_for_game(requests_session)
        if shifts:
            self.shifts = self.__get_game_shifts(requests_session)
        
    def __get_url(self, game_id: int, report_type: str="PL") -> str:
        """ Get the url used for retrieving data. """
        
        if report_type not in ["PL", "SH"]:
            raise ValueError("The report type is not supported.")
        
        # Specify the url
        if report_type == "PL":
            url = f"https://statsapi.web.nhl.com/api/v1/game/{game_id}/feed/live"
        elif report_type == "SH":
            url = f"https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
            
        return url
    
            
    def __get_event_data(self, requests_session) -> DataFrame:
        """ Get play by play data from the NHL API for a given game. """
    
        # Get the json data from the game
        json_data = requests_session.get(self.pbp_url).json()
            
        # Get both team names
        team_name = [json_data["gameData"]["teams"]["away"]["name"],
                     json_data["gameData"]["teams"]["home"]["name"]]
        
        # Extract the play by play data
        pbp_data = pd.json_normalize(json_data["liveData"]["plays"]["allPlays"])
        
        # Add Game id
        pbp_data["GameId"] = self.game_id
        
        # Add team names
        pbp_data["AwayTeamName"] = team_name[0]
        pbp_data["HomeTeamName"] = team_name[1]
        
        # Specify columns to keep
        cols = ["GameId", "AwayTeamName", "HomeTeamName", "about.eventIdx",
                "about.period", "about.periodTime", "result.eventTypeId", "team.name",
                "about.goals.away", "about.goals.home", "coordinates.x", "coordinates.y",
                "players", "result.strength.name", "result.secondaryType",
                "result.gameWinningGoal", "result.emptyNet", "result.penaltySeverity",
                "result.penaltyMinutes"]
        
        # In case of missing columns
        if "result.emptyNet" not in pbp_data.columns:
            pbp_data["result.emptyNet"] = np.nan
        if "result.gameWinningGoal" not in pbp_data.columns:
            pbp_data["result.gameWinningGoal"] = np.nan
        if "result.penaltySeverity" not in pbp_data.columns:
            pbp_data["result.penaltySeverity"] = np.nan
        if "result.penaltyMinutes" not in pbp_data.columns:
            pbp_data["result.penaltyMinutes"] = np.nan
        
        # Specify renaming of columns
        column_renaming = {"about.eventIdx": "EventNumber", 
                           "about.period": "PeriodNumber",
                           "about.periodTime": "EventTime",
                           "result.eventTypeId": "EventType",
                           "team.name": "Team",
                           "about.goals.away": "GoalsAgainst",
                           "about.goals.home": "GoalsFor",
                           "coordinates.x": "X",
                           "coordinates.y": "Y",
                           "result.strength.name": "ScoringManpower",
                           "result.secondaryType": "Type",
                           "result.gameWinningGoal": "GameWinningGoal", 
                           "result.emptyNet": "EmptyNet", 
                           "result.penaltySeverity": "PenaltyType",
                           "result.penaltyMinutes": "PenaltyMinutes"}
        
        # If there is no data
        if len(pbp_data) == 0:
            return pd.DataFrame(columns=[
                "GameId", "AwayTeamName", "HomeTeamName", "EventNumber", "PeriodNumber",
                "EventTime", "TotalElapsedTime", "EventType", "Team", "GoalsAgainst", "GoalsFor", 
                "X", "Y", "ScoringManpower", "Type", "GameWinningGoal", "EmptyNet", "PenaltyType",
                "PenaltyMinutes", "PlayerType1",  "Player1", "PlayerId1", 
                "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3", "PlayerId3", 
                "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2", "AwayPlayerId2", 
                "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4", "AwayPlayerId4", 
                "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6", "AwayPlayerId6", 
                "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2", 
                "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4", 
                "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6"])
        
        # Select columns
        pbp_data = pbp_data[cols]
        
        # Extract the players involved in the actions
        pbp_data["Player1"] = pbp_data["players"].apply(
            lambda x: x[0]["player"]["id"] if type(x) != float else x)
        
        pbp_data["Player2"] = pbp_data["players"].apply(
            lambda x: x[1]["player"]["id"] if type(x) != float and len(x) > 1 else np.nan)
        
        pbp_data["Player3"] = pbp_data["players"].apply(
            lambda x: x[2]["player"]["id"] if type(x) != float and len(x) > 2 else np.nan)

        # Extract player roles
        pbp_data["PlayerType1"] = pbp_data["players"].apply(
            lambda x: x[0]["playerType"] if type(x) != float else x)
        
        pbp_data["PlayerType2"] = pbp_data["players"].apply(
            lambda x: x[1]["playerType"] if type(x) != float and len(x) > 1 else np.nan)
        
        pbp_data["PlayerType3"] = pbp_data["players"].apply(
            lambda x: x[2]["playerType"] if type(x) != float and len(x) > 2 else np.nan)
        
        # Remove player column
        pbp_data.drop("players", axis=1, inplace=True)
        
        # Remove "goalie" role
        pbp_data.loc[pbp_data.PlayerType1.eq("Goalie"), "Player1"] = np.nan
        pbp_data.loc[pbp_data.PlayerType1.eq("Goalie"), "PlayerType1"] = np.nan
        pbp_data.loc[pbp_data.PlayerType2.eq("Goalie"), "Player2"] = np.nan
        pbp_data.loc[pbp_data.PlayerType2.eq("Goalie"), "PlayerType2"] = np.nan
        pbp_data.loc[pbp_data.PlayerType3.eq("Goalie"), "Player3"] = np.nan
        pbp_data.loc[pbp_data.PlayerType3.eq("Goalie"), "PlayerType3"] = np.nan
        
        # Rename columns
        pbp_data.rename(columns=column_renaming, inplace=True)
        
        # Add total elapsed time
        pbp_data["TotalElapsedTime"] = 1200 * (pbp_data["PeriodNumber"] - 1) + [
            60 * int(x[0]) + int(x[1])  for x in pbp_data["EventTime"].str.split(":")
            ]
        
        # Remove events not needed
        pbp_data = pbp_data.loc[~pbp_data.EventType.isin(["GAME_SCHEDULED", "PERIOD_OFFICIAL",
                                                          "PERIOD_READY"])]
        
        # Replace to match existing codebase
        pbp_data["EventType"] = pbp_data["EventType"].str.replace("_", " ")
        pbp_data["EventType"] = pbp_data["EventType"].str.replace("STOP", "STOPPAGE")
        
        return pbp_data
    
    
    def __get_players_dressed_for_game(self, requests_session) -> DataFrame:
        """ Get the players dressed for a given game. """

        # Get the json data from the game
        json_data = requests_session.get(self.pbp_url).json()
        
        # Get all players
        away_players = json_data["liveData"]["boxscore"]["teams"]["away"]["players"]
        home_players = json_data["liveData"]["boxscore"]["teams"]["home"]["players"]
        
        # Get the team names
        teams = [json_data["gameData"]["teams"]["away"]["name"],
                 json_data["gameData"]["teams"]["home"]["name"]]
        
        # Create a player id -> player position mapping for each team
        away_positions = {player["person"]["id"]: player["position"]["code"] for 
                          idx_str, player in away_players.items()}
        
        home_positions = {player["person"]["id"]: player["position"]["code"] for 
                          idx_str, player in home_players.items()}
        
        # Create a player id -> player name mapping for each team
        away_players = {player["person"]["id"]: player["person"]["fullName"] for 
                        idx_str, player in away_players.items()}
        
        home_players = {player["person"]["id"]: player["person"]["fullName"] for 
                        idx_str, player in home_players.items()}
        
        # Add team name
        away_players_with_team = {teams[0]: away_players}
        home_players_with_team = {teams[1]: home_players}
    
        # Combine players from both team into one dictionary
        players_with_team = {**away_players_with_team, **home_players_with_team}
        
        # Create a wide representation of the player and id mapping
        players_with_team_wide = pd.json_normalize(players_with_team.values())
        
        # Set a new column for team names
        players_with_team_wide["Team"] = teams
        players_with_team_wide["Side"] = ["Away", "Home"]
        
        # Create a data frame representation of the id name mapping
        game_players = players_with_team_wide.melt(id_vars=["Team", "Side"], 
                                                   var_name="PlayerId", 
                                                   value_name="Player").dropna(
                                                       ).reset_index(drop=True)
            
        # Add playing position
        game_players["Position"] = game_players["PlayerId"].replace({**away_positions, **home_positions})
        
        # Add a column for game id
        game_players.insert(0, column="GameId", value=self.game_id) 
        
        return game_players
    
    
    def __get_game_shifts(self, requests_session) -> DataFrame:
        """ Extract shift information from NHL's API for a given game. """
        
        # Extract shift information from NHL api
        game_shifts = requests_session.get(self.shifts_url).json()["data"]
        
        # Convert json to pandas data frame
        game_shifts_df = pd.json_normalize(game_shifts)
        
        # Add player name
        game_shifts_df["playerName"] = game_shifts_df[["firstName", "lastName"]].apply(
            lambda x: f"{x.firstName} {x.lastName}", axis=1)
        
        # If there is no data for a given game
        if len(game_shifts_df) == 0:
            return pd.DataFrame(columns=["gameId", "playerId", "playerName", "startTime", "period",
                                         "endTime", "duration", "teamId", "teamName"])
        
        # Select the desired columns
        game_shifts_df = game_shifts_df[["gameId", "playerId", "playerName", "startTime", "period", 
                                         "endTime", "duration", "teamId", "teamName"]]
        
        # Remove goals from the data
        game_shifts_df.dropna(inplace=True)
        
        # If there is no data (besides goals) for a given game
        if len(game_shifts_df) == 0:
            return pd.DataFrame(columns=["gameId", "playerId", "playerName", "startTime", "period",
                                         "endTime", "duration", "teamId", "teamName"])
        
        # In case of empty values
        missing_start_time = game_shifts_df["startTime"].eq("")
        missing_end_time = game_shifts_df["endTime"].eq("")
        
        # Final period in regulation
        final_period = game_shifts_df["period"].eq(3)
        
        # Final two minutes of the period
        final_two_minutes = game_shifts_df["startTime"].apply(lambda x: int(x[0:2]) >= 18)
        
        # Update end time for final shifts in regulation
        game_shifts_df.loc[missing_end_time & final_period &
                           final_two_minutes, "endTime"] = "20:00"
        
        # Update in case of new end times
        missing_end_time = game_shifts_df["endTime"].eq("")
        
        # Compute start time for missing values
        game_shifts_df.loc[missing_start_time, "startTime"] = game_shifts_df.loc[missing_start_time, ["endTime", "duration"]].apply(
            lambda x: f"{int(x.endTime[:2]) - int(x.duration[:2])}:{int(x.endTime[3:]) - int(x.duration[3:])}",
            axis=1)  
        
        # Compute end time for missing values
        game_shifts_df.loc[missing_end_time, "endTime"] = game_shifts_df.loc[missing_end_time, ["startTime", "duration"]].apply(
            lambda x: f"{int(x.startTime[:2]) + int(x.duration[:2])}:{int(x.startTime[3:]) + int(x.duration[3:])}",
            axis=1)  
        
        # Convert time columns to seconds
        game_shifts_df["startTime"] = [int(minute) * 60 + int(second) for minute, second in 
                                       game_shifts_df["startTime"].str.split(':')]
        game_shifts_df["endTime"]   = [int(minute) * 60 + int(second) for minute, second in 
                                       game_shifts_df["endTime"].str.split(':')]
        game_shifts_df["duration"]  = [int(minute) * 60 + int(second) for minute, second in 
                                       game_shifts_df["duration"].str.split(':')]
        
        # Combine time with period number to get TotalElapsedTime
        game_shifts_df["startTime"] = 1200 * (game_shifts_df["period"] - 1) + game_shifts_df["startTime"]
        game_shifts_df["endTime"]   = 1200 * (game_shifts_df["period"] - 1) + game_shifts_df["endTime"]

        # For end times in separate periods
        period_shift = game_shifts_df.apply(lambda row: row["endTime"] < row["startTime"], 
                                            axis=1)
        
        # Add one period worth of seconds
        game_shifts_df.loc[period_shift, "endTime"] += 1200

        # Compute duration to ensure correctness to the highest level
        game_shifts_df["duration"] = game_shifts_df["endTime"] - game_shifts_df["startTime"]

        # Rename columns
        game_shifts_df.columns = (game_shifts_df.columns.str.get(0).str.capitalize() + 
                                  game_shifts_df.columns.str.replace("^.{1}", "", regex=True))

        return game_shifts_df
        
        
    def get_event_data(self):
        """ Return the play-by-play data. """
        return self.pbp
    
    def get_players_dressed_for_game(self):
        """ Return the players dressed for the game. """
        return self.dressed_for_game
    
    def get_shifts(self):
        """ Return the shifts in the game. """
        return self.shifts