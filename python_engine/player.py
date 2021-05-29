import queue
import shlex
import subprocess
import threading
import time
import typing

HANDLER_TYPE = typing.Callable[[str], typing.Any]
NO_HANDLER: HANDLER_TYPE = lambda _: None

KILL_TIMEOUT: float = 1.0


class Player:
    def __init__(self, command: str, stdin_handler: HANDLER_TYPE = NO_HANDLER,
                 stdout_handler: HANDLER_TYPE = NO_HANDLER,
                 stderr_handler: HANDLER_TYPE = NO_HANDLER) -> None:
        self._process = subprocess.Popen(
            args=shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        self._stdin_handler: HANDLER_TYPE = stdin_handler
        self._stdout_handler: HANDLER_TYPE = stdout_handler
        self._stderr_handler: HANDLER_TYPE = stderr_handler

        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        self._stdout_thread = threading.Thread(target=self._monitor_stdout)
        self._stderr_thread = threading.Thread(target=self._monitor_stderr)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def stop(self) -> None:
        if not hasattr(self, "_process"):
            return

        self._process.terminate()

        timeout_time = time.perf_counter() + KILL_TIMEOUT
        while time.perf_counter() < timeout_time:
            if self._process.poll() is not None:
                break
        else:
            self._process.kill()
            self._process.wait()

    def _monitor_stdout(self) -> None:
        for line in self._process.stdout:
            self.stdout_queue.put(line)
            self._stdout_handler(line)

    def _monitor_stderr(self) -> None:
        for line in self._process.stderr:
            self.stderr_queue.put(line)
            self._stderr_handler(line)

    def send_stdin(self, input_string: str) -> None:
        self._process.stdin.write(input_string)
        self._process.stdin.flush()

        self._stdin_handler(input_string)

    def is_alive(self) -> bool:
        return self._process.poll() is None


class TurnThread(threading.Thread):
    def __init__(self, player: Player, input_string: str) -> None:
        self.output_list: list[str] = []
        self.had_error: bool = False

        super().__init__(target=self._do_turn, args=(player, input_string))
        self.start()

    def _do_turn(self, player: Player, input_string: str) -> None:
        try:
            player.send_stdin(input_string)
            while player.is_alive() or not player.stdout_queue.empty():
                try:
                    line = str(player.stdout_queue.get_nowait()).strip()
                    if line == "go":
                        break
                    self.output_list.append(line)
                except queue.Empty:
                    ...
        except OSError:
            self.had_error = True
