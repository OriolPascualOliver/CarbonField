from app.services.meteo_service import get_meteo_service


def get_xema_client():
    """Wrapper for legacy XEMA pipeline calls.

    When XEMA is unavailable, this returns the Open-Meteo based meteo service.
    """
    return get_meteo_service()
