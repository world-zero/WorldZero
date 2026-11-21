"""The praxis room's ASGI app, driven by real ``pycrdt`` clients (#1740, ADR-0073).

In-memory ASGI on one side, pycrdt ``Channel`` on the other. Don't stub the
CRDT: the bug guarded is two clients each seeding and merging into two copies.
"""

import asyncio
import base64
import io
import linecache
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Callable

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pycrdt import (
    Awareness,
    Doc,
    Map,
    Provider,
    Text,
    YMessageType,
    create_awareness_message,
    create_update_message,
    read_message,
)
from pycrdt.websocket import YRoom
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import services.collab_consensus as collab_consensus
import services.praxis_room as praxis_room
from config import settings
from game_config import CURRENT_ERA
from main import app as fastapi_app
from models.character import Character
from models.character_stats import CharacterStats
from models.duel import Duel, DuelStatus
from models.praxis import (
    PRAXIS_BODY_MAX,
    PRAXIS_TITLE_MAX,
    Praxis,
    PraxisMember,
    PraxisStatus,
    PraxisType,
)
from models.praxis_room import PraxisRoomUpdate
from models.task import Task
from services.admin_service import apply_ban, suspend_account
from services.auth import create_jwt
from services.character import soft_delete_character
from services.character_stats import recalculate_character_stats
from services.praxis import (
    delete_praxis,
    kick_member,
    leave_praxis,
    submit_praxis,
    unsubmit_praxis,
)
from services.praxis_out import build_praxis_out
from services.praxis_room import (
    ROOM_BODY_KEY,
    ROOM_META_KEY,
    ROOM_TITLE_KEY,
    PraxisRoomASGIServer,
    PraxisRoomServer,
    acquire_single_instance_lock,
    room_name_for,
)
from tests.integration.factories import attach_proof, cast_vote, make_solo_praxis

SEED_BODY = "The seeded body of one praxis."
ALLOWED_ORIGIN = settings.cors_origins[0]
_TIMEOUT_SECONDS = 5.0

#: Ceiling on non-poll waits (connect, start/stop, unwind) so a hang names its
#: seam (#1930). Worst case 4 x 10s must stay under pytest-timeout's 60s.
_CEILING_SECONDS = 10.0


def _await_chain(task: asyncio.Task) -> str:
    """Walks ``cr_await``: ``Task.get_stack`` stops at the outermost frame."""
    lines: list[str] = []
    awaited: Any = task.get_coro()
    seen: set[int] = set()
    while awaited is not None and id(awaited) not in seen:
        seen.add(id(awaited))
        frame = getattr(awaited, "cr_frame", None) or getattr(awaited, "gi_frame", None)
        if frame is not None:
            source = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
            lines.append(
                f'  File "{frame.f_code.co_filename}", line {frame.f_lineno},'
                f" in {frame.f_code.co_name}\n    {source}"
            )
        awaited = getattr(awaited, "cr_await", None) or getattr(
            awaited, "gi_yieldfrom", None
        )
    return "\n".join(lines) or "  <no frames>"


def _pending_task_dump() -> str:
    """pytest-timeout dumps threads, and all tasks share one (#1930)."""
    buffer = io.StringIO()
    running = asyncio.current_task()
    tasks = sorted(
        (task for task in asyncio.all_tasks() if task is not running),
        key=lambda task: task.get_name(),
    )
    buffer.write(f"\n\n--- {len(tasks)} other pending task(s) on this event loop ---")
    for task in tasks:
        state = "cancelling" if task.cancelling() else "pending"
        buffer.write(f"\n\n== {task.get_name()} [{state}]\n")
        try:
            buffer.write(_await_chain(task))
        except Exception as exc:  # pragma: no cover — diagnostics must not raise
            buffer.write(f"  <could not read stack: {exc!r}>")
    return buffer.getvalue()


@asynccontextmanager
async def _bounded(description: str) -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(_CEILING_SECONDS):
            yield
    except TimeoutError:
        raise AssertionError(
            f"timed out after {_CEILING_SECONDS}s waiting for "
            f"{description}{_pending_task_dump()}"
        ) from None


#: Read off the live app so the test follows the mount if it moves.
ROOM_MOUNT = next(
    route for route in fastapi_app.routes if getattr(route, "name", None) == "praxis-rooms"
)


def mounted_room_path(praxis_id: int) -> str:
    return f"{ROOM_MOUNT.path}/praxis/{praxis_id}"


class _Socket:
    """Both ends of one WebSocket: ASGI for the app, ``Channel`` for the client."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.accepted = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_code: int | None = None
        self._to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._to_client: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def receive(self) -> dict[str, Any]:
        return await self._to_app.get()

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "websocket.accept":
            self.accepted.set()
        elif message["type"] == "websocket.send":
            await self._to_client.put(message["bytes"])
        elif message["type"] == "websocket.close":
            self.close_code = message.get("code")
            self.closed.set()
            await self._to_client.put(None)

    def __aiter__(self) -> "_Socket":
        return self

    async def __anext__(self) -> bytes:
        return await self.recv()

    async def send_bytes(self, message: bytes) -> None:
        await self._to_app.put({"type": "websocket.receive", "bytes": message})

    async def recv(self) -> bytes:
        message = await self._to_client.get()
        if message is None:
            raise StopAsyncIteration()
        return message

    async def disconnect(self) -> None:
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})
        await self._to_client.put(None)

    async def connect(self) -> None:
        await self._to_app.put({"type": "websocket.connect"})


class _ChannelAdapter:

    def __init__(self, socket: _Socket) -> None:
        self._socket = socket

    @property
    def path(self) -> str:
        return self._socket.path

    def __aiter__(self) -> "_ChannelAdapter":
        return self

    async def __anext__(self) -> bytes:
        return await self._socket.recv()

    async def send(self, message: bytes) -> None:
        await self._socket.send_bytes(message)

    async def recv(self) -> bytes:
        return await self._socket.recv()


class _SharedSessionFactory:
    """The test's one session, locked: room tasks would otherwise use it
    concurrently with the test body."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None

    def __call__(self) -> Any:
        return self._context()

    @asynccontextmanager
    async def _context(self) -> AsyncIterator[AsyncSession]:
        # Reentrant per task: a submit that opens the room reads rows inside it.
        if self._owner is asyncio.current_task():
            yield self._session
            return
        async with self._lock:
            self._owner = asyncio.current_task()
            try:
                yield self._session
            finally:
                self._owner = None


