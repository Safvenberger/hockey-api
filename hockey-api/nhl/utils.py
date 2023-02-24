import requests
import re
import numpy as np
import pandas as pd
from difflib import get_close_matches
from pandera.typing import DataFrame


def get_player_data() -> DataFrame:
    """
    Download all player data from NHL.com.

    Returns
    -------
    players : DataFrame
        All information available about all players recorded NHL's database, 
        upto the date of retrieval.

    """
    # Get all players from the NHL api
    player_data = requests.get("https://records.nhl.com/site/api/player").json()

    # Covnert json file to data frame
    players = pd.json_normalize(player_data["data"])

    return players


def add_player_ids_to_html_shifts(json_shifts: DataFrame, html_shifts: DataFrame) -> DataFrame:
    """
    Add a player id column to the HTML shifts.

    Parameters
    ----------
    json_shifts : DataFrame
        All shifts from the game and its JSON representation.
    html_shifts : DataFrame
        All shifts from the game and its HTML representation.

    Returns
    -------
    html_shifts : DataFrame
        Modified HTML shifts with a new column for player id.

    """
    # Storage for player name and id mapping
    player_name_to_id_map = {}
    
    # Get all unique players from the HTML shifts
    html_players = html_shifts[["Player", "TeamName"]].drop_duplicates()
    
    # Get all unique players from the JSON shifts
    json_players = json_shifts[["Player", "PlayerId", "TeamName"]].drop_duplicates()
    
    # Loop over both teams
    for team, team_players in html_players.groupby("TeamName"):
        # Get all players from the current team
        json_team_players = json_players.loc[json_players.TeamName.eq(team)].copy()
        
        # Loop over each player in the team
        for player in team_players.Player:
            # Get the closest player from the list
            match = get_close_matches(player, json_team_players.Player.str.upper().to_list(), n=1)
        
            # If there was a match
            if len(match) > 0:
                # Find the index of the matched player name
                match_idx = json_team_players.Player.str.upper().eq(match[0])
                
                # Get the player id from the matched player
                match_player_id = json_team_players.loc[match_idx, "PlayerId"].values[0]
                
                # Remove the matched player from the possibilites
                json_team_players.drop(match_idx[match_idx].index, inplace=True)
                
            else:
                # If there is no match
                match_player_id = np.nan
                
            # Save the player id in the dictionary
            player_name_to_id_map[player] = match_player_id

    # Copy to avoid changing in-place
    html_shifts = html_shifts.copy()

    # Add player id as a column
    html_shifts.insert(1, "PlayerId", html_shifts.Player.replace(player_name_to_id_map))

    return html_shifts


def map_player_ids_to_names(json_game) -> DataFrame:
    """
    Add player names to the JSON data.

    Parameters
    ----------
    json_game : GameJSON
        Object containing the JSON representation of the game.

    Returns
    -------
    pbp : DataFrame
        Modified JSON play by play data frame with player names added.

    """
    # Get the data frame from the object
    pbp = json_game.pbp.copy()
     
    # Get all players dressed for the game
    players_in_game = json_game.get_players_dressed_for_game()
    
    # Extract the column names of home and away players
    home_players = pbp.columns.str.extract("(HomePlayer.+)").dropna().values[:, 0]
    away_players = pbp.columns.str.extract("(AwayPlayer.+)").dropna().values[:, 0]
    
    # Add a new column for player ids
    pbp[[re.sub("Player", "PlayerId", i) for i in home_players]] = pbp[home_players]
    pbp[[re.sub("Player", "PlayerId", i) for i in away_players]] = pbp[away_players]
    
    # Map player id to player name
    home_player_map = players_in_game.loc[players_in_game.Side.eq("Home")].set_index("PlayerId")["Player"].to_dict()
    away_player_map = players_in_game.loc[players_in_game.Side.eq("Away")].set_index("PlayerId")["Player"].to_dict()

    # Remap away player id columns to away player names
    pbp[away_players] = pbp[away_players].replace(
        away_player_map)
    
    # Remap home player id columns to home player names
    pbp[home_players] = pbp[home_players].replace(
        home_player_map)
    
    # Add new columns for player involvement and map to player names
    for i in range(1, 4):
        pbp[f"PlayerId{i}"] = pbp[f"Player{i}"]
        
        pbp[f"Player{i}"] = pbp[f"Player{i}"].replace(
            {**away_player_map, **home_player_map})
    
    # Reorder columns
    pbp = pbp[
        ["GameId", "AwayTeamName", "HomeTeamName", "EventNumber", "PeriodNumber",
         "EventTime", "TotalElapsedTime", "EventType", "Team", "GoalsAgainst", "GoalsFor", 
         "X", "Y", "ScoringManpower", "Type", "GameWinningGoal", "EmptyNet", "PenaltyType",
         "PenaltyMinutes", "PlayerType1",  "Player1", "PlayerId1", 
         "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3", "PlayerId3", 
         "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2", "AwayPlayerId2", 
         "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4", "AwayPlayerId4", 
         "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6", "AwayPlayerId6", 
         "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2", 
         "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4", 
         "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6"]]
    
    return pbp


