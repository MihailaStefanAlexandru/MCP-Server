#!/usr/bin/env python3
"""
Modul de autentificare

Utilizatorii și rolurile sunt stocate în llm_config.json.
Parolele sunt hash-uite cu PBKDF2-HMAC-SHA256 (standard Python).

Structura adăugată în llm_config.json:
{
    "app_users": [
        {
            "username": "ion",
            "pass_hash": "abc123...",
            "salt": "def456...",
            "role": "viewer"
        }
    ],
    "roles": {
        "viewer": {
            "alfresco_user": "app_viewer",
            "alfresco_password": "...",
            "allowed_tools": [...]
        },
        ...
    }
}
"""

import hashlib
import hmac
import os
import time
import json
import base64
import logging
import tempfile
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_CONFIG_PATH: str = "llm_config.json"


def set_config_path(path: str):
    global _CONFIG_PATH
    _CONFIG_PATH = path


def get_config_path() -> str:
    return _CONFIG_PATH

class UserRole(str, Enum):
    ADMIN  = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

@dataclass
class User:
    username: str
    role: UserRole

@dataclass
class TokenData:
    username: str
    role: UserRole
    exp: float

def _load_config() -> dict:
    """Citește fișierul config."""
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_config(config: dict):
    """
    Salvează fișierul config atomic: scrie în fișier temporar, apoi rename.
    Fișierul nu e niciodată corupt dacă aplicația cade la mijloc.
    """
    dir_path = os.path.dirname(os.path.abspath(_CONFIG_PATH))

    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        dir=dir_path, delete=False, suffix='.tmp'
    ) as tmp:
        json.dump(config, tmp, indent=4, ensure_ascii=False)
        tmp_path = tmp.name

    os.replace(tmp_path, _CONFIG_PATH)


def _get_users() -> List[dict]:
    try:
        return _load_config().get("app_users", [])
    except Exception as e:
        logger.error(f"Eroare citire utilizatori: {e}")
        return []


def _get_roles() -> dict:
    try:
        return _load_config().get("roles", {})
    except Exception as e:
        logger.error(f"Eroare citire roluri: {e}")
        return {}

def hash_password(password: str, salt: Optional[str] = None):
    """
    Hashează parola cu PBKDF2-HMAC-SHA256 (260.000 iterații — OWASP 2023).
    Returnează (hash_hex, salt_hex).
    Nu necesită nicio dependență externă.
    """
    if salt is None:
        salt = os.urandom(32).hex()

    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        iterations=260_000
    )
    return key.hex(), salt


def verify_password(plain_password: str, stored_hash: str, salt: str) -> bool:
    """Verifică parola față de hash. Comparare time-constant (anti timing attack)."""
    computed_hash, _ = hash_password(plain_password, salt)
    return hmac.compare_digest(computed_hash, stored_hash)

JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

def _get_jwt_secret() -> str:
    """
    Citește secretul JWT din config.
    Dacă nu există îl generează o singură dată și îl salvează.
    Astfel token-urile rămân valide și după repornirea aplicației.
    """
    try:
        config = _load_config()
        secret = config.get("_jwt_secret")
        if not secret:
            secret = os.urandom(32).hex()
            config["_jwt_secret"] = secret
            _save_config(config)
            logger.info("✅ JWT secret generat și salvat în config")
        return secret
    except Exception as e:
        logger.error(f"Nu pot gestiona JWT secret: {e}")
        return os.urandom(32).hex()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.urlsafe_b64decode(s)


