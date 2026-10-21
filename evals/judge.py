"""Fresh-context judge for eval runs without a desktop session (cloud or batch).

Each call starts a new headless Claude Code session in an empty folder that holds only the
images, renamed image1.png, image2.png, ... It gets the art-director agent's instructions as
an appended system prompt and nothing else: no file names, no brief, no protocol, no MCP
servers, no project settings. "Unclear" counts as No.

    python evals/judge.py blind --image sheet.jpg --prompt-file prompt.txt --names "wolf|dog"
    python evals/judge.py checklist --image a.png --image b.png --question "..." --question "..."
    python evals/judge.py letter --image lineup.png --prompt-file prompt.txt

Prints one JSON object: the verdict, the judge's full answer and its token usage. With --log,
the same object is appended to a JSONL file (for `opus eval tokens`-style accounting).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "plugins" / "opus-tools" / "agents" / "art-director.md"
MODEL = "claude-opus-5-5"

BLIND = """Blind read mode. {prompt}

End your answer with exactly three lines:
GUESS1: <one or two words>
GUESS2: <one or two words>
GUESS3: <one or two words>"""

CHECKLIST = """Checklist mode. Look at {images}. Answer each yes/no question about what the images show.
For each question, reason briefly first, then answer Yes, No or Unclear. Judge only what you can see.

{questions}

End your answer with one line per question, exactly in this form:
{answer_lines}"""

LETTER = """{prompt}

End your answer with exactly one line:
ANSWER: <letter>"""


def _agent_prompt() -> str:
    text = AGENT.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


def _names(images: list[Path], work: Path) -> list[str]:
    out = []
    for i, src in enumerate(images, 1):
        dst = work / f"image{i}{src.suffix.lower()}"
        shutil.copyfile(src, dst)
        out.append(dst.name)
    return out


def _ask(prompt: str, work: Path, model: str, timeout: int) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model, "--append-system-prompt", _agent_prompt(),
           "--allowedTools", "Read", "--max-turns", "8", "--output-format", "json",
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--setting-sources", ""]
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"judge failed (exit {p.returncode}): {p.stderr[-800:] or p.stdout[-800:]}")
    return {"answer": data.get("result", ""), "usage": data.get("usage", {}), "cost_usd": data.get("total_cost_usd"),
            "is_error": data.get("is_error", False)}


def _tail(answer: str, key: str) -> str:
    hits = re.findall(rf"^\s*\**{key}\**\s*:\s*\**(.+?)\**\s*$", answer, flags=re.M | re.I)
    return hits[-1].strip() if hits else ""


def check_args(mode: str, questions: list[str], names: str = "") -> list[str]:
    """Refuse arguments the mode can't use, and return the accepted names (lowercase), split on
    '|' or ','. A checklist takes 1-5 questions: a re-check asks only the questions that failed."""
    if mode == "checklist" and not 1 <= len(questions) <= 5:
        raise SystemExit("checklist mode takes 1-5 questions")
    return [n.strip().lower() for n in re.split(r"[|,]", names or "") if n.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["blind", "checklist", "letter"])
    ap.add_argument("--image", action="append", required=True)
    ap.add_argument("--prompt-file", help="blind and letter modes: the prompt the tool returned")
    ap.add_argument("--question", action="append", default=[], help="checklist mode, 1-5 times")
    ap.add_argument("--names", default="", help="blind mode: accepted names, separated by '|' or ',' "
                                                "(never shown to the judge)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--log", help="append the result to this JSONL file")
    a = ap.parse_args(argv)
    accepted = check_args(a.mode, a.question, a.names)
    images = [Path(i).expanduser().resolve() for i in a.image]
    with tempfile.TemporaryDirectory(prefix="judge_") as tmp:
        work = Path(tmp)
        names = _names(images, work)
        if a.mode == "checklist":
            qs = "\n".join(f"Q{i}. {q}" for i, q in enumerate(a.question, 1))
            lines = "\n".join(f"Q{i}: Yes|No|Unclear" for i in range(1, len(a.question) + 1))
            prompt = CHECKLIST.format(images=", ".join(names), questions=qs, answer_lines=lines)
        else:
            text = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else ""
            # The tool's prompt names the sheet by its path; the judge only ever sees image1
            text = re.sub(r"Image:\s*\S+", "Image: " + names[0], text) if text else f"Look at {names[0]}."
            if names[0] not in text:
                text += f"\n\nImage: {names[0]}"
            prompt = (BLIND if a.mode == "blind" else LETTER).format(prompt=text)
        res = _ask(prompt, work, a.model, a.timeout)
    out = {"mode": a.mode, "model": a.model, **res}
    if a.mode == "blind":
        guesses = [_tail(res["answer"], f"GUESS{i}") for i in (1, 2, 3)]
        top1 = guesses[0].lower()
        out.update(guesses=guesses,
                   top1_names_subject=bool(accepted) and any(re.search(rf"\b{re.escape(n)}s?\b", top1) for n in accepted))
    elif a.mode == "checklist":
        ans = [_tail(res["answer"], f"Q{i}") for i in range(1, len(a.question) + 1)]
        ans = [x.split()[0].strip(".").capitalize() if x else "Unclear" for x in ans]
        out.update(questions=a.question, answers=ans, checklist_no=sum(x != "Yes" for x in ans))
    else:
        out["letter"] = _tail(res["answer"], "ANSWER").strip()[:1].upper()
    if a.log:
        with open(a.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(out) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
