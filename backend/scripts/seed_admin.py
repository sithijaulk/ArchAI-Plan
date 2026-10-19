"""Backward-compatible entry point for interactive admin creation."""
try:
    from .create_admin import create_admin
except ImportError:
    from create_admin import create_admin


if __name__ == "__main__":
    create_admin()
