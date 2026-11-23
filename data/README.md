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
