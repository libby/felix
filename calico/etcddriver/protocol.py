# -*- coding: utf-8 -*-
# Copyright (c) 2015-2016 Tigera, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
calico.etcddriver.protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~

Protocol constants for Felix <-> Driver protocol.
"""
import logging
import socket
import errno
from io import BytesIO
import msgpack
import select

_log = logging.getLogger(__name__)

MSG_KEY_TYPE = "type"

# Init message Felix -> Driver.
MSG_TYPE_INIT = "init"
MSG_KEY_ETCD_URLS = "etcd_urls"
MSG_KEY_HOSTNAME = "hostname"
MSG_KEY_KEY_FILE = "etcd_key_file"
MSG_KEY_CERT_FILE = "etcd_cert_file"
MSG_KEY_CA_FILE = "etcd_ca_file"
MSG_KEY_PROM_PORT = "prom_port"

# Config loaded message Driver -> Felix.
MSG_TYPE_CONFIG_LOADED = "config_loaded"
MSG_KEY_GLOBAL_CONFIG = "global"
MSG_KEY_HOST_CONFIG = "host"

# Config message Felix -> Driver.
MSG_TYPE_CONFIG = "config_resolved"
MSG_KEY_LOG_FILE = "log_file"
MSG_KEY_SEV_FILE = "sev_file"
MSG_KEY_SEV_SCREEN = "sev_screen"
MSG_KEY_SEV_SYSLOG = "sev_syslog"

# Status message Driver -> Felix.
MSG_TYPE_STATUS = "datastore_status"
MSG_KEY_STATUS = "status"
STATUS_WAIT_FOR_READY = "wait-for-ready"
STATUS_RESYNC = "resync"
STATUS_IN_SYNC = "in-sync"


MSG_TYPE_PROFILE_UPDATE = "profile_update"
MSG_TYPE_PROFILE_REMOVED = "profile_remove"
MSG_TYPE_POLICY_UPDATE = "policy_update"
MSG_TYPE_POLICY_REMOVED = "policy_remove"
MSG_KEY_TIER_NAME = "tier"
MSG_KEY_NAME = "name"
MSG_KEY_POLICY = "policy"
MSG_KEY_PROFILE = "profile"

MSG_TYPE_WL_EP_UPDATE = "wl_ep_update"
MSG_TYPE_WL_EP_REMOVE = "wl_ep_remove"
MSG_TYPE_HOST_EP_UPDATE = "host_ep_update"
MSG_TYPE_HOST_EP_REMOVE = "host_ep_remove"
MSG_KEY_ORCH = "orchestrator"
MSG_KEY_WORKLOAD_ID = "workload_id"
MSG_KEY_ENDPOINT_ID = "endpoint_id"
MSG_KEY_ENDPOINT = "endpoint"

# Selector/IP added/removed message Driver -> Felix.
MSG_TYPE_IPSET_UPDATE = "ipset_update"
MSG_TYPE_IPSET_REMOVED = "ipset_remove"
MSG_TYPE_IPSET_DELTA = "ipset_delta"

MSG_KEY_MEMBERS = "members"
MSG_KEY_ADDED_IPS = "added_ips"
MSG_KEY_REMOVED_IPS = "removed_ips"
MSG_KEY_IPSET_ID = "ipset_id"


FLUSH_THRESHOLD = 200


class SocketClosed(Exception):
    """The socket was unexpectedly closed by the other end."""
    pass


class WriteFailed(Exception):
    """Write to the socket failed."""
    pass


class MessageWriter(object):
    """
    Wrapper around a socket used to write protocol messages.

    Supports buffering a number of messages for subsequent flush().
    """
    def __init__(self, sck):
        self._sck = sck
        self._buf = BytesIO()
        self._updates_pending = 0

    def send_message(self, msg_type, fields=None, flush=True):
        """
        Send a message of the given type with the given fields.
        Optionally, flush the data to the socket.

        This method will flush the buffer if it grows too large in any
        case.

        :param msg_type: one of the MSG_TYPE_* constants.
        :param dict fields: dict mapping MSG_KEY_* constants to values.
        :param flush: True to force the data to be written immediately.
        """
        _log.debug("Sending message %s: %s", msg_type, fields)
        self._buf.write(msgpack.dumps(msg_type))
        self._buf.write(msgpack.dumps(fields))
        if flush:
            self.flush()
        else:
            self._maybe_flush()

    def _maybe_flush(self):
        self._updates_pending += 1
        if self._updates_pending > FLUSH_THRESHOLD:
            self.flush()

    def flush(self):
        """
        Flushes the write buffer to the socket immediately.
        """
        _log.debug("Flushing the buffer to the socket")
        buf_contents = self._buf.getvalue()
        if buf_contents:
            try:
                self._sck.sendall(buf_contents)
            except socket.error as e:
                _log.exception("Failed to write to socket")
                raise WriteFailed(e)
            self._buf = BytesIO()
        self._updates_pending = 0


class MessageReader(object):
    def __init__(self, sck):
        self._sck = sck
        self._current_msg_type = None
        self._unpacker = msgpack.Unpacker()

    def new_messages(self, timeout=1):
        """
        Generator: generates 0 or more tuples containing message type and
        message body (as a dict).

        May generate 0 events in certain conditions even if there are
        events available.  (If the socket returns EAGAIN, for example.)

        :param timeout: Maximum time to block waiting on the socket before
               giving up.  No exception is raised upon timeout but 0 events
               are generated.
        :raises SocketClosed if the socket is closed.
        :raises socket.error if an unexpected socket error occurs.
        """
        if timeout is not None:
            read_ready, _, _ = select.select([self._sck], [], [], timeout)
            if not read_ready:
                return
        try:
            data = self._sck.recv(16384)
        except socket.error as e:
            if e.errno in (errno.EAGAIN,
                           errno.EWOULDBLOCK,
                           errno.EINTR):
                _log.debug("Retryable error on read.")
                return
            else:
                _log.error("Failed to read from socket: %r", e)
                raise
        if not data:
            # No data indicates an orderly shutdown of the socket,
            # which shouldn't happen.
            _log.error("Socket closed by other end.")
            raise SocketClosed()
        # Feed the data into the Unpacker, if it has enough data it will then
        # generate some messages.
        self._unpacker.feed(data)
        for msg in self._unpacker:
            if self._current_msg_type is None:
                self._current_msg_type = msg
                _log.debug("Read message type: %r", self._current_msg_type)
                assert self._current_msg_type is not None
                assert isinstance(msg, basestring), (
                    "Unexpected message type: %r" % self._current_msg_type
                )
                continue
            yield self._current_msg_type, msg
            self._current_msg_type = None
