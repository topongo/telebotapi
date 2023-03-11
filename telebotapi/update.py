from .messages import Message


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
        self.content, self.type = Message.cast(u)
        self.raw = u

    def __str__(self):
        return f"Update(content={self.content}, type=\"{self.type}\")"

    def __repr__(self):
        return str(self)
