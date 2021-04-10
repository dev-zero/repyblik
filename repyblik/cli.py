import click

from .token import TokenDispenser, TokenType

API_URL_REPUBLIK = "https://api.republik.ch/graphql"


@click.group()
@click.option(
    "--email",
    "-m",
    prompt="Your email address",
    help="The email address you registered with the REPUBLIK",
    required=True,
    type=str,
)
@click.pass_context
def cli(ctx, email):
    click.echo(f"Using '{email}' for this session...")

    ctx.ensure_object(dict)
    ctx.obj["EMAIL"] = email


@cli.group()
def token():
    """Manage authentication tokens"""
    pass


@token.command()
@click.pass_context
def get(ctx):
    """Get a new token from the Republik API"""
    dispenser = TokenDispenser(API_URL_REPUBLIK)
    signin_data = dispenser.request(ctx.obj["EMAIL"])

    if signin_data.token_type == TokenType.App:
        click.echo("You have to verify the request on the Republik API")
    elif signin_data.token_type == TokenType.Email:
        click.echo(
            "You have to verify the request by clicking on the link you get by email"
        )

    click.echo("Please check that the verification phrase is as follows:")
    click.echo(f"    {signin_data.verification_phrase}")
    click.echo(f"The request expires {signin_data.expiration_date.diff_for_humans()}")

    click.echo(f"If verified in time, the token returned by the API is:")
    click.echo(f"    {dispenser.token}")