class _Rooms:
    def __init__(
        self, server: PraxisRoomServer, sessions: _SharedSessionFactory
    ) -> None:
        self.server = server
        self.app = PraxisRoomASGIServer(server)
        #: DB reads while rooms run MUST go through this, not ``db_session``,
        #: or a room task raises "concurrent operations are not permitted".
        self.sessions = sessions
        self._tasks: list[asyncio.Task] = []
        self._sockets: list[_Socket] = []

    async def open(
        self,
        praxis_id: int,
        account_id: int | None,
        *,
        origin: str | None = ALLOWED_ORIGIN,
        path: str | None = None,
        raw_token: str | None = None,
        through: Any | None = None,
    ) -> _Socket:
        """Returns once accepted or refused. ``through`` (the FastAPI app, to
        cross the mount) needs ``path`` too: :func:`mounted_room_path`."""
        socket = _Socket(path or f"/praxis/{praxis_id}")
        headers: list[tuple[bytes, bytes]] = [(b"host", b"api.worldzero.test")]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        token = raw_token or (None if account_id is None else create_jwt(account_id))
        if token is not None:
            headers.append((b"cookie", f"access_token={token}".encode()))
        scope = {
            "type": "websocket",
            "path": socket.path,
            "raw_path": socket.path.encode(),
            "query_string": b"",
            "scheme": "ws",
            # Empty at the outermost app; each mount grows it.
            "root_path": "",
            "headers": headers,
        }

        self._sockets.append(socket)
        self._tasks.append(
            asyncio.create_task(
                (through or self.app)(scope, socket.receive, socket.send)
            )
        )
        await socket.connect()
        await _wait_for(
            lambda: socket.accepted.is_set() or socket.closed.is_set(),
            "handshake to settle",
        )
        return socket

    async def submit(
        self, praxis_id: int, character_id: int, doc_state: str | None = None
    ) -> Any:
        """Harness-only: holds the session lock, since a submit races room tasks
        on the one shared session (production uses separate sessions)."""
        async with self.sessions() as session:
            result = await submit_praxis(
                praxis_id, character_id, session, doc_state=doc_state
            )
            await session.commit()  # get_db's commit; the absorb hangs on it
            return result

    def room_doc(self, praxis_id: int) -> Doc | None:
        room = self.server.rooms.get(room_name_for(praxis_id))
        return None if room is None else room.ydoc

    async def aclose(self) -> None:
        """Disconnect ends the tasks; cancel is only the backstop (#1930).

        A raw ``Task.cancel`` inside anyio's task group occasionally wedged the
        task. ``asyncio.wait`` because ``release``'s shielded scope ignores a
        cancel of this task.
        """
        if not self._tasks:
            return
        for socket in self._sockets:
            await socket.disconnect()
        _, pending = await asyncio.wait(self._tasks, timeout=_CEILING_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            _, pending = await asyncio.wait(pending, timeout=_CEILING_SECONDS)
        for task in self._tasks:
            # Retrieve, or it surfaces as unretrieved on a later test.
            if task.done():
                with suppress(asyncio.CancelledError, Exception):
                    task.result()
        if pending:
            raise AssertionError(
                f"{len(pending)} praxis-room socket task(s) were still running "
                f"{_CEILING_SECONDS}s after being hung up on and cancelled."
                f"{_pending_task_dump()}"
            )


@asynccontextmanager
async def running_rooms(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    squash_updates_above: int = 200,
    flush_debounce_seconds: float = 2.0,
) -> AsyncIterator[_Rooms]:
    """Patches the module singleton, which ``services.praxis`` reads per call."""
    sessions = _SharedSessionFactory(db_session)
    server = PraxisRoomServer(
        session_factory=sessions,
        squash_updates_above=squash_updates_above,
        flush_debounce_seconds=flush_debounce_seconds,
    )
    monkeypatch.setattr(praxis_room, "PRAXIS_ROOM_SERVER", server)
    # The mounted app holds its own server reference.
    monkeypatch.setattr(praxis_room.PRAXIS_ROOM_APP, "rooms", server)
    rooms = _Rooms(server, sessions)
    # By hand so ceilings bound start/stop only, not the test body.
    async with _bounded("the room server to start"):
        await server.__aenter__()
    try:
        yield rooms
    finally:
        await rooms.aclose()
        async with _bounded("the room server to stop"):
            await server.__aexit__(None, None, None)


@asynccontextmanager
async def client_doc(socket: _Socket) -> AsyncIterator[Doc]:
    """A real pycrdt client. Never seeds: all content comes from the server."""
    doc = Doc()
    provider = Provider(doc, _ChannelAdapter(socket))
    async with _bounded(f"the client on {socket.path} to connect"):
        await provider.__aenter__()
    try:
        yield doc
    finally:
        async with _bounded(f"the client on {socket.path} to disconnect"):
            await provider.__aexit__(None, None, None)


async def _wait_for(predicate: Callable[[], bool], description: str) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _TIMEOUT_SECONDS
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"timed out waiting for {description}{_pending_task_dump()}"
    )


def _body(doc: Doc) -> str:
    return str(doc.get(ROOM_BODY_KEY, type=Text))


async def _wait_for_body(doc: Doc, expected: str, who: str) -> None:
    await _wait_for(lambda: _body(doc) == expected, f"{who} to hold {expected!r}")


@pytest_asyncio.fixture
async def collab(
    db_session: AsyncSession,
    active_task: Task,
    character: Character,
    character2: Character,
) -> Praxis:
    praxis = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.collab,
        status=PraxisStatus.in_progress,
        title="Collab Praxis",
        body_text=SEED_BODY,
    )
    db_session.add(praxis)
    await db_session.flush()
    db_session.add_all(
        [
            PraxisMember(praxis_id=praxis.id, character_id=character.id),
            PraxisMember(praxis_id=praxis.id, character_id=character2.id),
        ]
    )
    await db_session.commit()
    await db_session.refresh(praxis)
    return praxis


