from .messages import Message


class QueryException(Exception):
    def __init__(self, data, method, query):
        self.error_code = data.get("error_code")
        self.description = data.get("description")
        self.method = method
        self.query = query

    def __str__(self):
        return f"code {self.error_code}: {self.description}"

    @staticmethod
    def cast(data, method, query):
        c = QueryException
        if "description" in data:
            if data["description"] == "Bad Request: message to edit not found" or \
                    data["description"] == "Bad Request: message to delete not found":
                c = MessageNotFound
            elif "Bad Request: message is not modified:" in data["description"]:
                c = MessageNotModified
            elif "Too Many Requests" in data["description"]:
                c = TooManyRequests
        return c(data, method, query)


class MessageNotFound(QueryException):
    def __init__(self, *args, **kwargs):
        super(MessageNotFound, self).__init__(*args, **kwargs)
        self.message = Message.by_id(self.query["message_id"], self.query["chat_id"])


class MessageNotModified(QueryException):
    def __init__(self, *args, **kwargs):
        super(MessageNotModified, self).__init__(*args, **kwargs)
        self.message = Message.by_id(self.query["message_id"], self.query["chat_id"])
        if self.method == "editMessageText":
            self.body = self.query["text"]
        elif self.method == "editMessageCaption":
            self.body = self.query["caption"]
        else:
            self.body = None


class TooManyRequests(QueryException):
    def __init__(self, *args, **kwargs):
        super(TooManyRequests, self).__init__(*args, **kwargs)
        try:
            self.delay = int(self.description.split("retry after ")[-1])
        except ValueError:
            self.delay = None
