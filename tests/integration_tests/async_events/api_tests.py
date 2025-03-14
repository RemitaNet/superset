# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from typing import Any, Optional, Type
from unittest import mock

from superset.async_events.cache_backend import (
    RedisCacheBackend,
    RedisSentinelCacheBackend,
)
from superset.extensions import async_query_manager, async_query_manager_factory
from superset.utils import json
from tests.integration_tests.base_tests import SupersetTestCase
from tests.integration_tests.constants import ADMIN_USERNAME
from tests.integration_tests.test_app import app


class TestAsyncEventApi(SupersetTestCase):
    UUID = "943c920-32a5-412a-977d-b8e47d36f5a4"

    def fetch_events(self, last_id: Optional[str] = None):
        base_uri = "api/v1/async_event/"
        uri = f"{base_uri}?last_id={last_id}" if last_id else base_uri
        return self.client.get(uri)

    def run_test_with_cache_backend(self, cache_backend_cls: Type[Any], test_func):
        app._got_first_request = False
        async_query_manager_factory.init_app(app)

        # Create a mock cache backend instance
        mock_cache = mock.Mock(spec=cache_backend_cls)

        # Set the mock cache instance
        async_query_manager._cache = mock_cache

        self.login(ADMIN_USERNAME)
        test_func(mock_cache)

    def _test_events_logic(self, mock_cache):
        with mock.patch.object(mock_cache, "xrange") as mock_xrange:
            rv = self.fetch_events()
            response = json.loads(rv.data.decode("utf-8"))

        assert rv.status_code == 200
        channel_id = app.config["GLOBAL_ASYNC_QUERIES_REDIS_STREAM_PREFIX"] + self.UUID
        mock_xrange.assert_called_with(channel_id, "-", "+", 100)
        assert response == {"result": []}

    def _test_events_last_id_logic(self, mock_cache):
        with mock.patch.object(mock_cache, "xrange") as mock_xrange:
            rv = self.fetch_events("1607471525180-0")
            response = json.loads(rv.data.decode("utf-8"))

        assert rv.status_code == 200
        channel_id = app.config["GLOBAL_ASYNC_QUERIES_REDIS_STREAM_PREFIX"] + self.UUID
        mock_xrange.assert_called_with(channel_id, "1607471525180-1", "+", 100)
        assert response == {"result": []}

    def _test_events_results_logic(self, mock_cache):
        with mock.patch.object(mock_cache, "xrange") as mock_xrange:
            mock_xrange.return_value = [
                (
                    "1607477697866-0",
                    {
                        "data": '{"channel_id": "1095c1c9-b6b1-444d-aa83-8e323b32831f", "job_id": "10a0bd9a-03c8-4737-9345-f4234ba86512", "user_id": "1", "status": "done", "errors": [], "result_url": "/api/v1/chart/data/qc-ecd766dd461f294e1bcdaa321e0e8463"}'  # noqa: E501
                    },
                ),
                (
                    "1607477697993-0",
                    {
                        "data": '{"channel_id": "1095c1c9-b6b1-444d-aa83-8e323b32831f", "job_id": "027cbe49-26ce-4813-bb5a-0b95a626b84c", "user_id": "1", "status": "done", "errors": [], "result_url": "/api/v1/chart/data/qc-1bbc3a240e7039ba4791aefb3a7ee80d"}'  # noqa: E501
                    },
                ),
            ]
            rv = self.fetch_events()
            response = json.loads(rv.data.decode("utf-8"))

        assert rv.status_code == 200
        channel_id = app.config["GLOBAL_ASYNC_QUERIES_REDIS_STREAM_PREFIX"] + self.UUID
        mock_xrange.assert_called_with(channel_id, "-", "+", 100)
        expected = {
            "result": [
                {
                    "channel_id": "1095c1c9-b6b1-444d-aa83-8e323b32831f",
                    "errors": [],
                    "id": "1607477697866-0",
                    "job_id": "10a0bd9a-03c8-4737-9345-f4234ba86512",
                    "result_url": "/api/v1/chart/data/qc-ecd766dd461f294e1bcdaa321e0e8463",  # noqa: E501
                    "status": "done",
                    "user_id": "1",
                },
                {
                    "channel_id": "1095c1c9-b6b1-444d-aa83-8e323b32831f",
                    "errors": [],
                    "id": "1607477697993-0",
                    "job_id": "027cbe49-26ce-4813-bb5a-0b95a626b84c",
                    "result_url": "/api/v1/chart/data/qc-1bbc3a240e7039ba4791aefb3a7ee80d",  # noqa: E501
                    "status": "done",
                    "user_id": "1",
                },
            ]
        }
        assert response == expected

    @mock.patch("uuid.uuid4", return_value=UUID)
    def test_events_redis_cache_backend(self, mock_uuid4):
        self.run_test_with_cache_backend(RedisCacheBackend, self._test_events_logic)

    @mock.patch("uuid.uuid4", return_value=UUID)
    def test_events_redis_sentinel_cache_backend(self, mock_uuid4):
        self.run_test_with_cache_backend(
            RedisSentinelCacheBackend, self._test_events_logic
        )

    def test_events_no_login(self):
        app._got_first_request = False
        async_query_manager_factory.init_app(app)
        rv = self.fetch_events()
        assert rv.status_code == 401

    def test_events_no_token(self):
        self.login(ADMIN_USERNAME)
        self.client.set_cookie(app.config["GLOBAL_ASYNC_QUERIES_JWT_COOKIE_NAME"], "")
        rv = self.fetch_events()
        assert rv.status_code == 401
