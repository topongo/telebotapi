import threading
import json
from socket import timeout
from requests import get, post
from requests.exceptions import ConnectionError, ConnectTimeout, Timeout
from urllib.parse import urlencode
from time import sleep


class File:
    def __init__(self, f):
        self.id = f["file_id"]
        self.unique_id = f["file_unique_id"]
        self.size = f["file_size"]
        self.raw = f

    def __str__(self):
        return f"File(id={self.id}, unique_id={self.unique_id}, size={self.size})"

    @staticmethod
    def from_id(id_):
        return File({
            "file_id": id_,
            "file_unique_id": "",
            "file_size": 0
        })


class TelegramBot:
    def __init__(self, token, name=None, safe_mode=None, max_telegram_timeout=60):
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
        self.daemon_delay = 1
        self.bootstrapped = False
        self.current_thread = threading.current_thread()
        self.daemon = self.Daemon(self.poll, self.current_thread, self.daemon_delay)
        self.safe_mode = safe_mode
        self.max_telegram_timeout = max_telegram_timeout

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

        delay = 1
        while True:
            try:
                self.busy = True
                r = post("https://api.telegram.org/bot{0}/{1}".format(self.token, method), data=params,
                         headers=headers, timeout=5).json()
                break
            except (timeout, Timeout, ConnectTimeout, ConnectionError):
                print(f"Telegram timed out, retrying in {delay} seconds...")
                sleep(delay)
                delay = min(delay * 2, self.max_telegram_timeout)
            finally:
                self.busy = False
        if not r["ok"]:
            if "message is not modified" in r["description"]:
                print(":: warn: message not modified.")
                return r
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
                    try:
                        self.updates.append(self.Update(u))
                    except TypeError as e:
                        if not self.safe_mode:
                            raise e
                if len(self.updates) == 0:
                    self.last_update = p["result"][-1]["update_id"]
                else:
                    self.last_update = self.updates[-1].id + 1

    class Daemon(threading.Thread):
        def __init__(self, poll, parent_thread, delay):
            threading.Thread.__init__(self)
            self.poll = poll
            self.active = True
            self.verbose = False
            self.delay = delay
            self.parent_thread = parent_thread

        def run(self):
            try:
                while self.active and self.parent_thread.is_alive():
                    self.poll()
                    sleep(self.delay)
                    # print("Polled")
            except KeyboardInterrupt:
                pass

    def restart_daemon(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.daemon.is_alive():
            self.daemon.active = False
            self.daemon.join()
        self.daemon = self.Daemon(self.poll, self.current_thread, self.daemon_delay)
        self.daemon.start()

    def news(self):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if self.updated:
            self.updated = False
            return True
        else:
            return False

    def sendMessage(self, user, body, parse_mode="markdown", reply_markup=None, reply_to_message=None, a=None):
        assert type(user) == TelegramBot.User or type(user) == TelegramBot.Chat
        assert type(reply_markup) is str or reply_markup is None
        assert reply_to_message is None or isinstance(reply_to_message, TelegramBot.Update.Message)
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "text": body, "parse_mode": parse_mode}
        p.update(a)
        if reply_markup:
            a = {
                "reply_markup": reply_markup
            }
            p.update(a)
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        return TelegramBot.Update.Message.detect_type(self.query("sendMessage", p))[0]
        # return True if telegram does, otherwise False

    def editMessageText(self, message, body, parse_mode="markdown", reply_markup=None, a=None):
        assert isinstance(message, TelegramBot.Update.Message) or isinstance(message, TelegramBot.Update.CallbackQuery)
        assert type(reply_markup) is str or reply_markup is None
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "text": body,
            "parse_mode": parse_mode
        }
        p.update(a)
        if reply_markup:
            a = {
                "reply_markup": reply_markup
            }
            p.update(a)
        return self.query("editMessageText", p)
        # return True if telegram does, otherwise False

    def editMessageReplyMarkup(self, reply_markup, message=None, a=None):
        if not message:
            raise TypeError("message parameter must be specified.")
        if not isinstance(reply_markup, str):
            raise TypeError("reply_markup must be of type str")
        if not isinstance(message, TelegramBot.Update.Message):
            raise TypeError("message must be of type TelegramBot.Update.Message")
        data = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "reply_markup": reply_markup
        }
        if a is not None:
            data.update(a)
        return self.query("editMessageReplyMarkup", data)

    def deleteMessage(self, message, a=None):
        assert isinstance(message, TelegramBot.Update.Message)
        p = {
            "chat_id": message.chat.id,
            "message_id": message.id
        }
        if a:
            p.update(a)
        return self.query("deleteMessage", p)

    def sendPhoto(self, user, photo, reply_to_message=None, a=None):
        assert isinstance(user, TelegramBot.Chat)
        assert isinstance(photo, TelegramBot.Photo)
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "photo": photo.id}
        p.update(a)
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        return self.query("sendPhoto", p)

    def sendSticker(self, user, sticker, reply_to_message=None, a=None):
        if not isinstance(user, TelegramBot.Chat):
            raise TypeError(user)
        assert type(sticker) == TelegramBot.Update.Sticker
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": user.id, "sticker": sticker.file.id}
        p.update(a)
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        return self.query("sendSticker", p)

    def sendDocument(self, user, document, name=None, mime=None, reply_to_message=None, a=None):
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
            files = {
                "document": (
                    ["document", name][type(name) is str],
                    document,
                    ["application/octet-stream", mime][type(mime) is str]
                )
            }
            p = {"chat_id": user.id}
        p.update(a)
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        while True:
            try:
                r = post("https://api.telegram.org/bot{0}/sendDocument".format(self.token),
                         files=files, data=p, timeout=5).json()
                break
            except (timeout, Timeout, ConnectTimeout, ConnectionError):
                print("Telegram timed out, retrying...")
        if not r["ok"]:
            raise self.GenericQueryException(
                "Telegram responded: \"" + r["description"] + "\" with error code " + str(r["error_code"]))
        return r

    def forwardMessage(self, chat_in, chat_out, message, reply_to_message=None, a=None):
        assert type(chat_in) == TelegramBot.Chat
        assert type(chat_out) == TelegramBot.Chat
        assert type(message) == TelegramBot.Update.Message
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {"chat_id": chat_out.id, "from_chat_id": chat_in.id, "message_id": message.id}
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        p.update(a)
        return self.query("forwardMessage", p)

    def answerCallbackQuery(self, callback_query, text, show_alert=None, a=None):
        assert isinstance(callback_query, TelegramBot.Update.CallbackQuery)
        assert isinstance(text, str)
        assert isinstance(show_alert, bool) or show_alert is None
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        if show_alert is None:
            show_alert = False
        p = {"callback_query_id": callback_query.id, "text": text, "show_alert": show_alert}
        p.update(a)
        return self.query("answerCallbackQuery", p)

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
        if delay is not None and delay != self.daemon_delay:
            self.daemon_delay = delay

        if self.bootstrapped:
            if delay is not None or active and not self.daemon.is_alive():
                self.restart_daemon()

    def has_updates(self) -> bool:
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        return len(self.updates) > 0

    def get_updates(self, from_=None):
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if from_ is None:
            for i in range(len(self.updates)):
                tmp = self.updates.pop(0)
                yield tmp
        else:
            if type(from_) is TelegramBot.User or type(from_) is TelegramBot.Chat:
                for i in [k for k in self.updates if k.message.from_.id == from_.id]:
                    tmp = self.updates.pop(self.updates.index(i))
                    yield tmp
            elif type(from_) == list and \
                    all((type(i) is TelegramBot.Chat or type(i) is TelegramBot.User for i in from_)):
                for i in [k for k in self.updates if k.message.from_.id in from_.id]:
                    tmp = self.updates.pop(self.updates.index(i))
                    yield tmp
            else:
                raise self.TypeError(
                    f"Parameter \"from_\" must be TelegramBot.User or TelegramBot.Chat {type(from_)} provided.")

    def read(self, from_=None, type_=None):
        pass

    class Update:
        def __init__(self, u):
            self.id = u["update_id"]
            """
            for i in ("message", "edited_message", "channel_post", "edited_channel_post", "callback_query"):

                if i in u:
                    if "text" in u[i]:
                        self.content = self.Text(u[i])
                    elif "photo" in u[i]:
                        self.content = self.Photo(u[i])
                    elif "message" in u[i]:
                        self.content = self.CallbackQuery(u[i])
                    self.type = i
                    break
            """
            self.content, self.type = TelegramBot.Update.Message.detect_type(u)
            self.raw = u

        def __str__(self):
            return f"Update(content={self.content}, type=\"{self.type}\")"

        def __repr__(self):
            return str(self)

        class Message:
            def __init__(self, c):
                self.id = c["message_id"]
                if "from" in c:
                    self.from_ = TelegramBot.User(c["from"])
                self.chat = TelegramBot.Chat(c["chat"])
                if "reply_to_message" in c:
                    self.reply_to_message = TelegramBot.Update.Message.detect_type({"message": c["reply_to_message"]})[
                        0]
                self.entities = []
                if "entities" in c:
                    self.text = c["text"]
                    for i in c["entities"]:
                        self.entities.append(self.Entity(i, self.text))

            def __str__(self):
                return f"GenericMessage(from={self.from_}, chat={self.chat})"

            @staticmethod
            def detect_type(u):
                for i in ("message", "edited_message", "channel_post", "edited_channel_post", "callback_query",
                          "result"):
                    if i in u:
                        if "text" in u[i]:
                            return TelegramBot.Update.Text(u[i]), i
                        elif "photo" in u[i]:
                            return TelegramBot.Update.Photo(u[i]), i
                        elif "message" in u[i]:
                            return TelegramBot.Update.CallbackQuery(u[i]), i
                        elif "sticker" in u[i]:
                            return TelegramBot.Update.Sticker(u[i]), i
                        elif "audio" in u[i]:
                            return TelegramBot.Update.Audio(u[i]), i
                        else:
                            # return generic message
                            return TelegramBot.Update.Message(u[i]), i
                            # raise TypeError(f"Malformed data: {u[i]}")
                raise TypeError(f"Unrecognized data: {u}")

            class Entity:
                def __init__(self, e, text):
                    self.offset = e["offset"]
                    self.length = e["length"]
                    self.type = e["type"]
                    self.text = text[self.offset:self.offset + self.length]
                    for i in dict([(k, e[k]) for k in e if k not in "offset length type"]):
                        self.__setattr__(i, e[i])
                    self.raw = e

                def __str__(self):
                    return f"Entity(\"{self.text}\", o={self.offset}, l={self.length}, type=\"{self.type}\")"

                def __repr__(self):
                    return str(self)

        class Text(Message):
            def __init__(self, c):
                super().__init__(c)
                self.type = "text"
                self.text = c["text"]

                for k, v in [
                    (k, v)
                    for k, v in c.items()
                    if k not in "id text from chat entities caption caption_entities reply_to_message"
                ]:
                    self.__setattr__(k, v)
                self.raw = c

            def __str__(self):
                return f"Text(\"{self.text}\", chat={self.chat})"

            def __repr__(self):
                return str(self)

        class Audio(Message, File):
            def __init__(self, c):
                super().__init__(c)
                File.__init__(self, c)
                self.duration = c["duration"]
                for k, v in [
                    (k, v)
                    for k, v in c.items()
                    if k not in "performer title file_name mime_type thumb"
                ]:
                    if k == "thumb":
                        self.__setattr__(k, TelegramBot.Photo(v))
                    else:
                        self.__setattr__(k, v)

        class Sticker(Message, File):
            def __init__(self, f):
                TelegramBot.Update.Message.__init__(self, f)
                s = f["sticker"]
                self.file = File(s)
                self.height = s["height"]
                self.width = s["width"]
                self.raw = f

            @staticmethod
            def from_id(id_):
                return TelegramBot.Update.Sticker({
                    "message_id": 0,
                    "chat": {
                        "id": 0
                    },
                    "sticker": {
                        "file_id": id_,
                        "file_unique_id": "",
                        "file_size": "",
                        "height": "",
                        "width": ""
                    },
                })

            def __repr__(self):
                return str(self)

            def __str__(self):
                return f"Sticker(height={self.height}, width={self.width}) <derived from {self.file} and " \
                       f"{TelegramBot.Update.Message.__str__(self)}>"

        class CallbackQuery:
            def __init__(self, c):
                self.id = c["id"]
                if "from" in c:
                    self.from_ = TelegramBot.User(c["from"])
                self.entities = []
                if "entities" in c:
                    self.text = c["text"]
                    for i in c["entities"]:
                        self.entities.append(TelegramBot.Update.Message.Entity(i, self.text))

                self.type = "callback_query"
                self.original_message = TelegramBot.Update.Message.detect_type({"message": c["message"]})[0]
                self.chat = self.original_message.chat
                self.chat_instance = c["chat_instance"]
                self.data = c["data"]

                for i in dict([(k, c[k]) for k in c if k not in "id text from chat entities caption caption_entities"
                                                                "chat_instance data message reply_to_message"]):
                    self.__setattr__(i, c[i])
                self.raw = c

            def __str__(self):
                return f"CallbackQuery(id={self.id}, chat_instance={self.chat_instance}, " \
                       f"original_message={self.original_message})"

            def __repr__(self):
                return str(self)

        class Photo(Message):
            def __init__(self, c):
                TelegramBot.Update.Message.__init__(self, c)
                self.photos = []
                self.type = "photo"
                self.thumbnail = TelegramBot.Photo(c["photo"][0])
                self.photo = TelegramBot.Photo(c["photo"][1])
                if "caption" in c:
                    self.text = c["caption"]
                    for i in c["caption_entities"]:
                        self.entities.append(self.Entity(i, self.text))

            @staticmethod
            def from_id(id_):
                return TelegramBot.Photo({
                    "file_id": id_,
                    "file_unique_id": "",
                    "file_size": ""
                })

            def __str__(self):
                return f"Photo({self.photo})"

            def __repr__(self):
                return str(self)

    class Chat:
        def __init__(self, c):
            self.id = c["id"]
            for i in ("last_name", "type", "username", "language_code", "first_name", "is_bot"):
                if i in c:
                    self.__setattr__(i, c[i])
            self.raw = c

        def __str__(self):
            return f"Chat({self.id})"

        def __repr__(self):
            return str(self)

        def __eq__(self, other):
            if not isinstance(other, TelegramBot.Chat):
                raise TypeError(other)
            return self.id == other.id

        @staticmethod
        def by_id(i):
            return TelegramBot.Chat({"id": int(i)})

    class User(Chat):
        def __init__(self, u):
            TelegramBot.Chat.__init__(self, u)
            self.raw = u

        def __str__(self):
            return f"User({self.id})"

        def __repr__(self):
            return str(self)

    class Photo(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.height = f["height"]
            self.width = f["width"]

        @staticmethod
        def from_id(id_):
            t_ = File.from_id(id_).raw
            t_.update({"height": 0, "width": 0})
            return TelegramBot.Photo(t_)

    class Document(File):
        def __init__(self, f):
            File.__init__(self, f)
            self.file_name = f["file_name"]
            self.mime = f["mime_type"]


if __name__ == "__main__":
    from sys import argv

    if len(argv) < 2:
        print("No token supplied")
        exit()
    t = TelegramBot(argv[1])
    t.bootstrap()
