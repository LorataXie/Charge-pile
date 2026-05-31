from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_user_service, get_current_user, get_current_admin
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, MessageResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/auth", tags=["用户认证"])


@router.post("/register", response_model=TokenResponse)
async def register(req: UserRegister, svc: UserService = Depends(get_user_service)):
    if req.role == "admin":
        raise HTTPException(status_code=403, detail="管理员账号只能由后端创建")
    try:
        user = await svc.register(req.username, req.password, req.role)
        token = svc._create_token(user)
        return TokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register-admin", response_model=MessageResponse)
async def register_admin(
    req: UserRegister,
    current_user: dict = Depends(get_current_admin),
    svc: UserService = Depends(get_user_service),
):
    try:
        await svc.register(req.username, req.password, "admin")
        return MessageResponse(message=f"管理员 {req.username} 创建成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(req: UserLogin, svc: UserService = Depends(get_user_service)):
    try:
        token = await svc.login(req.username, req.password)
        return TokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    svc: UserService = Depends(get_user_service),
):
    user = await svc.get_user(int(current_user["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user
