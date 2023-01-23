import requests
import pandas as pd
from tqdm import tqdm
import time


def get_game_shifts(gameId: int) -> pd.DataFrame:
    """
    Extract shift information from NHL's API for a given game.

    Parameters
    ----------
    gameId : int
        Integer of the type 'xxxxyyzzzz', where xxxx signifies the starting year
        of the season, e.g., 2013yyzzzz for 2013-2014, yy is the type of game 
        (01 = preseason, 02 = regular season, 03 = playoffs), and zz is the id 
        of the game itself.

    Returns
    -------
    game_shifts_df: pd.DataFrame
        All shifts from the game stored in a data frame.

    """
    # Specify the url to retrieve
    url = f"https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={gameId}"
    
    # Extract shift information from NHL api
    game_shifts = requests.get(url).json()["data"]
    
    # Convert json to pandas data frame
    game_shifts_df = pd.json_normalize(game_shifts)
    
    # If there is no data for a given game
    if len(game_shifts_df) == 0:
        return pd.DataFrame(columns=["gameId", "playerId", "startTime", "period",
                                     "endTime", "duration", "teamId", "teamName"])
    
    # Select the desired columns
    game_shifts_df = game_shifts_df[["gameId", "playerId", "startTime", "period", "endTime", "duration", 
                     "teamId", "teamName"]]
    
    # Remove goals from the data
    game_shifts_df.dropna(inplace=True)
    
    # If there is no data (besides goals) for a given game
    if len(game_shifts_df) == 0:
        return pd.DataFrame(columns=["gameId", "playerId", "startTime", "period",
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
    game_shifts_df["endTime"] = 1200 * (game_shifts_df["period"] - 1) + game_shifts_df["endTime"]

    # For end times in separate periods
    period_shift = game_shifts_df.apply(lambda row: row["endTime"] < row["startTime"], 
                                        axis=1)
    
    # Add one period worth of seconds
    game_shifts_df.loc[period_shift, "endTime"] += 1200

    # Compute duration to ensure correctness to the highest level
    game_shifts_df["duration"] = game_shifts_df["endTime"] - game_shifts_df["startTime"]

    return game_shifts_df


def get_season_game_shifts(season: int = 2013) -> pd.DataFrame:
    """
    Get all shifts from all games during a season.

    Parameters
    ----------
    season : int, default is 2013.
        The season to get shifts from. Is of the type season-season+1. 
        Needs to be 2010 or higher as it is not defined for earlier seasons.

    Returns
    -------
    game_shifts_df : pd.DataFrame
        All shifts from a season stored in a data frame.

    """
    
    assert season >= 2010, "Season need to be 2010 or later"
    
    # Empty dictionary to store results
    game_shifts_dict = {}
    
    # Url for the season
    season_url = f"https://statsapi.web.nhl.com/api/v1/schedule?season={season}{season+1}&gameType=R"
            
    # Number of games played during the season
    n_games = requests.get(season_url).json()["totalGames"]
        
    # Loop over all games in the season
    for idx in tqdm(range(1, n_games+1)):
        # Specify the gameId
        gameId = f"{season}02{format(idx, '04d')}"
        
        # Extract the shift information
        game_shifts = get_shift_information(gameId)
        
        # Store the shift information
        game_shifts_dict[gameId] = game_shifts
            
    # Combine into one dataframe
    game_shifts_df = pd.concat(game_shifts_dict)

    return game_shifts_df


def get_overlapping_shifts(game_shifts_df: pd.DataFrame, gameId: int) -> pd.DataFrame:
    """
    Find all overlapping shifts from a given shift and compute time played together.

    Parameters
    ----------
    game_shifts_df : pd.DataFrame
        All shifts from a season stored in a data frame.
    gameId : int
        Integer of the type '2013020001'.

    Returns
    -------
    all_overlapping_shifts_long : pd.DataFrame
        All overlapping shifts.

    """
    # Select the specific game
    all_game_shifts = game_shifts_df.loc[game_shifts_df.gameId == gameId].copy()
    
    # Dictionary for all players and shift combination
    overlap_dict_all = {}
    
    # Keep track of players which have been already checked
    checked_players = []
    
    # Loop over all players and their shifts
    for player_team, shifts in all_game_shifts.groupby(["playerId", "teamId"]):
        # Loop over all the shifts of the player
        for shift in shifts.itertuples():
            # Only consider other players for overlapping shifts to avoid duplicates
            other_players = all_game_shifts.drop(shifts.index)
            
            # Remove players that have already been investigated to avoid duplicates
            other_players = other_players.loc[~other_players.playerId.isin(checked_players)]
            
            # Check that the team is correct
            correct_team = (other_players.teamId.to_numpy() == player_team[1])
            
            # Check that the times are overlapping
            correct_time = (
                ((other_players.startTime.to_numpy() >= shift.startTime) &
                 (other_players.startTime.to_numpy() < shift.endTime)) | 
                ((other_players.startTime.to_numpy() < shift.startTime) &
                 (other_players.endTime.to_numpy() > shift.startTime))
                )
            
            # Find all players from the same team that was on the ice during the given shift
            shift_overlap = other_players.loc[correct_team & correct_time]
            
            # Empty dictionary to store intermediate results
            overlap_dict = {}
            
            # Loop over all overlapping shifts from other players
            for overlapping_shift in shift_overlap.itertuples():
                # Starting and ending time of the current shift
                shift_range = range(int(shift.startTime), int(shift.endTime))
                
                # Starting and ending time of the other player's shift
                overlapping_shift_range = range(int(overlapping_shift.startTime), 
                                                int(overlapping_shift.endTime))
                
                # If there is no overlap
                if len(overlapping_shift_range) == 0:
                    overlap_dict[overlapping_shift.playerId] = 0

                else:
                    # Find the range of overlap between the two players
                    overlap_range = range(max(shift_range[0], overlapping_shift_range[0]),
                                          min(shift_range[-1], overlapping_shift_range[-1])+1)
                    
                    # Save the amount of shared minutes played
                    overlap_dict[overlapping_shift.playerId] = len(overlap_range)
                
            # Conver the dictionary to a pandas dataframe 
            json_data = pd.json_normalize(overlap_dict)     
    
            # Combine the pandas dataframe with the current shift
            json_data = pd.concat([json_data, 
                                   pd.Series(shift._asdict()).to_frame().T], 
                                  axis=1)
            
            # Set a unique index from the shift data
            json_data.set_index(['gameId', 'playerId', 'startTime', 'period',
                                 'endTime', 'duration', 'teamId', 'teamName'], 
                                inplace=True)
            
            # Remove unneeded column
            json_data.drop("Index", axis=1, inplace=True)
            
            # Save in dictionary for future use
            overlap_dict_all[shift.Index] = json_data
            
        # Add the current player as already examined
        checked_players.append(player_team[0])

    # Combine into one data frame
    all_overlapping_shifts = pd.concat(overlap_dict_all)
   
    # Reset index and drop unneeded columns
    all_overlapping_shifts = all_overlapping_shifts.reset_index().set_index(
        "level_0").drop(["startTime", "endTime", "period", 
                         "duration", "teamId", "teamName"], axis=1)
                         
    # Convert the data from wide to long format
    all_overlapping_shifts_long = pd.melt(all_overlapping_shifts, 
                                          id_vars=["gameId", "playerId"], 
                                          var_name="playerId2", 
                                          value_name="seconds").dropna()    
    
    return all_overlapping_shifts_long
