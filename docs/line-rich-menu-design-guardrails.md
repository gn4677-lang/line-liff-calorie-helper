# LINE Rich Menu Design Guardrails

This file exists to stop the same design mistake from happening again.

The LINE rich menu is not a desktop card layout. It is a persistent mobile launcher made of a single image plus three tappable regions.

## Core Principle

Treat each region as one full-size button.

Do not design the rich menu like:

- three cards with tiny CTA buttons inside
- a desktop dashboard
- a marketing banner with explanatory copy

Design it like:

- three large mobile launcher buttons
- one clear label per region
- one clear icon per region
- the entire block is tappable

## Non-Negotiable Rules

- No small descriptive text.
- No fake CTA text such as `點一下`, `打開`, `開始`, `查看更多`.
- No nested visual hierarchy that suggests only a small sub-area is clickable.
- No loud or cheap-looking saturated colors.
- No decorative empty space that does not improve touch clarity or hierarchy.
- No desktop card language.

## Visual Rules

- Use three equally weighted blocks.
- Keep labels short:
  - `今日日誌`
  - `吃什麼`
  - `身體策略`
- Each block should have:
  - one large title
  - one simple icon
  - one restrained background color
- Prefer soft, low-saturation colors.
- Prefer neutral backgrounds and gentle contrast over bright gradients.
- The label should remain the visual anchor, not the icon.

## Interaction Rules

- The whole region is the button.
- Never draw an inner button inside the region.
- Never imply a second tap target inside the same region.
- Rich menu should feel instant and obvious inside LINE chat.

## Product Rules

- Rich menu is for launching surfaces, not for teaching the product.
- Explanations belong in LIFF or LINE messages, not in the rich menu artwork.
- Rich menu should feel stable and familiar, not dynamic or promotional.

## Review Checklist

Before shipping a new rich menu, verify all of the following:

- Does each section read as one entire button?
- If you remove the LINE tap map, would a user still assume the whole block is tappable?
- Is there any small helper copy that can be removed?
- Is there any fake CTA that should not exist?
- Are the colors calm enough to feel product-grade rather than ad-like?
- Does it look correct in a chat launcher context, not a desktop UI context?

## Current Decision

Current preferred direction:

- three large rounded rectangular blocks
- no subtitles
- no CTA pills
- muted palette
- simple icon + bold title only

If a future revision violates these rules, treat it as a design regression.
