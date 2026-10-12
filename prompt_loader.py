import os
from docx import Document

PROMPTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.docx")


def load_prompts(path=PROMPTS_PATH):
    """Read prompts.docx: each Heading 1 is a key, following paragraphs are its text."""
    prompts, key = {}, None
    for p in Document(path).paragraphs:
        if p.style.name == "Heading 1":
            key = p.text.strip()
            prompts[key] = []
        elif key and p.text.strip():
            prompts[key].append(p.text.strip())
    return {k: "\n".join(v) for k, v in prompts.items()}


def get_prompt(name, **fields):
    text = load_prompts()[name]
    return text.format(**fields) if fields else text