def create_access_token(user: User) -> str:
    """Generează JWT pentru utilizator."""
    secret = _get_jwt_secret()

    header  = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub":  user.username,
        "role": user.role.value,
        "iat":  time.time(),
        "exp":  time.time() + JWT_EXPIRE_HOURS * 3600,
    }

    header_b64  = _b64url_encode(json.dumps(header,  separators=(',', ':')).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    signing_input = f"{header_b64}.{payload_b64}"

    signature = hmac.new(
        secret.encode(),
        signing_input.encode(),
        hashlib.sha256
    ).digest()

    return f"{signing_input}.{_b64url_encode(signature)}"


def verify_access_token(token: str) -> Optional[TokenData]:
    """Validează JWT. Returnează TokenData sau None dacă e invalid/expirat."""
    try:
        secret = _get_jwt_secret()
        parts  = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        expected_sig = hmac.new(
            secret.encode(),
            signing_input.encode(),
            hashlib.sha256
        ).digest()

        if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
            return None

        payload = json.loads(_b64url_decode(payload_b64))

        if payload.get("exp", 0) < time.time():
            return None

        return TokenData(
            username=payload["sub"],
            role=UserRole(payload["role"]),
            exp=payload["exp"],
        )

    except Exception as e:
        logger.warning(f"JWT validare eșuată: {e}")
        return None

class UserManager:
    """
    CRUD utilizatori direct în llm_config.json.
    Fără bază de date, fără dependențe externe.
    """

    @staticmethod
    def authenticate(username: str, password: str) -> Optional[User]:
        """Verifică credențialele. Timp constant indiferent dacă userul există."""
        users  = _get_users()
        target = next((u for u in users if u.get("username") == username), None)

        if target is None:
            hash_password("dummy_anti_timing")   # timp constant
            return None

        if not verify_password(password, target["pass_hash"], target["salt"]):
            return None

        return User(username=target["username"], role=UserRole(target.get("role", "viewer")))

    @staticmethod
    def get(username: str) -> Optional[User]:
        target = next((u for u in _get_users() if u.get("username") == username), None)
        if not target:
            return None
        return User(username=target["username"], role=UserRole(target.get("role", "viewer")))

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        """Returnează toți utilizatorii fără pass_hash și salt."""
        return [
            {"username": u["username"], "role": u.get("role", "viewer")}
            for u in _get_users()
        ]

    @staticmethod
    def create(username: str, password: str, role: UserRole) -> User:
        """Adaugă utilizator nou. Aruncă ValueError dacă există deja."""
        config = _load_config()
        users  = config.setdefault("app_users", [])

        if any(u["username"] == username for u in users):
            raise ValueError(f"Utilizatorul '{username}' există deja")

        pass_hash, salt = hash_password(password)
        users.append({
            "username":  username,
            "pass_hash": pass_hash,
            "salt":      salt,
            "role":      role.value,
        })

        _save_config(config)
        logger.info(f"✅ Utilizator creat: {username} (rol: {role.value})")
        return User(username=username, role=role)

    @staticmethod
    def update_password(username: str, new_password: str) -> bool:
        """Actualizează parola unui utilizator."""
        config = _load_config()
        users  = config.get("app_users", [])

        for u in users:
            if u["username"] == username:
                u["pass_hash"], u["salt"] = hash_password(new_password)
                _save_config(config)
                logger.info(f"🔑 Parolă actualizată: {username}")
                return True
        return False

    @staticmethod
    def update_role(username: str, role: UserRole) -> bool:
        """Schimbă rolul unui utilizator."""
        config = _load_config()
        users  = config.get("app_users", [])

        for u in users:
            if u["username"] == username:
                u["role"] = role.value
                _save_config(config)
                logger.info(f"🔄 Rol actualizat: {username} → {role.value}")
                return True
        return False

    @staticmethod
    def delete(username: str) -> bool:
        """Șterge utilizatorul din config."""
        config = _load_config()
        users  = config.get("app_users", [])
        new_users = [u for u in users if u["username"] != username]

        if len(new_users) == len(users):
            return False

        config["app_users"] = new_users
        _save_config(config)
        logger.info(f"🗑️  Utilizator șters: {username}")
        return True

def get_alfresco_credentials_for_role(role: UserRole) -> Dict[str, str]:
    """Credențialele contului tehnic Alfresco pentru un rol."""
    roles       = _get_roles()
    role_config = roles.get(role.value, roles.get("viewer", {}))
    return {
        "username": role_config.get("alfresco_user", "admin"),
        "password": role_config.get("alfresco_password", "admin"),
    }


def get_allowed_tools_for_role(role: UserRole) -> List[str]:
    """Tool-urile MCP permise pentru un rol."""
    roles       = _get_roles()
    role_config = roles.get(role.value, roles.get("viewer", {}))
    return role_config.get("allowed_tools", [
        "list_root_children", "get_node_children",
        "get_node_info", "get_node_id_by_name", "browse_by_path",
    ])


def extract_token_from_header(authorization: str) -> Optional[str]:
    """Extrage token-ul din 'Authorization: Bearer <token>'."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

def init_auth(config_path: str):
    """
    Apelat o singură dată din main.py la pornirea aplicației.
    - Setează path-ul fișierului config
    - Adaugă secțiunile lipsă în config (app_users, roles)
    - Creează admin implicit dacă nu există niciun utilizator
    - Generează și salvează JWT secret dacă nu există
    """
    set_config_path(config_path)

    try:
        config = _load_config()
    except FileNotFoundError:
        logger.error(f"❌ Fișierul config nu există: {config_path}")
        return

    changed = False

    # Adaugă secțiunea app_users dacă lipsește
    if "app_users" not in config:
        config["app_users"] = []
        changed = True

    # Adaugă secțiunea roles cu valorile implicite dacă lipsește
    if "roles" not in config:
        config["roles"] = {
            "viewer": {
                "alfresco_user":     "app_viewer",
                "alfresco_password": "viewer_pass",
                "allowed_tools": [
                    "list_root_children", "get_node_children",
                    "get_node_info", "get_node_id_by_name", "browse_by_path"
                ]
            },
            "editor": {
                "alfresco_user":     "app_editor",
                "alfresco_password": "editor_pass",
                "allowed_tools": [
                    "list_root_children", "get_node_children",
                    "get_node_info", "get_node_id_by_name", "browse_by_path",
                    "create_folder"
                ]
            },
            "admin": {
                "alfresco_user":     "admin",
                "alfresco_password": "admin",
                "allowed_tools": [
                    "list_root_children", "get_node_children",
                    "get_node_info", "get_node_id_by_name", "browse_by_path",
                    "create_folder", "delete_node"
                ]
            }
        }
        changed = True

    if changed:
        _save_config(config)

    # Admin implicit dacă nu există niciun utilizator
    if not config.get("app_users"):
        default_pass = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
        UserManager.create("admin", default_pass, UserRole.ADMIN)
        logger.warning(
            f"⚠️  Admin implicit creat cu parola '{default_pass}'. "
            f"Schimbă parola cu: POST /admin/users/admin/password"
        )

    # JWT secret persistent
    _get_jwt_secret()

    n_users = len(_get_users())
    logger.info(f"✅ Auth inițializat: {n_users} utilizatori | config: {config_path}")