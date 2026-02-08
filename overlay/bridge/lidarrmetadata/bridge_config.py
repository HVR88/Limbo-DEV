from lidarrmetadata.config import DefaultConfig, ConfigMeta
import six

class BridgeConfig(six.with_metaclass(ConfigMeta, DefaultConfig)):
    # Use your mirror's default credentials unless environment overrides exist
    PROVIDERS = {
        'MUSICBRAINZDBPROVIDER': ([], {
            'DB_HOST': 'db',
            'DB_PORT': 5432,
            'DB_USER': 'musicbrainz',
            'DB_PASSWORD': 'musicbrainz',
        }),
        'SOLRSEARCHPROVIDER': ([], {
            'SEARCH_SERVER': 'http://search:8983/solr',
        }),
        'FANARTTVPROVIDER': ([DefaultConfig.FANART_KEY], {}),
        'THEAUDIODBPROVIDER': ([DefaultConfig.TADB_KEY], {}),
        'WIKIPEDIAPROVIDER': ([], {}),
        'SPOTIFYAUTHPROVIDER': ([], {
            'CLIENT_ID': DefaultConfig.SPOTIFY_ID,
            'CLIENT_SECRET': DefaultConfig.SPOTIFY_SECRET,
            'REDIRECT_URI': DefaultConfig.SPOTIFY_REDIRECT_URL
        }),
        'SPOTIFYPROVIDER': ([], {
            'CLIENT_ID': DefaultConfig.SPOTIFY_ID,
            'CLIENT_SECRET': DefaultConfig.SPOTIFY_SECRET
        }),
    }

    USE_CACHE = True
    ENABLE_STATS = False
