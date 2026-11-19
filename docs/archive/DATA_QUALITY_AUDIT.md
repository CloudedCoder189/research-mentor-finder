> Latest follow-up: RESEARCH_RECOVERY_STATUS.md records active recovery of 51 descriptions, refresh of 61 mismatched vectors, source-reviewed topics, 569 backend tests and 22 browser scenarios. Remaining research gaps: 444; hash mismatches: 0. Current batch cost $0.00627430 of the approved $0.50 cap. Earlier entries below are historical; do not repeat paid jobs.

> Current follow-up: the 50 invalid UCLA titles are repaired in the working prototype and 51 reviewed records regenerated. The original database remains unchanged. The broader audit still has 61 provenance mismatches and 495 missing research-interest texts. Read UCLA_EXPANDED_REPAIR_STATUS.md.

# Researcher data audit — 2026-10-04

The local prototype works, but the dataset needs further repair before a public
release. Checking every row found 50 invalid UCLA titles, 61 embedding-provenance
inconsistencies and substantial missing source/research information. Twelve
official university pages were checked for a purposive sample; this is not an
estimated accuracy rate for all 2,063 records.

No researcher records, statuses, embeddings, database files or running-service
configuration were changed. No paid provider calls were made. The original DB
fingerprint and isolated researcher-content hash still match the saved baseline.

## Whole-dataset results

| Check | Result | Interpretation |
|---|---:|---|
| Researchers / institutions | 2,063 / 20 | Full structural scan, not full source verification. |
| Stored verification status | 1,366 Verified / 539 Review / 158 Failed | Historical audit labels; not a guarantee of every field's accuracy. |
| Numeric embeddings | 2,063 valid, finite, 1,536-dimensional vectors | Every row has a usable vector shape. |
| Embedding source-hash mismatch | 61: UCSB 33, UCSC 28 | Stored provenance differs from current academic text. No blank hashes. Does not prove every vector is numerically wrong. |
| Literal title `Expert Directory` | 50 UCLA rows | Confirmed title contamination; 46 are marked Verified and 4 Review. All 50 also store department Bioengineering, which needs source-by-source checking. |
| Missing title | 16 | Completeness gap; missing values must remain explicit. |
| Missing research-interest text | 496: 395 Review, 101 Failed | Nonempty summaries do not necessarily mean useful research evidence. |
| Missing profile URL / data-source URL | 118 / 118, all Failed | No usable individual source URL in these rows. |
| Moderate/Strong opportunity without source URL | 101 | Provenance gap, not proof of an advertised student opening. |
| Personal/lab website status | 2,063 Not checked | This is a separate check from stored academic-profile verification. |
| Normalized name + university duplicates | 0 groups | Case/whitespace check only; not proof that no identities are duplicated. |
| Shared profile URLs | 7 groups | Directory pages can legitimately be shared; do not delete these as duplicates automatically. |

No malformed non-placeholder URLs, invalid vectors or titles longer than the
180-character review threshold were found by the defined checks. Counts can
overlap; do not sum them into a number of distinct defective researchers.

## Prioritized findings

### D1 — High: UCLA title and department extraction reads navigation text