async def test_first_client_receives_the_seeded_body(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(collab.id, account.id)
        assert socket.accepted.is_set()
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")


async def test_second_client_does_not_duplicate_the_seed(
    db_session, collab, account, account2, monkeypatch
) -> None:
    """Per-client seeding would merge into ``SEED_BODY * 2`` on both clients."""
    async with running_rooms(db_session, monkeypatch) as rooms:
        first = await rooms.open(collab.id, account.id)
        async with client_doc(first) as first_doc:
            await _wait_for_body(first_doc, SEED_BODY, "the first client")

            second = await rooms.open(collab.id, account2.id)
            async with client_doc(second) as second_doc:
                await _wait_for_body(second_doc, SEED_BODY, "the second client")
                assert _body(first_doc) == SEED_BODY
                assert _body(rooms.room_doc(collab.id)) == SEED_BODY


async def test_simultaneous_first_connections_seed_once(
    db_session, collab, account, account2, monkeypatch
) -> None:
    """Needs the lock around check-then-seed."""
    async with running_rooms(db_session, monkeypatch) as rooms:
        first, second = await asyncio.gather(
            rooms.open(collab.id, account.id),
            rooms.open(collab.id, account2.id),
        )
        async with client_doc(first) as first_doc, client_doc(second) as second_doc:
            await _wait_for_body(first_doc, SEED_BODY, "the first client")
            await _wait_for_body(second_doc, SEED_BODY, "the second client")
            assert _body(rooms.room_doc(collab.id)) == SEED_BODY


async def test_two_clients_editing_converge(
    db_session, collab, account, account2, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        first = await rooms.open(collab.id, account.id)
        second = await rooms.open(collab.id, account2.id)
        async with client_doc(first) as first_doc, client_doc(second) as second_doc:
            await _wait_for_body(first_doc, SEED_BODY, "the first client")
            await _wait_for_body(second_doc, SEED_BODY, "the second client")

            first_doc.get(ROOM_BODY_KEY, type=Text).insert(0, "one ")
            await _wait_for_body(second_doc, f"one {SEED_BODY}", "the second client")

            second_doc.get(ROOM_BODY_KEY, type=Text).insert(0, "two ")
            expected = f"two one {SEED_BODY}"
            await _wait_for_body(first_doc, expected, "the first client")
            await _wait_for_body(second_doc, expected, "the second client")


async def test_document_survives_a_room_restart(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        first = await rooms.open(collab.id, account.id)
        async with client_doc(first) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "kept ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"kept {SEED_BODY}", "the room"
            )
        await first.disconnect()
        await _wait_for(
            lambda: rooms.room_doc(collab.id) is None, "the empty room to be dropped"
        )

        rejoined = await rooms.open(collab.id, account.id)
        async with client_doc(rejoined) as doc:
            await _wait_for_body(doc, f"kept {SEED_BODY}", "the rejoining client")


# Each case: what the handshake presents. ``CORSMiddleware`` skips WebSockets, so
# the origin check is the only CSWSH guard.
_REFUSED_HANDSHAKES = {
    "non_member": lambda collab, account, other: (collab.id, other.id, {}),
    "no_cookie": lambda collab, account, other: (collab.id, None, {}),
    "foreign_origin": lambda collab, account, other: (
        collab.id, account.id, {"origin": "https://evil.example"}
    ),
    "missing_origin": lambda collab, account, other: (
        collab.id, account.id, {"origin": None}
    ),
    "unreadable_token": lambda collab, account, other: (
        collab.id, None, {"raw_token": "not-a-jwt"}
    ),
    "unknown_praxis": lambda collab, account, other: (
        collab.id + 10_000, account.id, {}
    ),
    "unknown_path": lambda collab, account, other: (
        collab.id, account.id, {"path": "/praxis/not-a-number"}
    ),
}
_ALSO_REFUSED_THROUGH_THE_MOUNT = ("non_member", "foreign_origin", "missing_origin")


@pytest.mark.parametrize(
    "case, through_mount",
    [(case, False) for case in _REFUSED_HANDSHAKES]
    + [(case, True) for case in _ALSO_REFUSED_THROUGH_THE_MOUNT],
)
async def test_a_bad_handshake_is_refused(
    db_session, collab, account, account3, character3, monkeypatch, case, through_mount
) -> None:
    assert settings.ROOM_ALLOW_MISSING_ORIGIN is False
    praxis_id, account_id, extra = _REFUSED_HANDSHAKES[case](collab, account, account3)
    if through_mount:
        extra = {
            **extra,
            "path": mounted_room_path(praxis_id),
            "through": fastapi_app,
        }
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(praxis_id, account_id, **extra)
        assert socket.closed.is_set()
        assert not socket.accepted.is_set()


async def test_missing_origin_is_allowed_when_configured(
    db_session, collab, account, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "ROOM_ALLOW_MISSING_ORIGIN", True)
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(collab.id, account.id, origin=None)
        assert socket.accepted.is_set()


# Through ``main.app``: Starlette's ``Mount`` sets ``root_path`` but leaves
# ``path`` whole, so the room app sees ``/rooms/praxis/12``.


async def test_member_handshake_through_the_mount_is_accepted(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(
            collab.id,
            account.id,
            path=mounted_room_path(collab.id),
            through=fastapi_app,
        )
        assert socket.accepted.is_set()
        assert not socket.closed.is_set()
        # Accepted is not served: the document must arrive too.
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "a client behind the mount")


async def test_kicked_member_socket_is_closed(
    db_session, collab, account, account2, character, character2, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        kickee = await rooms.open(collab.id, account2.id)
        async with client_doc(kickee) as doc:
            await _wait_for_body(doc, SEED_BODY, "the member about to be kicked")

            await kick_member(collab.id, character2.id, character.id, db_session)

            await _wait_for(kickee.closed.is_set, "the kicked member's socket to close")
            assert kickee.close_code == 1008


async def _close_via(action, rooms, collab, account, account2, *, closes: bool):
    """Run ``action`` against character2; return (their socket, the collaborator's).

    When it closes them, also prove their later edit never reaches ``body_text``.
    """
    victim = await rooms.open(collab.id, account2.id)
    mate = await rooms.open(collab.id, account.id)
    async with client_doc(victim) as doc, client_doc(mate) as mate_doc:
        await _wait_for_body(doc, SEED_BODY, "the member about to lose access")
        await _wait_for_body(mate_doc, SEED_BODY, "the collaborator")
        await action()
        if closes:
            await _wait_for(victim.closed.is_set, "the removed player's socket")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "ghost ")
            # The mate's edit is the control: once it lands, a flush has run.
            mate_doc.get(ROOM_BODY_KEY, type=Text).insert(0, "mate ")
            await _wait_for_record(
                rooms,
                collab.id,
                "the collaborator's flush",
                body_text=f"mate {SEED_BODY}",
            )
        else:
            await asyncio.sleep(0.3)
        return victim, mate


@pytest.mark.parametrize("path", ["ban", "suspend", "delete"])
async def test_removing_a_player_closes_their_socket_not_the_collaborators(
    path, db_session, collab, account, account2, character2, monkeypatch
) -> None:
    actions = {
        "ban": lambda: apply_ban(character2, True, db_session, actor_id=account.id),
        "suspend": lambda: suspend_account(
            account2.id, True, db_session, actor_id=account.id
        ),
        "delete": lambda: soft_delete_character(character2.id, db_session),
    }
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=0.05
    ) as rooms:
        victim, mate = await _close_via(
            actions[path], rooms, collab, account, account2, closes=True
        )
        assert victim.close_code == 1008
        assert not mate.closed.is_set()


async def test_unban_and_unsuspend_close_nothing(
    db_session, collab, account, account2, character2, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        victim, _ = await _close_via(
            lambda: _lift(db_session, account, account2, character2),
            rooms, collab, account, account2, closes=False,
        )
        assert not victim.closed.is_set()


async def _lift(db_session, account, account2, character2) -> None:
    await apply_ban(character2, False, db_session, actor_id=account.id)
    await suspend_account(account2.id, False, db_session, actor_id=account.id)


async def test_leaving_member_socket_is_closed(
    db_session, collab, account2, character2, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        leaver = await rooms.open(collab.id, account2.id)
        async with client_doc(leaver) as doc:
            await _wait_for_body(doc, SEED_BODY, "the member about to leave")

            await leave_praxis(collab.id, character2.id, db_session)

            await _wait_for(leaver.closed.is_set, "the leaver's socket to close")
            assert leaver.close_code == 1008


async def test_a_second_instance_refuses_to_start(test_engine) -> None:
    """Rooms are in-process; a process can't see its replica count (ADR-0073)."""
    held = await acquire_single_instance_lock(test_engine)
    try:
        with pytest.raises(RuntimeError, match="single-instance"):
            await acquire_single_instance_lock(test_engine, wait_seconds=0)
    finally:
        await held.close()

    reacquired = await acquire_single_instance_lock(test_engine)
    await reacquired.close()


async def test_the_lock_waits_out_a_departing_predecessor(
    test_engine, monkeypatch
) -> None:
    monkeypatch.setattr(praxis_room, "_LOCK_RETRY_SECONDS", 0.05)
    predecessor = await acquire_single_instance_lock(test_engine)

    async def let_go() -> None:
        await asyncio.sleep(0.1)
        await predecessor.close()

    release = asyncio.create_task(let_go())
    successor = await acquire_single_instance_lock(test_engine, wait_seconds=5)
    await release
    await successor.close()


async def test_store_squashes_its_history_losslessly(db_session, collab) -> None:
    """Straight at the store: rows via a socket would be a timing test."""
    store = praxis_room.PostgresYStore(
        room_name_for(collab.id),
        session_factory=_SharedSessionFactory(db_session),
        squash_updates_above=2,
    )
    doc = Doc()
    # Observe from before the seed, as a room does.
    updates: list[bytes] = []
    doc.observe(lambda event: updates.append(event.update))
    body = Text(SEED_BODY)
    doc[ROOM_BODY_KEY] = body
    for index in range(6):
        body.insert(0, f"{index} ")

    for update in updates:
        await store.write(update)
    assert len(updates) == 7

    assert await _update_count(db_session, collab.id) <= 3

    restored = Doc()
    await store.apply_updates(restored)
    assert str(restored.get(ROOM_BODY_KEY, type=Text)) == str(body)


async def _update_count(session: AsyncSession, praxis_id: int) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(PraxisRoomUpdate)
        .where(PraxisRoomUpdate.praxis_id == praxis_id)
    )


# The flush: the room is the only writer of a body (#1743).


async def _record(rooms: _Rooms, praxis_id: int) -> tuple[str | None, str | None]:
    """Past any identity map."""
    async with rooms.sessions() as session:
        row = (
            await session.execute(
                select(Praxis.title, Praxis.body_text).where(Praxis.id == praxis_id)
            )
        ).one()
    return row[0], row[1]


async def _wait_for_record(
    rooms: _Rooms,
    praxis_id: int,
    description: str,
    *,
    title: str | None = None,
    body_text: str | None = None,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _TIMEOUT_SECONDS
    while True:
        stored_title, stored_body = await _record(rooms, praxis_id)
        if (title is None or stored_title == title) and (
            body_text is None or stored_body == body_text
        ):
            return
        if loop.time() >= deadline:
            raise AssertionError(
                f"timed out waiting for {description}: the row holds "
                f"title={stored_title!r} body_text={stored_body!r}"
            )
        await asyncio.sleep(0.02)


async def test_an_edit_in_a_room_lands_in_body_text(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "typed ")
            await _wait_for_record(
                rooms,
                collab.id,
                "the debounced flush",
                body_text=f"typed {SEED_BODY}",
            )


async def test_a_non_creator_members_edit_reaches_the_record(
    db_session, collab, account2, monkeypatch
) -> None:
    """Any member may edit (ADR-0013); ``account2`` is not the creator."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account2.id)
        assert socket.accepted.is_set()
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the non-creator member")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "theirs too ")
            await _wait_for_record(
                rooms,
                collab.id,
                "the non-creator's flush",
                body_text=f"theirs too {SEED_BODY}",
            )


async def test_flushed_body_text_is_the_markdown_the_document_holds(
    db_session, collab, account, monkeypatch
) -> None:
    """Byte for byte (ADR-0073): every markdown reader reads this column."""
    markdown = "# A heading\n\n- one\n- two\n\n> quoted  \n\n**bold** and `code`\n"
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            body = doc.get(ROOM_BODY_KEY, type=Text)
            await _wait_for_body(doc, SEED_BODY, "the first client")
            del body[0 : len(SEED_BODY)]
            body.insert(0, markdown)
            await _wait_for_record(
                rooms, collab.id, "the flush", body_text=markdown
            )
            _, stored = await _record(rooms, collab.id)
            assert stored == str(body)


async def test_two_clients_editing_converge_into_one_body_text(
    db_session, collab, account, account2, monkeypatch
) -> None:
    """Both insertions must survive in the column, not just a change."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        first = await rooms.open(collab.id, account.id)
        second = await rooms.open(collab.id, account2.id)
        async with client_doc(first) as first_doc, client_doc(second) as second_doc:
            await _wait_for_body(first_doc, SEED_BODY, "the first client")
            await _wait_for_body(second_doc, SEED_BODY, "the second client")

            first_doc.get(ROOM_BODY_KEY, type=Text).insert(0, "one ")
            second_doc.get(ROOM_BODY_KEY, type=Text).insert(len(SEED_BODY), " two")

            await _wait_for(
                lambda: _body(first_doc) == _body(second_doc)
                and "one " in _body(first_doc)
                and " two" in _body(first_doc),
                "both clients to converge",
            )
            converged = _body(first_doc)
            assert SEED_BODY in converged
            await _wait_for_record(
                rooms, collab.id, "the converged flush", body_text=converged
            )


async def test_opening_a_room_alone_leaves_the_record_untouched(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
        await socket.disconnect()
        await _wait_for(
            lambda: rooms.room_doc(collab.id) is None, "the empty room to be dropped"
        )
    assert await _record(rooms, collab.id) == ("Collab Praxis", SEED_BODY)


async def test_a_praxis_whose_room_never_opened_keeps_its_body_text(
    db_session, collab, account, active_task, character, monkeypatch
) -> None:
    untouched = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Untouched",
        body_text="Never opened in a room.",
    )
    db_session.add(untouched)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=untouched.id, character_id=character.id))
    await db_session.commit()

    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "edited ")
            await _wait_for_record(
                rooms,
                collab.id,
                "the edited praxis",
                body_text=f"edited {SEED_BODY}",
            )

    assert await _record(rooms, untouched.id) == (
        "Untouched",
        "Never opened in a room.",
    )


