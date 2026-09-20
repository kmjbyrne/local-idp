"""The records a first run writes, when there is no file yet.

The subject ids are the ones eagata-backend's ``app.fixtures`` seeds into its
database. They are the join: a token carrying one of these subjects describes
somebody that service already has an organization and a workspace for. Changing
one here without changing it there is silent, because a token for an unknown
subject looks exactly like a new signup rather than an error.

Data, not behaviour. Point the service at a different project by editing
``instance/users.json``, or by deleting it and letting a different seed write.
Nothing else in this service refers to these values.
"""

from app.clients import Client
from app.store import User

USERS: tuple[User, ...] = (
    User(
        key="maya",
        subject="019b76da-a800-741f-8a5b-bba72959884e",
        name="Maya Okonkwo",
        email="maya@example.test",
        purpose="Personal space only.",
    ),
    User(
        key="tom",
        subject="019b76da-abe8-7f61-a3de-0b4ffc4342a6",
        name="Tom Reilly",
        email="tom@example.test",
        purpose="Personal space only.",
    ),
    User(
        key="sana",
        subject="019b76da-afd0-7aee-9b90-40c912f6822c",
        name="Sana Qureshi",
        email="sana@example.test",
        purpose="Personal space only.",
    ),
    User(
        key="alice",
        subject="019b76da-b3b8-741c-ada2-4c1da1ed4927",
        name="Alice Admin",
        email="alice@example.test",
        purpose="Owner of Acme, plus a personal space.",
    ),
    User(
        key="bob",
        subject="019b76da-b7a0-7b14-887c-e85ad1ac3085",
        name="Bob Editor",
        email="bob@example.test",
        purpose="Member of Acme, plus a personal space.",
    ),
    User(
        key="priya",
        subject="019b76da-bb88-7691-9cac-d88fd2ea6258",
        name="Priya Nair",
        email="priya@example.test",
        purpose="Admin of Acme, plus a personal space.",
    ),
    User(
        key="eve",
        subject="019b76da-bf70-7a2f-87d3-af68609ed18c",
        name="Eve Guest",
        email="eve@example.test",
        purpose="In Acme, with reach on none of its workspaces.",
    ),
    User(
        key="nomad",
        subject="019b76da-c358-7ab7-b78b-17919adc77c9",
        name="Noa Nomad",
        email="nomad@example.test",
        purpose="No space and no organization: every resource refuses.",
    ),
    User(
        key="stale",
        subject="019b76da-c740-7972-b57c-06ae0972b8e2",
        name="Stale Session",
        email="stale@example.test",
        purpose="Member of Acme, plus a personal space.",
    ),
)

# One client, matching what eagata-backend's dev configuration uses. Its secret
# is written here in the open because it guards nothing: this provider mints
# tokens for people who do not exist, so the registry exists to make a wrong
# secret fail, not to keep a right one private.
CLIENTS: tuple[Client, ...] = (
    Client(
        client_id="dev-client",
        client_secret="dev-secret",
        name="Local development",
    ),
)
