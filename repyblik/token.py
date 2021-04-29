from enum import Enum
from dataclasses import dataclass
from typing import cast, Optional

import requests
import pendulum


class TokenType(Enum):
    App = "APP"
    Email = "EMAIL_TOKEN"


@dataclass
class TokenRequestData:
    verification_phrase: str
    token_type: TokenType
    expiration_date: pendulum.DateTime


class TokenFetchError(Exception):
    """Exception to be raised when the token service returned an invalid answer"""

    pass


class TokenDispenser:
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._token = None

    def _verify_token_available(self):
        if not self._token:
            raise RuntimeError(
                "Request was not made, request failed or token not loaded"
            )

    def request(self, email: str) -> TokenRequestData:
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
            self._token = resp.cookies["connect.sid"]
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

        return TokenRequestData(signin_data["phrase"], token_type, expiration_date)

    @property
    def token(self) -> Optional[str]:
        self._verify_token_available()
        return self._token
