# Brag Plan: DataPilot

## What is this app?
DataPilot is an AI business intelligence copilot on PostgreSQL databases that translates plain-English business questions into validated SQL, auto-runs diagnostic breakdown queries, and renders interactive charts with answers strictly grounded in actual database rows.

## The angle
BI dashboards take weeks to build and ChatGPT hallucinates fake numbers. DataPilot bridges the gap: ask natural business questions, watch it match tables with semantic embeddings, validate read-only SQL through SQLGlot, and return instant charts grounded strictly in real Postgres rows.

## Hook (first 2-3 seconds)
A focused query prompt in a sleek dark-themed workspace. The prompt types out a real-world, high-stakes question: `"Which products are losing money after discounts?"`

## Key moments (the middle)
1. **The Semantic & Safety Pipeline**: Instant table retrieval (`dim_product` + `fact_sales`) with cosine similarity confidence, followed by automated SQLGlot syntax & read-only verification (`✓ Read-Only & Schema Verified`).
2. **Interactive Visualization & Grounding**: A multi-series Recharts-style combo chart pops in with negative profit callouts, accompanied by an executive insight summary and an explicit proof badge: `"Grounded in 142 returned rows • Zero hallucinations"`.
3. **Inspectable Query & Actions**: "View query details" expands real generated SQL with a "Copy SQL" button and "★ Save insight" interaction.

## Outro / punchline
DataPilot logo lockup with the golden mark and tagline:
**DataPilot: AI Layer on your Database.**
"Ask plain English. Run verified SQL. Zero hallucinations."

## User flow worth showing
Entry → Key Action → Result:
1. User enters natural question into prompt bar.
2. Pipeline identifies tables via embeddings, writes query, and passes strict SQLGlot validation.
3. System renders interactive chart + verified narrative + inspectable SQL.

## Tone
- **Preset**: `polished`
- **Creative direction**: Modern developer & data tool product film — clean, confident, technical, and premium.
- **Interpretation**: Crisp typography, high contrast, elegant dark UI with warm amber highlights, snappy transitions, and zero corporate fluff.

## Format: landscape — 1920x1080
## Duration: 19.0 seconds

## Visual identity (from the project)
- Background: `#1F1E1C` (Dark surface `#252420`, `#2A2926`)
- Accent: `#f2d252` (warm amber/gold) and `#4E9F6E` (success green) / `#C24A3F` (error red)
- Text: `#EDEAE4` (muted `#9C978E`)
- Border: `#3A3834`
- Display font: `Plus Jakarta Sans`, sans-serif
- Body font: `Plus Jakarta Sans`, sans-serif
- Monospace font: `JetBrains Mono`, monospace
- Strongest visual element: The clean dark-mode chat card with Recharts visualization, SQL badge, and status pill (`Connected to: Sales Database`).

## Share copy (draft)
DataPilot turns plain English into validated SQL and instant charts — strictly grounded in your database with zero hallucinations.

## Audio direction
- Role: Steady, confident modern tech bed with sparse, tactile interface accents.
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: Starts at 0.0s, steady volume at 0.32, subtle swell into the chart reveal, gentle fade-out in the final second.
- Music cue guidance: Preset available (109.96 BPM). Useful cues: 8.74s (reveal candidate), 13.11s (strong beat), 17.47s (outro transition), 18.56s (final logo hold).
- Audio-reactive treatment: Subtle; background ambient glow and card highlight breathe with track RMS.
- SFX posture: Sparse, motion-matched, tactile.
- Audio-coupled moments:
  - 0.8s - 2.4s: Keyboard typing ticks as the prompt is typed.
  - 4.8s: Verification toggle chime (`switch_001.ogg` or `select_008.ogg`) on SQL safety check.
  - 7.6s: Impact drop (`interface/drop_001.ogg` or `impactSoft_medium_001.ogg`) as the chart and insight cards snap into view.
  - 14.5s: Resonant bell (`impact/impactBell_heavy_000.ogg`) on the final logo lockup.
- Restraint rule: No cheesy cartoony swooshes, no loud explosions; only clean digital and acoustic impacts.

## Storyboard

### Scene 1 — The Prompt Hook — 3.2s (0.0s - 3.2s)
The screen opens on the dark minimalist DataPilot interface. The status pill pulses: "Connected to: Sales Database".
The prompt bar activates, and the question types in with rapid tactile keystrokes:
`"Which products are losing money after discounts?"`
A glowing cursor blinks and the Send button triggers.
Sequential/interaction: Cursor types question character-by-character, then Send button activates.
Audio intent: Immediate focus, rhythmic human action.
Audio-coupled idea: Keyboard tick sounds on typing.
Music: Steady intro groove establishing tempo.
Transition mood: Snappy zoom/push → Scene 2

### Scene 2 — Semantic Engine & SQLGlot Validation — 4.3s (3.2s - 7.5s)
The query expands into the AI pipeline visualization.
Two table chips slide in: `dim_product` (96.4% match) and `fact_sales` (98.1% match).
Generated SQL block scrolls in:
`SELECT product_name, SUM(sales), SUM(profit) FROM fact_sales JOIN dim_product ... WHERE discount > 0.20 GROUP BY 1 HAVING SUM(profit) < 0`
A green shield badge illuminates: `✓ SQLGlot Verified: Read-Only • Schema Grounded`.
Sequential/interaction: Table chips pop in one by one, SQL generates, check badge locks.
Audio intent: Technical confidence, precision.
Audio-coupled idea: Subtle click/select sound on table chips and verification badge lock.
Transition mood: Clean slide → Scene 3

### Scene 3 — Instant BI & Grounded Insights — 7.0s (7.5s - 14.5s)
The answer card springs to life in full fidelity.
A dynamic Recharts visualization renders: Bars showing Revenue, with a red alert line showing negative profit margins.
Beside it, the verified summary appears:
"3 products operate at net negative margin after 25%+ discounts. Top loss leader: Office Pro Desk (-$4,820)."
Grounding pill: `Grounded in 142 Postgres rows • 0 Hallucinations`.
Interactive UI: The "View query details" accordion expands with copy button, and "★ Saved" lights up.
Sequential/interaction: Chart bars grow up, insight text slides in, grounding badge dings.
Audio intent: High payoff, satisfaction of instant clarity from messy data.
Audio-coupled idea: Soft impact/drop at 7.6s when the chart arrives, subtle success ping on grounding badge.
Transition mood: Elegant dissolve → Scene 4

### Scene 4 — Outro / Punchline — 4.5s (14.5s - 19.0s)
The view resolves to the centered DataPilot brand mark.
The golden DP monogram logo pulses softly with ambient glow.
Title: **DataPilot**
Subtitle: **AI Layer on your Database**
Callout: "Ask plain English. Run verified SQL. Zero hallucinations."
URL / Action: `datapilot.dev • Connect Postgres in 60s`
Sequential/interaction: Logo slam, text fade-up, final ambient hold.
Audio intent: Authoritative closure, memorable branding.
Audio-coupled idea: Resonant bell (`impactBell_heavy_000`) at 14.6s.
Transition mood: Final hold to end.

**Music mood for this video:** Upbeat, steady, clean corporate-tech.
**Audio summary:** Starts with focused typing over a clean bass groove, builds through the SQL verification beat, lands on an expansive chart reveal, and resolves to a resonant bell under the logo lockup.
