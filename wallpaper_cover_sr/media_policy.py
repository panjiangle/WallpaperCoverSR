"""Source selection has no knowledge of wallpapers, packages or layer layouts."""
APP_ID = 'WallpaperCoverSR'


def is_own_session(app_id):
    return 'wallpapercoversr' in app_id.casefold()


def choose_source(sources, current_id='', previous_id='', preferred_id=''):
    eligible = [s for s in sources if not is_own_session(s['id']) and not s.get('closed', False)]
    by_id = {s['id']: s for s in eligible}
    if preferred_id:
        return preferred_id if preferred_id in by_id else None
    if current_id in by_id:
        return current_id
    playing = [s for s in eligible if s.get('playing', False)]
    if previous_id in by_id and (by_id[previous_id].get('playing') or not playing):
        return previous_id
    if playing:
        return next((s['id'] for s in playing if 'cloudmusic' in s['id'].lower()), playing[0]['id'])
    return next((s['id'] for s in eligible if 'cloudmusic' in s['id'].lower()), eligible[0]['id'] if eligible else None)
