A shift-out or shift-in byte more than two bytes before a stream's first escape no longer rules out ISO-2022-JP, as in
chardetng: ``b"\x0eab\x1b(B"`` now detects as ISO-2022-JP instead of windows-1252.
