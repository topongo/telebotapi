import threading
import json
from http.client import HTTPSConnection
from urllib.parse import urlencode
from time import sleep


class File:
    def __init__(self, f):
        self.id = f["file_id"]
        self.size = f["file_size"]


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
        self.current_thread = threading.currentThread()
        self.daemon = self.Daemon(self.poll, self.current_thread, self.daemonDelay)

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
        if len(r["result"]) > 0:
            self.last_update = r["result"][0]["update_id"]
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
        def __init__(self, poll, parent_thread, delay):
            threading.Thread.__init__(self)
            self.poll = poll
            self.active = True
            self.delay = delay
            self.parent_thread = parent_thread

        def run(self):
            while self.active and self.parent_thread.is_alive():
                self.poll()
                sleep(self.delay)
                # print("Polled")

    def restart_daemon(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.daemon.is_alive():
            self.daemon.active = False
            self.daemon.join()
        self.daemon = self.Daemon(self.poll, self.current_thread, self.daemonDelay)
        self.daemon.start()

    def news(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.updated:
            self.updated = False
            return True
        else:
            return False

    def sendMessage(self, user, body, a=None):
        assert type(user) == TelegramBot.User
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "text": body}
        p.update(a)
        return self.query("sendMessage", p)
        # return True if telegram does, otherwise False

    def sendPhoto(self, user, photo, a=None):
        assert type(user) == TelegramBot.User
        assert type(photo) == TelegramBot.Photo
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "photo": photo.id}
        p.update(a)
        return self.query("sendPhoto", p)

    def sendSticker(self, user, sticker, a=None):
        assert type(user) == TelegramBot.User
        assert type(sticker) == TelegramBot.Sticker
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "sticker": sticker.id}
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
                    self.content = self.Message(u[i])
                    self.type = i
                    break

            self.raw = u

        class Message:
            def __init__(self, c):
                if "from" in c:
                    self.from_ = TelegramBot.User(c["from"])
                self.chat = TelegramBot.Chat(c["chat"])
                self.entities = []
                self.type = "unknown"
                self.text = ""
                if "text" in c:
                    self.type = "text"
                    self.text = c["text"]
                    if "entities" in c:
                        self.text = c["text"]
                        for i in c["entities"]:
                            self.entities.append(self.Entity(i, self.text))
                elif "photo" in c:
                    self.photos = []
                    self.type = "photo"
                    self.photo = TelegramBot.Photo(c["photo"])
                    if "caption" in c:
                        self.text = c["caption"]
                        for i in c["caption_entities"]:
                            self.entities.append(self.Entity(i, self.text))

                for i in dict([(k, c[k]) for k in c if k not in "text from chat entities caption caption_entities"]):
                    self.__setattr__(i, c[i])
                self.raw = c

            class Entity:
                def __init__(self, e, text):
                    self.offset = e["offset"]
                    self.length = e["length"]
                    self.type = e["type"]
                    self.text = text[self.offset:self.offset + self.length]
                    for i in dict([(k, e[k]) for k in e if k not in "offset length type"]):
                        self.__setattr__(i, e[i])
                    self.raw = e

    class User:
        def __init__(self, u):
            for i in u:
                self.__setattr__(i, u[i])
            self.raw = u

    class Chat:
        def __init__(self, c):
            for i in c:
                self.__setattr__(i, c[i])

    class Photo(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.height = f["height"]
            self.width = f["width"]

            self.raw = f

    class Sticker(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.height = f["height"]
            self.width = f["width"]
            for i in dict([(k, f[k]) for k in f if k not in "height width file_id"]):
                self.__setattr__(i, f[i])
