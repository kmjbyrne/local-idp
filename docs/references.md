# References

## RFCs

| RFC                                                     | Title                                 | Relevant doc                           |
| ------------------------------------------------------- | ------------------------------------- | -------------------------------------- |
| [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749.html) | The OAuth 2.0 Authorization Framework | [oauth2.md](oauth2.md)                 |
| [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html) | Bearer Token Usage                    | [oauth2.md](oauth2.md)                 |
| [RFC 7517](https://www.rfc-editor.org/rfc/rfc7517.html) | JSON Web Key (JWK)                    | [oauth2.md](oauth2.md)                 |
| [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519.html) | JSON Web Token (JWT)                  | [oauth2.md](oauth2.md)                 |
| [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html) | Proof Key for Code Exchange (PKCE)    | [oauth2.md](oauth2.md)                 |
| [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html) | OAuth 2.0 Token Exchange              | [token-exchange.md](token-exchange.md) |

## OpenID Connect Specs

| Spec                                                                                       | Title                                              | Relevant doc                           |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------- | -------------------------------------- |
| [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)           | Core OIDC spec (id_token, userinfo, scopes, nonce) | [openid-connect.md](openid-connect.md) |
| [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html) | `/.well-known/openid-configuration`                | [openid-connect.md](openid-connect.md) |

## Doc Directory

| Doc                                            | Covers                                             |
| ---------------------------------------------- | -------------------------------------------------- |
| [oauth2.md](oauth2.md)                         | Authorization Code flow, token anatomy, refresh    |
| [openid-connect.md](openid-connect.md)         | OIDC layer, id_token, scopes, userinfo, federation |
| [client-credentials.md](client-credentials.md) | M2M authentication (no user)                       |
| [token-exchange.md](token-exchange.md)         | RFC 8693, API key to JWT exchange                  |
| [simple-login.md](simple-login.md)             | Development-only direct login                      |
