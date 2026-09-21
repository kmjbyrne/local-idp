# OAuth2 Authorization Code Flow

OAuth2 handles **authorization**, granting a client (your app) access to
resources on behalf of a user, without the client ever seeing the user's
password. It says nothing about _whom_ the user is.

## Roles

| Role                     | In our stack                                        |
| ------------------------ | --------------------------------------------------- |
| **Resource Owner**       | The user (person in the browser)                    |
| **Client**               | Resource provider/app                               |
| **Authorization Server** | Possibly `local-idp` (or Google, Auth0, etc.)       |
| **Resource Server**      | API routes (`/api/<resource>`, `/api/<user>`, etc.) |

## Authorization Code Flow

The most common OAuth2 grant. The browser never touches the access token
directly as it stays server-side.

```mermaid
sequenceDiagram
    participant User as User (Browser)
    participant App as Nuxt App (Client)
    participant IdP as Authorization Server (local-idp)
    participant API as Resource Server (API routes)

    User->>App: Click "Sign in"
    App->>App: Generate state parameter
    App->>User: Redirect to IdP /dev/authorize

    User->>IdP: GET /dev/authorize?client_id=...&redirect_uri=...&state=...
    IdP->>User: Show sign-in page (pick a persona)
    User->>IdP: Pick a user
    IdP->>IdP: Issue authorization code
    IdP->>User: Redirect to redirect_uri?code=...&state=...

    User->>App: GET /auth/callback?code=...&state=...
    App->>App: Validate state matches
    App->>IdP: POST /dev/token (code + client_id + client_secret)
    IdP->>IdP: Validate code, check client credentials
    IdP->>App: { access_token, refresh_token, expires_in }

    App->>App: Store tokens in encrypted session cookie

    User->>App: Navigate to /inventory
    App->>API: GET /api/nodes (session cookie attached)
    API->>API: Read access_token from session
    API->>API: Verify token signature against JWKS
    API->>App: { children: [...] }
    App->>User: Render inventory page
```

## Token Anatomy

In our setup, the access token is a signed JWT. This is a choice our IdP makes,
not something the OAuth2 spec requires. Many providers issue opaque tokens
instead (a random string that the resource server exchanges at an introspection
endpoint).

Our access token payload:

```json
{
  "iss": "http://localhost:9001",
  "aud": "dev",
  "sub": "user-bobby",
  "email": "bobby@example.com",
  "name": "Bobby Tables",
  "roles": ["admin"],
  "permissions": ["boards.write"],
  "iat": 1695312000,
  "exp": 1695315600
}
```

## Token Refresh

Access tokens _should_ expire. Rather than forcing a new login, the client uses
the refresh token to get a new access token silently.

```mermaid
sequenceDiagram
    participant App as App
    participant IdP as Authorization Server
    participant API as Resource Server

    App->>API: GET /api/resource (expired access_token in session)
    API->>API: Token signature valid but expired
    API->>App: (requireAuth detects expiry)

    App->>IdP: POST /dev/token (grant_type=refresh_token)
    IdP->>App: { access_token (new), refresh_token (new), expires_in }
    App->>App: Update session with new tokens

    App->>API: GET /api/resource (new access_token)
    API->>App: { data: [...] }
```

## Key Points

- The browser never sees the access token. It lives in an encrypted server-side
  session cookie.
- The `state` parameter prevents CSRF on the callback. Without it, an attacker
  could craft a callback URL that binds your session to their account.
- The `client_secret` is sent server-to-server on the token exchange. The
  browser never has it.
- OAuth2 alone does not tell you who the user is. The `sub` claim in our access
  token is something our IdP chose to include, not something the spec
  guarantees.
