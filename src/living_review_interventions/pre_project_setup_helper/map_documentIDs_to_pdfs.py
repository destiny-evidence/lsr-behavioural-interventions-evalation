"""Map each documentID of the unique-studies CSV to a PDF file.

Usage: map_documentIDs_to_pdfs.py STUDIES_CSV PDF_DIR OUT_DIR

Stage 1: fuzzy first-author / author-set / year match of study metadata against PDF
         filenames. Unambiguous 1:1 matches are accepted, the rest is ambiguous.
Stage 2: among ambiguous candidates, PDFs with matching filename authors whose
         abstracts (first three pages) are near-identical are duplicates; one is kept.
Stage 3: the study title is looked for (with slop) in the first three pages of the
         remaining candidate PDFs. Anything still unclear is flagged `review`.

Files are only read, never deleted or moved. The STUDIES_CSV is rewritten with the
columns pdf_path, pdf_match_status, pdf_match_note and pdf_title_score; a copy of the
original is kept in OUT_DIR. Diagnostics and cached first-three-page texts go to
OUT_DIR.
"""

import csv
import difflib
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium

FIRST_MIN = 0.85  # first-author / author-token similarity
OVERLAP_MIN = 0.5  # share of study authors found in the filename
MARGIN = 0.3  # score gap needed for a filename match to count as unambiguous
YEAR_EXACT, YEAR_OTHER, YEAR_CONFLICT = 0.5, 0.3, -0.5
DUP_SIM = 0.85  # abstract similarity above which two PDFs are duplicates
TITLE_MIN = 0.75  # title found in the PDF text
TITLE_GAP = 0.15  # advantage over the runner-up
TITLE_ONLY_MIN = 0.8  # for matches that have no filename support at all
TITLE_WARN = 0.6  # warn about filename matches whose title is not found
TITLE_WRONG = 0.3  # filename match whose PDF is clearly another paper
TITLE_DUP = 0.9  # both PDFs carry the title of the same study: same paper
MIN_WORDS = 120  # distinct words needed to call the first pages "text"
PAGES = 3
STOP = {"et", "al", "and"}
NEW_COLUMNS = ["pdf_path", "pdf_match_status", "pdf_match_note", "pdf_title_score"]


