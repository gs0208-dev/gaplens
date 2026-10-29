import os
import secrets

# The app refuses to start without a JWT secret. Tests use a random throwaway value, set here
# because this file runs before anything imports the app.
os.environ["JWT_SECRET"] = secrets.token_hex(32)
