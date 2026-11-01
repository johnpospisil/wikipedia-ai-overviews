# Quick-answer rubric (P12)

**Question:** when someone reaches this article from a search engine, can a typical query be fully answered in one or two sentences? That means one fact, a short definition, or a few values from the infobox. If so, an AI answer on the results page can replace the click.

**Label:** `1` = quick-answer, `0` = long-read. Each label also gets a confidence (`high` or `low`) and a short reason.

## How to decide

1. Think of the 2–3 most common search queries that would bring a reader to this article. Use the article's subject, not its length.
2. Ask: can most of those queries be answered by one fact or a short definition? Examples:
   - a date or year (born, released, founded, happened);
   - a number (age, height, population, length, molar mass, score);
   - a place (where is it, capital of);
   - a name (who directed, who won, who founded, CEO);
   - a one-sentence "what is X" for a well-bounded thing or term.
3. If yes, the label is **1**. It is **0** if the common queries need:
   - an explanation of how or why something works;
   - a narrative (what happened and why);
   - a comparison;
   - step-by-step instructions;
   - a long list;
   - or the reader wants to read or browse the article itself (open-ended or study queries).

## Typical cases

| Usually 1 (quick-answer) | Usually 0 (long-read) |
|---|---|
| People: age, born, died, spouse, nationality, "who is X" | Broad topics: "History of X", "Economy of X", ideologies, fields of study |
| Places: where, population, country, area, elevation | Historical events and wars: causes, course, consequences |
| Chemical elements and compounds: formula, properties, uses in brief | Diseases and medical topics: symptoms, causes, treatment (several facts and an explanation) |
| Species: what it is, where it lives, size | Lists and "List of …" pages |
| Films, TV series, albums, books, games: release date, cast, author, plot in a sentence | Abstract concepts that need explanation (e.g. "Quantum entanglement", "Postmodernism") |
| Sports seasons and tournaments: who won, final score | Processes and how-tos |
| Buildings, bridges, mountains, rivers: height, length, location, when built | Complex organisations or institutions whose typical query is "how does X work" |
| Units, constants, simple terms: one-line definition or value | |
| Companies, clubs, bands: founded, headquarters, members, owner | |

## Edge cases

- **Very famous subjects** (e.g. Albert Einstein, Paris): label by the *typical* query, not by how much there is to read. Most queries about a person are still "who is / how old / when did" → 1.
- **Disambiguation-like or mixed articles:** use the main subject.
- **Year or date articles** (e.g. "1987", "March 3"): readers browse them; the typical query is "what happened in 1987" → 0.
- **Concept or term articles:** use 1 if a one-sentence definition satisfies the typical query (e.g. "Kilogram", "Haiku"), 0 if the term needs real explanation.
- **Unsure:** pick the more likely label and mark the confidence `low`.

The label must be based on the subject (title, Wikidata label and description). It must not be based on the rule's output or on the article's features.
