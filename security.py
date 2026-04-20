import os
import base64
from datetime import datetime, timedelta, timezone
import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import jwt

# Get or generate AES master key and JWT secret key
# Note: In production, these MUST be set via environment variables.
AES_MASTER_KEY_B64 = os.environ.get("AES_MASTER_KEY", base64.b64encode(AESGCM.generate_key(bit_length=256)).decode('utf-8'))
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback_secret_key_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Initialize AESGCM (AES-256 GCM)
try:
    aes_key_bytes = base64.b64decode(AES_MASTER_KEY_B64)
    # Ensure it's exactly 32 bytes (256 bits)
    if len(aes_key_bytes) != 32:
        aes_key_bytes = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key_bytes)
except Exception:
    aes_key_bytes = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key_bytes)

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def encrypt_data(plaintext: str) -> str:
    """Encrypt a string using AES-256 GCM and return a base64 encoded ciphertext"""
    if not plaintext:
        return ""
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')


def decrypt_data(ciphertext_b64: str) -> str:
    """Decrypt a base64 encoded AES-256 GCM ciphertext back to plaintext"""
    if not ciphertext_b64:
        return ""
    try:
        data = base64.b64decode(ciphertext_b64.encode('utf-8'))
        nonce = data[:12]
        ciphertext = data[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return ""


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
