import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
import uuid
from app.models.user import User, CreateUserRequest, LoginRequest, UserStatus
from app.core.database import db
from app.core.config import settings

class AuthService:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY or "your-secret-key-change-this"
        self.algorithm = "HS256"
        self.token_expire_hours = 24

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def create_access_token(self, user_id: str, username: str) -> str:
        """Create a JWT access token"""
        expire = datetime.utcnow() + timedelta(hours=self.token_expire_hours)
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def register_user(self, request: CreateUserRequest) -> User:
        """Register a new user"""
        # Check if username already exists
        existing_user = await db.database.users.find_one({"username": request.username})
        if existing_user:
            raise ValueError("Username already exists")

        # Check if email already exists
        existing_email = await db.database.users.find_one({"email": request.email})
        if existing_email:
            raise ValueError("Email already exists")

        # Create new user
        user_id = str(uuid.uuid4())
        password_hash = self.hash_password(request.password)
        
        user = User(
            id=user_id,
            username=request.username,
            email=request.email,
            password_hash=password_hash,
            display_name=request.display_name or request.username,
            status=UserStatus.OFFLINE,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow()
        )

        # Save to database
        await db.database.users.insert_one(user.model_dump(mode='json'))
        
        return user

    async def login_user(self, request: LoginRequest) -> tuple[User, str]:
        """Login a user and return user + token"""
        # Find user by username
        user_data = await db.database.users.find_one({"username": request.username})
        if not user_data:
            raise ValueError("Invalid username or password")

        user = User(**user_data)

        # Verify password
        if not self.verify_password(request.password, user.password_hash):
            raise ValueError("Invalid username or password")

        # Update last active and status
        user.last_active = datetime.utcnow()
        user.status = UserStatus.ONLINE
        
        await db.database.users.update_one(
            {"id": user.id},
            {"$set": {
                "last_active": user.last_active,
                "status": user.status.value
            }}
        )

        # Create access token
        token = self.create_access_token(user.id, user.username)

        return user, token

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        user_data = await db.database.users.find_one({"id": user_id})
        if user_data:
            return User(**user_data)
        return None

    async def update_user_status(self, user_id: str, status: UserStatus):
        """Update user status"""
        await db.database.users.update_one(
            {"id": user_id},
            {"$set": {
                "status": status.value,
                "last_active": datetime.utcnow()
            }}
        )

    async def logout_user(self, user_id: str):
        """Logout user (set status to offline)"""
        await self.update_user_status(user_id, UserStatus.OFFLINE)

# Global service instance
auth_service = AuthService()