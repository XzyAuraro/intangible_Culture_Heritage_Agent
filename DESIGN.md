# Design System: Palace Museum Agent

## 1. Visual Theme & Atmosphere
A premium cultural-heritage interface with a cinematic museum-map entrance, calm gallery pacing, and tactile exhibition browsing. The density is balanced: the map page is immersive and spacious, while gallery and artifact pages carry enough structure for repeated exploration. Motion should feel ceremonial rather than flashy.

## 2. Color Palette & Roles
- **Parchment Canvas** (#F2EADB): primary page background.
- **Ivory Surface** (#FFF8EA): cards, panels, input surfaces.
- **Palace Umber** (#201814): primary text, never pure black.
- **Archive Taupe** (#786D61): secondary copy and metadata.
- **Imperial Vermilion** (#8E2F28): single accent for CTAs, pins, active states.
- **Aged Gold** (#C49A55): metadata emphasis and artifact highlights.
- **Jade Shadow** (#365F54): restrained secondary atmospheric overlays only.
- **Hairline Border** (rgba(99, 68, 44, 0.18)): structural lines.

## 3. Typography Rules
- **Display:** Satoshi or Aptos Display fallback. Large type must use weight and color for hierarchy, not excessive scale.
- **Body:** Satoshi, Aptos, Microsoft YaHei fallback. Relaxed 1.65-1.85 leading, max readable line length.
- **Mono:** system monospace only for technical/debug labels if needed.
- **Banned:** generic serif stacks, pure black, neon gradients, purple/blue AI styling.

## 4. Component Stylings
- **Map Pins:** circular vermilion marker plus ivory label capsule. Active/hover state uses transform and soft shadow, never glow.
- **Cards:** rounded 22-28px, warm border, tinted shadow. Use for artifact tiles and AI panels only.
- **Buttons:** pill-shaped, tactile, no outer glow. Primary is vermilion; secondary is ivory with palace-umber text.
- **Inputs:** rounded 14px, label or contextual placeholder, warm border, ivory fill.
- **Audio:** native control is acceptable, placed only inside AI interaction panels.

## 5. Layout Principles
- Three distinct screens: login/entrance, full-screen map, gallery/detail.
- Do not place map, gallery list, detail text, and AI chat all on one screen.
- Map page is full bleed. Gallery page uses content + AI rail. Detail page uses exhibit object + interpretation column.
- Mobile collapses to single column with no horizontal overflow except intentional artifact carousel.

## 6. Motion & Interaction
- Use opacity and transform only.
- Screen changes fade in quickly.
- Map pins breathe subtly to signal interactivity.
- Artifact cards lift on hover and active tap.
- Avoid decorative animated noise or heavy filters.

## 7. Anti-Patterns
- No emojis.
- No generic dashboard metrics.
- No "next-gen/elevate/seamless" copy.
- No pure black, neon glow, purple AI palette, or three equal feature cards.
- No crowded all-in-one interface.
