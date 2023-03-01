from hockey_api.nhl.html_scraper import GameHTML
from hockey_api.nhl.json_scraper import GameJSON
from hockey_api.nhl.merge_data import merge_json_pbp_and_shifts, merge_json_and_html_pbp, merge_json_and_html_shifts
from hockey_api.nhl.schedule_scraper import get_number_of_games_in_season, get_game_ids_between_dates
from hockey_api.nhl.utils import map_player_names_to_ids, map_player_ids_to_names, standardize_coordinates, \
    add_player_ids_to_html_shifts, adjust_player_roles_html
import pandas as pd
import requests
from typing import List, Tuple, Union
from pandera.typing import DataFrame
from tqdm import tqdm, trange
from time import sleep
from json import JSONDecodeError


def scrape_game(game_id: Union[str, int]) -> Tuple[DataFrame, DataFrame]:
    """
    Scrape play by play and shift data from a given game.

    Parameters
    ----------
    game_id : Union[str, int]
        The ID of the game, given as e.g. 2021020001 or "2021020001".

    Returns
    -------
    merged_game : DataFrame
        Combined information from the HTML and JSON representations of the game.
    merged_shifts : DataFrame
        Combined information from the HTML and JSON representations of the shifts.
        
    """
    # Specify a requests session
    requests_session = requests.Session()
    
    # Get the JSON data
    json_game = GameJSON(game_id, requests_session)
    
    # Get the HTML data
    html_game = GameHTML(game_id, requests_session)
    
    # Merge json play by play and shifts
    try:
        json_game.pbp = merge_json_pbp_and_shifts(json_game)
    except ValueError:
        print("No JSON data to merge.")

    # Add player names/ids to the data sources
    json_game.pbp = map_player_ids_to_names(json_game)
    html_game.pbp = map_player_names_to_ids(json_game, html_game)

    # Adjust player roles in the HTML data
    html_game.pbp = adjust_player_roles_html(html_game)

    # Merge JSON and HTML data
    merged_game = merge_json_and_html_pbp(json_game, html_game)
    
    # Standardize coordinates
    merged_game = standardize_coordinates(merged_game)
  
    # Get the JSON and HTML shift data
    json_shifts = json_game.get_shifts()
    html_shifts = pd.concat([html_game.get_shifts(home=True),
                             html_game.get_shifts(home=False)])
    
    # Add the player id column to the HTML shifts
    html_shifts = add_player_ids_to_html_shifts(json_shifts, html_shifts)
        
    # Merge the shifts from both sources
    merged_shifts = merge_json_and_html_shifts(json_shifts, html_shifts)
    
    return merged_game, merged_shifts


def scrape_list_of_games(game_id_list: List) -> Tuple[DataFrame, DataFrame]:
    """
    Scrape all games in the provided list.

    Parameters
    ----------
    game_id_list : List
        List of all game ids to scrape.
   
    Returns
    -------
    games_in_list : DataFrame
        All events from the list of games, concatenated into one data frame.
    shifts_in_list : DataFrame
        All shifts from the list of games, concatenated into one data frame.

    """
    # Storage of all games
    game_dict = {}
    shift_dict = {}
    
    # Loop over all game ids 
    for game_id in tqdm(game_id_list, desc="Scraping list of games"):
        ## Default values
        # Return an empty data frame if scraping failed
        game = pd.DataFrame(columns=[
            "GameId", "Date", "AwayTeamName", "HomeTeamName", "EventNumber",
            "PeriodNumber", "Manpower", "EventTime", "TotalElapsedTime",
            "EventType", "Description", "Team", "GoalsAgainst", "GoalsFor", "X",
            "Y", "GameWinningGoal", "EmptyNet", "Zone", "ShotType", "PenaltyShot",
            "PenaltyType", "PenaltyMinutes", "PlayerType1", "Player1", "PlayerId1",
            "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3",
            "PlayerId3", "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2",
            "AwayPlayerId2", "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4",
            "AwayPlayerId4", "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6",
            "AwayPlayerId6", "AwayGoalieOnIce", "AwayGoalieName", "AwayGoalieId",
            "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2",
            "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4",
            "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6",
            "HomeGoalieOnIce", "HomeGoalieName", "HomeGoalieId"])
        
        shifts = pd.DataFrame(columns=[
            "GameId", "PlayerId", "Player", "TeamName", "ShiftNumber",
            "PeriodNumber", "ShiftStart", "ShiftEnd", "Duration", "Event",
            "Source"])
        
        try:
            # Scrape the game
            game, shifts = scrape_game(game_id)
        except KeyError: 
            print(f"Scraping failed for game: {game_id}. Returning empty data frame.")
                    
        except JSONDecodeError:
            print("JSON error found, waiting 10 seconds before trying again.")
            sleep(10)
        
        # Save the result in the dictionary
        game_dict[game_id] = game
        shift_dict[game_id] = shifts
    
    # Combine all games into one data frame
    games_in_list = pd.concat(game_dict).reset_index(drop=True)
    shifts_in_list = pd.concat(shift_dict).reset_index(drop=True)

    return games_in_list, shifts_in_list