async def test_the_title_key_flushes_to_praxis_title(
    db_session, collab, account, monkeypatch
) -> None:
    """The title is a last-write-wins map key."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_META_KEY, type=Map)[ROOM_TITLE_KEY] = "A renamed praxis"
            await _wait_for_record(
                rooms,
                collab.id,
                "the title flush",
                title="A renamed praxis",
                body_text=SEED_BODY,
            )


async def test_an_absent_title_key_never_blanks_the_praxis_title(
    db_session, collab, account, monkeypatch
) -> None:
    """Absent means "no remote value yet", not empty: nothing seeds it."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "body only ")
            await _wait_for_record(
                rooms,
                collab.id,
                "the flush",
                title="Collab Praxis",
                body_text=f"body only {SEED_BODY}",
            )


async def test_the_last_edit_before_a_room_closes_still_lands(
    db_session, collab, account, monkeypatch
) -> None:
    """The 30s debounce means only the closing flush can satisfy this."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=30.0) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "last words ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"last words {SEED_BODY}", "the room"
            )
        await socket.disconnect()
        await _wait_for_record(
            rooms,
            collab.id,
            "the closing flush",
            body_text=f"last words {SEED_BODY}",
        )


# The proposal: an edit cancels it, and nothing is ever refused (ADR-0079).


async def _stored_updates(rooms: _Rooms, praxis_id: int) -> list[bytes]:
    async with rooms.sessions() as session:
        rows = await session.execute(
            select(PraxisRoomUpdate.update)
            .where(PraxisRoomUpdate.praxis_id == praxis_id)
            .order_by(PraxisRoomUpdate.id)
        )
        return list(rows.scalars().all())


async def _every_stored_update(rooms: _Rooms) -> list[bytes]:
    async with rooms.sessions() as session:
        rows = await session.execute(select(PraxisRoomUpdate.update))
        return list(rows.scalars().all())


async def _settle() -> None:
    for _ in range(25):
        await asyncio.sleep(0.01)


async def _proposal(rooms: _Rooms, praxis_id: int) -> tuple[PraxisStatus, Any]:
    """Column select: the identity map may hold a stale ``Praxis``."""
    async with rooms.sessions() as session:
        row = (
            await session.execute(
                select(Praxis.status, Praxis.submit_proposed_at).where(
                    Praxis.id == praxis_id
                )
            )
        ).one()
    return row[0], row[1]


async def _wait_for_drafting(rooms: _Rooms, praxis_id: int, description: str) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _TIMEOUT_SECONDS
    while True:
        status, proposed_at = await _proposal(rooms, praxis_id)
        if status == PraxisStatus.in_progress and proposed_at is None:
            return
        if loop.time() >= deadline:
            raise AssertionError(
                f"timed out waiting for {description}: the row holds "
                f"status={status} submit_proposed_at={proposed_at!r}"
            )
        await asyncio.sleep(0.02)


async def test_typing_while_a_proposal_is_live_cancels_it(
    db_session, collab, account2, character, monkeypatch
) -> None:
    """ADR-0079: a CRDT text change by the holdout cancels the proposal."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        holdout = await rooms.open(collab.id, account2.id)
        async with client_doc(holdout) as doc:
            await _wait_for_body(doc, SEED_BODY, "the holdout")

            # `character` proposes over REST, not connected.
            proposed = await rooms.submit(collab.id, character.id)
            assert proposed.status == PraxisStatus.pending
            assert proposed.submit_proposed_at is not None

            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "not yet ")
            await _wait_for_drafting(
                rooms, collab.id, "the edit to cancel the proposal"
            )
            # Nobody is hung up on for writing.
            assert not holdout.closed.is_set()

        await _wait_for_record(
            rooms, collab.id, "the cancelled proposal's text", body_text=f"not yet {SEED_BODY}"
        )
        async with rooms.sessions() as session:
            approvals = (
                await session.execute(
                    select(PraxisMember.has_approved).where(
                        PraxisMember.praxis_id == collab.id
                    )
                )
            ).scalars().all()
        assert list(approvals) == [False, False]


def _offline_state(doc: Doc, words: str) -> str:
    """The browser's whole state after typing ``words`` the room never received."""
    offline = Doc()
    offline.apply_update(doc.get_update())
    offline.get(ROOM_BODY_KEY, type=Text).insert(0, words)
    return base64.b64encode(offline.get_update()).decode()


