import threading
import json
from socket import timeout
from requests import get, post
from requests.exceptions import Timeout
from urllib.parse import urlencode
from time import sleep


class File:
    def __init__(self, f):
        self.id = f["file_id"]
        self.size = f["file_size"]
        self.raw = f


class TelegramBot:
    def __init__(self, token, name=None):
        if len(token) == 46:
            self.token = token
        else:
            raise self.TokenException("Invalid token length, should be 46 and it's " + str(len(token)))

        self.busy = False
        self.h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
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

    class GenericQueryException(Exception):
        pass

    class BootstrapException(Exception):
        pass

    class ResponseNotOkException(Exception):
        pass

    class TypeError(Exception):
        pass

    def query(self, method, params, connection=None, headers=None):
        if headers is None:
            headers = self.h

        while self.busy:
            sleep(0.5)

        while True:
            try:
                self.busy = True
                r = post("https://api.telegram.org/bot{0}/{1}".format(self.token, method), data=params, headers=headers).json()
                self.busy = False
                break
            except timeout:
                print("Telegram timed out, retrying...")
                self.busy = False
        if not r["ok"]:
            raise self.GenericQueryException(
                "Telegram responded: \"" + r["description"] + "\" with error code " + str(r["error_code"]))
        return r

    def getUpdates(self, a=None):
        # p = self.g
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"offset": self.last_update}
        p.update(a)
        return self.query("getUpdates", p)

    def bootstrap(self):
        r = self.getUpdates()
        if not r["ok"]:
            raise self.GenericQueryException(
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
            self.verbose = False
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

    def sendMessage(self, user, body, parse_mode="markdown", a=None):
        assert type(user) == TelegramBot.User or type(user) == TelegramBot.Chat
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "text": body, "parse_mode": parse_mode}
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

    def sendDocument(self, user, document, name=None, mime=None, a=None):
        if type(user) is not TelegramBot.User and type(user) is not TelegramBot.Chat:
            raise TypeError(f"User argument must be TelegramBot.User or TelegramBot.Chat, {type(user)} given.")
        if issubclass(type(document), File) is not File and type(document) is not bytes:
            raise TypeError(f"Document argument must be a File object/children, {type(document)} given.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        if type(document) is TelegramBot.Document:
            files = None
            p = {"chat_id": user.id, "document": document.id}
        else:
            files = {"document": (["document", name][type(name) is str], document, ["application/octet-stream", mime][type(mime) is str])}
            p = {"chat_id": user.id}
        p.update(a)
        while True:
            try:
                r = post("https://api.telegram.org/bot{0}/sendDocument".format(self.token),
                                  files=files, data=p).json()
                break
            except Timeout:
                print("Telegram timed out, retrying...")
        if not r["ok"]:
            raise self.GenericQueryException(
                "Telegram responded: \"" + r["description"] + "\" with error code " + str(r["error_code"]))
        return r

    def forwardMessage(self, chat_in, chat_out, message, a=None):
        assert type(chat_in) == TelegramBot.Chat
        assert type(chat_out) == TelegramBot.Chat
        assert type(message) == TelegramBot.Update.Message
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": chat_out.id, "from_chat_id": chat_in.id, "message_id": message.id}
        p.update(a)
        return self.query("forwardMessage", p)


    def chat_from_user(self, user):
        assert type(user) == TelegramBot.User
        p = {"chat_id": user.id}
        q = self.query("getChat", p)
        if not q["ok"]:
            raise TelegramBot.ResponseNotOkException(q)
        else:
            return TelegramBot.Chat(q["result"])

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

    def get_updates(self, from_=None):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if from_ is None:
            for i in range(len(self.updates)):
                yield self.updates.pop(0)
        else:
            if type(from_) is TelegramBot.User or type(from_) is TelegramBot.Chat:
                for i in [k for k in self.updates if k.message.from_.id == from_.id]:
                    yield self.updates.pop(self.updates.index(i))
            elif type(from_) == list and all((type(i) is TelegramBot.Chat or type(i) is TelegramBot.User for i in from_)):
                for i in [k for k in self.updates if k.message.from_.id in from_.id]:
                    yield self.updates.pop(self.updates.index(i))
            else:
                raise self.TypeError(
                    f"Parameter \"from_\" must be TelegramBot.User or TelegramBot.Chat {type(from_)} provided.")

    def read(self, from_=None, type_=None):
        pass

    class Update:
        def __init__(self, u):
            self.id = u["update_id"]
            for i in ("message", "edited_message", "channel_post", "edited_channel_post"):
                if i in u:
                    if "text" in u[i]:
                        self.content = self.Text(u[i])
                    elif "photo" in u[i]:
                        self.content = self.Photo(u[i])
                    self.type = i
                break
            self.raw = u

        class Message:
            def __init__(self, c):
                self.id = c["message_id"]
                if "from" in c:
                    self.from_ = TelegramBot.User(c["from"])
                self.chat = TelegramBot.Chat(c["chat"])
                self.entities = []
                if "entities" in c:
                    self.text = c["text"]
                    for i in c["entities"]:
                        self.entities.append(self.Entity(i, self.text))

            class Entity:
                def __init__(self, e, text):
                    self.offset = e["offset"]
                    self.length = e["length"]
                    self.type = e["type"]
                    self.text = text[self.offset:self.offset + self.length]
                    for i in dict([(k, e[k]) for k in e if k not in "offset length type"]):
                        self.__setattr__(i, e[i])
                    self.raw = e

        class Text(Message):
            def __init__(self, c):
                TelegramBot.Update.Message.__init__(self, c)
                self.type = "text"
                self.text = c["text"]

                for i in dict([(k, c[k]) for k in c if k not in "id text from chat entities caption caption_entities"]):
                    self.__setattr__(i, c[i])
                self.raw = c

        class Photo(Message):
            def __init__(self, c):
                TelegramBot.Update.Message.__init__(self, c)
                self.photos = []
                self.type = "photo"
                self.photo = TelegramBot.Photo(c["photo"])
                if "caption" in c:
                    self.text = c["caption"]
                    for i in c["caption_entities"]:
                        self.entities.append(self.Entity(i, self.text))

    class Chat:
        def __init__(self, c):
            self.id = c["id"]
            for i in ("last_name", "username", "language_code", "first_name", "is_bot"):
                if i in c:
                    self.__setattr__(i, c[i])
            self.raw = c

    class User(Chat):
        def __init__(self, u):
            TelegramBot.Chat.__init__(self, u)
            self.raw = u

    class Photo(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.height = f["height"]
            self.width = f["width"]

    class Sticker(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.height = f["height"]
            self.width = f["width"]

    class Document(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.file_name = f["file_name"]
            self.mime = f["mime_type"]
