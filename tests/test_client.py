# -*- coding: utf-8 -*-
import os
import ssl
from datetime import datetime
from typing import List
from unittest import TestCase
from uuid import UUID, uuid4

from grpc import RpcError, StatusCode
from grpc._channel import _MultiThreadedRendezvous, _RPCState
from grpc._cython.cygrpc import IntegratedCall

import esdbclient.protos.Grpc.persistent_pb2 as grpc_persistent
from esdbclient.client import EsdbClient
from esdbclient.esdbapi import SubscriptionReadRequest, handle_rpc_error
from esdbclient.events import NewEvent
from esdbclient.exceptions import (
    DeadlineExceeded,
    ExpectedPositionError,
    GrpcError,
    ServiceUnavailable,
    StreamNotFound,
)


class FakeRpcError(_MultiThreadedRendezvous):
    def __init__(self, status_code: StatusCode) -> None:
        super().__init__(
            state=_RPCState(
                due=set(),
                initial_metadata="",
                trailing_metadata="",
                code=status_code,
                details="",
            ),
            call=IntegratedCall(None, None),
            response_deserializer=lambda x: x,
            deadline=None,
        )


class FakeDeadlineExceededRpcError(FakeRpcError):
    def __init__(self) -> None:
        super().__init__(status_code=StatusCode.DEADLINE_EXCEEDED)


class FakeUnavailableRpcError(FakeRpcError):
    def __init__(self) -> None:
        super().__init__(status_code=StatusCode.UNAVAILABLE)


class FakeUnknownRpcError(FakeRpcError):
    def __init__(self) -> None:
        super().__init__(status_code=StatusCode.UNKNOWN)


