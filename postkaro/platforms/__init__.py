"""The platform plug-ins, by name. Loaded lazily so the page starts even if one plug-in's library is
missing."""
import importlib

MODULES = {'youtube': 'postkaro.platforms.youtube', 'instagram': 'postkaro.platforms.meta',
           'facebook': 'postkaro.platforms.meta'}
CLASSES = {'youtube': 'YouTube', 'instagram': 'Instagram', 'facebook': 'Facebook'}
_cache = {}
OVERRIDE = {}          # tests put fake platforms here


def get(name):
    if name in OVERRIDE:
        return OVERRIDE[name]
    if name not in _cache:
        mod = importlib.import_module(MODULES[name])
        _cache[name] = getattr(mod, CLASSES[name])()
    return _cache[name]
