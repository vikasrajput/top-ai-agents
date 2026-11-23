# Published directory contract

`directory.json` is the generated public edition, not a collector configuration.
No prompts, unpublished reviews, ranking scripts, or reusable rendering templates
are stored in this public repository.

## Schema version 1

The root contains `schema_version` (exactly `1`), `published_at` (ISO 8601 timestamp),
`period` (`start`, exclusive `end`, and descriptive `label`), `categories`,
`projects`, `top50`, and `rising`.

Categories are objects with string `id`, `name`, and `description`.
Project fields:

| Field | Type and meaning |
| --- | --- |
| `id` | Stable numeric GitHub repository ID encoded as a string |
| `slug`, `full_name`, `name`, `github_url`, `category_id`, `kind` | Strings; kind is agent, framework, platform, skill, or infrastructure |
| `stars`, `stars_added_period` | Nonnegative integer; unknown measurements are `null`, never zero |
| `metrics_as_of` | ISO 8601 metric snapshot timestamp, or `null` when unknown |
| `profile_kind` | `full` or `brief` |
| `intro`, `example`, `license` | Editorial strings |
| `utilities`, `requirements`, `limitations`, `cost_notes`, `source_urls` | Arrays of strings |
| `reviewed_at` | ISO 8601 editorial review timestamp, independent of metrics |
| `audience` | Optional compatible v1 extension: array of intended-audience strings |

All top-list IDs resolve to full profiles. Rising IDs resolve to projects outside
the top list, match their category, and have measured period additions. Each
category has an ordered array of zero to three rising IDs. IDs and slugs remain
stable; previously published profiles remain in `projects` when rankings change.
Old period additions are cleared to `null` unless measured for the new period.

Briefs have only a one- or two-sentence introduction and classification, links,
metrics, and dates. Required full-only fields are empty strings or arrays and are
not displayed. Nonempty examples explicitly say they are illustrative and not
tested. Source URLs link to primary documentation; full profiles include reviewed
licensing sources or an explicit licensing uncertainty.

## Static outputs

Canonical base: <https://vikasrajput.github.io/top-ai-agents/>.
Outputs are `index.html`, `categories/{id}/index.html`,
`projects/{slug}/index.html`, `methodology/index.html`,
`changelog/{YYYY-MM}.html`, `README.md`, `sitemap.xml`, `robots.txt`, and this
public JSON. Presentation lives in `assets/site.css` and `assets/directory.js`.
The minimal workflow deploys only allowlisted public outputs through GitHub Pages.

Generated HTML uses content-versioned CSS and JavaScript URLs so returning
browsers receive updated presentation and behavior. These asset versions do not
change permanent profile URLs or the published directory data.

Tables and project content are rendered into HTML. Search, utility/kind filtering,
and sorting progressively enhance those tables; JavaScript is not required to
discover or read entries. Unknown values sort last. Edition-specific scope and
nominal GitHub day-bucket boundaries are explained in the public methodology.

## Reviewed editorial proposals

The public `Review editorial proposals` Actions workflow is a validation and
approval gate, not a content generator. Discovery, prompts, source evidence,
rendering and proposal creation remain private.

Configure these **public repository Actions variables** before enabling merges:

| Variable | Value |
| --- | --- |
| `EDITORIAL_BOT_LOGIN` | Exact installed GitHub App bot login, including `[bot]` |
| `EDITORIAL_BOT_ID` | Numeric account ID returned by `GET /users/{bot-login}`; not the App ID or installation ID |

Use the bot identity of the public-repository-scoped App that creates proposals.
No App private key or private-repository token is needed by this workflow. With
either variable missing, the gate reports that merging is disabled. Invalid
configured values fail closed.

An eligible PR must be authored by that exact bot account, come from this same
repository, target `main`, have label `engine-editorial`, and use branch
`engine-editorial/YYYY-MM-DD-ID`, where `ID` is the project's stable repository
ID. It may modify **only `data/directory.json`** and exactly one project's
`limitations`, `source_urls` and `reviewed_at`. It must make a substantive
limitation/source change and advance the review timestamp. Date-only or
reordering-only changes, metric/ranking changes and changes to other projects
are rejected. Brief profiles keep empty limitations.

All sources must use HTTPS. Existing source URLs may remain; newly added URLs
must point to that project's canonical GitHub README, license or release.
Structural validation does not establish that a source supports a claim:
**the owner's review is the factual/editorial approval**.

The workflow runs trusted `main` code only, never proposal code. It validates
the merge-base-to-head payload and the current-main-to-test-merge result,
allowing unrelated weekly metadata refreshes but rejecting stale editorial
conflicts. The head-bound `Editorial proposal validation` check must succeed,
along with all other current-head checks and commit statuses. Only a genuine,
undismissed `APPROVED` review by `vikasrajput` on that exact head permits a squash
merge; an old-head approval, later changes request, draft or pending check does
not. Head, base and approval are rechecked immediately before the REST merge,
which also requires the expected head SHA.

Opening/updating/labelling a PR runs the gate. A 15-minute scheduled sweep
(subject to GitHub scheduling delays) notices later reviews and check results.
The workflow's **Run workflow** action can check a PR number immediately, or
scan all open proposals when the input is empty. Unapproved proposals remain
open without blocking independent metadata publishing. No PRs or reviews are
created by this gate.

A merge made with `GITHUB_TOKEN` does not trigger a new push workflow. The private
engine polls approved merged proposals on its next scheduled run, reconciles
only validated editorial fields and rerenders the public site. Its App-authored
publication then triggers Pages. Thus an approved JSON edit may precede the
visible profile update; this gate contains no public renderer or private dispatch
credential.
