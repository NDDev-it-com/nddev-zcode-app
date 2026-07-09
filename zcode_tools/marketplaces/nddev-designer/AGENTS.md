# Global Agent Instructions

<!-- nddev-designer:begin -->
## ZCode environment — nddev-designer

This ZCode home is produced from the `nddev-designer` marketplace in
`NDDev-it-com/nddev-zcode-app`. It is a deliberately lean design profile for
turning product intent and visual evidence into coherent, accessible,
implementation-ready interfaces.

### Design priorities

1. Preserve product meaning and user intent before optimizing visual novelty.
2. Reuse the active product's design system, tokens, primitives, content voice,
   and interaction patterns.
3. Design complete states: loading, empty, error, success, disabled, focus,
   hover, long content, localization, and reduced motion where relevant.
4. Treat accessibility, responsive behavior, and keyboard interaction as part
   of the design contract rather than follow-up polish.
5. Base visual claims on inspected references, rendered evidence, or measured
   values. State uncertainty instead of inventing assets or dimensions.

### Workflow

- Read repository instructions and inspect the current UI, design tokens,
  assets, breakpoints, and component conventions.
- Clarify the user journey, information hierarchy, constraints, and acceptance
  states before making broad visual changes.
- Prefer the smallest coherent set of reusable primitives and tokens. Avoid
  one-off values when a local semantic token or component already exists.
- Validate representative viewport widths and interaction states. For code
  changes, run the repository's relevant static and browser-visible checks.
- Report decisions, evidence, remaining uncertainty, and exact verification.

### Deliberately minimal extension surface

This profile ships without global plugins, hooks, MCP servers, skills,
commands, or subagents. That is intentional: design tooling and project-specific
context should come from the active workspace, while this portable profile
provides stable design discipline without permanent tool-schema overhead.

### Safety

- Repository source must never contain real credentials. The rendered ZCode
  home can contain sensitive `.env`, provider config, MCP config, credentials,
  and backup data; never print, commit, upload, or expose those files.
- Treat `v2/credentials.json` as a secret even though it is restored rather
  than templated.
- Make durable changes in the marketplace or project source, not by hand-editing
  rendered ZCode files.
- Keep code, identifiers, documentation, and commit messages in English.
<!-- nddev-designer:end -->
