# cli.py
import typer
import json
from . import auth, setup

app = typer.Typer()
auth_app = typer.Typer()
app.add_typer(auth_app, name="auth")

@auth_app.command("login")
def login():
    auth.login()

@auth_app.command("status")
def status():
    """Show login readiness without printing token values."""
    print(json.dumps(auth.get_auth_status(auth.SCOPES), indent=2))

@app.command()
def init():
    setup.run()

@app.command()
def serve():
    from .spotify import mcp
    mcp.run(transport="stdio")