class TestEsdbClient(TestCase):
    def test_constructor_args(self) -> None:
        client = EsdbClient("localhost:2222")
        self.assertEqual(client.grpc_target, "localhost:2222")

        client = EsdbClient(host="localhost", port=2222)
        self.assertEqual(client.grpc_target, "localhost:2222")

        # ESDB URLs not yet supported...
        with self.assertRaises(ValueError):
            EsdbClient(uri="esdb:something")

    def test_service_unavailable_exception(self) -> None:
        client = EsdbClient("localhost:2222")  # wrong port

        with self.assertRaises(ServiceUnavailable) as cm:
            list(client.read_stream_events(str(uuid4())))
        self.assertIn(
            "failed to connect to all addresses", cm.exception.args[0].details()
        )

        with self.assertRaises(ServiceUnavailable) as cm:
            client.append_events(str(uuid4()), expected_position=None, events=[])
        self.assertIn(
            "failed to connect to all addresses", cm.exception.args[0].details()
        )

    def test_handle_deadline_exceeded_error(self) -> None:
        with self.assertRaises(GrpcError) as cm:
            raise handle_rpc_error(FakeDeadlineExceededRpcError()) from None
        self.assertEqual(cm.exception.__class__, DeadlineExceeded)

    def test_handle_unavailable_error(self) -> None:
        with self.assertRaises(GrpcError) as cm:
            raise handle_rpc_error(FakeUnavailableRpcError()) from None
        self.assertEqual(cm.exception.__class__, ServiceUnavailable)

    def test_handle_other_call_error(self) -> None:
        with self.assertRaises(GrpcError) as cm:
            raise handle_rpc_error(FakeUnknownRpcError()) from None
        self.assertEqual(cm.exception.__class__, GrpcError)

    def test_handle_non_call_rpc_error(self) -> None:
        # Check non-Call errors are handled.
        class MyRpcError(RpcError):
            pass

        msg = "some non-Call error"
        with self.assertRaises(GrpcError) as cm:
            raise handle_rpc_error(MyRpcError(msg)) from None
        self.assertEqual(cm.exception.__class__, GrpcError)
        self.assertIsInstance(cm.exception.args[0], MyRpcError)

    def test_stream_not_found_exception(self) -> None:
        client = self.construct_esdb_client()
        stream_name = str(uuid4())

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, backwards=True))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, position=1))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, position=1, backwards=True))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, limit=10))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, backwards=True, limit=10))

        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name, position=1, limit=10))

        with self.assertRaises(StreamNotFound):
            list(
                client.read_stream_events(
                    stream_name, position=1, backwards=True, limit=10
                )
            )

    def test_stream_append_and_read_without_occ(self) -> None:
        client = self.construct_esdb_client()
        stream_name = str(uuid4())

        event1 = NewEvent(type="Snapshot", data=b"{}", metadata=b"{}")

        # Append new event.
        client.append_events(stream_name, expected_position=-1, events=[event1])
        events = list(client.read_stream_events(stream_name, backwards=True, limit=1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "Snapshot")

    def construct_esdb_client(self) -> EsdbClient:
        server_cert = ssl.get_server_certificate(addr=("localhost", 2113))
        username = "admin"
        password = "changeit"
        return EsdbClient(
            host="localhost",
            port=2113,
            server_cert=server_cert,
            username=username,
            password=password,
        )

    def test_stream_append_and_read_with_occ(self) -> None:
        client = self.construct_esdb_client()
        stream_name = str(uuid4())

        # Check stream not found.
        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name))

        # Check stream position is None.
        self.assertEqual(client.get_stream_position(stream_name), None)

        # Check get error when attempting to append empty list to position 1.
        with self.assertRaises(ExpectedPositionError) as cm:
            client.append_events(stream_name, expected_position=1, events=[])
        self.assertEqual(cm.exception.args[0], f"Stream {stream_name!r} does not exist")

        # Append empty list of events.
        commit_position1 = client.append_events(
            stream_name, expected_position=None, events=[]
        )
        self.assertIsInstance(commit_position1, int)

        # Check stream still not found.
        with self.assertRaises(StreamNotFound):
            list(client.read_stream_events(stream_name))

        # Check stream position is None.
        self.assertEqual(client.get_stream_position(stream_name), None)

        # Check get error when attempting to append new event to position 1.
        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        with self.assertRaises(ExpectedPositionError) as cm:
            client.append_events(stream_name, expected_position=1, events=[event1])
        self.assertEqual(cm.exception.args[0], f"Stream {stream_name!r} does not exist")

        # Append new event.
        commit_position2 = client.append_events(
            stream_name, expected_position=None, events=[event1]
        )

        # Todo: Why isn't this +1?
        # self.assertEqual(commit_position2 - commit_position1, 1)
        self.assertEqual(commit_position2 - commit_position1, 126)

        # Check stream position is 0.
        self.assertEqual(client.get_stream_position(stream_name), 0)

        # Read the stream forwards from the start (expect one event).
        events = list(client.read_stream_events(stream_name))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderCreated")

        # Check we can't append another new event at initial position.
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        with self.assertRaises(ExpectedPositionError) as cm:
            client.append_events(stream_name, expected_position=None, events=[event2])
        self.assertEqual(cm.exception.args[0], "Current position is 0")

        # Append another event.
        commit_position3 = client.append_events(
            stream_name, expected_position=0, events=[event2]
        )

        # Todo: Write a separate test for idempotent appends.
        # commit_position3_1 = client.append_events(
        #     stream_name, expected_position=0, events=[event2]
        # )

        # Check stream position is 1.
        self.assertEqual(client.get_stream_position(stream_name), 1)

        # NB: Why isn't this +1? because it's "disk position" :-|
        # self.assertEqual(commit_position3 - commit_position2, 1)
        # self.assertEqual(commit_position3 - commit_position2, 142)
        self.assertGreater(commit_position3, commit_position2)

        # Read the stream (expect two events in 'forwards' order).
        events = list(client.read_stream_events(stream_name))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].type, "OrderCreated")
        self.assertEqual(events[1].type, "OrderUpdated")

        # Read the stream backwards from the end.
        events = list(client.read_stream_events(stream_name, backwards=True))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].type, "OrderCreated")
        self.assertEqual(events[0].type, "OrderUpdated")

        # Read the stream forwards from position 1.
        events = list(client.read_stream_events(stream_name, position=1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderUpdated")

        # Read the stream backwards from position 0.
        events = list(
            client.read_stream_events(stream_name, position=0, backwards=True)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderCreated")

        # Read the stream forwards from start with limit.
        events = list(client.read_stream_events(stream_name, limit=1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderCreated")

        # Read the stream backwards from end with limit.
        events = list(client.read_stream_events(stream_name, backwards=True, limit=1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderUpdated")

        # Check we can't append another new event at second position.
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")
        with self.assertRaises(ExpectedPositionError) as cm:
            client.append_events(stream_name, expected_position=0, events=[event3])
        self.assertEqual(cm.exception.args[0], "Current position is 1")

        # Append another new event.
        commit_position4 = client.append_events(
            stream_name, expected_position=1, events=[event3]
        )

        # Check stream position is 2.
        self.assertEqual(client.get_stream_position(stream_name), 2)

        # NB: Why isn't this +1? because it's "disk position" :-|
        # self.assertEqual(commit_position4 - commit_position3, 1)
        # self.assertEqual(commit_position4 - commit_position3, 142)
        self.assertGreater(commit_position4, commit_position3)

        # Read the stream forwards from start (expect three events).
        events = list(client.read_stream_events(stream_name))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].type, "OrderCreated")
        self.assertEqual(events[1].type, "OrderUpdated")
        self.assertEqual(events[2].type, "OrderDeleted")

        # Read the stream backwards from end (expect three events).
        events = list(client.read_stream_events(stream_name, backwards=True))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].type, "OrderCreated")
        self.assertEqual(events[1].type, "OrderUpdated")
        self.assertEqual(events[0].type, "OrderDeleted")

        # Read the stream forwards from position with limit.
        events = list(client.read_stream_events(stream_name, position=1, limit=1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderUpdated")

        # Read the stream backwards from position with limit.
        events = list(
            client.read_stream_events(stream_name, position=1, backwards=True, limit=1)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "OrderUpdated")

    def test_timeout_stream_append_and_read(self) -> None:
        client = self.construct_esdb_client()

        # Append three events.
        stream_name1 = str(uuid4())
        event1 = NewEvent(
            type="OrderCreated",
            data=b"{}",
            metadata=b"{}",
        )
        event2 = NewEvent(
            type="OrderUpdated",
            data=b"{}",
            metadata=b"{}",
        )
        event3 = NewEvent(
            type="OrderDeleted",
            data=b"{}",
            metadata=b"{}",
        )
        client.append_events(
            stream_name=stream_name1,
            expected_position=None,
            events=[event1, event2],
        )

        # Timeout appending new event.
        with self.assertRaises(DeadlineExceeded):
            client.append_events(
                stream_name1, expected_position=1, events=[event3], timeout=0
            )

        # Timeout reading stream.
        with self.assertRaises(DeadlineExceeded):
            list(client.read_stream_events(stream_name1, timeout=0))

    def test_read_all_events(self) -> None:
        client = self.construct_esdb_client()

        num_old_events = len(list(client.read_all_events()))

        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        commit_position1 = client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        stream_name2 = str(uuid4())
        commit_position2 = client.append_events(
            stream_name2, expected_position=None, events=[event1, event2, event3]
        )

        # Check we can read forwards from the start.
        events = list(client.read_all_events())
        self.assertEqual(len(events) - num_old_events, 6)
        self.assertEqual(events[-1].stream_name, stream_name2)
        self.assertEqual(events[-1].type, "OrderDeleted")
        self.assertEqual(events[-2].stream_name, stream_name2)
        self.assertEqual(events[-2].type, "OrderUpdated")
        self.assertEqual(events[-3].stream_name, stream_name2)
        self.assertEqual(events[-3].type, "OrderCreated")
        self.assertEqual(events[-4].stream_name, stream_name1)
        self.assertEqual(events[-4].type, "OrderDeleted")

        # Check we can read backwards from the end.
        events = list(client.read_all_events(backwards=True))
        self.assertEqual(len(events) - num_old_events, 6)
        self.assertEqual(events[0].stream_name, stream_name2)
        self.assertEqual(events[0].type, "OrderDeleted")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderUpdated")
        self.assertEqual(events[2].stream_name, stream_name2)
        self.assertEqual(events[2].type, "OrderCreated")
        self.assertEqual(events[3].stream_name, stream_name1)
        self.assertEqual(events[3].type, "OrderDeleted")

        # Check we can read forwards from commit position 1.
        events = list(client.read_all_events(commit_position=commit_position1))
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0].stream_name, stream_name1)
        self.assertEqual(events[0].type, "OrderDeleted")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderCreated")
        self.assertEqual(events[2].stream_name, stream_name2)
        self.assertEqual(events[2].type, "OrderUpdated")
        self.assertEqual(events[3].stream_name, stream_name2)
        self.assertEqual(events[3].type, "OrderDeleted")

        # Check we can read forwards from commit position 2.
        events = list(client.read_all_events(commit_position=commit_position2))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].stream_name, stream_name2)
        self.assertEqual(events[0].type, "OrderDeleted")

        # Check we can read backwards from commit position 1.
        # NB backwards here doesn't include event at commit position, otherwise
        # first event would an OrderDeleted event, and we get an OrderUpdated.
        events = list(
            client.read_all_events(commit_position=commit_position1, backwards=True)
        )
        self.assertEqual(len(events) - num_old_events, 2)
        self.assertEqual(events[0].stream_name, stream_name1)
        self.assertEqual(events[0].type, "OrderUpdated")
        self.assertEqual(events[1].stream_name, stream_name1)
        self.assertEqual(events[1].type, "OrderCreated")

        # Check we can read backwards from commit position 2.
        # NB backwards here doesn't include event at commit position.
        events = list(
            client.read_all_events(commit_position=commit_position2, backwards=True)
        )
        self.assertEqual(len(events) - num_old_events, 5)
        self.assertEqual(events[0].stream_name, stream_name2)
        self.assertEqual(events[0].type, "OrderUpdated")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderCreated")
        self.assertEqual(events[2].stream_name, stream_name1)
        self.assertEqual(events[2].type, "OrderDeleted")

        # Check we can read forwards from the start with limit.
        events = list(client.read_all_events(limit=3))
        self.assertEqual(len(events), 3)

        # Check we can read backwards from the end with limit.
        events = list(client.read_all_events(backwards=True, limit=3))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].stream_name, stream_name2)
        self.assertEqual(events[0].type, "OrderDeleted")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderUpdated")
        self.assertEqual(events[2].stream_name, stream_name2)
        self.assertEqual(events[2].type, "OrderCreated")

        # Check we can read forwards from commit position 1 with limit.
        events = list(client.read_all_events(commit_position=commit_position1, limit=3))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].stream_name, stream_name1)
        self.assertEqual(events[0].type, "OrderDeleted")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderCreated")
        self.assertEqual(events[2].stream_name, stream_name2)
        self.assertEqual(events[2].type, "OrderUpdated")

        # Check we can read backwards from commit position 2 with limit.
        events = list(
            client.read_all_events(
                commit_position=commit_position2, backwards=True, limit=3
            )
        )
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].stream_name, stream_name2)
        self.assertEqual(events[0].type, "OrderUpdated")
        self.assertEqual(events[1].stream_name, stream_name2)
        self.assertEqual(events[1].type, "OrderCreated")
        self.assertEqual(events[2].stream_name, stream_name1)
        self.assertEqual(events[2].type, "OrderDeleted")

    def test_timeout_read_all_events(self) -> None:
        client = self.construct_esdb_client()

        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        stream_name2 = str(uuid4())
        client.append_events(
            stream_name2, expected_position=None, events=[event1, event2, event3]
        )

        # Timeout reading all events.
        with self.assertRaises(DeadlineExceeded):
            list(client.read_all_events(timeout=0.001))

    def test_read_all_filter_include(self) -> None:
        client = self.construct_esdb_client()

        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Read only OrderCreated.
        events = list(client.read_all_events(filter_include=("OrderCreated",)))
        types = set([e.type for e in events])
        self.assertEqual(types, {"OrderCreated"})

        # Read only OrderCreated and OrderDeleted.
        events = list(
            client.read_all_events(filter_include=("OrderCreated", "OrderDeleted"))
        )
        types = set([e.type for e in events])
        self.assertEqual(types, {"OrderCreated", "OrderDeleted"})

    def test_read_all_filter_exclude(self) -> None:
        client = self.construct_esdb_client()

        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Exclude OrderCreated.
        events = list(client.read_all_events(filter_exclude=("OrderCreated",)))
        types = set([e.type for e in events])
        self.assertNotIn("OrderCreated", types)
        self.assertIn("OrderUpdated", types)
        self.assertIn("OrderDeleted", types)

        # Exclude OrderCreated and OrderDeleted.
        events = list(
            client.read_all_events(filter_exclude=("OrderCreated", "OrderDeleted"))
        )
        types = set([e.type for e in events])
        self.assertNotIn("OrderCreated", types)
        self.assertIn("OrderUpdated", types)
        self.assertNotIn("OrderDeleted", types)

    def test_read_all_filter_exclude_ignored_when_filter_include_is_set(self) -> None:
        client = self.construct_esdb_client()

        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Both include and exclude.
        events = list(
            client.read_all_events(
                filter_include=("OrderCreated",), filter_exclude=("OrderCreated",)
            )
        )
        types = set([e.type for e in events])
        self.assertIn("OrderCreated", types)
        self.assertNotIn("OrderUpdated", types)
        self.assertNotIn("OrderDeleted", types)

    def test_catchup_subscribe_all_events_default_filter(self) -> None:
        client = self.construct_esdb_client()

        event1 = NewEvent(type="OrderCreated", data=b"{a}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{b}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{c}", metadata=b"{}")

        # Append new events.
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe to all events, from the start.
        subscription = client.subscribe_all_events()

        # Iterate over the first three events.
        events = []
        for event in subscription:
            events.append(event)
            if len(events) == 3:
                break

        # Get the current commit position.
        commit_position = client.get_commit_position()

        # Subscribe from the current commit position.
        subscription = client.subscribe_all_events(commit_position=commit_position)

        # Append three more events.
        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")
        stream_name2 = str(uuid4())
        client.append_events(
            stream_name2, expected_position=None, events=[event1, event2, event3]
        )

        # Check the stream name of the newly received events.
        events = []
        for event in subscription:
            self.assertEqual(event.stream_name, stream_name2)
            events.append(event)
            self.assertIn(event.type, ["OrderCreated", "OrderUpdated", "OrderDeleted"])
            if len(events) == 3:
                break

    def test_catchup_subscribe_all_events_no_filter(self) -> None:
        client = self.construct_esdb_client()

        # Append new events.
        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe from the current commit position.
        subscription = client.subscribe_all_events(
            filter_exclude=[],
            filter_include=[],
        )

        # Expect to get system events.
        for event in subscription:
            if event.type.startswith("$"):
                break
        else:
            self.fail("Didn't get a system event")

    def test_catchup_subscribe_all_events_include_filter(self) -> None:
        client = self.construct_esdb_client()

        # Append new events.
        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe from the beginning.
        subscription = client.subscribe_all_events(
            filter_exclude=[],
            filter_include=["OrderCreated"],
        )

        # Expect to only get "OrderCreated" events.
        events = []
        for event in subscription:
            if not event.type.startswith("OrderCreated"):
                self.fail("Event type is not 'OrderCreated'")

            events.append(event)

            # Break if we see the 'OrderCreated' event appended above.
            if event.data == event1.data:
                break

        # Check we actually got some 'OrderCreated' events.
        self.assertGreater(len(events), 0)

    def test_catchup_subscribe_all_events_from_commit_position_zero(self) -> None:
        client = self.construct_esdb_client()

        # Append new events.
        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe from the beginning.
        subscription = client.subscribe_all_events()

        # Expect to only get "OrderCreated" events.
        count = 0
        for _ in subscription:
            count += 1
            break
        self.assertEqual(count, 1)

    def test_catchup_subscribe_all_events_from_commit_position_current(self) -> None:
        client = self.construct_esdb_client()

        position = client.get_commit_position()

        # Append new events.
        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe from the commit position.
        subscription = client.subscribe_all_events(commit_position=position)

        events = []
        for event in subscription:
            # Exclude event with given commit position.
            if event.commit_position == position:
                self.fail("Not exclusive")

            # Collect events.
            events.append(event)

            # Break if we got the last one we wrote.
            if event.data == event3.data:
                break

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].data, event1.data)
        self.assertEqual(events[1].data, event2.data)
        self.assertEqual(events[2].data, event3.data)

    def test_timeout_subscribe_all_events(self) -> None:
        client = self.construct_esdb_client()

        # Append new events.
        event1 = NewEvent(type="OrderCreated", data=b"{}", metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=b"{}", metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=b"{}", metadata=b"{}")
        stream_name1 = str(uuid4())
        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Subscribe from the beginning.
        subscription = client.subscribe_all_events(timeout=0.5)

        # Expect to only get "OrderCreated" events.
        count = 0
        with self.assertRaises(DeadlineExceeded):
            for _ in subscription:
                count += 1
        self.assertGreater(count, 0)

    def test_persistent_subscription_from_start(self) -> None:
        # Construct client.
        client = self.construct_esdb_client()

        # Create persistent subscription.
        group_name = f"my-subscription-{uuid4().hex}"
        client.create_subscription(group_name=group_name)

        # Append three events.
        stream_name1 = str(uuid4())

        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")

        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Read all events.
        read_req, read_resp = client.read_subscription(group_name=group_name)

        events = []
        for event in read_resp:
            read_req.ack(event.id)
            events.append(event)
            if event.data == event3.data:
                break

        assert events[-3].data == event1.data
        assert events[-2].data == event2.data
        assert events[-1].data == event3.data

    def test_persistent_subscription_from_commit_position(self) -> None:
        # Construct client.
        client = self.construct_esdb_client()

        # Get commit position.
        position = client.get_commit_position()

        # Append three events.
        stream_name1 = str(uuid4())

        def random_data() -> bytes:
            return os.urandom(16)

        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")

        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )
        # pos1 = client.append_events(stream_name1, expected_position=None, events=[event1])
        # client.append_events(stream_name1, expected_position=0, events=[event2, event3])

        # Create persistent subscription.
        group_name = f"my-subscription-{uuid4().hex}"

        client.create_subscription(
            group_name=group_name,
            commit_position=position,
        )

        # Read events from subscription.
        read_req, read_resp = client.read_subscription(group_name=group_name)

        events = []
        for event in read_resp:
            read_req.ack(event.id)
            if event.commit_position <= position:
                # self.fail("Not exclusive")
                continue

            events.append(event)

            if len(events) == 3:
                break

        assert events[0].data == event1.data
        assert events[1].data == event2.data
        assert events[2].data == event3.data

    def test_persistent_subscription_from_end(self) -> None:
        # Construct client.
        client = self.construct_esdb_client()

        # Create persistent subscription.
        group_name = f"my-subscription-{uuid4().hex}"
        client.create_subscription(
            group_name=group_name,
            from_end=True,
        )

        # Append three events.
        stream_name1 = str(uuid4())

        def random_data() -> bytes:
            return os.urandom(16)

        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")

        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Read three events.
        read_req, read_resp = client.read_subscription(group_name=group_name)

        events = []
        for event in read_resp:
            read_req.ack(event.id)
            events.append(event)
            if len(events) == 3:
                break

        assert events[0].data == event1.data
        assert events[1].data == event2.data
        assert events[2].data == event3.data

    def test_persistent_subscription_include_filter(self) -> None:
        # Construct client.
        client = self.construct_esdb_client()

        # Create persistent subscription.
        group_name = f"my-subscription-{uuid4().hex}"
        client.create_subscription(
            group_name=group_name,
            filter_include=["OrderCreated"],
        )

        # Append three events.
        stream_name1 = str(uuid4())

        def random_data() -> bytes:
            return os.urandom(16)

        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")

        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Read events from subscription.
        read_req, read_resp = client.read_subscription(group_name=group_name)

        for event in read_resp:
            read_req.ack(event.id)
            self.assertEqual(event.type, "OrderCreated")
            if event.data == event1.data:
                break

    def test_persistent_subscription_exclude_filter(self) -> None:
        # Construct client.
        client = self.construct_esdb_client()

        # Create persistent subscription.
        group_name = f"my-subscription-{uuid4().hex}"
        client.create_subscription(
            group_name=group_name,
            filter_exclude=["OrderCreated"],
        )

        # Append three events.
        stream_name1 = str(uuid4())

        def random_data() -> bytes:
            return os.urandom(16)

        event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
        event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
        event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")

        client.append_events(
            stream_name1, expected_position=None, events=[event1, event2, event3]
        )

        # Read events from subscription.
        read_req, read_resp = client.read_subscription(group_name=group_name)

        start = datetime.now()
        absstart = start
        for i, event in enumerate(read_resp):
            received = datetime.now()
            duration = (received - start).total_seconds()
            total_duration = (received - absstart).total_seconds()
            rate = i / total_duration
            start = received
            read_req.ack(event.id)
            print(i, f"duration: {duration:.4f}s", f"rate: {rate:.1f}/s --", event)
            if duration > 0.5:
                print("^^^^^^^^^^^^^^^^^^^^^^^^ seemed to take a long time")
                print()
            self.assertNotEqual(event.type, "OrderCreated")
            if event.data == event3.data:
                break

    # def test_persistent_subscription_no_filter(self) -> None:
    #     # Construct client.
    #     client = self.construct_esdb_client()
    #
    #     # Create persistent subscription.
    #     group_name = f"my-subscription-{uuid4().hex}"
    #     client.create_subscription(
    #         group_name=group_name,
    #         filter_exclude=[],
    #         filter_include=[ESDB_EVENTS_REGEX],
    #     )
    #
    #     # Append three events.
    #     stream_name1 = str(uuid4())
    #
    #     def random_data() -> bytes:
    #         return os.urandom(16)
    #
    #     event1 = NewEvent(type="OrderCreated", data=random_data(), metadata=b"{}")
    #     event2 = NewEvent(type="OrderUpdated", data=random_data(), metadata=b"{}")
    #     event3 = NewEvent(type="OrderDeleted", data=random_data(), metadata=b"{}")
    #
    #     client.append_events(
    #         stream_name1, expected_position=None, events=[event1, event2, event3]
    #     )
    #
    #     # Read events from subscription.
    #     read_req, read_resp = client.read_subscription(group_name=group_name)
    #
    #     for event in read_resp:
    #         # Look for a "system" event.
    #         read_req.ack(event.id)
    #         if event.type.startswith("$"):
    #             return
    #         else:
    #             print(event.stream_name)
    #         if event.data == event3.data:
    #             self.fail("Expected a 'system' event, but none seen")

    # Todo: subscribe to specific stream (not all)
    # Todo: "commit position" behaviour (not sure why it isn't working)
    # Todo: consumer_strategy, RoundRobin and Pinned, need to test with more than
    #  one consumer, also code this as enum rather than a string
    # Todo: Nack? exception handling on callback?
    # Todo: update subscription
    # Todo: delete subscription
    # Todo: filter options
    # Todo: subscribe from end? not interesting, because you can get commit position


class TestEsdbClientInsecure(TestEsdbClient):
    def construct_esdb_client(self) -> EsdbClient:
        server_cert = None
        username = None
        password = None
        return EsdbClient(
            host="localhost",
            port=2114,
            server_cert=server_cert,
            username=username,
            password=password,
        )


class TestSubscriptionReadRequest(TestCase):
    def test_ack_200_ids(self) -> None:
        read_request = SubscriptionReadRequest("group1")
        read_request_iter = read_request
        grpc_read_req = next(read_request_iter)
        self.assertIsInstance(grpc_read_req, grpc_persistent.ReadReq)

        # Do one batch of acks.
        event_ids: List[UUID] = []
        for _ in range(100):
            event_id = uuid4()
            event_ids.append(event_id)
            read_request.ack(event_id)
        grpc_read_req = next(read_request_iter)
        self.assertEqual(len(grpc_read_req.ack.ids), 100)

        # Do another batch of acks.
        event_ids.clear()
        for _ in range(100):
            event_id = uuid4()
            event_ids.append(event_id)
            read_request.ack(event_id)
        grpc_read_req = next(read_request_iter)
        self.assertEqual(len(grpc_read_req.ack.ids), 100)


def random_data() -> bytes:
    return os.urandom(16)
