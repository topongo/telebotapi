from .telebotapi import TelegramBot
from typing import Callable
from inspect import getsource
from datetime import datetime, timedelta
from time import sleep
from uuid import uuid4
from threading import Thread


class Filter:
    def __init__(self, comparer: Callable):
        self.comparer = comparer

    def call(self, msg):
        try:
            return self.comparer(msg)
        except AttributeError:
            print("Exception caught")
            return False

    def __str__(self):
        return f"Filter(\"{getsource(self.comparer).strip()}\""

    def __repr__(self):
        return str(self)


class Condition:
    def __init__(self, *filters: Filter, callback=lambda l_: None, stop_return=None, reversed_=False):
        self.callback = callback
        self.stop_return_ = stop_return
        self.reversed = reversed_
        self.filters = list(filters)

    def add_filter(self, *f):
        for i in f:
            self.filters.append(i)

    def meet(self, msg):
        ret = all(map(lambda l: l.call(msg), self.filters))
        if self.reversed:
            return not ret
        return ret

    def __str__(self):
        return f"Condition(filters=[{', '.join(map(lambda l: str(l), self.filters))}], callback={self.callback})"

    def __repr__(self):
        return str(self)

    def stop_return(self, msg=None):
        if msg is None:
            return self.stop_return_
        if callable(self.stop_return_):
            return self.stop_return_(msg)
        else:
            return self.stop_return_


class ExpiredException(Exception):
    pass


class Fork:
    def __init__(self, *conditions, completed, exclusive=False, timeout=None, timeout_callback=None):
        self.exclusive = exclusive
        self.quick_stop = True
        self.conditions = conditions
        self.substitute = None
        for c in self.conditions:
            if c.stop_return() is not None:
                raise TypeError("\"conditions\" argument cannot contain Conditions with stop_return, only the"
                                "\"completed\" argument can have it.")
        self.completed = completed
        if self.completed.stop_return() is None:
            raise TypeError("\"completed\" argument must have the stop_return attribute set")
        self.result = None
        self.done = False
        if timeout is not None:
            if not isinstance(timeout, timedelta):
                raise TypeError(timeout)
            self.time_target = datetime.now() + timeout
        else:
            self.time_target = None

    def process(self, u_: TelegramBot.Update):
        if self.done:
            return
        if self.quick_stop and self.completed.meet(u_.content):
            self.completed.callback(u_.content)
            self.result = self.completed.stop_return(u_.content)
            self.done = True
            return
        meet = False
        for c in self.conditions:
            if c.meet(u_.content):
                meet = True
                c.callback(u_.content)
                if self.exclusive:
                    break
        if self.completed.meet(u_.content):
            self.completed.callback(u_.content)
            self.result = self.completed.stop_return(u_.content)
            self.done = True
        elif meet:
            print(":: warning: fork has matched, but is still running")

    def join(self):
        while not self.done:
            if self.substitute:
                self.substitute.join()
                break
            if self.expired():
                raise ExpiredException(self)
            sleep(.2)

    def get_result(self):
        return self.result

    def expired(self):
        if self.time_target is None:
            return False
        return datetime.now() > self.time_target


class Forks:
    def __init__(self):
        self.forks = {}

    def attach(self, *conds: Condition, completed: Condition, exclusive=False, custom_id=None, timeout=None):
        return self.attach_fork(Fork(*conds, completed=completed, exclusive=exclusive, timeout=timeout), custom_id)

    def attach_fork(self, fork: Fork, custom_id=None):
        if not isinstance(fork, Fork):
            raise TypeError(fork)
        u_ = str(uuid4()) if custom_id is None else str(custom_id)
        self.forks[u_] = fork
        return u_

    def detach(self, id_):
        self.forks.pop(id_)

    def replace(self, id_, *conds: Condition, completed: Condition, exclusive=False):
        new_fork = Fork(*conds, completed=completed, exclusive=exclusive)
        self.get(id_).substitute = new_fork
        self.forks[id_] = new_fork

    def send(self, u_: TelegramBot.Update):
        exp = []
        for id_, f in self.forks.items():
            f.process(u_)
            if f.expired():
                exp.append(id_)
        for id_ in exp:
            self.detach(id_)

    def get(self, id_) -> Fork:
        return self.forks[id_]

    def attach_join_detach(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], Fork):
            u = self.attach_fork(*args, **kwargs)
        else:
            u = self.attach(*args, **kwargs)
        self.get(u).join()
        ret = self.get(u).result
        self.detach(u)
        return ret


def wait_for(t: TelegramBot,
             *conditions: Condition,
             timeout=0,
             forks=None):

    t.daemon.delay = 0.5

    if timeout == 0:
        infinite = True
    else:
        infinite = False
        timeout_end = datetime.now() + timedelta(seconds=timeout)

    while True:
        for u in t.get_updates():
            for c in conditions:
                if c.meet(u.content):
                    c.callback(u.content)
                    if c.stop_return() is not None:
                        return c.stop_return(u.content)
                    continue
            if forks:
                forks.send(u)
        if not infinite:
            if timeout_end < datetime.now():
                return False
        sleep(0.1)


def wait_for_threaded(t: TelegramBot,
                      *conditions: Condition,
                      timeout=0,
                      forks=None):
    th = Thread(target=wait_for, args=(t, ) + conditions, kwargs={"timeout": timeout, "forks": forks},
                daemon=True)
    th.start()
    return th
