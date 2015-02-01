#
# Copyright 2014 David Novakovic
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from twisted.trial import unittest
from mock import Mock
from cyclone.jsonrpc import JsonrpcRequestHandler
from cyclone.web import Application


class TestJsonrpcRequestHandler(unittest.TestCase):

    def setUp(self):
        self.request = Mock()
        self.app = Application()
        self.handler = JsonrpcRequestHandler(self.app, self.request)
        self.handler.finish = Mock()

    def test_post(self):
        self.handler.jsonrpc_foo = lambda: "value"
        self.handler.request.body = '{"id":1, "method":"foo"}'
        self.handler.post()
        self.handler.finish.assert_called_with(
            '{"error": null, "id": 1, "result": "value"}')
