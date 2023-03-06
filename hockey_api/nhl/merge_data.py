import pandas as pd
import numpy as np
from pandera.typing import DataFrame


def remove_duplicated_shifts(shifts: DataFrame) -> DataFrame:
    """
    Remove or flag shifts that are/could be duplicates.

    Parameters
    ----------
    shifts : DataFrame
        Data frame containing all shifts from a game.

    Returns
    -------
    game_shifts : DataFrame
        Data frame of all shifts with a new column to indicate possible duplicate shifts.

    """
    # Copy to avoid changing in-place
    game_shifts = shifts.copy()

    # Create a new column to flag for potential to flag for potential extra players
    game_shifts["PotentialExtraPlayer"] = False

    # See if the team has cases where an extra player is tagged
    for team, team_shifts in game_shifts.groupby("TeamName"):
        # The shift started at the start/end of the game
        start_of_game = team_shifts["ShiftStart"] == 0
        end_of_game = team_shifts["ShiftEnd"].isin([1200, 2400, 3600])
        
        # The start time of the shift is not present among team end times
        extra_start_player = ~team_shifts["ShiftStart"].isin(team_shifts["ShiftEnd"])

        # The end time of the shift is not present among team start times
        extra_end_player = ~team_shifts["ShiftEnd"].isin(team_shifts["ShiftStart"])
        
        # The shift occurred in regulation
        regulation = team_shifts["PeriodNumber"] < 4

        # Players who played an "extra" shift which they did not actually play
        extra = team_shifts.loc[((extra_start_player & ~start_of_game) | 
                                 (extra_end_player   & ~end_of_game)) & 
                                regulation]
        
        if len(extra) > 0:
            # Specify a potential extra shift
            game_shifts.loc[extra.index, "PotentialExtraPlayer"] = True

    # Remove shifts of duration 0
    game_shifts.loc[game_shifts["Duration"] != 0]        

    # Duplicated end time
    dupe_end = game_shifts.loc[game_shifts.duplicated(["PlayerId", "ShiftEnd"], keep=False)].copy()
    
    # Sort by duration, keep only the shortest
    dupe_end.sort_values(["PlayerId", "ShiftEnd", "Duration"], inplace=True)

    # Remove the longest duplicate per group
    drop_end_times = dupe_end.duplicated(["PlayerId", "ShiftEnd"], keep="first")
    
    # Drop the duplicated rows from the data
    game_shifts = game_shifts.drop(drop_end_times[drop_end_times].index)
    
    # Duplicated start time
    dupe_start = game_shifts.loc[game_shifts.duplicated(["PlayerId", "ShiftStart"], keep=False)].copy()
    
    # Sort by duration, keep only the shortest
    dupe_start.sort_values(["PlayerId", "ShiftStart", "Duration"], inplace=True)

    # Remove the longest duplicate per group
    drop_start_times = dupe_start.duplicated(["PlayerId", "ShiftStart"], keep="first")
    
    # Drop the duplicated rows from the data
    game_shifts = game_shifts.drop(drop_start_times[drop_start_times].index)

    return game_shifts