def scrape_date_range(start_date: str, end_date: str=None) -> Tuple[DataFrame, DataFrame]:
    """
    Scrape all games from a given date range.

    Parameters
    ----------
    start_date : str
        Date in YYYY-MM-DD format.
    end_date : str, optional
        Date in YYYY-MM-DD format. If not provided defaults to start_date.

    Returns
    -------
    games_in_date_range : DataFrame
        All events from the date range, concatenated into one data frame.
    shifts_in_date_range : DataFrame
        All shifts from the date range, concatenated into one data frame.

    """
    # If end date is not supplied
    if end_date is None:
        end_date = start_date
    
    # Get all game ids for the given date or date range
    game_ids = get_game_ids_between_dates(start_date, end_date)
    
    # Storage of all games
    game_dict = {}
    shift_dict = {}

    # Loop over all game ids 
    for game_id in tqdm(game_ids,
                        desc=f"Scraping games between {start_date} and {end_date}"):
        ## Default values
        # Return an empty data frame if scraping failed
        game = pd.DataFrame(columns=[
            "GameId", "Date", "AwayTeamName", "HomeTeamName", "EventNumber",
            "PeriodNumber", "Manpower", "EventTime", "TotalElapsedTime",
            "EventType", "Description", "Team", "GoalsAgainst", "GoalsFor", "X",
            "Y", "GameWinningGoal", "EmptyNet", "Zone", "ShotType", "PenaltyShot",
            "PenaltyType", "PenaltyMinutes", "PlayerType1", "Player1", "PlayerId1",
            "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3",
            "PlayerId3", "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2",
            "AwayPlayerId2", "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4",
            "AwayPlayerId4", "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6",
            "AwayPlayerId6", "AwayGoalieOnIce", "AwayGoalieName", "AwayGoalieId",
            "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2",
            "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4",
            "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6",
            "HomeGoalieOnIce", "HomeGoalieName", "HomeGoalieId"])
        
        shifts = pd.DataFrame(columns=[
            "GameId", "PlayerId", "Player", "TeamName", "ShiftNumber",
            "PeriodNumber", "ShiftStart", "ShiftEnd", "Duration", "Event",
            "Source"])
        
        try:
            # Scrape the game
            game, shifts = scrape_game(game_id)
        except KeyError: 
            print(f"Scraping failed for game: {game_id}. Returning empty data frame.")
                    
        except JSONDecodeError:
            print("JSON error found, waiting 10 seconds before trying again.")
            sleep(10)
            
        # Save the result in the dictionary
        game_dict[game_id] = game
        shift_dict[game_id] = shifts
        
    # Combine all games into one data frame
    games_in_date_range = pd.concat(game_dict).reset_index(drop=True)
    shifts_in_date_range = pd.concat(shift_dict).reset_index(drop=True)
    
    return games_in_date_range, shifts_in_date_range


