from .entities import Entity
from .files import File, PhotoFile
from .chats import User, Chat


class CallbackQuery:
    def __init__(self, c):
        self.id = c["id"]
        if "from" in c:
            self.from_ = User(c["from"])
        self.entities = []
        if "entities" in c:
            self.text = c["text"]
            for i in c["entities"]:
                self.entities.append(Entity(i, self.text))

        self.type = "callback_query"
        self.original_message = Message.cast({"message": c["message"]})[0]
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


class Message:
    def __init__(self, c):
        self.id = c["message_id"]
        if "from" in c:
            self.from_ = User(c["from"])
        self.chat = Chat(c["chat"])
        if "reply_to_message" in c:
            self.reply_to_message = Message.cast({"message": c["reply_to_message"]})[
                0]
        self.entities = []
        if "entities" in c:
            self.text = c["text"]
            for i in c["entities"]:
                self.entities.append(Entity(i, self.text))

    def __str__(self):
        return f"GenericMessage(from={self.from_}, chat={self.chat})"

    @staticmethod
    def cast(u):
        for i in ("message", "edited_message", "channel_post", "edited_channel_post", "callback_query",
                  "result"):
            if i in u:
                for t, c in zip(["text", "photo", "message", "sticker", "audio"],
                                [Text, PhotoMessage, CallbackQuery, Sticker, Audio]):
                    if t in u[i]:
                        return c(u[i]), t

                return Message(u[i]), i
        raise TypeError(f"Unrecognized data: {u}")

    @staticmethod
    def by_id(message_id, chat_id):
        return Message({"message_id": message_id, "chat": Chat.by_id(chat_id).raw})


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
                self.__setattr__(k, PhotoMessage(v))
            else:
                self.__setattr__(k, v)


class Sticker(Message, File):
    def __init__(self, f):
        Message.__init__(self, f)
        s = f["sticker"]
        self.file = File(s)
        self.height = s["height"]
        self.width = s["width"]
        self.raw = f

    @staticmethod
    def from_id(id_):
        return Sticker({
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
               f"{Message.__str__(self)}>"


class PhotoMessage(Message):
    def __init__(self, c):
        Message.__init__(self, c)
        self.photos = []
        self.type = "photo"
        self.thumbnail = PhotoFile(c["photo"][0])
        self.photo = PhotoFile(c["photo"][1])
        if "caption" in c:
            self.text = c["caption"]
            for i in c["caption_entities"]:
                self.entities.append(Entity(i, self.text))

    @staticmethod
    def from_id(id_):
        return PhotoMessage({
            "file_id": id_,
            "file_unique_id": "",
            "file_size": ""
        })

    def __str__(self):
        return f"PhotoMessage({self.photo})"

    def __repr__(self):
        return str(self)
