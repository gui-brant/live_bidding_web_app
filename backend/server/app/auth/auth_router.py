from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from .auth_deps import get_auth_service, get_token_from_request
from .auth_schemas import ErrorResponse, OtpRequestIn, OtpVerifyIn, SafeProfile, TokenResponse
from .auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_attr(obj: object, name: str):
    # Works for dicts or objects.
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _build_safe_profile(user: object) -> SafeProfile:
    # Keep profile minimal and safe for frontend.
    user_id = _get_attr(user, "id") or _get_attr(user, "user_id") or _get_attr(user, "_id")
    email = _get_attr(user, "email")
    role = _get_attr(user, "role")
    if not user_id or not email or not role:
        raise AuthError(status_code=500, detail="User record missing required fields.", code="USER_INVALID")
    return SafeProfile(user_id=str(user_id), email=str(email), role=str(role))


@router.post(
    "/otp/request",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def request_otp(
    payload: OtpRequestIn,
    auth_service: AuthService = Depends(get_auth_service),
):
    # Always 204 to avoid leaking whether email exists.
    try:
        await auth_service.request_otp(payload.email)
    except Exception:
        # Always return 204 to prevent account enumeration.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

#verify and login here
@router.post(
    "/otp/verify",# this endpoint is the login endpoint: client exchanges OTP for JWT here, so we return 200 with token on success, and 401 on failure
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
)
async def verify_otp(
    payload: OtpVerifyIn,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    # Verify OTP, issue token, return safe profile.
    try:
        result = await auth_service.verify_otp(email=payload.email, code=payload.code)
    except AuthError as exc:
        error = ErrorResponse(detail=exc.detail, code=exc.code)
        return JSONResponse(status_code=exc.status_code, content=error.model_dump())

    profile = _build_safe_profile(result.user)
    jwt_settings = auth_service.jwt_settings
    access_token = None
    if jwt_settings.use_cookie:
        response.set_cookie(
            key=jwt_settings.cookie_name,
            value=result.access_token,
            httponly=True,
            secure=jwt_settings.cookie_secure,
            samesite=jwt_settings.cookie_samesite,
            max_age=result.expires_in,
            path=jwt_settings.cookie_path,
            domain=jwt_settings.cookie_domain,
        )
    else:
        access_token = result.access_token

    return TokenResponse(
        access_token=access_token,
        expires_in=result.expires_in,
        profile=profile,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    # Clear auth cookie and optionally blocklist token.
    token = get_token_from_request(request, settings=auth_service.jwt_settings)
    await auth_service.logout(token)
    response.delete_cookie(
        key=auth_service.jwt_settings.cookie_name,
        path=auth_service.jwt_settings.cookie_path,
        domain=auth_service.jwt_settings.cookie_domain,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
