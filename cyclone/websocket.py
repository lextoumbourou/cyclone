# coding: utf-8
#
# Copyright 2011 Alexandre Fiori
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

import base64
import hashlib
import struct
import cyclone.web
from twisted.python import log
from cyclone import __version__

class WebSocketProtocol(object):
    def __init__(self, handler):
        self.handler = handler
        self.request = handler.request
        self.transport = handler.transport

    def acceptConnection(self):
        pass

    def rawDataReceived(self, data):
        pass

    def sendMessage(self, message):
        pass


class WebSocketProtocol17(WebSocketProtocol):
    def __init__(self, handler):
        WebSocketProtocol.__init__(self, handler)

        self._partial_data = None

        self._frame_fin = None
        self._frame_rsv = None
        self._frame_ops = None
        self._frame_mask = None
        self._frame_payload_length = None
        self._frame_header_length = None

        self._raw_data_length = None
        self._header_index = None

        self._message_buffer = ""


    def acceptConnection(self):
        versions = ('7', '8', '13')
        if self.request.headers['Sec-WebSocket-Version'] not in versions:
            message = "Unsupported WebSocket Protocol Version"
            self.transport.write("HTTP/1.1 403 Forbidden\r\nContent-Length: " +
                str(len(message)) + "\r\n\r\n" + message)
            return self.transport.loseConnection()

        log.msg('Using ws spec (draft 17)')
        if 'Origin' in self.request.headers:
            origin = self.request.headers['Origin']
        else:
            origin = self.request.headers['Sec-Websocket-Origin']

        key = self.request.headers['Sec-Websocket-Key']
        accept = base64.b64encode(hashlib.sha1(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())

        self.transport.write(
            "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
            "Upgrade: WebSocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: " + accept + "\r\n"
            "Server: cyclone/" +__version__+ "\r\n"
            "WebSocket-Origin: " + origin + "\r\n"
            "WebSocket-Location: ws://" + self.request.host +
            self.request.path + "\r\n\r\n")

    def rawDataReceived(self, data):
        self._raw_data_len = len(data)
        log.msg('raw data length %d' % self._raw_data_len)

        if self._partial_data:
            log.msg('we have partial data')
            data[0:0] = self._partial_data
            self._partial_data = None
        else:
            self._processFrameHeader(data)

        if (self._raw_data_len - self._header_index) < self._frame_payload_len:
            log.msg('not enough data')
            self._partial_data = data[self._header_index:]
            return


        self._message_buffer += self._extractMessageFromFrame(data)
        log.msg('message buffer %s' % self._message_buffer)
        if self._frame_fin:
            self.handler.messageReceived(self._message_buffer)
            self._message_buffer = ""

        # if there is still data after this frame, process again
        current_len = self._frame_header_len + self._frame_payload_len
        if current_len < self._raw_data_len:
            self.rawDataReceived(data[current_len:])

    def _processFrameHeader(self, data):
        # first byte contains fin, rsv and ops
        b = ord(data[0])
        self._frame_fin = (b & 0x80) != 0
        self._frame_rsv = (b & 0x70) >> 4
        self._frame_ops = b & 0x0f
        log.msg('fin %d rsv %d ops %d' % (self._frame_fin, self._frame_rsv, self._frame_ops))

        # second byte contains mask and payload length
        b = ord(data[1])
        self._frame_mask = (b & 0x80) != 0
        frame_payload_len1 = b & 0x7f

        if (self._frame_mask):
            mask_len = 4
        else:
            mask_len = 0

        # i is frame index. It's at 2 here because we've already processed the
        # first 2 bytes of the frame.
        i = 2

        if frame_payload_len1 <  126:
            self._frame_header_len = i + mask_len
            self._frame_payload_len = frame_payload_len1
        elif frame_payload_len1 == 126:
            self._frame_header_len = i + 2 + mask_len
            self._frame_payload_len = struct.unpack("!H", data[i:i+2])[0]
            i += 2
        elif frame_payload_len1 == 127:
            self._frame_header_len = i + 8 + mask_len
            self._frame_payload_len = struct.unpack("!Q", data[i:i+8])[0]
            i += 8

        self._header_index = i
        log.msg('masked  %d payload length %d header length %d header_index %d' % (self._frame_mask,
                                                                                   self._frame_payload_len, 
                                                                                   self._frame_header_len,
                                                                                   self._header_index))

    def _extractMessageFromFrame(self, data):
        i = self._header_index

        # when payload is masked, extract frame mask
        frame_mask = None
        frame_mask_array = []
        if self._frame_mask:
            frame_mask = data[i:i+4]
            for j in range(0, 4):
                frame_mask_array.append(ord(frame_mask[j]))
            i += 4
            payload = bytearray(data[i:i+self._frame_payload_len])
            log.msg('len(payload) %d' % len(payload))
            log.msg('self._frame_payload_len %d' % self._frame_payload_len)
            for k in xrange(0, self._frame_payload_len):
                payload[k] ^= frame_mask_array[k % 4]

            return str(payload)

    def sendMessage(self, message):
        message = unicode(message, "utf-8")
        length = len(message)
        newFrame = []
        newFrame.append(0x81)
        newFrame = bytearray(newFrame)
        if length <= 125:
            newFrame.append(length)
        elif length > 125 and length < 65536:
            newFrame.append(126)
            newFrame += struct.pack('!H', length)
        elif length >= 65536:
            newFrame.append(127)
            newFrame += struct.pack('!Q', length)

        newFrame += message.encode('utf-8')
        self.handler.transport.write(str(newFrame))


class WebSocketProtocol76(WebSocketProtocol):
    def acceptConnection(self):
        log.msg('accept connection!')

    def rawDataReceived(self, data):
        log.msg('raw data!')


class WebSocketHandler(cyclone.web.RequestHandler):
    def __init__(self, application, request):
        cyclone.web.RequestHandler.__init__(self, application, request)
        self.application = application
        self.request = request
        self.transport = request.connection.transport
        self.ws_protocol = None;

    def headersReceived(self):
        pass

    def connectionMade(self, *args, **kwargs):
        pass

    def messageReceived(self, message):
        pass

    def sendMessage(self, message):
        self.ws_protocol.sendMessage(message)
        """
        if self._protocol == 10:
            message = unicode(message, "utf-8")
            length = len(message)
            newFrame = []
            newFrame.append(0x81)
            newFrame = bytearray(newFrame)
            if length <= 125:
                newFrame.append(length)
            elif length > 125 and length < 65536:
                newFrame.append(126)
                newFrame += struct.pack('!H', length)
            elif length >= 65536:
                newFrame.append(127)
                newFrame += struct.pack('!Q', length)

            newFrame += message.encode()
            self.transport.write(str(newFrame))
        else:
            if isinstance(message, dict):
                message = escape.json_encode(message)
            if isinstance(message, unicode):
                message = message.encode("utf-8")
            assert isinstance(message, str)
            self.transport.write("\x00" + message + "\xff")
        """

    def _handle_request_exception(self, e):
        if isinstance(e, HTTPError):
            self.transport.loseConnection()
        else:
            log.err(e)
            log.err("Uncaught exception %s :: %r" % (self._request_summary(), self.request))
            self.transport.loseConnection()

    def _rawDataReceived(self, data):
        self.ws_protocol.handleRawData(data)
        """
        if len(data) == 8 and self._postheader == True and self._protocol >= 76:
            self.nonce = data.strip()
            token = self._calculate_token(self.k1, self.k2, self.nonce)
            self.transport.write(
                "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                "Upgrade: WebSocket\r\n"
                "Connection: Upgrade\r\n"
                "Server: cyclone/"+__version__+"\r\n"
                "Sec-WebSocket-Origin: " + self.request.headers["Origin"] + "\r\n"
                "Sec-WebSocket-Location: ws://" + self.request.host +
                self.request.path + "\r\n\r\n"+token+"\r\n")
            self._postheader = False
            self.flush()
            return
        elif ord(data[0]) & 0x80 == 0x80 and self._protocol == 10:
            ## Draft 10 Reference:
            ## https://github.com/oberstet/Autobahn/blob/master/lib/python/autobahn/websocket.py

            buffered_len = len(data)
            ## FIN, RSV, OPCODE
            ##
            b = ord(data[0])
            frame_fin = (b & 0x80) != 0
            frame_rsv = (b & 0x70) >> 4
            frame_opcode = b & 0x0f

            ## MASK, PAYLOAD LEN 1
            ##
            b = ord(data[1])
            frame_masked = (b & 0x80) != 0
            frame_payload_len1 = b & 0x7f

            ## compute complete header length
            ##
            if frame_masked:
                mask_len = 4
            else:
                mask_len = 0

            if frame_payload_len1 <  126:
                frame_header_len = 2 + mask_len
            elif frame_payload_len1 == 126:
                frame_header_len = 2 + 2 + mask_len
            elif frame_payload_len1 == 127:
                frame_header_len = 2 + 8 + mask_len

            ## only proceed when we have enough data buffered for complete
            ## frame header (which includes extended payload len + mask)
            ##
            if buffered_len >= frame_header_len:
                i = 2
                ## extract extended payload length
                ##
                if frame_payload_len1 == 126:
                    frame_payload_len = struct.unpack("!H", data[i:i+2])[0]
                    i += 2
                elif frame_payload_len1 == 127:
                    frame_payload_len = struct.unpack("!Q", data[i:i+8])[0]
                    i += 8
                else:
                    frame_payload_len = frame_payload_len1

                ## when payload is masked, extract frame mask
                ##
                frame_mask = None
                frame_mask_array = []
                if frame_masked:
                    frame_mask = data[i:i+4]
                    for j in range(0, 4):
                        frame_mask_array.append(ord(frame_mask[j]))
                    i += 4
                    payload = bytearray(data[i:i+frame_payload_len])
                    l = frame_payload_len
                    for k in xrange(0, l):
                        payload[k] ^= frame_mask_array[k % 4]

                    self.messageReceived(str(payload))

                    ## if there is still data after this frame, process again
                    ##
                    current_len = frame_header_len + frame_payload_len
                    if current_len < buffered_len:
                        self._rawDataReceived(data[current_len:])

                    return

        try:
            idx = data.find("\xff")
            message = data[1:idx]
            self._wsbuffer = data[idx+1:]
        except:
            log.err("Invalid WebSocket Message: %s" % repr(data))
        else:
            try:
                self.messageReceived(message)
            except Exception, e:
                self._handle_request_exception(e)
        """

    def _execute(self, transforms, *args, **kwargs):
        self.request.connection.setRawMode()

        # The difference between version 8 and 13 is that in 8 the
        # client sends a "Sec-Websocket-Origin" header and in 13 it's
        # simply "Origin".
        if self.request.headers.has_key('Sec-Websocket-Version') and \
        self.request.headers['Sec-Websocket-Version'] in ('7', '8', '13'):
            self.ws_protocol  = WebSocketProtocol17(self)
        elif self.request.headers.get("Sec-WebSocket-Version"):
            self.transport.write(cyclone.escape.utf8(
                "HTTP/1.1 426 Upgrade Required\r\n"
                "Sec-WebSocket-Version: 8\r\n\r\n"))
            self.transport.loseConnection()
            
        else:
            self.ws_protocol = WebSocketProtocol76(self)

        self.request.connection.rawDataReceived = self.ws_protocol.rawDataReceived
        self.ws_protocol.acceptConnection()

        """
        try:
            assert self.request.headers["Upgrade"].lower() == "websocket"
            assert self.request.headers["Connection"].lower() == "upgrade"
        except:
            message = "Expected WebSocket Headers"
            self.transport.write("HTTP/1.1 403 Forbidden\r\nContent-Length: " +
                str(len(message)) + "\r\n\r\n" + message)
            return self.transport.loseConnection()
        else:
            try:
                self.headersReceived()
            except Exception, e:
                return self._handle_request_exception(e)

            if 'Sec-Websocket-Version' in self.request.headers:
                versions = ('7', '8', '13')
                if self.request.headers['Sec-WebSocket-Version'] not in versions:
                    message = "Unsupported WebSocket Protocol Version"
                    self.transport.write("HTTP/1.1 403 Forbidden\r\nContent-Length: " +
                        str(len(message)) + "\r\n\r\n" + message)
                    return self.transport.loseConnection()

                log.msg('Using ws spec (draft 10)')
                if 'Origin' in self.request.headers:
                    origin = self.request.headers['Origin']
                else:
                    origin = self.request.headers['Sec-Websocket-Origin']
                key = self.request.headers['Sec-Websocket-Key']
                accept = base64.b64encode(hashlib.sha1(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
                self.transport.write(
                    "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                    "Upgrade: WebSocket\r\n"
                    "Connection: Upgrade\r\n"
                    "Sec-WebSocket-Accept: " + accept + "\r\n"
                    "Server: cyclone/" +__version__+ "\r\n"
                    "WebSocket-Origin: " + origin + "\r\n"
                    "WebSocket-Location: ws://" + self.request.host +
                    self.request.path + "\r\n\r\n")
                self._protocol = 10
            elif self.request.headers.has_key('Sec-Websocket-Key1') == False or \
                self.request.headers.has_key('Sec-Websocket-Key2') == False:
                log.msg('Using old ws spec (draft 75)')
                self.transport.write(
                    "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                    "Upgrade: WebSocket\r\n"
                    "Connection: Upgrade\r\n"
                    "Server: cyclone/"+__version__+"\r\n"
                    "WebSocket-Origin: " + self.request.headers["Origin"] + "\r\n"
                    "WebSocket-Location: ws://" + self.request.host +
                    self.request.path + "\r\n\r\n")
                self._protocol = 75
            else:
                log.msg('Using ws draft 76 header exchange')
                self.k1 = self.request.headers["Sec-WebSocket-Key1"]
                self.k2 = self.request.headers["Sec-WebSocket-Key2"]
                self._protocol = 76
        self._postheader = True
        self.connectionMade(*args, **kwargs)
        """

    def _calculate_token(self, k1, k2, k3):
        token = struct.pack('>ii8s', self._filterella(k1), self._filterella(k2), k3)
        return hashlib.md5(token).digest()

    def _filterella(self, w):
        nums = []
        spaces = 0
        for l in w:
            if l.isdigit(): nums.append(l)
            if l.isspace(): spaces = spaces + 1
        x = int(''.join(nums))/spaces
        return x
