from iduconfig import Config


def get_optional_config(config: Config, key: str) -> str | None:
    """
    Read an env var that's allowed to be absent, unlike Config.get() which raises
    ValueError for a missing/empty key. Used for integrations that are optional by
    design -- e.g. chat history persistence, which stays off until Keycloak/ChatStorage/
    Ollama vars are actually configured.
    """

    try:
        value = config.get(key)
    except ValueError:
        return None
    return value or None
