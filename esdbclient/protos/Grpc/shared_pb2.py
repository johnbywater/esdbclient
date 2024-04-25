# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: esdbclient/protos/Grpc/shared.proto
# Protobuf Python Version: 4.25.1
"""Generated protocol buffer code."""
from google.protobuf import (
    descriptor as _descriptor,
    descriptor_pool as _descriptor_pool,
    symbol_database as _symbol_database,
)
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n#esdbclient/protos/Grpc/shared.proto\x12\x12\x65vent_store.client\x1a\x1bgoogle/protobuf/empty.proto"\xa9\x01\n\x04UUID\x12\x39\n\nstructured\x18\x01'
    b" \x01(\x0b\x32#.event_store.client.UUID.StructuredH\x00\x12\x10\n\x06string\x18\x02"
    b" \x01(\tH\x00\x1aK\n\nStructured\x12\x1d\n\x15most_significant_bits\x18\x01"
    b" \x01(\x03\x12\x1e\n\x16least_significant_bits\x18\x02"
    b' \x01(\x03\x42\x07\n\x05value"\x07\n\x05\x45mpty"-\n\x10StreamIdentifier\x12\x13\n\x0bstream_name\x18\x03'
    b' \x01(\x0cJ\x04\x08\x01\x10\x03"F\n\x11\x41llStreamPosition\x12\x17\n\x0f\x63ommit_position\x18\x01'
    b" \x01(\x04\x12\x18\n\x10prepare_position\x18\x02"
    b' \x01(\x04"\xf7\x02\n\x14WrongExpectedVersion\x12!\n\x17\x63urrent_stream_revision\x18\x01'
    b" \x01(\x04H\x00\x12\x33\n\x11\x63urrent_no_stream\x18\x02"
    b' \x01(\x0b\x32\x16.google.protobuf.EmptyH\x00\x12"\n\x18\x65xpected_stream_position\x18\x03'
    b" \x01(\x04H\x01\x12.\n\x0c\x65xpected_any\x18\x04"
    b" \x01(\x0b\x32\x16.google.protobuf.EmptyH\x01\x12\x38\n\x16\x65xpected_stream_exists\x18\x05"
    b" \x01(\x0b\x32\x16.google.protobuf.EmptyH\x01\x12\x34\n\x12\x65xpected_no_stream\x18\x06"
    b" \x01(\x0b\x32\x16.google.protobuf.EmptyH\x01\x42"
    b' \n\x1e\x63urrent_stream_revision_optionB!\n\x1f\x65xpected_stream_position_option"\x0e\n\x0c\x41\x63\x63\x65ssDenied"P\n\rStreamDeleted\x12?\n\x11stream_identifier\x18\x01'
    b' \x01(\x0b\x32$.event_store.client.StreamIdentifier"\t\n\x07Timeout"\t\n\x07Unknown"\x14\n\x12InvalidTransaction"2\n\x19MaximumAppendSizeExceeded\x12\x15\n\rmaxAppendSize\x18\x01'
    b' \x01(\r"\x1d\n\nBadRequest\x12\x0f\n\x07message\x18\x01'
    b" \x01(\tB&\n$com.eventstore.dbclient.proto.sharedb\x06proto3"
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(
    DESCRIPTOR, "esdbclient.protos.Grpc.shared_pb2", _globals
)
if _descriptor._USE_C_DESCRIPTORS == False:
    _globals["DESCRIPTOR"]._options = None
    _globals["DESCRIPTOR"]._serialized_options = (
        b"\n$com.eventstore.dbclient.proto.shared"
    )
    _globals["_UUID"]._serialized_start = 89
    _globals["_UUID"]._serialized_end = 258
    _globals["_UUID_STRUCTURED"]._serialized_start = 174
    _globals["_UUID_STRUCTURED"]._serialized_end = 249
    _globals["_EMPTY"]._serialized_start = 260
    _globals["_EMPTY"]._serialized_end = 267
    _globals["_STREAMIDENTIFIER"]._serialized_start = 269
    _globals["_STREAMIDENTIFIER"]._serialized_end = 314
    _globals["_ALLSTREAMPOSITION"]._serialized_start = 316
    _globals["_ALLSTREAMPOSITION"]._serialized_end = 386
    _globals["_WRONGEXPECTEDVERSION"]._serialized_start = 389
    _globals["_WRONGEXPECTEDVERSION"]._serialized_end = 764
    _globals["_ACCESSDENIED"]._serialized_start = 766
    _globals["_ACCESSDENIED"]._serialized_end = 780
    _globals["_STREAMDELETED"]._serialized_start = 782
    _globals["_STREAMDELETED"]._serialized_end = 862
    _globals["_TIMEOUT"]._serialized_start = 864
    _globals["_TIMEOUT"]._serialized_end = 873
    _globals["_UNKNOWN"]._serialized_start = 875
    _globals["_UNKNOWN"]._serialized_end = 884
    _globals["_INVALIDTRANSACTION"]._serialized_start = 886
    _globals["_INVALIDTRANSACTION"]._serialized_end = 906
    _globals["_MAXIMUMAPPENDSIZEEXCEEDED"]._serialized_start = 908
    _globals["_MAXIMUMAPPENDSIZEEXCEEDED"]._serialized_end = 958
    _globals["_BADREQUEST"]._serialized_start = 960
    _globals["_BADREQUEST"]._serialized_end = 989
# @@protoc_insertion_point(module_scope)
