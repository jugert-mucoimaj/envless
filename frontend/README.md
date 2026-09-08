# envless command centre

The screen where a name and a value go in and get saved. Next.js App Router,
talking to the backend at `NEXT_PUBLIC_ENVLESS_API`.

```powershell
npm install
copy .env.example .env.local
npm run dev          # http://localhost:3000
```

The backend must be up on port 8000, or the panel says so and does nothing else.

In a container:

```powershell
docker build -t envless-centre --build-arg NEXT_PUBLIC_ENVLESS_API=http://127.0.0.1:8000 ./frontend
docker run --rm -p 3000:3000 envless-centre
```

`NEXT_PUBLIC_ENVLESS_API` is read by the browser, not by the container, so it
is compiled into the client bundle at **build** time. It has to be an address
the browser can reach — the published host port, never a compose service name
— and changing it means rebuilding the image. `output: "standalone"` in
`next.config.ts` is what keeps the runtime image free of `node_modules` and the
build toolchain.

## The design

It is drawn as a railway interlocking panel, because the job is the same one: a
change to a live environment is only safe if you can see what is currently
running on it. Every environment carries an aspect — **clear**, **caution** or
**danger** — which is a real column in the database, not decoration, and it
drives the signal lamps.

- **The promotion line** across the top is the hero: development → staging →
  production drawn as track, with a signal at each environment and the one you
  are looking at illuminated like an occupied block.
- **Surfaces are bevelled, not shadowed.** A plate has a light top edge and a
  dark bottom edge, and a 2px radius. Painted metal has no rounded cards on it.
- **Lamps only light when they mean something.** A row's lamp is an unlit berth
  until that value moves, and then it flashes once in the environment's own
  aspect. That single flash is the only motion the page makes on its own.
- **Colour**: fascia `#C6CCC2`, plate `#D8DCD3`, ink `#191C18`, and the three
  aspects `#2F6F4E` / `#B8892B` / `#8C2F39`.
- **Type**: Barlow for the interface, Barlow Semi Condensed for panel labels,
  IBM Plex Mono for keys and values — where monospace is literally correct.

Row controls stay hidden until a row is hovered or focused. Seventeen rows each
repeating "Copy · Mark secret · Remove" is noise; the controls remain in the
document and reachable by keyboard.

## The files

| | |
|---|---|
| `app/globals.css` | the whole design system: tokens, plates, lamps, controls |
| `components/CommandCentre.tsx` | the shell — selection, loading, live updates, actions |
| `components/RouteDiagram.tsx` | the promotion line |
| `components/VariableRow.tsx` | one variable: read, reveal, edit, rename, remove |
| `components/CommandPalette.tsx` | Ctrl-K — jump to an environment or start a job |
| `components/TokensPanel.tsx` | issuing and revoking what applications read with |
| `components/ConsumersPanel.tsx` | what is reading this environment, from where, on which version |
| `components/AlertsPanel.tsx` | the few entries flagged for attention, and what to do about each |
| `components/ImportPanel.tsx` | pasting a .env file in |
| `components/Drawer.tsx` | the over-panel the side panels above open in |
| `hooks/useLiveChanges.ts` | the connection that keeps the panel current |
| `lib/api.ts` | every call to the backend, with readable errors |

## Rotating

**Rotate** on a secret row opens the editor with the value blank. That is
deliberate — rotating means replacing the value, and showing the compromised
one only invites pasting it back. **Generate** fills in a fresh one for
credentials envless itself mints.

Above the table, a strip says how many running applications are on the current
value and names any that are not. It comes from the environment's status, which
the panel polls, so it settles on its own as each one catches up.

The **Alerts** lamp in the top bar lights when a token reads from an unfamiliar
address or reads far more often than an application should.

## Getting around

- **Ctrl-K** opens the command palette.
- **/** focuses the filter.
- **Enter** in a row saves, **Escape** abandons the edit.

## Notes

- Selection is derived, not synchronised: the panel keeps what you last picked
  and falls back to something real if it disappears, so an environment deleted
  elsewhere never leaves a blank screen.
- Writes return the value in full — you just typed it — and the panel puts a
  secret back behind its mask before storing it in the list.
- `allowedDevOrigins` in `next.config.ts` covers both `localhost` and
  `127.0.0.1`. Without it, Next blocks its own dev resources on whichever one
  it did not start under and the page never hydrates.
