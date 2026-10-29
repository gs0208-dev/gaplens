# Design system

GapLens is a working tool for people who read documents closely. The interface should feel like a well-made reference tool: calm, dense, precise. It should not look like a landing page or a template.

Stack: Tailwind CSS, shadcn/ui components (source lives in `src/components/ui/`), `lucide-react` icons. shadcn/ui was chosen over Material UI (ADR-005).

## Principles

1. Content first. The document and its findings are the interface; chrome stays quiet.
2. Density with clarity. Show real information at a readable size; use whitespace to group, not to pad.
3. One accent. Color carries meaning, not decoration.
4. Every state is designed: loading, empty, error, long, and very long.
5. Keyboard and screen reader users get the same product.

## Anti-slop checklist

Reject a design or a pull request if any of these appear.

- Emojis anywhere, including toasts, empty states and commit messages.
- Gradients used as decoration (hero backgrounds, buttons, text, borders). Purple-to-blue gradients in particular.
- Glassmorphism, blurred translucent panels, glowing shadows, neon accents.
- A marketing hero section, a "three feature cards" grid, floating decorative blobs, stock or AI-generated illustrations, abstract mesh backgrounds.
- Every element wrapped in a rounded card with a drop shadow. Cards are used only when the content is a distinct object.
- Placeholder copy: "Lorem ipsum", "Unlock the power of", "Seamless", "Supercharge", "Revolutionize", "Effortlessly", "Welcome back!".
- Exclamation marks, rhetorical questions, or chatty microcopy.
- Icon-only buttons without an accessible name and tooltip.
- Mixed icon sets, or icons at arbitrary sizes.
- Inline hex colors, one-off pixel values, or fonts not defined here.
- Centered everything. Left-align text and data.
- Animation that does not explain a change of state.

## Layout

- App shell: left sidebar 240 px (collapsible below 1024 px), top bar 48 px, content area. Content max width 1120 px for lists and settings; the document workspace uses the full width.
- Document workspace: two panes. Left, the document text with section labels and highlight on the cited quote. Right, tabs for Report and Chat. On narrow screens the panes become tabs.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48 px (Tailwind `1, 2, 3, 4, 6, 8, 12`). Nothing else.
- Responsive: usable at 360 px wide. No horizontal page scroll. Tables turn into stacked rows below 640 px.
- Grid: align to the spacing scale. Group related controls; separate groups with 24 px or a border, not both.

## Tokens

Defined once in `src/styles/tokens.css` as CSS variables and mapped in the Tailwind theme. Components use semantic names only.

Neutral scale (cool gray) with one accent (a deep teal) keeps the tool serious and avoids the default blue and purple look. Final values are chosen once during Sprint 3 and must meet the contrast targets below.

| Token | Use |
|---|---|
| `background`, `surface`, `surface-muted` | Page, panels, table stripes and code blocks |
| `foreground`, `foreground-muted` | Primary and secondary text |
| `border`, `border-strong` | Dividers and input borders |
| `accent`, `accent-foreground`, `accent-subtle` | Primary buttons, links, focus ring, selected state |
| `severity-high`, `severity-medium`, `severity-low` | Finding severity (text, border and subtle background) |
| `success`, `warning`, `danger`, `info` | Status messages and badges |

Contrast: body text at least 4.5:1, large text and UI boundaries at least 3:1, in light and dark themes. Check with a contrast tool; do not estimate by eye.

Themes: light first, dark second, both driven by the same variables (`.dark` class). Do not ship a theme that has not been checked.

## Typography

- Sans: IBM Plex Sans. Mono: IBM Plex Mono, used for quotes from the document, section labels, ids and code. Both self-hosted through `@fontsource` packages (no third-party font requests, see `docs/security.md`).
- Scale: 12 (captions), 14 (default UI), 16 (document text), 20 (section titles), 24 (page titles), 32 (rare). Line height 1.5 for text, 1.25 for headings.
- Weights: 400, 500, 600 only. Sentence case everywhere. No all-caps text except short badges.
- Document text is set at 16 px, line length 60 to 80 characters, so reading is comfortable.

## Shape and depth

