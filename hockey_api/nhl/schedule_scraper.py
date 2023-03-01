import requests
from typing import Union, List, Tuple


def get_number_of_games_in_season(season: Union[str, int], season_type: str="R", 
                                  requests_session: requests.sessions.Session=None) -> Tuple[int, str]:
    """
    Retrieve the number of games for 

    Parameters
    ----------
    season : int or str
        Integer denoting the starting year of the season, e.g., 2021 gives 2021-2022.
    season_type : str
        One of: R = Regular Season, P = Playoffs, PR = Preseason, A = All-star.
    requests_session : requests.sessions.Session
        Session for requests.

    Returns
    -------
    n_games : int
        The total number of games in the season.

    """    
    # Create a new session if none is provided
    if requests_session is None:
        requests_session = requests.Session()
    
    # Converting the season type to its numerical representation
    season_type_code_dict = {"PR": "01", "R": "02", "P": "03", "A": "04"}    
    
    # Convert the season to an integer
    year = int(season)
    
    # Url for the season
    season_url = f"https://statsapi.web.nhl.com/api/v1/schedule?season={year}{year+1}&gameType={season_type}"
            
    # Number of games played during the season
    n_games = requests_session.get(season_url).json()["totalGames"]
        
    # Get the season type code
    season_type_code = season_type_code_dict[season_type]
    
    return n_games, season_type_code


def get_game_ids_between_dates(start_date: str, end_date: str,
                               requests_session: requests.sessions.Session=None) -> List[int]:
    """
    Find all game ids that took place between start and end date. 

    Parameters
    ----------
    start_date : str
        Date in YYYY-MM-DD format.
    end_date : str
        Date in YYYY-MM-DD format.
    requests_session : requests.sessions.Session
        Session for requests.
        
    Returns
    -------
    date_game_ids : list
        List of all game ids, given as integers, between the two dates.

    """
    # Create a new session if none is provided
    if requests_session is None:
        requests_session = requests.Session()
        
    # Get the information of all games between the two dates
    date_url = f"https://statsapi.web.nhl.com/api/v1/schedule?startDate={start_date}&endDate={end_date}"
    
    # Get the game information between the two dates
    games_between_dates = requests.get(date_url).json()["dates"]
    
    # Get all games for a given date
    date_games = [date["games"] for date in games_between_dates]
    
    # Find all game ids between the two dates
    date_game_ids = [game["gamePk"] for date in date_games for game in date]

    return date_game_ids