"""Atrapa do testów i demo."""


class FakeProvider:
    os_name = "fake"

    def __init__(self, script):
        self.script = list(script)  # [(idle_s, foreground_dict_or_None), ...]
        self.i = 0

    def _cur(self):
        return self.script[min(self.i, len(self.script) - 1)]

    def advance(self):
        self.i += 1

    def idle_seconds(self):
        return self._cur()[0]

    def foreground(self):
        return self._cur()[1]
