import numpy as np
import pandas as pd
import re
from itertools import chain
from datetime import datetime
import requests
from selectolax.parser import HTMLParser
from pandera.typing import DataFrame, Series
from typing import Tuple, List


class GameHTML:
    """
    Extract information from the HTML report of an NHL game.
    
    Arguments:
        game_id: int, the id of the game, given as e.g. 2021020001.
        requests_session: optional, the session to use for scraping.
    
    Attributes:
        game_id: int, the id of the game.
        away_team: str, the name of the away team.
        home_team: str, the name of the home team.
        url: str, the url of the HTML report. One for play-by-play, and one for each home and away shifts.
        tree: selectolax.parser.HTMLParser, parser for the page content. One for each url.
        event_base: list, list of all nodes (from the tree) for each event in the game.
    
    Methods:
        get_event_data: retrieves the event data from the game.
        get_shifts: retrieves all shifts from the home or away team.
    
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
        self.pbp_url = self.__get_url(game_id, report_type="PL")
        self.home_shifts_url = self.__get_url(game_id, report_type="TH")
        self.away_shifts_url = self.__get_url(game_id, report_type="TV")

        # Save the parsed HTML tree
        self.pbp_tree = self.__parse_url(requests_session, report_type="PL")
        self.home_shifts_tree = self.__parse_url(requests_session, report_type="TH")
        self.away_shifts_tree = self.__parse_url(requests_session, report_type="TV")

        # Extract the event base from the HTML
        self.event_base = self.__get_event_base()

        # Get team names
        team_names = self.__get_team_names()

        # Add home and away team names    
        self.away_team = team_names[0]
        self.home_team = team_names[1]

        # Get and set the game info
        self.game_date = self.__get_game_info()

        
    def __get_url(self, game_id: int, report_type: str="PL") -> str:
        """ Get the url used for retrieving data. """
        
        if report_type not in ["PL", "TH", "TV"]:
            raise ValueError("The report type is not supported.")
        
        # Extract season
        season = int(f"{game_id}"[:4])

        # Convert the season name to season-season+1
        season_full = f"{season}{season+1}"

        # Extract the unique identifying features of the game
        game_id_short = f"{game_id}"[5:]

        # Specify the url
        url = f"https://www.nhl.com/scores/htmlreports/{season_full}/{report_type}0{game_id_short}.HTM"

        return url


    def __parse_url(self, requests_session: requests.sessions.Session, report_type: str="PL") -> HTMLParser:
        """ Parse the url."""
        
        if report_type == "PL":
            url = self.pbp_url
        elif report_type == "TH":
            url = self.home_shifts_url
        elif report_type == "TV":
            url = self.away_shifts_url
        else:
            raise ValueError("The report type is not supported.")
        
        # Retrieve the page
        page = requests_session.get(url)

        if page.status_code == 404:
            raise ValueError("The webpage does not exist.")

        # Parse the content on the page
        tree = HTMLParser(page.content)

        return tree


    def __get_team_names(self) -> List:
        """ Get the away and home teams in the game. """
        # Get the nodes satisfying the condition
        parsed_tree = self.pbp_tree.css("tr > td[class^=heading]")
        
        # Get all teams in the game
        teams = [node.text() for node in parsed_tree if "On Ice" in node.text()][:2]
        
        # Keep only the team acronym
        teams = [team[:3] for team in teams]
        
        return teams


    def __get_game_info(self) -> Tuple[int, str]:
        """ Get the about-game information from the game. """
        
        # Get the game info
        game_info = self.pbp_tree.css("table[id=GameInfo]")[0].text()

        # Remove whitespace
        game_info = re.sub("\xa0|\n", " ", game_info)

        # Remove unwanted info
        game_info = re.sub("\s+Play By Play\s+|Start[\s\S]+", "", game_info)

        # Get the date of the game (as a string)
        try:
            game_date = re.findall("(?<=,)[\s\S]+(?=Attendance)", game_info)[0].strip()
        except IndexError:
            game_date = np.nan

        try:
            # Convert the game from a string to an integer
            game_date_int = datetime.strftime(datetime.strptime(game_date, "%B %d, %Y"), "%Y%m%d")
        except TypeError:
            game_date_int = 0
        
        return game_date_int


    def __get_event_base(self) -> List:
        """ Get list of all nodes with all events, i.e., starts with id=PL. """
        
        # Get the event base from the newest seasons
        event_base = self.pbp_tree.css("tr[id^=PL]")
        
        if int(str(self.game_id)[:4]) < 2021 or len(event_base) == 0:
            # Search for color rather than id if id does not exist
            event_base = self.pbp_tree.css("tr[class$=Color]")
                       
            # If there are not id given for each node, create one.
            for idx, event in enumerate(event_base):
                event.attrs["id"] = f"PL-{idx+1}"
        
        return event_base


    def _get_event_number(self) -> np.ndarray:
        """ Get the event number from the event nodes. """
        
        # Extract event number
        event_number_list = [int(re.sub("PL-", "", event.id))
                             if bool(re.search("(?<=\n)\d+(?=\n\d)", event.text())) else 1
                             for event in self.event_base]

        return np.array(event_number_list)


    def _get_period_number(self) -> np.ndarray:
        """ Get the period number from the event nodes. """
        
        # Extract period number
        period_number_list = [int(re.findall("(?<=\d\n)\d(?=\n)", event.text())[0])
                              if bool(re.search("(?<=\d\n)\d(?=\n)", event.text())) else 1
                              for event in self.event_base]

        return np.array(period_number_list)


    def _get_event_manpower(self) -> np.ndarray:
        """ Get the manpower from the event nodes."""
        
        # Extract manpower situation
        event_manpower_list = [re.findall("(?<=\d\n)[A-z]+(?=\n\d)", event.text())
                               for event in self.event_base]
        
        # Convert to string representation
        event_manpower_list = [event[0] if len(event) > 0 else np.nan 
                               for event in event_manpower_list]

        return np.array(event_manpower_list, dtype=object)


    def _get_event_time(self) -> np.ndarray:
        """ Get the event time from the event nodes."""
        
        # Extract the time of each event
        event_time_list = [re.findall("(?<=[A-z]\n)\d+:\d{2}(?=\d)|(?<=\xa0\n)\d+:\d{2}(?=\d)", 
                                      event.text())
                           for event in self.event_base]
        
        # Convert to string representation
        event_time_list = [event[0] if len(event) > 0 else np.nan 
                           for event in event_time_list]

        return np.array(event_time_list, dtype=object)


    def _get_event_type(self) -> np.ndarray:
        """ Get the event type from the event nodes."""
        
        # Extract the type of event
        event_type_list = [re.findall("(?<=:\d{2}\n)[A-z]+(?=\n)", event.text())
                           for event in self.event_base]

        # Convert to string representation
        event_type_list = [event[0] if len(event) > 0 else np.nan 
                           for event in event_type_list]

        return np.array(event_type_list, dtype=object)


    def _get_event_description(self) -> np.ndarray:
        """ Get the description from the event nodes. """
        
        # Extract the description of each event
        event_description_list = [re.findall("(?<=[A-z]\n)[A-z]+.+(?=\n)", 
                                             re.sub("\xa0", " ", event.text()))
                                  for event in self.event_base]

        # Convert to string representation
        event_description_list = [event[0] if len(event) > 0 else np.nan 
                                  for event in event_description_list]

        return np.array(event_description_list, dtype=object)


    def _get_event_team(self, event_description_list: np.ndarray) -> Series:
        """ Get the team of the event from the event description."""
        
        # Get only the first team of the event
        event_team_list = [re.findall("(?<=^)[A-Z]{3}(?=\s)|(?<=^)[A-Z]\.[A-Z](?=\s)", 
                                       re.sub("HIT", "", description))
                            if not isinstance(description, float) else np.nan
                            for description in event_description_list]
        
        # Convert to string representation
        event_team_list = [event[0] if not isinstance(event, float) and 
                            len(event) > 0 else np.nan 
                            for event in event_team_list]
        
        return pd.Series(event_team_list, name="Team")
    
    
    def _get_event_players(self, event_description_list: np.ndarray) -> Series:
        """ Get the players involved in the event from the event description."""
    
        # Get all players who were involved
        event_players_list = [re.findall("\#\d+ [\w+'-]+", description)
                              if not isinstance(description, float) else np.nan
                              for description in event_description_list]
        
        return pd.Series(event_players_list, name="Players")


    def _get_event_zone(self, event_description_list: np.ndarray) -> Series:
        """ Get the zone from the event description."""
    
        # Get the zone of the event
        event_zone_list = [re.findall("[A-z]{3}(?=\. Zone)", description)
                              if not isinstance(description, float) else np.nan
                              for description in event_description_list]
        
        # Convert to string representation
        event_zone_list = [event[0] if not isinstance(event, float) and 
                           len(event) > 0 else np.nan 
                           for event in event_zone_list]
        
        return pd.Series(event_zone_list, name="Zone")


    def _get_event_shot_type_and_distance(self, event_description_list: np.ndarray) -> Tuple[Series, Series]:
        """ Get the shot type and distance of the event from the event description."""
                
        # Get the shot type for all shots
        event_shot_type_list = [re.findall("(?<=, )[A-z]+(?=,)|(?<=, )[A-z]+-[A-z]+(?=,)", 
                                           re.sub("Goalpost", "", description))
                                if not isinstance(description, float) else np.nan
                                for description in event_description_list]
        
        # Get the shot distance
        event_shot_distance_list = [re.findall("\d+(?= ft.)", description)
                                    if not isinstance(description, float) else np.nan
                                    for description in event_description_list]
        
        # Convert to string representation
        event_shot_type_list = [event[0] if not isinstance(event, float) and 
                                len(event) > 0 else np.nan 
                                for event in event_shot_type_list]
        
        # Convert to numeric representation
        event_shot_distance_list = [float(event[0]) if not isinstance(event, float) and 
                                    len(event) > 0 else np.nan 
                                    for event in event_shot_distance_list]
        
        return (pd.Series(event_shot_type_list, name="ShotType"), 
                pd.Series(event_shot_distance_list, name="ShotDistance"))

    
    def _get_event_penalty(self, event_description_list: np.ndarray) -> Tuple[Series, Series]:
        """ Get the name of the penalty and its duration from the event description."""
        
        # Get all penalties, inlcuding type and severity
        event_penalty_list = [re.findall("(?<=[A-Z] ).+\(\d+ min\)(?=,)|(?<=[A-Z] ).+\(\d+ min\)",
                                         re.sub("\#\d+ [\w+'-]+| Served By:\s+| [A-Z]+(?=, [A-z]{3}\. Zone)", "",
                                                re.sub("\xa0", " ", event)))
                              if not isinstance(event, float) and len(event) > 0 else np.nan 
                              for event in event_description_list]
        
        # Get the name of the penalty type
        event_penalty_name_list = [re.sub("\([\s\S]+\)|[A-Z]+ (?=[A-Z][a-z]+)|\#", "", 
                                          event[0].strip()).strip()
                                   if not isinstance(event, float) and 
                                   len(event) > 0 else np.nan 
                                   for event in event_penalty_list]
        
        # Get the duration of the penalty
        event_penalty_duration_list = [re.sub("[\s\S]+\(|\)", "", event[0].strip()) 
                                       if not isinstance(event, float) and 
                                       len(event) > 0 else np.nan 
                                       for event in event_penalty_list]
        
        return (pd.Series(event_penalty_name_list, name="PenaltyType"), 
                pd.Series(event_penalty_duration_list, name="PenaltyMinutes"))


    def _penalty_shot_bool(self, event_description_list: np.ndarray) -> Series:
        """ Determine if there were any penalty shots from the event description."""
        
        # Get all penalties, inlcuding type and severity
        event_penalty_shot_list = [bool(re.search("Penalty Shot", event))
                                   if not isinstance(event, float) and len(event) > 0 else False
                                   for event in event_description_list]
        
        return pd.Series(event_penalty_shot_list, name="PenaltyShot")


    def _get_team_players(self, idx_to_drop: np.ndarray, home: bool=True) -> Tuple[np.ndarray, dict,
                                                                                   pd.Series]:
        """ Get the players from the home/away team on the ice. """
        
        # Clone the original tree
        tree_copy = self.pbp_tree.clone()
        
        # Loop over all ids to drop
        for idx in idx_to_drop:
            # Find the matching node
            for tag in tree_copy.css(f"tr[id=PL-{idx+1}]"):
                # Remove nodes that does not have players on the ice
                tag.decompose()
                
        # Get the event base of the new tree
        new_event_base = tree_copy.css("tr[id^=PL]")

        # Specify the team selector
        team_css_selector = "td[class$=bborder]" if home else "td[class$=rborder]"

        # Get all the nodes which may contain players from the team
        player_nodes = [event.css(team_css_selector)
                        for event in new_event_base]
        
        # Get all the nodes that contain players from the team
        player_nodes = [[node.css("font[style=\"cursor:hand;\"]") 
                         for node in node_list if 
                         node.css_matches("font[style=\"cursor:hand;\"]")][0]
                        for node_list in player_nodes]
        
        # Remove all players who do not have the attribute "title"
        players = [[player for player in player_list if 
                    "title" in player.attributes] for 
                   player_list in player_nodes]
                    
        # Get all player names and positions
        player_names = [[player.attributes["title"] if "title" in player.attributes
                         else re.findall("(?<=title=\")[\s\S]+(?=\">)", player.html)
                         for player in player_list] for
                        player_list in players]

        # Create a nested tuple of (# LAST NAME, FULL NAME)
        player_number_name = [[(f"#{player.text()} {player.attributes['title'].split(' - ')[1].split()[1]}", 
                                f"{player.attributes['title'].split(' - ')[1]}")
                               if bool(re.search("[A-Z]", player.attributes["title"])) else None
                               for player in player_list ] for
                              player_list in players]
        
        # Remove any None values
        for list_idx, player_list in enumerate(player_number_name):
            if None in player_list:
                # Only keep non None values
                player_list_new = [player for player in player_list if player is not None]
                
                # Overwrite the pre-existing list
                player_number_name[list_idx] = player_list_new
        
        # Flatten the list of lists and convert to a set
        unique_player_number_name = set(chain.from_iterable(player_number_name))

        # Create a dictionary of mappings from # LAST NAME to FULL NAME
        number_name_map = {item[0]: item[1] for item in unique_player_number_name}

        # Get all player positions
        player_positions = [[player.split(" - ")[0] for player in player_list] for
                            player_list in player_names]

        # Get all player names
        player_names = [[player.split(" - ")[1] for player in player_list] for
                        player_list in player_names]

        # Check if the goalie was on the ice
        goalie_on_ice = ["Goalie" in player_list for player_list
                         in player_positions]
        
        # Find the goalie name for the team (if available)
        goalie_name = [np.array(name_list)[np.where([position == "Goalie" for position
                                                     in position_list])[0]]
                       for name_list, position_list in zip(player_names, player_positions)]
        
        # Convert to string representation
        goalie_name = [name[0] if len(name) > 0 else np.nan for name in goalie_name]
        
        # Determine the name of the series indicating if the goalie was on the ice
        side = "Home" if home else "Away"

        return (np.array(player_names, dtype=object), number_name_map, 
                pd.Series(goalie_name, name=f"{side}GoalieName"),
                pd.Series(goalie_on_ice, name=f"{side}GoalieOnIce"))

        
    def _expand_column_of_list(self, array: np.ndarray, column_name: str) -> DataFrame:
        """
        Expand a column that has list elements to multiple columns, each containing
        a unique element from the list. The columns are renamed as 'column_nameN' 
        where N is the number of columns 1, 2, ...
        """
        
        # Remove None if it exists
        column_series = pd.Series([[] if obj is None or isinstance(obj, float) 
                                   else obj for obj in array])
        
        # Expand the column of list to be one item per column
        column_df = pd.DataFrame(column_series.tolist())
        
        # Rename columns
        column_df.columns = [f"{column_name}{i}" for i in range(1, len(column_df.columns)+1)]
        
        return column_df


    def _define_player_roles(self, event_type_list: np.ndarray, players_involved: DataFrame) -> DataFrame:
        """ Define the player roles. """
        
        # Copy to avoid changing in-place
        players_involved = players_involved.copy()
        
        # Combine event and players involved
        event_type_series = pd.Series(event_type_list, name="EventType")        

        # Compute the number of players for each event
        nr_players_per_event = players_involved.notna().sum(axis=1)

        # Define the first player role
        players_involved["PlayerType1"] = np.select(
            [event_type_series.eq("FAC"),
             event_type_series.eq("HIT"),
             event_type_series.isin(["TAKE", "GIVE"]),
             event_type_series.isin(["SHOT", "BLOCK", "MISS"]),
             event_type_series.eq("GOAL"),
             event_type_series.eq("PENL")],
            ["Winner", "Hitter", "PlayerId", "Shooter", "Scorer", "PenaltyOn"],
            default=np.nan)

        # Define the second player role
        players_involved["PlayerType2"] = np.select(
            [event_type_series.eq("FAC")   & nr_players_per_event.eq(2),
             event_type_series.eq("HIT")   & nr_players_per_event.eq(2),
             event_type_series.eq("BLOCK") & nr_players_per_event.eq(2),
             event_type_series.eq("GOAL")  & nr_players_per_event.ge(2),
             event_type_series.eq("PENL")  & nr_players_per_event.ge(2)],
            ["Loser", "Hittee", "Blocker", "Assist", "DrewBy"],
            default=np.nan)
        
        # Define the third player role
        players_involved["PlayerType3"] = np.select(
            [event_type_series.eq("GOAL") & nr_players_per_event.eq(3),
             event_type_series.eq("PENL") & nr_players_per_event.eq(3)],
            ["Assist", "ServedBy"],
            default=np.nan)
        
        return players_involved


    def _map_team_tri_to_names(self) -> dict:
        """ Map a team's tri code to their full team name """
        
        # Create the mapping
        tri_to_team_map = {
            "ANA": "Anaheim Ducks",
            "ARI": "Arizona Coyotes",
            "ATL": "Atlanta Thrashers",
            "BOS": "Boston Bruins",
            "BUF": "Buffalo Sabres",
            "CGY": "Calgary Flames" ,
            "CAR": "Carolina Hurricanes",
            "CHI": "Chicago Blackhawks" ,
            "COL": "Colorado Avalanche",
            "CBJ": "Columbus Blue Jackets",
            "DAL": "Dallas Stars",
            "DET": "Detroit Red Wings",
            "EDM": "Edmonton Oilers" ,
            "FLA": "Florida Panthers",
            "L.A": "Los Angeles Kings",
            "LAK": "Los Angeles Kings",
            "MIN": "Minnesota Wild",
            "MTL": "Montréal Canadiens",
            "NSH": "Nashville Predators",
            "N.J": "New Jersey Devils",
            "NJD": "New Jersey Devils",
            "NYI": "New York Islanders",
            "NYR": "New York Rangers",
            "OTT": "Ottawa Senators",
            "PHI": "Philadelphia Flyers",
            "PHX": "Phoenix Coyotes",
            "PIT": "Pittsburgh Penguins",
            "S.J": "San Jose Sharks",
            "SJS": "San Jose Sharks",
            "SEA": "Seattle Kraken",
            "STL": "St. Louis Blues",
            "T.B": "Tampa Bay Lightning",
            "TBL": "Tampa Bay Lightning",
            "TOR": "Toronto Maple Leafs",
            "VAN": "Vancouver Canucks",
            "VGK": "Vegas Golden Knights",
            "WSH": "Washington Capitals",
            "WPG": "Winnipeg Jets"
            }
        
        return tri_to_team_map


    def _add_events_without_players_on_ice(self, idx_to_drop: np.ndarray, 
                                           event_number_list: np.ndarray,
                                           period_number_list: np.ndarray,
                                           event_manpower_list: np.ndarray,
                                           event_time_list: np.ndarray,
                                           event_type_list: np.ndarray,
                                           event_description_list: np.ndarray
                                           ) -> DataFrame:
        """ Add the events where there are no players on the ice but an 
            event description is still available. """
            
        # Find the entries which are not nan
        non_nan_entries = np.where([isinstance(event, str) for event in 
                                    event_description_list[idx_to_drop]])[0]
        
        # Get the indexes of events which have a description
        non_na_idx = idx_to_drop[non_nan_entries]
        
        # The events where the players are missing and an event description is available
        missing_players_df = pd.DataFrame([event_number_list[non_na_idx],
                                           period_number_list[non_na_idx],
                                           event_manpower_list[non_na_idx],
                                           event_time_list[non_na_idx],
                                           event_type_list[non_na_idx],                                                
                                           event_description_list[non_na_idx]],
                                          index=["EventNumber", "PeriodNumber", 
                                                 "Manpower", "EventTime", 
                                                 "EventType", "Description"]).T
        
        return missing_players_df


    def get_event_data(self) -> DataFrame:
        """ Get all events from the HTML RTSS report. """
        
        # Get the game metadata
        meta_data = (self.game_id, self.away_team, self.home_team, self.game_date)
        
        # Get the event and period numbers
        event_number_list = self._get_event_number()
        period_number_list = self._get_period_number()
        
        # Get the manpower situation
        event_manpower_list = self._get_event_manpower()
        
        # Get the time of the event
        event_time_list = self._get_event_time()
        
        # Get the type of event
        event_type_list = self._get_event_type()
        
        # Get the description of the event
        event_description_list = self._get_event_description()
        
        # Find the events to keep (i.e., events with players on ice)
        idx_to_keep = np.array([int(node.attributes["id"].split("-")[1]) for node in self.event_base if 
                                # If the away team has players for the given node
                                bool(re.search("bborder \+ rborder\">\n<table", node.html)) and
                                # If the home team has players for the given node
                                bool(re.search("bborder\">\n<table", node.html))])-1

        # Find the events to drop as the non-intersection
        idx_to_drop = np.setxor1d(event_number_list-1, idx_to_keep)
        
        # Get all events where players are missing but event description is available
        missing_players_df = self._add_events_without_players_on_ice(idx_to_drop, event_number_list,
                                                                     period_number_list, event_manpower_list,
                                                                     event_time_list, event_type_list,
                                                                     event_description_list)
        
        # Get player names and positions for each team
        away_player_names, away_name_map, away_goalie_name, away_goalie_on_ice = self._get_team_players(idx_to_drop, home=False)
        home_player_names, home_name_map, home_goalie_name, home_goalie_on_ice = self._get_team_players(idx_to_drop, home=True)
        
        # Combine the home and away name maps into one dictionary
        name_map = {**away_name_map, **home_name_map}
        
        # Expand a column of list to multiple columns for player names
        away_player_names_df = self._expand_column_of_list(away_player_names, "AwayPlayer")
        home_player_names_df = self._expand_column_of_list(home_player_names, "HomePlayer")

        # Combine all events into one data frame
        events = pd.DataFrame([event_number_list[idx_to_keep], period_number_list[idx_to_keep], 
                               event_manpower_list[idx_to_keep], event_time_list[idx_to_keep], 
                               event_type_list[idx_to_keep], event_description_list[idx_to_keep]],
                              index=["EventNumber", "PeriodNumber", 
                                     "Manpower", "EventTime", 
                                     "EventType", "Description"]).T               

        # Combine events and players on the ice
        events_with_players_on_ice = pd.concat([events,
                                                away_player_names_df.reset_index(drop=True), 
                                                home_player_names_df.reset_index(drop=True),
                                                away_goalie_on_ice, 
                                                away_goalie_name,
                                                home_goalie_on_ice,
                                                home_goalie_name],
                                               axis=1)
       
        # Add events with missing players
        events_and_missing = pd.concat([events_with_players_on_ice, missing_players_df]).sort_values(
            "EventNumber").reset_index(drop=True)
        
        # Get the zone of the event
        event_zone_list = self._get_event_zone(events_and_missing.Description)

        # Get the teams in the event
        event_team_list = self._get_event_team(events_and_missing.Description)
        
        # Get the players involved in the event
        event_players_list = self._get_event_players(events_and_missing.Description)
        
        # Get the shot type
        event_shot_type_list, event_shot_distance_list = self._get_event_shot_type_and_distance(events_and_missing.Description)
        
        # Get penalty information
        event_penalty_name_list, event_penalty_duration_list = self._get_event_penalty(events_and_missing.Description)

        # Determine if there were any penalty shots
        event_penalty_shot_bool = self._penalty_shot_bool(events_and_missing.Description)
        
        # Expand a column of list to multiple columns for team and involved players
        players_involved = self._expand_column_of_list(event_players_list, "Player")

        # Rename from # LAST NAME to FULL NAME
        players_involved.replace(name_map, inplace=True)

        # Define player roles
        players_involved = self._define_player_roles(events_and_missing.EventType, players_involved)
        
        # Combine events with all information regarding players, teams etc.
        events_with_all_info = pd.concat([events_and_missing, event_team_list, 
                                          players_involved, event_zone_list, 
                                          event_shot_type_list, event_penalty_shot_bool, 
                                          event_penalty_name_list, event_penalty_duration_list],
                                         axis=1)
        
        # Repeat meta data to match the length of the data
        meta_data_df = pd.DataFrame(np.repeat([meta_data], len(events_with_all_info), axis=0),
                                     columns=["GameId", "AwayTeamName", "HomeTeamName",
                                              "Date"])
        
        # Map team tri code to team name
        meta_data_df.AwayTeamName.replace(self._map_team_tri_to_names(), inplace=True)
        meta_data_df.HomeTeamName.replace(self._map_team_tri_to_names(), inplace=True)
        
        # Add meta data to the data frame
        pbp = pd.concat([meta_data_df, events_with_all_info], axis=1)
        
        # Map team to full name
        pbp.Team.replace(self._map_team_tri_to_names(), inplace=True)
             
        # Change data type to integer 
        pbp["Date"] = pbp.Date.astype(int)
        pbp["EventNumber"] = pbp.EventNumber.astype(int)
        pbp["PeriodNumber"] = pbp.PeriodNumber.astype(int)
                
        # Convert penalty minutes to an integer
        pbp["PenaltyMinutes"] = pbp.PenaltyMinutes.astype(str).str.replace(" min", "").astype(float)  
        
        # Reduce event number by 2 to account for the extra events before the game
        if pbp.iloc[0].EventType == "PGSTR":
            pbp["EventNumber"] -= 2
        
        # Adjust event number of later periods to account for additional events between periods
        for period_number in pbp.loc[pbp.PeriodNumber.gt(1)].PeriodNumber.unique():
            pbp.loc[pbp.PeriodNumber.eq(period_number), "EventNumber"] += 2 * (period_number - 1)
        
        # Find all delayed penalties and unusual events/double stoppage for a challenge
        unusual = (pbp.EventType.isin(["DELPEN", "EGT"]) |
                   (pbp.EventType.eq("STOP") & pbp.EventType.shift(-1).eq("CHL") &
                    pbp.EventType.shift(-2).eq("STOP")))
        
        if any(unusual) > 0:
            # Get the unusual events event numbers
            unusual_event_numbers = pbp.loc[unusual, "EventNumber"].values
            
            # Add the final event number to the array
            unusual_event_numbers = np.concatenate((unusual_event_numbers, 
                                                    np.array([pbp.EventNumber.max()])))
            
            for idx, event_number in enumerate(unusual_event_numbers[1:]):
                # Get the event number of the previous unsual event
                previous_event_number = unusual_event_numbers[idx]
                
                # Find the event number that need to be adjusted
                event_number_to_change = (pbp.EventNumber.gt(previous_event_number) &
                                          pbp.EventNumber.le(event_number))
                
                # Reduce the event number by 1
                pbp.loc[event_number_to_change, "EventNumber"] -= 1 * (idx + 1)
            
            # Remove delayed penalties and unusual events
            pbp = pbp.loc[~unusual].copy()
        
        # All penalties served by another player
        serving_penalties = (pbp.EventType.eq("PENL") &
                             pbp.Description.astype(str).str.contains("Served By"))
        
        # Add missing column if needed
        if "Player3" not in pbp.columns:
            pbp["Player3"] = np.nan
            pbp["PlayerType3"] = np.nan
            
        # Switch player names as they are incorrect when a third player serves the penalty
        pbp.loc[serving_penalties & pbp.PlayerType3.ne("nan"), 
                       ["Player3", "Player2"]] = \
        pbp.loc[serving_penalties & pbp.PlayerType3.ne("nan"), 
                       ["Player2", "Player3"]].values
        
        # For players serving the penalty of a goalie
        pbp.loc[serving_penalties & pbp.PlayerType3.eq("nan") & 
                pbp.PlayerType2.ne("nan"), "PlayerType2"] = "ServedBy"
        
        # For players serving a team penalty
        pbp.loc[serving_penalties & pbp.PlayerType3.eq("nan") & 
                pbp.PlayerType2.eq("nan"), "PlayerType1"] = "ServedBy"
            
        # Determine the winner of faceoffs
        faceoff_winning_team = pbp.loc[ pbp.EventType.eq("FAC"), "Description"].str.extract(
                "(^[A-Z]{3})", expand=False).replace(self._map_team_tri_to_names())
                
        # Switch the order of players if the home team won the faceoff
        pbp.loc[faceoff_winning_team.eq(pbp.HomeTeamName),
                       ["Player1", "Player2"]] = \
        pbp.loc[faceoff_winning_team.eq(pbp.HomeTeamName),
                       ["Player2", "Player1"]].values
        
        # Find all the columns with players on the ice
        player_columns = pbp.columns[pbp.columns.str.contains(
            "[HomeAway]Goalie|[HomeAway]Player\d")]
        
        # Reorder the columns in the data to have players on the ice at the end
        pbp = pd.concat([pbp.drop(player_columns, axis=1), 
                                pbp[player_columns]], axis=1)

        # Find columns that should not exist/are erroneous
        erroneous_cols = pbp.columns[pbp.columns.str.contains("\d{2}|^Player4", regex=True)]
        
        # Remove the erroneous columns
        pbp.drop(erroneous_cols, axis=1, inplace=True)
        
        # Fill NA time values with a placeholder
        pbp.EventTime.fillna("20:00", inplace=True)
        
        # Add total elapsed time
        pbp["TotalElapsedTime"] = 1200 * (pbp["PeriodNumber"] - 1) + [
            60 * int(x[0]) + int(x[1]) for x in pbp["EventTime"].str.split(":")
            ]

        # Rename events
        pbp.EventType.replace({
            "FAC": "FACEOFF", "STOP": "STOPPAGE", "CHL": "CHALLENGE",
            "GEND": "GAME END", "PSTR": "PERIOD START", "PEND": "PERIOD END",
            "GIVE": "GIVEAWAY", "TAKE": "TAKEAWAY", "PENL": "PENALTY",
            "MISS": "MISSED SHOT", "BLOCK": "BLOCKED SHOT"}, inplace=True)
    
        return pbp


    def get_shifts(self, home: bool=True):
        """ Get all shifts from the given game. """
        
        # Determine the team perspective
        if home: 
            tree = self.home_shifts_tree
        else:
            tree = self.away_shifts_tree
            
        # Get all nodes with player number and names
        player_names_css = tree.css("tr > td[class~=playerHeading]")
        
        # Extract player names
        player_names = [re.sub("\d+ ", "", re.findall("(?<=\>).+(?=\</)", player.html)[0]) 
                        for player in player_names_css]
        
        # Switch order of first and last names
        player_names = [f"{re.findall('(?<=, ).+', player)[0]} {re.findall('.+(?=, )', player)[0]}"
                        for player in player_names]
        
        # Find all shifts
        shifts = tree.css("tr[class$=Color]")
        
        # Extract shift information for each shift
        shift_info = [shift.css("[class$=border]") for shift in shifts]
        
        # Extract the text from the shift information
        shift_info_text = [[re.findall("(?<=\>).+(?=\</)", s.html) for s in shift] for shift in shift_info]
        
        # Simplify the nest list structure
        shift_info_text = [[attr[0] if len(attr) > 0 else [] for attr in shift] for shift in shift_info_text] 
        
        # Create a data frame of the shifts
        shifts = pd.DataFrame(shift_info_text, 
                              columns=["ShiftNumber", "PeriodNumber",
                                       "ShiftStart", "ShiftEnd", 
                                       "Duration", "Event"]).dropna().reset_index(drop=True)
        # Change column types
        cols = ["ShiftNumber", "PeriodNumber"]
        shifts[cols] = shifts[cols].astype(int)
        
        # Create a grouping to indiciate unique players
        shifts["PlayerNr"] = (shifts.ShiftNumber != shifts.ShiftNumber.shift() + 1).cumsum()
        
        # Create a mapping from plyer nr to player name
        player_mapping = {nr: player for nr, player in zip(shifts["PlayerNr"].unique(), player_names)}
        
        # Insert the new column with player name
        shifts.insert(0, "Player", shifts["PlayerNr"].replace(player_mapping))   
        
        # Remove unwanted text
        shifts.replace("&nbsp;|\s/\s.+", "", regex=True, inplace=True)
        
        # Convert time columns to seconds
        shifts["ShiftStart"] = [int(minute) * 60 + int(second) for minute, second in 
                                shifts["ShiftStart"].str.split(":")]
        shifts["ShiftEnd"] = [int(minute) * 60 + int(second) for minute, second in 
                              shifts["ShiftEnd"].str.split(":")]
        shifts["Duration"] = [int(minute) * 60 + int(second) for minute, second in 
                              shifts["Duration"].str.split(":")]   
        
        # Add period number offsets
        shifts["ShiftStart"] = (1200 * (shifts["PeriodNumber"] - 1)) + shifts["ShiftStart"] 
        shifts["ShiftEnd"]   = (1200 * (shifts["PeriodNumber"] - 1)) + shifts["ShiftEnd"] 
        
        # Insert game id and team
        shifts.insert(0, "GameId", self.game_id)   
        shifts.insert(2, "TeamName", self.home_team if home else self.away_team)   

        # Map team name tri-code to full name
        shifts["TeamName"] = shifts["TeamName"].replace(self._map_team_tri_to_names())
        
        shifts.drop("PlayerNr", axis=1, inplace=True)
        
        return shifts
    