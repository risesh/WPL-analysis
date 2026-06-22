def build_player_map(all_player_names, kaggle_profiles=None):
    """
    Returns {abbrev_name: {full_name, image_url, country, ...}} for every player.
    Data comes entirely from kaggle_profiles (player_profiles.json built by kaggle_data.py).
    Players absent from kaggle_profiles fall back to abbreviated name with no image.
    """
    kaggle_profiles = kaggle_profiles or {}
    player_map = {}
    for name in set(all_player_names):
        if not name:
            continue
        if name in kaggle_profiles:
            kp = kaggle_profiles[name]
            player_map[name] = {
                "full_name": kp.get("full_name") or name,
                "image_url": kp.get("image_url"),
                "country": kp.get("country"),
                "batting_style": kp.get("batting_style"),
                "bowling_style": kp.get("bowling_style"),
                "playing_role": kp.get("playing_role"),
            }
        else:
            player_map[name] = {
                "full_name": name,
                "image_url": None,
                "country": None,
                "batting_style": None,
                "bowling_style": None,
                "playing_role": None,
            }
    return player_map
