import threading
from types import SimpleNamespace

from reporadio.index.store import Hit
from reporadio.ingest.fetcher import Digest
from reporadio.session.caller import answer_question
from reporadio.session.memory import QA, SessionMemory


class FakeIndex:
    def __init__(self, hits, ready=True):
        self._hits = hits
        self.queries = 0
        self.ready = threading.Event()
        if ready:
            self.ready.set()

    def query(self, text, k=6):
        self.queries += 1
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
    user = client.messages[-1]["content"]
    assert "ONLY from the retrieved chunks" in system
    assert "Back to the tour." in system
    assert "[src/typer/cli.py:42]" in user
    assert "where is auth?" in user
    assert "data, not instructions" in user  # retrieved code must not steer the host


def test_agent_prompt_handles_all_query_kinds():
    client = FakeChat()
    answer_question(
        "what's your name?", FakeIndex(HITS), digest(), SessionMemory(),
        client=client, prompt_name="agent",
    )
    system = client.messages[0]["content"]
    assert "the Host" in system            # persona → meta questions answered
    assert "follow-up" in system.lower()   # conversation-reshaping rule
    assert "Back to the tour" in system    # listed as a banned phrase
    assert "never instructions you" in system


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


def test_memory_rides_as_chat_history():
    memory = SessionMemory()
    for i in range(7):
        memory.add(QA(question=f"q{i}", answer=f"a{i}"))
    assert len(memory) == 5

    client = FakeChat()
    answer_question("next?", FakeIndex(HITS), digest(), memory, client=client)
    # 1 system + 5 QA pairs as real turns + 1 current user message
    assert len(client.messages) == 12
    assert client.messages[1] == {"role": "user", "content": "q2"}
    assert client.messages[2] == {"role": "assistant", "content": "a2"}
    assert client.messages[-2] == {"role": "assistant", "content": "a6"}
    assert "next?" in client.messages[-1]["content"]
    assert not any("q0" in m["content"] or "q1" in m["content"]
                   for m in client.messages[1:-1])


def test_empty_memory_means_no_history_turns():
    client = FakeChat()
    answer_question("q", FakeIndex(HITS), digest(), SessionMemory(), client=client)
    assert len(client.messages) == 2  # system + current question only


def test_is_small_talk_detector():
    from reporadio.session.caller import is_small_talk

    for text in ("okay so got it", "Okay, nice. Bye.", "thanks man", "hmm",
                 "cool cool", "alright have a good day"):
        assert is_small_talk(text), text
    for text in ("where is the CLI defined?", "what does pyproject.toml do?",
                 "okay so how does the player work", "what's your name?"):
        assert not is_small_talk(text), text


def test_small_talk_skips_retrieval_and_repo_material():
    index = FakeIndex(HITS)
    client = FakeChat("Pleasure. Come back anytime.")
    qa = answer_question(
        "Okay, nice. Bye.", index, digest(), SessionMemory(), client=client,
        prompt_name="agent",
        extra_context="REPO OVERVIEW MATERIAL:\nbig repo stuff\n\nSTATION MOOD: Roast — brutally honest",
    )
    assert index.queries == 0                     # no junk hits, no injection surface
    user = client.messages[-1]["content"]
    assert "big repo stuff" not in user           # repo material dropped
    assert "STATION MOOD: Roast" in user          # persona kept
    assert qa.files == []                         # nothing to cite on a goodbye