def merge_json_pbp_and_shifts(json_game) -> DataFrame:
    """
    Combine play by play and shifts from the JSON data into one data frame.

    Parameters
    ----------
    json_game : GameJSON
        Object with information from the JSON representation of the game.

    Returns
    -------
    events_with_players : DataFrame
        Adjusted data frame with players added to the play by play data.

    """
    # Extract pbp and shifts
    pbp = json_game.get_event_data()
    shifts = json_game.get_shifts()
    
    # Remove duplicate game shifts
    game_shifts = remove_duplicated_shifts(shifts)
   
    # Copy to avoid changing in-place    
    events = pbp.copy()
       
    # Ensure GameId is an integer
    game_shifts["GameId"] = game_shifts["GameId"].astype(int)
    events["GameId"] = events["GameId"].astype(int)
            
    # Get the game shifts
    shifts = game_shifts.copy()
        
    # Determine which team played at home
    home_team = events.HomeTeamName.unique()[0]
    
    # Combine event data with shifts to get all available information
    event_shifts = events.merge(shifts, on=["GameId", "PeriodNumber"], how="outer")

    # Keep only players who were (most likely) on the ice during the event
    on_ice = event_shifts.loc[(event_shifts.TotalElapsedTime.between(event_shifts.ShiftStart, 
                                                                     event_shifts.ShiftEnd-1) &
                               event_shifts.EventType.isin(["PERIOD START", "FACEOFF"]) &
                               event_shifts.PeriodNumber.le(3)) |
                              (event_shifts.TotalElapsedTime.between(event_shifts.ShiftStart+1,
                                                                     event_shifts.ShiftEnd) &
                               ~event_shifts.EventType.isin(["PERIOD START", "FACEOFF"])) |
                              (event_shifts.TotalElapsedTime.between(event_shifts.ShiftStart, 
                                                                     event_shifts.ShiftEnd-1) &
                               event_shifts.EventType.isin(["PERIOD START", "FACEOFF"]) &
                               event_shifts.PeriodNumber.gt(3)) |
                              (event_shifts.TotalElapsedTime.between(event_shifts.ShiftStart, 
                                                                     event_shifts.ShiftEnd) &
                               event_shifts.EventType.isin(["GOAL"]) &
                               event_shifts.PeriodNumber.gt(3)) 
                              ].copy()

    # Combine all player ids for each event number into a string
    player_ids_on_ice = on_ice[["TeamName", "EventNumber", "PlayerId"]].astype(str).groupby(
        ["TeamName", "EventNumber"])["PlayerId"].agg(",".join).unstack().T

    # Determine if the first team is the home team
    first_is_home = player_ids_on_ice.iloc[:, 0].name == home_team

    # Players on the ice for first and second team, respectively
    f1 = player_ids_on_ice.iloc[:, 0].str.split(pat=",", expand=True)
    f2 = player_ids_on_ice.iloc[:, 1].str.split(pat=",", expand=True)

    # Rename columns
    if first_is_home:
        f1.columns = [f"HomePlayer{i}" for i in range(1, len(f1.columns)+1)]    
        f2.columns = [f"AwayPlayer{i}" for i in range(1, len(f2.columns)+1)]    
    else:
        f1.columns = [f"AwayPlayer{i}" for i in range(1, len(f1.columns)+1)]    
        f2.columns = [f"HomePlayer{i}" for i in range(1, len(f2.columns)+1)]    
        
    # Combine home and away players into one data frame
    home_away_players = pd.merge(f1.reset_index(), f2.reset_index())
    
    # Convert all columns to float
    home_away_players = home_away_players.astype(float)
    
    # Convert eventnumber to integer
    home_away_players["EventNumber"] = home_away_players["EventNumber"].astype(int)
    
    # Sort by event number
    home_away_players.sort_values("EventNumber", inplace=True)
    
    # Combine event data with home and away players in the wide format
    events_with_players = events.merge(home_away_players, on="EventNumber")
    
    # Find players that may be duplicates
    possible_duplicates = on_ice.loc[on_ice.PotentialExtraPlayer, 
                                     ["TeamName", "EventNumber", "PlayerId",
                                      "PotentialExtraPlayer"]]
    
    # Loop over all shifts that maybe be erroneous
    for possible_duplicate in possible_duplicates.itertuples():
        
        # If it was the home team with the duplicate
        is_home = possible_duplicate.TeamName == home_team
        
        # See if there have been tagged with more than 6 players on the ice simultaneously
        cond = (events_with_players.EventNumber.eq(possible_duplicate.EventNumber) &
                (is_home and "HomePlayer7" in events_with_players.columns) |
                (~is_home and "AwayPlayer7" in events_with_players.columns))
        
        # Where the player is on the ice
        player = np.where(events_with_players.iloc[:, 30:].values == 
                          possible_duplicate.PlayerId)
        
        # In case there is no actual duplicate
        if len(player[0]) == 0:
            continue
        
        # Find the common index
        duplicate_idx = np.intersect1d(events_with_players.loc[cond].index, player[0])
        
        # Find the column where the index are duplicated
        duplicate_col = player[1][np.in1d(player[0], duplicate_idx)]
        
        for dupe_idx, dupe_col in zip(duplicate_idx, duplicate_col):
            # Find the column name of the duplicate
            col_name = events_with_players.columns[30+dupe_col]
            
            # Replace the duplicate player with nan
            events_with_players.loc[dupe_idx, col_name] = np.nan
    
    # Shift the home player columns to the left to fill NA holes        
    home = events_with_players.loc[:, events_with_players.columns.str.startswith("HomePlayer")].apply(
        lambda x: pd.Series(x.dropna().to_numpy()), axis=1)

    # Save the shifted player values
    events_with_players.loc[:, [f"HomePlayer{i}" for i in range(1, len(home.columns)+1)]] = home.values

    # Shift the away player columns to the left to fill NA holes
    away = events_with_players.loc[:, events_with_players.columns.str.startswith("AwayPlayer")].apply(
        lambda x: pd.Series(x.dropna().to_numpy()), axis=1)
    
    # Save the shifted player values
    events_with_players.loc[:, [f"AwayPlayer{i}" for i in range(1, len(away.columns)+1)]] = away.values
    
    for team in ["Home", "Away"]:
        # Find if there are any columns that are extra, i.e., PlayerX, where X = 7/8/9
        player_cond = (events_with_players.columns.str.startswith(f"{team}Player") &
                       events_with_players.columns.str.contains("7|8|9|10|11|12"))
        # If there are no extra columns
        if all(~player_cond):
            continue
        
        # Get the data corresponding to extra columns
        player_extra_columns = events_with_players.loc[:, player_cond]
        
        # Find rows that might have duplicated player ids
        player_duplicate = np.where(player_extra_columns.notna())
        
        # For the players who are duplicated, set the PlayerX to nan
        events_with_players.loc[player_duplicate[0], 
                                player_extra_columns.columns[player_duplicate[1]]] = np.nan
        
        # Remove duplicated columns
        events_with_players = events_with_players.loc[:, ~events_with_players.columns.duplicated()].copy()
        
    # Find columns with only NA values
    only_na_columns = events_with_players.notna().sum(axis=0)
    
    # Remove columns with only NA
    events_with_players = events_with_players.loc[:, only_na_columns.ne(0)].copy()
    
    # Add penalty shootout events too not drop any events
    events_with_players = pd.concat([
        events_with_players, 
        events.loc[events.TotalElapsedTime.eq(4800)]]).reset_index(drop=True)

    return events_with_players


