# Netlify deployment

Use Netlify when Render requires a card or Vercel requires phone verification.

## Build settings

- Build command: `mkdir -p public && cp index.html public/index.html`
- Publish directory: `public`
- Functions directory: `netlify/functions`

These settings are already defined in `netlify.toml`.

## Environment variables

Set these in Netlify Site configuration -> Environment variables:

```bash
RAPIDAPI_KEY=your_rapidapi_key_here
RAPIDAPI_TRIPADVISOR_HOST=tripadvisor-com1.p.rapidapi.com
RAPIDAPI_TIMEOUT=12
```

## Routes

- `/api/tripadvisor/search`
- `/api/tripadvisor/reviews`
- `/api/tripadvisor/hotels`
- `/api/tripadvisor/destination`
- `/api/tripadvisor/health`
- `/api/destination/discover`