async def test_a_proposers_unsent_edits_are_proposed_not_cancelled(
    db_session, collab, account2, character, monkeypatch
) -> None:
    """#3611: merged edits are part of the proposal; the flush mustn't cancel it."""
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=0.05
    ) as rooms:
        holdout = await rooms.open(collab.id, account2.id)
        async with client_doc(holdout) as doc:
            await _wait_for_body(doc, SEED_BODY, "the holdout")
            state = _offline_state(doc, "offline ")

            proposed = await rooms.submit(collab.id, character.id, doc_state=state)
            assert proposed.status == PraxisStatus.pending
            await _wait_for_record(
                rooms, collab.id, "the proposed text", body_text=f"offline {SEED_BODY}"
            )
            status, proposed_at = await _proposal(rooms, collab.id)
            assert (status, proposed_at is not None) == (PraxisStatus.pending, True)

            # A duplicate of what the room already holds changes nothing.
            await rooms.submit(collab.id, character.id, doc_state=state)
            await _settle()
            assert (await _proposal(rooms, collab.id))[0] == PraxisStatus.pending

            # Another member's later edit still cancels.
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "later ")
            await _wait_for_drafting(rooms, collab.id, "the later edit to cancel")


async def _approved(rooms: _Rooms, praxis_id: int) -> dict[int, bool]:
    async with rooms.sessions() as session:
        rows = await session.execute(
            select(PraxisMember.character_id, PraxisMember.has_approved).where(
                PraxisMember.praxis_id == praxis_id
            )
        )
    return {cid: approved for cid, approved in rows}


@pytest.mark.parametrize("extra_members", [0, 1])
async def test_a_submit_that_changes_text_cancels_a_live_proposal(
    db_session, collab, account2, character, character2, character3,
    extra_members, monkeypatch,
) -> None:
    """ADR-0079: text the proposer never saw is a new proposal, not an approval."""
    if extra_members:
        db_session.add(PraxisMember(praxis_id=collab.id, character_id=character3.id))
        await db_session.commit()
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        holdout = await rooms.open(collab.id, account2.id)
        async with client_doc(holdout) as doc:
            await _wait_for_body(doc, SEED_BODY, "the holdout")
            await rooms.submit(collab.id, character2.id)  # B proposes
            state = _offline_state(doc, "unseen ")

            result = await rooms.submit(collab.id, character.id, doc_state=state)

        assert result.status == PraxisStatus.pending
        approved = await _approved(rooms, collab.id)
        assert approved[character.id] and not approved[character2.id]
        assert (await _proposal(rooms, collab.id))[1] is not None


async def test_a_submit_after_unflushed_socket_edits_cancels_the_proposal(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """The room already holds the text (unflushed), so the merge adds nothing."""
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            await rooms.submit(collab.id, character2.id)  # B proposes
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"unseen {SEED_BODY}", "the room"
            )
            state = base64.b64encode(doc.get_update()).decode()

            result = await rooms.submit(collab.id, character.id, doc_state=state)

        assert result.status == PraxisStatus.pending
        approved = await _approved(rooms, collab.id)
        assert approved[character.id] and not approved[character2.id]


async def test_an_approve_without_doc_state_cancels_on_unflushed_socket_edits(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """#3746: an API client sends no doc_state; the loaded room is compared anyway."""
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            await rooms.submit(collab.id, character2.id)  # B proposes
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"unseen {SEED_BODY}", "the room"
            )

            result = await rooms.submit(collab.id, character.id)

        assert result.status == PraxisStatus.pending
        approved = await _approved(rooms, collab.id)
        assert approved[character.id] and not approved[character2.id]


