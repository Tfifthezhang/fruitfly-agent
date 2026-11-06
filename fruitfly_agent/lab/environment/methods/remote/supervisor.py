"""Linux/POSIX remote command supervisor, sent over SSH without installation."""

# No credentials enter this program. SSH stdin is the cancellation/liveness
# channel. Child stdin is closed. A child process group is killed on EOF,
# explicit cancellation, or supervisor exit; detached sessions can escape it.
PROGRAM = r'''
import json, os, selectors, signal, subprocess, sys, threading
options = json.loads(sys.argv[1])
env = os.environ.copy() if options['inherit_env'] else {'PATH': '/usr/bin:/bin'}
env.update(options['env'])
process = subprocess.Popen(['/bin/bash', '-c', options['command']], cwd=options['cwd'],
    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    start_new_session=True)
def kill():
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
def interrupted(signum, frame):
    kill()
    sys.exit(128 + signum)
for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
    signal.signal(signum, interrupted)
watchdog = threading.Timer(options['timeout'], kill) if options.get('timeout') else None
if watchdog is not None:
    watchdog.daemon = True
    watchdog.start()
selector = selectors.DefaultSelector()
selector.register(sys.stdin.buffer, selectors.EVENT_READ, None)
selector.register(process.stdout, selectors.EVENT_READ, 1)
selector.register(process.stderr, selectors.EVENT_READ, 2)
try:
    streams = 2
    while streams or process.poll() is None:
        for key, _ in selector.select(.1):
            data = os.read(key.fd, 65536)
            if key.data is None:
                kill()
                selector.unregister(key.fileobj)
            elif data:
                view = memoryview(data)
                while view:
                    view = view[os.write(key.data, view):]
            else:
                selector.unregister(key.fileobj)
                streams -= 1
    status = process.wait()
finally:
    kill()
    if watchdog is not None:
        watchdog.cancel()
    selector.close()
sys.exit(status if status >= 0 else 128 - status)
'''