def map_player_names_to_ids(json_game, html_game) -> DataFrame:
    """
    Add player ids to the HMTL data.

    Parameters
    ----------
    json_game : GameJSON
        Object containing the JSON representation of the game.
    html_game : GameHTML
        Object containing the HTML representation of the game.

    Returns
    -------
    pbp : DataFrame
        Modified HTML play by play data frame with player names added.

    """
    # Get the play by play data form the HTML report
    pbp = html_game.get_event_data().copy()
    
    # Get the players dressed for the game
    players_in_game = json_game.get_players_dressed_for_game()
    
    # Extract the column names of home and away players
    home_players = pbp.columns.str.extract("(HomePlayer.+)").dropna().values[:, 0]
    away_players = pbp.columns.str.extract("(AwayPlayer.+)").dropna().values[:, 0]
    
    # Column names for id columns
    home_player_ids = [re.sub("Player", "PlayerId", i) for i in home_players]
    away_player_ids = [re.sub("Player", "PlayerId", i) for i in away_players]
    
    # Add a new column for player ids
    pbp[[re.sub("Player", "PlayerId", i) for i in home_players]] = pbp[home_players]
    pbp[[re.sub("Player", "PlayerId", i) for i in away_players]] = pbp[away_players]
    
    # Map player id to player name
    home_player_map = players_in_game.loc[players_in_game.Side.eq("Home")].set_index("Player")["PlayerId"].to_dict()
    away_player_map = players_in_game.loc[players_in_game.Side.eq("Away")].set_index("Player")["PlayerId"].to_dict()

    # Convert dictionary keys to all caps to match HTML format
    home_player_map = {player.upper(): player_id for player, player_id in home_player_map.items()}
    away_player_map = {player.upper(): player_id for player, player_id in away_player_map.items()}

    # Remap home player id columns to home player names
    pbp[home_player_ids] = pbp[home_player_ids].replace(
        home_player_map)
    
    # Remap away player id columns to away player names
    pbp[away_player_ids] = pbp[away_player_ids].replace(
        away_player_map)
    
    # Fix any possible unmatched names
    unmatched_home = any(pbp[home_player_ids].dtypes == "object")
    unmatched_away = any(pbp[away_player_ids].dtypes == "object")
    
    if unmatched_home:
        # Find all home players
        unique_home_players = pbp[home_player_ids].melt().value.dropna().unique()
        
        # Find the unmapped home players
        unmapped_home_players = [player for player in unique_home_players if isinstance(player, str)]
        
        # Find all the player ids that have been matched successfully
        mapped_home_player_ids = set(unique_home_players).symmetric_difference(unmapped_home_players)
        
        # Find all players who were not matched
        unmapped_home_player_ids = {player: player_id for player, player_id in home_player_map.items() if
                                    player_id not in mapped_home_player_ids}
        
        # Loop through all unmapped players
        for unmapped_home_player in unmapped_home_players:
            # Get the closest match from the unmapped players
            unmapped = get_close_matches(unmapped_home_player, unmapped_home_player_ids, n=1)[0]
            
            # Save the name in the dictionary
            home_player_map[unmapped_home_player] = home_player_map[unmapped]
            
            # Delete the other name
            del home_player_map[unmapped]
    
        # Remap home player id columns to home player names
        pbp[home_player_ids] = pbp[home_player_ids].replace(
            home_player_map)
        
    if unmatched_away:
        # Find all away players
        unique_away_players = pbp[away_player_ids].melt().value.dropna().unique()
        
        # Find the unmapped away players
        unmapped_away_players = [player for player in unique_away_players if isinstance(player, str)]
        
        # Find all the player ids that have been matched successfully
        mapped_away_player_ids = set(unique_away_players).symmetric_difference(unmapped_away_players)
        
        # Find all players who were not matched
        unmapped_away_player_ids = {player: player_id for player, player_id in away_player_map.items() if
                                    player_id not in mapped_away_player_ids}
        
        # Loop through all unmapped players
        for unmapped_away_player in unmapped_away_players:
            # Get the closest match from the unmapped players
            unmapped = get_close_matches(unmapped_away_player, unmapped_away_player_ids, n=1)[0]
            
            # Save the name in the dictionary
            away_player_map[unmapped_away_player] = away_player_map[unmapped]
            
            # Delete the other name
            del away_player_map[unmapped]
    
        # Remap away player id columns to away player names
        pbp[away_player_ids] = pbp[away_player_ids].replace(
            away_player_map)
    
    # Add new columns for player involvement and map to player names
    for i in range(1, 4):
        pbp[f"PlayerId{i}"] = pbp[f"Player{i}"]
        
        pbp[f"PlayerId{i}"] = pbp[f"PlayerId{i}"].replace(
            {**away_player_map, **home_player_map})    
        
    # Map goalie names to ids
    pbp["HomeGoalieId"] = pbp["HomeGoalieName"].replace(home_player_map)
    pbp["AwayGoalieId"] = pbp["AwayGoalieName"].replace(away_player_map)
        
    # Reorder columns
    pbp = pbp[
        ["GameId", "Date", "AwayTeamName", "HomeTeamName", "EventNumber", 
         "PeriodNumber", "Manpower", "EventTime", "TotalElapsedTime",
         "EventType", "Description", "Team", "Zone", "ShotType", "PenaltyShot", 
         "PenaltyType", "PenaltyMinutes", "PlayerType1", "Player1", "PlayerId1", 
         "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3", "PlayerId3", 
         "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2", "AwayPlayerId2", 
         "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4", "AwayPlayerId4", 
         "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6", "AwayPlayerId6",
         "AwayGoalieOnIce", "AwayGoalieName", "AwayGoalieId",
         "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2", 
         "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4", 
         "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6",
         "HomeGoalieOnIce", "HomeGoalieName", "HomeGoalieId"]]
    
    return pbp