async def test_a_refused_submit_absorbs_nothing(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """The refusal rolls the merge back, so the edit is still nobody's proposal."""
    praxis_id, character_id, other_id = collab.id, character.id, character2.id
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(praxis_id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            await rooms.submit(praxis_id, other_id)  # B proposes
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(praxis_id), f"unseen {SEED_BODY}", "the room"
            )
            state = base64.b64encode(doc.get_update()).decode()

            async def no_proof(*_args: Any) -> bool:
                return False

            with monkeypatch.context() as patch:
                patch.setattr(collab_consensus, "_has_proof", no_proof)
                with pytest.raises(HTTPException) as refused:
                    await rooms.submit(praxis_id, character_id, doc_state=state)
            assert refused.value.status_code == 422
            async with rooms.sessions() as session:
                await session.rollback()  # get_db's answer to the raise

            await rooms.server._flushers[room_name_for(praxis_id)].write()

        assert (await _proposal(rooms, praxis_id))[1] is None


async def test_a_flush_between_the_commit_and_its_hook_keeps_the_proposal(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """A flush that lands after the row lock drops but before after_commit runs."""
    praxis_id, character_id, other_id = collab.id, character.id, character2.id
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(praxis_id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            await rooms.submit(praxis_id, other_id)  # B proposes
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(praxis_id), f"unseen {SEED_BODY}", "the room"
            )
            state = base64.b64encode(doc.get_update()).decode()
            flusher = rooms.server._flushers[room_name_for(praxis_id)]
            hook = flusher.absorb
            held: list[dict[str, str]] = []
            monkeypatch.setattr(flusher, "absorb", held.append)

            await rooms.submit(praxis_id, character_id, doc_state=state)
            await flusher.write()  # the window: committed, hook not yet run
            assert (await _proposal(rooms, praxis_id))[1] is not None
            hook(held[0])


async def test_a_flush_between_the_rollback_and_its_hook_still_cancels(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """The flush skips on_room_edit while the submit is in flight; once the
    submit rolls back, the unseen text must still cancel the proposal."""
    praxis_id, character_id, other_id = collab.id, character.id, character2.id
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(praxis_id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            await rooms.submit(praxis_id, other_id)  # B proposes
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(praxis_id), f"unseen {SEED_BODY}", "the room"
            )
            state = base64.b64encode(doc.get_update()).decode()
            flusher = rooms.server._flushers[room_name_for(praxis_id)]
            hook = flusher.forget
            monkeypatch.setattr(flusher, "forget", lambda: None)

            async def no_proof(*_args: Any) -> bool:
                return False

            with monkeypatch.context() as patch:
                patch.setattr(collab_consensus, "_has_proof", no_proof)
                with pytest.raises(HTTPException):
                    await rooms.submit(praxis_id, character_id, doc_state=state)
            async with rooms.sessions() as session:
                await session.rollback()
            await flusher.write()  # the window: rolled back, hook not yet run
            assert (await _proposal(rooms, praxis_id))[1] is not None
            hook()
    # the closing flush runs only if forget() left the document marked changed
    assert (await _proposal(rooms, praxis_id))[1] is None


async def test_a_cooldown_refused_submit_absorbs_nothing(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """429 takes the same post-merge refusal path as the 422 above. It needs the
    submitter to complete the praxis, so a lone member: an edit with others
    present clears their approvals first and the cooldown never applies."""
    praxis_id, character_id = collab.id, character.id
    await db_session.execute(
        delete(PraxisMember).where(PraxisMember.character_id == character2.id)
    )
    object.__setattr__(CURRENT_ERA, "praxis_post_cooldown_hours", 24)
    account.last_praxis_posted_at = datetime.now(timezone.utc)
    await db_session.commit()
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(praxis_id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the editor")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "unseen ")
            await _wait_for_body(
                rooms.room_doc(praxis_id), f"unseen {SEED_BODY}", "the room"
            )
            state = base64.b64encode(doc.get_update()).decode()

            with pytest.raises(HTTPException) as refused:
                await rooms.submit(praxis_id, character_id, doc_state=state)
            assert refused.value.status_code == 429
            async with rooms.sessions() as session:
                await session.rollback()  # get_db's answer to the raise

            flusher = rooms.server._flushers[room_name_for(praxis_id)]
            assert flusher._absorbed is None
            assert flusher._expected is None


async def test_a_submit_that_changes_nothing_still_approves(
    db_session, collab, account2, character, character2, monkeypatch
) -> None:
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        holdout = await rooms.open(collab.id, account2.id)
        async with client_doc(holdout) as doc:
            await _wait_for_body(doc, SEED_BODY, "the holdout")
            await rooms.submit(collab.id, character2.id)
            same = base64.b64encode(doc.get_update()).decode()

            result = await rooms.submit(collab.id, character.id, doc_state=same)

        assert result.status == PraxisStatus.submitted


async def test_an_awareness_update_never_cancels_a_proposal(
    db_session, collab, account2, character, monkeypatch
) -> None:
    """Pins the document observer: an inbound-message hook can't tell a caret
    from a keystroke."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=0.05) as rooms:
        socket = await rooms.open(collab.id, account2.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the holdout")
            await rooms.submit(collab.id, character.id)

            awareness = Awareness(Doc())
            awareness.set_local_state({"user": {"name": "Holdout"}, "cursor": 7})
            await socket.send_bytes(
                create_awareness_message(
                    awareness.encode_awareness_update([awareness.client_id])
                )
            )
            await _settle()

            status, proposed_at = await _proposal(rooms, collab.id)
            assert status == PraxisStatus.pending
            assert proposed_at is not None


async def _announce(socket: _Socket, state: dict[str, Any]) -> int:
    awareness = Awareness(Doc())
    awareness.set_local_state(state)
    update = awareness.encode_awareness_update([awareness.client_id])
    await socket.send_bytes(create_awareness_message(update))
    return awareness.client_id


async def _mirror_awareness(socket: _Socket, mirror: Awareness) -> None:
    async for frame in socket:
        if frame[0] == YMessageType.AWARENESS:
            mirror.apply_awareness_update(read_message(frame[1:]), "remote")


@pytest.mark.parametrize("how", ["drop", "kick"])
async def test_a_departing_socket_takes_its_awareness_with_it(
    how, db_session, collab, account, account2, character, character2, monkeypatch
) -> None:
    """A closed tab sends no awareness disconnect; the room clears it instead
    (#3211)."""
    async with running_rooms(db_session, monkeypatch) as rooms:
        stayer = await rooms.open(collab.id, account.id)
        leaver = await rooms.open(collab.id, account2.id)
        mirror = Awareness(Doc())
        peer = asyncio.create_task(_mirror_awareness(stayer, mirror))
        try:
            stayer_id = await _announce(stayer, {"user": {"name": "Stayer"}})
            leaver_id = await _announce(leaver, {"user": {"name": "Leaver"}})
            room = rooms.server.rooms[room_name_for(collab.id)]
            await _wait_for(
                lambda: {stayer_id, leaver_id} <= set(mirror.states),
                "the peer to see both members",
            )

            if how == "drop":
                await leaver.disconnect()
            else:
                await kick_member(collab.id, character2.id, character.id, db_session)
            await _wait_for(
                lambda: leaver_id not in mirror.states,
                "the peer to be told the leaver is gone",
            )

            assert leaver_id not in room.awareness.states
            assert stayer_id in room.awareness.states
            assert stayer_id in mirror.states
        finally:
            peer.cancel()
            with suppress(asyncio.CancelledError):
                await peer


async def test_withdrawing_a_proposal_has_the_same_effect_as_an_edit(
    db_session, collab, account2, character, character2, monkeypatch
) -> None:
    """ADR-0079; the withdrawer is deliberately not the proposer."""
    async with running_rooms(db_session, monkeypatch) as rooms:
        await submit_praxis(collab.id, character.id, db_session)
        reopened = await unsubmit_praxis(collab.id, character2.id, db_session)

        assert reopened.status == PraxisStatus.in_progress
        assert [member.has_approved for member in reopened.members] == [False, False]
        assert reopened.submit_proposed_at is None

        socket = await rooms.open(collab.id, account2.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the reopening client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "withdrawn ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"withdrawn {SEED_BODY}", "the room"
            )


async def test_unsubmit_after_publish_carries_a_newer_room_generation(
    db_session, collab, character, character2, monkeypatch
) -> None:
    """#3644: a browser's offline copy is told apart from the reseed by this."""
    async with running_rooms(db_session, monkeypatch):
        before = collab.room_generation
        await submit_praxis(collab.id, character.id, db_session)
        await submit_praxis(collab.id, character2.id, db_session)
        reopened = await unsubmit_praxis(collab.id, character2.id, db_session)

        assert reopened.room_generation == before + 1
        out = await build_praxis_out(reopened, db_session, viewer=character2)
        assert out.room_generation == before + 1


async def test_publishing_discards_the_document_and_keeps_the_body(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """30s debounce: only the publish-time flatten can write the body."""
    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=30.0) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "final ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"final {SEED_BODY}", "the room"
            )
            assert await _stored_updates(rooms, collab.id) != []

            await rooms.submit(collab.id, character.id)          # Propose
            published = await rooms.submit(collab.id, character2.id)  # Approve → Live

        assert published.status == PraxisStatus.submitted
        assert await _stored_updates(rooms, collab.id) == []
        assert await _record(rooms, collab.id) == ("Collab Praxis", f"final {SEED_BODY}")


async def test_a_submit_carries_edits_the_room_never_received(
    db_session, active_task, character, account, monkeypatch
) -> None:
    """#3611: sockets give no ack, so the request itself carries the browser's doc."""
    solo = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Solo Praxis",
        body_text=SEED_BODY,
    )
    db_session.add(solo)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=solo.id, character_id=character.id))
    await db_session.commit()

    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=30
    ) as rooms:
        socket = await rooms.open(solo.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the solo author")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "synced ")
            await _wait_for_body(
                rooms.room_doc(solo.id), f"synced {SEED_BODY}", "the room"
            )
            offline = Doc()
            offline.apply_update(doc.get_update())
            offline.get(ROOM_BODY_KEY, type=Text).insert(0, "OFFLINE ")
            state = base64.b64encode(offline.get_update()).decode()

            published = await rooms.submit(solo.id, character.id, doc_state=state)
            assert await _record(rooms, solo.id) == (
                "Solo Praxis",
                f"OFFLINE synced {SEED_BODY}",
            )

        assert published.status == PraxisStatus.submitted


async def test_an_oversized_or_garbled_doc_state_is_refused(
    db_session, active_task, character, monkeypatch
) -> None:
    solo = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Solo Praxis",
        body_text=SEED_BODY,
    )
    db_session.add(solo)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=solo.id, character_id=character.id))
    await db_session.commit()

    big = base64.b64encode(bytes(praxis_room._MAX_CLIENT_UPDATE_BYTES + 1)).decode()
    async with running_rooms(db_session, monkeypatch) as rooms:
        # Opened outside the harness's session lock; a cold open would deadlock.
        await rooms.server.get_room(room_name_for(solo.id))
        cases = (
            (big, 413, "PRAXIS_DOC_UPDATE_TOO_LARGE"),
            ("not base64!", 422, "PRAXIS_DOC_UPDATE_INVALID"),
            ("AAEC", 422, "PRAXIS_DOC_UPDATE_INVALID"),
        )
        for state, status, code in cases:
            with pytest.raises(HTTPException) as refused:
                await rooms.submit(solo.id, character.id, doc_state=state)
            assert refused.value.status_code == status
            assert refused.value.detail["code"] == code


