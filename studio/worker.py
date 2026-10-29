"""Independent queue consumer with an OS lease covering owned Harness children."""

import fcntl
import json
import os
import signal
import threading
import time


class Worker:
    """Own one executor lease, heartbeat, and orderly child shutdown."""

    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()

    def loop(self):
        """Run until requested to stop; another lease owner is left untouched."""
        with (self.store.root / "worker.lock").open("a+b") as lease:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # Another Worker or its surviving child still owns execution.
            marker=self.store.root/'worker-capabilities.json'
            temporary=self.store.root/'.worker-capabilities.tmp'
            temporary.write_text(json.dumps({'pid':os.getpid(),'routes':['business','style'],'modelRouting':1,'documentInputs':1,'focusedReview':1,'workspaceRecovery':1,'stageRouting':1,'projectChat':4,'reasoningSelection':1,'chatFiles':1,'assistantSteering':1}))
            os.replace(temporary,marker)
            self.store.recover_worker()
            with self.store.transaction():
                self.store.db.execute("INSERT INTO worker(id,pid,heartbeat,stop_requested) VALUES(1,?,?,0) ON CONFLICT(id) DO UPDATE SET pid=excluded.pid,heartbeat=excluded.heartbeat,stop_requested=0", (os.getpid(), time.time()))
            def heartbeat():
                while not self.stop.wait(1):
                    try:
                        with self.store.transaction():
                            row = self.store.db.execute("SELECT stop_requested FROM worker WHERE id=1").fetchone()
                            if row[0]:
                                self.stop.set()
                            self.store.db.execute("UPDATE worker SET heartbeat=? WHERE id=1", (time.time(),))
                    except Exception:
                        self.stop.set()
                        raise  # Lost persistence stops dependent execution and is visible in worker.log.
            monitor = threading.Thread(target=heartbeat)
            monitor.start()
            old_handlers = {}
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM, signal.SIGINT):
                    old_handlers[sig] = signal.signal(sig, lambda *_: self.stop.set())
            try:
                while not self.stop.is_set():
                    if not self.store.work_once(self.stop, lease.fileno()):
                        self.stop.wait(.4)
            finally:
                self.stop.set()
                monitor.join()
                with self.store.transaction():
                    self.store.db.execute("UPDATE worker SET heartbeat=0 WHERE id=1")
                marker.unlink(missing_ok=True)
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
