"""
Admin creation script for ArchAI-Plan.
Run: python scripts/create_admin.py
"""
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models.user import User
from app.security import hash_password
import uuid


def create_admin():
    print("=== ArchAI-Plan Admin Creation ===")
    full_name = input("Full Name: ").strip()
    email = input("Email: ").strip().lower()
    password = input("Password: ").strip()

    if not full_name or not email or not password:
        print("Error: All fields are required.")
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        admin = User(
            id=str(uuid.uuid4()),
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        print(f"\n✅ Admin account created successfully!")
        print(f"   Name : {full_name}")
        print(f"   Email: {email}")
        print(f"   Role : admin")
        print(f"\nYou can now login at: http://localhost:3000/admin/login")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