def merge_json_and_html_pbp(json_game, html_game) -> DataFrame:
    """
    Combine play by play data from the JSON and HTML representations.

    Parameters
    ----------
    json_game : GameJSON
        Object containing the JSON representation of the game.
    html_game : GameHTML
        Object containing the HTML representation of the game.

    Returns
    -------
    html_pbp : DataFrame
        Merged data frame with players from the HTML source.

    """
    # Extract the play by play data
    json_pbp = json_game.pbp.copy()
    html_pbp = html_game.pbp.copy()

    # Drop the events that are not important
    event_drops = ["DELPEN", "SOC", "ANTHEM", "PGEND", "PGSTR", "EGT"]
    
    # Remove unwanted events
    html_pbp = html_pbp.loc[~html_pbp.EventType.isin(event_drops)].copy()
    json_pbp = json_pbp.loc[~json_pbp.EventType.isin(event_drops)].copy()
        
    # If the team of the event was the home team
    home_team = html_pbp.Team.eq(html_pbp.HomeTeamName)
    
    # Find all blocked shots in the HTML data
    blocks = html_pbp.EventType.eq("BLOCKED SHOT")
    
    # Flip the perspective of the blocked shots
    html_pbp.loc[blocks, ["Player1", "Player2"]] = html_pbp.loc[blocks, ["Player2", "Player1"]].values
    html_pbp.loc[blocks, ["PlayerId1", "PlayerId2"]] = html_pbp.loc[blocks, ["PlayerId2", "PlayerId1"]].values
    html_pbp.loc[blocks, ["PlayerType1", "PlayerType2"]] = html_pbp.loc[blocks, ["PlayerType2", "PlayerType1"]].values
    
    # If the home team blocked the shot; set team name to away
    html_pbp.loc[blocks & home_team, "Team"] = html_pbp.loc[blocks & home_team, "AwayTeamName"]
    
    # If the away team blocked the shot; set team name to home
    html_pbp.loc[blocks & ~home_team, "Team"] = html_pbp.loc[blocks & ~home_team, "HomeTeamName"]
    
    # Ensure GameId is an integer
    html_pbp["GameId"] = html_pbp["GameId"].astype(int)
    json_pbp["GameId"] = json_pbp["GameId"].astype(int)
    
    # Specify the columns to add
    cols = ["GoalsAgainst", "GoalsFor", "X", "Y", "GameWinningGoal", "EmptyNet"]
    
    # Find the index of the zone column
    zone_col_idx = int(np.where(html_pbp.columns.str.contains("Zone"))[0][0])
    
    # Loop over each column
    for col in cols[::-1]:
        # Insert the new column at the specified index
        html_pbp.insert(zone_col_idx, col, np.nan)
        
    # Loop over all the events in each game
    for game_id, events in html_pbp.groupby("GameId"):
        # Get all events from the JSON data of the same game
        json_events = json_pbp.loc[json_pbp.GameId.eq(game_id)].copy()
        
        # If there are no JSON events to add
        if len(json_events) == 0:
            break
        
        # Loop over each event
        for event in events.itertuples():
            # Get the same event type from the JSON data
            same_json_event_type = json_events.loc[json_events.EventType.eq(event.EventType) &
                                                   json_events.PeriodNumber.eq(event.PeriodNumber) &
                                                   (np.isnan(event.PenaltyMinutes) | 
                                                    (~np.isnan(event.PenaltyMinutes) &
                                                     json_events.PenaltyMinutes.eq(event.PenaltyMinutes))
                                                    )].copy()
            
            # Compute the time difference between the current event and the other events
            time_diff = same_json_event_type.TotalElapsedTime - event.TotalElapsedTime
            
            # If no close difference is found
            if all(time_diff > 30):
                continue
            
            # Find the JSON event with the closest time
            min_time_diff = min(time_diff)
            closest_time_idx = [idx for idx, diff in enumerate(time_diff) if diff == min_time_diff]
            
            # Get the event with the closest time
            closest_time = same_json_event_type.iloc[closest_time_idx]
            
            # print(len(closest_time))
            if len(closest_time) > 1:
                # Get the current length
                curr_len = len(closest_time)
                
                if event.PlayerId1 is not None:
                    # Find the player involved with the event
                    closest_time = closest_time.loc[closest_time.PlayerId1.eq(event.PlayerId1) |
                                                    np.isnan(event.PlayerId1)].copy()
                
                if len(closest_time) > 1:
                    # If there are still more than one match, use the first one
                    closest_time = closest_time.iloc[[0], :].copy()
                elif len(closest_time) == 0 and curr_len > 1:
                    # Get the first match if many still remain
                    closest_time = same_json_event_type.iloc[closest_time_idx].iloc[[0]]
            
            # Save the event in the HTML data
            html_pbp.loc[event.Index, cols] = closest_time[cols].values[0]
            
            # Remove the observation from the JSON data
            json_events.drop(closest_time.index, inplace=True)
    
    ## Update goals against / goals for
    # Get all goals
    goals = html_pbp.loc[html_pbp.EventType.eq("GOAL")]
    
    # Determine if the home team scored
    home_goal = goals.HomeTeamName.eq(goals.Team)
    
    # Current index 
    curr_idx = 0
    
    # Current number of home and away goals
    curr_home_goals = 0
    curr_away_goals = 0
    
    # Get the index of all goals
    index_of_goals = set(goals.index)
    
    # Get the index of the last event
    max_idx = html_pbp.index.max()
    
    # Add the index of the last event in case it is not already present
    index_of_goals.add((max_idx))
    
    # Loop over each goal index
    for goal_idx in sorted(index_of_goals):
        # Update the goals scored for all events prior
        html_pbp.loc[curr_idx:goal_idx, "GoalsAgainst"] = curr_away_goals
        html_pbp.loc[curr_idx:goal_idx, "GoalsFor"] = curr_home_goals
        
        # Update the score
        if goal_idx != max_idx and home_goal[goal_idx]:
            curr_home_goals += 1
        elif goal_idx != max_idx and ~home_goal[goal_idx]:
            curr_away_goals += 1
        
        # Update the goals scored for the actual goal
        html_pbp.loc[goal_idx, "GoalsAgainst"] = curr_away_goals
        html_pbp.loc[goal_idx, "GoalsFor"] = curr_home_goals
            
        # Update the current index
        curr_idx = goal_idx
    
    # Adjust goals against/for to only count after the goal has been confirmed
    html_pbp.loc[html_pbp.AwayTeamName.eq(html_pbp.Team) & 
                 html_pbp.EventType.eq("GOAL") &
                 html_pbp.PeriodNumber.le(3), "GoalsAgainst"] -= 1
    
    html_pbp.loc[html_pbp.HomeTeamName.eq(html_pbp.Team) & 
                 html_pbp.EventType.eq("GOAL") &
                 html_pbp.PeriodNumber.le(3), "GoalsFor"] -= 1
    
    # Fill the values for the events that occur after the last goal
    goal_cols = ["GoalsAgainst", "GoalsFor"]
    html_pbp.loc[:, goal_cols] = html_pbp.loc[:, goal_cols].ffill()
    
    return html_pbp