def scrape_season(season: Union[str, int], season_type: str="R") -> Tuple[DataFrame, DataFrame]:
    """
    Scrape all games and shifts from a given part of a season.

    Parameters
    ----------
    season : Union[str, int]
        The starting year of the season to consider, e.g. 2021 for 2021-2022.
    season_type : str
        One of: R = Regular Season, P = Playoffs, PR = Preseason, A = All-star.

    Returns
    -------
    games_in_season : DataFrame
        All events from the season, concatenated into one data frame.
    shifts_in_season : DataFrame
        All shifts from the season, concatenated into one data frame.

    """
    # Get the number of games in the season and the season type code
    nr_of_games, season_type_code = get_number_of_games_in_season(season, season_type)
    
    # Storage of all games
    game_dict = {}
    shift_dict = {}

    # The base for game id
    game_id_base = f"{season}{season_type_code}"
    
    # Loop over all game ids 
    for game_id_nr in trange(1, nr_of_games+1, 
                             desc=f"Scraping season {season}-{int(season)+1}"):
        
        # The padding to be added with zeros
        padding = ""
        
        # Pad with zeros if needed
        if game_id_nr < 10:
            padding = "000"
        elif game_id_nr >= 10 and game_id_nr < 100:
            padding = "00"
        elif game_id_nr >= 100 and game_id_nr < 1000:
            padding = "0"
        
        # Get the game id
        game_id = f"{game_id_base}{padding}{game_id_nr}"
        
        ## Default values
        # Return an empty data frame if scraping failed
        game = pd.DataFrame(columns=[
            "GameId", "Date", "AwayTeamName", "HomeTeamName", "EventNumber",
            "PeriodNumber", "Manpower", "EventTime", "TotalElapsedTime",
            "EventType", "Description", "Team", "GoalsAgainst", "GoalsFor", "X",
            "Y", "GameWinningGoal", "EmptyNet", "Zone", "ShotType", "PenaltyShot",
            "PenaltyType", "PenaltyMinutes", "PlayerType1", "Player1", "PlayerId1",
            "PlayerType2", "Player2", "PlayerId2", "PlayerType3", "Player3",
            "PlayerId3", "AwayPlayer1", "AwayPlayerId1", "AwayPlayer2",
            "AwayPlayerId2", "AwayPlayer3", "AwayPlayerId3", "AwayPlayer4",
            "AwayPlayerId4", "AwayPlayer5", "AwayPlayerId5", "AwayPlayer6",
            "AwayPlayerId6", "AwayGoalieOnIce", "AwayGoalieName", "AwayGoalieId",
            "HomePlayer1", "HomePlayerId1", "HomePlayer2", "HomePlayerId2",
            "HomePlayer3", "HomePlayerId3", "HomePlayer4", "HomePlayerId4",
            "HomePlayer5", "HomePlayerId5", "HomePlayer6", "HomePlayerId6",
            "HomeGoalieOnIce", "HomeGoalieName", "HomeGoalieId"])
        
        shifts = pd.DataFrame(columns=[
            "GameId", "PlayerId", "Player", "TeamName", "ShiftNumber",
            "PeriodNumber", "ShiftStart", "ShiftEnd", "Duration", "Event",
            "Source"])
        
        try:
            # Scrape the game
            game, shifts = scrape_game(game_id)
        except KeyError: 
            print(f"Scraping failed for game: {game_id}. Returning empty data frame.")
                    
        except JSONDecodeError:
            print("JSON error found, waiting 10 seconds before trying again.")
            sleep(10)
            
            # Scrape the game
            game, shifts = scrape_game(game_id)
        
        # Save the result in the dictionary
        game_dict[game_id] = game
        shift_dict[game_id] = shifts
        
    # Combine all games into one data frame
    games_in_season = pd.concat(game_dict).reset_index(drop=True)
    shifts_in_season = pd.concat(shift_dict).reset_index(drop=True)

    return games_in_season, shifts_in_season
