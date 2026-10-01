# Hyperframes Composition Brief: DataPilot

## Objective
Create a short, premium launch-style brag video for DataPilot, an AI-powered BI copilot that translates plain English into validated SQL and grounded data visualisations over PostgreSQL databases.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 19.0 seconds

## Source Material
- Project root: `C:/Users/Ankit_Johari/Downloads/GOD_POC/DataPilot`
- Primary files read:
  - `frontend/src/App.tsx`
  - `frontend/src/App.css`
  - `ARCHITECTURE.md`
  - `README.md`
- Product name: DataPilot
- Tagline / strongest claim: "AI Layer on your Database. Ask plain English. Run verified SQL. Zero hallucinations."
- Key UI or visual moment to recreate:
  - Connected database status pill (`Connected to: Sales Database`)
  - Natural language input bar with question: `"Which products are losing money after discounts?"`
  - Semantic table match chips (`dim_product`, `fact_sales`)
  - SQL code box with SQLGlot validation badge
  - Interactive Recharts-style BI chart (revenue bars & negative profit callouts)
  - Grounding badge: `"Grounded in 142 returned rows • 0 hallucinations"`
  - Brand lockup with golden `DP` logo mark
- Copy that must appear verbatim:
  - "Which products are losing money after discounts?"
  - "Connected to: Sales Database"
  - "SQLGlot Verified: Read-Only"
  - "Grounded in 142 returned rows • Zero hallucinations"
  - "DataPilot: AI Layer on your Database"

## Creative Direction
- Tone preset: `polished`
- Creative direction: Modern developer & data tool product film — clean, confident, technical, and premium.
- Interpretation: Restrained elegance, dark surface palette with warm amber and emerald accents, crisp typography (`Plus Jakarta Sans` + `JetBrains Mono`), fast-in snappy motion followed by generous legible reading holds.
- Angle: Modern BI takes weeks, and LLMs hallucinate numbers. DataPilot gives executives and analysts instant verified SQL and charts grounded purely in real database rows.
- Hook: The question prompt typing out in a sleek dark UI.
- Outro / punchline: DataPilot logo slam with the golden monogram, tagline, and call to action.
- Avoid:
  - Generic SaaS buzzwords
  - Abstract 3D floating spheres or irrelevant stock visuals
  - Flashy rainbow gradients that clash with the product's warm minimal theme

## Visual Identity
- Background: `#1F1E1C` (Surfaces: `#252420`, `#2A2926`)
- Text: `#EDEAE4` (Muted: `#9C978E`)
- Accent: `#f2d252` (warm amber/gold), `#4E9F6E` (success emerald), `#C24A3F` (loss crimson)
- Border: `#3A3834`
- Display font: `Plus Jakarta Sans`, sans-serif
- Body font: `Plus Jakarta Sans`, sans-serif
- Monospace font: `JetBrains Mono`, monospace
- Visual references from the project: The real DataPilot header, status pill, question prompt, suggestion chips, results table, Recharts combo chart, and SQL inspection drawer.

## Storyboard
Total duration: 19.0s.
1. **The Prompt Hook** — 3.2s — Minimalist dark UI opens, pulsing status pill ("Connected to: Sales Database"), prompt bar types out `"Which products are losing money after discounts?"` and clicks Send.
2. **The Semantic & Safety Engine** — 4.3s — Semantic embedding chips slide in (`dim_product` 96.4%, `fact_sales` 98.1%), SQL query generates with syntax highlighting, green shield badge activates: `✓ SQLGlot Verified: Read-Only`.
3. **Instant BI & Grounded Insights** — 7.0s — Dynamic multi-series chart animates in (Sales vs Profit Margin), loss leader callout, grounding badge (`Grounded in 142 rows • Zero hallucinations`), and "View query details" drawer.
4. **Outro & Lockup** — 4.5s — Golden DP logo mark pulses into full scale, title "DataPilot", subtitle "AI Layer on your Database", tagline "Ask plain English. Run verified SQL. Zero hallucinations."

## Audio
- Audio role: Steady, clean, corporate-tech modern groove.
- Audio arc: Opens with focused rhythmic typing, swells as the query and safety check run, blossoms on the chart payoff, resolves on a deep bell hit for the logo.
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: Plays throughout (0.0s to 19.0s) at 0.32 volume, fading smoothly over the last 1.2 seconds.
- Music cue guidance: 109.96 BPM. Strong cues at 8.74s, 13.11s, 17.47s.
- Audio-reactive treatment: Subtle ambient glow behind the dashboard and logo card breathing with the music track.
- Audio-coupled moments:
  - 0.6s - 2.0s: Tactile keypress sounds for typing.
  - 4.8s: Verification toggle chime (`switch_001.ogg`) on SQLGlot check.
  - 7.6s: Impact drop (`interface/drop_001.ogg`) on chart and insight reveal.
  - 14.5s: Resonant bell (`impact/impactBell_heavy_000.ogg`) on logo lockup.
- Exact SFX choice: Copied into `composition/assets/sfx/`.

## Hyperframes Instructions
- Show real UI components and design tokens from DataPilot.
- Keep all typography legible with high WCAG contrast compliance.
- Keep total composition duration exactly 19.0 seconds.
- Ensure audio files are relative paths within the `composition/` directory.
- Pass `hyperframes check` before rendering.
