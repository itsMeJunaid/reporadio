import threading
from types import SimpleNamespace

from reporadio.index.store import Hit
from reporadio.ingest.fetcher import Digest
from reporadio.session.caller import answer_question
from reporadio.session.memory import QA, SessionMemory


class FakeIndex:
    def __init__(self, hits, ready=True):
        self._hits = hits
        self.ready = threading.Event()
        if ready:
            self.ready.set()

    def query(self, text, k=6):
        return self._hits


class FakeChat:
    def __init__(self, answer="It's in cli dot py. Back to the tour."):
        self.calls = 0
        self.messages = None
        self._answer = answer
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        self.messages = kwargs["messages"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._answer))]
        )


def digest():
    return Digest(
        url="u", name="fastapi/typer", commit="a" * 10, summary="", tree="src/",
        files={},
    )


HITS = [
    Hit(path="src/typer/cli.py", start_line=42, text="app = typer.Typer()", distance=0.1),
    Hit(path="src/typer/main.py", start_line=1, text="from .cli import app", distance=0.3),
]


def test_grounded_answer_cites_files_and_updates_memory():
    client = FakeChat()
    memory = SessionMemory()
    qa = answer_question("where is the CLI?", FakeIndex(HITS), digest(), memory, client=client)
    assert client.calls == 1
    assert "cli dot py" in qa.answer
    assert "src/typer/cli.py" in qa.files
    assert len(memory) == 1


def test_prompt_forbids_out_of_context_answers():
    client = FakeChat()
    answer_question("where is auth?", FakeIndex(HITS), digest(), SessionMemory(), client=client)
    system = client.messages[0]["content"]
    user = client.messages[1]["content"]
    assert "ONLY from the retrieved chunks" in system
    assert "Back to the tour." in system
    assert "[src/typer/cli.py:42]" in user
    assert "where is auth?" in user


def test_no_hits_answers_honestly_without_llm_call():
    client = FakeChat()
    qa = answer_question("where is auth?", FakeIndex([]), digest(), SessionMemory(), client=client)
    assert client.calls == 0
    assert "Honest answer" in qa.answer
    assert qa.answer.endswith("Back to the tour.")


def test_index_not_ready_says_still_indexing():
    client = FakeChat()
    qa = answer_question(
        "anything?", FakeIndex(HITS, ready=False), digest(), SessionMemory(),
        client=client, wait_index_s=0.05,
    )
    assert client.calls == 0
    assert "still filing" in qa.answer


def test_memory_keeps_last_five_and_reaches_prompt():
    memory = SessionMemory()
    for i in range(7):
        memory.add(QA(question=f"q{i}", answer=f"a{i}"))
    assert len(memory) == 5
    rendered = memory.render()
    assert "q2" in rendered and "q6" in rendered
    assert "q0" not in rendered and "q1" not in rendered

    client = FakeChat()
    answer_question("next?", FakeIndex(HITS), digest(), memory, client=client)
    assert "RECENT Q&A" in client.messages[0]["content"]
    assert "q6" in client.messages[0]["content"]


def test_empty_memory_not_injected():
    client = FakeChat()
    answer_question("q", FakeIndex(HITS), digest(), SessionMemory(), client=client)
    assert "RECENT Q&A" not in client.messages[0]["content"]