def merge_json_and_html_shifts(json_shifts: DataFrame, html_shifts: DataFrame) -> DataFrame:
    """
    Combine shifts from the JSON and HTML representations.

    Parameters
    ----------
    json_shifts : DataFrame
        Shifts from the JSON representation of the game.
    html_shifts : DataFrame
        Shifts from the HTML representation of the game.

    Returns
    -------
    shifts : DataFrame
        Merged data frame with shifts from both sources.

    """

    # Sort shifts by player id and shift start and end time
    sorted_json_shifts = json_shifts.sort_values(["PlayerId", "ShiftStart", "ShiftEnd"]
                                                 ).reset_index(drop=True).copy()
    
    sorted_html_shifts = html_shifts.sort_values(["PlayerId", "ShiftStart", "ShiftEnd"]
                                                 ).reset_index(drop=True).copy()
        
    # Loop over all end/start of periods from Period 1/2 to 11/12
    for time_idx, time in enumerate(range(1200, 12001, 1200)):
        # Find the shifts that overlap between periods
        json_shift_overlap_bool = (sorted_json_shifts.ShiftStart.lt(time) & 
                                   sorted_json_shifts.ShiftEnd.gt(time))
        html_shift_overlap_bool = (sorted_html_shifts.ShiftStart.lt(time) & 
                                   sorted_html_shifts.ShiftEnd.gt(time))
        
        # Get the overlapping shifts
        json_shift_overlap = sorted_json_shifts.loc[json_shift_overlap_bool].copy()
        html_shift_overlap = sorted_html_shifts.loc[html_shift_overlap_bool].copy()
        
        # Update the end time to be the end of the period
        sorted_json_shifts.loc[json_shift_overlap.index, "ShiftEnd"] = time
        sorted_html_shifts.loc[html_shift_overlap.index, "ShiftEnd"] = time
        
        # Update the period and time of the shift start
        json_shift_overlap[["PeriodNumber", "ShiftStart"]] = [time_idx + 2, time]
        html_shift_overlap[["PeriodNumber", "ShiftStart"]] = [time_idx + 2, time]
        
        # Add to the data 
        sorted_json_shifts = pd.concat([sorted_json_shifts, json_shift_overlap])
        sorted_html_shifts = pd.concat([sorted_html_shifts, html_shift_overlap])
        
    # Sort values and reset index
    sorted_json_shifts = sorted_json_shifts.sort_values(
        ["PlayerId", "ShiftStart", "ShiftEnd"]).reset_index(drop=True)
    
    sorted_html_shifts = sorted_html_shifts.sort_values(
        ["PlayerId", "ShiftStart", "ShiftEnd"]).reset_index(drop=True)
    
    # Update the duration to be correct
    sorted_json_shifts["Duration"] = sorted_json_shifts["ShiftEnd"] - sorted_json_shifts["ShiftStart"]
    sorted_html_shifts["Duration"] = sorted_html_shifts["ShiftEnd"] - sorted_html_shifts["ShiftStart"]

    # Ensure both columns are the correct data type
    sorted_html_shifts = sorted_html_shifts.astype({"GameId": int, "PlayerId": int})
    sorted_html_shifts = sorted_html_shifts.astype({"GameId": int, "PlayerId": int})

    # Combine both data sources into one dataframe
    shifts = sorted_html_shifts.drop(["Player", "ShiftNumber"], axis=1).merge(
        sorted_json_shifts.drop(["ShiftNumber"], axis=1), how="outer", indicator="Source")
        
    # Adjust the merge indicator column
    shifts["Source"].replace({"both": "Both", "left_only": "HTML", "right_only": "JSON"}, inplace=True)
    
    # Create a dictionary of player names and ids in the HTML shift data
    html_player_names = sorted_html_shifts[["Player", "PlayerId"]].set_index("PlayerId").to_dict()["Player"]
    
    # Find the id of any missing player names
    missing_player_names_id = shifts.loc[shifts.Player.isna(), "PlayerId"].values
    
    # Find the name of the missing players
    missing_player_names = {player_id: html_player_names[player_id].title() for 
                            player_id in missing_player_names_id}
    
    # Add any missing player names back
    shifts.loc[shifts.Player.isna(), "Player"] = shifts.loc[shifts.Player.isna(), "PlayerId"].replace(
        missing_player_names)

    # Determine the shift number by player
    shift_number = shifts.groupby("PlayerId")["ShiftStart"].rank(method="first").astype(int)
    
    # Add shift number back as a column
    shifts.insert(3, "ShiftNumber", shift_number)
    
    # Move the player column 
    player = shifts.pop("Player")
    shifts.insert(2, "Player", player)
    
    # Fill any NA with "" for Event
    shifts["Event"] = shifts.Event.fillna("")
    
    return shifts