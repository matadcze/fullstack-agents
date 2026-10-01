"""HTTP-level tests for audit event listing, filtering, pagination and scoping."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update

from src.domain.entities import AuditEvent, User
from src.domain.value_objects import EventType
from src.infrastructure.auth.jwt_provider import JWTProvider
from src.infrastructure.database.models import AuditEventModel
from src.infrastructure.repositories import AuditEventRepositoryImpl, UserRepositoryImpl

AUDIT = "/api/v1/audit"
RESOURCE_A = uuid4()
RESOURCE_B = uuid4()


@dataclass
class SeededAudit:
    owner: object
    other: object
    events: list[AuditEvent]

    def owner_events(self, predicate=lambda e: True) -> list[str]:
        matching = [e for e in self.events if e.user_id == self.owner.id and predicate(e)]
        return [str(e.id) for e in sorted(matching, key=lambda e: e.created_at, reverse=True)]


@pytest.fixture
async def seeded(register_user, db_sessions):
    owner = await register_user("owner@example.com")
    other = await register_user("other@example.com")
    specs = [
        (owner, EventType.USER_LOGGED_IN, None, datetime(2026, 1, 1, 9)),
        (owner, EventType.RESOURCE_CREATED, RESOURCE_A, datetime(2026, 1, 5, 12)),
        (owner, EventType.RESOURCE_UPDATED, RESOURCE_A, datetime(2026, 1, 10, 12)),
        (owner, EventType.RESOURCE_CREATED, RESOURCE_B, datetime(2026, 1, 15, 12)),
        (owner, EventType.USER_LOGGED_IN, None, datetime(2026, 1, 20, 9)),
        (other, EventType.USER_LOGGED_IN, None, datetime(2026, 1, 3, 9)),
        (other, EventType.RESOURCE_CREATED, RESOURCE_A, datetime(2026, 1, 6, 12)),
    ]
    events = [
        AuditEvent(
            user_id=user.id,
            event_type=event_type,
            resource_id=resource_id,
            created_at=created_at,
            details={"n": index},
        )
        for index, (user, event_type, resource_id, created_at) in enumerate(specs)
    ]
    async with db_sessions.begin() as session:
        repo = AuditEventRepositoryImpl(session)
        generated_events, total = await repo.list()
        assert total == 4
        for index, generated_event in enumerate(generated_events):
            generated_event.created_at = datetime(2026, 1, 21, 9) + timedelta(seconds=index)
            await session.execute(
                update(AuditEventModel)
                .where(AuditEventModel.id == generated_event.id)
                .values(created_at=generated_event.created_at)
            )
        for event in events:
            await repo.create(event)
    return SeededAudit(owner=owner, other=other, events=generated_events + events)


def ids(response) -> list[str]:
    return [item["id"] for item in response.json()["items"]]


async def test_lists_only_the_callers_events_newest_first(client, seeded):
    response = await client.get(AUDIT, headers=seeded.owner.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 7
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert ids(response) == seeded.owner_events()
    assert {item["user_id"] for item in body["items"]} == {str(seeded.owner.id)}
    expected_details = {str(event.id): event.details for event in seeded.events}
    assert all(item["details"] == expected_details[item["id"]] for item in body["items"])


async def test_other_user_sees_only_their_own_events(client, seeded):
    response = await client.get(AUDIT, headers=seeded.other.headers)

    assert response.json()["total"] == 4
    assert {item["user_id"] for item in response.json()["items"]} == {str(seeded.other.id)}


async def test_filter_by_resource_does_not_leak_other_users_events(client, seeded):
    response = await client.get(
        AUDIT, headers=seeded.other.headers, params={"resource_id": str(RESOURCE_A)}
    )

    assert response.json()["total"] == 1
    assert response.json()["items"][0]["user_id"] == str(seeded.other.id)


async def test_user_without_events_gets_empty_page(client, db_sessions, seeded):
    newcomer = User(email="newcomer@example.com", password_hash="unused")
    async with db_sessions.begin() as session:
        await UserRepositoryImpl(session).create(newcomer)
    headers = {"Authorization": f"Bearer {JWTProvider.create_access_token(newcomer.id)}"}

    response = await client.get(AUDIT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "page_size": 50, "total": 0}


async def test_filter_by_event_type(client, seeded):
    response = await client.get(
        AUDIT, headers=seeded.owner.headers, params={"event_type": "RESOURCE_CREATED"}
    )

    assert response.json()["total"] == 2
    assert ids(response) == seeded.owner_events(
        lambda e: e.event_type == EventType.RESOURCE_CREATED
    )


async def test_filter_by_resource_id(client, seeded):
    response = await client.get(
        AUDIT, headers=seeded.owner.headers, params={"resource_id": str(RESOURCE_A)}
    )

    assert response.json()["total"] == 2
    assert ids(response) == seeded.owner_events(lambda e: e.resource_id == RESOURCE_A)


async def test_date_range_bounds_are_inclusive(client, seeded):
    response = await client.get(
        AUDIT,
        headers=seeded.owner.headers,
        params={"start_date": "2026-01-05T12:00:00", "end_date": "2026-01-15T12:00:00"},
    )

    assert response.json()["total"] == 3
    assert ids(response) == seeded.owner_events(
        lambda e: datetime(2026, 1, 5, 12) <= e.created_at <= datetime(2026, 1, 15, 12)
    )


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"start_date": "2026-01-16T00:00:00"}, 3),
        ({"end_date": "2026-01-04T23:59:59"}, 1),
        ({"start_date": "2026-02-01T00:00:00"}, 0),
        ({"start_date": "2026-01-20T00:00:00", "end_date": "2026-01-01T00:00:00"}, 0),
    ],
    ids=["open-ended-start", "open-ended-end", "after-all-events", "inverted-range"],
)
async def test_partial_date_ranges(client, seeded, params, expected):
    response = await client.get(AUDIT, headers=seeded.owner.headers, params=params)

    assert response.status_code == 200
    assert response.json()["total"] == expected
    assert len(response.json()["items"]) == expected


async def test_combined_filters_are_intersected(client, seeded):
    response = await client.get(
        AUDIT,
        headers=seeded.owner.headers,
        params={
            "event_type": "RESOURCE_CREATED",
            "resource_id": str(RESOURCE_A),
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-01-31T00:00:00",
        },
    )

    assert ids(response) == seeded.owner_events(
        lambda e: e.event_type == EventType.RESOURCE_CREATED and e.resource_id == RESOURCE_A
    )
    assert response.json()["total"] == 1


async def test_pagination_reports_filtered_total_and_slices_in_order(client, seeded):
    expected = seeded.owner_events()
    pages = []
    for page in (1, 2, 3, 4):
        response = await client.get(
            AUDIT, headers=seeded.owner.headers, params={"page": page, "page_size": 2}
        )
        body = response.json()
        assert body["total"] == 7
        assert body["page"] == page
        assert body["page_size"] == 2
        pages.append(ids(response))

    assert [len(p) for p in pages] == [2, 2, 2, 1]
    assert sum(pages, []) == expected


async def test_page_past_the_end_is_empty_but_keeps_total(client, seeded):
    response = await client.get(
        AUDIT, headers=seeded.owner.headers, params={"page": 99, "page_size": 10}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 7


@pytest.mark.parametrize(
    "params",
    [
        {"event_type": "NOT_A_TYPE"},
        {"resource_id": "not-a-uuid"},
        {"start_date": "yesterday"},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
    ],
    ids=["event-type", "resource-id", "start-date", "page-zero", "page-size-zero", "page-size-max"],
)
async def test_invalid_query_parameters_are_rejected(client, seeded, params):
    response = await client.get(AUDIT, headers=seeded.owner.headers, params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ValidationError"


async def test_unknown_resource_returns_nothing(client, seeded):
    response = await client.get(
        AUDIT, headers=seeded.owner.headers, params={"resource_id": str(UUID(int=0))}
    )

    assert response.json() == {"items": [], "page": 1, "page_size": 50, "total": 0}
