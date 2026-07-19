"""Caller flow: question → retrieve top chunks → grounded spoken answer."""

from __future__ import annotations

from reporadio.session.memory import QA, SessionMemory
from reporadio.show.script import MODEL, load_prompt

STILL_INDEXING = (
    "Hold that thought, caller — I'm still filing this repo into the archive. "
    "Give me a few seconds and ask again. Back to the tour."
)


def _not_found(question: str, digest) -> str:
    return (
        "Honest answer, caller — that's not in the pages I have on my desk for "
        f"{digest.name}. My best guess is it lives somewhere deeper in the tree "
        "than this digest goes. Back to the tour."
    )


def answer_question(
    question: str,
    index,
    digest,
    memory: SessionMemory,
    *,
    client=None,
    model: str = MODEL,
    k: int = 6,
    wait_index_s: float = 30.0,
    lang: str = "en",
) -> QA:
    """Grounded answer from the index; honest fallbacks when we can't answer."""
    if not index.ready.wait(timeout=wait_index_s):
        return QA(question, STILL_INDEXING)

    hits = index.query(question, k=k)
    if not hits:
        qa = QA(question, _not_found(question, digest))
        memory.add(qa)
        return qa

    if client is None:
        from groq import Groq

        from reporadio.config import require_groq_key

        client = Groq(api_key=require_groq_key())

    from reporadio.show.modes import language_block

    context = "\n\n".join(f"[{h.path}:{h.start_line}]\n{h.text}" for h in hits)
    system = load_prompt("answer") + language_block(lang)
    if len(memory):
        system += "\n\n" + memory.render()

    resp = client.chat.completions.create(
        model=model,
        temperature=0.4,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"REPO: {digest.name}\n\nRETRIEVED CHUNKS:\n{context}\n\n"
                    f"CALLER QUESTION: {question}"
                ),
            },
        ],
    )
    answer = (resp.choices[0].message.content or "").strip()
    qa = QA(question, answer, files=sorted({h.path for h in hits}))
    memory.add(qa)
    return qa