async def test_a_solo_seal_flattens_the_live_room_into_the_record(
    db_session, active_task, character, account, monkeypatch
) -> None:
    """Solo seals with no proposal and ``abandon()`` cancels the closing flush.
    Covers duels too (ADR-0011)."""
    solo = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Solo Praxis",
        body_text=SEED_BODY,
    )
    db_session.add(solo)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=solo.id, character_id=character.id))
    await db_session.commit()

    async with running_rooms(db_session, monkeypatch, flush_debounce_seconds=30.0) as rooms:
        socket = await rooms.open(solo.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the solo author")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "last sentence ")
            await _wait_for_body(
                rooms.room_doc(solo.id), f"last sentence {SEED_BODY}", "the room"
            )

            published = await submit_praxis(solo.id, character.id, db_session)

        assert published.status == PraxisStatus.submitted
        assert await _stored_updates(rooms, solo.id) == []
        assert await _record(rooms, solo.id) == (
            "Solo Praxis",
            f"last sentence {SEED_BODY}",
        )


async def test_reopening_a_published_praxis_seeds_a_fresh_document_once(
    db_session, collab, account, account2, character, character2, monkeypatch
) -> None:
    """A surviving document merged with a fresh seed would double (#1740)."""
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            doc.get(ROOM_BODY_KEY, type=Text).insert(0, "published ")
            await _wait_for_body(
                rooms.room_doc(collab.id), f"published {SEED_BODY}", "the room"
            )
            await rooms.submit(collab.id, character.id)     # Propose
            await rooms.submit(collab.id, character2.id)    # Approve → Live

        await unsubmit_praxis(collab.id, character2.id, db_session)

        rejoined = await rooms.open(collab.id, account2.id)
        async with client_doc(rejoined) as doc:
            await _wait_for_body(doc, f"published {SEED_BODY}", "the rejoining client")
            assert _body(rooms.room_doc(collab.id)) == f"published {SEED_BODY}"


async def test_text_a_member_deleted_does_not_outlive_the_draft(
    db_session, collab, account, character, character2, monkeypatch
) -> None:
    """Privacy: a CRDT keeps deleted text, so the discard deletes the rows.

    Real squash policy: squashing GCs deletions only past
    ``_SQUASH_UPDATES_ABOVE``; the raw tail below keeps them verbatim.
    """
    secret = "MY NEIGHBOURS REAL NAME"
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for_body(doc, SEED_BODY, "the first client")
            body = doc.get(ROOM_BODY_KEY, type=Text)
            body.insert(0, secret)
            await _wait_for_body(
                rooms.room_doc(collab.id), f"{secret}{SEED_BODY}", "the room"
            )
            del body[0 : len(secret)]
            await _wait_for_body(rooms.room_doc(collab.id), SEED_BODY, "the retraction")

            # Premise: the secret is on disk while the draft lives.
            stored = await _stored_updates(rooms, collab.id)
            assert any(secret.encode() in update for update in stored), (
                "the tombstone premise failed: no retained update holds the deleted "
                "text, so this test would pass without discarding anything"
            )

            await rooms.submit(collab.id, character.id)     # Propose
            await rooms.submit(collab.id, character2.id)    # Approve → Live

        assert await _stored_updates(rooms, collab.id) == []
        for update in await _every_stored_update(rooms):
            assert secret.encode() not in update
        assert await _record(rooms, collab.id) == ("Collab Praxis", SEED_BODY)


@pytest.mark.parametrize("kind", [PraxisType.solo, PraxisType.duel, PraxisType.collab])
async def test_a_doc_state_on_a_live_praxis_is_refused_and_opens_no_room(
    db_session, active_task, character, monkeypatch, kind
) -> None:
    live = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=kind,
        status=PraxisStatus.submitted,
        title="Honest proof",
        body_text=SEED_BODY,
    )
    db_session.add(live)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=live.id, character_id=character.id))
    await db_session.commit()

    rewrite = Doc()
    rewrite.get(ROOM_BODY_KEY, type=Text).insert(0, "EDITED AFTER VOTING")
    state = base64.b64encode(rewrite.get_update()).decode()
    async with running_rooms(db_session, monkeypatch) as rooms:
        with pytest.raises(HTTPException) as refused:
            await rooms.submit(live.id, character.id, doc_state=state)
        assert refused.value.status_code == 409
        assert refused.value.detail["code"] == "PRAXIS_ALREADY_LIVE"
        assert rooms.room_doc(live.id) is None
    await db_session.refresh(live)
    assert (live.title, live.body_text) == ("Honest proof", SEED_BODY)
    assert live.status == PraxisStatus.submitted


async def test_a_refused_doc_state_leaves_a_voted_duel_score_unchanged(
    db_session, active_task, character, character2, character3, monkeypatch
) -> None:
    live = await make_solo_praxis(
        db_session, active_task, character, body_text=SEED_BODY
    )
    opponent = await make_solo_praxis(db_session, active_task, character2)
    await cast_vote(db_session, live, character3, 4)
    db_session.add(
        Duel(
            task_id=active_task.id,
            challenger_praxis_id=live.id,
            opponent_character_id=character2.id,
            opponent_praxis_id=opponent.id,
            status=DuelStatus.settled,
            accepted_at=datetime.now(timezone.utc),
        )
    )
    await recalculate_character_stats(character.id, db_session)
    await db_session.commit()

    async def score() -> int:
        stats = await db_session.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        await db_session.refresh(stats)
        return stats.score

    before = await score()
    assert before > 0
    rewrite = Doc()
    rewrite.get(ROOM_BODY_KEY, type=Text).insert(0, "EDITED AFTER VOTING")
    state = base64.b64encode(rewrite.get_update()).decode()
    async with running_rooms(db_session, monkeypatch) as rooms:
        with pytest.raises(HTTPException) as refused:
            await rooms.submit(live.id, character.id, doc_state=state)
        assert refused.value.status_code == 409
    assert await score() == before
    await recalculate_character_stats(character.id, db_session)
    assert await score() == before


async def test_a_live_praxis_refuses_the_room_handshake(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        collab.status = PraxisStatus.submitted
        await db_session.commit()
        socket = await rooms.open(collab.id, account.id)
        assert socket.closed.is_set()
        assert not socket.accepted.is_set()



async def test_an_over_cap_room_document_is_not_flushed(
    db_session, collab, account, monkeypatch
) -> None:
    """Over-cap text can only be in the store (a restart, an old row); never flushed."""
    db_session.add(
        PraxisRoomUpdate(praxis_id=collab.id, update=_over_cap_doc().get_update())
    )
    await db_session.commit()
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=0.05
    ) as rooms:
        socket = await rooms.open(collab.id, account.id)
        async with client_doc(socket) as doc:
            await _wait_for(
                lambda: len(str(doc.get(ROOM_BODY_KEY, type=Text))) > PRAXIS_BODY_MAX,
                "the over-cap document",
            )
            long_title = "t" * (PRAXIS_TITLE_MAX + 1)
            doc.get(ROOM_META_KEY, type=Map)[ROOM_TITLE_KEY] = long_title
            await asyncio.sleep(0.4)
            assert await _record(rooms, collab.id) == ("Collab Praxis", SEED_BODY)


async def _over_cap_solo(db_session, active_task, character) -> Praxis:
    solo = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Solo Praxis",
        body_text=SEED_BODY,
    )
    db_session.add(solo)
    await db_session.flush()
    db_session.add(PraxisMember(praxis_id=solo.id, character_id=character.id))
    await db_session.commit()
    return solo


def _over_cap_doc() -> Doc:
    doc = Doc()
    doc[ROOM_BODY_KEY] = Text("x" * (PRAXIS_BODY_MAX + 1))
    return doc


async def test_a_submit_with_an_over_cap_draft_is_refused_and_changes_nothing(
    db_session, active_task, character, monkeypatch
) -> None:
    solo = await _over_cap_solo(db_session, active_task, character)
    state = base64.b64encode(_over_cap_doc().get_update()).decode()
    async with running_rooms(db_session, monkeypatch) as rooms:
        await rooms.server.get_room(room_name_for(solo.id))
        with pytest.raises(HTTPException) as refused:
            await rooms.submit(solo.id, character.id, doc_state=state)
        assert refused.value.status_code == 413
        assert refused.value.detail["code"] == "PRAXIS_DOC_UPDATE_INVALID"
        assert await _record(rooms, solo.id) == ("Solo Praxis", SEED_BODY)
        assert (await db_session.get(Praxis, solo.id)).status != PraxisStatus.submitted


async def test_an_over_cap_submit_stores_nothing_and_strands_no_room(
    db_session, active_task, character, monkeypatch
) -> None:
    solo = await _over_cap_solo(db_session, active_task, character)
    state = base64.b64encode(_over_cap_doc().get_update()).decode()
    async with running_rooms(db_session, monkeypatch) as rooms:
        # Straight at the server: a cold open under the harness's lock deadlocks.
        with pytest.raises(HTTPException) as refused:
            await praxis_room.merge_client_state(solo.id, state)
        assert refused.value.status_code == 413
        assert room_name_for(solo.id) not in rooms.server.rooms
        before = await _stored_updates(rooms, solo.id)

        await rooms.server.get_room(room_name_for(solo.id))
        stored = await _stored_updates(rooms, solo.id)
        with pytest.raises(HTTPException):
            await praxis_room.merge_client_state(solo.id, state)
        body = rooms.room_doc(solo.id).get(ROOM_BODY_KEY, type=Text)
        assert str(body) == SEED_BODY
        assert await _stored_updates(rooms, solo.id) == stored
        assert len(stored) >= len(before)


