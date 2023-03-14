import threading
from socket import timeout
from requests import post
from requests.exceptions import ConnectionError, ConnectTimeout, Timeout
from time import sleep
from collections.abc import Iterable
from sys import stderr
from .update import Update
from .chats import Chat, User
from .messages import CallbackQuery, Message, Sticker
from .files import PhotoFile, Document, File
from .exceptions import QueryException, TooManyRequests


class TelegramBot:
    def __init__(self, token, name=None, safe_mode=None, max_telegram_timeout=60, auto_retry=None):
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
        self.auto_retry = auto_retry

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
            exc = QueryException.cast(r, method, params)
            if isinstance(exc, TooManyRequests) and self.auto_retry:
                delay = int(exc.timeout or 30)
                print(f"too many requests, waiting {delay} seconds", file=stderr)
                sleep(delay)
                return self.query(method, params, connection, headers)
            raise exc
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
                        self.updates.append(Update(u))
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
        assert type(user) == User or type(user) == Chat
        assert type(reply_markup) is str or reply_markup is None
        assert reply_to_message is None or isinstance(reply_to_message, Message)
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
        return Message.cast(self.query("sendMessage", p))[0]
        # return True if telegram does, otherwise False

    def editMessageText(self, message, body, parse_mode="markdown", reply_markup=None, a=None):
        assert isinstance(message, Message) or isinstance(message, CallbackQuery)
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
        if (ret := self.query("editMessageText", p)) is None:
            return message
        else:
            return Message.cast(ret)[0]
        # return True if telegram does, otherwise False

    def editMessageCaption(self, message, caption, parse_mode="markdown", reply_markup=None, a=None):
        assert isinstance(message, Message) or isinstance(message, CallbackQuery)
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
            "caption": caption,
            "parse_mode": parse_mode
        }
        p.update(a)
        if reply_markup:
            a = {
                "reply_markup": reply_markup
            }
            p.update(a)
        if (ret := self.query("editMessageCaption", p)) is None:
            return message
        else:
            return Message.cast(ret)[0]
        # return True if telegram does, otherwise False

    def editMessageReplyMarkup(self, reply_markup, message=None, a=None):
        if not message:
            raise TypeError("message parameter must be specified.")
        if not isinstance(reply_markup, str):
            raise TypeError("reply_markup must be of type str")
        if not isinstance(message, Message):
            raise TypeError("message must be of type Message")
        data = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "reply_markup": reply_markup
        }
        if a is not None:
            data.update(a)
        return self.query("editMessageReplyMarkup", data)

    def deleteMessage(self, message, a=None):
        assert isinstance(message, Message)
        p = {
            "chat_id": message.chat.id,
            "message_id": message.id
        }
        if a:
            p.update(a)
        return self.query("deleteMessage", p)

    def sendPhoto(self, user, photo, caption=None, parse_mode="markdown", reply_to_message=None, a=None):
        assert isinstance(user, Chat)
        assert isinstance(photo, (PhotoFile, str))
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        p = {
            "chat_id": user.id,
            "photo": photo if isinstance(photo, str) else photo.id,
            "parse_mode": parse_mode
        }
        if caption is not None:
            p["caption"] = caption
        p.update(a)
        if reply_to_message:
            a = {
                "reply_to_message_id": reply_to_message.id
            }
            p.update(a)
        return Message.cast(self.query("sendPhoto", p))[0]

    def sendSticker(self, user, sticker, reply_to_message=None, a=None):
        if not isinstance(user, Chat):
            raise TypeError(user)
        assert type(sticker) == Sticker
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
        return Message.cast(self.query("sendSticker", p))[0]

    def sendDocument(self, user, document, name=None, mime=None, reply_to_message=None, a=None):
        if type(user) is not User and type(user) is not Chat:
            raise TypeError(f"User argument must be User or Chat, {type(user)} given.")
        if issubclass(type(document), File) is not File and type(document) is not bytes:
            raise TypeError(f"Document argument must be a File object/children, {type(document)} given.")
        if a is not None:
            assert type(a) == dict
        else:
            a = {}
        if type(document) is Document:
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
        assert type(chat_in) == Chat
        assert type(chat_out) == Chat
        assert type(message) == Message
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
        return Message.cast(self.query("forwardMessage", p))[0]

    def answerCallbackQuery(self, callback_query, text, show_alert=None, a=None):
        assert isinstance(callback_query, CallbackQuery)
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
        assert type(user) == User
        p = {"chat_id": user.id}
        q = self.query("getChat", p)
        if not q["ok"]:
            raise TelegramBot.ResponseNotOkException(q)
        else:
            return Chat(q["result"])

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

    def get_updates(self, from_=None) -> Iterable[Update]:
        if not self.bootstrapped:
            raise self.BootstrapException("perform bootstrap before other operations.")
        if from_ is None:
            for i in range(len(self.updates)):
                tmp = self.updates.pop(0)
                yield tmp
        else:
            if type(from_) is User or type(from_) is Chat:
                for i in [k for k in self.updates if k.message.from_.id == from_.id]:
                    tmp = self.updates.pop(self.updates.index(i))
                    yield tmp
            elif type(from_) == list and \
                    all((type(i) is Chat or type(i) is User for i in from_)):
                for i in [k for k in self.updates if k.message.from_.id in from_.id]:
                    tmp = self.updates.pop(self.updates.index(i))
                    yield tmp
            else:
                raise self.TypeError(
                    f"Parameter \"from_\" must be User or Chat {type(from_)} provided.")

    def read(self, from_=None, type_=None):
        pass


if __name__ == "__main__":
    from sys import argv

    if len(argv) < 2:
        print("No token supplied")
        exit()
    t = TelegramBot(argv[1])
    t.bootstrap()
