import requests
from typing import Union, List


def get_number_of_games_in_season(season: Union[str, int], requests_session: requests.sessions.Session) -> int:
    """
    Retrieve the number of games for 

    Parameters
    ----------
    season : int or str
        Integer denoting the starting year of the season, e.g., 2021 gives 2021-2022.
    requests_session : requests.sessions.Session
        Session for requests.

    Returns
    -------
    n_games : int
        The total number of games in the season.

    """    
    
    # Convert the season to an integer
    year = int(season)
    
    # Url for the season
    season_url = f"https://statsapi.web.nhl.com/api/v1/schedule?season={year}{year+1}&gameType=R"
            
    # Number of games played during the season
    n_games = requests_session.get(season_url).json()["totalGames"]
        
    return n_games


def get_game_ids_between_dates(start_date: str, end_date: str) -> List[int]:
    """
    Find all game ids that took place between start and end date. 

    Parameters
    ----------
    start_date : str
        Date in YYYY-MM-DD format.
    end_date : str
        Date in YYYY-MM-DD format.

    Returns
    -------
    date_game_ids : list
        List of all game ids, given as integers, between the two dates.

    """
    
    # Get the information of all games between the two dates
    date_url = f"https://statsapi.web.nhl.com/api/v1/schedule?startDate={start_date}&endDate={end_date}"
    
    # Get the game information between the two dates
    games_between_dates = requests.get(date_url).json()["dates"]
    
    # Get all games for a given date
    date_games = [date["games"] for date in games_between_dates]
    
    # Find all game ids between the two dates
    date_game_ids = [game["gamePk"] for date in date_games for game in date]

    return date_game_ids