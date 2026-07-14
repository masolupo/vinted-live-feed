"""
token_crypto.py — symmetric encryption (Fernet) of the Vinted tokens before
saving them to the DB. The key is in VINTED_TOKEN_KEY (feed/.env).

Nothing ever lands in the database in cleartext: access_token, refresh_token and
cookies always go through encrypt()/decrypt().
"""

from os import getenv

from cryptography.fernet import Fernet

# Read lazily on the first encryption: this way it does not depend on the import
# order relative to load_dotenv().
_fernet: Fernet | None = None


def _get() -> Fernet:
  global _fernet
  if _fernet is None:
    key = getenv('VINTED_TOKEN_KEY')
    if not key:
      raise RuntimeError('VINTED_TOKEN_KEY not configured: cannot encrypt/decrypt tokens')
    _fernet = Fernet(key.encode())
  return _fernet


def available() -> bool:
  return bool(getenv('VINTED_TOKEN_KEY'))


def encrypt(plaintext: str) -> str:
  if not plaintext:
    return ''
  return _get().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
  if not token:
    return ''
  return _get().decrypt(token.encode()).decode()
