from hockey_api.nhl.scraper import scrape_game
from hockey_api.nhl.schedule_scraper import get_number_of_games_in_season, get_game_ids_between_dates
import pytest


def test_game_scraper():
    """Test if a given game has the correct structure"""
    # Specify the game id
    game_id = 2021020001
    
    # Scrape the game
    pbp, shifts = scrape_game(game_id)
    
    # Test pbp scraping    
    pbp_game_id = pbp.GameId[0]
    
    assert pbp.shape == (321, 64) 
    assert pbp_game_id == 2021020001
    
    # Test shift scraping
    shifts_game_id = shifts.GameId[0]
    
    assert shifts.shape == (789, 11) 
    assert shifts_game_id == 2021020001


@pytest.mark.filterwarnings("ignore:The game id provided does not exist")
def test_bad_game_id():
    """Test if the scraper fails if a bad game id is provided."""
    # Catch the error here
    result = scrape_game(2021020000)
    
    assert result is None


def test_number_of_games_in_season():
    """Ensure the correct number of games in a season."""
    n_games, season_type = get_number_of_games_in_season(2021, season_type="R")
    
    assert n_games == 1312
   
   
def test_games_on_date():
    """Ensure the correct games for a given date."""
    game_ids = get_game_ids_between_dates(start_date="2021-10-31", end_date="2021-10-31")
    
    assert isinstance(game_ids, list)
    assert min(game_ids) == 2021020127 
    assert max(game_ids) == 2021020131
    
    
def test_games_between_empty_dates():
    """Ensure the correct games between two dates."""
    game_ids = get_game_ids_between_dates(start_date="2021-01-01", end_date="2021-01-02")
    
    assert isinstance(game_ids, list)
    assert len(game_ids) == 0
    
    
def test_games_between_dates():
    """Ensure the correct games between two dates."""
    game_ids = get_game_ids_between_dates(start_date="2022-01-01", end_date="2022-01-02")
    
    assert isinstance(game_ids, list) 
    assert min(game_ids) == 2021020566 
    assert max(game_ids) == 2021020582
