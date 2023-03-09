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


class PhotoFile(File):
    def __init__(self, f):
        File.__init__(self, f)
        self.height = f["height"]
        self.width = f["width"]

    @staticmethod
    def from_id(id_):
        t_ = File.from_id(id_).raw
        t_.update({"height": 0, "width": 0})
        return PhotoFile(t_)


class Document(File):
    def __init__(self, f):
        File.__init__(self, f)
        self.file_name = f["file_name"]
        self.mime = f["mime_type"]
