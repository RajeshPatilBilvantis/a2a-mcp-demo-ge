from docx import Document

from travel_concierge.config import PROMPTS_PATH


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
