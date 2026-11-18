# Virtual Trading App - BrokerLens India

Independent Next.js application for virtual equity paper trading and investor education, utilizing delayed end-of-day pricing from official NSE bhavcopy data.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Configuration

Set the required environment variables in `.env.local` (see `.env.example`):
- `DATABASE_URL`: Neon Postgres connection string (from console.neon.tech)
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: Clerk publishable key (from dashboard.clerk.com)
- `CLERK_SECRET_KEY`: Clerk secret key
- `CLERK_WEBHOOK_SIGNING_SECRET`: Clerk webhook secret
- `CRON_SECRET`: Bearer authentication token for `/api/cron/sync-eod-prices`

## Deploy on Cloudflare Pages

This application deploys natively to Cloudflare Pages:
1. Connect this repository to Cloudflare Pages (Project directory: `virtual-trading/`).
2. Set build command: `npm run build` and output directory: `.next`.
3. Add environment variables in Cloudflare Dashboard under Project Settings > Variables and Secrets.
4. Deploy using Cloudflare Pages Git integration or via `npx wrangler pages deploy`.
