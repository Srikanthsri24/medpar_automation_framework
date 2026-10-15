"""Timestamped, bounded terminal progress with a heartbeat for long synchronous work."""
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
import threading
import time

HEARTBEAT_SECONDS=15
_lock=threading.RLock()
_output_lock=threading.Lock()
_tasks={}
_stop=None


def emit(message, *, update=True):
    """Flush each event immediately; messages must contain no credentials or signed URLs."""
    message=str(message).replace('\r',' ').replace('\n',' ')
    with _lock:
        if update and _tasks:next(reversed(_tasks.values()))['detail']=message
    with _output_lock:
        print(f'[{datetime.now().astimezone():%H:%M:%S %z}] {message}',flush=True)


def _heartbeat(stop):
    while not stop.wait(HEARTBEAT_SECONDS):
        with _lock:
            task=dict(next(reversed(_tasks.values()))) if _tasks else None
        if task:emit(f"WORKING: {task['detail']} | elapsed {time.monotonic()-task['started']:.0f}s; operation has not returned yet",update=False)


@contextmanager
def activity(label):
    """Show start/end/error and periodic current-task status without changing exceptions."""
    global _stop
    token=object();started=time.monotonic()
    with _lock:
        if not _tasks:
            _stop=threading.Event()
            threading.Thread(target=_heartbeat,args=(_stop,),daemon=True,name='medpar-progress').start()
        _tasks[token]={'detail':label,'started':started}
    emit('START: '+label)
    try:
        yield
    except BaseException:
        emit(f'FAILED: {label} after {time.monotonic()-started:.1f}s; see error details',update=False)
        raise
    else:
        emit(f'DONE: {label} in {time.monotonic()-started:.1f}s',update=False)
    finally:
        with _lock:
            _tasks.pop(token,None)
            if not _tasks and _stop is not None:_stop.set()


def tracked(label):
    def decorate(function):
        @wraps(function)
        def wrapper(*args,**kwargs):
            with activity(label):return function(*args,**kwargs)
        return wrapper
    return decorate


class Progress:
    """Known work totals get a percentage; unknown totals get counts only."""
    def __init__(self,label,total=None,unit='items',interval=2):
        self.label=label;self.total=total;self.unit=unit;self.interval=interval
        self.value=0;self.started=time.monotonic();self.last=self.started
        self.lock=threading.Lock();self._show()
    def _show(self):
        elapsed=time.monotonic()-self.started
        amount=f'{self.value:,} {self.unit}'
        if self.total is not None:
            percent=100*self.value/self.total if self.total else 100
            amount=f'{self.value:,}/{self.total:,} {self.unit} ({percent:.1f}%); {max(0,self.total-self.value):,} remaining'
        emit(f'{self.label}: {amount}; elapsed {elapsed:.1f}s')
    def update(self,value,*,force=False):
        with self.lock:
            self.value=max(0,min(value,self.total)) if self.total is not None else max(0,value)
            now=time.monotonic()
            if force or now-self.last>=self.interval:
                self.last=now;self._show()
    def advance(self,amount):
        with self.lock:
            self.value=max(0,min(self.value+amount,self.total)) if self.total is not None else max(0,self.value+amount)
            now=time.monotonic()
            if now-self.last>=self.interval:self.last=now;self._show()
    def finish(self):self.update(self.value if self.total is None else self.total,force=True)