def fold(s):
    """Lowercase ASCII letters and spaces only (drops digits, punctuation, mojibake)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[-_]", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s)).strip()


def norm(text):
    """Lowercase alphanumerics, de-hyphenated line breaks, single spaces."""
    text = re.sub(r"-\s*\n\s*", "", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def study_keys(authorship):
    """Surname keys (last word of each author's surname) of an authorship string."""
    s = re.sub(r"\s+", " ", authorship)
    if ";" in s:
        parts = [p.split(",")[0] for p in s.split(";")]
    else:
        parts = re.split(r",|&|\band\b|\bet al\b", s)
    keys = []
    for part in parts:
        words = [w for w in fold(part).split() if w not in STOP]
        if words and len(words[-1]) >= 2:
            keys.append(words[-1])
    return keys


def parse_pdf(path):
    stem = path.stem
    years = re.findall(r"(?<!\d)(?:19|20)\d\d(?!\d)", stem)
    first_segment = re.split(r",|;|&|\band\b|\bet al\b|\(", stem, maxsplit=1)[0]
    return {
        "path": path,
        "stem": stem,
        "year": years[-1] if years else None,
        "first": [w for w in fold(first_segment).split() if w not in STOP],
        "tokens": {w for w in fold(stem).split() if len(w) >= 2 and w not in STOP},
    }


def hits(keys, tokens):
    return sum(any(ratio(k, t) >= FIRST_MIN for t in tokens) for k in keys)


def author_overlap(keys, tokens):
    keys = keys[:8]
    if not keys or not tokens:
        return 0.0
    return hits(keys, tokens) / min(len(keys), len(tokens))


def year_score(pdf_year, years):
    if pdf_year is None:
        return 0.0
    if pdf_year == years[0]:
        return YEAR_EXACT
    return YEAR_OTHER if pdf_year in years else YEAR_CONFLICT


def extract_text(path):
    """Text of the first PAGES pages and the page count (pdfium, then pdftotext)."""
    try:
        pdf = pdfium.PdfDocument(str(path))
        n_pages = len(pdf)
        chunks = []
        for i in range(min(PAGES, n_pages)):
            page = pdf[i]
            chunks.append(page.get_textpage().get_text_range())
            page.close()
        pdf.close()
        return "\n".join(chunks), n_pages
    except Exception:
        exe = shutil.which("pdftotext")
        if exe is None:
            return "", 0
        out = subprocess.run(
            [exe, "-f", "1", "-l", str(PAGES), str(path), "-"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        return out.stdout, 0


def title_score(title, text):
    """Share of the title found in the text, allowing for slop (0..1)."""
    t = norm(title)
    if not t or not text:
        return 0.0
    sm = difflib.SequenceMatcher(None, text, t, autojunk=False)
    m = sm.find_longest_match(0, len(text), 0, len(t))
    if m.size < 12:
        return m.size / len(t)
    start = max(0, m.a - m.b - 20)
    window = text[start : m.a - m.b + len(t) + 20]
    blocks = difflib.SequenceMatcher(None, window, t, autojunk=False)
    return sum(b.size for b in blocks.get_matching_blocks()) / len(t)


def abstract_block(text):
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"(?<![=/\w])abstract\b", flat, re.I)
    start = m.end() if m else 200
    return norm(flat[start : start + 1500])


def rel(path):
    return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()


def gap(ranked):
    return ranked[0][0] - ranked[1][0] if len(ranked) > 1 else float("inf")


def main():
    studies_path, pdf_dir, out_dir = (Path(a) for a in sys.argv[1:4])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "first3pages").mkdir(exist_ok=True)

    with studies_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        in_fields = list(reader.fieldnames or [])
        studies = list(reader)
    if "pdf_path" not in in_fields:
        shutil.copy(studies_path, out_dir / "unique_studies_before_pdf_mapping.csv")
    base_fields = [c for c in in_fields if c not in NEW_COLUMNS]

    pdfs = [parse_pdf(p) for p in sorted(pdf_dir.glob("*.pdf"))]
    texts, n_pages = [], []
    for i, p in enumerate(pdfs):
        text, n = extract_text(p["path"])
        texts.append(text)
        n_pages.append(n)
        safe = re.sub(r"[^\w.-]+", "_", p["stem"])
        (out_dir / "first3pages" / f"{i:03d}_{safe}.txt").write_text(
            text, encoding="utf-8"
        )
    norm_text = [norm(t)[:8000] for t in texts]
    # repeated download banners on scanned PDFs must not count as text
    has_text = [len(set(norm(t).split())) >= MIN_WORDS for t in texts]

    sids = [s["document_id"] for s in studies]
    info = {}
    for s in studies:
        years = [s["publication_year"]] + [y for y in s["other_years"].split(";") if y]
        titles = [s["name"]] + [t for t in s["other_titles"].split(" | ") if t]
        info[s["document_id"]] = {
            "keys": study_keys(s["authorship"]),
            "years": years,
            "titles": titles,
            "row": s,
        }

    def tscore(sid, pi):
        return max(title_score(t, norm_text[pi]) for t in info[sid]["titles"])

    # ---- Stage 1: metadata vs filename -------------------------------------
    edges = {}  # (sid, pi) -> (score, relaxed)
    for sid in sids:
        keys, years = info[sid]["keys"], info[sid]["years"]
        if not keys:
            continue
        for pi, p in enumerate(pdfs):
            first = max((ratio(keys[0], t) for t in p["first"]), default=0.0)
            ov = author_overlap(keys, p["tokens"])
            if first >= FIRST_MIN and ov >= OVERLAP_MIN:
                score = first + ov + year_score(p["year"], years)
                edges[(sid, pi)] = (score, False)
    for sid in sids:  # authors listed in a different order: weak, never "unique"
        if any(e[0] == sid for e in edges):
            continue
        keys, years = info[sid]["keys"], info[sid]["years"]
        for pi, p in enumerate(pdfs):
            ov = author_overlap(keys, p["tokens"])
            if hits(keys[:8], p["tokens"]) >= min(2, len(keys)) and ov >= 0.6:
                edges[(sid, pi)] = (ov + year_score(p["year"], years), True)

    by_study, by_pdf = defaultdict(list), defaultdict(list)
    for (sid, pi), (score, _) in edges.items():
        by_study[sid].append((score, pi))
        by_pdf[pi].append((score, sid))
    for lst in [*by_study.values(), *by_pdf.values()]:
        lst.sort(key=lambda x: (-x[0], str(x[1])))

    res = {sid: {"pi": None, "status": "none", "note": ""} for sid in sids}
    claimed = {}
    for sid in sids:
        if not by_study[sid]:
            continue
        score, pi = by_study[sid][0]
        res[sid]["status"] = "ambiguous"
        if (
            not edges[(sid, pi)][1]
            and by_pdf[pi][0][1] == sid
            and gap(by_study[sid]) >= MARGIN
            and gap(by_pdf[pi]) >= MARGIN
        ):
            res[sid].update(pi=pi, status="unique")
            claimed[pi] = sid
            pdf_year = pdfs[pi]["year"]
            if pdf_year is not None and pdf_year not in info[sid]["years"]:
                res[sid]["note"] = (
                    f"filename year {pdf_year} differs from {info[sid]['years'][0]}"
                )

    ambiguous = [sid for sid in sids if res[sid]["status"] == "ambiguous"]
    with (out_dir / "ambiguous_stage1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.writer(f)
        w.writerow(["document_id", "name", "authorship", "year", "candidate_pdfs"])
        for sid in ambiguous:
            r = info[sid]["row"]
            cands = "; ".join(
                f"{pdfs[pi]['path'].name} ({score:.2f}"
                f"{', claimed by ' + str(claimed[pi]) if pi in claimed else ''}"
                f"{', author order only' if edges[(sid, pi)][1] else ''})"
                for score, pi in by_study[sid]
            )
            w.writerow([sid, r["name"], r["authorship"], r["publication_year"], cands])

    cands2 = {
        sid: [pi for _, pi in by_study[sid] if pi not in claimed] for sid in ambiguous
    }
    for sid in ambiguous:
        if not cands2[sid]:
            res[sid]["status"] = "none"
            taken = ", ".join(
                f"{pdfs[pi]['stem']} -> {claimed[pi]}" for _, pi in by_study[sid]
            )
            res[sid]["note"] = f"only candidate PDF(s) already matched: {taken}"
    pending = [sid for sid in ambiguous if cands2[sid]]

    # ---- Stage 2: duplicate PDFs --------------------------------------------
    pairs = defaultdict(set)
    for sid in pending:
        for a in cands2[sid]:
            for b in cands2[sid]:
                if a < b:
                    pairs[(a, b)].add(sid)
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def similar_names(a, b):
        pa, pb = pdfs[a], pdfs[b]
        if not any(ratio(x, y) >= FIRST_MIN for x in pa["first"] for y in pb["first"]):
            return False
        shared = hits(sorted(pa["tokens"]), pb["tokens"])
        return shared / min(len(pa["tokens"]), len(pb["tokens"])) >= OVERLAP_MIN

    def abstract_similarity(a, b):
        abs_a, abs_b = abstract_block(texts[a]), abstract_block(texts[b])
        return difflib.SequenceMatcher(None, abs_a, abs_b, autojunk=False).ratio()

    dup_rows = []  # (pdf_a, pdf_b, abstract similarity, title basis, duplicate basis)
    for (a, b), pair_sids in sorted(pairs.items()):
        if not (similar_names(a, b) and has_text[a] and has_text[b]):
            continue
        sim = abstract_similarity(a, b)
        both_titled = any(
            min(tscore(s, a), tscore(s, b)) >= TITLE_DUP for s in pair_sids
        )
        basis = "abstract" if sim >= DUP_SIM else "title" if both_titled else ""
        dup_rows.append((pdfs[a]["path"].name, pdfs[b]["path"].name, sim, basis))
        if basis:
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)

    def year_hit(i):
        return any(
            pdfs[i]["year"] == info[sid]["years"][0]
            for sid in pending
            if i in cands2[sid]
        )

    rep = {}
    ignored = defaultdict(list)
    for members in groups.values():
        keep = min(
            members,
            key=lambda i: (
                not year_hit(i),
                -len(pdfs[i]["stem"]),
                -n_pages[i],
                pdfs[i]["path"].name,
            ),
        )
        for m in members:
            rep[m] = keep
            if m != keep:
                ignored[keep].append(m)

    reps = {sid: sorted({rep.get(pi, pi) for pi in cands2[sid]}) for sid in pending}
    rep_studies = defaultdict(set)
    for sid in pending:
        for pi in reps[sid]:
            rep_studies[pi].add(sid)
    for sid in list(pending):
        if len(reps[sid]) == 1 and len(rep_studies[reps[sid][0]]) == 1:
            if len(cands2[sid]) > 1:
                pi = reps[sid][0]
                dups = "; ".join(pdfs[d]["path"].name for d in ignored[pi])
                res[sid].update(pi=pi, status="resolved_by_duplicate")
                res[sid]["note"] = f"duplicate PDF(s) ignored: {dups}"
                pending.remove(sid)

    # ---- Stage 3: study title vs PDF text -----------------------------------
    scores = {}
    for sid in pending:
        for pi in reps[sid]:
            scores[(sid, pi)] = tscore(sid, pi) if has_text[pi] else None
    review_pdfs = {}  # documentID -> candidate PDF indices that need a human look
    for sid in pending:
        ranked = sorted(
            ((scores[(sid, pi)] or 0.0, pi) for pi in reps[sid]), reverse=True
        )
        best, pi = ranked[0]
        rivals = sorted(
            (((scores[(o, pi)] or 0.0), o) for o in rep_studies[pi]), reverse=True
        )
        if (
            best >= TITLE_MIN
            and gap(ranked) >= TITLE_GAP
            and rivals[0][1] == sid
            and gap(rivals) >= TITLE_GAP
        ):
            res[sid].update(pi=pi, status="resolved_by_title")
            dups = "; ".join(pdfs[d]["path"].name for d in ignored[pi])
            res[sid]["note"] = f"title match {best:.2f}" + (
                f"; duplicate PDF(s) ignored: {dups}" if dups else ""
            )
        else:
            res[sid]["status"] = "review"
            res[sid]["note"] = "; ".join(
                f"{pdfs[p]['path'].name} (title {s if s is None else round(s, 2)})"
                for p, s in sorted((p, scores[(sid, p)]) for p in reps[sid])
            )
            review_pdfs[sid] = reps[sid]

    # a study whose only candidates went to other studies simply has no PDF
    taken = {r["pi"]: sid for sid, r in res.items() if r["pi"] is not None}
    for sid in list(review_pdfs):
        if all(pi in taken for pi in review_pdfs[sid]):
            owners = ", ".join(
                f"{pdfs[pi]['path'].name} -> documentID {taken[pi]}"
                for pi in review_pdfs.pop(sid)
            )
            res[sid].update(
                status="none", note=f"candidate PDF matched elsewhere: {owners}"
            )

    # ---- Stage 3b: studies without any filename match vs unclaimed PDFs ------
    used = {r["pi"] for r in res.values() if r["pi"] is not None}
    used |= {d for ds in ignored.values() for d in ds}
    free = [pi for pi in range(len(pdfs)) if pi not in used and has_text[pi]]
    none_ids = [sid for sid in sids if res[sid]["status"] == "none"]
    tmat = {(sid, pi): tscore(sid, pi) for sid in none_ids for pi in free}
    for sid in none_ids:
        ranked = sorted(((tmat[(sid, pi)], pi) for pi in free), reverse=True)
        if not ranked or ranked[0][0] < TITLE_ONLY_MIN or gap(ranked) < TITLE_GAP:
            continue
        pi = ranked[0][1]
        rivals = sorted(((tmat[(o, pi)], o) for o in none_ids), reverse=True)
        if rivals[0][1] == sid and gap(rivals) >= TITLE_GAP:
            res[sid].update(pi=pi, status="resolved_by_title")
            res[sid]["note"] = f"no filename match; title match {ranked[0][0]:.2f}"

    # ---- Stage 2b: leftover PDFs that are another version of an assigned PDF --
    assigned = {r["pi"]: sid for sid, r in res.items() if r["pi"] is not None}
    ignored_all = {d for ds in ignored.values() for d in ds}
    for li, lp in enumerate(pdfs):
        if li in assigned or li in ignored_all or not has_text[li]:
            continue
        for ai, sid in assigned.items():
            if not (similar_names(li, ai) and has_text[ai]):
                continue
            sim = abstract_similarity(li, ai)
            same_title = tscore(sid, li) >= TITLE_DUP and tscore(sid, ai) >= TITLE_DUP
            basis = "abstract" if sim >= DUP_SIM else "title" if same_title else ""
            dup_rows.append((lp["path"].name, pdfs[ai]["path"].name, sim, basis))
            if basis:
                ignored[ai].append(li)
                ignored_all.add(li)
                extra = f"duplicate PDF ignored: {lp['path'].name}"
                res[sid]["note"] = "; ".join(x for x in [res[sid]["note"], extra] if x)
                break

    # ---- Title check for every assigned PDF -----------------------------------
    for sid in sids:
        pi = res[sid]["pi"]
        res[sid]["tscore"] = ""
        if pi is None:
            continue
        s = tscore(sid, pi) if has_text[pi] else None
        if s is None:
            extra = "no usable text layer in PDF, title not checked"
        else:
            res[sid]["tscore"] = f"{s:.2f}"
            if s < TITLE_WRONG and res[sid]["status"] == "unique":
                res[sid].update(pi=None, status="review")
                review_pdfs[sid] = [pi]
                extra = (
                    f"filename match {pdfs[pi]['path'].name} is probably a different"
                    f" paper (title score {s:.2f})"
                )
            elif s < TITLE_WARN and res[sid]["status"] == "unique":
                extra = f"title not found in first {PAGES} pages"
            else:
                continue
        res[sid]["note"] = "; ".join(x for x in [res[sid]["note"], extra] if x)

    # ---- Outputs ---------------------------------------------------------------
    with studies_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[*base_fields, *NEW_COLUMNS])
        w.writeheader()
        for s in studies:
            r = res[s["document_id"]]
            w.writerow(
                {
                    **{c: s[c] for c in base_fields},
                    "pdf_path": "" if r["pi"] is None else rel(pdfs[r["pi"]]["path"]),
                    "pdf_match_status": r["status"],
                    "pdf_match_note": r["note"],
                    "pdf_title_score": r["tscore"],
                }
            )

    with (out_dir / "needs_review.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["document_id", "name", "authorship", "year", "candidates", "snippets"]
        )
        for sid, cand in sorted(review_pdfs.items(), key=lambda kv: int(kv[0])):
            r = info[sid]["row"]
            snippets = " || ".join(
                f"{pdfs[pi]['path'].name}: {re.sub(r'\s+', ' ', texts[pi][:300])}"
                for pi in cand
            )
            row = [sid, r["name"], r["authorship"], r["publication_year"]]
            w.writerow([*row, res[sid]["note"], snippets])

    with (out_dir / "duplicates.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pdf_a", "pdf_b", "abstract_similarity", "duplicate_basis"])
        for a, b, sim, basis in dup_rows:
            w.writerow([a, b, f"{sim:.3f}", basis or "not a duplicate"])

    used = {r["pi"] for r in res.values() if r["pi"] is not None}
    dup_ignored = {d for ds in ignored.values() for d in ds}
    review_for = defaultdict(list)
    for sid, cand in review_pdfs.items():
        for pi in cand:
            review_for[pi].append(sid)
    with (out_dir / "unmatched_pdfs.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pdf", "reason"])
        for pi, p in enumerate(pdfs):
            if pi in used:
                continue
            if pi in dup_ignored:
                reason = "duplicate of an assigned PDF (ignored)"
            elif pi in review_for:
                reason = f"candidate for documentID {','.join(review_for[pi])}"
            else:
                reason = "no matching study"
            w.writerow([p["path"].name, reason])

    counts = defaultdict(int)
    for r in res.values():
        counts[r["status"]] += 1
    print(f"{len(sids)} studies, {len(pdfs)} PDFs; status counts: {dict(counts)}")
    no_text = [p["path"].name for p, ok in zip(pdfs, has_text, strict=True) if not ok]
    print(f"PDFs without usable text layer: {no_text}")
    n_assigned = sum(r["pi"] is not None for r in res.values())
    print(f"PDFs assigned to more than one documentID: {len(used) != n_assigned}")


if __name__ == "__main__":
    main()
