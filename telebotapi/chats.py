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
        if not isinstance(other, Chat):
            raise TypeError(other)
        return self.id == other.id

    @staticmethod
    def by_id(i):
        return Chat({"id": int(i)})


class User(Chat):
    def __init__(self, u):
        Chat.__init__(self, u)
        self.raw = u

    def __str__(self):
        return f"User({self.id})"

    def __repr__(self):
        return str(self)
