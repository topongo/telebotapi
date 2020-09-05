import threading
import json
from http.client import HTTPSConnection
from urllib.parse import urlencode
from time import sleep


class TelegramBot:
    def __init__(self, token, name=None):
        if len(token) == 46:
            self.token = token
        else:
            raise self.TokenException("Invalid token length, should be 46 and it's " + str(len(token)))

        self.h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
        self.c = HTTPSConnection("api.telegram.org")
        self.c_updates = HTTPSConnection("api.telegram.org")
        self.updates = []
        self.last_update = 0
        self.updated = False
        self.name = name
        self.daemonDelay = 1
        self.bootstrapped = False
        self.daemon = self.Daemon(self.poll, self.daemonDelay)

    class TokenException(Exception):
        pass

    class QueryException(Exception):
        pass

    class BootstrapException(Exception):
        pass

    def query(self, method, params, connection=None):
        if connection is None:
            connection = self.c

        connection.request("POST", "/bot{0}/{1}".format(self.token, method), urlencode(params), headers=self.h)
        return json.load(connection.getresponse())

    def getUpdates(self, a=None):
        # p = self.g
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"offset": self.last_update}
        p.update(a)
        return self.query("getUpdates", p, self.c_updates)

    def bootstrap(self):
        r = self.getUpdates()
        if not r["ok"]:
            raise self.QueryException(
                "Telegram responded: \"" + r["description"] + "\" with error code " + str(r["error_code"]))
        try:
            with open("telegrambot_data/last_offset", "r") as f:
                self.last_update = int(f.read())
        except (ValueError, FileNotFoundError):
            try:
                self.last_update = r["result"][0]["update_id"]
            except KeyError:
                self.last_update = 0
            with open("telegrambot_data/last_offset", "w+") as f:
                f.write(str(self.last_update))
        self.bootstrapped = True
        self.daemon.start()

    def poll(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        # print("Polled")
        p = self.getUpdates()
        if p["ok"]:
            if len(p["result"]) > 0:
                self.updated = True
                for u in p["result"]:
                    self.updates.append(self.Update(u))
                self.last_update = self.updates[-1].id + 1
                # print(self.g)

    class Daemon(threading.Thread):
        def __init__(self, poll, delay):
            threading.Thread.__init__(self)
            self.poll = poll
            self.active = True
            self.delay = delay

        def run(self):
            while self.active:
                self.poll()
                sleep(self.delay)
                # print("Polled")

    def restart_daemon(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.daemon.is_alive():
            self.daemon.active = False
            self.daemon.join()
        self.daemon = self.Daemon(self.poll, self.daemonDelay)
        self.daemon.start()

    def news(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.updated:
            self.updated = False
            return True
        else:
            return False

    def sendMessage(self, chat_id, body, a=None):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        params = {"chat_id": chat_id, "text": body}
        params.update(a)
        return json.load(self.c.getresponse())["ok"]
        # return True if telegram does, otherwise False

    def sendPhoto(self, chat_id, file_id, a=None):
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": chat_id, "photo": file_id}
        p.update(a)
        return self.query("sendPhoto", p)

    def sendSticker(self, chat_id, file_id, a=None):
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": chat_id, "sticker": file_id}
        p.update(a)
        return self.query("sendSticker", p)

    def daemon_remote(self, active, delay):
        self.daemon.active = active
        if delay is not None and delay != self.daemonDelay:
            self.daemonDelay = delay

        if self.bootstrapped:
            if delay is not None or active and not self.daemon.is_alive():
                self.restart_daemon()

    def has_updates(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        return len(self.updates) > 0

    def get_updates(self, chat_id=None):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if chat_id is None:
            for i in range(len(self.updates)):
                yield self.updates.pop(0)
        else:
            if type(chat_id) == int:
                for i in [k for k in self.updates if k.message.from_.id == chat_id]:
                    yield self.updates.pop(self.updates.index(i))
            elif type(chat_id) == list:
                for i in [k for k in self.updates if k.message.from_.id in chat_id]:
                    yield self.updates.pop(self.updates.index(i))
            else:
                raise TypeError("the provided id must be int or list")

    class Update:
        def __init__(self, u):
            self.id = u["update_id"]
            for i in ["message", "edited_message", "channel_post", "edited_channel_post"]:
                if i in u:
                    self.message = self.Message(u[i])
                    break

            self.raw = u

        class Message:
            def __init__(self, m):
                if "from" in m:
                    self.from_ = User(m["from"])
                self.chat = Chat(m["chat"])
                if "entities" in m:
                    self.entities = []
                    for i in m["entities"]:
                        self.entities.append(self.Entity(i))

                for i in dict([(k, m[k]) for k in m if k in "from chat entities"]):
                    self.__setattr__(i, m[i])
                self.raw = m

            class Entity:
                def __init__(self, e):
                    for i in e:
                        self.__setattr__(i, e[i])
                    self.raw = e


class User:
    def __init__(self, u):
        for i in u:
            self.__setattr__(i, u[i])
        self.raw = u


class Chat:
    def __init__(self, c):
        self.username = c["username"]
        self.id = c["id"]
        self.is_bot = c["type"]
