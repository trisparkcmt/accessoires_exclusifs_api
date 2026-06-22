import threading

_thread_locals = threading.local()

def get_current_user():
    """Récupère l'utilisateur connecté à l'origine de la requête en cours."""
    user = getattr(_thread_locals, 'user', None)
    if user and user.is_authenticated:
        return user
    return None

class CurrentUserMiddleware:
    """Middleware pour capturer l'utilisateur connecté dans chaque thread de requête."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        try:
            response = self.get_response(request)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
        return response
