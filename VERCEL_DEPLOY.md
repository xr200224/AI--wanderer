# Vercel deployment

This project can be deployed to Vercel without binding a credit card.

## Environment variables

Set these variables in Vercel Project Settings -> Environment Variables:

```bash
RAPIDAPI_KEY=your_rapidapi_key_here
RAPIDAPI_TRIPADVISOR_HOST=tripadvisor-com1.p.rapidapi.com
RAPIDAPI_TIMEOUT=12
```

## Notes

- `index.html` is served as the static frontend.
- `/api/tripadvisor/*` and `/api/destination/discover` are Vercel Python Functions.
- Do not put `RAPIDAPI_KEY` in frontend code.
