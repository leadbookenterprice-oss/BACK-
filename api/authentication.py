from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken


class JWTAuthenticationFromQueryParam(JWTAuthentication):
    """
    Extiende JWTAuthentication para aceptar el token también
    desde el query param ?token=... además del header Authorization.
    Útil para descargas directas del browser (window.location.href).
    """
    def authenticate(self, request):
        # Primero intentar autenticación por header (comportamiento estándar)
        header_result = super().authenticate(request)
        if header_result:
            return header_result

        # Fallback: intentar desde query param ?token=...
        token_str = request.GET.get('token')
        if not token_str:
            return None

        try:
            validated = self.get_validated_token(token_str.encode())
            user = self.get_user(validated)
            return (user, validated)
        except (TokenError, InvalidToken):
            return None
