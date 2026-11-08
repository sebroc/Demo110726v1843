#!/usr/bin/env python3
"""Generate a PreTeXt book from the three original lecture TeX files."""
import html
import re
import subprocess
import sys
import shutil
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = OUT / "source"
STRUCT = re.compile(r"\\(chaptertitle|sectiontitle|activity|theorem|definition|fact|note|remark|corollary|lemma)\b")


def braced(s, pos):
    assert s[pos] == "{"
    depth = 1
    i = pos + 1
    while depth and i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "{": depth += 1
        elif s[i] == "}": depth -= 1
        i += 1
    if depth: raise ValueError("Unclosed TeX group")
    return s[pos + 1:i - 1], i


def args(s, pos, count):
    result = []
    for _ in range(count):
        while pos < len(s) and s[pos].isspace(): pos += 1
        value, pos = braced(s, pos)
        result.append(value)
    return result, pos


def replace_one_arg(s, name, template):
    pattern = re.compile(r"\\" + name + r"\s*\{")
    pos = 0
    while m := pattern.search(s, pos):
        value, end = braced(s, m.end() - 1)
        new = template(value)
        s = s[:m.start()] + new + s[end:]
        pos = m.start() + len(new)
    return s


def prepare(s):
    s = re.sub(r"(?<!\\)%[^\n]*", "", s)
    # MathJax does not implement these TeX layout macros from the PDF notes.
    s = re.sub(r"\\noalign\s*\{\s*\\medskip\s*\}", "", s)
    s = s.replace(r"\dashline", r"\mid")
    for name in ("fillin", "underline", "shortanswer"):
        s = replace_one_arg(s, name, lambda x: r"\textbf{" + x + "}")
    s = re.sub(r"\\(?:bigskip|medskip|smallskip|newpage|noindent|centering)\b", "\n\n", s)
    s = re.sub(r"\\(?:vspace|hspace)\s*\{[^{}]*\}", " ", s)
    s = re.sub(r"\\begin\{framed\}|\\end\{framed\}", "\n\n", s)
    return s


def convert_fragment(tex, blank_terms=None):
    tex = prepare(tex).strip()
    if not tex: return ""
    output = subprocess.run(["pandoc", "-f", "latex", "-t", "html", "--mathjax"], input=tex, text=True, capture_output=True, check=True).stdout
    soup = BeautifulSoup(output, "html.parser")
    blank = r"\underline{\phantom{0000}}"
    def replace_blanks(value, math=False):
        if blank_terms is None:
            return value
        def replace(match):
            index = int(match[1])
            if math:
                blank_terms[index] = "$" + blank_terms[index] + "$"
            return blank if math else f"<m>{blank}</m>"
        return re.sub(r"PTXActivityBlank(\d+)End", replace, value)

    def node(n):
        if isinstance(n, NavigableString): return replace_blanks(html.escape(str(n), quote=False))
        if not isinstance(n, Tag): return ""
        if n.name == "span" and "math" in n.get("class", []):
            display = "display" in n.get("class", [])
            math = n.get_text()
            math = math[2:-2] if math.startswith((r"\(", r"\[")) else math
            return f"<{'me' if display else 'm'}>{replace_blanks(html.escape(math, quote=False), math=True)}</{'me' if display else 'm'}>"
        children = "".join(node(c) for c in n.children)
        names = {"p":"p", "strong":"b", "b":"b", "em":"em", "i":"em", "ul":"ul", "ol":"ol", "li":"li", "blockquote":"blockquote"}
        if n.name == "img":
            src = n.get("src", "")
            return f'<image source="{html.escape(src, quote=True)}"/>'
        if n.name == "a": return f'<url href="{html.escape(n.get("href", ""), quote=True)}">{children}</url>'
        if n.name in names: return f"<{names[n.name]}>{children}</{names[n.name]}>"
        if n.name == "br": return " "
        return children
    result = "".join(node(c) for c in soup.contents)
    # Pandoc often wraps a display equation in a paragraph; PreTeXt does not.
    result = re.sub(r"<p>\s*(<me>.*?</me>)\s*</p>", r"\1", result, flags=re.S)
    return result


def extract_answers(s):
    answers = []
    pattern = re.compile(r"\\answer\b")
    while m := pattern.search(s):
        pos = m.end()
        if pos < len(s) and s[pos] == "[":
            pos = s.find("]", pos) + 1
        while pos < len(s) and s[pos].isspace(): pos += 1
        if pos >= len(s) or s[pos] != "{": break
        answer, end = braced(s, pos)
        answers.append(answer)
        s = s[:m.start()] + s[end:]
    return s, answers


def content(parent, tex, activity=False):
    statement, answers = extract_answers(tex)
    if activity:
        terms = []
        pattern = re.compile(r"\\(?:fillin|underline|shortanswer)\s*\{")
        pos = 0
        while match := pattern.search(statement, pos):
            term, end = braced(statement, match.end() - 1)
            marker = f"PTXActivityBlank{len(terms)}End"
            terms.append(term)
            statement = statement[:match.start()] + marker + statement[end:]
            pos = match.start() + len(marker)
        rendered = convert_fragment(statement, blank_terms=terms)
        parent.append("<statement>" + (rendered or "<p></p>") + "</statement>")
        blanks = ""
        if terms:
            blanks = "<p><b>" + ("Missing term:" if len(terms) == 1 else "Missing terms, in order:") + "</b></p>"
            blanks += convert_fragment("\\begin{enumerate}\n" + "\n".join(r"\item " + term for term in terms) + "\n\\end{enumerate}")
        solution = "".join(convert_fragment(a) for a in answers)
        parent.append("<solution>" + (blanks + solution or "<p>Work through the activity.</p>") + "</solution>")
    else:
        parent.append(convert_fragment(statement))
        for a in answers: parent.append("<p><b>Answer:</b></p>" + convert_fragment(a))


