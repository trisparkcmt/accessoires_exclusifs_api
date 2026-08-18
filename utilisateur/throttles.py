import re

from rest_framework.throttling import SimpleRateThrottle


class ConfigurableRateThrottle(SimpleRateThrottle):
    """DRF throttle with support for rates like 5/15min or 1/2min."""

    duration_units = {
        's': 1,
        'sec': 1,
        'second': 1,
        'seconds': 1,
        'm': 60,
        'min': 60,
        'minute': 60,
        'minutes': 60,
        'h': 3600,
        'hour': 3600,
        'hours': 3600,
        'd': 86400,
        'day': 86400,
        'days': 86400,
    }

    def parse_rate(self, rate):
        if rate is None:
            return None, None

        num, period = rate.split('/')
        match = re.fullmatch(r'(?P<count>\d+)?(?P<unit>[a-zA-Z]+)', period.strip())
        if not match:
            return super().parse_rate(rate)

        count = int(match.group('count') or 1)
        unit = match.group('unit').lower()
        duration = count * self.duration_units[unit]
        return int(num), duration


def _normalize_identifier(value):
    if value is None:
        return ''
    return str(value).strip().lower()


class LoginIPThrottle(ConfigurableRateThrottle):
    scope = 'login_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class LoginCredentialThrottle(ConfigurableRateThrottle):
    scope = 'login_credential'

    def get_cache_key(self, request, view):
        credential = (
            request.data.get('email')
            or request.data.get('telephone')
            or request.data.get('username')
            or self.get_ident(request)
        )
        return self.cache_format % {
            'scope': self.scope,
            'ident': _normalize_identifier(credential),
        }


class RegisterIPThrottle(ConfigurableRateThrottle):
    scope = 'register_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class RegisterEmailThrottle(ConfigurableRateThrottle):
    scope = 'register_email'

    def get_cache_key(self, request, view):
        email = request.data.get('email') or self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': _normalize_identifier(email),
        }


class ResendEmailShortThrottle(ConfigurableRateThrottle):
    scope = 'resend_email_short'

    def get_cache_key(self, request, view):
        email = request.data.get('email') or self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': _normalize_identifier(email),
        }


class ResendEmailDailyThrottle(ConfigurableRateThrottle):
    scope = 'resend_email_daily'

    def get_cache_key(self, request, view):
        email = request.data.get('email') or self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': _normalize_identifier(email),
        }


class PasswordResetIPThrottle(ConfigurableRateThrottle):
    scope = 'password_reset_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class PasswordResetEmailThrottle(ConfigurableRateThrottle):
    scope = 'password_reset_email'

    def get_cache_key(self, request, view):
        email = request.data.get('email') or self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': _normalize_identifier(email),
        }


class ChangeEmailThrottle(ConfigurableRateThrottle):
    scope = 'change_email'

    def get_cache_key(self, request, view):
        user_ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': user_ident,
        }


class IARecommendationThrottle(ConfigurableRateThrottle):
    scope = 'ia_anon'

    def allow_request(self, request, view):
        self.scope = 'ia_user' if request.user and request.user.is_authenticated else 'ia_anon'
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }


# Alias français
IARecommandationThrottle = IARecommendationThrottle
