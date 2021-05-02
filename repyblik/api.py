import pathlib
import enum
from dataclasses import dataclass
from typing import cast, Optional, List

import pendulum
import requests


class TokenType(enum.Enum):
    App = "APP"
    Email = "EMAIL_TOKEN"


@dataclass
class TokenRequestData:
    verification_phrase: str
    token_type: TokenType
    expiration_date: pendulum.DateTime


@dataclass
class ArticleData:
    title: str
    path: str
    publication_date: pendulum.DateTime


class TokenFetchError(Exception):
    """Exception to be raised when the token service returned an invalid answer"""

    pass


class RepublikApi:
    def __init__(self, base_url: str = "https://api.republik.ch/graphql", token: str = ""):
        self._base_url = base_url
        self._session = requests.Session()
        self._token = ""

        if token:
            self._set_token(token)

    def _set_token(self, token: str):
        self._token = token
        if token:
            self._session.cookies.set("connect.sid", token)

    def _verify_token_available(self):
        if not self._token:
            raise RuntimeError(
                "Request was not made, request failed or token not loaded"
            )

    def request_token(self, email: str) -> TokenRequestData:
        """ Request a new session token (connect.sid) from the REPUBLIK GraphQL API"""

        resp = requests.post(
            self._base_url,
            json={
                "query": "mutation signIn($email: String!) { signIn(email: $email) { phrase expiresAt tokenType }}",
                "variables": {
                    "email": email,
                },
            },
        )

        resp.raise_for_status()

        try:
            token = resp.cookies["connect.sid"]
        except KeyError as exc:
            raise TokenFetchError("The response is missing the 'connect.sid' cookie") from exc

        resp_body = resp.json()

        try:
            signin_data = resp_body["data"]["signIn"]
        except KeyError as exc:
            raise TokenFetchError("The response body is missing the 'signIn' data part") from exc

        expiration_date = cast(
            pendulum.DateTime, pendulum.parse(signin_data["expiresAt"])
        )

        try:
            token_type = TokenType(signin_data["tokenType"])
        except KeyError as exc:
            raise TokenFetchError("Unknown token type in response") from exc

        self._set_token(token)

        return TokenRequestData(signin_data["phrase"], token_type, expiration_date)

    @property
    def token(self) -> Optional[str]:
        self._verify_token_available()
        return self._token

    def get_my_id(self) -> Optional[str]:
        self._verify_token_available()

        resp = self._session.post(
            self._base_url,
            json={"query": "{ me { id } }"},
            )

        resp.raise_for_status()
        resp_body = resp.json()

        # data.me is Null/None if not authorized
        return resp_body["data"]["me"]

    def get_last_articles(self, first: int) -> List[ArticleData]:
        """Get all new documents"""

        self._verify_token_available()

        resp = self._session.post(
            self._base_url,
            json={
                "query": "query($first: Int) {"
                         "  documents(feed: true, first: $first) {"
                         "    nodes { meta { title path publishDate } }"
                         "  }"
                         "}",
                "variables": {
                    "first": first,
                }
            })
        resp.raise_for_status()
        resp_body = resp.json()

        return [ArticleData(n["meta"]["title"], n["meta"]["path"], cast(pendulum.DateTime, pendulum.parse(n["meta"]["publishDate"]))) for n in resp_body["data"]["documents"]["nodes"]]

    def get_articles_since(self, since: pendulum.DateTime) -> List[ArticleData]:
        """Get all new documents"""

        self._verify_token_available()

        resp = self._session.post(
            self._base_url,
            json={
                "query": "query($since:DateTime) {"
                         "  search(filter: {feed: true, publishedAt: {from: $since}},"
                         "         sort: {key: publishedAt}) {"
                         "    nodes { entity { ... on Document { meta { title path publishDate } } } }"
                         "  }"
                         "}",
                "variables": {
                    "since": since.to_rfc3339_string(),
                }
            })

        resp.raise_for_status()
        resp_body = resp.json()

        return [ArticleData(n["entity"]["meta"]["title"], n["entity"]["meta"]["path"], cast(pendulum.DateTime, pendulum.parse(n["entity"]["meta"]["publishDate"]))) for n in resp_body["data"]["search"]["nodes"]]


class RepublikCDN:
    def __init__(self, base_url: str = "https://cdn.repub.ch"):
        self._base_url = base_url
        self._session = requests.Session()

    def download_pdf(self, path: str, destination: pathlib.Path):
        cdn_url = f"{self._base_url}/pdf{path}.pdf"

        with self._session.get(cdn_url, stream=True) as stream:
            stream.raise_for_status()
            with destination.open("wb") as fhandle:
                for chunk in stream.iter_content(chunk_size=16*1024**2):
                    fhandle.write(chunk)