- One border radius for controls and panels: 6 px. Pills only for badges.
- Prefer 1 px borders to shadows. Shadows only on floating layers (menus, dialogs, toasts), one soft shadow value.
- Focus ring: 2 px accent ring with 2 px offset, always visible on keyboard focus.

## Components

Use these shadcn/ui components: Button, Input, Textarea, Label, Form, Dialog, AlertDialog, DropdownMenu, Tabs, Table, Badge, Skeleton, Tooltip, ScrollArea, Separator, Sonner (toasts), Progress. Add others only when a screen needs them.

Rules:
- Primary button: one per view. Destructive actions use a destructive variant and an AlertDialog with the resource name.
- Tables for lists of documents. Findings are a list of expandable rows, not cards.
- Badges for status and severity always contain text. Never use color alone.
- Forms: label above the input, helper text below, inline error text under the field, error summary at the top for submit failures.
- Toasts for confirmations only. Errors that need action stay inline.

## Icons

- Library: `lucide-react` only.
- Sizes: `size-4` (16 px) inline with text and in buttons, `size-5` (20 px) standalone. Default stroke width. Use `aria-hidden` on decorative icons; icon-only buttons get `aria-label` and a tooltip.
- Mapping (keep consistent): upload `Upload`, document `FileText`, delete `Trash2`, search `Search`, settings `Settings`, sign out `LogOut`, high severity `CircleAlert`, medium `TriangleAlert`, low `Info`, success `CircleCheck`, copy `Copy`, external `ExternalLink`, loading `Loader2` with a spin animation.

## Screens

| Screen | Contents |
|---|---|
| Sign in, Register | Single column form, 400 px wide, product name as text, no illustration |
| Documents | Table: title, status badge, pages, uploaded date, actions menu. Upload button top right. Empty state: one sentence and the upload button |
| Upload dialog | File drop area plus a file button, accepted types and size stated, progress, validation errors inline |
| Document workspace | Header with title and status; left document pane; right tabs Report and Chat |
| Report tab | Summary, counts by severity, filter by kind and severity, findings list. Each finding: title, kind and severity badges, description, evidence quotes with section labels (click scrolls and highlights in the document pane), suggested client question with copy button, status control (open, confirmed, dismissed) |
| Chat tab | Message list, input at the bottom, answers with numbered citations that highlight the source; not-found answers styled as a neutral note |
| Settings | Account email, sign out, delete account (AlertDialog) |

## States

- Loading: skeletons that match the final layout. A spinner only inside a button during a submit.
- Processing documents: a progress row with the current stage in words (extracting, chunking, embedding).
- Empty: one plain sentence and the next action.
- Error: what happened, what to do, the request id in small text, a retry button where it makes sense.
- Long content: truncate with an expand control; never break the layout.
- Offline or failed network: banner at the top, actions disabled with a reason.

## Copy

- Sentence case, plain verbs, present tense. Say what happened and what to do next.
- Name things the same way everywhere: "document", "report", "finding", "suggested question".
- Good: "Upload a PDF or text file up to 5 MB." Bad: "Drop your files and let the magic happen!"
- Good: "The report could not be generated. Try again in a few minutes." Bad: "Oops! Something went wrong."
- Not-found chat answer: "This is not covered in the document." followed by what the document does say about the nearest topic, if anything.

## Motion

- 150 ms ease-out for opening and closing menus, dialogs and accordions. No bounce, no parallax, no auto-playing animation.
- Respect `prefers-reduced-motion`: remove transitions that move content.

## Accessibility

- WCAG 2.2 AA is the floor.
- Every control reachable and operable by keyboard; logical focus order; focus returns to the trigger when a dialog closes.
- Semantic HTML first (button, nav, main, table). ARIA only to fill gaps.
- Chat answers are announced through an `aria-live="polite"` region.
- Form errors are linked to fields with `aria-describedby`.
- Test with keyboard only and with a screen reader before Sprint 4 sign-off.

## Definition of done for a screen

- Matches the tokens and spacing scale; no inline colors or off-scale values.
- Loading, empty and error states exist and are tested.
- Works at 360 px and at 1440 px, light and dark.
- Keyboard and contrast checks pass.
- Copy follows the rules above and contains no emojis.
