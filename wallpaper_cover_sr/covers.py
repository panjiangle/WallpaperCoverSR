"""Choose verified original artwork first, with the existing offline path as fallback."""
from . import backend, netease_artwork


def process(info, settings, cancelled=lambda: False):
    reason = ''
    if settings.get('prefer_hd', False):
        result, reason = netease_artwork.resolve(info, settings, cancelled)
        if result:
            return result
    result = dict(backend.process(info['data'], settings, cancelled))
    result['artwork_source'] = ('super-resolution' if result['output'] != result['input'] else 'system-original')
    if reason:
        result.update(hd_note=reason, hd_retry=True)
    return result