async def test_a_socket_update_over_the_cap_is_dropped_before_it_is_stored(
    db_session, collab, account, monkeypatch
) -> None:
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(collab.id, account.id)
        name = room_name_for(collab.id)
        # Registered is not seeded: ready flips only after the seed is stored.
        await _wait_for(
            lambda: name in rooms.server.rooms and rooms.server.rooms[name].ready,
            "the seeded room",
        )
        doc = rooms.room_doc(collab.id)
        stored = await _stored_updates(rooms, collab.id)
        await socket.send_bytes(create_update_message(_over_cap_doc().get_update()))
        await _wait_for(socket.closed.is_set, "the socket to be refused")
        assert socket.close_code == 1008
        assert await _stored_updates(rooms, collab.id) == stored
        assert len(str(doc.get(ROOM_BODY_KEY, type=Text))) <= PRAXIS_BODY_MAX


async def test_deleting_a_praxis_evicts_its_room_and_sockets(
    db_session, active_task, character, account, monkeypatch
) -> None:
    solo = await _over_cap_solo(db_session, active_task, character)
    name = room_name_for(solo.id)
    async with running_rooms(db_session, monkeypatch) as rooms:
        socket = await rooms.open(solo.id, account.id)
        await _wait_for(lambda: name in rooms.server._flushers, "the flusher")
        async with rooms.sessions() as session:
            await delete_praxis(solo.id, character.id, session)
            await session.commit()
        await _wait_for(socket.closed.is_set, "the socket to be revoked")
        assert socket.close_code == 1008
        assert name not in rooms.server.rooms
        assert name not in rooms.server._flushers


async def test_publishing_after_a_restart_cannot_drop_an_over_cap_document(
    db_session, active_task, character, monkeypatch
) -> None:
    """Stored updates outlive the room; the flush skip must not become lost text."""
    solo = await _over_cap_solo(db_session, active_task, character)
    db_session.add(
        PraxisRoomUpdate(praxis_id=solo.id, update=_over_cap_doc().get_update())
    )
    await db_session.commit()
    async with running_rooms(db_session, monkeypatch) as rooms:
        # Not via rooms.submit: it holds the one session lock the cold read needs.
        with pytest.raises(HTTPException) as refused:
            await rooms.server.discard_document(solo, db_session)
        assert refused.value.status_code == 413
        assert len(await _stored_updates(rooms, solo.id)) == 1


async def test_a_lapsed_collab_with_an_over_cap_draft_stays_unsealed(
    db_session, active_task, character, monkeypatch
) -> None:
    """A read path's lazy seal must skip the 413, not raise it on every read."""
    import services.collab_consensus as collab_consensus

    collab = await _over_cap_solo(db_session, active_task, character)
    collab.type = PraxisType.collab
    collab.status = PraxisStatus.pending
    db_session.add(
        PraxisRoomUpdate(praxis_id=collab.id, update=_over_cap_doc().get_update())
    )
    await db_session.commit()

    async def _proof(*_args: Any) -> bool:
        return True

    monkeypatch.setattr(collab_consensus, "_has_proof", _proof)
    async with running_rooms(db_session, monkeypatch):
        await db_session.refresh(collab, ["members"])
        await collab_consensus.seal_to_live(collab, db_session, CURRENT_ERA)
        assert collab.status == PraxisStatus.pending
        assert collab.submitted_at is None


async def test_era_close_leaves_a_lapsed_over_cap_collab_unsealed(
    db_session, active_task, character, era, monkeypatch
) -> None:
    collab = await _over_cap_solo(db_session, active_task, character)
    collab.type = PraxisType.collab
    collab.status = PraxisStatus.pending
    collab.submit_proposed_at = datetime.now(timezone.utc) - timedelta(
        days=CURRENT_ERA.collab_auto_submit_days + 1
    )
    db_session.add(
        PraxisRoomUpdate(praxis_id=collab.id, update=_over_cap_doc().get_update())
    )
    await attach_proof(db_session, collab)
    await db_session.commit()

    async with running_rooms(db_session, monkeypatch):
        sealed = await collab_consensus.seal_lapsed_at_era_close(
            db_session, era, CURRENT_ERA
        )

    assert sealed == set()
    assert collab.status == PraxisStatus.pending
    assert collab.submitted_at is None


@pytest.mark.parametrize("socket_holds_room", [False, True])
async def test_a_submit_on_an_unopened_room_stores_its_text(
    db_session, collab, account, account2, character, character2, character3,
    socket_holds_room, monkeypatch,
) -> None:
    """#3992: the first update into a freshly opened room must reach the rows."""
    db_session.add(PraxisMember(praxis_id=collab.id, character_id=character3.id))
    await db_session.commit()
    async with running_rooms(
        db_session, monkeypatch, flush_debounce_seconds=0.05
    ) as rooms:
        seeder = await rooms.open(collab.id, account2.id)
        async with client_doc(seeder) as doc:
            await _wait_for_body(doc, SEED_BODY, "the seed")
        await seeder.disconnect()
        await _wait_for(lambda: rooms.room_doc(collab.id) is None, "room to unload")
        offline = Doc()
        for update in await _stored_updates(rooms, collab.id):
            offline.apply_update(update)
        offline.get(ROOM_BODY_KEY, type=Text).insert(0, "PROPOSED ")
        state = base64.b64encode(offline.get_update()).decode()
        if socket_holds_room:
            await rooms.open(collab.id, account.id)
            # The socket is accepted before its room opens; a submit racing that
            # open deadlocks on the harness lock (production has no such lock).
            await _wait_for(
                lambda: getattr(
                    rooms.server.rooms.get(room_name_for(collab.id)), "ready", False
                )
                and rooms.server.rooms[room_name_for(collab.id)].ydoc_observed.is_set(),
                "the socket's room to open",
            )

        await rooms.submit(collab.id, character.id, doc_state=state)
        proposed_at = (await _proposal(rooms, collab.id))[1]
        assert proposed_at is not None

        async with asyncio.timeout(_TIMEOUT_SECONDS):
            while await _update_count(rooms.sessions._session, collab.id) < 2:
                await asyncio.sleep(0.02)
        await _wait_for_record(
            rooms, collab.id, "the flush", body_text=f"PROPOSED {SEED_BODY}"
        )
        name = room_name_for(collab.id)
        async with rooms.server._open_lock:
            await rooms.server._evict_locked(name, rooms.server.rooms.get(name))
        reader = await rooms.open(collab.id, account2.id)
        async with client_doc(reader) as doc:
            await _wait_for_body(doc, f"PROPOSED {SEED_BODY}", "the reloaded room")
            again = base64.b64encode(doc.get_update()).decode()
            await rooms.submit(collab.id, character2.id, doc_state=again)

        assert await _approved(rooms, collab.id) == {
            character.id: True,
            character2.id: True,
            character3.id: False,
        }
        assert (await _proposal(rooms, collab.id))[1] == proposed_at


async def test_a_room_whose_observer_never_arms_is_dropped_and_refused(
    db_session, collab, monkeypatch,
) -> None:
    async def never_armed(self) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(YRoom, "_watch_ready", never_armed)
    monkeypatch.setattr(praxis_room, "_OBSERVER_WAIT_SECONDS", 0.05)
    async with running_rooms(db_session, monkeypatch) as rooms:
        with pytest.raises(HTTPException) as caught:
            await rooms.server.get_room(room_name_for(collab.id))

        assert caught.value.status_code == 503
        assert caught.value.detail["code"] == "PRAXIS_ROOM_UNAVAILABLE"
        assert rooms.room_doc(collab.id) is None
