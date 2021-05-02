import time
import pathlib
import typing

import pendulum
import click
import xdg

from .api import RepublikApi, TokenType, RepublikCDN

API_URL_REPUBLIK = "https://api.republik.ch/graphql"
POLL_FREQUENCY = pendulum.duration(seconds=3)
TOKENS_DIR = xdg.xdg_config_home() / "repyblik" / "tokens"


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
    ctx.obj["TOKEN_FILE"] = TOKENS_DIR / email


@cli.group()
def token():
    """Manage authentication tokens"""
    pass


@token.command("get")
@click.pass_context
@click.option("--overwrite", is_flag=True)
def token_get(ctx, overwrite):
    """Get a new token from the Republik API"""

    if ctx.obj["TOKEN_FILE"].exists() and not overwrite:
        raise click.BadArgumentUsage(
            f"The token file '{ctx.obj['TOKEN_FILE']}' already exists, use --overwrite to force regeneration"
        )

    api = RepublikApi(API_URL_REPUBLIK)
    signin_data = api.request_token(ctx.obj["EMAIL"])

    if signin_data.token_type == TokenType.App:
        click.echo("You have to verify the request on the Republik API")
    elif signin_data.token_type == TokenType.Email:
        click.echo("You have to verify the request by clicking on the link you get by email")

    click.echo("Please check that the verification phrase is as follows:")
    click.echo(f"    {signin_data.verification_phrase}")
    click.echo(f"The request expires {signin_data.expiration_date.diff_for_humans()}")

    click.echo(f"If verified in time, the token returned by the API is:")
    click.echo(f"    {api.token}")

    with click.progressbar(
        length=signin_data.expiration_date.diff() // POLL_FREQUENCY,
        label="Waiting for confirmation",
    ) as bar:
        for _ in bar:
            time.sleep(POLL_FREQUENCY.seconds)
            if api.get_my_id():
                break
        else:
            click.echo("Token could not be verified", err=True)

    click.echo("Token confirmed", err=True)

    if not ctx.obj["TOKEN_FILE"].parent.exists():
        ctx.obj["TOKEN_FILE"].parent.mkdir(parents=True, exist_ok=True, mode=0o750)

    ctx.obj["TOKEN_FILE"].write_text(api.token)


@token.command("check")
@click.pass_context
def token_check(ctx):
    """Check whether the token is valid"""

    try:
        token = ctx.obj["TOKEN_FILE"].read_text().strip()
    except (FileNotFoundError, PermissionError):
        raise click.BadArgumentUsage(
            f"The token file '{ctx.obj['TOKEN_FILE']}' could not be accessed, please request a token first"
        )

    api = RepublikApi(API_URL_REPUBLIK, token=token)

    if not api.get_my_id():
        raise click.BadArgumentUsage(f"Login failed, the token '{api.token}' has either not been confirmed or is invalid")

    click.echo(f"The token registered for '{ctx.obj['EMAIL']}' seems to be valid")


@cli.group()
@click.pass_context
def articles(ctx):
    """Fetch articles"""

    try:
        ctx.obj["TOKEN"] = ctx.obj["TOKEN_FILE"].read_text().strip()
    except (FileNotFoundError, PermissionError):
        raise click.BadArgumentUsage(
            f"The token file '{ctx.obj['TOKEN_FILE']}' could not be accessed, please request a token first"
        )


@articles.command("list")
@click.option(
    "--first",
    "-f",
    help="Number of latest articles to list",
    required=True,
    type=int,
    default=10,
    show_default=True,
)
@click.pass_context
def articles_list(ctx, first):
    """List articles"""

    api = RepublikApi(API_URL_REPUBLIK, ctx.obj["TOKEN"])

    if not api.get_my_id():
        raise click.BadArgumentUsage(f"Login failed, is the token '{api.token}' still valid?")

    for article in api.get_last_articles(first):
        click.echo(f"{article.publication_date}: {article.title}")


@articles.command("fetch")
@click.option(
    "--directory",
    "-d",
    help="The directory to download the PDFs to",
    required=True,
    type=click.Path(file_okay=False, writable=True, readable=True, resolve_path=True),
    default="./republik-articles",
    show_default=True,
)
@click.option(
    "--first",
    "-f",
    help="Number of latest articles to fetch (if not incremental)",
    required=True,
    type=int,
    default=10,
    show_default=True,
)
@click.pass_context
def articles_fetch(ctx, directory, first):
    """Fetch articles as PDFs"""

    api = RepublikApi(API_URL_REPUBLIK, ctx.obj["TOKEN"])
    directory = pathlib.Path(directory)
    timestamp_path = directory / ".last"

    if not api.get_my_id():
        raise click.BadArgumentUsage(f"Login failed, is the token '{api.token}' still valid?")

    last = None

    try:
        last = typing.cast(pendulum.DateTime, pendulum.parse(timestamp_path.read_text().strip()))
        articles = api.get_articles_since(last + pendulum.Duration(seconds=1))

        if not articles:
            click.echo(f"No new articles published since {last}")
            return

    except (FileNotFoundError, PermissionError):
        articles = api.get_last_articles(first)

        if not articles:
            click.echo("No articles found, something is probably wrong")
            return

    directory.mkdir(parents=True, exist_ok=True)

    cdn = RepublikCDN()

    for article in articles:
        destination = directory / f"{article.publication_date} - {article.title}.pdf"

        click.echo(f"Fetching: {article.publication_date}: {article.title}")
        click.echo(f"  -> {destination}")

        cdn.download_pdf(article.path, destination)

    timestamp_path.write_text(articles[0].publication_date.to_rfc3339_string())
