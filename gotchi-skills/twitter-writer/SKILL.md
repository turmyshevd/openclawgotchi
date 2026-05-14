---
name: twitter-writer
description: Write X/Twitter posts, tweet drafts, shitposts, and short threads for engineering or startup topics. Use this when the user asks for a tweet, X post, shitpost, post draft, or wants social copy for Twitter/X. Always return 3 distinct variants, each inside its own code block, unless the user explicitly asks for one.
metadata:
  {
    "openclaw": {
      "emoji": "🐦",
      "always": true
    }
  }
---

# Twitter Writer Skill

Use this skill when the user wants help writing for X/Twitter.

## Default Output

Unless the user says otherwise:

1. Return exactly 3 variants.
2. Put each variant in its own fenced code block.
3. Do not add long commentary before or after the drafts.
4. Keep each variant tweet-ready.

Preferred format:

```text
Variant 1
```

```text
Variant 2
```

```text
Variant 3
```

## Tone Rules

- Sound like a real technical person, not brand copy.
- Be concise, sharp, and specific.
- Zero corporate speak.
- Avoid obvious AI wording, filler, and over-explaining.
- Avoid em dashes if a plain sentence works.
- Use emojis sparingly. Usually zero is better. In shitposting mode, 0-2 is fine.
- Prefer one idea per tweet.

## Writing Priorities

1. Start with a hook or sharp first line.
2. Focus on one pain point, observation, or joke.
3. Make the wording feel native to X.
4. Keep it easy to post as-is.

## Modes

### Standard Tweet

Use for product, founder, engineering, launch, insight, or opinion posts.

- Usually under 280 characters.
- Under 220 is often better.
- Clean, punchy, and direct.
- If the user gives raw notes, turn them into polished tweet drafts.

### Shitpost Mode

Use when the user asks for a shitpost, spicy tweet, memey post, banter, or a more unhinged/relatable engineering tone.

For extra angle ideas, see `references/shitposting.md`.

- Punch up at tools, hype, pricing, process theater, and broken workflows.
- Do not punch down at junior engineers.
- Focus on the absurdity of modern software work.
- Pain points that work well: cloud bills, flaky tests, AI-generated code, observability chaos, infra debt, LeetCode irony, Friday deploys.
- The goal is relatability and engagement, not direct selling.
- Do not force product mentions unless the user explicitly wants promo.

## Variation Strategy

The 3 variants should not be trivial rewrites.

- Variant 1: safest and cleanest
- Variant 2: sharper / more opinionated
- Variant 3: most playful, memey, or aggressive within reason

## Cleanup Rules

Before finalizing, remove:

- PR-sounding language
- generic hype words
- vague “future of” phrasing
- fake breadth like “whether you’re X or Y”
- bloated setup before the point

## If the User Gives Context

If the user provides notes, links, rough ideas, screenshots, or bullets:

- preserve the core claim
- compress aggressively
- keep the strongest detail
- write as if the user could post it immediately

## Approved Draft Tracking (Gold Standard)

When the user approves a tweet or thread draft:

1. **Save to Vault:** Use `vault_write` to create a new note in `knowledge/notes/twitter-drafts-*.md`.
2. **Template:** Use the Gold Standard template with `note_type: "asset"` and `status: "evergreen"` for approved drafts.
3. **Continuity:** Before starting a new writing task, always check `vault_search` for previous approved drafts to maintain style and context.
4. **Style Guide:** Raw technical honesty, no corporate polish, price transparency.

## If the User Asks for a Thread

- still provide 3 variants unless they ask for one
- each variant can be a short thread
- keep each tweet self-contained and readable
