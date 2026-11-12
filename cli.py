# cli.py
import typer
from . import auth, setup

app = typer.Typer()
auth_app = typer.Typer()
app.add_typer(auth_app, name="auth")

@auth_app.command("login")
def login():
    auth.login()

