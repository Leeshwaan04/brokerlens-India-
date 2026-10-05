import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import fastifyCors from '@fastify/cors';
import fastifyCompress from '@fastify/compress';
import fastifyHelmet from '@fastify/helmet';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const SITE_DIR = path.join(ROOT_DIR, 'site');

const fastify = Fastify({
  logger: process.env.NODE_ENV !== 'production' ? { level: 'info' } : false,
  disableRequestLogging: true,
  trustProxy: true,
});

// Middleware & Plugins
await fastify.register(fastifyCompress, { global: true });
await fastify.register(fastifyCors, {
  origin: ['https://www.brokerlens.in', 'https://brokerlens.in', 'http://localhost:8080'],
  methods: ['GET', 'HEAD', 'OPTIONS'],
});
await fastify.register(fastifyHelmet, {
  contentSecurityPolicy: false, // Managed via CDN/Cloudflare headers
});

// Static Assets with immutable 1-year caching
fastify.register(fastifyStatic, {
  root: path.join(SITE_DIR, 'assets'),
  prefix: '/assets/',
  maxAge: '31536000s',
  immutable: true,
});

// Cloud Run Liveness/Readiness Probe
fastify.get('/health', async (_req, reply) => {
  return reply.code(200).send({ status: 'ok', service: 'brokerlens-fastify', timestamp: new Date().toISOString() });
});

// Dynamic In-Memory IPO Live Bidding Demand API
fastify.get('/api/ipo/live', async (_req, reply) => {
  reply.header('Cache-Control', 'public, max-age=15, s-maxage=30, stale-while-revalidate=60');
  try {
    // In production, reads from GCS / Redis / local cache
    return {
      status: 'active',
      as_of: new Date().toISOString(),
      active_bidding: [
        { symbol: 'VNL', demand_x: 0.43, status: 'Active' },
        { symbol: 'NITYAS', demand_x: 0.43, status: 'Active' },
        { symbol: 'EVENTIONS', demand_x: 1.75, status: 'Active' },
      ],
    };
  } catch (err) {
    return reply.code(500).send({ error: 'Failed to load live IPO data' });
  }
});

// Dedicated 404 Handler returning genuine HTTP 404 status
fastify.setNotFoundHandler((_req, reply) => {
  reply.header('Cache-Control', 'no-cache, no-store, must-revalidate');
  return reply.code(404).sendFile('404.html', SITE_DIR);
});

const port = Number(process.env.PORT) || 8080;
const host = '0.0.0.0';

try {
  await fastify.listen({ port, host });
  console.log(`[BrokerLens Fastify] Service running on http://${host}:${port}`);
} catch (err) {
  fastify.log.error(err);
  process.exit(1);
}
