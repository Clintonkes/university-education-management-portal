"""
cli.py — Command-line tools for setting up the database.

    flask --app run init-db           create all tables (safe to run again)
    flask --app run seed              load demo data into an EMPTY database
    flask --app run seed --reset      wipe everything and reload demo data
    flask --app run create-superadmin create your own Super Admin account
"""

import click
from flask import Flask

from .extensions import db


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create database tables."""
        from . import models  # noqa: F401  (make sure every table is known)
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Delete ALL data first.")
    def seed(reset: bool):
        """Load demo data so every workflow can be tested immediately."""
        from .seed import seed_demo_data
        if reset:
            click.confirm("This deletes every record in the database. Continue?", abort=True)
            db.drop_all()
        db.create_all()
        created = seed_demo_data()
        click.echo("Demo data loaded." if created else "Database already has users; nothing was changed. Use --reset.")

    @app.cli.command("create-superadmin")
    @click.option("--email", prompt=True)
    @click.option("--first-name", prompt=True)
    @click.option("--last-name", prompt=True)
    @click.password_option()
    def create_superadmin(email, first_name, last_name, password):
        """Create a Super Admin account (for a fresh production database)."""
        from .models import AccountStatus, Role, User
        from .services.accounts import validate_password
        from .services.errors import ServiceError

        try:
            validate_password(password)
        except ServiceError as error:
            raise click.ClickException(str(error)) from None
        db.create_all()
        user = User(email=email.strip().lower(), first_name=first_name, last_name=last_name,
                    role=Role.SUPER_ADMIN, status=AccountStatus.ACTIVE)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Super Admin {user.email} created.")
