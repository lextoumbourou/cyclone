# coding: utf-8
#
# Copyright 2010 Alexandre Fiori
# based on the original Tornado by Facebook
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

"""Server-side implementation of the JSON-RPC protocol.

`JSON-RPC <http://json-rpc.org/wiki/specification>`_  is a lightweight remote
procedure call protocol, designed to be simple.

For more information, check out the `RPC demo
<https://github.com/fiorix/cyclone/tree/master/demos/rpc>`_.
"""

import types

import cyclone.escape
from cyclone.web import HTTPError, RequestHandler

from twisted.internet import defer
from twisted.python import log, failure


class JsonrpcRequestHandler(RequestHandler):
    """Subclass this class and define jsonrpc_* to make a handler.

    The response and request for your jsonrpc_* methods will be de/encoded with
    JsonrpcRequestHandler.encoder. By default that is set to cyclone.escape
    but you can override that for all JsonrpcRequestHandlers by setting it
    at the class level, or in each subclass (see the example):

        JsonrpcRequestHandler.encoder = myencoder

    The only requirement of setting a custom encoder is that it has
    two callable attributes: json_encode and json_decode.

    Example::

        class MyRequestHandler(JsonrpcRequestHandler):
            encoder = MyCustomEncoder()  # optional

            def jsonrpc_echo(self, text):
                return text

            def jsonrpc_sort(self, items):
                return sorted(items)

            @defer.inlineCallbacks
            def jsonrpc_geoip_lookup(self, address):
                response = yield cyclone.httpclient.fetch(
                    "http://freegeoip.net/json/%s" % address.encode("utf-8"))
                defer.returnValue(response.body)

    Example hybrid encoder::

        class DateTimeAwareEncoder(object):

            json_decode = lambda self, *args, **kwargs:\
                cyclone.escape.json_decode(*args, **kwargs)

            def default_encode(self, value):
                if isinstance(value, datetime):
                    return value.isoformat()

            json_encode = lambda self, *args, **kwargs:\
                json.dumps(default=self.default_encode, *args, **kwargs)
    """

    encoder = cyclone.escape

    def post(self, *args):
        self._auto_finish = False
        try:
            req = self.encoder.json_decode(self.request.body)
            jsonid = req["id"]
            method = req["method"]
            assert isinstance(method, types.StringTypes), \
                "Invalid method type: %s" % type(method)
            params = req.get("params", [])
            assert isinstance(params, (types.ListType, types.TupleType)), \
                "Invalid params type: %s" % type(params)
        except Exception, e:
            log.msg("Bad Request: %s" % str(e))
            raise HTTPError(400)

        function = getattr(self, "jsonrpc_%s" % method, None)
        if callable(function):
            args = list(args) + params
            d = defer.maybeDeferred(function, *args)
            d.addBoth(self._cbResult, jsonid)
        else:
            self._cbResult(AttributeError("method not found: %s" % method),
                           jsonid)

    def _cbResult(self, result, jsonid):
        if isinstance(result, failure.Failure):
            error = {'code': 0, 'message': str(result.value)}
            result = None
        else:
            error = None
        data = {"result": result, "error": error, "id": jsonid}
        self.finish(self.encoder.json_encode(data))