**Reproduce:** Open `http://localhost:13310/researchers/126` (Aditya Grover),
or GET `/api/researchers/126`. Read the title, department and verification badge.
Compare them with [his official UCLA page](https://samueli.ucla.edu/people/aditya-grover/).
The app serves `Expert Directory`, `Bioengineering`, and `Verified`; UCLA's
faculty block identifies a Computer Science appointment with rank Assistant
Professor. Similar title/department errors are confirmed for
[Yuchen Cui](https://samueli.ucla.edu/people/yuchen-cui/),
[Adnan Darwiche](https://samueli.ucla.edu/people/adnan-darwiche/), and
[Quanquan Gu](https://samueli.ucla.edu/people/quanquan-gu/).

**Expected:** Read the person's faculty block, preserve actual appointment
fields and let field filters use the correct department. Verification should
not imply the correctness of fields known to contain navigation text.

**Actual:** Fifty UCLA titles contain directory navigation. Department errors
are confirmed for the five UCLA pages sampled; all fifty stored Bioengineering
values are candidates for reinspection, not fifty proven department errors.

**Cause demonstrated:** `scrapers/ucla.py:_extract_title` tests substrings.
`director` matches the beginning of `directory`, so the pure function returns
`Expert Directory` even when the next input is `Assistant Professor`.
`_extract_department` takes the first department anywhere in its input lines;
navigation Bioengineering before the actual Computer Science block wins.
The precise historical HTML traversal was not replayed against saved HTML.

**Suggested fix:** Scope extraction to the named faculty content, ignore
navigation, match academic ranks with word boundaries and retain a fixture of
the actual page structure. Repair only reviewed fields through a proposed
old/new manifest. Add a verification rule rejecting navigation titles. Do not
turn all other records into Verified or apply guessed ranks to all fifty.

For [Kai-Wei Chang](https://samueli.ucla.edu/people/kai-wei-chang/), the department
is clearly Computer Science, but the page's heading and biography disagree
about rank. Resolve that conflict before choosing a replacement title.

### D2 — Medium: embedding provenance is inconsistent for 61 rows

**Reproduce:** Run the read-only audit and inspect the
`embedding_document_hash_mismatch` flags. Compare `embedding_source_hash` with
the app's exact pure `source_hash(record)` function. IDs 489, 490, 491, 493 and
494 are examples. The independent audit calculation was checked against those
exact application functions for all rows; the same 61 IDs mismatch.

**Expected:** Stored provenance identifies the current academic text used to
generate the vector, or outdated vectors are excluded until refreshed.

**Actual:** Nonempty vectors/hashes exist, but the hashes differ. Search uses
compatible vector dimensions without checking source-hash freshness in
`services/search.py:rank_professors`. Ranking impact was not measured. The
historical cause and the original embedding input text remain unknown.

**Suggested fix:** Trace write/normalization order and exclude demonstrably
outdated vectors from semantic scoring. Re-embed only confirmed stale inputs
under a separately bounded budget after text repairs. Do not just overwrite
hashes to make this check pass. Recheck both hash consistency and search output.

### D3 — Medium: missing research text sometimes misses evidence on the source

**Reproduce:** Open researcher 30 (David Bamman) and compare the stored absent
research interests with [the official Berkeley biography](https://www2.eecs.berkeley.edu/Faculty/Homepages/dbamman.html).
That biography describes work applying NLP and machine learning to humanities
and social-science questions, while the record summary says interests are
unavailable.

**Expected:** Extract supported research evidence from a biography when no
dedicated interests section exists, with its source attached.

**Actual:** 496 rows lack interests. The sampled Bamman record confirms one
recoverable extraction gap. [Ahmed Alaa's sampled directory page](https://www2.eecs.berkeley.edu/Faculty/Homepages/amalaa.html)
contains no comparable research description in the retrieved page: his absent
interests are not automatically a scraper defect. More sources may be needed.

**Suggested fix:** Support narrowly scoped biography extraction and preserve
unavailable values where evidence is absent. Do not fabricate interests from
department names or fill all 496 with generated text.

### D4 — Medium: verification and opportunity labels need narrower meaning

**Reproduce:** Inspect D1's Verified examples and the 101
`opportunity_without_source_url` flags. Researcher 1662 is one source-less
Moderate example. Inspect researcher 721 (Abbas Mazloumi), whose stored Failed
note cites an earlier 404; [the university page](https://cs.sdsu.edu/people/abbas-mazloumi/)
was retrievable through web browsing and supports the stored lecturer/research
fields. Retrieval can use cached/indexed content and is not a fresh HTTP audit.

**Expected:** Separate identity/source availability, field accuracy and explicit
opportunity evidence. Historical link failures should carry their audit date.

**Actual:** A Verified badge can coexist with obvious field errors. Historical
Failed status does not establish a link's present condition. Appointment/lab
signals can support Moderate without demonstrating an open student position.

**Suggested fix:** Treat labels as dated checks, require field-level evidence
for repaired records and distinguish appointment signals from advertised
opportunities. Review source-less opportunity classifications. Recheck historical
link failures without discarding still useful researchers automatically.

### D5 — Medium: taxonomy can misdescribe research outside computing

**Reproduce:** Open researcher 1126 (Umesh Mishra). The app shows Systems and
Other Computing Research while [his official research description](https://www.ece.ucsb.edu/people/faculty/umesh-mishra)
centers on wide-bandgap devices and electronics. His current cleaned appointment
title is consistent with the source; do not repeat the earlier title repair.

**Expected:** Topic labels represent the actual ECE research field; a computing
fallback should not become a claimed published research area.

**Actual:** Stored topics force a broad computing interpretation. The source
supports the research text, not those exact taxonomy labels. The rest of the
taxonomy was not exhaustively fact-checked.

**Suggested fix:** Review discipline-specific taxonomies and fallback wording;
add electronics/semiconductor coverage before recategorizing affected records.
Avoid relabeling them with tags the app does not yet understand.

## Other source checks

The appointment/topic descriptions sampled for
[Chelsea Finn](https://www.cs.stanford.edu/people/chelsea-finn) and
[Pieter Abbeel](https://www2.eecs.berkeley.edu/Faculty/Homepages/abbeel.html) were
consistent with the stored broad descriptions. [Emma Brunskill's page](https://profiles.stanford.edu/emma-brunskill)
supports her stored associate-professor appointment; her Review label contains
separate link/contact observations, which this audit did not resolve. These
checks do not certify every field or position availability.

## Reviewable repair proposal and evidence

**2026-10-05 follow-up:** The extraction fix and ten-field application to a
separate staging database are documented in UCLA_REPAIR_STATUS.md. Original and
active acceptance databases remain unchanged. The following text records the
2026-10-04 audit baseline, before those staged changes.

`evidence/data-audit-2026-10-04/proposed-field-repairs.csv` contains ten
source-supported field proposals: four UCLA titles, five UCLA departments,
and Bamman's research-interest text. **None were applied.** Kai-Wei Chang's
rank is deliberately unresolved. Changes would require refreshed verification
and enrichment/provenance for affected academic text; these side effects must
be tracked explicitly. Fifty invalid titles remain in the underlying data.

The full audit, all flagged IDs and public source sample are in
`structural-audit.json`; exact parser/API reproductions and baseline preservation
are in `validation.json`; source comparisons are in `source-checks.json`.
The audit script uses a read-only SQLite connection and public-column allowlist,
with no app imports, session/profile reads, provider calls or repair functions.

Next sequence: fix extraction against fixtures, expand source review for the
remaining UCLA rows, apply a reviewed manifest to a backed-up isolated copy,
then verify/re-enrich only affected records under an agreed budget. Public
release stays pending data-quality and deployment gates. Real student feedback
remains unavailable and is not substituted by this audit.
