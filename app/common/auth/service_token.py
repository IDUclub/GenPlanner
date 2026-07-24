from idu_service_auth import KeycloakTokenClient, KeycloakTokenConfig
from iduconfig import Config

from app.common.config_utils import get_optional_config


def build_keycloak_token_client(config: Config) -> KeycloakTokenClient | None:
    """
    Build the Keycloak client_credentials token client used for service-to-service
    calls (e.g. to ChatStorage). Returns None if Keycloak isn't configured, so chat
    history persistence can be disabled by simply leaving KEYCLOAK_* empty.
    """

    auth_server_url = get_optional_config(config, "KEYCLOAK_URL")
    realm = get_optional_config(config, "KEYCLOAK_REALM")
    client_id = get_optional_config(config, "KEYCLOAK_CLIENT_ID")
    client_secret = get_optional_config(config, "KEYCLOAK_CLIENT_SECRET")

    if not (auth_server_url and realm and client_id and client_secret):
        return None

    keycloak_config = KeycloakTokenConfig(
        auth_server_url=auth_server_url,
        realm=realm,
        client_id=client_id,
        client_secret=client_secret,
        scope=get_optional_config(config, "KEYCLOAK_SCOPE"),
    )
    return KeycloakTokenClient(keycloak_config)
