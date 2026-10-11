"""Custom Flask CLI commands.

Usage:
    flask create-admin --email admin@example.com --name "Admin Name"
    (or run scripts/seed.py for full demo data)
"""
import getpass

import click

from app.extensions import db
from app.models import User, Profile


def register_cli_commands(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True, help="Administrator email address.")
    @click.option("--name", prompt="Full name", help="Administrator full name.")
    @click.option("--password", default=None, help="Admin password (will prompt securely if omitted).")
    def create_admin(email, name, password):
        """Securely create the first administrator account."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f"A user with email {email} already exists.")
            return

        if not password:
            password = getpass.getpass("Admin password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                click.echo("Passwords do not match. Aborting.")
                return
        if len(password) < 8:
            click.echo("Password must be at least 8 characters. Aborting.")
            return

        admin = User(full_name=name, email=email, role="admin")
        admin.set_password(password)
        db.session.add(admin)
        db.session.flush()
        db.session.add(Profile(user_id=admin.id, status="approved"))
        db.session.commit()
        click.echo(f"Administrator account created for {email}.")

    @app.cli.command("init-categories")
    def init_categories():
        """Populate the default business categories if missing."""
        from app.models import BusinessCategory, DEFAULT_CATEGORIES
        created = 0
        for name in DEFAULT_CATEGORIES:
            if not BusinessCategory.query.filter_by(name=name).first():
                db.session.add(BusinessCategory(name=name))
                created += 1
        db.session.commit()
        click.echo(f"Created {created} new business categories.")
