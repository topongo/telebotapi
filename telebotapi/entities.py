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
