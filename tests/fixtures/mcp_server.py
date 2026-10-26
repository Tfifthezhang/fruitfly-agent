"""Standard-library-only offline MCP peer; no network or model requests."""
import argparse
import json
import os
import sys
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument('--mode', default='normal')
parser.add_argument('--pidfile')
args = parser.parse_args()
if args.pidfile:
    with open(args.pidfile, 'w') as stream:
        stream.write(str(os.getpid()))
lock = threading.Lock()
stop = threading.Event()


def send(message):
    with lock:
        print(json.dumps(message), flush=True)


SCHEMA = {'type': 'object', 'properties': {'value': {'$ref': '#/$defs/value'},
    'delay': {'type': 'number', 'minimum': 0}, 'count': {'type': 'integer'}},
    '$defs': {'value': {'anyOf': [{'type': 'string'}, {'type': 'null'}]}},
    'required': ['value'], 'additionalProperties': False}
TOOLS = [{'name': name, 'description': 'Offline fixture ' + name, 'inputSchema': SCHEMA,
          'annotations': {'readOnlyHint': True}} for name in ('echo', 'fail', 'large', 'wait', 'change', 'image')]


def handle(message):
    method, params = message['method'], message.get('params', {})
    request_id = message.get('id')
    if request_id is None:
        if method == 'notifications/cancelled':
            stop.set()
        return
    if args.mode == 'hang' and method in {'server/discover', 'initialize'}:
        stop.wait(60)
        return
    if method == 'server/discover':
        if args.mode == 'legacy':
            send({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': 'legacy server'}})
            return
        result = {'supportedVersions': ['2026-07-28'], 'capabilities': {'tools': {}}, 'resultType': 'complete'}
    elif method == 'initialize':
        result = {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif method == 'tools/list':
        tools = TOOLS
        if args.mode == 'duplicate':
            tools = [TOOLS[0], TOOLS[0]]
        if args.mode == 'pages':
            tools = TOOLS[:3] if not params.get('cursor') else TOOLS[3:]
        result = {'tools': tools, 'resultType': 'complete', 'cacheScope': 'public', 'ttlMs': 0}
        if args.mode == 'pages' and not params.get('cursor'):
            result['nextCursor'] = 'page-2'
        if args.mode == 'loop':
            result['nextCursor'] = 'loop'
    elif method == 'tools/call':
        name, values = params['name'], params.get('arguments', {})
        if args.mode == 'disconnect':
            os._exit(0)
        if name == 'wait':
            stop.wait(values.get('delay', 60))
        if name == 'change':
            send({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed'})
        value = {'value': values.get('value'), 'count': values.get('count')}
        if name == 'large':
            value = {'value': 'x' * 25000}
        result = {'content': [{'type': 'text', 'text': json.dumps(value)}],
                  'structuredContent': value, 'isError': False, 'resultType': 'complete',
                  '_meta': {'provenance': {'untrusted_content': True}}}
        if name == 'fail':
            result = {'content': [{'type': 'text', 'text': 'fixture failure'}], 'isError': True, 'resultType': 'complete'}
        if name == 'image':
            result = {'resultType': 'complete', 'content': [{'type': 'image', 'mimeType': 'image/png',
                'data': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZL8AAAAASUVORK5CYII='}]}
    elif method == 'ping':
        result = {}
    else:
        send({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': 'unknown method'}})
        return
    if args.mode == 'legacy':
        for key in ('resultType', 'cacheScope', 'ttlMs', '_meta'):
            result.pop(key, None)
    send({'jsonrpc': '2.0', 'id': request_id, 'result': result})


for line in sys.stdin:
    message = json.loads(line)
    if message.get('method') == 'tools/call':
        threading.Thread(target=handle, args=(message,), daemon=True).start()
    else:
        handle(message)
