import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Every page is per-user and rendered on each request (no ISR, no "use
// cache"), so no incremental cache, tag cache or queue is configured and no
// R2 bucket or KV namespace is needed.
export default defineCloudflareConfig({});