def build():
    SOURCE.mkdir(parents=True, exist_ok=True)
    chapters = []
    preamble = (ROOT / "Notes/Chap1/Chap1-lectures.tex").read_text().split(r"\begin{document}", 1)[0]
    math_preamble = preamble[preamble.index(r"\newcommand{\bbR}"):preamble.index("%%%  TIKZ")]
    math_preamble = re.sub(r"(?<!\\)%[^\n]*", "", math_preamble)
    macro_lines = []
    pattern = re.compile(r"\\(?:newcommand|DeclareMathOperator)\s*\{\\([A-Za-z]+)\}(?:\[(\d+)\])?\s*\{")
    pos = 0
    while match := pattern.search(math_preamble, pos):
        definition, end = braced(math_preamble, match.end() - 1)
        name = match.group(1)
        if name not in {"coordsys", "ola", "peti", "rub", "points", "notice", "question", "proof", "setup", "idea", "warning", "topic", "activity", "theorem", "corollary", "lemma", "fact", "note", "definition", "remark", "sectiontitle", "chaptertitle"}:
            macro_lines.append(math_preamble[match.start():end])
        pos = end
    (SOURCE / "docinfo.ptx").write_text("<docinfo><macros>\n" + html.escape("\n".join(macro_lines)) + "\n</macros></docinfo>\n")
    for chapter in (1, 2, 3):
        path = ROOT / f"Notes/Chap{chapter}/Chap{chapter}-lectures.tex"
        body = path.read_text().split(r"\begin{document}", 1)[1].rsplit(r"\end{document}", 1)[0]
        # Keep interleaved equations and answer boxes together on the web.
        def worked_solution(match):
            steps = re.sub(r"(?<!\\)%[^\n]*", "", match[1])
            steps = re.sub(r"\\answer\s*\[[^\]]*\]", lambda _: r"\answer", steps)
            steps = replace_one_arg(steps, "answer", lambda matrix: "\n\n" + matrix + "\n\n")
            return "\\answer{\n" + steps + "\n}\n"

        body = re.sub(
            r"(?ms)^% pretext: begin worked solution[ \t]*\n(.*?)^% pretext: end worked solution[ \t]*$",
            worked_solution,
            body,
        )
        body = re.sub(r"(?<!\\)%[^\n]*", "", body)
        matches = list(STRUCT.finditer(body))
        lines = []
        opened = None
        count = 0
        title = ""
        for index, match in enumerate(matches):
            kind = match.group(1)
            start = match.end()
            if kind in ("chaptertitle", "sectiontitle"):
                values, start = args(body, start, 2)
                if kind == "chaptertitle":
                    title = values[1].strip()
                    lines.append(f'<chapter xml:id="ch-{chapter}"><title>{html.escape(title)}</title>')
                    opened = "introduction"
                    lines.append("<introduction>")
                else:
                    if opened: lines.append(f"</{opened}>")
                    number = values[0]
                    lines.append(f'<section xml:id="sec-{number.replace(".", "-")}"><title>{html.escape(values[1].strip())}</title>')
                    opened = "section"
                content(lines, body[start:matches[index+1].start() if index+1 < len(matches) else len(body)])
                continue
            if kind in ("activity", "theorem", "definition", "fact", "note", "remark", "corollary", "lemma"):
                count += 1
                end = matches[index+1].start() if index+1 < len(matches) else len(body)
                chunk = body[start:end]
                label = re.match(r"\s*\\label\{([^}]+)\}", chunk)
                if label: chunk = chunk[label.end():]
                tag = kind if kind in ("activity", "theorem", "definition", "remark", "corollary", "lemma") else "remark"
                if kind == "activity":
                    lines.append(f'<activity xml:id="{html.escape(label.group(1) if label else f"ch{chapter}-activity-{count}")}">')
                    content(lines, chunk, activity=True)
                else:
                    lines.append(f'<{tag} xml:id="ch{chapter}-item-{count}"><statement>')
                    content(lines, chunk)
                    lines.append("</statement>")
                lines.append(f"</{tag}>")
        if opened: lines.append(f"</{opened}>")
        lines.append("</chapter>")
        (SOURCE / f"chapter-{chapter}.ptx").write_text("\n".join(lines))
        chapters.append(f'<xi:include href="chapter-{chapter}.ptx"/>')
    (SOURCE / "main.ptx").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<pretext xml:lang="en-US" xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="docinfo.ptx"/><book xml:id="lecture-notes"><title>Math 345: Linear Algebra Lecture Notes</title><frontmatter><bibinfo><author><personname>Phillipson</personname></author><author><personname>Sebastien Roch</personname></author></bibinfo></frontmatter>\n' + "\n".join(chapters) + "\n</book></pretext>\n")
    assets = OUT / "assets" / "images"
    assets.mkdir(parents=True, exist_ok=True)
    for image in (ROOT / "Notes").glob("Chap*/*.png"):
        shutil.copy2(image, assets / image.name)
    for chapter in (1, 2, 3):
        file = SOURCE / f"chapter-{chapter}.ptx"
        xml = file.read_text()
        xml = re.sub(r'<image source="([^"]+)"/>', lambda m: f'<image source="images/{m.group(1) if m.group(1).endswith(".png") else m.group(1) + ".png"}"/>', xml)
        file.write_text(xml)


if __name__ == "__main__": build()
