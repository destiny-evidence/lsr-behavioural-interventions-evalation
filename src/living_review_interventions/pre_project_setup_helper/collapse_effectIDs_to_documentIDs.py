import csv
import difflib
import re
import sys
import unicodedata
from collections import Counter, OrderedDict

SRC, DST, LINK = sys.argv[1], sys.argv[2], sys.argv[3]
THRESHOLD = 0.88


def norm_title(t):
    t = re.sub(r"[\r\n]+", " ", t)
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r"[^a-zA-Z0-9 ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def first_surname(a):
    a = re.sub(r"[\r\n]+", " ", a).strip()
    return re.sub(r"[^a-z]", "", a.split(";")[0].split(",")[0].lower())


rows = list(csv.DictReader(open(SRC, encoding="utf-8", newline="")))
recs = [
    dict(
        name=re.sub(r"\s+", " ", r["name"].replace("\r", " ").replace("\n", " ")).strip(),
        authorship=re.sub(r"\s+", " ", r["authorship"].replace("\r", " ").replace("\n", " ")).strip(),
        year=r["publication_year"].strip(),
        source_id=r["document_id"],
        effect_id=r["effectID"],
        dtype=r["documentType"].strip(),
        nt=norm_title(r["name"]),
    )
    for r in rows
]

# Union-find over records whose normalised titles are similar
parent = list(range(len(recs)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


pairs = []
uniq_titles = sorted(set(r["nt"] for r in recs))
title_pairs = []
for i, a in enumerate(uniq_titles):
    for b in uniq_titles[i + 1 :]:
        if abs(len(a) - len(b)) > 0.2 * max(len(a), len(b)):
            continue
        s = difflib.SequenceMatcher(None, a, b).ratio()
        if s >= THRESHOLD:
            title_pairs.append((a, b, s))

title_to_idx = {}
for idx, r in enumerate(recs):
    title_to_idx.setdefault(r["nt"], []).append(idx)

for a, b, s in title_pairs:
    ia, ib = title_to_idx[a][0], title_to_idx[b][0]
    parent[find(ia)] = find(ib)
for nt, idxs in title_to_idx.items():
    for j in idxs[1:]:
        parent[find(j)] = find(idxs[0])

clusters = OrderedDict()
for idx in range(len(recs)):
    clusters.setdefault(find(idx), []).append(idx)

out_rows = []
out_members = []
for members in clusters.values():
    group = [recs[i] for i in members]
    name = max(Counter(g["name"] for g in group).items(), key=lambda kv: (kv[1], len(kv[0])))[0]
    authorship = Counter(g["authorship"] for g in group).most_common(1)[0][0]
    year = Counter(g["year"] for g in group).most_common(1)[0][0]
    out_members.append(members)
    out_rows.append(
        dict(
            name=name,
            authorship=authorship,
            publication_year=year,
            n_records=len(group),
            other_years=";".join(sorted({g["year"] for g in group} - {year})),
            other_titles=" | ".join(sorted({g["name"] for g in group} - {name})),
            other_authorship=" | ".join(sorted({g["authorship"] for g in group} - {authorship})),
        )
    )

order = sorted(
    range(len(out_rows)),
    key=lambda i: (out_rows[i]["publication_year"], first_surname(out_rows[i]["authorship"]), out_rows[i]["name"].lower()),
)
links = []
for n, i in enumerate(order, start=1):
    out_rows[i]["document_id"] = n
    links += [
        dict(document_id=n, effectID=recs[m]["effect_id"], effect_originalRow=recs[m]["source_id"])
        for m in out_members[i]
    ]
out_rows = [out_rows[i] for i in order]

fields = ["document_id", "name", "authorship", "publication_year", "n_records", "other_years", "other_titles", "other_authorship"]
with open(DST, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out_rows)

with open(LINK, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["document_id", "effectID", "effect_originalRow"])
    w.writeheader()
    w.writerows(sorted(links, key=lambda r: (r["document_id"], int(r["effect_originalRow"]))))

print("records", len(recs), "unique studies", len(out_rows))
print("merged title pairs (similarity >= %.2f):" % THRESHOLD)
for a, b, s in title_pairs:
    print("  %.3f  %s  <->  %s" % (s, a[:70], b[:70]))

