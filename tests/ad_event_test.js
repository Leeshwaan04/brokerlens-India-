'use strict';
// Unit test for api/ad-event.js: run with `node tests/ad_event_test.js`. Prints PASS/FAIL lines and a summary.
const path = require('path');
const handler = require(path.join(__dirname, '..', 'api', 'ad-event.js'));
let pass = 0, fail = 0;
const logs = [];
const origLog = console.log;
console.log = (...a) => logs.push(a.join(' '));
function mk(method, origin, body, ip) {
  const headers = {}; if (origin) headers.origin = origin; headers['x-forwarded-for'] = ip || '1.2.3.4';
  return { method, headers, body };
}
function run(req) {
  return new Promise((resolve) => {
    const res = { headers: {}, setHeader(k, v) { this.headers[k] = v; }, status(s) { this.code = s; return this; }, end() { resolve(this); } };
    handler(req, res);
  });
}
const good = { v: 1, t: 'click', ad: 'ibsl', slot: 'wide', pt: 'ipo', path: '/ipo/kfintech/', ref: 'www.google.com', dev: 'd' };
function check(name, cond) { (cond ? pass++ : fail++); origLog((cond ? 'PASS ' : 'FAIL ') + name); }
(async () => {
  let r = await run(mk('POST', 'https://www.brokerlens.in', good));
  check('valid same-site event is accepted with 204 and no body', r.code === 204);
  check('accepted event is logged once as a structured line', logs.length === 1 && JSON.parse(logs[0]).evt === 'ad' && JSON.parse(logs[0]).pt === 'ipo');
  check('logged line carries no ip, user agent or headers', !/1\\.2\\.3\\.4|user-agent|forwarded|origin/i.test(logs.join(' ')));
  r = await run(mk('POST', 'https://evil.example', good));
  check('cross-site origin is refused (403)', r.code === 403);
  r = await run(mk('POST', null, good));
  check('missing origin is refused (403)', r.code === 403);
  r = await run(mk('GET', 'https://www.brokerlens.in', good));
  check('GET is refused (405)', r.code === 405 && r.headers.Allow === 'POST');
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, t: 'close' }));
  check('close is no longer an accepted event type (banners have no close button) (400)', r.code === 400);
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, ad: 'zerodha' }));
  check('unknown advertiser is rejected (400)', r.code === 400);
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, path: '/x"><script>' }));
  check('path with markup characters is rejected (400)', r.code === 400);
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, ref: 'a b' }));
  check('malformed referrer host is rejected (400)', r.code === 400);
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, extra: 'x'.repeat(700) }));
  check('oversized body is rejected (413)', r.code === 413);
  r = await run(mk('POST', 'https://www.brokerlens.in', '{not json'));
  check('invalid JSON string is rejected (400)', r.code === 400);
  r = await run(mk('POST', 'https://www.brokerlens.in', { ...good, injected: '<b>x</b>' }));
  check('unknown extra fields are dropped, not logged', r.code === 204 && !logs[logs.length - 1].includes('injected'));
  let last = 0;
  for (let i = 0; i < 130; i++) { r = await run(mk('POST', 'https://www.brokerlens.in', good, '9.9.9.9')); last = r.code; }
  check('per-address rate limit kicks in (429) after 120 events', last === 429);
  check('responses never set CORS headers', !('Access-Control-Allow-Origin' in r.headers));
  console.log = origLog;
  origLog('\n' + pass + ' passed, ' + fail + ' failed');
  process.exit(fail ? 1 : 0);
})();