def standardize_coordinates(pbp: DataFrame) -> DataFrame:
    """
    Synchronize the attacking direction within games such that both teams have
    their own net located at x=-89 and opposition's net at x=89.

    Parameters
    ----------
    pbp : DataFrame
        Data frame of play by play data.

    Returns
    -------
    pbp : DataFrame
        Adjusted data frame with new X and Y coordinates.

    """
    
    # Copy to avoid changing in-place
    pbp = pbp.copy()
    
    # Check if the team was the home team
    pbp["IsHome"] = pbp.Team.eq(pbp.HomeTeamName)
        
    # Check if the game was in overtime 
    pbp["Overtime"] = pbp.PeriodNumber.eq(4)
    
    # Get all shot events in regulation where the goalie is on the ice
    shot_events = pbp.loc[pbp.EventType.isin(["GOAL", "MISSED SHOT", "SHOT"]) &
                          ((pbp.IsHome & pbp.AwayGoalieOnIce) | 
                           (~pbp.IsHome & pbp.HomeGoalieOnIce)) &
                          pbp.PeriodNumber.lt(5)]
                                  
    # Compute the game median x-coordinate and number of shots by group
    game_median_x = shot_events.groupby(["GameId", "IsHome", "PeriodNumber", "Overtime"], 
                                        as_index=False).agg({"X": ["median", "size"]}
                                                            ).reset_index(drop=True)
    # Rename columns
    game_median_x.columns = ["GameId", "IsHome", "PeriodNumber", "Overtime", "Xmedian", "Size"]
    
    # Check if the median x coordinate was positive or negative
    game_median_x["Sign"] = np.sign(game_median_x["Xmedian"])
        
    # Add sign, indicating if the attack was toward 100 or -100
    pbp = pbp.merge(game_median_x[["GameId", "IsHome", "PeriodNumber", "Overtime", "Sign"]], 
                    how="left")
    
    # Adjust the X and Y coordinates by considering the sign
    pbp.insert(int(np.where(pbp.columns.str.contains("^X$"))[0][0]), 
               "X_adj", pbp["X"] * pbp["Sign"])
    pbp.insert(int(np.where(pbp.columns.str.contains("^Y$"))[0][0]), 
               "Y_adj", pbp["Y"] * pbp["Sign"])

    # Remove the unwanted columns
    pbp.drop(["IsHome", "Overtime", "Sign"], axis=1, inplace=True)    

    return pbp
